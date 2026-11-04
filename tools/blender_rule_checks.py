"""Real Blender checks for rule inspection; synthetic indices are not anatomy."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import numpy as np


class Layout:
    """Capture labels and exercise the draw path without a visible window."""
    def __init__(self):
        self.labels = []

    def label(self, *, text, **kwargs): self.labels.append(text)
    def operator(self, *args, **kwargs): return SimpleNamespace()
    def prop(self, *args, **kwargs): pass
    def box(self): return self
    def separator(self): pass


def run_rule_checks(addon, directory):
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Rule panel checks')
    bpy.context.window.scene = scene
    module = addon._core_module('blender_rules')
    try:
        settings = scene.gnm_rule_checks
        assert not settings.catalogue_json and not settings.result_json
        assert bpy.ops.gnm.anatomical_rule_checks(action='REFRESH') == {'FINISHED'}
        rows = json.loads(settings.catalogue_json)['rules']
        assert len(rows) == 6 and sum(r['execution_status'] == 'not_configured' for r in rows) == 5
        assert rows[-1]['execution_status'] == 'unused'
        assert all(r['registry_status'] == 'needs_verification' for r in rows)
        scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
        vertices = np.arange(27, dtype=float).reshape(9, 3)
        vertices[7:] = [[0, 0, 0], [3, 4, 0]]
        triangles = np.arange(9).reshape(3, 3)
        model = Path(directory)/'rule-model.npz'
        np.savez(model, template_vertex_positions=vertices/1000, triangles=triangles)
        scene.gnm_live.npz_path = str(model)
        mesh = bpy.data.meshes.new('Rule synthetic mesh')
        mesh.from_pydata(vertices.tolist(), [], triangles.tolist())
        obj = bpy.data.objects.new('Rule synthetic face', mesh)
        scene.collection.objects.link(obj)
        obj.location = (10, 20, 30)
        bpy.context.view_layer.update()
        obj['gnm_fit_state'] = json.dumps(dict(model_sha256=module.sha256_file(model)))
        settings.source = obj
        settings.mapping_path = str(Path(directory)/'rule-map.json')
        settings.output_path = str(Path(directory)/'rule-snapshot.json')
        assert bpy.ops.gnm.anatomical_rule_checks(action='TEMPLATE') == {'FINISHED'}
        mapping_path = Path(settings.mapping_path)
        mapping = json.loads(mapping_path.read_text(encoding='utf-8'))
        assert all(p['vertex'] is None for p in mapping['points'].values())
        for i, name in enumerate(module.core.POINTS):
            point = mapping['points'][name]
            point.update(vertex=i, reviewed=True, definition='Synthetic point', source='Engineering test')
        for feature in mapping['features'].values():
            feature.update(reviewed=True, definition='Synthetic measurement', source='Engineering test')
        mapping['features']['mouth_width']['rule_id'] = 'mouth_stephan_evaluation'
        mapping_path.write_text(json.dumps(mapping), encoding='utf-8')
        before = (module._api._core_module('blender_postfit').coordinates(mesh.vertices).copy(),
                  np.array(obj.matrix_world), len(scene.gnm_markers), dict(obj.items()))
        assert bpy.ops.gnm.anatomical_rule_checks(action='MEASURE') == {'FINISHED'}
        saved = Path(settings.output_path).read_bytes()
        result = json.loads(saved)
        assert result == json.loads(settings.result_json)
        assert result['features']['mouth_width']['measurement']['value'] == 5
        assert result['features']['mouth_width']['comparison']['rule_status'] == 'not_configured'
        assert result['features']['pronasale_position']['measurement']['value'] == [28, 39, 50]
        assert result['snapshot']['world_matrix'] == np.array(obj.matrix_world).tolist()
        assert result['input_sha256']['mapping'] == module.sha256_file(mapping_path)
        direct = module.core.measure_and_compare(vertices+[10, 20, 30], triangles, triangles,
                                                module.sha256_file(model), mapping)
        assert direct['features'] == result['features']
        assert all(f['comparison']['light'] == 'not_assessed' for f in result['features'].values())
        layout = Layout()
        def forbidden(*args, **kwargs): raise AssertionError('Redraw attempted I/O or computation')
        with patch.object(module, 'load_registry', forbidden), patch.object(module, '_snapshot', forbidden), \
             patch.object(module, 'sha256_file', forbidden), patch.object(Path, 'read_text', forbidden):
            module.draw_cached(layout, settings)
        assert any('LAST SNAPSHOT' in line for line in layout.labels)
        assert any('not assessed' in line for line in layout.labels)
        assert not any('green' in line for line in layout.labels)
        assert any('10.1002/ajpa.10166' in line for line in layout.labels)

        def fails(message):
            try:
                status = bpy.ops.gnm.anatomical_rule_checks(action='MEASURE')
            except RuntimeError as exc:
                assert message in str(exc), str(exc)
            else:
                assert status == {'CANCELLED'}
            assert message in settings.status and not settings.result_json

        fails('Output exists')
        assert Path(settings.output_path).read_bytes() == saved
        settings.output_path = str(Path(directory)/'rule-second.json')
        scene.unit_settings.scale_length = 1
        fails('scene scale')
        scene.unit_settings.scale_length = .001
        obj['gnm_presentation'] = True
        fails('presentation copy')
        del obj['gnm_presentation']
        modifier = obj.modifiers.new('Rule test modifier', 'SUBSURF')
        fails('modifiers')
        obj.modifiers.remove(modifier)
        obj['gnm_fit_state'] = json.dumps(dict(model_sha256='0'*64))
        fails('metadata')
        obj['gnm_fit_state'] = before[3]['gnm_fit_state']
        malformed = dict(mapping, model_sha256='b'*64)
        mapping_path.write_text(json.dumps(malformed), encoding='utf-8')
        fails('model_sha256')
        mapping_path.write_text(json.dumps(mapping), encoding='utf-8')
        settings.output_path = settings.mapping_path
        fails('overwrite an input')
        assert json.loads(mapping_path.read_text(encoding='utf-8')) == mapping
        settings.output_path = str(Path(directory)/'rule-second.json')
        mapping['points']['cheilion_L']['reviewed'] = False
        mapping_path.write_text(json.dumps(mapping), encoding='utf-8')
        assert bpy.ops.gnm.anatomical_rule_checks(action='MEASURE') == {'FINISHED'}
        partial = json.loads(settings.result_json)
        assert partial['features']['mouth_width']['measurement'] is None
        assert partial['features']['pronasale_position']['measurement'] is not None
        settings.mapping_path = str(Path(directory)/'different-map.json')
        assert not settings.result_json
        assert bpy.ops.gnm.anatomical_rule_checks(action='REFRESH') == {'FINISHED'}
        assert not settings.result_json
        # Input geometry and fit/marker metadata are untouched by all operations.
        np.testing.assert_array_equal(module._api._core_module('blender_postfit').coordinates(mesh.vertices), before[0])
        np.testing.assert_array_equal(np.array(obj.matrix_world), before[1])
        assert len(scene.gnm_markers) == before[2] and dict(obj.items()) == before[3]
        print('BLENDER_RULE_PANEL_PASS: catalogue, snapshot parity, world mm, review gates, no redraw I/O, safe export')
    finally:
        bpy.context.window.scene = previous
        for obj in list(scene.objects):
            mesh = obj.data if obj.type == 'MESH' else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh and not mesh.users:
                bpy.data.meshes.remove(mesh)
        bpy.data.scenes.remove(scene)
