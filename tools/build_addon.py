"""Build the self-contained Blender legacy add-on ZIP (no model weights)."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def build(destination=None):
    root = Path(__file__).resolve().parents[1]
    destination = Path(destination or root / 'dist' / 'gnm_cranio-5.0.0rc2.zip')
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = [(root / 'addon_v13.py', 'gnm_cranio/__init__.py'),
             (root / 'gnm_reconstruct.py', 'gnm_cranio/gnm_reconstruct.py'),
             (root / 'landmark_vertex_map.json', 'gnm_cranio/landmark_vertex_map.json'),
             (root / 'LICENSE', 'gnm_cranio/LICENSE'),
             (root / 'NOTICE', 'gnm_cranio/NOTICE')]
    files += [(p, 'gnm_cranio/' + p.relative_to(root).as_posix()) for p in sorted((root / 'cranio').rglob('*.py'))]
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for source, name in files:
            archive.writestr(name, source.read_bytes())
    print(destination)
    return destination


if __name__ == '__main__':
    build()
