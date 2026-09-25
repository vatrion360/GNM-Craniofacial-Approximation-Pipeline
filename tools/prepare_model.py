"""Copy a separately acquired GNM asset into an offline bundle after checksum verification."""
import argparse
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cranio.backend.gnm_backend import OFFICIAL_V3_SHA256
from cranio.validation import sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination', default='models/gnm_head.npz')
    args = parser.parse_args()
    if sha256_file(args.source) != OFFICIAL_V3_SHA256:
        parser.error('Checksum differs from the reviewed GNM v3 asset; refusing to install')
    destination = Path(args.destination)
    if destination.exists():
        parser.error('Destination already exists; choose a new path')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.source, destination)
    print(destination)


if __name__ == '__main__':
    main()
