"""Paired offline tissue scenarios, same original case frame, no ICP realignment."""
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
from .backend import GNMBackend
from .export import atomic_text, _heat_color
from .io_csv import read_marker_csv
from .tissue import load_table, table_path
from .tissue_application import apply_table
from .validation import finite_array, residual_metrics, sha256_file, validate_outputs


def read_exported_vertices(path, count):
    """Read pipeline OBJ coordinates, serialized to six decimals in world mm."""
    with open(path, encoding='utf-8') as stream:
        points = [[float(x) for x in line.split()[1:]] for line in stream if line.startswith('v ')]
    return finite_array(points, 'exported vertices', (count, 3))


def export_difference_ply(path, vertices, triangles, differences, color_max_mm):
    """Numeric vertex distances with an explicit common colour scale."""
    with atomic_text(path) as stream:
        stream.write('ply\nformat ascii 1.0\ncomment units mm; corresponding vertices in case world frame; no ICP\n')
        stream.write('comment tissue scenario difference; NOT uncertainty or face accuracy\n')
        stream.write(f'comment common_color_scale_max_mm {color_max_mm:.12g}\n')
        stream.write(f'element vertex {len(vertices)}\nproperty float x\nproperty float y\nproperty float z\n')
        stream.write('property uchar red\nproperty uchar green\nproperty uchar blue\nproperty double vertex_difference_mm\n')
        stream.write(f'element face {len(triangles)}\nproperty list uchar int vertex_indices\nend_header\n')
        for vertex, distance in zip(vertices, differences):
            rgb = _heat_color(distance/color_max_mm if color_max_mm > 0 else 0.)
            stream.write(' '.join([*(f'{x:.6f}' for x in vertex), *(str(c) for c in rgb), f'{distance:.12g}'])+'\n')
        for triangle in triangles:
            stream.write('3 '+' '.join(str(int(i)) for i in triangle)+'\n')


def run_comparison(config):
    """Preflight every table; fit each from original targets; publish summary last.

    A fresh <output stem>_tissue_compare directory is required even with overwrite.
    Existing QC gates remain active. No completed summary is written on failure.
    """
    from .pipeline import run_pipeline
    if config.tissue_table or not config.tissue_labels:
        raise ValueError('tissue-compare needs explicit tissue-labels and no tissue-table')
    if config.protocol:
        raise ValueError('Use separately frozen individual protocols for different tissue scenarios')
    if any(getattr(config, k) for k in ('output_error_mesh', 'output_stats', 'output_json', 'output_statistical')):
        raise ValueError('Comparison uses per-table outputs; specify only --output prefix')
    if not isinstance(config.tissue_compare, str):
        raise ValueError('tissue-compare must be a comma-separated list')
    sources = [x.strip() for x in config.tissue_compare.split(',')]
    if len(sources) < 2 or any(not x for x in sources):
        raise ValueError('Supply at least two nonempty table IDs/paths; duplicates allowed')
    cfg = replace(config)
    cfg.fill_default_outputs()
    cfg.validate()
    destination = Path(cfg.output).parent/(Path(cfg.output).stem+'_tissue_compare')
    if destination.exists():
        raise ValueError('Comparison directory exists; choose a fresh --output prefix')
    tables = [load_table(s) for s in sources]
    backend = GNMBackend(cfg.npz)
    targets, _, metadata = read_marker_csv(cfg.input, backend.index_to_label, backend.landmark_vertex_map)
    targets = [t for t in targets if t.label not in cfg.exclude]
    for table in tables:
        apply_table(targets, metadata, table, cfg.tissue_labels, cfg.tissue_axis)
        if cfg.depth_weighting == 'sd':
            from .depth_weighting import marker_weights
            marker_weights(table, [t.label for t in targets], [t.weight for t in targets])
    model = backend.load()
    if cfg.depth_weighting == 'sd' and cfg.skull and not cfg.no_dense_fit and cfg.dense_weight > 0:
        from .geometry import build_scalp_mask, build_face_dense_regions
        from .depth_weighting import region_factors
        scalp = build_scalp_mask(model.mu, model.vertex_groups, model.vertex_group_names)
        faces = [] if cfg.no_face_dense else build_face_dense_regions(model.mu, model.vertex_groups, model.vertex_group_names)
        regions = np.full(model.vertex_count, '', dtype=object)
        regions[scalp] = 'scalp'
        # Same face-first precedence as the deduplicated dense candidate set.
        for name, indices, _ in reversed(faces):
            regions[indices] = name
        for table in tables:
            region_factors(table, regions[regions != ''], cfg.dense_nose_weight)
    protected = [cfg.input, cfg.npz, cfg.skull, cfg.prior, cfg.landmark_map, cfg.case_metadata, cfg.craniometry,
                 *(table_path(s) for s in sources)]
    pinned = {str(Path(p).resolve()): sha256_file(p) for p in protected if p}
    children, outputs = [], [destination/'summary.json']
    for i, (source, table) in enumerate(zip(sources, tables)):
        folder = destination/f'{i:02d}_{table.document["id"]}'
        child = replace(cfg, tissue_compare=None, tissue_table=source, output=str(folder/'face.obj'),
            output_error_mesh=None, output_stats=None, output_json=None, output_statistical=None, overwrite=False)
        child.fill_default_outputs()
        child.validate()
        children.append(child)
        outputs.extend(getattr(child, k) for k in ('output', 'output_json', 'output_error_mesh', 'output_stats', 'output_statistical'))
        outputs.extend(folder/name for name in ('difference_final.ply', 'difference_statistical.ply'))
    validate_outputs(pinned, outputs)
    def unchanged():
        if any(sha256_file(p) != h for p, h in pinned.items()):
            raise ValueError('Comparison input changed between runs; no completed summary')
    unchanged()
    destination.mkdir(parents=True, exist_ok=False)
    reports, surfaces = [], []
    for child, table in zip(children, tables):
        unchanged()
        code = run_pipeline(child)
        if code:
            return code
        report = json.loads(Path(child.output_json).read_text(encoding='utf-8'))
        if report['marker_metadata']['tissue_application']['table']['sha256'] != table.sha256:
            raise ValueError('Table changed since comparison preflight')
        reports.append(report)
        surfaces.append({key: read_exported_vertices(getattr(child, attr), model.vertex_count)
                         for key, attr in [('final', 'output'), ('statistical', 'output_statistical')]})
    unchanged()
    differences = [{k: np.linalg.norm(v-surfaces[0][k], axis=1) for k, v in surface.items()} for surface in surfaces]
    color_max = max(float(d.max()) for run in differences for d in run.values())
    skin = model.group_mask('skin_exterior') if 'skin_exterior' in model.vertex_group_names else None
    results = []
    for i, (child, table, report, surface, difference) in enumerate(zip(children, tables, reports, surfaces, differences)):
        entries = {}
        for key, distance in difference.items():
            path = Path(child.output).parent/f'difference_{key}.ply'
            export_difference_ply(path, surface[key], model.triangles, distance, color_max)
            entries[key] = dict(all_vertices=residual_metrics(distance), skin_exterior=None if skin is None else residual_metrics(distance[skin]),
                                ply=str(path.relative_to(destination)), sha256=sha256_file(path))
        results.append(dict(index=i, table=table.record(), report=str(Path(child.output_json).relative_to(destination)),
            report_sha256=sha256_file(child.output_json), selected_labels=report['marker_metadata']['tissue_application']['replaced_labels'],
            differences_to_first=entries, lambda_used=report['lambda'], solver_converged=report['solver']['converged'],
            qc=report['geometry_quality'], excluded_markers=report['skipped'], auto_excluded=report['auto_excluded']))
    unchanged()
    summary = dict(schema_version=1, status='completed', units='mm', reference_index=0, axis_policy=cfg.tissue_axis,
        source_direction_enforced=False, dense_regions_applied=False, color_scale_max_mm=color_max,
        input_sha256=pinned, tables=results, depth_weighting=cfg.depth_weighting,
        interpretation='Sensitivity to selected marker depths and optional SD weights, NOT uncertainty or anatomical accuracy. Independent fits from original case targets. Corresponding vertices in the case world frame include pose/scale changes; no ICP. Six-decimal OBJ coordinates. All-vertex metrics include internal geometry; inspect skin metrics, QC, convergence and exclusions.')
    with atomic_text(destination/'summary.json') as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    return 0
