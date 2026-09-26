import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from cranio.external_python import (CHECK_PREFIX, executable_path, inspect_python,
                                    launch_error, start_pipeline)


@pytest.mark.parametrize('name', ['gnm_reconstruct.py', 'activate.bat', 'python-installer.msi',
                                 'blender.exe', 'pythonw.exe', 'python-3.12.8-amd64.exe'])
def test_wrong_file_is_rejected_before_launch(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b'MZnot-a-python-interpreter')
    with pytest.raises(ValueError, match='python.exe|Python executable|interpreter'):
        executable_path(path, windows=True)


def test_linux_environment_is_not_accepted_as_windows_python(tmp_path):
    path = tmp_path / 'python.exe'
    path.write_bytes(b'\x7fELF')
    with pytest.raises(ValueError, match='WinError 193 prevented.*Linux ELF'):
        executable_path(path, windows=True)


def test_windows_environment_folder_resolves_interpreter(tmp_path):
    exe = tmp_path / 'venv folder șță' / 'Scripts' / 'python.exe'
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b'MZfixture')
    assert executable_path(exe.parent.parent, windows=True) == exe.absolute()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX virtualenv symlink regression')
def test_venv_symlink_is_preserved(tmp_path):
    exe = tmp_path / 'environment' / 'bin' / 'python'
    exe.parent.mkdir(parents=True)
    exe.symlink_to(sys.executable)
    assert executable_path(exe.parent.parent) == exe.absolute()
    assert executable_path(exe) != exe.resolve()


def test_actual_python_probe_ignores_embedded_python_paths(monkeypatch):
    monkeypatch.setenv('PYTHONHOME', '/nonexistent/blender/python')
    monkeypatch.setenv('PYTHONPATH', '/nonexistent/blender/modules')
    info = inspect_python(sys.executable)
    assert tuple(info['version']) >= (3, 10) and info['bits'] == 64
    assert set(info['dependencies']) == {'numpy', 'scipy', 'trimesh'}


@pytest.mark.skipif(os.name != 'nt', reason='Windows CreateProcess error reproduction')
def test_real_windows_193_is_reproduced_and_explained(tmp_path):
    wrong = tmp_path / 'gnm_reconstruct.py'
    wrong.write_text("print('This script needs python.exe')\n")
    with pytest.raises(OSError) as caught:
        subprocess.run([str(wrong)], check=False, capture_output=True)
    assert caught.value.winerror == 193
    message = launch_error(caught.value, wrong)
    assert '193' in message and 'Scripts/python.exe' in message
    with pytest.raises(ValueError, match='not a Python executable'):
        inspect_python(wrong)


def test_probe_translates_native_format_error(tmp_path, monkeypatch):
    exe = tmp_path / 'python.exe'
    exe.write_bytes(b'MZfixture')
    error = OSError('%1 is not a valid Win32 application')
    error.winerror = 193
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(ValueError, match='193.*invalid executable format'):
        inspect_python(exe)


@pytest.mark.parametrize('changes,match', [({'bits': 32}, '64-bit'),
    ({'version': [3, 9, 1]}, '3.10'),
    ({'errors': {'scipy': 'DLL load failed'}}, 'same Python environment')])
def test_probe_reports_incompatible_environment(tmp_path, monkeypatch, changes, match):
    exe = tmp_path / 'python.exe'
    exe.write_bytes(b'MZfixture')
    info = dict(version=[3, 12, 1], bits=64, executable=str(exe), errors={}, dependencies={})
    info.update(changes)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: SimpleNamespace(
        stdout=CHECK_PREFIX + json.dumps(info), stderr='', returncode=0))
    with pytest.raises(ValueError, match=match):
        inspect_python(exe)


def test_external_process_handles_unicode_spaces_and_metacharacters(tmp_path):
    folder = tmp_path / 'case șță with spaces'
    folder.mkdir()
    script = folder / 'probe script.py'
    script.write_text('import json,sys\nprint(json.dumps(sys.argv[1:],ensure_ascii=False))\n', encoding='utf-8')
    argument = 'șță & echo should-not-run'
    logfile = folder / 'run.log'
    info = {'executable': sys.executable, 'version': list(sys.version_info[:3]), 'bits': 64}
    with logfile.open('w', encoding='utf-8') as stream:
        process = start_pipeline(info, script, [argument], stream)
        assert process.wait(timeout=20) == 0
    assert json.loads(logfile.read_text(encoding='utf-8').splitlines()[-1]) == [argument]
