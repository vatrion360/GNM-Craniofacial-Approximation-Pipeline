"""Synthetic exchange fixtures only; numbers are not anatomical estimates."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from cranio import tissue


def sample():
    table = tissue.empty_table('synthetic_exchange')
    table.update(citation='Engineering fixture, no source claim', doi='synthetic identifier',
                 measurement_method='other', posture='fixture', sex='fixture',
                 age_range_years=[0, 1], ancestry_label='Fixture label preserved exactly', n=10)
    table['landmarks']['point_Ș'] = dict(central_mm=2.5, sd_mm=1., p10_mm=.2, p90_mm=4., n=7,
        estimator='median', measurement_direction='other', direction_notes='fixture axis',
        notes='Synthetic, "quoted"\nmultiline text', provenance='user_supplied')
    table['regions']['shell'] = dict(central_mm=None)
    return table


def test_normalization_does_not_impute_or_mutate():
    original = sample()
    snapshot = copy.deepcopy(original)
    result, diagnostics = tissue.validate_table(original)
    assert original == snapshot
    assert result['regions']['shell']['sd_mm'] is None
    assert result['regions']['shell']['central_mm'] is None
    assert 'regions.shell' in ' '.join(diagnostics)
    assert result['regions']['shell']['estimator'] is None
    assert result['regions']['shell']['measurement_direction'] is None
    assert result['regions']['shell']['provenance'] == 'user_supplied'


@pytest.mark.parametrize('field,value', [('central_mm', -1), ('sd_mm', -1), ('p10_mm', -1),
    ('central_mm', float('nan')), ('sd_mm', float('inf')), ('central_mm', True),
    ('central_mm', '3'), ('n', 0), ('n', 1.5), ('n', True), ('estimator', 'unknown'),
    ('measurement_direction', 'automatic'), ('extra', 1), ('notes', None)])
def test_reject_bad_rows(field, value):
    table = sample()
    table['landmarks']['point_Ș'][field] = value
    with pytest.raises(ValueError):
        tissue.validate_table(table)


@pytest.mark.parametrize('field,value', [('schema_version', 2), ('schema_version', True),
    ('units', 'm'), ('id', '../escape'), ('revision', ''), ('citation', '  '),
    ('age_range_years', [3, 1]), ('age_range_years', [1]), ('age_range_years', [None, 1]),
    ('n', -1), ('n', False), ('provenance', 'verified'), ('extra', 1)])
def test_reject_bad_metadata(field, value):
    table = sample()
    table[field] = value
    with pytest.raises(ValueError):
        tissue.validate_table(table)


def test_percentile_order_and_zero_sd():
    table = sample()
    table['landmarks']['point_Ș'].update(p10_mm=5, p90_mm=1)
    with pytest.raises(ValueError, match='P10'):
        tissue.validate_table(table)
    table['landmarks']['point_Ș'].update(p10_mm=1, p90_mm=5, sd_mm=0)
    _, warnings = tissue.validate_table(table)
    assert any('undefined' in w for w in warnings)


def test_required_fields_and_empty_template():
    table = tissue.empty_table('empty')
    assert any('No tissue' in x for x in tissue.validate_table(table)[1])
    table['landmarks']['unknown'] = {}
    with pytest.raises(ValueError, match='central_mm'):
        tissue.validate_table(table)
    table = sample()
    del table['citation']
    with pytest.raises(ValueError, match='citation'):
        tissue.validate_table(table)


@pytest.mark.parametrize('bad', ['{"id":"one","id":"two"}', '{"a":{"x":1,"x":2}}',
                                '{"a":NaN}', '{"a":Infinity}'])
def test_json_never_accepts_duplicate_keys_or_nonfinite_tokens(tmp_path, bad):
    path = tmp_path/'bad.json'
    path.write_text(bad)
    with pytest.raises(ValueError):
        tissue.load_table(path)


def test_csv_json_roundtrip_and_file_hash(tmp_path):
    csv_path, json_path = tmp_path/'table.csv', tmp_path/'table.json'
    table = sample()
    tissue.export_csv(csv_path, table)
    imported = tissue.import_csv(csv_path)
    assert imported == tissue.validate_table(table)[0]
    tissue.write_table(json_path, imported)
    loaded = tissue.load_table(json_path)
    assert loaded.document == imported
    assert loaded.sha256 == hashlib.sha256(json_path.read_bytes()).hexdigest()
    assert loaded.record()['revision'] == '1'
    assert loaded.record()['warnings']
    # UTF-8 BOM is accepted, without dropping metadata or altering text.
    csv_path.write_bytes(b'\xef\xbb\xbf'+csv_path.read_bytes())
    assert tissue.import_csv(csv_path) == imported


@pytest.mark.parametrize('direction', ['bone_normal', 'vertical', 'sagittal', 'other', None])
def test_direction_is_metadata_not_inferred_or_applied(direction, tmp_path):
    table = sample()
    table['landmarks']['point_Ș']['measurement_direction'] = direction
    tissue.export_csv(tmp_path/'t.csv', table)
    assert tissue.import_csv(tmp_path/'t.csv')['landmarks']['point_Ș']['measurement_direction'] == direction


@pytest.mark.parametrize('estimator', ['mean', 'median', 'shorth', '75-shormax', None])
def test_estimator_preserved_without_computation(estimator):
    table = sample()
    table['landmarks']['point_Ș']['estimator'] = estimator
    result, _ = tissue.validate_table(table)
    assert result['landmarks']['point_Ș']['central_mm'] == 2.5
    assert result['landmarks']['point_Ș']['estimator'] == estimator


@pytest.mark.parametrize('header,rows', [
    ('scope,label,central_mm', ['landmarks,a,1', 'landmarks,a,2']),
    ('scope,label,label,central_mm', ['landmarks,a,a,1']),
    ('scope,label,central_mm,typo', ['landmarks,a,1,2']),
    ('scope,label,central_mm', ['landmarks,a,NaN']),
    ('scope,label,central_mm', ['unknown,a,1']),
    ('scope,label,central_mm', ['landmarks, ,1']),
    ('scope,label,central_mm', ['landmarks,a']),
    ('scope,label,central_mm', ['landmarks,a,1,2']),
    ('scope,label,central_mm,n', ['landmarks,a,1,1.5']),
    ('scope,label,central_mm', ['landmarks,"unfinished,1']),
])
def test_csv_rejects_malformed_rows(tmp_path, header, rows):
    metadata = tissue.empty_table('synthetic')
    for key in ('landmarks', 'regions'):
        del metadata[key]
    path = tmp_path/'bad.csv'
    path.write_text(tissue.CSV_MAGIC+'\n# '+json.dumps(metadata)+'\n'+header+'\n'+'\n'.join(rows)+'\n')
    with pytest.raises(ValueError):
        tissue.import_csv(path)


def test_csv_optional_columns_and_unknown_depth(tmp_path):
    table = sample()
    path = tmp_path/'table.csv'
    tissue.export_csv(path, table)
    with path.open(newline='', encoding='utf-8') as f:
        lines = [f.readline(), f.readline()]
    path.write_text(''.join(lines)+'scope,label,central_mm\nlandmarks,unknown,\n')
    row = tissue.import_csv(path)['landmarks']['unknown']
    assert row['central_mm'] is None and row['sd_mm'] is None


def test_cli_roundtrip_refuses_overwrite_input_and_preserves_failed_output(tmp_path, capsys):
    path, exchange, restored = [tmp_path/x for x in ('table.json', 'table.csv', 'restored.json')]
    assert tissue.main(['template', '--id', 'empty', '--output', str(path)]) == 0
    assert tissue.main(['inspect', str(path)]) == 0
    assert tissue.main(['export-csv', '--input', str(path), '--output', str(exchange)]) == 0
    assert tissue.main(['import-csv', '--input', str(exchange), '--output', str(restored)]) == 0
    assert tissue.load_table(path).document == tissue.load_table(restored).document
    before = path.read_bytes()
    assert tissue.main(['template', '--id', 'empty', '--output', str(path)]) == 2
    assert tissue.main(['template', '--id', '../invalid', '--output', str(path), '--overwrite']) == 2
    assert tissue.main(['export-csv', '--input', str(path), '--output', str(path), '--overwrite']) == 2
    assert path.read_bytes() == before
    assert 'unknown' in capsys.readouterr().out


def test_atomic_writes_keep_destination_on_failure(tmp_path, monkeypatch):
    import cranio.export
    path = tmp_path/'table.json'
    path.write_text('previous file')
    def fail(*args):
        raise OSError('simulated replace failure')
    monkeypatch.setattr(cranio.export.os, 'replace', fail)
    with pytest.raises(OSError):
        tissue.write_table(path, sample())
    assert path.read_text() == 'previous file'
    assert list(tmp_path.iterdir()) == [path]


def test_bundled_id_resolution_and_no_external_schema_fetch(tmp_path, monkeypatch):
    # The ID resolver never treats an untrusted string as an import or URL.
    assert tissue.table_path('some_table') == tissue.DATA_DIR/'some_table.json'
    assert tissue.table_path(Path('some_table')) == Path('some_table')
    with pytest.raises(ValueError, match='reference'):
        tissue._validate({}, {'$ref': 'https://example.invalid/schema'}, {})
    with pytest.raises(ValueError, match='keywords'):
        tissue._validate({}, {'unimplementedConstraint': True}, {})


def test_zip_includes_schema_and_is_importable_without_source_tree(tmp_path):
    from tools.build_addon import build
    archive = build(tmp_path/'addon.zip')
    with ZipFile(archive) as z:
        z.extractall(tmp_path/'installed')
        assert 'gnm_cranio/cranio/data/tissue/schema.json' in z.namelist()
    code = "from cranio.tissue import empty_table, validate_table; assert validate_table(empty_table('fixture'))[1]"
    # Isolated search path: don't accidentally test the working tree.
    root = tmp_path/'installed'/'gnm_cranio'
    subprocess.run([sys.executable, '-I', '-c', f'import sys; sys.path.insert(0, {str(root)!r}); '+code],
                   cwd=tmp_path, check=True)


def test_loaded_document_edits_do_not_change_source_record(tmp_path):
    path = tmp_path/'table.json'
    tissue.write_table(path, sample())
    loaded = tissue.load_table(path)
    record = loaded.record()
    edited = loaded.document
    edited['citation'] = 'different source'
    edited['landmarks']['point_Ș']['central_mm'] = 99
    assert loaded.record() == record
    assert loaded.document['landmarks']['point_Ș']['central_mm'] == 2.5


def test_huge_numbers_and_newline_id_are_rejected_cleanly():
    table = sample()
    table['landmarks']['point_Ș']['central_mm'] = 10**1000
    with pytest.raises(ValueError):
        tissue.validate_table(table)
    table = sample()
    table['id'] += '\n'
    with pytest.raises(ValueError):
        tissue.validate_table(table)
