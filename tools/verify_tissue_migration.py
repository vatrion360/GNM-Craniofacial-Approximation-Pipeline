"""Generate a synthetic numerical migration replay for a specified source tree.

Run against the historical and new trees in separate processes. Compare manifest
numeric data and OBJ/PLY hashes. Output directories must be new and outside Git;
no anatomical accuracy, human-subject data or tissue source validation is implied.
"""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-tree', required=True)
    parser.add_argument('--npz', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    source, output = Path(args.source_tree).resolve(), Path(args.output_dir).resolve()
    if output.exists():
        parser.error('Use a new output directory')
    # Imports must use the requested tree, never the script's checkout.
    sys.path.insert(0, str(source))
    import numpy as np
    from cranio.backend import GNMBackend
    from cranio.backend.gnm_backend import OFFICIAL_V3_SHA256
    from cranio.config import PipelineConfig
    from cranio.io_csv import write_marker_csv_v3
    from cranio.landmarks import LANDMARK_ORDER, LANDMARK_INFO, CONFIDENCE_WEIGHTS, REGION_OFFSETS_MM
    from cranio.pipeline import run_pipeline
    from cranio.validation import sha256_file
    assert sha256_file(args.npz) == OFFICIAL_V3_SHA256
    backend = GNMBackend(args.npz)
    model = backend.load()
    output.mkdir(parents=True)
    labels = LANDMARK_ORDER
    ids = np.array([backend.landmark_vertex_map[k] for k in labels])
    # Synthetic normals/displacement; NOT a simulated anatomical skull.
    rng = np.random.default_rng(1902)
    directions = rng.normal(size=(len(ids), 3))
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    bone = model.mu[ids].astype(float) - 2.0 * directions
    depths = np.array([LANDMARK_INFO[k][0] for k in labels])
    targets = bone + depths[:, None] * directions
    rows = [dict(label=k, vertex=int(vid), placed=1, x=float(t[0]), y=float(t[1]), z=float(t[2]),
                 bone_x=float(b[0]), bone_y=float(b[1]), bone_z=float(b[2]), tissue_depth_mm=float(d),
                 weight=CONFIDENCE_WEIGHTS[k], tissue_source='synthetic migration replay')
            for k, vid, t, b, d in zip(labels, ids, targets, bone, depths)]
    markers = output/'synthetic.csv'
    write_marker_csv_v3(markers, rows, {'model_sha256': OFFICIAL_V3_SHA256})
    manifest = dict(seed=1902, model_sha256=OFFICIAL_V3_SHA256,
                    tissue_defaults=LANDMARK_INFO, region_offsets=REGION_OFFSETS_MM,
                    scalp_offset=PipelineConfig().scalp_offset_mm, runs={})
    for name, local in (('statistical_default', False), ('local_correction', True)):
        cfg = PipelineConfig(input=str(markers), npz=str(Path(args.npz).resolve()),
                             output=str(output/name/'face.obj'), regularization='adaptive', skip_tps=not local)
        assert run_pipeline(cfg) == 0
        report = json.loads(Path(cfg.output_json).read_text())
        manifest['runs'][name] = dict(
            mesh_hashes={k: sha256_file(getattr(cfg, k)) for k in ('output', 'output_statistical', 'output_error_mesh')},
            numerical={k: report[k] for k in ('transform', 'identity_coefficients', 'lambda', 'metrics', 'iteration_history', 'solver')})
    (output/'migration_manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    print(output/'migration_manifest.json')


if __name__ == '__main__':
    main()
