"""Explicit paired identity-prior sensitivity, using the unchanged pipeline.

No demographic category, prior distribution, age effect or scientific cutoff is
inferred. Reports describe independent full fits in the original case frame.
"""
import copy
from dataclasses import replace
import json
from pathlib import Path

import numpy as np

from .backend import GNMBackend
from .export import atomic_text
from .identity import active_components
from .prior import load_prior, validate_justification
from .tissue import _json, table_path
from .tissue_compare import read_exported_vertices, export_difference_ply
from .validation import finite_array, residual_metrics, sha256_file, validate_outputs

OUTPUTS = ('output', 'output_statistical', 'output_error_mesh', 'output_stats', 'output_json')
INTERPRETATION = ('Experimental identity-prior sensitivity, NOT uncertainty or anatomical accuracy. '
    'Independent refits in the case world-mm frame include pose, scale and any enabled local-correction '
    'changes; no ICP or post-hoc realignment. Distances use six-decimal exported OBJ coordinates. '
    'All-vertex metrics include internal geometry. No demographic category or soft-tissue ageing is inferred.')


def validate_request(config) -> None:
    """Validate explicit intent without choosing a scientific prior or rationale."""
    reason = config.prior_justification
    validate_justification(reason)
    if reason is not None:
        if not config.prior:
            raise ValueError('prior-justification requires an explicit prior file')
    if not config.prior_compare:
        return
    if type(config.prior_compare) is not bool:
        raise ValueError('prior_compare must be boolean')
    if not config.prior or reason is None:
        raise ValueError('prior-compare requires --prior and --prior-justification')
    if config.protocol or config.profile_constraint or config.tissue_compare or config.exclude_outliers:
        raise ValueError('Prior comparison does not combine with frozen protocols, profile refinement, '
                         'tissue comparison or automatic marker exclusion; use explicit separate runs')
    if any(getattr(config, key) for key in OUTPUTS if key != 'output'):
        raise ValueError('Prior comparison owns per-run outputs; specify only --output prefix')


def _checked_report(child, pinned):
    """Require an intact completed child report and its serialized output files."""
    report = _json(Path(child.output_json).read_text(encoding='utf-8'))
    if report.get('status') != 'completed' or report.get('units') != 'mm':
        raise ValueError('Incomplete prior comparison child report')
    for row in report['inputs'].values():
        path = str(Path(row['path']).resolve())
        if path not in pinned or pinned[path] != row['sha256']:
            raise ValueError('Child report inputs differ from pinned comparison inputs')
    for name in OUTPUTS[:-1]:
        row = report['outputs'][name]
        if (Path(row['path']).resolve() != Path(getattr(child, name)).resolve()
                or row['sha256'] != sha256_file(getattr(child, name))):
            raise ValueError('Child output changed after fitting')
    return report


def run_comparison(config) -> int:
    """Run no-prior then selected-prior scenarios; publish summary only on success.

    Nonzero child exits preserve partial diagnostics without a completed summary.
    Nonconverged but completed child fits remain explicitly diagnostic-only.
    Existing output directories are refused even when overwrite was requested.
    """
    from .pipeline import run_pipeline
    validate_request(config)
    if config.prior_compare is not True:
        raise ValueError('Explicit prior_compare=True required')
    cfg = copy.deepcopy(config)
    prefix = Path(cfg.output) if cfg.output else Path(cfg.input).with_name(Path(cfg.input).stem+'_reconstructie.obj')
    destination = prefix.parent/(prefix.stem+'_prior_compare')
    if destination.exists():
        raise ValueError('Prior comparison directory exists; choose a fresh output prefix')
    children = []
    for name, prior, reason in [('neutral', None, None), ('prior', cfg.prior, cfg.prior_justification)]:
        child = replace(cfg, prior=prior, prior_compare=False, prior_justification=reason,
                        output=str(destination/name/'face.obj'), output_statistical=None,
                        output_error_mesh=None, output_json=None, output_stats=None, overwrite=False)
        child.fill_default_outputs()
        child.validate()
        children.append(child)
    paths = [getattr(cfg, key) for key in ('input', 'npz', 'prior', 'skull', 'landmark_map',
                                          'case_metadata', 'craniometry', 'tissue_directions')]
    if cfg.tissue_table:
        paths.append(table_path(cfg.tissue_table))
    pinned = {str(Path(path).resolve()): sha256_file(path) for path in paths if path}
    backend = GNMBackend(cfg.npz)
    model = backend.load()
    active = active_components(model, cfg.identity_subspace)
    prior = load_prior(cfg.prior, model.identity_dim)
    if prior['sha256'] != pinned[str(Path(cfg.prior).resolve())]:
        raise ValueError('Prior changed during preflight')
    planned = [getattr(child, key) for child in children for key in OUTPUTS]
    planned += [destination/'summary.json', destination/'comparison.txt',
                destination/'difference_final.ply', destination/'difference_statistical.ply']
    validate_outputs(pinned, planned)

    def unchanged():
        if any(sha256_file(path) != digest for path, digest in pinned.items()):
            raise ValueError('Comparison input changed between runs; no completed summary')

    unchanged()
    destination.mkdir(parents=True, exist_ok=False)
    reports, surfaces = [], []
    for child in children:
        unchanged()
        code = run_pipeline(child)
        if code:
            return code
        unchanged()
        report = _checked_report(child, pinned)
        reports.append(report)
        surfaces.append({key: read_exported_vertices(getattr(child, name), model.vertex_count)
                         for key, name in [('final', 'output'), ('statistical', 'output_statistical')]})
    if ([(r['label'], r['vertex'], r['target_mm'], r['weight']) for r in reports[0]['landmarks']]
            != [(r['label'], r['vertex'], r['target_mm'], r['weight']) for r in reports[1]['landmarks']]):
        raise ValueError('Comparison fits used different marker targets/weights; no completed summary')
    differences = {key: finite_array(np.linalg.norm(surfaces[1][key]-surfaces[0][key], axis=1),
                                    key+' difference') for key in surfaces[0]}
    color_max = max(float(distance.max()) for distance in differences.values())
    skin = model.group_mask('skin_exterior') if 'skin_exterior' in model.vertex_group_names else None
    difference_record = {}
    for key, distance in differences.items():
        path = destination/f'difference_{key}.ply'
        export_difference_ply(path, surfaces[1][key], model.triangles, distance, color_max,
                              interpretation='identity-prior scenario difference; NOT uncertainty or face accuracy')
        difference_record[key] = dict(all_vertices=residual_metrics(distance),
            skin_exterior=None if skin is None else residual_metrics(distance[skin]),
            ply=path.name, sha256=sha256_file(path), surface='prior')
    scenarios = []
    for name, child, report in zip(('neutral', 'prior'), children, reports):
        scenarios.append(dict(id=name, prior_enabled=bool(child.prior),
            report=str(Path(child.output_json).relative_to(destination)), report_sha256=sha256_file(child.output_json),
            lambda_used=report['lambda'], lambda_selection=report['lambda_selection'],
            transform=report['transform'], metrics=report['metrics'], solver=report['solver'],
            qc=report['geometry_quality'], skipped=report['skipped'], warnings=report['warnings']))
    converged = all(report['solver']['converged'] for report in reports)
    warnings = ['Experimental sensitivity only; prior provenance and case applicability require human review.',
                'Prior mean/scale dimensions are checked; no model/component-order provenance is inferred from legacy archives.',
                'No age parameter or soft-tissue ageing model is introduced.']
    if not converged:
        warnings.append('At least one fit did not converge; differences are diagnostic-only, not a stable sensitivity estimate.')
    record = dict(schema_version=1, status='completed', units='mm', coordinate_space='world',
        comparison_status='completed_converged' if converged else 'diagnostic_only_nonconverged',
        interpretation=INTERPRETATION, justification=cfg.prior_justification, reference='neutral',
        neutral_definition='No external identity prior; existing zero-centred regularization remains active.',
        input_sha256=pinned, prior=dict(path=str(Path(cfg.prior).resolve()), sha256=prior['sha256'],
            mean=prior['mean'].tolist(), scale=prior['scale'].tolist(), weight=cfg.prior_weight,
            n_samples=prior['n_samples'], identity_subspace=cfg.identity_subspace,
            active_components=list(range(model.identity_dim)) if active is None else active.tolist(),
            inactive_policy='none' if active is None else 'zero'),
        scenarios=scenarios, differences_to_neutral=difference_record,
        color_scale_max_mm=color_max, warnings=warnings)
    lines = ['Experimental identity-prior comparison', 'Operator justification: '+cfg.prior_justification,
             INTERPRETATION, 'Comparison status: '+record['comparison_status']]
    for scenario in scenarios:
        lines.append(f"{scenario['id']}: lambda={scenario['lambda_used']:g}; converged={scenario['solver']['converged']}; report={scenario['report']}")
    for key, row in difference_record.items():
        lines.append(f"{key} all vertices: RMS={row['all_vertices']['rmse_mm']:.9g} mm; max={row['all_vertices']['max_mm']:.9g} mm")
    lines.extend(warnings)
    with atomic_text(destination/'comparison.txt') as stream:
        stream.write('\n'.join(lines)+'\n')
    record['text_report'] = dict(path='comparison.txt', sha256=sha256_file(destination/'comparison.txt'))
    # Recheck children and input pins before publishing the completion marker.
    for child in children:
        _checked_report(child, pinned)
    unchanged()
    with atomic_text(destination/'summary.json') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)+'\n')
    return 0
