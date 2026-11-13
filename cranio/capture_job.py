"""Background Blender capture requests and completion checks; no bpy imports."""
import json
from pathlib import Path
import subprocess

from .capture_plan import settings, VIEWS
from .external_python import process_options, launch_error
from .record import _digest, validate_report
from .tissue import _json


def prepare_request(report_path, bundle_path, *, resolution=1024, bar_mm=50., samples=16):
    """Pin explicitly selected report and export marker; deeper reads run in child."""
    report, marker = Path(report_path).resolve(), Path(bundle_path).resolve()
    if marker.name != 'export_decision.json':
        raise ValueError('Select the completed export_decision.json bundle marker')
    raw, bundle_raw = report.read_bytes(), marker.read_bytes()
    validate_report(_json(raw.decode('utf-8-sig')))
    bundle = _json(bundle_raw.decode('utf-8-sig'))
    if (not isinstance(bundle, dict) or bundle.get('kind') != 'saved_fit_export'
            or bundle.get('status') != 'completed' or bundle.get('source_report_sha256') != _digest(raw)):
        raise ValueError('Select a completed mesh bundle matching the saved fit report')
    return dict(kind='standardized_captures', report_path=str(report), report_sha256=_digest(raw),
        bundle_path=str(marker), bundle_sha256=_digest(bundle_raw), **settings(resolution, bar_mm, samples))


def start(binary, package_root, request, output_dir, log):
    """Execute only the installed Blender binary and this package's fixed script."""
    root = Path(package_root).resolve()
    script = root/'cranio'/'capture_render.py'
    if not script.is_file() or not Path(binary).is_file():
        raise ValueError('Blender binary or capture script missing; reinstall the complete add-on ZIP')
    command = [str(binary), '--background', '--factory-startup', '--python-exit-code', '1',
               '--python', str(script), '--', '--report', request['report_path'],
               '--bundle', str(Path(request['bundle_path']).parent), '--output-dir', str(output_dir),
               '--resolution', str(request['resolution']), '--bar-mm', str(request['bar_mm']),
               '--samples', str(request['samples'])]
    log.write('Capture arguments: '+json.dumps(command, ensure_ascii=False)+'\n')
    log.flush()
    try:
        return subprocess.Popen(command, cwd=str(root), stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, **process_options())
    except OSError as exc:
        raise ValueError(launch_error(exc, str(binary))) from exc


def read_result(output_dir, request):
    """No embedded file paths are followed; verify the three PNGs and source pins."""
    root = Path(output_dir).resolve()
    def read(name):
        path = root/name
        if not path.resolve().is_relative_to(root):
            raise ValueError('Capture output escapes directory')
        return path.read_bytes()
    result = _json(read('capture_manifest.json').decode('utf-8-sig'))
    if (not isinstance(result, dict) or type(result.get('schema_version')) is not int or result['schema_version'] != 1
            or result.get('kind') != 'standardized_saved_fit_captures' or result.get('status') != 'completed'
            or result.get('units') != 'mm' or result.get('projection') != 'orthographic'
            or result.get('source_report_sha256') != request['report_sha256']
            or result.get('source_export_decision_sha256') != request['bundle_sha256']
            or any(result.get(key) != request[key] for key in ('resolution', 'samples', 'bar_mm'))):
        raise ValueError('Capture result differs from submitted request')
    expected = {view+'.png' for view in VIEWS}
    files = result.get('files')
    if not isinstance(files, dict) or set(files) != expected:
        raise ValueError('Unexpected capture file manifest')
    for name, row in files.items():
        raw = read(name)
        if not isinstance(row, dict) or row.get('sha256') != _digest(raw) or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Capture PNG integrity failure: '+name)
    if (_digest(Path(request['report_path']).read_bytes()) != request['report_sha256']
            or _digest(Path(request['bundle_path']).read_bytes()) != request['bundle_sha256']):
        raise ValueError('Capture sources changed after submission')
    return result
