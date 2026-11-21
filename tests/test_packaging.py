import ast
from pathlib import Path
import zipfile
from tools.build_addon import build, default_archive
from cranio import __version__


def test_addon_zip_contains_core_and_cli(tmp_path):
    path = build(tmp_path / 'addon.zip')
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert {'gnm_cranio/__init__.py', 'gnm_cranio/cranio/optimize.py',
                'gnm_cranio/cranio/io_csv.py', 'gnm_cranio/gnm_reconstruct.py',
                'gnm_cranio/docs/CRANIOMETRY.md', 'gnm_cranio/docs/GHID_RO.md',
                'gnm_cranio/docs/PERFORMANCE.md', 'gnm_cranio/docs/performance_v18.json',
                'gnm_cranio/docs/MARKER_DEPTH_ADJUSTMENT.md',
                'gnm_cranio/docs/POSTFIT_PRESENTATION.md',
                'gnm_cranio/cranio/postfit.py',
                'gnm_cranio/cranio/prior_compare.py',
                'gnm_cranio/cranio/age_context.py',
                'gnm_cranio/cranio/blender_prior_audit.py',
                'gnm_cranio/cranio/record.py',
                'gnm_cranio/cranio/record_uncertainty.py',
                'gnm_cranio/cranio/record_job.py',
                'gnm_cranio/cranio/validity_domain.py',
                'gnm_cranio/cranio/check_policy.py',
                'gnm_cranio/cranio/consistency.py',
                'gnm_cranio/cranio/tps.py',
                'gnm_cranio/cranio/local_correction.py',
                'gnm_cranio/cranio/review_export.py',
                'gnm_cranio/cranio/capture_plan.py',
                'gnm_cranio/cranio/capture_render.py',
                'gnm_cranio/cranio/capture_job.py',
                'gnm_cranio/cranio/blender_record.py',
                'gnm_cranio/cranio/rules/__init__.py',
                'gnm_cranio/cranio/rules/__main__.py',
                'gnm_cranio/cranio/rules/registry.json',
                'gnm_cranio/cranio/rules/schema.json',
                'gnm_cranio/cranio/rules/contracts.py',
                'gnm_cranio/cranio/rules/comparison.py',
                'gnm_cranio/cranio/blender_rules.py',
                'gnm_cranio/cranio/rules/engine.py',
                'gnm_cranio/cranio/rules/eyes.py',
                'gnm_cranio/cranio/rules/mouth.py',
                'gnm_cranio/cranio/rules/nose.py',
                'gnm_cranio/cranio/rules/ears.py',
                'gnm_cranio/cranio/blender_postfit.py',
                'gnm_cranio/cranio/blender_marker_depths.py'}.issubset(names)
        assert not any(name.endswith('.npz') or '__pycache__' in name for name in names)
        for name in names:
            if name.endswith('.py'):
                compile(archive.read(name), name, 'exec')


def test_candidate_archive_identity_and_reproducibility(tmp_path):
    first = build(tmp_path / 'first.zip')
    second = build(tmp_path / 'second.zip')
    assert first.read_bytes() == second.read_bytes()
    assert default_archive().name == f'gnm_cranio-{__version__}.zip'
    with zipfile.ZipFile(first) as archive:
        infos = archive.infolist()
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
        assert archive.namelist() == sorted(set(archive.namelist()))
        citation = archive.read('gnm_cranio/CITATION.cff').decode().splitlines()
        assert f'version: {__version__}' in citation
        source = ast.parse(archive.read('gnm_cranio/__init__.py').decode('utf-8'))
        info = next(ast.literal_eval(node.value) for node in source.body if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'bl_info' for t in node.targets))
        addon_version = '.'.join(map(str, info['version']))
        changelog = archive.read('gnm_cranio/CHANGELOG.md').decode()
        assert f'# {__version__} / add-on {addon_version}' in changelog.splitlines()
        assert 'gnm_cranio/docs/T_FINAL.md' in archive.namelist()


def test_no_background_thread_creation_in_blender():
    source = (Path(__file__).resolve().parents[1] / 'addon_v13.py').read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert not (isinstance(node.func.value, ast.Name) and
                        node.func.value.id == 'threading' and node.func.attr == 'Thread')
