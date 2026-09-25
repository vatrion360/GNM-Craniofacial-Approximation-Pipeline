"""Generate synthetic v3 markers from the local GNM mean, NOT a forensic case."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cranio.backend import GNMBackend
from cranio.io_csv import write_marker_csv_v3
from cranio.validation import sha256_file


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--npz', required=True)
    p.add_argument('--output', default='examples/synthetic_markers.csv')
    args = p.parse_args()
    backend = GNMBackend(args.npz)
    model = backend.load()
    rows = []
    for label, vertex in backend.landmark_vertex_map.items():
        xyz = model.mu[vertex].astype(float)
        rows.append(dict(label=label, vertex=vertex, placed=1,
                         x=xyz[0], y=xyz[1], z=xyz[2], weight=1,
                         tissue_source='synthetic mean-model target; not FSTT data'))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    write_marker_csv_v3(args.output, rows,
                        {'model_sha256': sha256_file(args.npz), 'synthetic': True,
                         'purpose': 'software smoke test, NOT accuracy validation'})
    print(args.output)


if __name__ == '__main__':
    main()
