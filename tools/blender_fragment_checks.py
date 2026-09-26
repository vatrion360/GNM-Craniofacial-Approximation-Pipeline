"""Headless acceptance for mixed-side fragments, safe originals and lambda."""
import math
import uuid

import bpy
from mathutils import Matrix, Vector
import numpy as np


def expect_cancel(operation, text):
    try:
        result = operation()
    except RuntimeError as exc:
        assert text in str(exc), str(exc)
    else:
        assert result == {'CANCELLED'}, result


def run_fragment_checks(addon):
    scene = bpy.data.scenes.new('Mixed fragments regression')
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = .001
    def empty(name, location):
        obj = bpy.data.objects.new(name, None)
        scene.collection.objects.link(obj)
        obj.location = location
        return obj
    for label, position, provenance in [
        ('Nasion', (0, 0, 0), 'observed'), ('Rhinion', (0, 30, 0), 'observed'),
        ('Glabella', (0, 0, 40), 'observed'), ('Pogonion', (500, 40, -50), 'observed'),
        ('Acanthion', (400, 30, 20), 'inferred')]:
        marker = scene.gnm_markers.add()
        marker.label = label
        marker.bone_empty = empty('bone_' + label, position)
        marker.bone_status = provenance
    scene.view_layers[0].update()
    plane = addon._fit_midsagittal_plane(scene)
    assert plane is not None and abs(plane[1].x) > .999999 and plane[2] < 1e-5
    # Only preserved, enabled cranial sites determine the automatic plane.
    scene.gnm_markers[0].use_for_plane = False
    assert addon._fit_midsagittal_plane(scene) is None
    scene.gnm_markers[0].use_for_plane = True

    coordinates = [(-4, 0, 12), (-4, 3, 12), (-4, 0, 15),
                   (3, 0, 0), (3, 3, 0), (3, 0, 3),
                   (-.5, 0, 8), (.5, 0, 8), (0, 1, 9)]
    mesh = bpy.data.meshes.new('Preserved mixed bones')
    mesh.from_pydata(coordinates, [], [(0, 1, 2), (3, 4, 5), (6, 7, 8)])
    source = bpy.data.objects.new('Right cranium + nasal bone + left mandible', mesh)
    scene.collection.objects.link(source)
    transform = Matrix.Translation((7, 2, 3)) @ Matrix.Rotation(.37, 4, 'Z') @ Matrix.Diagonal((2, .8, 1.3, 1))
    source.matrix_world = transform
    groups = [('Cranium right', [0, 1, 2]), ('Mandible left', [3, 4, 5]), ('Nasal preserved', [6, 7, 8])]
    for name, indices in groups:
        source.vertex_groups.new(name=name).add(indices, 1.0, 'REPLACE')
    cranial_plane = empty('Cranial plane', (0, 0, 0))
    cranial_plane.matrix_world = transform @ Matrix.Rotation(math.pi / 2, 4, 'Y')
    mandibular_plane = empty('Independent mandibular plane', (0, 0, 0))
    mandibular_plane.matrix_world = transform @ Matrix.Translation((1, 0, 0)) @ Matrix.Rotation(math.pi / 2, 4, 'Y')
    scene.gnm_settings.restoration_plane_object = cranial_plane
    scene.view_layers[0].update()
    rows = []
    for index, (name, _) in enumerate(groups):
        row = scene.gnm_restoration_regions.add()
        row.uid = uuid.uuid4().hex
        row.name, row.source_object, row.vertex_group = name, source, name
        row.action = 'KEEP' if index == 2 else 'MIRROR'
        row.anatomy = ['CRANIUM', 'MANDIBLE', 'NASAL'][index]
        row.donor_side = 'DR' if index == 0 else 'ST'
        rows.append(row)
    original_positions = [v.co[:] for v in source.data.vertices]
    original_faces = [tuple(p.vertices) for p in source.data.polygons]
    original_matrix = source.matrix_world.copy()
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        expect_cancel(bpy.ops.gnm.mirror_reconstruct, 'mandibular reference plane')
        assert all(row.result_object is None for row in rows)
        rows[1].plane_object = mandibular_plane
        assert bpy.ops.gnm.mirror_reconstruct() == {'FINISHED'}
        assert rows[2].result_object is None
        for row, start, x in [(rows[0], 0, 4), (rows[1], 3, -1)]:
            actual = np.array([v.co[:] for v in row.result_object.data.vertices])
            expected = np.array([(transform @ Vector((x, *coordinates[i][1:])))[:] for i in range(start, start+3)])
            for point in expected:
                assert np.min(np.linalg.norm(actual-point, axis=1)) < 1e-5
            assert len(row.result_object.data.polygons) == 1
        expected_normal = -(transform.to_3x3().inverted().transposed() @ Vector((1, 0, 0))).normalized()
        assert rows[0].result_object.data.polygons[0].normal.dot(expected_normal) > .999
        ids = [row.result_object.as_pointer() for row in rows[:2]]
        assert bpy.ops.gnm.mirror_reconstruct() == {'FINISHED'}
        assert ids == [row.result_object.as_pointer() for row in rows[:2]]
        # A mixed-side selection is rejected, rather than amputating the source.
        rows[0].vertex_group = ''
        expect_cancel(bpy.ops.gnm.mirror_reconstruct, 'both sides')
        assert ids == [row.result_object.as_pointer() for row in rows[:2]]
        rows[0].vertex_group = groups[0][0]
        # A preserved contralateral fragment takes precedence over inferred faces.
        patch = rows[0].result_object
        preserved = bpy.data.objects.new('Preserved opposite cranial fragment', patch.data.copy())
        scene.collection.objects.link(preserved)
        keep = scene.gnm_restoration_regions.add()
        keep.uid, keep.source_object, keep.action = uuid.uuid4().hex, preserved, 'KEEP'
        assert bpy.ops.gnm.mirror_reconstruct() == {'FINISHED'}
        assert len(rows[0].result_object.data.polygons) == 0
        assert len(rows[1].result_object.data.polygons) == 1
        assert [v.co[:] for v in source.data.vertices] == original_positions
        assert [tuple(p.vertices) for p in source.data.polygons] == original_faces
        assert source.matrix_world == original_matrix and not source.hide_get()
        marker = scene.gnm_markers[0]
        addon._record_marker_surface(marker, rows[1].result_object)
        assert marker.bone_status == 'reconstructed' and not marker.use_for_fit and not marker.use_for_plane
        scene.view_layers[0].objects.active = source
        shifted = [source, preserved, cranial_plane, mandibular_plane, rows[1].result_object]
        old_positions = {obj: obj.matrix_world.translation.copy() for obj in shifted}
        offset = -cranial_plane.matrix_world.translation.copy()
        assert bpy.ops.gnm.recenter_on_plane() == {'FINISHED'}
        for obj in shifted:
            assert (obj.matrix_world.translation - old_positions[obj] - offset).length < 1e-5
        assert [v.co[:] for v in source.data.vertices] == original_positions
        print('BLENDER_MIXED_FRAGMENTS_PRESERVED_PASS')


def run_lambda_checks(addon, scene, model):
    snapshot = addon._build_snapshot(scene)
    assert len(snapshot['labels']) == 48
    first, second = scene.gnm_markers[0], scene.gnm_markers[1]
    old = first.gnm_vertex_override
    first.gnm_vertex_override = addon._resolve_vertex(second)
    try:
        addon._build_snapshot(scene)
    except ValueError as exc:
        assert 'Duplicate GNM vertex' in str(exc)
    else:
        raise AssertionError('Preview accepted a duplicate manual correspondence')
    first.gnm_vertex_override = old
    assert addon._adaptive_lambda(12, 1, .3, 1000) == 4
    assert addon._adaptive_lambda(48, 1, .3, 1000) == 1
    assert addon._adaptive_lambda(0, 1, .3, 1000) == 1000
    previous_cfg, previous_model = dict(addon._LIVE.cfg), addon._LIVE.model
    previous_fit = addon._CRANIO.get('fit_identity')
    previous_loss = addon._CRANIO.get('LossConfig')
    calls = []
    def fake_fit(*args, **kwargs):
        calls.append(True)
        return None, None, None, None, 3.0, None, None
    try:
        addon._LIVE.model = model
        addon._LIVE.cfg['loo_auto'] = True
        addon._LIVE.loo_cache = {}
        addon._CRANIO.update(fit_identity=fake_fit, LossConfig=lambda: None)
        addon._live_lambda(48, snapshot)
        addon._live_lambda(48, snapshot)
        assert len(calls) == 1
        snapshot['targets'][0, 0] += 1
        addon._live_lambda(48, snapshot)
        assert len(calls) == 2
        snapshot['weights'][0] *= .5
        addon._live_lambda(48, snapshot)
        assert len(calls) == 3
    finally:
        addon._LIVE.cfg = previous_cfg
        addon._LIVE.model = previous_model
        addon._CRANIO['fit_identity'] = previous_fit
        addon._CRANIO['LossConfig'] = previous_loss
        addon._LIVE.loo_cache = {}
    print('BLENDER_DUPLICATE_AND_LAMBDA_PASS')
