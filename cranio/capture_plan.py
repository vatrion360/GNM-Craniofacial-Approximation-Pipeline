"""Verified saved-bundle camera planning, NumPy only; no inferred anatomical frame."""
import copy
from pathlib import Path

import numpy as np

from .record import _digest, canonical_bytes, validate_report
from .tissue import _json
from . import craniometry as cm, reference_frame as rf, review_export

VIEWS = ('front', '3quarter', 'profile')
INTERPRETATION = ('Orthographic documentation of the saved neutral fit using reviewed snapshot references. '
                  'Orientation and scale bars are not anatomical validation; current scene edits are excluded.')


def settings(resolution=1024, bar_mm=50., samples=16):
    """Rendering limits/defaults are engineering choices, never anatomical thresholds."""
    if type(resolution) is not int or not 128 <= resolution <= 4096:
        raise ValueError('Capture resolution must be an integer in [128, 4096]')
    if type(samples) is not int or not 1 <= samples <= 128:
        raise ValueError('CPU render samples must be an integer in [1, 128]')
    try:
        valid = type(bar_mm) in (int, float) and np.isfinite(bar_mm) and bar_mm > 0
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        raise ValueError('Scale-bar length must be finite and positive in mm')
    return dict(resolution=resolution, bar_mm=float(bar_mm), samples=samples)


def reviewed_frame(report):
    """Recompute frame geometry; require matching observed/reference provenance."""
    validate_report(report)
    document = report['marker_metadata'].get('craniometry')
    if not isinstance(document, dict):
        raise ValueError('Saved report has no craniometry/reference frame; recompute and export a reviewed frame')
    stored = document.get('reference_frame')
    if not isinstance(stored, dict) or stored.get('status') != 'current':
        raise ValueError('Saved reference frame is missing or stale; no automatic orientation fallback')
    config = stored.get('configuration')
    signature = rf.input_signature(document, config)
    if signature != stored.get('input_signature'):
        raise ValueError('Saved reference-frame signature does not match observations')
    points = {code: np.asarray(row['xyz_mm']) for code, row in cm.validate_document(document)[0].items()}
    frame = copy.deepcopy(stored)
    frame['geometry'] = rf.geometry_frame(points, config)
    return frame


def plan(vertices, frame, *, resolution=1024, bar_mm=50., samples=16):
    """Square orthographic views with common scale and camera-aligned metric bars.

    A sphere around the anatomical origin bounds all vertices in every view.
    Layout fractions reserve header/footer space outside that sphere. They are
    presentation constants, not scientific plausibility thresholds.
    """
    options = settings(resolution, bar_mm, samples)
    vertices = np.asarray(vertices, dtype=float)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices) or not np.isfinite(vertices).all():
        raise ValueError('Capture vertices must be a nonempty finite N by 3 array')
    origin = np.asarray(frame['geometry']['origin_mm'], dtype=float)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError('Invalid frame origin')
    radius = float(np.linalg.norm(vertices-origin, axis=1).max())
    if not np.isfinite(radius) or radius <= np.finfo(float).eps:
        raise ValueError('Degenerate capture extent')
    scale = 2.8*radius
    if not np.isfinite(scale) or bar_mm > .7*scale:
        raise ValueError('Scale bar does not fit the image; choose a shorter length')
    views = []
    for name in VIEWS:
        basis = rf.camera_basis(frame, name)
        back = basis[:, 2]
        bar_camera = np.array([[-.4*scale, -.42*scale, 1.5*radius], [-.4*scale+bar_mm, -.42*scale, 1.5*radius]])
        bar_world = origin+bar_camera@basis.T
        # Pixel convention: upper-left image boundary is (0, 0); pixel centres are +0.5.
        pixels = np.column_stack(((bar_camera[:, 0]/scale+.5)*resolution,
                                  (.5-bar_camera[:, 1]/scale)*resolution))
        views.append(dict(name=name, camera_to_world_rotation=basis.tolist(),
            camera_location_mm=(origin+back*3*radius).tolist(), look_at_mm=origin.tolist(),
            ortho_scale_mm=scale, clip_start_mm=radius*.001, clip_end_mm=6*radius,
            bar_endpoints_world_mm=bar_world.tolist(), bar_endpoints_pixels=pixels.tolist(),
            bar_length_pixels=float(bar_mm/scale*resolution),
            annotation_plane_offset_mm=1.5*radius))
    result = dict(schema_version=1, units='mm', projection='orthographic', pixel_aspect=[1, 1],
        pixel_convention='upper-left boundary; centres at half-integers', **options,
        frame=frame, bounding_radius_mm=radius, views=views, interpretation=INTERPRETATION)
    canonical_bytes(result)
    return result


def load_inputs(report_path, bundle_dir, **options):
    """Read only explicitly chosen inputs and the exporter's fixed artifact names."""
    report_path, bundle = Path(report_path).resolve(), Path(bundle_dir).resolve()
    report_raw = report_path.read_bytes()
    report = _json(report_raw.decode('utf-8-sig'))
    validate_report(report)
    marker = bundle/'export_decision.json'
    if not marker.resolve().is_relative_to(bundle):
        raise ValueError('Export decision escapes bundle')
    decision_raw = marker.read_bytes()
    decision = _json(decision_raw.decode('utf-8-sig'))
    if not isinstance(decision, dict) or decision.get('status') != 'completed':
        raise ValueError('Captures require a completed mesh export; blocked exports have no face')
    request = dict(report_path=str(report_path), report_sha256=_digest(report_raw), export_mode=decision.get('mode'))
    checked, _ = review_export.read_result(bundle, request)
    raw = (bundle/'face.obj').read_bytes()
    filtered = '\n'.join(line for line in raw.decode('utf-8-sig').splitlines()
                          if line.strip() not in ('mtllib face.mtl', 'usemtl GNM_Neutral_Gray'))
    lines, counts = review_export.geometry_lines(filtered.encode('utf-8'))
    vertices = np.array([[float(x) for x in line.split()[1:]] for line in lines if line.startswith('v ')])
    triangles = np.array([[int(x)-1 for x in line.split()[1:]] for line in lines if line.startswith('f ')])
    if counts != checked['geometry']:
        raise ValueError('Export geometry counts differ from manifest')
    frame = reviewed_frame(report)
    recipe = plan(vertices, frame, **options)
    pinned = {str(report_path): _digest(report_raw), str(marker): _digest(decision_raw)}
    for name, row in checked['files'].items():
        pinned[str(bundle/name)] = row['sha256']
    assert_unchanged(pinned)
    recipe.update(export_label=checked['label'], export_mode=checked['mode'],
        check_gate=checked['check_gate'], source_report_sha256=_digest(report_raw),
        source_export_decision_sha256=_digest(decision_raw), source_mesh_sha256=_digest(raw),
        source_bundle_files=checked['files'], geometry=counts, final_mesh_uncertainty='not_assessed')
    return vertices, triangles, recipe, pinned


def assert_unchanged(pinned):
    if any(_digest(Path(path).read_bytes()) != digest for path, digest in pinned.items()):
        raise ValueError('Capture source changed; no completion marker')
