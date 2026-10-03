"""Freeze code/settings before blinded CT cases; this is not clinical validation."""
import argparse
from dataclasses import asdict
import json
from .export import atomic_text
from .provenance import implementation_manifest
from .validation import sha256_file, validate_outputs

CASE_FIELDS = {'input', 'output', 'output_error_mesh', 'output_stats', 'output_json',
    'output_statistical', 'npz', 'skull', 'prior', 'landmark_map', 'protocol', 'case_metadata', 'craniometry', 'overwrite', 'require_qc'}


def scientific_settings(config):
    values = config if isinstance(config, dict) else asdict(config)
    return {key: value for key, value in values.items() if key not in CASE_FIELDS}


def _is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def frozen_from_report(report, protocol_id, split_sha256):
    if not isinstance(protocol_id, str) or not protocol_id.strip() or not _is_sha256(split_sha256):
        raise ValueError('Protocol ID and immutable subject-split SHA-256 required')
    if report['config']['geometry_qc'] != 'full':
        raise ValueError('Development run must use full geometry QC')
    from .craniometry import control_protocol
    return dict(schema_version=1, protocol_id=protocol_id, split_sha256=split_sha256,
        craniometry_policy=control_protocol(report['marker_metadata']['craniometry']) if report['config'].get('measurement_weight', 0) > 0 else None,
        model_sha256=report['inputs']['model']['sha256'], source_sha256=report['software']['implementation']['source_sha256'],
        runtime_versions={key: report['software'][key] for key in ('numpy', 'scipy', 'trimesh')},
        settings=scientific_settings(report['config']), skull_required='skull' in report['inputs'],
        optional_inputs={key: report['inputs'].get(key, {}).get('sha256') for key in ('prior', 'landmark_map')},
        scope='Engineering freeze; preregistration and independent CT validation remain required')


def validate_protocol(cfg, metadata, targets, model_hash):
    """Reject mismatched implementation/settings and untraceable observed markers."""
    from importlib.metadata import version
    with open(cfg.protocol, encoding='utf-8') as stream:
        protocol = json.load(stream)
    if not isinstance(protocol, dict) or protocol.get('schema_version') != 1:
        raise ValueError('Unsupported frozen protocol schema')
    expected = dict(model_sha256=model_hash, source_sha256=implementation_manifest()['source_sha256'],
        runtime_versions={key: version(key) for key in ('numpy', 'scipy', 'trimesh')},
        settings=scientific_settings(cfg), skull_required=bool(cfg.skull),
        optional_inputs={key: sha256_file(getattr(cfg, key)) if getattr(cfg, key) else None for key in ('prior', 'landmark_map')})
    from .craniometry import control_protocol
    expected['craniometry_policy'] = control_protocol(metadata.get('craniometry')) if cfg.measurement_weight > 0 else None
    for name, value in expected.items():
        if protocol.get(name) != value:
            raise ValueError(f'Frozen protocol mismatch: {name}')
    if not isinstance(metadata, dict):
        raise ValueError('Protocol metadata must be a JSON object')
    case = metadata.get('case_metadata', metadata)
    if not isinstance(case, dict):
        raise ValueError('Protocol case metadata must be a JSON object')
    required = ('case_id', 'observer_id', 'protocol_id', 'split_sha256', 'acquisition_sha256', 'segmentation_revision', 'coordinate_frame')
    if any(not isinstance(case.get(key), str) or not case[key].strip() for key in required):
        raise ValueError('Protocol case requires ' + ', '.join(required))
    if case['protocol_id'] != protocol.get('protocol_id') or case['split_sha256'] != protocol.get('split_sha256'):
        raise ValueError('Case protocol ID or subject split mismatch')
    for key in ('split_sha256', 'acquisition_sha256'):
        if not _is_sha256(case[key]):
            raise ValueError(f'Invalid SHA-256: {key}')
    source_rows = metadata.get('bone_sources', [])
    if not isinstance(source_rows, list):
        raise ValueError('Protocol bone_sources must be a list of source objects')
    sources = {}
    for row in source_rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'].strip():
            raise ValueError('Protocol bone source requires a nonempty string ID')
        if row['id'] in sources:
            raise ValueError(f'Duplicate protocol bone source ID: {row["id"]}')
        if not _is_sha256(row.get('geometry_sha256')):
            raise ValueError(f'{row["id"]}: invalid source geometry SHA-256')
        sources[row['id']] = row
    records = metadata.get('marker_records', {})
    if not isinstance(records, dict):
        raise ValueError('Protocol marker_records must be a JSON object')
    for target in targets:
        row = records.get(target.label, {})
        if not isinstance(row, dict):
            raise ValueError(f'{target.label}: marker record must be a JSON object')
        if row.get('mapping_reviewed') is not True or row.get('bone_status') != 'observed':
            raise ValueError(f'{target.label}: protocol requires reviewed mapping on observed bone')
        if row.get('tissue_source', '') in ('', 'unspecified', 'legacy-unvalidated'):
            raise ValueError(f'{target.label}: undocumented tissue source')
        source_id = row.get('bone_source_id')
        if not isinstance(source_id, str):
            raise ValueError(f'{target.label}: bone source ID must be a string')
        source = sources.get(source_id)
        if not source or not source.get('geometry_sha256') or row.get('bone_source_geometry_sha256') != source['geometry_sha256']:
            raise ValueError(f'{target.label}: missing or changed source geometry since placement')
        if row.get('bone_anatomy') in ('MANDIBLE', 'MIXED') and row.get('articulation_reviewed') is not True:
            raise ValueError(f'{target.label}: articulation unreviewed')
    return dict(status='freeze_matched', protocol_id=protocol['protocol_id'], protocol_sha256=sha256_file(cfg.protocol), subject_level_validation=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--development-report', required=True)
    parser.add_argument('--protocol-id', required=True)
    parser.add_argument('--split-manifest', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        validate_outputs([args.development_report, args.split_manifest], [args.output])
        with open(args.development_report, encoding='utf-8') as stream:
            report = json.load(stream)
        frozen = frozen_from_report(report, args.protocol_id, sha256_file(args.split_manifest))
        with atomic_text(args.output) as stream:
            json.dump(frozen, stream, indent=2, allow_nan=False)
        return 0
    except (KeyError, ValueError, OSError) as exc:
        print(f'[FATAL ERROR] {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
