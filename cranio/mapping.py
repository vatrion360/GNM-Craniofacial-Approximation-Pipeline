"""Reviewed anatomical-to-skin maps tied to an exact model checksum."""
import json
from .landmarks import LANDMARK_INFO


def reviewed_vertices(document, model_sha256, vertex_count):
    if not isinstance(document, dict):
        raise ValueError('Landmark map must be a JSON object')
    if 'schema_version' not in document:
        if any(isinstance(v, dict) and v.get('source') == 'manual_picked_blender' for v in document.values()):
            raise ValueError('Legacy manual map has no model hash; re-export picks from the original Blender scene')
        return {}
    if document.get('schema_version') != 1 or document.get('model_sha256') != model_sha256:
        raise ValueError('Reviewed map schema/model SHA-256 mismatch')
    entries = document.get('landmarks')
    if not isinstance(entries, dict):
        raise ValueError('Reviewed map requires a landmarks object')
    result = {}
    for label, entry in entries.items():
        if label not in LANDMARK_INFO or not isinstance(entry, dict):
            raise ValueError(f'Unknown or malformed landmark: {label}')
        vertex = entry.get('vertex_index')
        if type(vertex) is not int or not 0 <= vertex < vertex_count:
            raise ValueError(f'Invalid reviewed vertex: {label}')
        if entry.get('reviewed') is True:
            result[label] = vertex
    if len(result) != len(set(result.values())):
        raise ValueError('Reviewed map contains duplicate vertices')
    return result


def read_reviewed_map(path, model_sha256, vertex_count):
    with open(path, encoding='utf-8') as stream:
        return reviewed_vertices(json.load(stream), model_sha256, vertex_count)
