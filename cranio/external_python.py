"""Portable, dependency-free checks for Blender's external Python launcher.

The selection is one executable or virtual-environment folder, never a shell
command. Preserve virtualenv symlinks: resolving them can select the system
interpreter and silently lose the environment's dependencies.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

CHECK_PREFIX = "GNM_PYTHON_CHECK="
PROBE = '''import importlib, json, struct, sys
result = {"version": list(sys.version_info[:3]), "bits": struct.calcsize("P") * 8,
          "executable": sys.executable, "dependencies": {}, "errors": {}}
if sys.version_info >= (3, 10):
    for name in ("numpy", "scipy", "trimesh"):
        try:
            module = importlib.import_module(name)
            result["dependencies"][name] = getattr(module, "__version__", "unknown")
        except Exception as exc:
            result["errors"][name] = str(exc)
print("GNM_PYTHON_CHECK=" + json.dumps(result))
'''


def clean_environment():
    env = dict(os.environ)
    # Blender/embedded Python settings must not redirect a different Python.
    for key in list(env):
        if key.upper() in {"PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONINSPECT"}:
            env.pop(key)
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return env


def process_options():
    return {"env": clean_environment(), "shell": False,
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0}


def executable_path(selection, *, windows=None):
    windows = os.name == "nt" if windows is None else windows
    value = os.path.expandvars(os.path.expanduser(str(selection).strip().strip('"')))
    if not value:
        raise ValueError("Select Python 3.10+ (64-bit), e.g. .venv/Scripts/python.exe on Windows.")
    path = Path(value)
    if path.is_dir():
        candidates = (path / 'Scripts' / 'python.exe', path / 'python.exe') if windows else (
            path / 'bin' / 'python', path / 'python', path / 'bin' / 'python3')
        path = next((p for p in candidates if p.is_file()), candidates[0])
    elif not path.is_file() and path.name == value:
        found = shutil.which(value)
        if found:
            path = Path(found)
    if not path.is_file():
        raise ValueError(f"Python executable not found: {path}. Select the installed interpreter or its .venv folder.")
    if path.name.lower().startswith('blender'):
        raise ValueError("blender.exe is not the external Python interpreter. Select .venv/Scripts/python.exe.")
    if path.name.lower() == 'pythonw.exe':
        raise ValueError("Select python.exe rather than pythonw.exe so dependency checks and run logs remain available.")
    if path.name.lower().startswith('python-') and path.suffix.lower() == '.exe':
        raise ValueError("This appears to be a Python installer. Select the installed interpreter at .venv/Scripts/python.exe.")
    if path.suffix.lower() in {'.py', '.pyw', '.bat', '.cmd', '.ps1', '.zip', '.whl', '.msi'}:
        raise ValueError(f"{path.name} is not a Python executable. On Windows select .venv/Scripts/python.exe; put no script or command arguments in this field.")
    if windows:
        try:
            with path.open('rb') as stream:
                signature = stream.read(4)
        except OSError as exc:
            raise ValueError(f"Cannot read interpreter {path}: {exc}. Select an installed Python, not a Store execution alias.") from exc
        if path.suffix.lower() != '.exe' or not signature.startswith(b'MZ'):
            kind = "Linux ELF binary" if signature == b'\x7fELF' else "non-Windows executable"
            raise ValueError(f"WinError 193 prevented: {path} is a {kind}. Create the environment on Windows and select Scripts/python.exe; copying a Linux/macOS virtualenv does not work.")
    return Path(os.path.abspath(path))


def launch_error(exc, executable):
    if getattr(exc, 'winerror', None) in {193, 216} or getattr(exc, 'errno', None) == 8:
        return (f"Windows cannot execute {executable} (WinError {getattr(exc, 'winerror', 193)} / invalid executable format). "
                "Select a compatible installed 64-bit Python 3.10+ at .venv/Scripts/python.exe. "
                "A .py file, installer, or Linux/macOS virtualenv is not a Windows Python interpreter.")
    return f"Could not start Python {executable}: {exc}"


def inspect_python(selection, timeout=20):
    path = executable_path(selection)
    try:
        result = subprocess.run([str(path), '-c', PROBE], capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                timeout=timeout, stdin=subprocess.DEVNULL, **process_options())
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Python check timed out after {timeout}s: {path}. Select the interpreter, not its installer.") from exc
    except OSError as exc:
        raise ValueError(launch_error(exc, path)) from exc
    lines = [line[len(CHECK_PREFIX):] for line in result.stdout.splitlines() if line.startswith(CHECK_PREFIX)]
    if result.returncode != 0 or not lines:
        detail = (result.stderr or result.stdout).strip()[-800:]
        raise ValueError(f"Python check failed for {path} (exit {result.returncode}). Select Python 3.10+ (64-bit). {detail}")
    try:
        info = json.loads(lines[-1])
        version, bits, errors = tuple(info['version']), info['bits'], info['errors']
        actual = info['executable']
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"Invalid Python check response from {path}") from exc
    if version < (3, 10) or bits != 64:
        raise ValueError(f"Python 3.10+ (64-bit) required; selected {version}, {bits}-bit: {path}")
    if errors:
        details = '; '.join(f'{name}: {reason}' for name, reason in errors.items())
        raise ValueError(f"Interpreter works, but dependencies are unavailable: {details}. Install this project's dependencies in that same Python environment.")
    # A py.exe launcher may select another executable. Validate and retain it;
    # do not let a later change of launcher default pick a different Python.
    info['executable'] = str(executable_path(actual))
    info['selected_path'] = str(path)
    return info


def start_pipeline(info, script, arguments, log):
    script = Path(script)
    command = [info['executable'], str(script), *map(str, arguments)]
    log.write('External Python: ' + json.dumps(info, ensure_ascii=False) + '\n')
    log.write('Command arguments: ' + json.dumps(command, ensure_ascii=False) + '\n')
    log.flush()
    try:
        return subprocess.Popen(command, cwd=str(script.parent), stdout=log,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **process_options())
    except OSError as exc:
        raise ValueError(launch_error(exc, info['executable'])) from exc
