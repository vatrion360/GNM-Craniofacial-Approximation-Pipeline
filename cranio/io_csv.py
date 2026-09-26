"""Explicit v3 marker interchange in world millimetres; legacy v1/v2 readable."""
import csv
import json
from typing import NamedTuple

import numpy as np
from .landmarks import CONFIDENCE_WEIGHTS, DEFAULT_CONFIDENCE
from .validation import finite_array

V2_MAGIC = "# gnm-marker-csv v2"
V3_MAGIC = "# gnm-marker-csv v3"
V3_FIELDS = ["label", "vertex", "placed", "x", "y", "z", "weight",
             "bone_x", "bone_y", "bone_z", "tissue_depth_mm", "tissue_source",
             "use_for_fit", "bone_status", "mapping_reviewed", "mapping_source", "marker_notes"]


class MarkerTarget(NamedTuple):
    label: str
    vertex: int
    xyz: np.ndarray
    weight: float


def read_marker_csv(csv_path, index_to_label, label_to_vertex):
    with open(csv_path, encoding="utf-8-sig", newline="") as stream:
        lines = stream.read().splitlines()
    if not lines:
        raise ValueError("Marker CSV is empty")
    version = {V2_MAGIC: 2, V3_MAGIC: 3}.get(lines[0].strip(), 1)
    metadata = {"version": version}
    if version > 1:
        if len(lines) < 2 or not lines[1].lstrip().startswith("#"):
            raise ValueError("Versioned CSV requires a JSON metadata line")
        try:
            meta = json.loads(lines[1].lstrip()[1:].strip())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid marker metadata: {exc}") from exc
        if not isinstance(meta, dict):
            raise ValueError("Marker metadata must be a JSON object")
        metadata.update(meta)
        metadata["version"] = version
    if version == 3 and (metadata.get("units") != "mm" or
                         metadata.get("coordinate_space") != "world"):
        raise ValueError("v3 requires units='mm' and coordinate_space='world'")
    if metadata.get("units", "mm") != "mm":
        raise ValueError("Marker units must be mm; explicitly convert before fitting")
    reader = csv.DictReader(ln for ln in lines if not ln.lstrip().startswith("#"))
    required = {"label", "vertex", "placed", "x", "y", "z", "weight"} if version == 3 else {
        "gnm_landmark_index", "x", "y", "z"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError(f"CSV is missing required columns: {sorted(required)}")
    targets, skipped, seen_labels, seen_vertices = [], [], set(), set()
    bones, records = {}, {}
    for line_number, row in enumerate(reader, 1):
        try:
            use_for_fit = True
            if None in row:
                raise ValueError("extra columns")
            if version == 3:
                label = row["label"].strip()
                if not label:
                    raise ValueError("empty label")
                if label in seen_labels:
                    raise ValueError(f"duplicate label {label}")
                seen_labels.add(label)
                if row["placed"] not in ("0", "1"):
                    raise ValueError("placed must be 0 or 1")
                if row["placed"] == "0":
                    skipped.append((label, "not placed"))
                    continue
                vertex = int(row["vertex"])
                weight = float(row["weight"])
                enabled = row.get('use_for_fit') or '1'
                if enabled not in ('0', '1'):
                    raise ValueError('use_for_fit must be 0 or 1')
                use_for_fit = enabled == '1'
            else:
                enc = int(row["gnm_landmark_index"])
                label = index_to_label.get(enc)
                if label is None:
                    raise ValueError(f"unknown legacy index {enc}; export explicit v3 labels")
                if label in seen_labels:
                    raise ValueError(f"duplicate label {label}")
                seen_labels.add(label)
                vertex = label_to_vertex[label]
                weight = CONFIDENCE_WEIGHTS.get(label, DEFAULT_CONFIDENCE)
            xyz = finite_array([float(row[a]) for a in ("x", "y", "z")], label, (3,))
            if version < 3 and np.all(np.abs(xyz) < 1e-9):
                skipped.append((label, "legacy unplaced origin sentinel"))
                continue
            if vertex < 0 or (use_for_fit and vertex in seen_vertices):
                raise ValueError(f"negative or duplicate vertex {vertex}")
            if not np.isfinite(weight) or not 0 < weight <= 1:
                raise ValueError("weight must be finite and in (0, 1]")
            if version == 3:
                review = row.get('mapping_reviewed') or ''
                if review not in ('', '0', '1'):
                    raise ValueError('mapping_reviewed must be 0 or 1 when specified')
                bone_status = row.get('bone_status') or 'unspecified'
                if bone_status not in ('unspecified', 'observed', 'reconstructed', 'inferred'):
                    raise ValueError('invalid bone_status')
                record = {'use_for_fit': use_for_fit, 'bone_status': bone_status,
                          'mapping_reviewed': None if review == '' else review == '1',
                          'mapping_source': row.get('mapping_source') or 'unspecified',
                          'marker_notes': row.get('marker_notes') or '',
                          'vertex': vertex, 'target_xyz_mm': xyz.tolist()}
                values = [row.get("bone_" + axis, "") for axis in "xyz"]
                if any(v not in ("", None) for v in values):
                    bone = finite_array([float(v) for v in values], f"{label} bone", (3,))
                    bones[label] = bone.tolist()
                    record["bone_xyz_mm"] = bone.tolist()
                depth = row.get("tissue_depth_mm", "")
                if depth not in ("", None):
                    depth = float(depth)
                    if not np.isfinite(depth) or depth < 0:
                        raise ValueError("tissue_depth_mm must be finite and nonnegative")
                    record["tissue_depth_mm"] = depth
                    if label in bones and not np.isclose(np.linalg.norm(xyz - bones[label]), depth,
                                                         atol=0.05, rtol=0):
                        raise ValueError("bone-to-target distance differs from tissue_depth_mm")
                record["tissue_source"] = row.get("tissue_source", "") or "unspecified"
                records[label] = record
            if not use_for_fit:
                skipped.append((label, 'documentation only (use_for_fit=0)'))
                continue
            seen_vertices.add(vertex)
            targets.append(MarkerTarget(label, vertex, xyz, weight))
        except (TypeError, KeyError, ValueError) as exc:
            raise ValueError(f"CSV data row {line_number}: {exc}") from exc
    metadata["bone_positions_mm"] = bones
    metadata["marker_records"] = records
    if version < 3:
        metadata["legacy_assumptions"] = "world millimetres; origin means unplaced; no bone positions"
    return targets, skipped, metadata


def write_marker_csv_v3(csv_path, rows, metadata=None):
    meta = dict(metadata or {})
    meta.update(version=3, units="mm", coordinate_space="world")
    with open(csv_path, "w", newline="", encoding="utf-8") as stream:
        stream.write(V3_MAGIC + "\n# " + json.dumps(meta, sort_keys=True, ensure_ascii=False,
                                                   allow_nan=False) + "\n")
        writer = csv.DictWriter(stream, fieldnames=V3_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return meta


def write_marker_csv_v2(csv_path, rows, metadata=None):
    meta = {"version": 2, "units": "mm", **(metadata or {})}
    with open(csv_path, "w", newline="", encoding="utf-8") as stream:
        stream.write(V2_MAGIC + "\n# " + json.dumps(meta, ensure_ascii=False,
                                                  allow_nan=False) + "\n")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["gnm_landmark_index", "x", "y", "z"])
        writer.writerows(sorted(rows))
    return meta


def load_csv_targets(csv_path, index_to_label, label_to_vertex):
    targets, skipped, _ = read_marker_csv(csv_path, index_to_label, label_to_vertex)
    return targets, skipped
