"""Main-thread Blender adapter for marker orientation (no fitting or mesh edits)."""
import datetime
import json
import numpy as np
from mathutils import Matrix, Vector
from .blender_sources import evaluated_geometry, generated_surface
from .surface_normals import estimate_normal


def normal_frame(normal):
    """Orthonormal frame with exact +Z direction, including near-axis normals.

    Cross products avoid the near-parallel loss of precision in to_track_quat.
    """
    n = np.asarray(normal, dtype=float)
    n = n/np.linalg.norm(n)
    axis = np.eye(3)[np.argmin(np.abs(n))]
    x = np.cross(axis, n)
    x /= np.linalg.norm(x)
    y = np.cross(n, x)
    return Matrix(np.column_stack((x, y, n)).tolist())


def calculate(scene, obj, point, depsgraph, *, seed_polygon=None, previous=None):
    """Read one registered surface and return a fresh, auditable normal estimate."""
    source = next((row for row in scene.gnm_bone_sources
                   if row.enabled and row.source_object == obj), None)
    inferred = any(row.enabled and row.result_object == obj and obj.get('gnm_region_patch') == row.uid
                   and obj.get('gnm_reconstructed_via_mirroring') for row in scene.gnm_restoration_regions)
    if source is None and not inferred:
        raise ValueError('Choose a registered observed source or an enabled inferred patch')
    if source and generated_surface(obj):
        raise ValueError('A generated surface cannot supply observed bone normals')
    vertices, triangles, digest, _, polygons = evaluated_geometry(
        obj, depsgraph, source.flip_normals if source else False)
    seed_faces = None
    if previous is not None:
        placed_hash = previous.get('gnm_source_sha256_at_placement', '')
        if placed_hash and placed_hash != digest:
            raise ValueError('Source changed since placement; review and re-place this marker first')
        raw = previous.get('gnm_normal_record', '')
        if raw:
            record = json.loads(raw)
            if (record.get('source_geometry_sha256') == digest
                    and np.linalg.norm(np.asarray(record['point_mm'])-point) < 1e-5):
                seed_faces = [record['seed_triangle']]
    if seed_polygon is not None and seed_polygon >= 0:
        seed_faces = np.flatnonzero(polygons == seed_polygon)
    result = estimate_normal(vertices, triangles, np.asarray(point), scene.gnm_settings.normal_radius_mm,
                             mode=scene.gnm_settings.normal_mode, seed_faces=seed_faces)
    result.update(source_geometry_sha256=digest, source_name=obj.name,
                  source_id=source.uid if source else str(obj.get('gnm_region_patch', 'inferred')),
                  bone_provenance='observed' if source else 'inferred',
                  explicit_normal_flip=bool(source.flip_normals) if source else False,
                  exterior_normals_reviewed=bool(source.normals_reviewed) if source else False)
    if source is None:
        result['warnings'].append('Inferred bone: this is not observed surface evidence')
    elif not source.normals_reviewed:
        result['warnings'].append('Exterior normal sign is not reviewed; inspect source normals')
    return result


def marker_source(scene, item):
    """Resolve the marker's recorded source; never choose a nearby other fragment."""
    uid = item.bone_empty.get('gnm_bone_source_id', '')
    for row in scene.gnm_bone_sources:
        if row.enabled and row.uid == uid and row.source_object in list(scene.objects):
            return row.source_object
    for row in scene.gnm_restoration_regions:
        if row.enabled and row.uid == uid and row.result_object in list(scene.objects):
            return row.result_object
    raise ValueError('Marker source is missing or disabled; register the source and re-place the marker')


def set_direction(item, normal, thickness_mm):
    """Preserve the bone point and depth, set the target and unit-cylinder peg in world mm."""
    direction = Vector(normal)
    if not np.isfinite(direction).all() or direction.length < 1e-12:
        raise ValueError('Invalid marker direction')
    if not np.isfinite(item.tissue_depth_mm) or item.tissue_depth_mm < 0:
        raise ValueError('Invalid tissue depth')
    for obj in (item.target_empty, item.peg_object):
        if obj and (obj.parent or obj.constraints or obj.animation_data):
            raise ValueError('Detach marker target/peg parents, constraints or animation before reorienting')
    direction.normalize()
    bone = item.bone_empty.matrix_world.translation.copy()
    target = item.target_empty.matrix_world.copy()
    target.translation = bone+direction*item.tissue_depth_mm
    item.target_empty.matrix_world = target
    if item.peg_object:
        item.peg_object.rotation_mode = 'QUATERNION'
        rotation = normal_frame(direction).to_4x4()
        scale = Matrix.Diagonal((thickness_mm, thickness_mm, item.tissue_depth_mm, 1.))
        item.peg_object.matrix_world = Matrix.Translation(bone+direction*item.tissue_depth_mm/2) @ rotation @ scale
    item.bone_empty['gnm_normal'] = list(direction)


def record_application(item, record):
    """Store the applied estimate, not merely the most recent preview."""
    record = dict(record, applied_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  tissue_depth_mm_at_application=float(item.tissue_depth_mm))
    item.bone_empty['gnm_normal_record'] = json.dumps(record, allow_nan=False)


def export_record(item):
    """Distinguish a still-applied estimate from subsequent manual marker edits."""
    raw = item.bone_empty.get('gnm_normal_record', '') if item.bone_empty else ''
    if not raw or not item.is_placed:
        return {'method': 'legacy_or_manual_unrecorded'}
    record = json.loads(raw)
    point = np.array(item.bone_empty.matrix_world.translation)
    direction = np.array(item.target_empty.matrix_world.translation)-point
    depth = np.linalg.norm(direction)
    actual = direction/depth if depth > 1e-9 else np.array(item.bone_empty.get('gnm_normal', (0, 0, 0)))
    return dict(applied_estimate=record, current_direction=actual.tolist(),
                matches_current_marker=bool(np.linalg.norm(point-record['point_mm']) < 1e-5
                    and np.linalg.norm(actual-record['normal']) < 1e-5))


def clear_preview(scene=None):
    """Remove disposable helpers, including on file load or addon disable."""
    import bpy
    for obj in list(scene.objects if scene else bpy.data.objects):
        if obj.get('gnm_marker_normal_preview'):
            bpy.data.objects.remove(obj, do_unlink=True)


def show_preview(scene, item, record):
    """A snapshot arrow (+Z) and tangent circle; neither changes the marker."""
    import bpy
    clear_preview(scene)
    rotation = normal_frame(record['normal']).to_quaternion()
    for kind, size in (('SINGLE_ARROW', max(item.tissue_depth_mm, 3.)), ('CIRCLE', record['radius_mm'])):
        obj = bpy.data.objects.new('GNM_Normal_Preview', None)
        obj.empty_display_type, obj.empty_display_size = kind, size
        obj.location = item.bone_empty.matrix_world.translation
        obj.rotation_mode, obj.rotation_quaternion = 'QUATERNION', rotation
        obj.show_in_front, obj.hide_render = True, True
        obj.color = (1., .7, .05, 1.)
        obj['gnm_generated'], obj['gnm_marker_normal_preview'] = True, True
        obj['gnm_preview_record'] = json.dumps(record, allow_nan=False)
        obj.hide_select = True
        scene.collection.objects.link(obj)


def status(record):
    label = 'Local plane' if record['mode'] == 'LOCAL_PLANE' else 'Face normal'
    result = f"{label}: {record['patch_faces']} faces; change {record['angle_to_face_deg']:.1f} deg"
    if record['warnings']:
        result += '. ' + '; '.join(record['warnings'])
    return result
