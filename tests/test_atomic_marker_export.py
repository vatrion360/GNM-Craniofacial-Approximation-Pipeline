"""Failed export must not truncate or replace an existing case file."""
import csv
import io
import json

import pytest

from cranio.io_csv import V3_FIELDS, V3_MAGIC, read_marker_csv, write_marker_csv_v3, write_marker_csv_v2


def _row():
    return dict(label='Nasion', vertex=12319, placed=1, x=0, y=0, z=7,
                weight=1, bone_x=0, bone_y=0, bone_z=0, tissue_depth_mm=7,
                marker_notes='Știință, "quoted"\n# still data', tissue_source='synthetic')


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('failure', ['duplicate', 'metadata', 'row_stream', 'fields', 'replace'])
def test_failed_export_preserves_destination_and_cleans_temporary(tmp_path, monkeypatch, existing, failure):
    import cranio.export
    path = tmp_path/'caz șță.csv'
    original = b'previous case bytes\r\n'
    if existing:
        path.write_bytes(original)
    rows, metadata = [_row()], {}
    if failure == 'duplicate':
        rows *= 2
    elif failure == 'metadata':
        metadata['invalid'] = float('nan')
    elif failure == 'row_stream':
        def broken_rows():
            yield _row()
            raise OSError('interrupted row source')
        rows = broken_rows()
    elif failure == 'fields':
        rows[0]['unknown_column'] = 'must not silently drop data'
    else:
        def denied_replace(*args):
            raise PermissionError('destination locked')
        monkeypatch.setattr(cranio.export.os, 'replace', denied_replace)
    with pytest.raises((ValueError, OSError)):
        write_marker_csv_v3(path, rows, metadata)
    assert path.exists() == existing
    if existing:
        assert path.read_bytes() == original
    assert not list(tmp_path.glob('*.tmp'))


def test_valid_export_retains_serialization_and_multiline_notes(tmp_path):
    path = tmp_path/'subfolder'/'caz șță.csv'
    meta = dict(case_id='synthetic', version=3, units='mm', coordinate_space='world')
    expected = io.StringIO(newline='')
    expected.write(V3_MAGIC+'\n# '+json.dumps(meta, sort_keys=True, ensure_ascii=False)+'\n')
    writer = csv.DictWriter(expected, fieldnames=V3_FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerow(_row())
    write_marker_csv_v3(path, [_row()], {'case_id': 'synthetic'})
    assert path.read_bytes() == expected.getvalue().encode('utf-8')
    _, _, metadata = read_marker_csv(path, {}, {})
    assert metadata['marker_records']['Nasion']['marker_notes'] == _row()['marker_notes']
    write_marker_csv_v3(path, [])
    assert read_marker_csv(path, {}, {})[0] == []


def test_legacy_serialization_failure_also_preserves_destination(tmp_path):
    path = tmp_path/'legacy.csv'
    path.write_bytes(b'old case')
    with pytest.raises(ValueError):
        write_marker_csv_v2(path, [], {'invalid': float('nan')})
    assert path.read_bytes() == b'old case'
    assert not list(tmp_path.glob('*.tmp'))
