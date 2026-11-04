"""Inspect anatomical-rule evidence metadata or write an unconfigured template."""
import argparse
import json
import sys
from pathlib import Path

from . import DATA_DIR, empty_registry, load_registry, validate_registry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    inspect = sub.add_parser('inspect')
    inspect.add_argument('--input', help='Local registry JSON; omitted uses bundled unverified metadata')
    status = sub.add_parser('status', help='Report rule availability without evaluating a case')
    status.add_argument('--input', help='Optional local registry JSON')
    status.add_argument('--rule', help='Restrict to one exact registry rule ID')
    template = sub.add_parser('template')
    template.add_argument('--id', required=True)
    template.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'inspect':
            registry = load_registry(args.input)
            result = dict(registry=registry.document, record=registry.record())
        elif args.action == 'status':
            from .engine import readiness
            result = readiness(load_registry(args.input), args.rule)
        else:
            from ..export import atomic_text
            from ..validation import validate_outputs
            output = Path(args.output).expanduser()
            validate_outputs([DATA_DIR/'registry.json', DATA_DIR/'schema.json'], [output])
            document, warnings = validate_registry(empty_registry(args.id))
            with atomic_text(output, validate=load_registry) as stream:
                stream.write(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2)+'\n')
            result = dict(output=str(output), warnings=list(warnings))
        # ASCII JSON escapes preserve Unicode values across console/pipe encodings.
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        print(f'Rule registry: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
