"""Run configured offline fits and compare portable projections of their reports."""
import argparse
import difflib
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cranio.pipeline import run_pipeline
from cranio.record import PATH_SETTINGS, canonical_bytes, compile_record
from cranio.tissue import _json, table_path, DATA_DIR
from cranio.validation_cases import _publish
from gnm_reconstruct import parse_args


SCHEMA = 'gnm.offline-baseline.v1'


def run_suite(suite, model):
    cases = _json(suite.read_text(encoding='utf-8-sig'))
    if not isinstance(cases, dict) or not cases:
        raise ValueError('The suite must map case IDs to offline CLI argument lists')
    runs = {}
    environment = None
    for label, args in cases.items():
        if not label.strip() or not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise ValueError('Each case needs a name and a list of CLI arguments')
        try:
            cfg = parse_args(['--npz', str(model.resolve()), *args])
        except SystemExit as exc:
            raise ValueError(f'{label}: expected the arguments for a single offline fit') from exc
        if (any(getattr(cfg, key) is not None for key in PATH_SETTINGS if key.startswith('output'))
                or cfg.overwrite or cfg.tissue_compare or cfg.prior_compare):
            raise ValueError(f'{label}: output paths, overwrite and multi-fit comparisons are managed by the runner')
        if cfg.npz != str(model.resolve()):
            raise ValueError(f'{label}: select the shared model with --model')
        for key in PATH_SETTINGS - {'npz'}:
            value = getattr(cfg, key)
            if value is None:
                continue
            if key == 'tissue_table' and table_path(value).parent == DATA_DIR:
                continue
            setattr(cfg, key, str((suite.parent / value).resolve()))
        with tempfile.TemporaryDirectory() as directory:
            cfg.output = str(Path(directory) / 'fit.obj')
            code = run_pipeline(cfg)
            if code:
                raise ValueError(f'{label}: offline fit exited with code {code}')
            report = _json(Path(cfg.output_json).read_text(encoding='utf-8'))
            run = compile_record(report)['run']
            runs[label] = {key: run[key] for key in
                           ('inputs', 'outputs', 'config', 'metrics', 'lambda')}
            runs[label]['scale'] = run['transform']['scale']
            runs[label]['converged'] = run['solver']['converged']
            if environment is None:
                environment = report['software']
    return {'schema': SCHEMA, 'cases': runs}, environment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--record', type=Path, metavar='NEW_DIRECTORY')
    mode.add_argument('--compare', type=Path, metavar='BASELINE_DIRECTORY')
    args = parser.parse_args(argv)
    try:
        if args.record is not None and args.record.exists():
            raise ValueError('Choose a new baseline directory')
        if args.compare is not None:
            reference = _json((args.compare / 'snapshot.json').read_text(encoding='utf-8'))
            if (not isinstance(reference, dict) or reference.get('schema') != SCHEMA
                    or not isinstance(reference.get('cases'), dict) or not reference['cases']):
                raise ValueError('Expected a version 1 offline baseline snapshot')
        snapshot, environment = run_suite(args.suite, args.model)
        data = canonical_bytes(snapshot)
        if args.record is not None:
            _publish(args.record, {'snapshot.json': data, 'environment.json': canonical_bytes(environment)})
            print(f'Recorded {len(snapshot["cases"])} case(s) in {args.record}')
            return 0
        expected = canonical_bytes(reference)
        if data == expected:
            print(f'Matched {len(snapshot["cases"])} case(s)')
            return 0
        for label in sorted(reference['cases'].keys() | snapshot['cases'].keys()):
            before = canonical_bytes(reference['cases'].get(label)).decode().splitlines()
            after = canonical_bytes(snapshot['cases'].get(label)).decode().splitlines()
            for line in difflib.unified_diff(before, after, f'{label}/reference', f'{label}/current', lineterm=''):
                print(line)
        return 1
    except (OSError, ValueError, TypeError) as exc:
        print(f'Cannot complete baseline run: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
