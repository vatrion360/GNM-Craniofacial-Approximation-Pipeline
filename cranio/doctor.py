"""Offline preflight; never downloads anything or executes archive payloads."""
import argparse
import importlib.metadata
import json
import sys

from .backend import GNMBackend, default_npz_path
from .backend.gnm_backend import OFFICIAL_V3_SHA256
from .validation import sha256_file


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--npz', default=default_npz_path())
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    checks = {'python': sys.version.split()[0], 'packages': {}, 'errors': []}
    for name in ('numpy', 'scipy', 'trimesh'):
        try:
            checks['packages'][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            checks['errors'].append('Missing dependency: ' + name)
    try:
        model = GNMBackend(args.npz).load()
        digest = sha256_file(args.npz)
        checks['model'] = {'path': args.npz, 'sha256': digest,
                           'vertices': model.vertex_count, 'identity_dimensions': model.identity_dim,
                           'matches_reviewed_v3_asset': digest == OFFICIAL_V3_SHA256}
        if digest != OFFICIAL_V3_SHA256:
            checks['errors'].append('Model differs from reviewed v3 asset; built-in anatomical mappings require review')
    except (OSError, ValueError, KeyError) as exc:
        checks['errors'].append(str(exc))
    checks['ok'] = not checks['errors']
    print(json.dumps(checks, indent=2))
    return 0 if checks['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
