"""Case-specific bone chords and explicitly reviewed skin-distance controls.

GNM is a skin model. Bone lengths are never used as skin lengths. This module
has no Blender/SciPy dependency; both preview and offline use this contract.
See docs/CRANIOMETRY.md for anatomical conventions and evidential limits.
"""
from dataclasses import dataclass
from typing import Mapping
import json
import numpy as np
from .validation import finite_array

PROTOCOL = 'table3-chords-v1'
REFERENCE = 'https://doi.org/10.4995/var.2024.24796 (Table 3; definitions attributed to White et al. 2012)'

# Hints are localization aids, not a substitute for the operator's osteometric protocol.
POINTS = {
    'n': ('Nasion', 'Midline nasofrontal suture.'),
    'g': ('Glabella', 'Most projecting midline point above the nasal root.'),
    'ba': ('Basion', 'Anterior foramen magnum border, in the midline; no skin correspondence.'),
    'b': ('Bregma', 'Coronal/sagittal suture intersection at bone-surface level; not vertex.'),
    'l': ('Lambda', 'Sagittal/lambdoid suture intersection at bone-surface level.'),
    'o': ('Opisthion', 'Posterior foramen magnum border, in the midline; not opisthocranion.'),
    'op': ('Opisthocranion', 'Midline vault point maximizing g-op; localize on preserved anatomy.'),
    'ns': ('Nasospinale', 'Midline inferior nasal-aperture reference; record construction. Not acanthion. '
           'This endpoint chord is not the bilateral-average nasal-height protocol.'),
}
for _code, _name, _hint in (
    ('ec', 'Ectoconchion', 'Lateral orbital-rim reference for orbital breadth; review the orbital protocol, not a canthus.'),
    ('d', 'Dacryon', 'Frontal/lacrimal/maxillary junction at the medial orbit; not a canthus.'),
    ('eu', 'Eurion', 'Point of maximum cranial breadth; paired extrema require preserved vault and operator review.'),
    ('zy', 'Zygion', 'Most lateral point of the zygomatic arch.'),
    ('al', 'Alare (bone)', 'Lateral external nasal-aperture margin at maximum breadth; not nasal wing.'),
    ('fmt', 'Frontomalare temporale', 'External point of the frontomalar suture; Table 3 uses alias ftm.'),
    ('ft', 'Frontotemporale', 'Frontal temporal-line point defining the minimum frontal breadth.'),
):
    for _side in ('R', 'L'):
        POINTS[f'{_code}_{_side}'] = (_name + (' right' if _side == 'R' else ' left'), _hint)


@dataclass(frozen=True)
class Measurement:
    key: str
    name: str
    a: str
    b: str
    skin_control_allowed: bool = True


MEASUREMENTS = (
    Measurement('ec-ec', 'Biorbital breadth', 'ec_R', 'ec_L'),
    Measurement('d-d', 'Interorbital breadth', 'd_R', 'd_L'),
    Measurement('ba-n', 'Cranial base length', 'ba', 'n', False),
    Measurement('g-op', 'Maximum cranial length', 'g', 'op'),
    Measurement('eu-eu', 'Maximum cranial breadth', 'eu_R', 'eu_L'),
    Measurement('zy-zy', 'Bizygomatic breadth', 'zy_R', 'zy_L'),
    Measurement('ba-b', 'Basion-bregma height', 'ba', 'b', False),
    Measurement('al-al', 'Nasal aperture breadth', 'al_R', 'al_L'),
    Measurement('n-ns', 'Nasal aperture height (endpoint chord)', 'n', 'ns'),
    Measurement('fmt-fmt', 'Upper facial breadth (Table 3: ftm-ftm)', 'fmt_R', 'fmt_L'),
    Measurement('ft-ft', 'Minimum frontal breadth', 'ft_R', 'ft_L'),
    Measurement('n-b', 'Frontal chord', 'n', 'b'),
    Measurement('b-l', 'Parietal chord', 'b', 'l'),
    Measurement('l-o', 'Occipital chord', 'l', 'o', False),
)
BY_KEY = {row.key: row for row in MEASUREMENTS}
ALIASES = {'ftm-ftm': 'fmt-fmt', 'ftm_R': 'fmt_R', 'ftm_L': 'fmt_L'}


def empty_document(case_id=''):
    """No specimen values or inferred points are supplied as defaults."""
    return dict(schema_version=1, protocol=PROTOCOL, units='mm', coordinate_space='world',
                case_id=case_id, reference=REFERENCE, points=[], bindings=[], bone_sources=[])


def _bool(value, name):
    if not isinstance(value, bool):
        raise ValueError(f'{name} must be a JSON boolean')
    return value


def _text(value, name):
    if not isinstance(value, str):
        raise ValueError(f'{name} must be text')
    return value


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_document(document):
    """Return canonical point/binding dictionaries; reject ambiguity and nonfinite data."""
    if not isinstance(document, dict) or type(document.get('schema_version')) is not int or document.get('schema_version') != 1:
        raise ValueError('Unsupported craniometry schema')
    if (document.get('protocol') != PROTOCOL or document.get('units') != 'mm'
            or document.get('coordinate_space') != 'world'):
        raise ValueError('Craniometry requires table3-chords-v1 in world mm')
    points, bindings = {}, {}
    for kind, registry, output, key in (('points', POINTS, points, 'code'), ('bindings', BY_KEY, bindings, 'measurement')):
        rows = document.get(kind, [])
        if not isinstance(rows, list):
            raise ValueError(f'Craniometry {kind} must be a list')
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f'Invalid craniometry {kind} row')
            name = _text(row.get(key), key)
            name = ALIASES.get(name, name)
            if name not in registry or name in output:
                raise ValueError(f'Unknown or duplicate craniometry {key}: {name}')
            output[name] = dict(row, **{key: name})
    for code, point in points.items():
        if point.get('status') not in ('missing', 'observed', 'reconstructed', 'unspecified'):
            raise ValueError(f'{code}: invalid bone status')
        xyz = point.get('xyz_mm')
        if (xyz is None) != (point['status'] == 'missing'):
            raise ValueError(f'{code}: missing status and coordinates disagree')
        if xyz is not None:
            try:
                point['xyz_mm'] = finite_array(xyz, code, (3,)).tolist()
            except TypeError as exc:
                raise ValueError(f'{code}: coordinates must be three finite numbers') from exc
        for name in ('source_id', 'source_geometry_sha256', 'notes'):
            _text(point.get(name, ''), f'{code} {name}')
        digest = point.get('source_geometry_sha256', '')
        if digest and not _sha(digest):
            raise ValueError(f'{code}: invalid source geometry SHA-256')
        _bool(point.get('definition_reviewed', False), f'{code} definition_reviewed')
    for key, binding in bindings.items():
        _bool(binding.get('enabled', False), f'{key} enabled')
        _bool(binding.get('mapping_reviewed', False), f'{key} mapping_reviewed')
        if not binding.get('enabled', False):
            continue
        if not BY_KEY[key].skin_control_allowed:
            raise ValueError(f'{key}: skull-base measurements have no supported skin correspondence')
        if binding.get('target_mode') not in ('skin_markers', 'reviewed_prediction'):
            raise ValueError(f'{key}: invalid skin target mode')
        for name in ('sigma_mm', 'influence'):
            value = binding.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
                raise ValueError(f'{key}: {name} must be finite and positive')
        if binding['target_mode'] == 'reviewed_prediction':
            value = binding.get('target_mm')
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
                raise ValueError(f'{key}: reviewed skin target must be finite and positive')
        for name in ('marker_a', 'marker_b', 'method'):
            if not _text(binding.get(name, ''), name).strip():
                raise ValueError(f'{key}: document {name}')
    return points, bindings


def control_protocol(document):
    """Freeze control choices/tolerances/methods, excluding case-specific observations."""
    _, bindings = validate_document(document)
    fields = ('measurement', 'marker_a', 'marker_b', 'target_mode', 'sigma_mm', 'influence', 'method')
    return dict(protocol=PROTOCOL, bindings=[{name: row[name] for name in fields}
        for key, row in sorted(bindings.items()) if row.get('enabled', False)])


def measure(document):
    """Compute all 14 Euclidean chords. Missing endpoints never become estimates.

    'observed' describes bone preservation, not anatomical correctness. Review,
    source-current and degenerate flags remain separate from preservation.
    """
    points, _ = validate_document(document)
    sources = document.get('bone_sources', [])
    if not isinstance(sources, list) or any(not isinstance(s, dict) for s in sources):
        raise ValueError('Craniometry bone_sources must be a list of objects')
    source_map = {}
    for source in sources:
        sid = _text(source.get('id'), 'bone source ID')
        if not sid or sid in source_map or not _sha(source.get('geometry_sha256')):
            raise ValueError('Duplicate/invalid craniometry bone source')
        source_map[sid] = source['geometry_sha256']
    rows = []
    for spec in MEASUREMENTS:
        endpoints = [points.get(code, {'status': 'missing'}) for code in (spec.a, spec.b)]
        statuses = [p['status'] for p in endpoints]
        missing = [code for code, p in zip((spec.a, spec.b), endpoints) if p.get('xyz_mm') is None]
        status = ('missing' if missing else 'reconstructed' if 'reconstructed' in statuses
                  else 'unspecified' if 'unspecified' in statuses else 'observed')
        value = None if missing else float(np.linalg.norm(np.asarray(endpoints[0]['xyz_mm'])-endpoints[1]['xyz_mm']))
        if value is not None and not np.isfinite(value):
            raise ValueError(f'{spec.key}: bone distance overflow; review units/coordinates')
        current = all(_sha(p.get('source_geometry_sha256')) and
                      source_map.get(p.get('source_id')) == p.get('source_geometry_sha256') for p in endpoints)
        reviewed = all(p.get('definition_reviewed') is True for p in endpoints)
        rows.append(dict(measurement=spec.key, name=spec.name, endpoints=[spec.a, spec.b],
                         bone_mm=value, status=status, missing=missing, definition_reviewed=reviewed,
                         sources_current=current, degenerate=value is not None and value < 1e-6))
    return rows


def skin_marker_issues(record: Mapping[str, object]) -> list[str]:
    """Describe missing endpoint metadata without reading geometry or changing review.

    Shared by the Blender panel and the live/offline control resolver. An empty
    result only checks these three fields; source hashes, anchoring and bone
    reference review are still validated by ``resolve_controls``.
    """
    issues = []
    status = record.get('bone_status', 'unspecified')
    if status != 'observed':
        issues.append(f"Bone provenance = {status!r}; requires observed bone")
    if record.get('mapping_reviewed') is not True:
        issues.append('Skin correspondence reviewed is not confirmed')
    source = record.get('tissue_source', '')
    if (not isinstance(source, str) or
            source.strip().lower() in ('', 'unspecified', 'legacy-unvalidated')):
        issues.append(f"Tissue source / method = {source!r}; document the tissue-depth source or method")
    return issues


def resolve_controls(document, labels, vertices, skin_targets, records, bone_positions, model_sha256):
    """Validate opt-in controls against the *included* marker snapshot.

    Every endpoint needs preserved, reviewed bone, a current source hash and an
    included reviewed skin marker anchored at that point (within 0.1 mm). An
    excluded marker disables its dependent pair, including after outlier removal.
    """
    points, bindings = validate_document(document)
    measurements = {row['measurement']: row for row in measure(document)}
    if not _sha(model_sha256) or document.get('model_sha256') != model_sha256:
        raise ValueError('Craniometry model SHA-256 is missing or mismatched')
    lookup = {label: (int(vertex), np.asarray(xyz)) for label, vertex, xyz in zip(labels, vertices, skin_targets)}
    controls, skipped, pairs = [], [], set()
    for key, binding in bindings.items():
        if not binding.get('enabled', False):
            continue
        a, b = binding['marker_a'], binding['marker_b']
        if a not in lookup or b not in lookup:
            skipped.append(dict(measurement=key, reason='skin endpoint not included in fit'))
            continue
        measurement, spec = measurements[key], BY_KEY[key]
        if (measurement['status'] != 'observed' or not measurement['definition_reviewed']
                or not measurement['sources_current'] or measurement['degenerate']):
            raise ValueError(f'{key}: requires reviewed, current, distinct observed bone endpoints')
        if binding.get('mapping_reviewed') is not True:
            raise ValueError(f'{key}: review the bone-to-skin correspondence')
        endpoint_issues = []
        for label in (a, b):
            issues = skin_marker_issues(records.get(label, {}))
            if issues:
                endpoint_issues.append(f"{label}: {'; '.join(issues)}")
        if endpoint_issues:
            raise ValueError(f"{key}: " + ' | '.join(endpoint_issues))
        for label, code in ((a, spec.a), (b, spec.b)):
            rec, point = records.get(label, {}), points[code]
            if (rec.get('bone_source_id') != point.get('source_id') or
                    rec.get('bone_source_geometry_sha256') != point.get('source_geometry_sha256')):
                raise ValueError(f'{key}: {label} and bone reference must share a current source')
            if label not in bone_positions or np.linalg.norm(finite_array(bone_positions[label], label, (3,))-point['xyz_mm']) > .1:
                raise ValueError(f'{key}: {label} is not anchored at {code} (0.1 mm tolerance)')
        va, ta = lookup[a]
        vb, tb = lookup[b]
        pair = tuple(sorted((va, vb)))
        if va == vb or pair in pairs:
            raise ValueError(f'{key}: duplicate skin vertex pair')
        pairs.add(pair)
        target = (float(np.linalg.norm(ta-tb)) if binding['target_mode'] == 'skin_markers'
                  else float(binding['target_mm']))
        if not np.isfinite(target) or target <= 1e-6:
            raise ValueError(f'{key}: degenerate skin distance')
        controls.append(dict(measurement=key, vertices=[va, vb], target_mm=target,
            sigma_mm=float(binding['sigma_mm']), influence=float(binding['influence']),
            target_mode=binding['target_mode'], method=binding['method'], bone_mm=measurement['bone_mm']))
    return controls, skipped


def control_residuals(controls, vertices_world):
    """Skin distance residuals in world mm; these are not cranial measurements."""
    rows = []
    for control in controls:
        a, b = control['vertices']
        distance = float(np.linalg.norm(vertices_world[a]-vertices_world[b]))
        rows.append(dict(control, fitted_skin_mm=distance, residual_mm=distance-control['target_mm']))
    return rows


def load_document(path):
    with open(path, encoding='utf-8') as stream:
        document = json.load(stream)
    measure(document)
    return document
