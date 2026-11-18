"""On-demand landmark atlas. No scene objects, camera, fitting or file I/O in draw."""
import textwrap
import bpy
import bpy.utils.previews
import numpy as np
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, PointerProperty
from mathutils.bvhtree import BVHTree
from . import landmark_atlas as atlas
from .blender_sources import generated_surface

_previews = None
_last = None
SIZE = 176
PREFIX = 'ATLAS_REVIEWED:'
SOURCE = 'gnm_atlas_source'


def active_label(scene):
    i = scene.gnm_marker_active_index
    return scene.gnm_markers[i].label if 0 <= i < len(scene.gnm_markers) else None


def _reference(scene, label):
    obj = scene.gnm_atlas_skull
    if obj is None:
        raise ValueError('No reference skull selected; use the text card')
    if (obj.type != 'MESH' or obj.mode != 'OBJECT' or scene.objects.get(obj.name) is not None
            or generated_surface(obj) or obj.modifiers or obj.data.shape_keys):
        raise ValueError('Use a separate reference mesh outside this case scene, in Object Mode, without modifiers or shape keys')
    source = obj.get(SOURCE)
    if not isinstance(source, str) or not source.strip():
        raise ValueError('Document the reference skull and annotation source in its gnm_atlas_source property')
    group = obj.vertex_groups.get(PREFIX+label)
    if group is None:
        raise ValueError(f'No reviewed reference vertex for {label}; use the text card')
    sites = [v.index for v in obj.data.vertices if any(g.group == group.index and g.weight > 0 for g in v.groups)]
    if len(sites) != 1:
        raise ValueError('A reviewed site group must contain exactly one positively weighted vertex')
    return obj, sites[0], source.strip()


def render(scene, label, axis):
    """Raycast an annotation on the actual local mesh; do not mark a hidden site."""
    atlas.card(label)
    obj, vid, source = _reference(scene, label)
    mesh = obj.data
    points = np.empty((len(mesh.vertices), 3), dtype=np.float32)
    mesh.vertices.foreach_get('co', points.ravel())
    mesh.calc_loop_triangles()
    tri = np.empty((len(mesh.loop_triangles), 3), dtype=np.int32)
    mesh.loop_triangles.foreach_get('vertices', tri.ravel())
    if not len(tri) or not np.any(tri == vid):
        raise ValueError('Reference vertex must belong to the triangulated bone surface')
    # Normalize the native mesh uniformly for display and BVH precision. No case alignment.
    points = points.astype(float)
    points -= points.min(axis=0)
    scale = float(points.max())
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError('Invalid reference skull extent')
    points /= scale
    view = atlas.make_view(points, axis, SIZE)
    tree = BVHTree.FromPolygons(points.tolist(), tri.tolist(), all_triangles=True)
    direction = tuple(-view.toward)
    rgba = np.full((SIZE, SIZE, 4), .055, np.float32)
    rgba[:,:,3] = 1.
    row_offsets = (np.arange(SIZE)*view.span/SIZE)[:, None]*view.right
    depth_axis = int(np.argmax(np.abs(view.toward)))
    for y in range(SIZE):
        start = view.ray_origin(0, y)
        for x, origin in enumerate((start + row_offsets).tolist()):
            _, normal, index, _ = tree.ray_cast(origin, direction)
            if index is not None:
                # Display shading only, independent of consistent winding.
                shade = .22+.54*abs(normal[depth_axis])
                rgba[y,x,:3] = shade
    p = points[vid]
    # Cast from the annotation toward the viewer. A small float32 offset avoids
    # hitting incident faces at the origin; this is a rendering tolerance only.
    eps = 32*np.finfo(np.float32).eps
    _, _, blocker, _ = tree.ray_cast(tuple(p + eps*view.toward), tuple(view.toward))
    xy = view.project(p)
    visible = blocker is None
    if visible:
        y,x = np.ogrid[:SIZE,:SIZE]
        d = (x-xy[0])**2+(y-xy[1])**2
        rgba[(d>=9)&(d<=49),:3] = .01
        rgba[(d>=16)&(d<=36),:3] = (1., .64, .04)
    return rgba, dict(label=label, vertex=vid, source=source, axis=axis, visible=visible)


def _key(scene):
    obj = scene.gnm_atlas_skull
    return (scene.as_pointer(), active_label(scene), obj.as_pointer() if obj else 0, scene.gnm_atlas_view)


@persistent
def clear(_=None, *args):
    global _last
    _last = None
    if _previews is not None:
        _previews.clear()


class GNM_OT_atlas_refresh(bpy.types.Operator):
    bl_idname = 'gnm.atlas_refresh'
    bl_label = 'Refresh Reference View'

    def execute(self, context):
        global _last
        clear()
        scene = context.scene
        try:
            pixels, record = render(scene, active_label(scene), scene.gnm_atlas_view)
            preview = _previews.new('reference')
            preview.image_size = SIZE, SIZE
            preview.image_pixels_float = pixels.ravel()
            _last = (_key(scene), record)
        except (TypeError, ValueError, RuntimeError) as exc:
            clear()
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def draw(layout, scene):
    layout.prop(scene, 'gnm_show_atlas', text='Placement atlas for selected marker', toggle=True)
    label = active_label(scene)
    if not scene.gnm_show_atlas or label is None:
        return
    box = layout.box()
    if label not in atlas.LANDMARK_INFO:
        box.label(text='No atlas entry for this label')
        return
    entry = atlas.card(label)
    box.label(text=f"{label} ({entry['side']})")
    def lines(value):
        for line in textwrap.wrap(value, width=43):
            box.label(text=line)
    lines('Definition: '+(entry['definition'] or 'No sourced definition configured.'))
    if entry['definition_source']:
        lines(entry['definition_source'])
    if entry['placement_hint']:
        lines('Project placement note: '+entry['placement_hint'])
    lines('Placement caveat: '+(entry['caution'] or 'No separate site-specific caveat documented.'))
    lines('Definition needs expert review. Reference viewing does not review the case marker.')
    box.prop(scene, 'gnm_atlas_skull')
    if scene.gnm_atlas_skull:
        box.prop(scene, 'gnm_atlas_view')
        box.operator('gnm.atlas_refresh')
        if _last and _last[0] == _key(scene):
            result = _last[1]
            box.template_icon(icon_value=_previews['reference'].icon_id, scale=8)
            lines('Last snapshot: '+('ring at annotated vertex' if result['visible'] else 'site occluded; try another view'))
            lines(f"Reference vertex {result['vertex']}; local {result['axis']} view. Source: {result['source']}")
    else:
        lines('Text only. A reviewed reference skull is optional.')


def register():
    global _previews
    bpy.utils.register_class(GNM_OT_atlas_refresh)
    _previews = bpy.utils.previews.new()
    bpy.types.Scene.gnm_show_atlas = BoolProperty(default=False)
    bpy.types.Scene.gnm_atlas_skull = PointerProperty(type=bpy.types.Object, name='Reference skull',
        poll=lambda self, obj: obj.type == 'MESH' and self.objects.get(obj.name) is None and not generated_surface(obj))
    bpy.types.Scene.gnm_atlas_view = EnumProperty(name='View from (local axis)',
        items=[(v,v,'Reference mesh local axis, not anatomical orientation') for v in atlas.VIEWS], default='+Y')
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        handlers.append(clear)


def unregister():
    global _previews
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if clear in handlers:
            handlers.remove(clear)
    clear()
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
    for name in ('gnm_atlas_view','gnm_atlas_skull','gnm_show_atlas'):
        delattr(bpy.types.Scene, name)
    bpy.utils.unregister_class(GNM_OT_atlas_refresh)
