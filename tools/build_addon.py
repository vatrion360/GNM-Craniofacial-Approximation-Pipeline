"""Build the self-contained Blender legacy add-on ZIP (no model weights)."""
import hashlib
from pathlib import Path
from runpy import run_path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parents[1]


def default_archive():
    version = run_path(str(ROOT / 'cranio' / '__init__.py'))['__version__']
    return ROOT / 'dist' / f'gnm_cranio-{version}.zip'


def build(destination=None):
    root = ROOT
    destination = Path(destination or default_archive())
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = [(root / 'addon_v13.py', 'gnm_cranio/__init__.py'),
             (root / 'gnm_reconstruct.py', 'gnm_cranio/gnm_reconstruct.py'),
             (root / 'landmark_vertex_map.json', 'gnm_cranio/landmark_vertex_map.json'),
             (root / 'cranio/data/scenarios.json', 'gnm_cranio/cranio/data/scenarios.json'),
             (root / 'LICENSE', 'gnm_cranio/LICENSE'),
             (root / 'NOTICE', 'gnm_cranio/NOTICE'),
             (root / 'README.md', 'gnm_cranio/README.md'),
             (root / 'CITATION.cff', 'gnm_cranio/CITATION.cff'),
             (root / 'CHANGELOG.md', 'gnm_cranio/CHANGELOG.md')]
    files += [(p, 'gnm_cranio/' + p.relative_to(root).as_posix()) for p in sorted((root / 'cranio').rglob('*.py'))]
    files += [(p, 'gnm_cranio/' + p.relative_to(root).as_posix())
              for p in sorted((root / 'cranio' / 'data' / 'tissue').glob('*.json'))]
    files += [(p, 'gnm_cranio/' + p.relative_to(root).as_posix())
              for p in sorted((root / 'cranio' / 'rules').glob('*.json'))]
    files += [(p, 'gnm_cranio/' + p.relative_to(root).as_posix()) for p in sorted((root / 'docs').iterdir())
              if p.suffix in {'.md', '.json', '.bib'}]
    with NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with ZipFile(temporary, 'w') as archive:
            for source, name in sorted(files, key=lambda entry: entry[1]):
                member = ZipInfo(name)  # Fixed ZIP epoch, independent of the build clock.
                member.create_system = 3
                member.external_attr = 0o100644 << 16
                archive.writestr(member, source.read_bytes(), compress_type=ZIP_DEFLATED)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(destination)
    print(f"SHA-256: {hashlib.sha256(destination.read_bytes()).hexdigest()}")
    return destination


if __name__ == '__main__':
    build()
