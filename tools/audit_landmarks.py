"""Audit registry identity and nearby skin candidates; no automatic anatomical merging."""
import argparse
from itertools import combinations
import json
from pathlib import Path

import numpy as np

from cranio.backend import GNMBackend
from cranio.landmarks import LANDMARK_ORDER, PLACEMENT_HINTS
from cranio.marker_audit import audit_landmarks
from cranio.validation import sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--npz', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--near-mm', type=float, default=2.0)
    args = parser.parse_args()
    backend = GNMBackend(args.npz)
    model = backend.load()
    mapping = backend.landmark_vertex_map
    labels = list(LANDMARK_ORDER)
    report = audit_landmarks(labels, [mapping[label] for label in labels])
    report.update(model_sha256=sha256_file(args.npz), proximity_threshold_mm=args.near_mm,
                  candidate_proximity_is_not_anatomical_equivalence=True,
                  marker_set_sizes={'extended': 48, 'paper': 32, 'legacy': 27})
    report['near_candidates'] = []
    for a, b in combinations(labels, 2):
        distance = float(np.linalg.norm(model.mu[mapping[a]] - model.mu[mapping[b]]))
        if distance <= args.near_mm:
            report['near_candidates'].append(dict(labels=[a, b], vertices=[mapping[a], mapping[b]],
                distance_mm=distance, placement_definitions=[PLACEMENT_HINTS.get(a), PLACEMENT_HINTS.get(b)]))
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"{len(labels)} labels, {len(set(mapping.values()))} unique vertices; {len(report['errors'])} duplicates; {len(report['near_candidates'])} proximity pairs")
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
