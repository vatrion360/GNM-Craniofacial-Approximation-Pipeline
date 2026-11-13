"""External record-export request and result checks; no bpy or fitting.

Blender delegates artifact hashing and optional ensemble validation to a child
Python process. Only the explicit source report and small result files are read
on the UI thread. No path found in a report chooses executable code.
"""
import hashlib
import json
from pathlib import Path
import subprocess

from .external_python import launch_error, process_options
from .record import validate_report
from .tissue import _json


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare_request(report_path, *, artifacts=None, limitations=None, uncertainty=None, scenario=None,
                    validity_domain=None, domain_case=None, check_policy=None, check_override=None):
    """Snapshot explicit paths and source-report identity; do not inspect meshes."""
    report_path = Path(report_path).resolve()
    raw = report_path.read_bytes()
    validate_report(_json(raw.decode('utf-8-sig')))
    if (uncertainty is None) != (scenario is None):
        raise ValueError('Select both an uncertainty JSON and an explicit prior scenario')
    if scenario is not None and scenario not in ('off', 'on'):
        raise ValueError('Select the explicit uncertainty prior scenario off or on')
    if (validity_domain is None) != (domain_case is None):
        raise ValueError('Select both validation domain and bound case observations')
    if check_override is not None:
        from .check_policy import _text
        _text(check_override)
        if check_policy is None:
            raise ValueError('A check override requires an explicit policy')
    arguments = ['build', '--report', str(report_path)]
    for flag, value in (('--artifacts', artifacts), ('--limitations', limitations), ('--uncertainty', uncertainty),
                        ('--validation-domain', validity_domain), ('--domain-case', domain_case), ('--check-policy', check_policy)):
        if value is None:
            continue
        path = Path(value).resolve()
        if not (path.is_dir() if flag == '--artifacts' else path.is_file()):
            raise ValueError('Missing '+flag+' input: '+str(path))
        arguments.extend([flag, str(path)])
    if check_override is not None:
        arguments.extend(['--check-override', check_override])
    if scenario is not None:
        arguments.extend(['--uncertainty-scenario', scenario])
    return dict(report_path=str(report_path), report_sha256=_digest(raw), arguments=arguments)


def start_record(info, package_root, request, output_dir, log):
    """Launch this checkout/ZIP's fixed CLI module, with the shared safe environment."""
    root = Path(package_root).resolve()
    if not (root/'cranio'/'record.py').is_file():
        raise ValueError('The installed add-on is missing cranio/record.py; reinstall the complete ZIP')
    bootstrap = ("import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); "
                 "runpy.run_module('cranio.record', run_name='__main__', alter_sys=True)")
    command = [info['executable'], '-c', bootstrap, str(root),
               *request['arguments'], '--output-dir', str(output_dir)]
    log.write('External Python: '+json.dumps(info, ensure_ascii=False)+'\n')
    log.write('Command arguments: '+json.dumps(command, ensure_ascii=False)+'\n')
    log.flush()
    try:
        return subprocess.Popen(command, cwd=str(root), stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, **process_options())
    except OSError as exc:
        raise ValueError(launch_error(exc, info['executable'])) from exc


def read_result(output_dir, request):
    """Verify fixed completion files before displaying text, without opening mesh paths.

    Integrity is not authentication. The report must still match the clicked
    source identity; optional files are pinned by the child CLI when it reads them.
    """
    root = Path(output_dir).resolve()
    def read(name):
        path = root/name
        if not path.resolve().is_relative_to(root):
            raise ValueError('Record result escapes its directory')
        return path.read_bytes()
    raw = read('approximation_record.json')
    page = read('approximation_record.txt')
    envelope = _json(read('provenance.json').decode('utf-8-sig'))
    record = _json(raw.decode('utf-8-sig'))
    if (not isinstance(envelope, dict) or type(envelope.get('schema_version')) is not int
            or envelope['schema_version'] != 1 or not isinstance(envelope.get('source_report'), dict)
            or envelope['source_report'].get('sha256') != request['report_sha256']):
        raise ValueError('Record source differs from the submitted report')
    expected = envelope.get('derived_files')
    if not isinstance(expected, dict) or set(expected) != {'approximation_record.json', 'approximation_record.txt'}:
        raise ValueError('Missing derived-file integrity manifest')
    for name, content in (('approximation_record.json', raw), ('approximation_record.txt', page)):
        row = expected[name]
        if not isinstance(row, dict) or row.get('sha256') != _digest(content):
            raise ValueError('Record result checksum mismatch: '+name)
    if (not isinstance(record, dict) or type(record.get('schema_version')) is not int
            or record['schema_version'] != 1 or record.get('kind') != 'derived_approximation_record'
            or record.get('units') != 'mm' or record.get('status') not in ('recorded_not_validated', 'diagnostic_only')):
        raise ValueError('Unsupported derived approximation record')
    if _digest(Path(request['report_path']).read_bytes()) != request['report_sha256']:
        raise ValueError('Source report changed after submission; result was not displayed')
    return record, page.decode('utf-8')
