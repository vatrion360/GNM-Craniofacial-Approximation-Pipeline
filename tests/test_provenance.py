import json
import numpy as np
import pytest
from cranio.backend import GNMBackend
from cranio.config import PipelineConfig
from cranio.io_csv import read_marker_csv, write_marker_csv_v3
from cranio.landmarks import bilateral_pairs, side_of
from cranio.mapping import reviewed_vertices
from cranio.pipeline import run_pipeline
from cranio.prior import load_prior
from cranio.protocol import frozen_from_report, validate_protocol
from cranio.validation import sha256_file


def test_all_orbital_pairs_are_audited():
    pairs = bilateral_pairs()
    assert len(pairs) == 17
    assert ('Orbita_Dr_Int', 'Orbita_St_Int') in pairs
    assert ('Orbita_Dr_Ext', 'Orbita_St_Ext') in pairs
    assert side_of('Orbita_Dr_Ext') == -1 and side_of('Orbita_St_Int') == 1


def test_multiline_csv_and_duplicate_headers(tmp_path):
    path = tmp_path/'quoted.csv'
    note = 'first line\n# data, not a comment\nlast line'
    write_marker_csv_v3(path, [dict(label='Nasion', vertex=12319, placed=1, x=0, y=0, z=0, weight=1, marker_notes=note)], {})
    targets, _, meta = read_marker_csv(path, {}, {})
    assert len(targets) == 1 and meta['marker_records']['Nasion']['marker_notes'] == note
    text = path.read_text()
    path.write_text(text.replace('label,vertex,', 'label,label,'))
    with pytest.raises(ValueError, match='duplicate column'):
        read_marker_csv(path, {}, {})
    path.write_text(text[:text.rfind(chr(34))])
    with pytest.raises(ValueError, match='Malformed CSV'):
        read_marker_csv(path, {}, {})


def test_reviewed_map_identity_and_duplicates():
    doc = dict(schema_version=1, model_sha256='a'*64, landmarks={'Nasion': dict(vertex_index=2, reviewed=True)})
    assert reviewed_vertices(doc, 'a'*64, 10) == {'Nasion': 2}
    with pytest.raises(ValueError, match='mismatch'):
        reviewed_vertices(doc, 'b'*64, 10)
    doc['landmarks']['Rhinion'] = dict(vertex_index=2, reviewed=True)
    with pytest.raises(ValueError, match='duplicate'):
        reviewed_vertices(doc, 'a'*64, 10)
    with pytest.raises(ValueError, match='Legacy manual'):
        reviewed_vertices({'nasion': dict(source='manual_picked_blender', vertex_index=2)}, 'a'*64, 10)
    assert reviewed_vertices({'nasion': dict(vertex_index=2)}, 'a'*64, 10) == {}


@pytest.mark.parametrize('kind', ['missing', 'nan', 'zero', 'pickle'])
def test_invalid_prior_archives(tmp_path, kind):
    path = tmp_path/'prior.npz'
    mean, scale = np.zeros(3), np.ones(3)
    if kind == 'nan': mean[0] = np.nan
    if kind == 'zero': scale[0] = 0
    if kind == 'pickle': mean = np.array([{}, {}, {}], dtype=object)
    np.savez(path, **({'mean': mean} if kind == 'missing' else dict(mean=mean, scale=scale)))
    with pytest.raises(ValueError):
        load_prior(path, 3)


def test_report_replay_and_protocol_freeze(tmp_path, model_file, marker_file):
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path/'face.obj'), regularization='30', geometry_qc='full')
    assert run_pipeline(cfg) == 0
    report = json.loads(open(cfg.output_json).read())
    assert report['schema_version'] == 2 and report['solver']['converged'] and report['solver']['irls_layers'] == 1
    assert report['software']['implementation']['files']['cranio/optimize.py']
    model, transform = GNMBackend(str(model_file)).load(), report['transform']
    replay = transform['scale']*(model.generate(report['identity_coefficients']) @ np.array(transform['rotation']).T)+transform['translation_mm']
    assert np.max(np.linalg.norm(replay-model.mu, axis=1)) < .001
    protocol = frozen_from_report(report, 'ct-study/r1', 'c'*64)
    path = tmp_path/'protocol.json'
    path.write_text(json.dumps(protocol))
    cfg.protocol = str(path)
    targets, _, meta = read_marker_csv(marker_file, {}, {})
    meta.update(case_id='synthetic', observer_id='observer1', protocol_id='ct-study/r1', split_sha256='c'*64,
        acquisition_sha256='d'*64, segmentation_revision='fixture', coordinate_frame='fixture-mm',
        bone_sources=[dict(id='source', geometry_sha256='e'*64)])
    for record in meta['marker_records'].values():
        record.update(mapping_reviewed=True, bone_status='observed', bone_source_id='source', bone_source_geometry_sha256='e'*64)
    assert validate_protocol(cfg, meta, targets, sha256_file(model_file))['status'] == 'freeze_matched'
    # Malformed provenance must fail explicitly, never overwrite duplicate
    # sources or escape the CLI's validation boundary with TypeError/KeyError.
    from copy import deepcopy
    malformed = [
        ('case_metadata', []),
        ('bone_sources', {}),
        ('bone_sources', [None]),
        ('bone_sources', [{}]),
        ('bone_sources', [dict(id=[], geometry_sha256='e'*64)]),
        ('bone_sources', [dict(id='source', geometry_sha256='not-a-hash')]),
        ('bone_sources', meta['bone_sources']*2),
        ('marker_records', []),
        ('marker_records', {targets[0].label: None}),
    ]
    for key, value in malformed:
        invalid = deepcopy(meta)
        invalid[key] = value
        with pytest.raises(ValueError):
            validate_protocol(cfg, invalid, targets, sha256_file(model_file))
    invalid = deepcopy(meta)
    invalid['marker_records'][targets[0].label]['bone_source_id'] = []
    with pytest.raises(ValueError, match='ID must be a string'):
        validate_protocol(cfg, invalid, targets, sha256_file(model_file))
    for split_hash in ('g'*64, None, 'c'*63):
        with pytest.raises(ValueError, match='SHA-256'):
            frozen_from_report(report, 'ct-study/r1', split_hash)
    cfg.dense_weight = .6
    with pytest.raises(ValueError, match='settings'):
        validate_protocol(cfg, meta, targets, sha256_file(model_file))
    cfg.dense_weight = .5
    meta['marker_records'][targets[0].label]['bone_source_geometry_sha256'] = 'f'*64
    with pytest.raises(ValueError, match='changed source'):
        validate_protocol(cfg, meta, targets, sha256_file(model_file))


def test_qc_failure_keeps_report_with_nonzero_exit(tmp_path, model_file, marker_file, monkeypatch):
    import cranio.quality
    original = cranio.quality.geometry_quality
    def forced_failure(*args, **kwargs):
        result = original(*args, **kwargs)
        result['status'] = 'needs_review'
        return result
    monkeypatch.setattr(cranio.quality, 'geometry_quality', forced_failure)
    cfg = PipelineConfig(input=str(marker_file), npz=str(model_file), output=str(tmp_path/'face.obj'), regularization='30', geometry_qc='full', require_qc=True)
    assert run_pipeline(cfg) == 3
    report = json.loads(open(cfg.output_json).read())
    assert report['status'] == 'completed' and report['geometry_quality']['status'] == 'needs_review'
