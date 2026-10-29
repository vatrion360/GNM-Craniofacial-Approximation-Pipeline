"""Migration invariants against committed pre-migration values, not source validation."""
import hashlib
import json
from pathlib import Path

from cranio import landmarks, paper_reference, tissue
from cranio.config import PipelineConfig
from gnm_reconstruct import parse_args

BASELINE = json.loads((Path(__file__).parent/'fixtures'/'tissue_defaults_24d3706.json').read_text())


def test_every_default_side_order_and_source_matches_before_migration_exactly():
    # JSON normalization changes tuples to lists; no rounding/tolerance is used.
    assert json.loads(json.dumps(landmarks.LANDMARK_INFO)) == BASELINE['landmarks']
    assert landmarks.LANDMARK_ORDER == BASELINE['order']
    assert list(landmarks.LEGACY_LANDMARK_ORDER) == BASELINE['legacy_order']
    assert landmarks.REGION_OFFSETS_MM == BASELINE['regions']
    assert {k: landmarks.initial_tissue_source(k) for k in landmarks.LANDMARK_ORDER} == BASELINE['sources']
    assert json.loads(json.dumps(paper_reference.TABLE2)) == BASELINE['paper']
    assert paper_reference.reference_metadata() == BASELINE['paper_meta']
    assert paper_reference.CITATION == BASELINE['citation']
    assert paper_reference.TISSUE_SOURCE == BASELINE['tissue_source']
    # Compare float encodings too, not just numerical equality.
    for label, (value, _) in landmarks.LANDMARK_INFO.items():
        assert value.hex() == BASELINE['landmarks'][label][0].hex()


def test_scalp_default_shared_and_explicit_case_override_retained():
    expected = BASELINE['scalp_offset_mm']
    assert landmarks.SCALP_OFFSET_MM == expected
    assert PipelineConfig().scalp_offset_mm == expected
    assert parse_args(['--input', 'case.csv']).scalp_offset_mm == expected
    assert parse_args(['--input', 'case.csv', '--scalp-offset-mm', '2.75']).scalp_offset_mm == 2.75


def test_legacy_and_transcribed_defaults_remain_distinct_and_unverified():
    legacy = tissue.load_table('legacy_hardcoded').document
    paper = tissue.load_table('var2026_table2').document
    assert len(legacy['landmarks']) == 27 and len(legacy['regions']) == 6
    assert len(paper['landmarks']) == 32
    assert legacy['landmarks']['Nasion']['central_mm'] != paper['landmarks']['Nasion']['central_mm']
    assert legacy['citation'] is None and legacy['doi'] is None
    assert paper['citation'] == BASELINE['citation']
    for table in (legacy, paper):
        assert table['posture'] is None and table['measurement_method'] is None
        assert table['n'] is None and table['age_range_years'] is None
        for row in [*table['landmarks'].values(), *table['regions'].values()]:
            assert row['sd_mm'] is None and row['estimator'] is None
            assert row['measurement_direction'] is None
            assert row['provenance'] == table['provenance']


def test_default_catalogue_does_not_claim_to_be_applied_to_case():
    record = landmarks.default_tissue_records()
    assert 'Actual marker targets/sources come from case CSV' in record['interpretation']
    assert [t['id'] for t in record['tables']] == ['legacy_hardcoded', 'var2026_table2']
    for table in record['tables']:
        assert table['warnings']
        assert table['sha256'] == hashlib.sha256(tissue.table_path(table['id']).read_bytes()).hexdigest()


def test_tissue_changes_are_included_in_implementation_hash(tmp_path, monkeypatch):
    from cranio import provenance
    package = tmp_path/'cranio'
    data = package/'data'/'tissue'
    data.mkdir(parents=True)
    (package/'provenance.py').write_text('# synthetic source fixture')
    file = data/'table.json'
    file.write_text('{"revision":"before"}')
    monkeypatch.setattr(provenance, '__file__', str(package/'provenance.py'))
    before = provenance.implementation_manifest()
    assert 'cranio/data/tissue/table.json' in before['files']
    file.write_text('{"revision":"after"}')
    after = provenance.implementation_manifest()
    assert before['source_sha256'] != after['source_sha256']
    assert before['files']['cranio/provenance.py'] == after['files']['cranio/provenance.py']


def test_table_io_does_not_mutate_case_marker_csv(tmp_path):
    from cranio.io_csv import read_marker_csv, write_marker_csv_v3
    path = tmp_path/'manual.csv'
    rows = [dict(label='Nasion', vertex=1, placed=1, x=11., y=12., z=13., weight=.4,
                 tissue_depth_mm=2.75, tissue_source='individual manual measurement')]
    write_marker_csv_v3(path, rows, {})
    before = path.read_bytes()
    for table_id in ('legacy_hardcoded', 'var2026_table2'):
        tissue.export_csv(tmp_path/(table_id+'.csv'), tissue.load_table(table_id).document)
    assert path.read_bytes() == before
    targets, _, metadata = read_marker_csv(path, {}, {})
    assert targets[0].xyz.tolist() == [11., 12., 13.]
    assert targets[0].weight == .4
    assert metadata['marker_records']['Nasion']['tissue_depth_mm'] == 2.75
    assert metadata['marker_records']['Nasion']['tissue_source'] == 'individual manual measurement'
