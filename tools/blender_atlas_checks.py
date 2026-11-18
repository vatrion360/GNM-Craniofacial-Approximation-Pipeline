"""Exercise read-only atlas presentation in the installed Blender add-on."""
import bpy
import numpy as np


def run_atlas_checks(addon):
    api = addon._core_module('blender_atlas')
    scene = bpy.context.scene
    # Separate case and reference scene, no GNM asset needed.
    case = bpy.data.scenes.new('Synthetic atlas case')
    reference = bpy.data.scenes.new('Synthetic atlas source')
    bpy.context.window.scene = case
    mesh = bpy.data.meshes.new('Atlas fixture mesh')
    mesh.from_pydata([(-2,-2,0),(2,-2,0),(0,2,0),(0,0,1)], [], [(0,2,1),(0,1,3),(1,2,3),(2,0,3)])
    mesh.update()
    obj = bpy.data.objects.new('Synthetic reference only', mesh)
    reference.collection.objects.link(obj)
    try:
        row = case.gnm_markers.add()
        row.label = 'Nasion'
        original = (row.is_placed, row.use_for_fit, row.mapping_reviewed, row.tissue_depth_mm)
        assert not case.gnm_show_atlas and case.gnm_atlas_skull is None
        assert api.active_label(case) == 'Nasion'
        assert bpy.ops.gnm.atlas_refresh() == {'CANCELLED'} and api._last is None
        case.gnm_show_atlas = True
        case.gnm_atlas_skull = obj
        obj[api.SOURCE] = 'Synthetic software fixture; no anatomical mapping'
        assert bpy.ops.gnm.atlas_refresh() == {'CANCELLED'}
        group = obj.vertex_groups.new(name=api.PREFIX+'Nasion')
        group.add([3],1.,'REPLACE')
        case.gnm_atlas_view = '+Z'
        assert bpy.ops.gnm.atlas_refresh() == {'FINISHED'}
        key, record = api._last
        assert record['visible'] and record['vertex'] == 3 and key == api._key(case)
        preview = api._previews['reference']
        pixels = np.array(preview.image_pixels_float).reshape(api.SIZE,api.SIZE,4)
        assert pixels[:,:,0].max() > .95 and len(np.unique(pixels[:,:,0])) >= 4
        case.gnm_atlas_view = '-Z'
        assert api._key(case) != key
        assert bpy.ops.gnm.atlas_refresh() == {'FINISHED'}
        assert not api._last[1]['visible']
        group.add([0],1.,'REPLACE')
        assert bpy.ops.gnm.atlas_refresh() == {'CANCELLED'} and api._last is None
        group.remove([0])
        case.collection.objects.link(obj)
        assert bpy.ops.gnm.atlas_refresh() == {'CANCELLED'}
        case.collection.objects.unlink(obj)
        assert len(case.objects)==0 and len(case.gnm_bone_sources)==0
        assert original == (row.is_placed, row.use_for_fit, row.mapping_reviewed, row.tissue_depth_mm)
        print('BLENDER_PLACEMENT_ATLAS_PASS: text fallback, reviewed vertex, visible/occluded views, unchanged case')
    finally:
        api.clear()
        bpy.context.window.scene = scene
        bpy.data.scenes.remove(case)
        bpy.data.scenes.remove(reference)
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)
