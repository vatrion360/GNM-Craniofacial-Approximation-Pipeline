import ast
from pathlib import Path
import zipfile
from tools.build_addon import build


def test_addon_zip_contains_core_and_cli(tmp_path):
    path = build(tmp_path / 'addon.zip')
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert {'gnm_cranio/__init__.py', 'gnm_cranio/cranio/optimize.py',
                'gnm_cranio/cranio/io_csv.py', 'gnm_cranio/gnm_reconstruct.py'}.issubset(names)
        assert not any(name.endswith('.npz') or '__pycache__' in name for name in names)
        for name in names:
            if name.endswith('.py'):
                compile(archive.read(name), name, 'exec')


def test_no_background_thread_creation_in_blender():
    source = (Path(__file__).resolve().parents[1] / 'addon_v13.py').read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert not (isinstance(node.func.value, ast.Name) and
                        node.func.value.id == 'threading' and node.func.attr == 'Thread')
