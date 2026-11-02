"""Optional bone bookkeeping must not silently add or change skin-fit constraints."""
import copy
import json
from pathlib import Path
import numpy as np
import pytest

from cranio import craniometry as cm
from cranio.landmarks import BONE_REFERENCE_EXTENSIONS as EXT, LANDMARK_ORDER, LANDMARK_INFO, marker_labels
from cranio.paper_reference import PAPER_DEFINITIONS


def point(code='ss', *, reviewed=False):
    return dict(code=code, status='observed', xyz_mm=[0., 0., 0.], definition_reviewed=reviewed,
                definition_text='Synthetic test definition only', definition_source='Synthetic fixture, not human anatomy')


def test_catalog_preserves_default_markers_and_bone_order():
    assert len(LANDMARK_ORDER) == len(LANDMARK_INFO) == 48
    assert len(set(LANDMARK_ORDER)) == 48
    assert len(marker_labels('LEGACY_27')) == 27 and len(marker_labels('PAPER_32')) == 32
    assert len(cm.POINTS) == 22 and len(cm.ALL_POINTS) == 34 and len(cm.MEASUREMENTS) == 14
    assert list(cm.ALL_POINTS)[:22] == list(cm.POINTS)
    assert set(EXT).isdisjoint(cm.POINTS)
    for code in ('ba', 'b', 'op', 'ft_R', 'ft_L'):
        assert code in cm.POINTS and code not in EXT
    for code, entry in EXT.items():
        assert not entry['fit_target'] and entry['definition_status'] == 'needs_expert_review'
        assert entry['gnm_vertex'] is entry['tissue_depth_mm'] is entry['sd_mm'] is None
        if entry['existing_marker']:
            assert entry['definition_text'] == PAPER_DEFINITIONS[entry['existing_marker']]
            assert entry['existing_marker'] in LANDMARK_INFO
        else:
            assert entry['definition_text'] is entry['definition_source'] is None


def test_orbitale_reuses_rim_not_foramen_and_menton_not_gnathion():
    assert EXT['or_R']['existing_marker'] == 'Suborbitale_Dr'
    assert EXT['or_L']['existing_marker'] == 'Suborbitale_St'
    assert EXT['me']['existing_marker'] == 'Menton'
    assert EXT['po_R']['reference_frame_only'] and EXT['po_L']['reference_frame_only']
    assert EXT['po_R']['side'] == -1 and EXT['po_L']['side'] == 1


@pytest.mark.parametrize('code', list(EXT))
def test_new_points_accept_independent_fragments_and_keep_14_chords(code):
    doc = cm.empty_document()
    doc['points'] = [point(code, reviewed=True)]
    before = copy.deepcopy(doc)
    points, bindings = cm.validate_document(doc)
    assert points[code]['xyz_mm'] == [0., 0., 0.] and not bindings
    rows = cm.measure(doc)
    assert len(rows) == 14 and all(r['bone_mm'] is None for r in rows)
    assert doc == before


@pytest.mark.parametrize('value', ['', ' unspecified ', 'legacy-unvalidated', 'TODO(verify-source)',
                                 'needs_expert_review', 'not_configured', '[de completat]'])
def test_review_requires_nonplaceholder_definition_and_source(value):
    for field in ('definition_text', 'definition_source'):
        doc = cm.empty_document()
        row = point(reviewed=True)
        row[field] = value
        doc['points'] = [row]
        with pytest.raises(ValueError, match=field):
            cm.validate_document(doc)
        row['definition_reviewed'] = False
        assert cm.validate_document(doc)[0]['ss']['definition_reviewed'] is False


def test_aliases_cannot_double_count_same_bone_point():
    doc = cm.empty_document()
    doc['points'] = [point('A'), point('B')]
    assert set(cm.validate_document(doc)[0]) == {'ss', 'sm'}
    doc['points'].append(point('ss'))
    with pytest.raises(ValueError, match='duplicate'):
        cm.validate_document(doc)


def test_missing_and_reconstructed_do_not_become_observed():
    doc = cm.empty_document()
    doc['points'] = [dict(point('po_L'), status='missing', xyz_mm=None),
                     dict(point('co_R'), status='reconstructed')]
    parsed, _ = cm.validate_document(doc)
    assert parsed['po_L']['xyz_mm'] is None
    assert parsed['co_R']['status'] == 'reconstructed'
    assert 'co_L' not in parsed


def test_new_points_cannot_enable_unregistered_skin_measurements():
    doc = cm.empty_document()
    doc['bindings'] = [dict(measurement='po-po', enabled=True)]
    with pytest.raises(ValueError, match='Unknown'):
        cm.validate_document(doc)


def test_v3_metadata_roundtrip_and_offline_mesh_identity(marker_file, model_file, tmp_path):
    from cranio.io_csv import read_marker_csv
    from cranio.config import PipelineConfig
    from cranio.pipeline import run_pipeline
    lines = marker_file.read_text().splitlines(keepends=True)
    metadata = json.loads(lines[1].lstrip('# '))
    doc = cm.empty_document('synthetic-extended-case')
    doc['points'] = [point('po_R', reviewed=True), dict(point('co_L'), status='reconstructed')]
    metadata['craniometry'] = doc
    lines[1] = '# '+json.dumps(metadata)+'\n'
    extra = tmp_path/'extended.csv'
    extra.write_text(''.join(lines))
    before, _, _ = read_marker_csv(marker_file, {}, {})
    after, _, saved = read_marker_csv(extra, {}, {})
    assert saved['craniometry'] == doc and len(before) == len(after)
    np.testing.assert_array_equal([t.xyz for t in before], [t.xyz for t in after])
    results = []
    for name, source in [('base', marker_file), ('extra', extra)]:
        config = PipelineConfig(input=str(source), npz=str(model_file), output=str(tmp_path/f'{name}.obj'), regularization='30')
        assert run_pipeline(config) == 0
        results.append(config)
    for field in ('output', 'output_statistical', 'output_error_mesh'):
        assert Path(getattr(results[0], field)).read_bytes() == Path(getattr(results[1], field)).read_bytes()
    report = json.loads(Path(results[1].output_json).read_text())
    assert report['marker_metadata']['craniometry']['points'] == doc['points']
