"""Anatomical bookkeeping and observable numerical effects; no accuracy claims."""
import copy
import json
from types import SimpleNamespace
import numpy as np
import pytest
from numpy.testing import assert_allclose
from cranio import craniometry as cm, measurement_fit as mf
from cranio.optimize import fit_identity
from cranio.preview import fit_preview


def case():
    doc = cm.empty_document('synthetic-case')
    doc['model_sha256'] = 'a'*64
    doc['bone_sources'] = [dict(id='vault', geometry_sha256='b'*64)]
    doc['points'] = [dict(code=code, xyz_mm=xyz, status='observed', definition_reviewed=True,
                         source_id='vault', source_geometry_sha256='b'*64)
                     for code, xyz in [('eu_R', [60., 0, 0]), ('eu_L', [-60., 0, 0])]]
    doc['bindings'] = [dict(measurement='eu-eu', enabled=True, mapping_reviewed=True,
        marker_a='right', marker_b='left', target_mode='skin_markers', sigma_mm=2., influence=1.,
        method='Synthetic offset targets for software verification only')]
    records = {label: dict(mapping_reviewed=True, bone_status='observed', tissue_source='synthetic',
        bone_source_id='vault', bone_source_geometry_sha256='b'*64) for label in ('right', 'left')}
    bones = dict(right=[60., 0, 0], left=[-60., 0, 0])
    return doc, records, bones


def resolve(doc, records, bones, labels=('right', 'left')):
    return cm.resolve_controls(doc, list(labels), [0, 1][:len(labels)],
        [[65., 0, 0], [-65., 0, 0]][:len(labels)], records, bones, 'a'*64)


def test_catalog_missing_fragments_and_bone_vs_skin():
    doc, records, bones = case()
    rows = {r['measurement']: r for r in cm.measure(doc)}
    assert len(rows) == 14 and len(cm.POINTS) == 22
    assert rows['eu-eu']['bone_mm'] == 120
    assert rows['l-o']['missing'] == ['l', 'o']
    controls, skipped = resolve(doc, records, bones)
    assert controls[0]['target_mm'] == 130 and controls[0]['bone_mm'] == 120 and not skipped
    doc['points'].pop()
    assert next(r for r in cm.measure(doc) if r['measurement'] == 'eu-eu')['bone_mm'] is None
    with pytest.raises(ValueError, match='observed bone'):
        resolve(doc, records, bones)


def test_reconstructed_half_never_becomes_observed_or_mirrored():
    doc, records, bones = case()
    doc['points'][1]['status'] = 'reconstructed'
    measurement = next(r for r in cm.measure(doc) if r['measurement'] == 'eu-eu')
    assert measurement['bone_mm'] == 120 and measurement['status'] == 'reconstructed'
    with pytest.raises(ValueError, match='observed bone'):
        resolve(doc, records, bones)
    controls, skipped = resolve(doc, records, bones, labels=('right',))
    assert not controls and skipped[0]['reason'] == 'skin endpoint not included in fit'


def test_chords_are_rigid_frame_invariant_and_mm_are_explicit():
    doc, _, _ = case()
    rotation, _ = np.linalg.qr(np.random.default_rng(4).normal(size=(3, 3)))
    for point in doc['points']:
        point['xyz_mm'] = (rotation @ point['xyz_mm']+[400, -700, 98]).tolist()
    assert cm.measure(doc)[4]['bone_mm'] == pytest.approx(120)
    doc['units'] = 'm'
    with pytest.raises(ValueError, match='world mm'):
        cm.measure(doc)


def test_anatomical_alias_is_canonical_and_cannot_duplicate_a_point():
    doc = cm.empty_document()
    doc['points'] = [dict(code='ftm_R', status='observed', xyz_mm=[1, 2, 3])]
    assert 'fmt_R' in cm.validate_document(doc)[0]
    doc['points'].append(dict(code='fmt_R', status='observed', xyz_mm=[2, 2, 3]))
    with pytest.raises(ValueError, match='duplicate'):
        cm.measure(doc)
    assert cm.BY_KEY['l-o'].b == 'o' and cm.BY_KEY['g-op'].b == 'op'
    assert not cm.BY_KEY['ba-b'].skin_control_allowed


@pytest.mark.parametrize('failure', ['nan', 'malformed_xyz', 'hash', 'stale', 'review', 'anchor', 'marker_review', 'wrong_model', 'base', 'bool_string', 'duplicate_pair'])
def test_invalid_or_unreviewed_controls_are_rejected(failure):
    doc, records, bones = case()
    if failure == 'nan': doc['points'][0]['xyz_mm'][0] = np.nan
    if failure == 'malformed_xyz': doc['points'][0]['xyz_mm'] = {'x': 0}
    if failure == 'hash': doc['points'][0]['source_geometry_sha256'] = 'wrong'
    if failure == 'stale': doc['bone_sources'][0]['geometry_sha256'] = 'c'*64
    if failure == 'review': doc['points'][0]['definition_reviewed'] = False
    if failure == 'anchor': bones['right'][0] += .2
    if failure == 'marker_review': records['left']['mapping_reviewed'] = False
    if failure == 'wrong_model': doc['model_sha256'] = 'c'*64
    if failure == 'base': doc['bindings'][0]['measurement'] = 'ba-b'
    if failure == 'bool_string': doc['bindings'][0]['enabled'] = 'false'
    if failure == 'duplicate_pair':
        doc['bindings'].append(dict(doc['bindings'][0], measurement='zy-zy'))
        doc['points'] += [dict(p, code=code) for p, code in zip(doc['points'][:2], ['zy_R', 'zy_L'])]
    with pytest.raises(ValueError):
        resolve(doc, records, bones)


def test_prediction_is_explicit_and_protocol_freezes_method_not_subject_values():
    doc, records, bones = case()
    binding = doc['bindings'][0]
    binding.update(target_mode='reviewed_prediction', target_mm=135.)
    assert resolve(doc, records, bones)[0][0]['target_mm'] == 135
    frozen = cm.control_protocol(doc)
    binding['target_mm'] = 140.
    assert cm.control_protocol(doc) == frozen
    binding['sigma_mm'] = 4.
    assert cm.control_protocol(doc) != frozen
    binding['method'] = ''
    with pytest.raises(ValueError, match='method'):
        resolve(doc, records, bones)


def test_legacy_endpoint_error_names_actual_fields_for_both_markers():
    doc, records, bones = case()
    for record in records.values():
        record.update(mapping_reviewed=False, tissue_source='legacy-unvalidated')
    before = copy.deepcopy(records)
    with pytest.raises(ValueError) as error:
        resolve(doc, records, bones)
    message = str(error.value)
    assert message.startswith('eu-eu: right:') and ' | left:' in message
    assert message.count('Skin correspondence reviewed is not confirmed') == 2
    assert message.count("Tissue source / method = 'legacy-unvalidated'") == 2
    assert 'Bone provenance' not in message
    assert records == before  # Diagnostics never certify or migrate case data.
    # Completing only one requirement must not mask the remaining blocker.
    for record in records.values():
        record['mapping_reviewed'] = True
    with pytest.raises(ValueError) as error:
        resolve(doc, records, bones)
    assert 'Skin correspondence reviewed' not in str(error.value)
    assert 'Tissue source / method' in str(error.value)
    for record in records.values():
        record['tissue_source'] = 'Synthetic fixture; not anatomical evidence'
    assert len(resolve(doc, records, bones)[0]) == 1


@pytest.mark.parametrize('field,value,expected', [
    ('bone_status', 'unspecified', "Bone provenance = 'unspecified'"),
    ('bone_status', 'reconstructed', "Bone provenance = 'reconstructed'"),
    ('bone_status', 'inferred', "Bone provenance = 'inferred'"),
    ('mapping_reviewed', False, 'Skin correspondence reviewed'),
    ('tissue_source', 'legacy-unvalidated', 'Tissue source / method'),
    ('tissue_source', 'unspecified', 'Tissue source / method'),
    ('tissue_source', '', 'Tissue source / method'),
    ('tissue_source', '  \t', 'Tissue source / method'),
    ('tissue_source', ' Legacy-Unvalidated ', 'Tissue source / method'),
    ('tissue_source', None, 'Tissue source / method'),
])
def test_endpoint_metadata_diagnostic_reports_only_the_failed_field(field, value, expected):
    doc, records, bones = case()
    records['right'][field] = value
    issues = cm.skin_marker_issues(records['right'])
    assert len(issues) == 1 and expected in issues[0]
    with pytest.raises(ValueError) as error:
        resolve(doc, records, bones)
    assert str(error.value) == f'eu-eu: right: {issues[0]}'


def problem():
    rng = np.random.default_rng(62)
    mu = rng.normal(size=(20, 3))*35
    basis = rng.normal(size=(3, 20, 3))*3
    idx = np.arange(20)
    target = mu.copy()*1.4+[10, -20, 50]
    control = dict(vertices=[0, 1], target_mm=np.linalg.norm(target[0]-target[1])+9., sigma_mm=3., influence=1.)
    return mu, basis, idx, target, [control]


def test_distance_jacobian_matches_finite_differences_at_nonunit_scale():
    mu, basis, _, _, controls = problem()
    prepared = mf.prepare(controls, len(mu), 20., .5)
    c, scale = np.array([.2, -.4, .3]), 1.7
    jac, rhs = mf.linear_rows(c, mu, basis, prepared, scale, np.ones(1))
    _, _, _, dist = mf.differences(c, mu, basis, prepared[0])
    assert_allclose(jac @ c-rhs, dist-prepared[1]/scale)
    for i in range(3):
        delta = np.eye(3)[i]*1e-6
        plus = mf.differences(c+delta, mu, basis, prepared[0])[3]
        minus = mf.differences(c-delta, mu, basis, prepared[0])[3]
        assert_allclose(jac[:, i], (plus-minus)/2e-6, rtol=1e-6)


@pytest.mark.parametrize('lam', [3., 'auto'])
def test_shared_fit_improves_skin_distance_without_changing_lambda_count(lam):
    mu, basis, idx, target, controls = problem()
    weights = np.ones(len(idx))
    base = fit_identity(mu, basis, idx, target, weights, lam=lam)
    settings = dict(measurement_controls=controls, measurement_weight=2.)
    offline = fit_identity(mu, basis, idx, target, weights, lam=lam, **settings)
    model = SimpleNamespace(mu=mu, basis=basis, identity_dim=3)
    snapshot = dict(labels=['P'+str(i) for i in idx], verts=idx, targets=target, weights=weights, **settings)
    live = fit_preview(model, snapshot, lam, {})
    for a, b in zip(live[:5], offline[:5]):
        assert_allclose(a, b, atol=1e-10)
    def error(result):
        vertices = result.scale*(mu+np.einsum('i,ivk->vk', result.coefficients, basis))
        return abs(cm.control_residuals(controls, vertices)[0]['residual_mm'])
    # Conditional LOO is marker-only and may deliberately choose stronger ridge;
    # require an observable pair improvement, not an assumed percentage gain.
    assert error(offline) < error(base)-.5
    disabled = fit_identity(mu, basis, idx, target, weights, lam=lam, measurement_controls=controls, measurement_weight=0.)
    assert_allclose(base.coefficients, disabled.coefficients, atol=0)
    assert base.scale == disabled.scale


def test_final_scale_retains_distance_control_even_without_deformation_basis():
    mu, basis, idx, target, controls = problem()
    basis[:] = 0
    result = fit_identity(mu, basis, idx, target, np.ones(len(idx)), lam=3,
        measurement_controls=controls, measurement_weight=5.)
    assert result.scale > 1.401  # Final marker-only Umeyama would reset this to exactly 1.4.
    assert_allclose(np.mean(result.scale*(mu @ result.rotation.T)+result.translation, axis=0), target.mean(axis=0))


def test_pair_count_does_not_inflate_block_mass_and_tolerance_has_effect():
    _, _, _, _, controls = problem()
    first = mf.prepare(controls, 20, 48, .5)[3]
    controls += [dict(controls[0], vertices=[2, 3])]
    second = mf.prepare(controls, 20, 48, .5)[3]
    assert first.sum() == pytest.approx(second.sum())
    controls[0]['sigma_mm'] *= 2
    assert mf.prepare(controls, 20, 48, .5)[3][0] == pytest.approx(second[0]/4)
    with pytest.raises(ValueError, match='Duplicate'):
        mf.prepare(controls*2, 20, 48, .5)


@pytest.mark.parametrize('external', [False, True])
def test_offline_document_report_and_active_control_roundtrip(tmp_path, model_file, external):
    from cranio.backend import GNMBackend
    from cranio.config import PipelineConfig
    from cranio.pipeline import run_pipeline
    from cranio.io_csv import write_marker_csv_v3
    from cranio.validation import sha256_file
    model = GNMBackend(str(model_file)).load()
    doc, _, _ = case()
    doc['model_sha256'] = sha256_file(model_file)
    bones = model.mu-[0, 0, 5]
    for point, xyz in zip(doc['points'], bones[:2]):
        point['xyz_mm'] = xyz.tolist()
    doc['bindings'][0].update(marker_a='P0', marker_b='P1')
    rows = [dict(label=f'P{i}', vertex=i, placed=1, x=x, y=y, z=z, weight=1.,
        bone_x=bones[i, 0], bone_y=bones[i, 1], bone_z=bones[i, 2], tissue_depth_mm=5.,
        tissue_source='synthetic fixture', bone_status='observed', mapping_reviewed=1,
        bone_source_id='vault', bone_source_geometry_sha256='b'*64)
        for i, (x, y, z) in enumerate(model.mu)]
    csv = tmp_path/'markers.csv'
    metadata = dict(case_id=doc['case_id'], model_sha256=doc['model_sha256'], bone_sources=doc['bone_sources'], craniometry=doc)
    document_path = tmp_path/'craniometry.json'
    document_path.write_text(json.dumps(dict(doc, measurements=cm.measure(doc))))
    if external:
        del metadata['craniometry']
    write_marker_csv_v3(csv, rows, metadata)
    cfg = PipelineConfig(input=str(csv), npz=str(model_file), output=str(tmp_path/'fit.obj'),
                         regularization='adaptive', measurement_weight=.5, geometry_qc='full',
                         craniometry=str(document_path) if external else None)
    assert run_pipeline(cfg) == 0
    report = json.loads(open(cfg.output_json).read())
    assert len(report['craniometry']['bone_measurements']) == 14
    assert report['lambda'] == pytest.approx(48/12)
    assert abs(report['craniometry']['statistical_skin'][0]['residual_mm']) < .001
    assert 'eu-eu' in open(cfg.output_stats).read()
    from cranio.protocol import frozen_from_report, validate_protocol
    from cranio.io_csv import read_marker_csv
    frozen = frozen_from_report(report, 'synthetic-protocol', 'c'*64)
    protocol_path = tmp_path/'protocol.json'
    protocol_path.write_text(json.dumps(frozen))
    cfg.protocol = str(protocol_path)
    targets, _, meta = read_marker_csv(csv, {}, {})
    meta.update(craniometry=doc, observer_id='synthetic-observer', protocol_id='synthetic-protocol',
        split_sha256='c'*64, acquisition_sha256='d'*64, segmentation_revision='fixture', coordinate_frame='world-mm')
    assert validate_protocol(cfg, meta, targets, sha256_file(model_file))['status'] == 'freeze_matched'
    changed = copy.deepcopy(meta)
    changed['craniometry']['bindings'][0]['sigma_mm'] = 4.
    with pytest.raises(ValueError, match='craniometry_policy'):
        validate_protocol(cfg, changed, targets, sha256_file(model_file))
    cfg.protocol = None
    cfg.output = str(tmp_path/'excluded.obj')
    cfg.output_json = cfg.output_stats = cfg.output_error_mesh = cfg.output_statistical = None
    cfg.exclude = ['P1']
    assert run_pipeline(cfg) == 0
    report = json.loads(open(cfg.output_json).read())
    assert not report['craniometry']['controls'] and report['craniometry']['skipped_controls']
    assert report['lambda'] == pytest.approx(48/11)
    # A gross misplaced skin/bone endpoint is removed automatically together
    # with its pair; the pair must not survive through its raw vertex indices.
    shift = np.array([180., -90., 120.])
    for axis, delta in zip('xyz', shift):
        rows[1][axis] += delta
        rows[1]['bone_'+axis] += delta
    doc['points'][1]['xyz_mm'] = (bones[1]+shift).tolist()
    document_path.write_text(json.dumps(doc))
    write_marker_csv_v3(csv, rows, metadata)
    cfg.output = str(tmp_path/'auto-excluded.obj')
    cfg.output_json = cfg.output_stats = cfg.output_error_mesh = cfg.output_statistical = None
    cfg.exclude, cfg.exclude_outliers, cfg.measurement_weight = [], True, .01
    assert run_pipeline(cfg) == 0
    report = json.loads(open(cfg.output_json).read())
    assert 'P1' in [row[0] for row in report['auto_excluded']]
    assert not report['craniometry']['controls']
    assert report['craniometry']['skipped_controls'][0]['measurement'] == 'eu-eu'
