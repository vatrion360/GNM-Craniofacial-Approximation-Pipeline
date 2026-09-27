"""Regenerate reviewed Python 3.12 wheel hashes from PyPI; maintainer-only network use."""
import json
from pathlib import Path
from urllib.request import urlopen

VERSIONS = {'numpy': '2.3.5', 'scipy': '1.17.0', 'trimesh': '5.1.0'}


def main():
    lines = ['# Python 3.12 reviewed runtime. Install with --require-hashes --only-binary=:all:.',
             '# All release wheel platforms included; regenerate deliberately with tools/lock_runtime.py.']
    for package, version in VERSIONS.items():
        with urlopen(f'https://pypi.org/pypi/{package}/{version}/json', timeout=30) as stream:
            release = json.load(stream)
        hashes = sorted({item['digests']['sha256'] for item in release['urls'] if item['packagetype'] == 'bdist_wheel'})
        if not hashes:
            raise ValueError('No wheels found for '+package)
        lines.append(f'{package}=={version} \\')
        lines += ['    --hash=sha256:'+digest+(' \\' if i < len(hashes)-1 else '') for i, digest in enumerate(hashes)]
    path = Path(__file__).resolve().parents[1]/'requirements-tested-py312.txt'
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(path.name)


if __name__ == '__main__':
    main()
