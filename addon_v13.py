"""GNM Craniofacial Markers 16.0 / software package 5.0.0rc3.

Install the complete ZIP built with tools/build_addon.py. The bundled numerical
core is imported under the add-on namespace. Optional previews run serially in
Blender's main thread and may pause the UI; final fitting uses a separate Python
process polled by a timer. No background Python thread calls Blender APIs.

Built-in depths, weights and skin-vertex correspondences are inherited research
heuristics, not a validated anatomical standard. Review tissue sources, target
directions and landmark definitions before casework. Export v3 preserves bone
positions, skin targets, manual vertex overrides and model provenance.
"""

import csv
import os
import datetime
# V13: module standard suplimentare pentru workflow-ul live.
import json
import shutil
import sys
import threading
import time
import textwrap
import bpy
import bmesh
import numpy as np  # livrat cu Blender (fitul live e numpy-pur, fara scipy)
from mathutils import Matrix, Vector, kdtree
from bpy.props import (
    StringProperty, FloatProperty, IntProperty, PointerProperty,
    CollectionProperty, EnumProperty, BoolProperty,
)
from bpy.types import PropertyGroup, Panel, Operator, UIList
from bpy_extras import view3d_utils

bl_info = {
    "name": "GNM Scientific Markers",
    "author": "VATRION",
    "version": (16, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > GNM Markers",
    "category": "3D View",
}

# -----------------------------------------------------------------------
# BAZA DE DATE MARKERI
# -----------------------------------------------------------------------
def _core_module(name):
    import importlib
    # ZIP vendors the numerical package under this add-on namespace. Never
    # evict unrelated modules or infer executable code paths from model paths.
    return importlib.import_module((__package__ + ".cranio." if __package__ else "cranio.") + name)


# One canonical registry supplies the GUI and offline pipeline.
_MARKER_DATA = _core_module('landmarks')
_VERTEX_DATA = _core_module('backend.gnm_backend')
LANDMARKS = [(_VERTEX_DATA.LABEL_TO_VERTEX[label], label,
               *_MARKER_DATA.LANDMARK_INFO[label], True)
             for label in _MARKER_DATA.LANDMARK_ORDER]

def _encode_index(v_id: int, is_exact: bool) -> int:
    return -(v_id + 1) if is_exact else v_id

def _get_or_create_material(name: str, color: tuple):
    """Returneaza materialul cu numele dat, creandu-l daca nu exista deja.
    Folosit doar pentru distinctia vizuala os-original vs. os-reconstruit."""
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = color
    return mat

def _pair_label(label: str):
    """Returneaza eticheta perechii contralaterale (Dr<->St) pentru un marker
    lateral, sau None daca eticheta e a unui marker median (fara pereche)."""
    if "_Dr" in label:
        return label.replace("_Dr", "_St")
    if "_St" in label:
        return label.replace("_St", "_Dr")
    return None

def _plane_markers(scene):
    return [item for item in scene.gnm_markers
            if item.side == 0 and item.bone_empty is not None
            and item.use_for_plane and item.bone_status == 'observed'
            and item.label not in _MARKER_DATA.MANDIBULAR_LANDMARKS]


def _fit_midsagittal_plane(scene):
    """Observed cranial references only; detached mandible cannot tilt the plane."""
    plane_object = scene.gnm_settings.restoration_plane_object
    if plane_object is not None:
        try:
            return _core_module('blender_restoration').object_plane(plane_object)
        except ValueError:
            return None
    points = [item.bone_empty.matrix_world.translation[:] for item in _plane_markers(scene)]
    try:
        centre, normal, rms = _core_module('restoration').fit_reference_plane(points)
        return Vector(centre), Vector(normal), rms
    except (ValueError, np.linalg.LinAlgError):
        return None

def _compute_asymmetry_rows(scene, plane_co, normal):
    """Pentru fiecare pereche Dr/St deja plasata complet, calculeaza distanta
    fiecareia fata de planul dat si diferenta dintre cele doua parti.
    Returneaza o lista de (nume_baza, dist_dr, dist_st, diferenta), sortata
    descrescator dupa diferenta (cele mai asimetrice primele)."""
    markers_by_label = {m.label: m for m in scene.gnm_markers}
    seen = set()
    rows = []
    for item in scene.gnm_markers:
        if item.side not in (-1, 1):
            continue
        if item.label in _MARKER_DATA.MANDIBULAR_LANDMARKS and not scene.gnm_settings.mandible_aligned:
            continue
        if item.label in seen:
            continue
        pair_lbl = _pair_label(item.label)
        seen.add(item.label)
        if pair_lbl:
            seen.add(pair_lbl)
        pair_item = markers_by_label.get(pair_lbl) if pair_lbl else None

        if item.bone_empty is None or pair_item is None or pair_item.bone_empty is None:
            continue

        base_name = item.label.replace("_Dr", "").replace("_St", "")
        dr_item = item if item.side == -1 else pair_item
        st_item = pair_item if item.side == -1 else item

        d_dr = abs((dr_item.bone_empty.matrix_world.translation - plane_co).dot(normal))
        d_st = abs((st_item.bone_empty.matrix_world.translation - plane_co).dot(normal))
        rows.append((base_name, d_dr, d_st, abs(d_dr - d_st)))

    rows.sort(key=lambda r: -r[3])
    return rows

def _estimate_facial_axes(scene):
    """Estimeaza un sistem de axe aproximativ pentru craniu (dreapta, sus,
    fata), folosind markerii deja plasati - necesar ca sa pozitionam camera
    de documentare consistent, indiferent de orientarea globala a craniului
    dupa import.

    'Dreapta' vine din normala planului medio-sagital (deja validata).
    'Sus' e presupus Z global (craniul e de regula importat aproximativ
    vertical). 'Fata' e estimata din Glabella/Nasion (anterior) fata de
    media Eurion_Dr/St (cel mai apropiat proxy posterior disponibil in
    setul curent de markeri - nu exista un landmark strict posterior, deci
    aceasta axa e o aproximare, nu o masuratoare riguroasa).

    Returneaza (centru, axa_dreapta, axa_sus, axa_fata) sau None daca nu sunt
    destui markeri pentru o estimare rezonabila.
    """
    from mathutils import Vector

    plane = _fit_midsagittal_plane(scene)
    if plane is None:
        return None
    plane_co, right_axis, _ = plane
    up_axis = Vector((0.0, 0.0, 1.0))

    markers_by_label = {m.label: m for m in scene.gnm_markers}
    anterior_pts = [
        markers_by_label[lbl].bone_empty.matrix_world.translation
        for lbl in ("Glabella", "Nasion")
        if lbl in markers_by_label and markers_by_label[lbl].bone_empty is not None
    ]
    posterior_pts = [
        markers_by_label[lbl].bone_empty.matrix_world.translation
        for lbl in ("Eurion_Dr", "Eurion_St")
        if lbl in markers_by_label and markers_by_label[lbl].bone_empty is not None
    ]
    if not anterior_pts or not posterior_pts:
        return None

    anterior_avg = sum(anterior_pts, Vector()) / len(anterior_pts)
    posterior_avg = sum(posterior_pts, Vector()) / len(posterior_pts)
    forward_axis = (anterior_avg - posterior_avg).normalized()

    return plane_co, right_axis, up_axis, forward_axis

# -----------------------------------------------------------------------
# PROPRIETATI
# -----------------------------------------------------------------------
class GNMSettings(PropertyGroup):
    marker_set: EnumProperty(name="Marker set", items=[
        ('EXTENDED_48', "Extended 48", "Existing 27 plus 21 additional Table 2 positions"),
        ('PAPER_32', "VAR 2026 Table 2: 32", "10 median plus 11 bilateral sites; case-study tissue reference"),
        ('LEGACY_27', "Legacy 27", "Original set with current candidate correspondences")], default='EXTENDED_48')
    cranial_modification: EnumProperty(name="Cranial modification", items=[
        ('unknown', "Not assessed", "No assessment recorded"),
        ('absent', "Not observed", "Operator reports no intentional modification"),
        ('present', "Present / suspected", "Document altered vault and review the general GNM model's applicability")], default='unknown')
    case_notes: StringProperty(name="Case / restoration notes")
    python_status: StringProperty(default="Select an installed 64-bit Python 3.10+ interpreter")
    python_executable: StringProperty(name="Python executable / venv folder", subtype="FILE_PATH", description="Windows: select .venv/Scripts/python.exe, not gnm_reconstruct.py or blender.exe")
    case_directory: StringProperty(name="Case output folder", subtype="DIR_PATH")
    offline_status: StringProperty(default="Ready")
    marker_size_mm: FloatProperty(name="Marker Radius (mm)", default=1.5, min=0.1)
    peg_thickness_mm: FloatProperty(name="Peg Thickness (mm)", default=0.5, min=0.1)

    restoration_plane_object: PointerProperty(
        name="Cranial reference plane", type=bpy.types.Object,
        description="Optional object whose local XY plane defines symmetry; otherwise use observed cranial midline markers")
    mandible_aligned: BoolProperty(name="Mandible articulated with cranium", default=False,
        description="Confirm its pose/occlusion has been reviewed before using the cranial plane for mandibular regions")
    restoration_tolerance_mm: FloatProperty(name="Overlap tolerance (mm)", default=0.1, min=0.001, max=2.0,
        description="Suppress generated triangles fully within this distance of registered preserved surfaces; inspect partial intersections")
    aplica_materiale_distincte: BoolProperty(name="Color inferred patches", default=True)
    restoration_status: StringProperty(default="Register each fragment; preserve central anatomy")


    sursa_fisier: StringProperty(name="Source File (Skull)", default="")
    ultim_export_csv: StringProperty(name="Last CSV Export", default="")
    ultim_export_timestamp: StringProperty(name="Last Export Date", default="")

def _update_tissue_depth(self, context):
    if self.bone_empty is None or self.target_empty is None:
        return
    bone = self.bone_empty.matrix_world.translation
    direction = self.target_empty.matrix_world.translation - bone
    if direction.length < 1e-9:
        direction = Vector(self.bone_empty.get("gnm_normal", (0, 0, 1)))
    direction.normalize()
    self.target_empty.matrix_world.translation = bone + direction * self.tissue_depth_mm
    if self.peg_object is not None:
        self.peg_object.location = bone + direction * self.tissue_depth_mm / 2
        self.peg_object.scale.z = self.tissue_depth_mm
        self.peg_object.rotation_quaternion = direction.to_track_quat("Z", "Y")


def _marker_fit_changed(self, context):
    if context is not None and hasattr(context.scene, 'gnm_live'):
        _refresh_marker_objects(context.scene)
        _request_refit(context.scene)


class GNMMarkerItem(PropertyGroup):
    gnm_index: IntProperty()
    label: StringProperty()
    tissue_depth_mm: FloatProperty(default=5.0, min=0.0, update=_update_tissue_depth)
    tissue_source: StringProperty(name="Tissue source / method", default="legacy-unvalidated")
    use_for_fit: BoolProperty(name="Include in fit", default=True, update=_marker_fit_changed)
    fit_weight: FloatProperty(name="Weight (0 = preset)", default=0.0, min=0.0, max=1.0, update=_marker_fit_changed)
    mapping_reviewed: BoolProperty(name="Skin correspondence reviewed", default=False, update=_marker_fit_changed)
    bone_status: EnumProperty(name="Bone provenance", items=[
        ('unspecified', "Not recorded", "Record whether the site is preserved or inferred"),
        ('observed', "Observed", "Landmark on preserved scanned anatomy"),
        ('reconstructed', "Digitally repaired", "Landmark on repaired or mirrored bone"),
        ('inferred', "Inferred", "Location inferred from incomplete anatomy")], default='unspecified')
    use_for_plane: BoolProperty(name="Use observed cranial point for plane", default=True)
    marker_notes: StringProperty(name="Placement / direction notes")
    side: IntProperty(default=0)
    bone_empty: PointerProperty(type=bpy.types.Object)
    target_empty: PointerProperty(type=bpy.types.Object)
    peg_object: PointerProperty(type=bpy.types.Object)
    # V13: override manual al vertexului GNM pentru acest landmark (-1 = fara
    # override; se foloseste lantul de precedenta V12 > JSON). Se seteaza cu
    # operatorul gnm.pick_gnm_vertex (click pe mesh-ul GNM din panoul drept).
    gnm_vertex_override: IntProperty(default=-1, min=-1)

    @property
    def is_placed(self) -> bool:
        return self.bone_empty is not None and self.target_empty is not None

# -----------------------------------------------------------------------
# OPERATORI
# -----------------------------------------------------------------------
class GNM_OT_import_setup(Operator):
    bl_idname = "gnm.import_setup"
    bl_label = "1. Import & Calibrate Skull (.stl/.obj)"
    bl_options = {"REGISTER", "UNDO"}
    filepath: StringProperty(subtype="FILE_PATH")
    source_units: EnumProperty(name="Source coordinates", items=[
        ('mm', "Millimetres", "1 source coordinate = 1 mm"),
        ('cm', "Centimetres", "1 source coordinate = 10 mm"),
        ('m', "Metres", "1 source coordinate = 1000 mm")], default='mm')

    def draw(self, context):
        self.layout.prop(self, "source_units")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        scene = context.scene
        scene.unit_settings.system = 'METRIC'
        scene.unit_settings.scale_length = 0.001
        scene.unit_settings.length_unit = 'MILLIMETERS'
        scene.gnm_settings.sursa_fisier = os.path.basename(self.filepath)

        ext = self.filepath.lower().split('.')[-1]
        objects_before = set(context.scene.objects)
        try:
            if ext == 'stl':
                if hasattr(bpy.ops.wm, "stl_import"): bpy.ops.wm.stl_import(filepath=self.filepath)
                else: bpy.ops.import_mesh.stl(filepath=self.filepath)
            elif ext == 'obj':
                if hasattr(bpy.ops.wm, "obj_import"): bpy.ops.wm.obj_import(filepath=self.filepath)
                else: bpy.ops.import_scene.obj(filepath=self.filepath, split_mode='OFF')
            else:
                self.report({"ERROR"}, "Unsupported format!")
                return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, f"Import error: {e}")
            return {"CANCELLED"}

        # Unele fisiere (mai ales .obj cu grupuri/obiecte multiple, sau
        # fragmente scanate neconectate) aduc MAI MULTE obiecte separate la
        # import. Inainte procesam doar primul selectat - restul ramaneau
        # neatinse, la scara/pozitia bruta din fisier. Le unim intr-un singur
        # obiect ÎNAINTE de centrare/scalare, ca sa fie procesate uniform.
        imported_objects = [o for o in context.scene.objects if o not in objects_before and o.type == 'MESH']
        if not imported_objects:
            self.report({"ERROR"}, "The import produced no mesh object.")
            return {"CANCELLED"}

        bpy.ops.object.select_all(action='DESELECT')
        for o in imported_objects:
            o.select_set(True)
        context.view_layer.objects.active = imported_objects[0]

        joined_multiple = len(imported_objects) > 1
        if joined_multiple:
            bpy.ops.object.join()

        obj = context.view_layer.objects.active

        # Aliniere si Scalare
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
        obj.location = (0, 0, 0)

        factor = {"mm": 1.0, "cm": 10.0, "m": 1000.0}[self.source_units]
        obj.scale *= factor
            
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

        # CORECTAREA NORMALELOR
        # Nota: pe fragmente neconectate (insule separate topologic in acelasi
        # mesh, ca la un craniu partial cu bucati care nu se ating), aceasta
        # corectie ruleaza independent pe fiecare insula - e posibil, desi rar,
        # ca o insula sa iasa cu normalele inversate fata de restul. Daca vezi
        # o zona cu shading ciudat/negru pe o singura piesa, verific-o manual.
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data)
        bm.free()

        msg = "Skull imported, scaled and normals fixed!"
        if joined_multiple:
            msg = f"The import brought {len(imported_objects)} separate objects - they were joined into one. " + msg
        self.report({"INFO"}, msg)
        return {"FINISHED"}

class GNM_OT_init_markers(Operator):
    bl_idname = "gnm.init_markers"
    bl_label = "Add Missing Markers"
    bl_description = "Add the chosen set while preserving existing placements, tissue values and manual vertices"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        existing = {item.label for item in scene.gnm_markers}
        paper = _core_module('paper_reference')
        added = 0
        for label in _MARKER_DATA.marker_labels(scene.gnm_settings.marker_set):
            if label in existing:
                continue
            item = scene.gnm_markers.add()
            item.gnm_index = _encode_index(_VERTEX_DATA.LABEL_TO_VERTEX[label], True)
            item.label = label
            item.tissue_depth_mm, item.side = _MARKER_DATA.LANDMARK_INFO[label]
            item.tissue_source = _MARKER_DATA.initial_tissue_source(label)
            if scene.gnm_settings.marker_set == 'PAPER_32':
                item.tissue_depth_mm = paper.PAPER_DEPTHS[label]
                item.tissue_source = paper.TISSUE_SOURCE
            added += 1
        scene.gnm_marker_active_index = min(scene.gnm_marker_active_index, max(0, len(scene.gnm_markers) - 1))
        self.report({'INFO'}, f"Added {added}; {len(scene.gnm_markers)} markers. Existing case data preserved.")
        return {'FINISHED'}


class GNM_OT_apply_paper_tissues(Operator):
    bl_idname = 'gnm.apply_paper_tissues'
    bl_label = 'Apply Table 2 Tissue Depths'
    bl_description = 'Replace depths at the paper sites using its normal-female reference; review applicability. Undo restores previous values'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        paper = _core_module('paper_reference')
        count = 0
        for item in context.scene.gnm_markers:
            if item.label in paper.PAPER_DEPTHS:
                item.tissue_depth_mm = paper.PAPER_DEPTHS[item.label]
                item.tissue_source = paper.TISSUE_SOURCE
                count += 1
        self.report({'INFO'}, f"Updated {count} Table 2 sites; review study applicability and placement direction.")
        return {'FINISHED'}


class GNM_OT_place_marker(Operator):
    bl_idname = "gnm.place_marker"
    bl_label = "Place Marker"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if not context.scene.gnm_markers: return {"CANCELLED"}
        if not _is_mm_scene(context.scene):
            self.report({"ERROR"}, "Set scene scale to 0.001 (1 Blender unit = 1 mm) before placing markers")
            return {"CANCELLED"}
        self._show_symmetry_ghost(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "MOUSEMOVE": return {"PASS_THROUGH"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            result = self._place(context, event)
            if result != {"RUNNING_MODAL"}:
                self._clear_symmetry_ghost()
            return result
        if event.type in {"RIGHTMOUSE", "ESC"}:
            self._clear_symmetry_ghost()
            return {"CANCELLED"}
        return {"PASS_THROUGH"}

    def _show_symmetry_ghost(self, context):
        """Daca marker-ul activ are o pereche (Dr/St) deja plasata si putem
        calcula planul medio-sagital din markerii mediani, aratam o pozitie-
        fantoma oglindita, ca reper vizual pentru unde ar trebui plasat."""
        self._clear_symmetry_ghost()

        scene = context.scene
        idx = scene.gnm_marker_active_index
        item = scene.gnm_markers[idx]

        pair_label = _pair_label(item.label)
        if pair_label is None:
            return  # marker median, nu are pereche

        pair_item = next((m for m in scene.gnm_markers if m.label == pair_label), None)
        if (item.label in _MARKER_DATA.MANDIBULAR_LANDMARKS
                and not scene.gnm_settings.mandible_aligned):
            return
        if pair_item is None or pair_item.bone_empty is None:
            return  # perechea nu e inca plasata

        plane = _fit_midsagittal_plane(scene)
        if plane is None:
            return  # inca nu sunt destui markeri mediani pentru un plan

        plane_co, normal, _ = plane
        pair_pos = pair_item.bone_empty.matrix_world.translation
        d = (pair_pos - plane_co).dot(normal)
        ghost_pos = pair_pos - 2.0 * d * normal

        ghost = bpy.data.objects.new("GNM_GHOST_PREVIEW", None)
        ghost.empty_display_type = 'CIRCLE'
        ghost.empty_display_size = scene.gnm_settings.marker_size_mm * 1.6
        ghost.location = ghost_pos
        context.collection.objects.link(ghost)

    def _clear_symmetry_ghost(self):
        old = bpy.data.objects.get("GNM_GHOST_PREVIEW")
        if old:
            bpy.data.objects.remove(old, do_unlink=True)

    def _place(self, context, event):
        scene = context.scene
        idx = scene.gnm_marker_active_index
        item = scene.gnm_markers[idx]

        region = context.region
        rv3d = context.region_data
        coord = (event.mouse_region_x, event.mouse_region_y)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        ray_dir = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)

        depsgraph = context.evaluated_depsgraph_get()
        # V13: in workflow-ul live, capul GNM (piele) coexista cu craniul in
        # aceeasi lume si il invaluie; sarim peste obiectele GNM live ca sa
        # lovim intotdeauna craniul (ray-marching, vezi _ray_cast_skull).
        result, location, normal, hit_object = _ray_cast_skull(
            scene, depsgraph, ray_origin, ray_dir, return_object=True)

        if not result: return {"RUNNING_MODAL"}

        depth = item.tissue_depth_mm
        target_location = location + normal.normalized() * depth
        m_size = scene.gnm_settings.marker_size_mm
        p_thick = scene.gnm_settings.peg_thickness_mm

        for old_obj in [item.bone_empty, item.target_empty, item.peg_object]:
            if old_obj: bpy.data.objects.remove(old_obj, do_unlink=True)
        
        bone = bpy.data.objects.new(f"GNM_OS_{item.label}", None)
        bone.empty_display_type = 'SPHERE'
        bone.empty_display_size = m_size
        bone.location = location
        bone["gnm_normal"] = tuple(normal.normalized())
        context.collection.objects.link(bone)
        item.bone_empty = bone
        _record_marker_surface(item, hit_object)

        tinta = bpy.data.objects.new(f"GNM_PIELE_{item.label}", None)
        tinta.empty_display_type = 'SPHERE'
        tinta.empty_display_size = m_size
        tinta.location = target_location
        context.collection.objects.link(tinta)
        item.target_empty = tinta

        direction = target_location - location
        mesh = bpy.data.meshes.new("Peg")
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=12, radius1=1.0, radius2=1.0, depth=1.0)
        bm.to_mesh(mesh)
        bm.free()
        
        peg = bpy.data.objects.new(f"GNM_BAT_{item.label}", mesh)
        peg.location = (location + target_location) / 2
        peg.rotation_mode = "QUATERNION"
        peg.rotation_quaternion = direction.to_track_quat("Z", "Y")
        peg.scale = (p_thick, p_thick, direction.length)
        context.collection.objects.link(peg)
        item.peg_object = peg

        # V13.7: coloreaza os/piele/bat dupa schema ghost-urilor (verde/
        # portocaliu/mov/rosu - vezi legenda din panou).
        _refresh_marker_objects(scene)

        # V13: declansam un refit live (no-op daca modul live e oprit).
        _request_refit(scene)
        scene.gnm_marker_active_index = (idx + 1) % len(scene.gnm_markers)
        return {"FINISHED"}

class GNM_OT_next_unplaced(Operator):
    bl_idname = "gnm.next_unplaced"
    bl_label = "Next Unplaced Marker"
    bl_description = "Jump directly to the first marker in the list that has not been placed yet"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        markers = scene.gnm_markers
        n = len(markers)
        if n == 0:
            return {"CANCELLED"}

        current = scene.gnm_marker_active_index
        for offset in range(1, n + 1):
            idx = (current + offset) % n
            if not markers[idx].is_placed:
                scene.gnm_marker_active_index = idx
                return {"FINISHED"}

        self.report({"INFO"}, "All markers are already placed!")
        return {"FINISHED"}

class GNM_OT_toggle_plane_preview(Operator):
    bl_idname = "gnm.toggle_plane_preview"
    bl_label = "Show/Hide Midsagittal Plane"
    bl_description = (
        "Shows the computed midsagittal plane as a reference grid (wireframe, "
        "visible through the skull), so you can verify its position before "
        "reconstruction. Press again to hide it"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        existing = bpy.data.objects.get("GNM_PLAN_PREVIEW")
        if existing:
            bpy.data.objects.remove(existing, do_unlink=True)
            return {"FINISHED"}

        scene = context.scene
        plane = _fit_midsagittal_plane(scene)
        if plane is None:
            self.report({"ERROR"}, "At least 3 placed midline markers are required.")
            return {"CANCELLED"}
        plane_co, normal, rms = plane

        ref_obj = context.active_object
        if ref_obj is not None and ref_obj.type == 'MESH':
            radius = max(ref_obj.dimensions) * 0.7
        else:
            radius = 100.0  # fallback rezonabil (mm) daca nu exista un obiect activ

        mesh = bpy.data.meshes.new("GNM_PlanPreviewMesh")
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=10, y_segments=10, size=radius)
        bm.to_mesh(mesh)
        bm.free()

        obj = bpy.data.objects.new("GNM_PLAN_PREVIEW", mesh)
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = normal.to_track_quat("Z", "Y")
        obj.location = plane_co
        obj.display_type = 'WIRE'
        obj.show_in_front = True
        context.collection.objects.link(obj)

        self.report({"INFO"},
                    f"Plane shown (fit RMS error: {rms:.3f} mm). Run again to hide it.")
        return {"FINISHED"}

class GNM_OT_recenter_on_plane(Operator):
    bl_idname = "gnm.recenter_on_plane"
    bl_label = "Recenter on Midsagittal Plane"
    bl_description = (
        "Moves the skull and ALL already-placed markers together, so that the "
        "center of the computed midsagittal plane ends up at the scene origin "
        "(0,0,0). Useful for partial/asymmetric skulls, where the automatic "
        "bounding-box centering at import does not match the real anatomic center"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        scene = context.scene
        src_obj = context.active_object
        if src_obj is None or src_obj.type != 'MESH':
            self.report({"ERROR"}, "Select the skull (mesh object) before recentering.")
            return {"CANCELLED"}

        plane = _fit_midsagittal_plane(scene)
        if plane is None:
            self.report({"ERROR"}, "At least 3 placed midline markers are required to compute the center.")
            return {"CANCELLED"}
        plane_co, normal, rms = plane

        offset = -plane_co

        # Adunam TOATE obiectele care trebuie mutate impreuna: craniul insusi,
        # plus toate empty-urile/"betele" markerilor deja plasati - altfel
        # markerii ar ramane in urma si s-ar dezalinia de pe craniu. Niciun
        # obiect din acest addon nu e parentat, deci deplasarea world-space
        # se aplica direct pe .location.
        to_move = [src_obj]
        for item in scene.gnm_markers:
            for o in (item.bone_empty, item.target_empty, item.peg_object):
                if o is not None:
                    to_move.append(o)

        for name in ("GNM_PLAN_PREVIEW",):
            extra = bpy.data.objects.get(name)
            if extra is not None:
                to_move.append(extra)
        for suffix in ("_PreviewOglindit", "_Intact", "_Oglindit", "_Reconstruit"):
            extra = bpy.data.objects.get(f"{src_obj.name}{suffix}")
            if extra is not None and extra not in to_move:
                to_move.append(extra)

        for row in scene.gnm_restoration_regions:
            to_move.extend(o for o in (row.source_object, row.result_object, row.plane_object) if o is not None)
        if scene.gnm_settings.restoration_plane_object:
            to_move.append(scene.gnm_settings.restoration_plane_object)
        to_move = list(dict.fromkeys(to_move))
        transforms = {o: o.matrix_world.copy() for o in to_move}
        # Apply world transforms parent-first, from an unchanged snapshot.
        def parent_depth(obj):
            depth = 0
            while obj.parent is not None:
                depth += 1
                obj = obj.parent
            return depth
        for o in sorted(to_move, key=parent_depth):
            matrix = transforms[o]
            matrix.translation += offset
            o.matrix_world = matrix
            if o.get('gnm_region_patch') and o.get('gnm_restoration_metadata'):
                import json
                metadata = json.loads(o['gnm_restoration_metadata'])
                metadata['plane_origin_mm'] = list(Vector(metadata['plane_origin_mm']) + offset)
                previous = Vector(metadata.get('post_generation_translation_mm', (0, 0, 0)))
                metadata['post_generation_translation_mm'] = list(previous + offset)
                o['gnm_restoration_metadata'] = json.dumps(metadata)
        context.view_layer.update()
        _LIVE.skull = None  # world-space samples must be prepared again
        _LIVE.dense_set = None

        self.report({"INFO"},
                    f"Recentering complete: {len(to_move)} objects moved by "
                    f"{offset.length:.2f} mm (plane RMS error: {rms:.3f} mm).")
        return {"FINISHED"}

class GNM_OT_asymmetry_report(Operator):
    bl_idname = "gnm.asymmetry_report"
    bl_label = "Generate Bilateral Asymmetry Report"
    bl_description = (
        "For each placed R/L pair, computes each side's distance to the "
        "midsagittal plane and the difference between the two sides"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        plane = _fit_midsagittal_plane(scene)
        if plane is None:
            self.report({"ERROR"}, "Use at least 3 non-collinear observed cranial midline markers, or a manual reference plane.")
            return {"CANCELLED"}
        plane_co, normal, rms = plane

        rows = _compute_asymmetry_rows(scene, plane_co, normal)
        if not rows:
            self.report({"WARNING"}, "There is no complete R/L pair (both sides placed) yet.")
            return {"CANCELLED"}

        n_midline = len(_plane_markers(scene))
        lines = []
        lines.append("=== Bilateral Asymmetry Report (GNM) ===")
        lines.append(f"Midsagittal plane: fit RMS error = {rms:.3f} mm ({n_midline} midline markers)")
        lines.append("")
        lines.append(f"{'Landmark':22s}  {'Dist. R (mm)':>14s}  {'Dist. L (mm)':>14s}  {'Difference (mm)':>15s}")
        lines.append("-" * 72)
        for base_name, d_dr, d_st, diff in rows:
            lines.append(f"{base_name:22s}  {d_dr:14.2f}  {d_st:14.2f}  {diff:15.2f}")

        avg_diff = sum(r[3] for r in rows) / len(rows)
        max_diff = max(r[3] for r in rows)
        max_label = next(r[0] for r in rows if r[3] == max_diff)
        lines.append("-" * 72)
        lines.append(f"Mean difference: {avg_diff:.2f} mm  |  Max difference: {max_diff:.2f} mm ({max_label})")
        lines.append("")
        lines.append(
            "Note: some asymmetry is biologically normal. Large, consistent "
            "differences across several pairs may indicate either a marker "
            "placement error or a real asymmetry/deformation of the specimen."
        )

        text_name = "GNM_Asymmetry_Report"
        existing_text = bpy.data.texts.get(text_name)
        if existing_text:
            bpy.data.texts.remove(existing_text)
        text_block = bpy.data.texts.new(text_name)
        text_block.write("\n".join(lines))

        self.report({"INFO"},
                    f"Report generated ({len(rows)} pairs) - see Text Editor > {text_name}. "
                    f"Mean difference: {avg_diff:.2f} mm, max: {max_diff:.2f} mm ({max_label}).")
        return {"FINISHED"}

class GNM_OT_session_report(Operator):
    bl_idname = "gnm.session_report"
    bl_label = "Generate Session Report"
    bl_description = (
        "Generates a complete summary of the current session (placed markers, "
        "tissue depths used, plane quality, asymmetry, reconstruction), useful "
        "as supplementary material in a publication or project report"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        settings = scene.gnm_settings
        default_depths = {lbl: depth for _, lbl, depth, _, _ in LANDMARKS}

        lines = []
        lines.append("=== GNM Session Report ===")
        lines.append(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Addon version: {'.'.join(str(v) for v in bl_info['version'])}")
        if settings.sursa_fisier:
            lines.append(f"Source file (skull): {settings.sursa_fisier}")
        lines.append("")

        placed = [m for m in scene.gnm_markers if m.is_placed]
        unplaced = [m for m in scene.gnm_markers if not m.is_placed]
        lines.append(f"Markers placed: {len(placed)}/{len(scene.gnm_markers)}")
        if unplaced:
            lines.append("Not placed yet: " + ", ".join(m.label for m in unplaced))
        lines.append("")

        modified_depths = [
            (m.label, m.tissue_depth_mm, default_depths.get(m.label))
            for m in scene.gnm_markers
            if m.label in default_depths and abs(m.tissue_depth_mm - default_depths[m.label]) > 1e-6
        ]
        if modified_depths:
            lines.append("Tissue depths changed from defaults:")
            for lbl, current, default in modified_depths:
                lines.append(f"  {lbl}: {current:.2f} mm (default: {default:.2f} mm)")
        else:
            lines.append("Tissue depths: all at the default values from the GNM table.")
        lines.append("")

        plane = _fit_midsagittal_plane(scene)
        if plane is None:
            lines.append("Midsagittal plane: cannot be computed (insufficient stable, observed cranial references; use a manual plane).")
        else:
            plane_co, normal, rms = plane
            n_midline = len(_plane_markers(scene))
            lines.append(f"Midsagittal plane: {n_midline} midline markers, RMS error = {rms:.3f} mm")

            rows = _compute_asymmetry_rows(scene, plane_co, normal)
            if rows:
                avg_diff = sum(r[3] for r in rows) / len(rows)
                max_diff = max(r[3] for r in rows)
                max_label = next(r[0] for r in rows if r[3] == max_diff)
                lines.append(
                    f"Bilateral asymmetry ({len(rows)} complete pairs): "
                    f"mean {avg_diff:.2f} mm, max {max_diff:.2f} mm ({max_label})"
                )
            else:
                lines.append("Bilateral asymmetry: no complete R/L pair yet.")
        lines.append("")

        reconstructed = [o for o in scene.objects if o.get("gnm_reconstructed_via_mirroring")]
        if reconstructed:
            lines.append("Mirroring reconstruction:")
            for obj in reconstructed:
                lines.append(
                    f"  '{obj.name}' - intact side: {obj.get('gnm_mirror_intact_side', '?')}, "
                    f"plane RMS error: {float(obj.get('gnm_mirror_rms_mm', float('nan'))):.3f} mm, "
                    f"source: {obj.get('gnm_mirror_source', '?')}"
                )
        else:
            lines.append("Mirroring reconstruction: not used in this session.")
        lines.append("")

        if settings.ultim_export_csv:
            lines.append(f"Last CSV export: {settings.ultim_export_csv} ({settings.ultim_export_timestamp})")
        else:
            lines.append("CSV export: none yet in this session.")

        text_name = "GNM_Session_Report"
        existing_text = bpy.data.texts.get(text_name)
        if existing_text:
            bpy.data.texts.remove(existing_text)
        text_block = bpy.data.texts.new(text_name)
        text_block.write("\n".join(lines))

        self.report({"INFO"}, f"Session report generated - see Text Editor > {text_name}.")
        return {"FINISHED"}

class GNM_OT_capturi_standardizate(Operator):
    bl_idname = "gnm.capturi_standardizate"
    bl_label = "Generate Standardized Captures (Front/3-4/Profile)"
    bl_description = (
        "Creates an orthographic camera and a fixed light, positioned relative "
        "to the skull's estimated axes (not global coordinates), and renders 3 "
        "consistent captures: front, 3/4 and profile. Requires at least Glabella "
        "or Nasion, plus both Eurion_R and Eurion_L markers"
    )
    bl_options = {"REGISTER", "UNDO"}
    directory: StringProperty(subtype="DIR_PATH")

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def _get_or_create_sun(self, context, name, position, target, energy):
        light_data = bpy.data.lights.get(name)
        if light_data is None:
            light_data = bpy.data.lights.new(name, type='SUN')
        light_data.energy = energy

        light_obj = bpy.data.objects.get(name)
        if light_obj is None:
            light_obj = bpy.data.objects.new(name, light_data)
            context.collection.objects.link(light_obj)

        look_dir = target - position
        light_obj.location = position
        light_obj.rotation_mode = "QUATERNION"
        light_obj.rotation_quaternion = look_dir.to_track_quat('-Z', 'Y')
        return light_obj

    def execute(self, context):
        scene = context.scene
        src_obj = context.active_object
        if src_obj is None or src_obj.type != 'MESH':
            self.report({"ERROR"}, "Select the skull (mesh object) before generating captures.")
            return {"CANCELLED"}
        if not self.directory:
            self.report({"ERROR"}, "Choose a destination folder.")
            return {"CANCELLED"}

        axes = _estimate_facial_axes(scene)
        if axes is None:
            self.report({"ERROR"},
                        "Cannot estimate face orientation - place at least Glabella or "
                        "Nasion, plus both Eurion_R and Eurion_L markers.")
            return {"CANCELLED"}
        center, right_axis, up_axis, forward_axis = axes

        max_dim = max(src_obj.dimensions)
        cam_distance = max_dim * 3.0
        light_distance = max_dim * 4.0

        cam_data = bpy.data.cameras.get("GNM_Camera_Documentare")
        if cam_data is None:
            cam_data = bpy.data.cameras.new("GNM_Camera_Documentare")
        cam_data.type = 'ORTHO'
        cam_data.ortho_scale = max_dim * 1.4

        cam_obj = bpy.data.objects.get("GNM_Camera_Documentare")
        if cam_obj is None:
            cam_obj = bpy.data.objects.new("GNM_Camera_Documentare", cam_data)
            context.collection.objects.link(cam_obj)

        original_camera = scene.camera
        scene.camera = cam_obj

        key_dir = (forward_axis * 0.6 + right_axis * 0.6 + up_axis * 1.0).normalized()
        fill_dir = (forward_axis * 0.6 - right_axis * 0.6 + up_axis * 0.6).normalized()
        self._get_or_create_sun(context, "GNM_Lumina_Principala", center + key_dir * light_distance, center, energy=3.0)
        self._get_or_create_sun(context, "GNM_Lumina_Umplere", center + fill_dir * light_distance, center, energy=1.0)

        scene.render.resolution_x = 1200
        scene.render.resolution_y = 1200
        scene.render.image_settings.file_format = 'PNG'

        views = [
            ("front", forward_axis),
            ("3quarter", (forward_axis + right_axis).normalized()),
            ("profile", right_axis),
        ]

        saved_files = []
        for suffix, direction in views:
            cam_obj.location = center + direction * cam_distance
            look_dir = center - cam_obj.location
            cam_obj.rotation_mode = "QUATERNION"
            cam_obj.rotation_quaternion = look_dir.to_track_quat('-Z', 'Y')

            filepath = os.path.join(self.directory, f"{src_obj.name}_{suffix}.png")
            scene.render.filepath = filepath
            bpy.ops.render.render(write_still=True)
            saved_files.append(filepath)

        scene.camera = original_camera

        self.report({"INFO"}, f"3 captures saved in {self.directory} (front/three-quarter/profile).")
        return {"FINISHED"}

class GNMRestorationRegion(PropertyGroup):
    uid: StringProperty()
    name: StringProperty(name='Region', default='Preserved fragment')
    enabled: BoolProperty(default=True)
    source_object: PointerProperty(name='Preserved source', type=bpy.types.Object,
                                  poll=lambda self, obj: obj.type == 'MESH')
    vertex_group: StringProperty(name='Donor vertex group', description='Blank uses the entire object; only complete faces with all vertex weights > 0.5 are copied')
    anatomy: EnumProperty(name='Anatomy', items=[('CRANIUM', 'Cranium', ''),
        ('MANDIBLE', 'Mandible', ''), ('NASAL', 'Nasal / central', ''), ('OTHER', 'Other', '')])
    action: EnumProperty(name='Action', items=[('KEEP', 'Keep preserved', 'Protect this original fragment without mirroring'),
        ('MIRROR', 'Mirror selected region', 'Generate an inferred patch on the opposite side; originals remain untouched')], default='KEEP')
    donor_side: EnumProperty(name='Anatomical donor side', items=[('DR', 'Right', ''), ('ST', 'Left', '')])
    plane_object: PointerProperty(name='Region reference plane', type=bpy.types.Object,
        description='Optional local XY plane; required for an unarticulated mandible')
    result_object: PointerProperty(type=bpy.types.Object)
    notes: StringProperty(name='Restoration / articulation notes')


def _region_plane(scene, region):
    if region.plane_object is not None:
        return _core_module('blender_restoration').object_plane(region.plane_object)
    if region.anatomy == 'MANDIBLE' and not scene.gnm_settings.mandible_aligned:
        raise ValueError(f'{region.name}: use a mandibular reference plane or confirm reviewed articulation with the cranium')
    plane = _fit_midsagittal_plane(scene)
    if plane is None:
        raise ValueError('Set a reference-plane object or at least three non-collinear, observed cranial midline points enabled for the plane')
    if plane[2] > 1.5:
        raise ValueError('Plane RMS exceeds 1.5 mm. Review references or set an explicit plane before restoration')
    return plane


def _restoration_records(scene):
    import json
    records = []
    for item in scene.gnm_restoration_regions:
        record = dict(region=item.name, enabled=item.enabled, anatomy=item.anatomy,
                      action=item.action, donor_side=item.donor_side,
                      source=item.source_object.name if item.source_object else None,
                      vertex_group=item.vertex_group, notes=item.notes,
                      mandible_articulated=scene.gnm_settings.mandible_aligned)
        if item.result_object and item.result_object.get('gnm_region_patch') == item.uid:
            record['generated_patch'] = json.loads(item.result_object.get('gnm_restoration_metadata', '{}'))
        records.append(record)
    return records


class GNM_OT_region_add(Operator):
    bl_idname = 'gnm.region_add'
    bl_label = 'Add Active Fragment'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        import uuid
        if context.active_object.get('gnm_region_patch'):
            self.report({'ERROR'}, 'Select preserved bone, not a generated patch')
            return {'CANCELLED'}
        row = context.scene.gnm_restoration_regions.add()
        row.uid = uuid.uuid4().hex
        row.name = context.active_object.name
        row.source_object = context.active_object
        context.scene.gnm_restoration_active_index = len(context.scene.gnm_restoration_regions) - 1
        return {'FINISHED'}


class GNM_OT_region_remove(Operator):
    bl_idname = 'gnm.region_remove'
    bl_label = 'Remove Region and Its Generated Patch'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.gnm_restoration_regions)

    def execute(self, context):
        scene = context.scene
        index = scene.gnm_restoration_active_index
        row = scene.gnm_restoration_regions[index]
        if row.result_object and row.result_object.get('gnm_region_patch') == row.uid:
            bpy.data.objects.remove(row.result_object, do_unlink=True)
        scene.gnm_restoration_regions.remove(index)
        scene.gnm_restoration_active_index = min(index, max(0, len(scene.gnm_restoration_regions) - 1))
        return {'FINISHED'}


class GNM_UL_restoration_regions(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, 'enabled', text='')
        row.label(text=item.name, icon='MOD_MIRROR' if item.action == 'MIRROR' else 'LOCKED')


class GNM_OT_mirror_reconstruct(Operator):
    """Compatibility operator ID now generates separate, region-specific patches."""
    bl_idname = 'gnm.mirror_reconstruct'
    bl_label = 'Generate / Update Region Patches'
    bl_description = 'Mirror explicitly selected donors; regenerate managed patches; preserve every original fragment without cutting, joining or welding it'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.scene.gnm_restoration_regions)

    def execute(self, context):
        import json
        scene = context.scene
        settings = scene.gnm_settings
        geometry = _core_module('blender_restoration')
        rows = [row for row in scene.gnm_restoration_regions if row.enabled and row.action == 'MIRROR']
        try:
            if scene.unit_settings.system != 'METRIC' or abs(scene.unit_settings.scale_length - 0.001) > 1e-8:
                raise ValueError('Restoration requires world millimetres: Metric scale 0.001')
            if not rows:
                raise ValueError('Choose Mirror selected region for at least one donor; keep nasal/central anatomy as Keep preserved')
            sources = list({row.source_object for row in scene.gnm_restoration_regions if row.source_object})
            signatures = set()
            for row in rows:
                geometry.check_source(row.source_object)
                if row.result_object and row.result_object.get('gnm_region_patch') != row.uid:
                    raise ValueError('Result pointer does not refer to this region\'s generated patch')
                signature = (row.source_object.as_pointer(), row.vertex_group)
                if signature in signatures:
                    raise ValueError('Duplicate donor region: the same source/group is scheduled more than once')
                signatures.add(signature)
            protected = geometry.protected_surface(sources)
            prepared = []
            # Complete preflight and geometry before changing any output object.
            for row in rows:
                vertices, faces, metadata = geometry.build_patch(row.source_object, row.vertex_group,
                    _region_plane(scene, row), protected, settings.restoration_tolerance_mm)
                metadata.update(region=row.name, anatomy=row.anatomy, donor_side=row.donor_side,
                    notes=row.notes, preserved_objects=[obj.name for obj in sources],
                    plane_reference=(row.plane_object.name if row.plane_object else
                        settings.restoration_plane_object.name if settings.restoration_plane_object else
                        'observed cranial landmarks'))
                prepared.append((row, vertices, faces, metadata))
            for row, vertices, faces, metadata in prepared:
                obj = row.result_object
                if not faces and obj is None:
                    continue
                mesh = bpy.data.meshes.new('GNM_Inferred_' + row.name)
                mesh.from_pydata(vertices, [], faces)
                mesh.update()
                if obj is None:
                    obj = bpy.data.objects.new('GNM_Inferred_' + row.name, mesh)
                    scene.collection.objects.link(obj)
                    row.result_object = obj
                else:
                    old_mesh = obj.data
                    obj.data = mesh
                    if old_mesh.users == 0:
                        bpy.data.meshes.remove(old_mesh)
                obj.parent = None
                obj.matrix_world = Matrix.Identity(4)
                obj.hide_set(not bool(faces))
                obj['gnm_region_patch'] = row.uid
                obj['gnm_reconstructed_via_mirroring'] = True
                obj['gnm_mirror_source'] = row.source_object.name
                obj['gnm_mirror_intact_side'] = row.donor_side
                obj['gnm_mirror_rms_mm'] = metadata['plane_rms_mm']
                obj['gnm_restoration_metadata'] = json.dumps(metadata)
                if settings.aplica_materiale_distincte:
                    mesh.materials.append(_get_or_create_material('GNM_Inferred_Bone', (0.3, 0.55, 0.85, 1.0)))
            total = sum(len(faces) for _, _, faces, _ in prepared)
            contact = sum(meta['partial_contact_faces'] for _, _, _, meta in prepared)
            settings.restoration_status = f'{len(prepared)} regions; {total} inferred faces; {contact} faces near preserved surfaces. Inspect seams; originals retained.'
            self.report({'INFO'}, settings.restoration_status)
            return {'FINISHED'}
        except (ValueError, RuntimeError) as exc:
            settings.restoration_status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class GNM_OT_audit_landmarks(Operator):
    bl_idname = 'gnm.audit_landmarks'
    bl_label = 'Audit Landmark Duplicates'

    def execute(self, context):
        scene = context.scene
        rows = [item for item in scene.gnm_markers if item.is_placed and item.use_for_fit]
        bones = {item.label: item.bone_empty.matrix_world.translation[:] for item in rows}
        result = _core_module('marker_audit').audit_landmarks(
            [item.label for item in rows], [_resolve_vertex(item) for item in rows],
            [item.target_empty.matrix_world.translation[:] for item in rows], bones)
        missing = [item.label for item in rows if _resolve_vertex(item) is None]
        if missing:
            result['errors'].append('Unmapped: ' + ', '.join(missing))
        lines = ['GNM landmark audit', f"Included, placed: {result['included_count']}",
                 f"Unique model vertices: {result['unique_vertex_count']}"]
        lines.extend('ERROR: ' + entry for entry in result['errors'])
        lines.extend('REVIEW: ' + entry for entry in result['warnings'])
        lines.append('Registry: 48 distinct labels and model vertices. Nasospinale/Acanthion candidates are 1.5 mm apart; review their distinct bone definitions. Proximity alone is not duplication.')
        text = bpy.data.texts.get('GNM_Landmark_Audit') or bpy.data.texts.new('GNM_Landmark_Audit')
        text.clear()
        text.write('\n'.join(lines))
        self.report({'WARNING'} if result['errors'] else {'INFO'},
                    f"Audit: {len(result['errors'])} errors, {len(result['warnings'])} proximity warnings. See GNM_Landmark_Audit")
        return {'FINISHED'}


class GNM_OT_export_csv(Operator):
    bl_idname = "gnm.export_csv"
    bl_label = "4. Export Final CSV"
    filepath: StringProperty(subtype="FILE_PATH", default="markers_v3.csv")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            _export_markers(context.scene, self.filepath)
        except (ValueError, OSError, ImportError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        context.scene.gnm_settings.ultim_export_csv = os.path.basename(self.filepath)
        context.scene.gnm_settings.ultim_export_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self.report({"INFO"}, "Export complete!")
        return {"FINISHED"}

def _progress_bar_text(placed: int, total: int, width: int = 20) -> str:
    """Bara de progres text (caractere Unicode), fara dependinte de widget-uri
    de UI mai noi care ar putea sa nu existe in toate versiunile de Blender."""
    if total == 0:
        return ""
    filled = round(width * placed / total)
    return "█" * filled + "░" * (width - filled)

class GNM_UL_markers(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text="", icon="CHECKMARK" if item.is_placed else "RADIOBUT_OFF")
        side_str = "[M]" if item.side == 0 else ("[R]" if item.side == -1 else "[L]")
        row.label(text=f"{side_str} {item.label}")
        row.prop(item, "use_for_fit", text="")
        row.prop(item, "tissue_depth_mm", text="mm")
        # V13: iconita de status a correspondentei GNM (manual > V12 > JSON).
        # Protejata cu try/except: nu trebuie sa crape lista daca modelul
        # live nu e incarcat.
        try:
            st_icon, st_txt = _gnm_live_row_status(item)
            sub = row.row(align=True)
            sub.enabled = False
            sub.label(text=st_txt, icon=st_icon)
        except Exception:
            pass

class GNM_PT_panel(Panel):
    bl_label = "GNM Scientific Markers"
    bl_idname = "GNM_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GNM Markers"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.gnm_settings

        layout.operator("gnm.import_setup", icon="IMPORT")
        layout.separator()

        box = layout.box()
        box.label(text="Marker Visual Sizes:")
        box.prop(settings, "marker_size_mm")
        box.prop(settings, "peg_thickness_mm")
        layout.separator()

        layout.prop(settings, "marker_set")
        layout.operator("gnm.init_markers", icon="ADD")
        layout.operator("gnm.apply_paper_tissues", icon="PRESET")
        layout.label(text="Table 2: normal female; SW Native American")
        layout.label(text="Case-study reference; review applicability")
        if not scene.gnm_markers:
            return

        layout.template_list("GNM_UL_markers", "", scene, "gnm_markers", scene, "gnm_marker_active_index")

        placed_count = sum(1 for m in scene.gnm_markers if m.is_placed)
        total_count = len(scene.gnm_markers)
        progress_row = layout.row()
        progress_row.label(text=f"{_progress_bar_text(placed_count, total_count)}  {placed_count}/{total_count}")

        row = layout.row(align=True)
        row.operator("gnm.place_marker", icon="RESTRICT_SELECT_OFF")
        row.operator("gnm.next_unplaced", icon="FRAME_NEXT", text="")

        layout.operator("gnm.recenter_on_plane", icon="OBJECT_ORIGIN")

        layout.separator()
        box2 = layout.box()
        box2.label(text="Fragment restoration (originals preserved)")
        box2.prop(settings, 'restoration_plane_object')
        box2.label(text="Reference object's local XY plane")
        box2.prop(settings, 'mandible_aligned')
        box2.prop(settings, 'restoration_tolerance_mm')
        row = box2.row(align=True)
        row.operator('gnm.region_add', icon='ADD')
        row.operator('gnm.region_remove', text='', icon='REMOVE')
        box2.template_list('GNM_UL_restoration_regions', '', scene, 'gnm_restoration_regions',
                           scene, 'gnm_restoration_active_index', rows=3)
        if scene.gnm_restoration_regions:
            region = scene.gnm_restoration_regions[scene.gnm_restoration_active_index]
            box2.prop(region, 'name')
            box2.prop(region, 'source_object')
            box2.prop(region, 'anatomy')
            box2.prop(region, 'action')
            if region.action == 'MIRROR':
                if region.source_object:
                    box2.prop_search(region, 'vertex_group', region.source_object, 'vertex_groups')
                box2.prop(region, 'donor_side')
                box2.prop(region, 'plane_object')
            box2.prop(region, 'notes')
        box2.prop(settings, 'aplica_materiale_distincte')
        row2 = box2.row(align=True)
        row2.operator('gnm.toggle_plane_preview', icon='MESH_PLANE', text='Plane')
        row2.operator('gnm.asymmetry_report', icon='TEXT', text='Asymmetry')
        box2.operator('gnm.mirror_reconstruct', icon='MOD_MIRROR')
        for line in textwrap.wrap(settings.restoration_status, width=48):
            box2.label(text=line)
        box2.label(text='Register every preserved fragment, including central bone')

        layout.separator()
        box3 = layout.box()
        box3.label(text="Documentation & Reproducibility:")
        box3.operator("gnm.session_report", icon="TEXT")
        box3.operator("gnm.capturi_standardizate", icon="CAMERA_DATA")

        layout.separator()
        layout.operator('gnm.audit_landmarks', icon='VIEWZOOM')
        layout.operator("gnm.export_csv", icon="EXPORT")
        if scene.gnm_markers:
            item = scene.gnm_markers[scene.gnm_marker_active_index]
            details = layout.box()
            details.prop(item, "use_for_fit")
            details.prop(item, "fit_weight")
            details.prop(item, "mapping_reviewed")
            details.prop(item, "bone_status")
            if item.side == 0 and item.label not in _MARKER_DATA.MANDIBULAR_LANDMARKS:
                details.prop(item, 'use_for_plane')
            details.prop(item, "marker_notes")
            details.prop(item, "tissue_source")
            hint = _MARKER_DATA.PLACEMENT_HINTS.get(item.label, "Review anatomical location and target direction.")
            for line in textwrap.wrap(hint, width=48):
                details.label(text=line)
            caveat = _core_module('paper_reference').CAVEATS.get(item.label)
            if caveat:
                for line in textwrap.wrap(caveat, width=48):
                    details.label(text=line, icon='INFO' if line == textwrap.wrap(caveat, width=48)[0] else 'NONE')
        layout.prop(settings, "cranial_modification")
        layout.prop(settings, "case_notes")
        box = layout.box()
        box.label(text="Offline fit (external Python)")
        box.prop(settings, "python_executable")
        box.operator("gnm.check_python", icon="CHECKMARK")
        for line in textwrap.wrap(settings.python_status, width=48):
            box.label(text=line)
        box.label(text="Windows: .venv / Scripts / python.exe")
        box.prop(settings, "case_directory")
        box.label(text='Lambda: conditional LOO' if scene.gnm_live.loo_auto
                       else 'Lambda: adaptive from included markers')
        box.operator("gnm.run_offline", icon="PLAY")
        box.operator("gnm.cancel_offline", icon="CANCEL")
        for line in textwrap.wrap(settings.offline_status, width=48):
            box.label(text=line)
        box.label(text="Fit residuals are not reconstruction accuracy")

        # V13: sectiunea de reconstructie live (definita mai jos in fisier).
        _draw_live_section(layout, context)


# =======================================================================
# SECTIUNEA V13 - RECONSTRUCTIE GNM LIVE (DOUA VIEWPORT-URI)
# =======================================================================
# Ipoteze documentate (cerute explicit pentru livrabil):
#
# 1. ORIENTARE/UNITATI. Modelul GNM Head v3.0 (gnm_head.npz) este in METRI,
#    cu +X = stanga anatomica, +Y = sus, +Z = anterior. cranio.backend il
#    converteste in milimetri; aici il incarcam direct in float32 (vezi
#    _load_gnm_model) cu aceeasi conversie (x1000), pentru a injumatati
#    memoria (basis ~54 MB in loc de ~108 MB) si varful de incarcare.
#    Craniul din scena Blender e in mm (V12 forteaza scale_length=0.001).
#    Fitul este complet frame-agnostic: Umeyama recupereaza rotatie+scala+
#    translatie intre spatiul modelului si world-ul craniului, deci NU
#    presupunem nicio orientare a craniului. Singura conventie cosmetica:
#    inainte de primul fit, template-ul GNM (Y-up) e rotit cu +90 deg pe X
#    ca sa apara "in picioare" intr-o lume Blender Z-up; dupa >=3 markeri,
#    transformarea estimata suprascrie complet matrix_world obiectului.
#
# 2. TINTA FITULUI. Ca si exportul CSV offline, fitul foloseste
#    target_empty (pozitia PE PIELE = os + adancimea tesutului de-a lungul
#    normalei), nu bone_empty. GNM Head este un model al suprafetei pielii.
#
# 3. SPLIT-UL. "Split orizontal" din specificatie este implementat ca
#    bpy.ops.screen.area_split(direction='VERTICAL'): linia de taiere este
#    verticala, deci cele doua panouri rezulta alaturate ORIZONTAL
#    (stanga/dreapta). Ambele viewport-uri arata ACEEASI scena (in Blender
#    scena e proprietate de window, deci doua scene in aceeasi fereastra nu
#    se poate); izolarea vizuala se face cu local-view per area:
#    stanga = toate obiectele scenei EXCEPTAND cele GNM-live, dreapta =
#    doar obiectele GNM-live. Butonul "Setup / Repara Layout" reconstruieste
#    idempotent ambele local-view-uri (util daca utilizatorul iese din
#    local view cu Numpad-/).
#
# 4. EXECUTION. Preview snapshots and numerical fits run serially on the
#    main-thread timer. Heavy previews can pause Blender; final fitting uses
#    the external process below. The numerical preview is not identical to
#    the offline pipeline when different options or regularisation are used.
#
# 5. CORRESPONDENCE. Manual vertex selection takes precedence over the
#    inherited V12 map, then landmark_vertex_map.json. These skin-vertex
#    candidates and confidence colours require independent anatomical review.
#
# 6. PRIORS. Preview lambda schedules and optional demographic priors are
#    inherited heuristics. Conditional fixed-pose LOO tunes regularisation;
#    it does not measure independent predictive accuracy. See docs/SCIENCE.md.
# -----------------------------------------------------------------------

GNM_LIVE_COLLECTION = "GNM_Live"
GNM_MESH_NAME = "GNM_HEAD_LIVE"
GNM_GHOST_PREFIX = "GNM_LM_"

# V13.6: ghost separat (cyan) pentru pronasale estimat prin constructia
# Gerasimov/Ullrich-Stephan - diagnostic informativ, calculat in worker din
# pozitiile PE OS ale markerilor nazali, nu influenteaza fitul.
GNM_GERASIMOV_NAME = "GNM_PRONASALE_GERASIMOV"
GNM_GERASIMOV_COLOR = (0.2, 0.9, 0.95, 0.7)   # cyan
_GERASIMOV_LABELS = ("Nasion", "Rhinion", "Acanthion",
                     "Piriform_Dr", "Piriform_St")
_PRONASALE_VID = 12296  # iBUG 30 = varful nasului (nu e in LABEL_TO_VERTEX)

# Correspondenta eticheta-addon -> cheie din landmark_vertex_map.json.
# Folosita DOAR pentru confidence/culori (vertexul vine din lantul de
# precedenta de mai sus). Quirk-uri comentate inline.
ADDON_TO_JSON_KEY = {
    "Nasion": "nasion",
    # V13.4: intrarea JSON "rhinion" (iBUG 29, vertex 12310) este rhinion-ul
    # craniometric real; "pronasale" (iBUG 30, 12296) ramane varful nasului.
    "Rhinion": "rhinion",
    # JSON 12333 (extrema geometrica, low) vs V12 12337 (verificat) -
    # castiga V12; JSON contribuie doar cu confidence.
    "Glabella": "glabella",
    "Pogonion": None,
    "Gnathion": "gnathion",
    # gonion_*_approx din JSON = vechile valori v11 (iBUG 0/16, langa
    # ureche), corectate anatomic in V12 -> vertexul V12 castiga.
    "Gonion_Dr": "gonion_right_approx",
    "Gonion_St": "gonion_left_approx",
    "Orbita_Dr_Ext": "exocanthion_right",
    "Orbita_St_Ext": "exocanthion_left",
    "Orbita_Dr_Int": "endocanthion_right",
    "Orbita_St_Int": "endocanthion_left",
    "Supraorbitale_Dr": None,
    "Supraorbitale_St": None,
    "Infraorbitale_Dr": None,
    "Infraorbitale_St": None,
    "Zygion_Dr": "zygion_right",
    "Zygion_St": "zygion_left",
    "Alare_Dr": "alare_right",
    "Alare_St": "alare_left",
    "Eurion_Dr": None,
    "Eurion_St": None,
    "Vertex_VarfCap": None,
    "Nasospinale_BazaNas": "subnasale",
    "Prosthion_BuzaSup": None,
    # V13.6: intrari JSON proprii (manual_anatomical_v13.6, medium).
    "Acanthion": "acanthion",
    "Piriform_Dr": "piriform_right",
    "Piriform_St": "piriform_left",
}


class _LiveState:
    """Stare globala a modulului live (singleton _LIVE).

    Tinuta la nivel de modul (nu in scena): modelul numpy supravietuieste
    schimbarii de fisier .blend, iar thread-ul/timerul se opresc curat la
    unregister / reload (F8).
    """

    def __init__(self):
        self.model = None          # FaceModelData (mu/basis float32, mm)
        self.label_to_vertex = None  # dict din cranio.backend (sau fallback)
        self.json_map = None       # dict parsat din landmark_vertex_map.json
        self.enabled = False       # modul live pornit/oprit
        self.worker = None         # legacy state slot; no Python thread is started
        self.stop_event = threading.Event()
        self.pending = None        # snapshot de fit (latest-wins)
        self.pending_lock = threading.Lock()
        self.result = None         # ultimul rezultat de fit gata de aplicat
        self.result_lock = threading.Lock()
        self.fingerprints = {}     # nume_scena -> fingerprint markeri
        self.cfg = {"lambda_base": 1.0, "lambda_min": 0.3,
                    "lambda_max": 1000.0, "max_iter": 8,
                    "loo_auto": False, "prior_weight": 1.0,
                    # V13.3: forta/geometria constrangerilor dense + clip.
                    "dense_strength": 1.0, "dense_nose_weight": 0.7,
                    "dense_max_rows": 1500, "clip_sigma": 3.0}
        self.last_c = None         # ultimii coeficienti (pt. picking)
        self.prior = None          # {"mean","scale"} npz demografic (sau None)
        self.loo_cache = {"key": None, "lam": None}
        # V13.2: aliniere ICP + constrangeri dense din craniu
        self.skull = None          # {"points","normals","tree","source","flipped"}
        self.dense_full = None     # (dense_idx, offsets, max_dists) scalp+fata
        self.dense_scalp = None    # idem, doar scalp
        self.dense_set = None      # cel activ (comutat de toggle-ul doar-scalp)
        self.flip = None           # auto-detect orientare fete GNM (la 1-a corespondenta)


_LIVE = _LiveState()

# Cache de importuri lenes din pachetul cranio (acelasi cod ca offline-ul).
_CRANIO = {}


def _repo_root_from_npz(npz_path):
    """Radacina repo-ului dedusa din calea npz:
    <root>/gnm/shape/data/versions/v3_0/gnm_head.npz"""
    return os.path.abspath(os.path.join(
        os.path.dirname(npz_path), "..", "..", "..", "..", ".."))



def _ensure_cranio(npz_path):
    try:
        optimize = _core_module("optimize")
        geometry = _core_module("geometry")
        landmarks = _core_module("landmarks")
        backend = _core_module("backend")
        _CRANIO.update({
            "fit_identity": optimize.fit_identity, "LossConfig": optimize.LossConfig,
            "weighted_umeyama": optimize.weighted_umeyama,
            "CONFIDENCE_WEIGHTS": landmarks.CONFIDENCE_WEIGHTS,
            "DEFAULT_CONFIDENCE": landmarks.DEFAULT_CONFIDENCE,
            "LABEL_TO_VERTEX": backend.GNMBackend().landmark_vertex_map,
        })
        for key in ("build_scalp_mask", "build_face_dense_regions", "compute_vertex_normals", "gerasimov_pronasale"):
            _CRANIO[key] = getattr(geometry, key)
        return True, ""
    except ImportError as exc:
        return False, f"Install the complete gnm_cranio ZIP: {exc}"


def _load_gnm_model(npz_path):
    digest = _core_module("validation").sha256_file(npz_path)
    if digest != _core_module("backend.gnm_backend").OFFICIAL_V3_SHA256:
        raise ValueError("This add-on's built-in landmark map requires the reviewed GNM Head v3 asset; run gnm-doctor")
    return _core_module("backend").GNMBackend(npz_path).load(dtype=np.float32)
def _label_to_vertex_map():
    """Inherited V12 label-to-skin-vertex candidates; review anatomically.

    Prefera LABEL_TO_VERTEX din cranio.backend (sursa unica de adevar);
    fallback: primul element al liniilor LANDMARKS din addon (acelasi tabel
    V12, deci fara duplicare de date)."""
    if _CRANIO.get("LABEL_TO_VERTEX"):
        return _CRANIO["LABEL_TO_VERTEX"]
    return {lbl: vid for vid, lbl, _d, _s, _e in LANDMARKS}


def _marker_item(scene, label):
    for m in scene.gnm_markers:
        if m.label == label:
            return m
    return None


def _resolve_vertex(item):
    """Vertexul GNM folosit pentru un marker, sau None daca nu exista niciun
    candidat (landmark fara correspondenta - afisat ca 'needs manual GNM-side
    picking' si exclus din fit pana la un picking manual)."""
    if item.gnm_vertex_override >= 0:
        return int(item.gnm_vertex_override)
    vid = _label_to_vertex_map().get(item.label)
    if vid is not None:
        return int(vid)
    jk = ADDON_TO_JSON_KEY.get(item.label)
    entry = (_LIVE.json_map or {}).get(jk) if jk else None
    if entry and "vertex_index" in entry:
        return int(entry["vertex_index"])
    return None


def _json_confidence(label):
    """Confidence-ul din JSON pentru eticheta data (sau None)."""
    jk = ADDON_TO_JSON_KEY.get(label)
    entry = (_LIVE.json_map or {}).get(jk) if jk else None
    return entry.get("confidence") if entry else None


def _gnm_live_row_status(item):
    """(icon, text) pentru coloana de status GNM din UIList."""
    if item.gnm_vertex_override >= 0:
        return "PINNED", "M"
    if _resolve_vertex(item) is None:
        return "ERROR", "!"
    if not item.mapping_reviewed or (_json_confidence(item.label) or "") == "low":
        return "QUESTION", "~"
    return "LINKED", ""


def _weight_of(label, item=None):
    """Ponderea de incredere a landmarkului (aceeasi ca in pipeline-ul
    offline: cranio.landmarks.CONFIDENCE_WEIGHTS)."""
    if item is not None and item.fit_weight > 0:
        return float(item.fit_weight)
    return float(_MARKER_DATA.CONFIDENCE_WEIGHTS.get(label, _MARKER_DATA.DEFAULT_CONFIDENCE))


# -----------------------------------------------------------------------
# V13: obiecte scena (colectie, mesh GNM, ghost-uri)
# -----------------------------------------------------------------------
def _gnm_collection():
    coll = bpy.data.collections.get(GNM_LIVE_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(GNM_LIVE_COLLECTION)
        bpy.context.scene.collection.children.link(coll)
    return coll


def _gnm_live_objects():
    """Setul obiectelor vizibile doar in viewport-ul drept (mesh + ghost)."""
    objs = set()
    obj = bpy.data.objects.get(GNM_MESH_NAME)
    if obj is not None:
        objs.add(obj)
    for o in bpy.data.objects:
        if o.name.startswith(GNM_GHOST_PREFIX):
            objs.add(o)
    # V13.6 fix: ghost-ul cyan Gerasimov nu are prefixul GNM_LM_ (nu e
    # landmark de fit), dar apartine tot viewport-ului drept - altfel nu
    # intra in local-view la setup/sync/overlay si parea "inexistent" live.
    ger = bpy.data.objects.get(GNM_GERASIMOV_NAME)
    if ger is not None:
        objs.add(ger)
    return objs


def _ensure_gnm_mesh_object(context):
    """Creeaza (o singura data) obiectul mesh GNM.

    Vertecsii sunt tinuti in SPATIUL MODELULUI (mm); transformarea de
    similaritate estimata de fit se aplica prin obj.matrix_world, deci la
    fiecare update rescriem doar pozitiile (foreach_set), nu si topologia.
    """
    model = _LIVE.model
    obj = bpy.data.objects.get(GNM_MESH_NAME)
    if obj is not None:
        # La re-incarcare: rescriem template-ul si resetam poza cosmetica
        # (un eventual fit vechi nu mai corespunde noului model).
        obj.data.vertices.foreach_set("co", model.mu.ravel())
        obj.data.update()
        obj.matrix_world = Matrix.Rotation(np.deg2rad(90.0), 4, 'X')
        return obj
    me = bpy.data.meshes.new(GNM_MESH_NAME + "_MESH")
    n = model.vertex_count
    me.vertices.add(n)
    me.vertices.foreach_set("co", model.mu.ravel())
    tris = model.triangles
    nloops = int(tris.size)
    me.loops.add(nloops)
    me.loops.foreach_set("vertex_index", tris.ravel())
    nf = int(tris.shape[0])
    me.polygons.add(nf)
    me.polygons.foreach_set(
        "loop_start", np.arange(0, nloops, 3, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(nf, 3, dtype=np.int32))
    me.update()
    me.validate()
    me.polygons.foreach_set("use_smooth", np.ones(nf, dtype=np.bool_))

    obj = bpy.data.objects.new(GNM_MESH_NAME, me)
    # Cosmetic pre-fit: modelul e Y-up, lumea Blender Z-up (vezi ipoteza 1).
    obj.rotation_euler = (np.deg2rad(90.0), 0.0, 0.0)
    obj.color = (0.76, 0.57, 0.42, 1.0)
    _gnm_collection().objects.link(obj)
    mat = _get_or_create_material("GNM_Piele_Live", (0.76, 0.57, 0.42, 1.0))
    me.materials.append(mat)
    return obj


def _ghost_color(item):
    """Culoarea ghost-ului dupa sursa/confidence (vezi legenda din panou)."""
    if item is not None and not item.use_for_fit:
        return (0.5, 0.5, 0.5, 0.6)
    if item is not None and item.gnm_vertex_override >= 0:
        return (0.75, 0.35, 0.9, 0.6)   # picking manual: mov
    if item is not None and _resolve_vertex(item) is None:
        return (0.95, 0.15, 0.15, 0.6)  # lipsa correspondenta: rosu
    if item is not None and (not item.mapping_reviewed or (_json_confidence(item.label) or "") == "low"):
        return (1.0, 0.55, 0.1, 0.6)    # confidence low in JSON: portocaliu
    return (0.25, 0.85, 0.35, 0.6)      # V12 / JSON medium-high: verde


def _refresh_marker_objects(scene):
    """Coloreaza obiectele markerilor plasati (os/piele/bat) cu aceeasi
    schema de culori ca ghost-urile (vezi legenda din panou).

    Spre deosebire de ghost-uri (care se ascund cand landmark-ul nu are
    correspondenta GNM), batul ramane vizibil si in cazul rosu - el sta
    pe craniu (viewport-ul stang), nu pe capul GNM."""
    for item in scene.gnm_markers:
        col = _ghost_color(item)
        for obj in (item.bone_empty, item.target_empty, item.peg_object):
            if obj is not None:
                obj.color = col


def _refresh_ghosts(scene):
    """Sincronizeaza culorile/vizibilitatea ghost-urilor cu starea curenta.

    Nota: empty-urile folosesc obj.color (vizibil in Solid cu Color=Object,
    setat de operatorul de setup); alpha-ul e informativ in acest mod.
    """
    show = scene.gnm_live.show_ghosts
    size = scene.gnm_settings.marker_size_mm * 1.3
    for _vid, lbl, _d, _s, _e in LANDMARKS:
        obj = bpy.data.objects.get(GNM_GHOST_PREFIX + lbl)
        if obj is None:
            continue
        item = _marker_item(scene, lbl)
        obj.color = _ghost_color(item)
        unmapped = (item is None or _resolve_vertex(item) is None)
        obj.hide_set((not show) or unmapped)
        obj.empty_display_size = size
    # Betele/empties-urile markerilor (viewport-ul stang) urmeaza aceeasi
    # schema de culori.
    _refresh_marker_objects(scene)


def _ensure_ghosts(context):
    """Creeaza ghost-urile (cate unul per eticheta V12) si le initializeaza
    la pozitiile din template (prin matrix_world curent al mesh-ului GNM)."""
    scene = context.scene
    coll = _gnm_collection()
    mesh_obj = bpy.data.objects.get(GNM_MESH_NAME)
    m_world = (np.array(mesh_obj.matrix_world, dtype=np.float64)
               if mesh_obj is not None else np.eye(4))
    model = _LIVE.model
    for item in scene.gnm_markers:
        lbl = item.label
        name = GNM_GHOST_PREFIX + lbl
        obj = bpy.data.objects.get(name)
        if obj is None:
            obj = bpy.data.objects.new(name, None)
            obj.empty_display_type = 'SPHERE'
            coll.objects.link(obj)
        obj.show_in_front = True
        obj.hide_render = True
        item = _marker_item(scene, lbl)
        vid = (_resolve_vertex(item) if item is not None
               else _label_to_vertex_map().get(lbl))
        if vid is not None and model is not None:
            p = model.mu[vid].astype(np.float64)
            obj.location = m_world[:3, :3] @ p + m_world[:3, 3]
        elif mesh_obj is not None:
            obj.location = mesh_obj.matrix_world.translation
    # V13.6: ghost-ul cyan Gerasimov - separat de prefixul GNM_LM_ (nu e
    # landmark de fit), ascuns pana exista o estimare valida din worker.
    obj = bpy.data.objects.get(GNM_GERASIMOV_NAME)
    if obj is None:
        obj = bpy.data.objects.new(GNM_GERASIMOV_NAME, None)
        obj.empty_display_type = 'SPHERE'
        obj.color = GNM_GERASIMOV_COLOR
        coll.objects.link(obj)
    obj.show_in_front = True
    obj.hide_render = True
    obj.empty_display_size = scene.gnm_settings.marker_size_mm * 1.6
    obj.hide_set(True)
    _refresh_ghosts(scene)


def _update_ghosts_from_fit(scene, v_model, scale, rot, trans):
    """Muta ghost-urile la pozitiile landmark-urilor GNM dupa un fit."""
    idx_labels = []
    idxs = []
    for item in scene.gnm_markers:
        vid = _resolve_vertex(item)
        if vid is None:
            continue
        idx_labels.append(item.label)
        idxs.append(vid)
    if not idxs:
        return
    vw = scale * (v_model[np.asarray(idxs)] @ rot.T) + trans
    for k, lbl in enumerate(idx_labels):
        obj = bpy.data.objects.get(GNM_GHOST_PREFIX + lbl)
        if obj is not None:
            obj.location = vw[k]


def _update_gerasimov_ghost(scene, ger):
    """Pozitioneaza/ascunde ghost-ul cyan Gerasimov (V13.6). MAIN thread.

    ger = res["gerasimov"] din worker (None = nicio informatie -> ascuns).
    Respecta toggle-ul global show_ghosts."""
    obj = bpy.data.objects.get(GNM_GERASIMOV_NAME)
    if obj is None:
        return
    ok = bool(ger) and ger.get("ok") and ger.get("xyz") is not None
    if ok:
        obj.location = ger["xyz"]
    obj.hide_set((not scene.gnm_live.show_ghosts) or not ok)


# -----------------------------------------------------------------------
# V13: raycast filtrat (craniul sta "in interiorul" capului GNM)
# -----------------------------------------------------------------------
def _record_marker_surface(item, hit_object):
    inferred = hit_object is not None and hit_object.get('gnm_reconstructed_via_mirroring')
    item.bone_status = 'reconstructed' if inferred else 'observed'
    if item.bone_empty is not None and hit_object is not None:
        item.bone_empty['gnm_bone_source'] = hit_object.name
    if inferred:
        item.use_for_fit = False
        item.use_for_plane = False
        item.marker_notes = 'Placed on inferred bone; review before including in fit. ' + item.marker_notes


def _ray_cast_skull(scene, depsgraph, origin, direction, max_hops=8, return_object=False):
    """scene.ray_cast care ignora obiectele GNM-live.

    Capul GNM (piele) invaluie craniul in aceeasi lume; fara filtrare,
    clickul de plasare a markerilor ar lovi mereu mesh-ul GNM. Strategia:
    ray-marching - dupa fiecare hit pe un obiect GNM, avansam originea cu
    0.05 mm peste punctul de impact si relansam (max ~8 hopuri).
    Returneaza (result, location, normal) ca scene.ray_cast.
    """
    excluded = _gnm_live_objects()
    excluded.update(row.plane_object for row in scene.gnm_restoration_regions if row.plane_object)
    if scene.gnm_settings.restoration_plane_object:
        excluded.add(scene.gnm_settings.restoration_plane_object)
    preview = bpy.data.objects.get('GNM_PLAN_PREVIEW')
    if preview:
        excluded.add(preview)
    o = origin.copy()
    for _ in range(max_hops):
        result, location, normal, _i, hit_obj, _m = scene.ray_cast(
            depsgraph, o, direction)
        if not result:
            return (False, None, None, None) if return_object else (False, None, None)
        if hit_obj not in excluded:
            return (True, location, normal, hit_obj) if return_object else (True, location, normal)
        o = location + direction * 0.05
    return (False, None, None, None) if return_object else (False, None, None)


# -----------------------------------------------------------------------
# SECTIUNEA V13.2 - ALINIERE ICP + DEFORMARE GENERALA DIN CRANIU
# -----------------------------------------------------------------------
# Ipoteza 9 (documentata, ca si celelalte, in antetul fisierului):
#   * ICP multi-start presupune craniul aproximativ vertical (Z-up) dupa
#     importul V12; ipotezele sunt rotatii de yaw (0/90/180/270) aplicate
#     peste rotatia cosmetica X+90 a template-ului. Cu >=3 markeri plasati,
#     fitul pe markeri ofera o initializare mai buna decat multi-startul.
#   * Corespondentele dense se recalculeaza la nivel de SNAPSHOT (outer
#     ICP la ~rata timerului), nu la fiecare iteratie interna ca offline -
#     convergenta vine progresiv, in 3-10 update-uri vizibile.
#   * mathutils KDTree queries and previews run on Blender's main thread.
#   * Deformarea generala trece prin beta (spatiul GNM + clip +-3 sigma +
#     prior optional). Remaining in this parameterisation does not guarantee
#     anatomical validity or skull containment.
#
# V13.3 (calitate fitting: acoperire + nas):
#   * Randurile dense NU mai sunt down-ponderate Huber (huber_rows=
#     n_markeri in fit_identity): punctele cele mai departate de os -
#     exact cele care trebuie trase cel mai tare - isi pastreaza ponderea
#     (paritate cu offline, unde dense intra cu pondere fixa).
#   * Jobul ICP+deformare ruleaza cu schedule de respingere 2.0 -> 1.0:
#     zonele departate nu mai sunt respinse definitiv la inceput.
#   * Sub-esantionarea randurilor foloseste buget 50/50 fata/scalp:
#     scalpul (~73% din vertecsi) nu mai sufoaca regiunile faciale.
#   * Puntea nazala este constransa pe PUNTEA OSOASA (fix in
#     cranio.geometry: vechiul patch era centrat pe pronasale) si primeste
#     pondere reglabila (dense_nose_weight, implicit 0.7 = soft prior).
#   * Controale noi in UI: dense_strength, dense_nose_weight,
#     dense_max_rows, clip_sigma; diagnostice: keep-rate + distanta pe
#     regiunea nazala si RMS pe landmark-urile nazale.

# Landmark-urile nazale (V13.3): reziduurile lor sunt raportate separat
# (RMS nazal), ca diagnostic dedicat calitatii reconstructiei nasului.
_NASAL_LABELS = frozenset(
    {"Nasion", "Rhinion", "Nasospinale_BazaNas", "Alare_Dr", "Alare_St"})


def _nasal_rms(labels, res_m):
    """RMS doar pe landmark-urile nazale prezente (sau None)."""
    ids = [i for i, lb in enumerate(labels) if lb in _NASAL_LABELS]
    if not ids:
        return None
    return float(np.mean(np.asarray(res_m)[ids]))


def _build_dense_set(model, scalp_only):
    """Setul de vertecsi GNM constransi de craniu + offseturi (mm).

    Dedup cu regiunile faciale PRIMELE (offseturi mai specifice) - aceeasi
    conventie ca in cranio.pipeline: un vertex scalp ∩ zigomatic apare o
    singura data. Offset scalp = 5.0 mm (= --scalp-offset-mm offline).
    Returneaza (dense_idx, offsets, max_dists, region_of), unde region_of
    este numele regiunii dense per vertex (V13.3: ponderi per regiune,
    buget de randuri fata/scalp si diagnostice per regiune)."""
    vg, vgn = model.vertex_groups, model.vertex_group_names
    scalp_idx = _CRANIO["build_scalp_mask"](model.mu, vg, vgn)
    face_regions = ([] if scalp_only else
                    _CRANIO["build_face_dense_regions"](model.mu, vg, vgn))
    region_idx = [r[1] for r in face_regions] + [scalp_idx]
    region_offs = [np.full(len(r[1]), r[2], dtype=np.float64)
                   for r in face_regions]
    region_offs += [np.full(len(scalp_idx), 5.0, dtype=np.float64)]
    region_names = [r[0] for r in face_regions] + ["scalp"]
    dense_idx_all = np.concatenate(region_idx)
    offsets_all = np.concatenate(region_offs)
    region_of_all = np.repeat(np.array(region_names, dtype=object),
                              [len(x) for x in region_idx])
    dense_idx, first = np.unique(dense_idx_all, return_index=True)
    offsets = offsets_all[first]
    region_of = region_of_all[first]
    # Respingere per-vertex: peste offset+12 mm e sigur o zona lipsa
    # (craniu partial, ex. mandibula absenta) - aceeasi regula ca offline.
    return dense_idx, offsets, offsets + 12.0, region_of


def _balanced_region_sel(regs, max_rows):
    """Selectie determinista a randurilor dense cu buget 50/50 fata/scalp.

    Scalpul domina numeric setul dens (~73% din vertecsi); lasata libera,
    sub-esantionarea globala trimite ~3/4 din randuri pe bolta, care trage
    scala/poza spre craniu si lasa mijlocul fetei sub-constrans (osul
    zigomatic/nazal iese prin piele). Bugetul egal pastreaza toate
    regiunile faciale in fit; bugetul nefolosit de un grup mic trece la
    celalalt. Returneaza indici sortati (linspace per grup)."""
    idx = np.arange(len(regs))
    is_scalp = regs == "scalp"
    groups = [idx[~is_scalp], idx[is_scalp]]          # fata, scalp
    budgets = [max_rows // 2, max_rows - max_rows // 2]
    take = [min(len(g), b) for g, b in zip(groups, budgets)]
    slack = sum(b - t for b, t in zip(budgets, take))
    for i, g in enumerate(groups):
        if slack <= 0:
            break
        if take[i] == budgets[i] and len(g) > take[i]:
            extra = min(len(g) - take[i], slack)
            take[i] += extra
            slack -= extra
    sels = []
    for g, n_take in zip(groups, take):
        if len(g) <= n_take:
            sels.append(g)
        elif n_take > 0:
            sels.append(
                g[np.linspace(0, len(g) - 1, n_take).round().astype(np.int64)])
    return np.sort(np.concatenate(sels)) if sels else np.zeros(0, np.int64)


def _refresh_dense_set(scalp_only):
    """Alege setul dens activ (complet / doar-scalp), calculandu-l lenes."""
    if _LIVE.model is None:
        return
    if _LIVE.dense_full is None:
        _LIVE.dense_full = _build_dense_set(_LIVE.model, scalp_only=False)
        _LIVE.dense_scalp = _build_dense_set(_LIVE.model, scalp_only=True)
    _LIVE.dense_set = _LIVE.dense_scalp if scalp_only else _LIVE.dense_full


def _signed_volume(mu, triangles):
    """Volumul semnat al mesh-ului (pozitiv = winding spre exterior, in
    conventia cross(v1-v0, v2-v0)). Determinist si independent de poza -
    spre deosebire de detectia orientarii din normale (nesigura la o poza
    initiala proasta). Masurat pe GNM v3.0: +0.0071 m^3 -> flip=False."""
    tri = triangles.astype(np.int64)
    v = mu.astype(np.float64)
    v0, v1, v2 = v[tri[:, 0]], v[tri[:, 1]], v[tri[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


def _dense_rows(v_world, max_rows, dist_scale=1.0, use_normal=True,
                region_balance=False, min_dot=0.2):
    """Corespondente dense vertecsi-constransi -> craniu, cu respingere.

    Port fidel al lui cranio.geometry.dense_correspondences, cu adaptari
    Blender: KD-ul este mathutils.kdtree (interogat per punct, read-only);
    normalele modelului pe v_world curent; pragul de distanta este scalat
    cu dist_scale (ICP il lasa sa scada 4x -> 1x, largind bazinul de
    atractie la poza initiala proasta); testul de normala se poate relaxa
    cu min_dot < 0.2 (V13.5: in faza larga a jobului se resping doar
    potrivirile pe fata OPUSA a osului, dot < -0.2, nu si cele tangentiale).
    Cu region_balance=True (fituri, NU ICP) sub-esantionarea foloseste
    bugetul 50/50 fata/scalp (vezi _balanced_region_sel).
    Returneaza (sidx, targets_world, n_keep, mean_dist, info), unde
    info["row_mult"] = multiplicatorii de pondere pe rand (puntea nazala
    primeste dense_nose_weight din cfg - soft prior, V13.3),
    info["dists"] = distantele la os ale randurilor returnate (post
    sub-esantionare; pentru trim-ul V13.5), iar info["region_stats"] =
    {nume: (pastrate, total, distanta medie)} pentru diagnosticele din UI."""
    sk = _LIVE.skull
    dense_idx, offsets, max_dists, region_of = _LIVE.dense_set
    pts = v_world[dense_idx]
    kd = sk["tree"]
    n = len(pts)
    dists = np.empty(n, dtype=np.float64)
    nn = np.empty(n, dtype=np.int64)
    find = kd.find
    for i in range(n):
        _co, idx, d = find(pts[i])
        nn[i] = idx
        dists[i] = d
    closest = sk["points"][nn]
    n_skull = sk["normals"][nn]
    keep = dists < (max_dists * dist_scale)
    if use_normal:
        n_model = _CRANIO["compute_vertex_normals"](
            v_world, _LIVE.model.triangles, flip=bool(_LIVE.flip))[dense_idx]
        dots = np.einsum("ij,ij->i", n_model, n_skull)
        keep &= dots > min_dot
    # Plasa de siguranta: daca aproape nimic nu trece, probabil normalele
    # craniului sunt INTOARSE - le inversam o singura data si reincercam.
    if (not sk.get("flipped")) and keep.sum() < 0.1 * len(dists):
        sk["normals"] = -sk["normals"]
        sk["flipped"] = True
        return _dense_rows(v_world, max_rows, dist_scale=dist_scale,
                           use_normal=use_normal,
                           region_balance=region_balance, min_dot=min_dot)

    sidx = dense_idx[keep]
    targets_w = closest[keep] + offsets[keep, None] * n_skull[keep]
    regs = region_of[keep]
    mean_dist = float(dists[keep].mean()) if keep.any() else float("nan")
    # Statistici per regiune (diagnostice; ex. keep-rate-ul nazal din UI).
    d_keep = dists[keep]
    rstats = {}
    for name in np.unique(region_of):
        kp = regs == name
        rstats[name] = (int(kp.sum()), int((region_of == name).sum()),
                        float(d_keep[kp].mean()) if kp.any() else float("nan"))
    # Sub-esantionare determinista pentru viteza (max ~max_rows randuri).
    if len(sidx) > max_rows:
        sel = (_balanced_region_sel(regs, max_rows) if region_balance
               else np.linspace(0, len(sidx) - 1, max_rows).round()
               .astype(np.int64))
        sidx = sidx[sel]
        targets_w = targets_w[sel]
        regs = regs[sel]
        d_keep = d_keep[sel]
    nose_w = float(_LIVE.cfg.get("dense_nose_weight", 0.7))
    row_mult = np.where(regs == "punte_nazala", nose_w, 1.0)
    info = {"row_mult": row_mult, "region_stats": rstats, "dists": d_keep}
    return sidx, targets_w, int(keep.sum()), mean_dist, info


def _multi_start_icp(n_coarse=8, n_refine=20, max_rows=2000):
    """ICP multi-start (turneu): aliniaza template-ul NEDEFORMAT pe craniu.

    Ipoteze: yaw 0/90/180/270 peste rotatia cosmetica X+90; scala initiala
    = raportul diagonalelor bbox pe seturi CONSISTENTE (tot mesh-ul, nu doar
    regiunea densa - altfel initializarea porneste prea departe); translatia
    = centroizi. Faza 1: n_coarse iteratii pe fiecare ipoteza, cu raza de
    acceptare descrescatoare 4x -> 1.5x (bazin larg la inceput; testul de
    normala activ doar la faza fina). Faza 2: rafinare n_refine iteratii la
    raza 1x doar pe castigator (bolta e aproape sferica -> convergenta yaw
    lenta, are nevoie de iteratii suplimentare). Scorarea: distanta medie /
    rata de acoperire (ipotezele degenerate, cu putine corespondente bune
    intamplator, sunt penalizate; sub 15% acoperire = esuata).
    Returneaza (s, R, t, cost, n_keep, nume_ipoteza) sau None."""
    model = _LIVE.model
    sk = _LIVE.skull
    dense_idx, _offs, _md, _ro = _LIVE.dense_set
    mu = model.mu.astype(np.float64)
    head_c = mu.mean(axis=0)
    skull_c = sk["points"].mean(axis=0)
    d_skull = sk["points"].max(axis=0) - sk["points"].min(axis=0)
    d_head = mu.max(axis=0) - mu.min(axis=0)
    s0 = float(np.linalg.norm(d_skull) / max(np.linalg.norm(d_head), 1e-9))
    rx90 = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
    n_total = max(len(dense_idx), 1)

    def _run(R0, s_start, t_start, n_iter, f_hi, f_lo):
        s, R, t = s_start, R0, t_start
        cost, n_keep, prev, stall = np.inf, 0, None, 0
        for it in range(n_iter):
            vw = s * (mu @ R.T) + t
            f = max(f_lo, f_hi - it * ((f_hi - f_lo) / max(n_iter - 1, 1)))
            try:
                sidx, dt_w, nk, md, _di = _dense_rows(
                    vw, max_rows, dist_scale=f, use_normal=(f <= 2.0))
            except Exception:
                break
            if len(sidx) < 50:
                break
            s_prev, R_prev, t_prev = s, R, t
            try:
                s, R, t = _CRANIO["weighted_umeyama"](
                    mu[sidx], dt_w, np.ones(len(sidx)))
            except ValueError:
                break  # reflexie ceruta - ipoteza moarta
            cost, n_keep = md, nk
            # Oprire pe DELTA DE TRANSFORMARE (nu pe cost: suprafata de cost
            # e plata pe bolta aproape-sferica - unghiul mai progreseaza mult
            # dupa ce distanta medie plafoneaza).
            if prev is not None and f <= 1.05:
                d_ang = np.degrees(np.arccos(min(max(
                    (np.trace(R @ R_prev.T) - 1.0) / 2.0, -1.0), 1.0)))
                d_t = float(np.linalg.norm(t - t_prev))
                if d_ang < 0.1 and d_t < 0.5 and abs(s - s_prev) < 1e-4:
                    stall += 1
                    if stall >= 2:
                        break
                else:
                    stall = 0
            prev = (s, R, t)
        return s, R, t, cost, n_keep

    best = None
    for k in range(4):
        a = np.deg2rad(90.0 * k)
        rz = np.array([[np.cos(a), -np.sin(a), 0.0],
                       [np.sin(a), np.cos(a), 0.0], [0.0, 0.0, 1.0]])
        R0 = rz @ rx90
        t0 = skull_c - s0 * (R0 @ head_c)
        s, R, t, cost, nk = _run(R0, s0, t0, n_coarse, 4.0, 1.5)
        keep_rate = nk / n_total
        score = cost / max(keep_rate, 1e-6)
        if (np.isfinite(cost) and keep_rate >= 0.15
                and (best is None or score < best[3])):
            best = (s, R, t, float(cost), int(nk), f"yaw{90 * k}",
                    float(score))
    if best is None:
        return None
    # Faza 2: rafinare lunga pe castigator (daca nu degrada, o pastram).
    s, R, t, cost, nk = _run(best[1], best[0], best[2], n_refine, 1.0, 1.0)
    if nk >= 50 and cost <= best[3] * 1.5:
        return (s, R, t, float(cost), int(nk), best[5])
    return best[:6]


def _push_worker_result(res):
    """Scrie un rezultat intermediar pe canalul normal (latest-wins)."""
    with _LIVE.result_lock:
        _LIVE.result = res


def _icp_deform_job(snap):
    """Serialized preview job: ICP multi-start and several dense fits.

    Nu atinge bpy. Impinge rezultate intermediare pe canalul normal (vezi
    deformarea progresiv in viewport), apoi un rezultat final 'icp_done'.
    """
    model = _LIVE.model
    best = _multi_start_icp()
    if best is None:
        return {"status": "error",
                "error": "ICP failed: too few valid correspondences "
                         "(check skull preparation and normals)."}
    s, R, t, cost, n_keep, hyp = best
    c = np.zeros(model.identity_dim)
    _LIVE.last_c = c
    v0 = np.ascontiguousarray(model.mu, dtype=np.float32)
    _push_worker_result({
        "status": "ok", "n": 0, "scale": float(s), "rot": R, "trans": t,
        "v_model": v0, "rms": 0.0, "max_res": 0.0, "max_label": "-",
        "lam": 0.0, "lam_src": "icp", "beta_norm": 0.0, "n_clip": 0,
        "note": f"ICP {hyp}: cost {cost:.1f} mm, {n_keep} correspondences",
    })
    # Auto-dense scurt: fituri consecutive cu corespondente reimprospatate.
    n_markers = len(snap["labels"])
    lam, lam_src = _live_lambda(n_markers, snap)
    prior_kwargs = {}
    if _LIVE.prior is not None:
        prior_kwargs = {
            "prior_mean": _LIVE.prior["mean"],
            "prior_scale": _LIVE.prior["scale"],
            "prior_weight": float(_LIVE.cfg.get("prior_weight", 1.0)),
        }
    max_rows = int(_LIVE.cfg.get("dense_max_rows", 1500))
    strength = float(_LIVE.cfg.get("dense_strength", 1.0))
    clip_sigma = float(_LIVE.cfg.get("clip_sigma", 3.0))
    final = None
    n_outer = 6
    for k in range(n_outer):
        v = model.generate(c.astype(np.float32)).astype(np.float64)
        vw = s * (v @ R.T) + t
        # V13.3: schedule de respingere 2.0 -> 1.0 peste iteratii. La
        # inceput (cap inca departe de craniu) pragul largit pastreaza in
        # set si zonele departate - altfel ele erau respinse DEFINITIV si
        # ramaneau neacoperite (craniul iesea prin piele); spre final
        # pragul revine la regula stricta (zonele lipsa reale, ex.
        # mandibula absenta, sunt din nou respinse).
        # V13.5: testul de normala ramane ACTIV tot timpul, dar relaxat
        # (min_dot=-0.2): respinge doar potrivirile pe fata OPUSA a osului
        # (tabla interna, marginea aperturii), nu si cele tangentiale.
        f = 2.0 - k * (1.0 / max(n_outer - 1, 1))
        sidx, dt_w, nkeep, md, dinfo = _dense_rows(
            vw, max_rows, dist_scale=f, use_normal=True, min_dot=-0.2,
            region_balance=True)
        if len(sidx) < 10:
            break
        # V13.5: trim 10% - elimina cele mai DEPARTATE corespondente la
        # fiecare iteratie. Coada distributiei e dominata de potriviri
        # gresite (tabla interna, margini de apertura, muchii), care -
        # fara frana Huber pe dense (V13.3) - trageau beta in saturatie
        # ("fata exagerata"); fara ele, setul ramas converge la o
        # morfologie plauzibila cu acoperire MAI BUNA (masurat pe
        # v13-test: clip 30->23, expunere 4.8->2.0%).
        row_mult = dinfo["row_mult"]
        if len(sidx) > 20:
            thr = np.quantile(dinfo["dists"], 0.90)
            keep2 = dinfo["dists"] <= thr
            sidx = sidx[keep2]
            dt_w = dt_w[keep2]
            row_mult = row_mult[keep2]
        wm = snap["weights"]
        # V13.3: multiplicatorul de putere din UI (dense_strength) si
        # ponderile per regiune (puntea nazala = soft prior).
        wd = strength * 0.5 * (float(wm.mean()) if len(wm) else 0.7)
        verts = np.concatenate([snap["verts"], sidx])
        tg = np.concatenate([snap["targets"], dt_w])
        ws = np.concatenate([wm, wd * row_mult])
        try:
            c_new, s, R, t, lam_u, _i, res = _CRANIO["fit_identity"](
                model.mu, model.basis, verts, tg, ws, lam=lam,
                max_iter=int(_LIVE.cfg.get("max_iter", 8)), tol=1e-4,
                loss_cfg=_CRANIO["LossConfig"](clip_sigma=clip_sigma),
                huber_rows=n_markers,
                pose_rows=n_markers if n_markers >= 3 else None,
                **prior_kwargs)
        except ValueError as exc:
            # Reflexie ceruta de un set de corespondente prost (ex. ICP cazut
            # in minim local) - pastram ultima stare buna si oprim jobul.
            if final is None:
                return {"status": "error",
                        "error": f"Dense fit failed ({exc})"}
            break
        dc = float(np.linalg.norm(c_new - c))
        c = c_new
        _LIVE.last_c = c
        v_model = np.ascontiguousarray(
            model.generate(c.astype(np.float32)), dtype=np.float32)
        res_m = res[:n_markers] if n_markers else np.array([np.nan])
        final = {
            "status": "ok", "n": n_markers,
            "scale": float(s), "rot": R, "trans": t, "v_model": v_model,
            "c": c,
            "rms": float(np.sqrt(np.nanmean(res_m ** 2))) if n_markers else 0.0,
            "max_res": float(np.nanmax(res_m)) if n_markers else 0.0,
            "max_label": (snap["labels"][int(np.nanargmax(res_m))]
                          if n_markers else "-"),
            "lam": float(lam_u), "lam_src": lam_src,
            "beta_norm": float(np.linalg.norm(c)),
            "n_clip": int((np.abs(c) >= clip_sigma - 1e-3).sum()),
            "dense_keep": nkeep, "dense_mean": md,
            "dense_rstats": dinfo["region_stats"],
            "rms_nasal": _nasal_rms(snap["labels"], res_m) if n_markers else None,
        }
        _push_worker_result(final)
        if dc < 1e-3:
            break
    if final is None:
        return {"status": "error",
                "error": "Dense deformation produced no valid correspondences."}
    final["status"] = "icp_done"
    final["note"] = f"ICP {hyp} + dense deformation finished"
    return final


class GNM_OT_prepare_skull(Operator):
    """Esantioneaza craniul (obiectul mesh ACTIV) pentru aliniere/deformare:
    ~60k puncte world + normale (numpy) + KD-tree (mathutils)."""
    bl_idname = "gnm.prepare_skull"
    bl_label = "Prepare Skull for Alignment"
    bl_description = (
        "Select the skull object first. Samples its surface (points + "
        "normals) and builds the KD-tree used by ICP and the dense "
        "constraints")
    bl_options = {"REGISTER", "UNDO"}

    MAX_POINTS = 60000

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None
                and context.active_object.type == 'MESH')

    def execute(self, context):
        scene = context.scene
        st = scene.gnm_live
        obj = context.active_object
        if obj.name == GNM_MESH_NAME or obj.name.startswith(GNM_GHOST_PREFIX):
            self.report({"ERROR"}, "The active object is a GNM live object, "
                                   "not the skull. Select the skull.")
            return {"CANCELLED"}
        ok, msg = _ensure_cranio(st.npz_path)
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        t0 = time.perf_counter()
        me = obj.data
        n_v = len(me.vertices)
        verts = np.empty(n_v * 3, dtype=np.float32)
        me.vertices.foreach_get("co", verts)
        verts = verts.reshape(-1, 3).astype(np.float64)
        mw = np.array(obj.matrix_world, dtype=np.float64)
        pts_all = verts @ mw[:3, :3].T + mw[:3, 3]
        # Sub-esantionare determinista (craniile au ~265k+ vertecsi).
        if len(pts_all) > self.MAX_POINTS:
            rng = np.random.default_rng(42)
            sel = np.sort(rng.choice(len(pts_all), self.MAX_POINTS,
                                     replace=False))
        else:
            sel = np.arange(len(pts_all))
        pts = np.ascontiguousarray(pts_all[sel])
        # Normale per-vertex din triunghiuri (numpy; winding-ul a fost
        # corectat la importul V12, deci sunt orientate spre exterior).
        me.calc_loop_triangles()
        n_t = len(me.loop_triangles)
        tris = np.empty(n_t * 3, dtype=np.int32)
        me.loop_triangles.foreach_get("vertices", tris)
        tris = tris.reshape(-1, 3)
        nrm_all = _CRANIO["compute_vertex_normals"](pts_all, tris)
        nrm = np.ascontiguousarray(nrm_all[sel])
        kd = kdtree.KDTree(len(pts))
        for i in range(len(pts)):
            kd.insert(pts[i], i)  # semnatura: insert(co, index)
        kd.balance()
        _LIVE.skull = {
            "points": pts, "normals": nrm, "tree": kd,
            "source": obj.name, "flipped": False,
        }
        st.skull_status = f"{len(pts)}p ({obj.name})"
        self.report({"INFO"},
                    f"Skull prepared: {len(pts)} points from '{obj.name}' "
                    f"({time.perf_counter() - t0:.1f}s).")
        return {"FINISHED"}


class GNM_OT_icp_deform(Operator):
    """One-shot: aliniaza capul NEDEFORMAT pe craniu (ICP multi-start) apoi
    aplica deformarea generala din morfologia craniului (constrangeri dense,
    ~2-4 s, progres vizibil). Functioneaza si cu 0 markeri; cu >=3 markeri,
    acestia raman ancore in fiturile dense."""
    bl_idname = "gnm.icp_deform"
    bl_label = "Align & Deform from Skull (ICP)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _LIVE.model is not None and _LIVE.skull is not None

    def execute(self, context):
        scene = context.scene
        st = scene.gnm_live
        if not _LIVE.enabled:
            _start_live(scene)
            st.live_active = True
        if _LIVE.dense_set is None:
            _refresh_dense_set(st.dense_scalp_only)
        snap = _build_snapshot(scene)
        snap["job"] = "icp_deform"
        with _LIVE.pending_lock:
            _LIVE.pending = snap
        st.status_text = "ICP + dense deformation running (2-4 s)..."
        self.report({"INFO"}, "ICP multi-start + dense deformation started.")
        return {"FINISHED"}


# -----------------------------------------------------------------------
# Preview snapshots, serial numerical work and result application
# -----------------------------------------------------------------------
def _fingerprint(scene):
    """Amprenta ieftina a pozitiilor markerilor (detecteaza add/move/delete,
    undo, schimbari de override) fara polling constant."""
    parts = []
    for item in scene.gnm_markers:
        if not item.is_placed:
            parts.append((item.label, item.gnm_vertex_override, 0))
            continue
        b = item.bone_empty.matrix_world.translation
        t = item.target_empty.matrix_world.translation
        parts.append((item.label, item.gnm_vertex_override, item.use_for_fit, item.fit_weight, 1,
                      round(b.x, 3), round(b.y, 3), round(b.z, 3),
                      round(t.x, 3), round(t.y, 3), round(t.z, 3)))
    return tuple(parts)


def _build_snapshot(scene):
    """Colecteaza perechile (eticheta, vertex, tinta-piele, pondere) pentru
    markerii plasati si mapati. Ruleaza pe MAIN thread (citeste bpy)."""
    labels, verts, tgts, ws = [], [], [], []
    for item in scene.gnm_markers:
        if not item.is_placed or not item.use_for_fit:
            continue
        vid = _resolve_vertex(item)
        if vid is None:
            continue
        p = item.target_empty.matrix_world.translation
        labels.append(item.label)
        verts.append(vid)
        tgts.append((p.x, p.y, p.z))
        ws.append(_weight_of(item.label, item))
    _core_module('marker_audit').require_unique_landmarks(labels, verts, tgts)
    # V13.2: modul dense continuu + poza curenta a obiectului GNM (necesara
    # pentru calculul corespondentelor in worker; citita aici, pe main thread).
    gnm_obj = bpy.data.objects.get(GNM_MESH_NAME)
    # V13.6: pozitiile PE OS ale landmark-urilor nazale (Gerasimov lucreaza
    # pe craniu, nu pe tintele de piele).
    bone = {}
    for item in scene.gnm_markers:
        if (item.is_placed and item.bone_empty is not None
                and item.label in _GERASIMOV_LABELS):
            p = item.bone_empty.matrix_world.translation
            bone[item.label] = (p.x, p.y, p.z)
    return {
        "labels": labels,
        "verts": np.asarray(verts, dtype=np.int64),
        "targets": np.asarray(tgts, dtype=np.float64).reshape(-1, 3),
        "weights": np.asarray(ws, dtype=np.float64),
        "dense": bool(scene.gnm_live.dense_enabled),
        "m_world": (np.array(gnm_obj.matrix_world, dtype=np.float64)
                    if gnm_obj is not None else np.eye(4)),
        "bone": bone,
    }


def _request_refit(scene):
    """Marcheaza un nou snapshot pentru worker (no-op daca live e oprit)."""
    if not _LIVE.enabled or _LIVE.model is None or scene.name != getattr(_LIVE, "scene_name", scene.name):
        return
    try:
        snap = _build_snapshot(scene)
    except (ValueError, TypeError) as exc:
        scene.gnm_live.status_text = 'Cannot fit: ' + str(exc)
        with _LIVE.pending_lock:
            _LIVE.pending = None
        return
    with _LIVE.pending_lock:
        _LIVE.pending = snap


def _adaptive_lambda(n_markers, base, lam_min, lam_max):
    return _core_module('regularization').adaptive_lambda(n_markers, base, lam_min, lam_max)


def _live_lambda(n, snap):
    """Actual included count; conditional LOO is cached by data, not count."""
    cfg = _LIVE.cfg
    base = float(cfg.get('lambda_base', 1.0))
    minimum, maximum = float(cfg.get('lambda_min', 0.3)), float(cfg.get('lambda_max', 1000.0))
    lam_formula = _adaptive_lambda(n, base, minimum, maximum)
    if not cfg.get('loo_auto', False) or n < 4:
        return lam_formula, 'adaptive' if n else 'no landmarks: maximum'
    module = _core_module('regularization')
    key = module.tuning_key(snap['verts'], snap['targets'], snap['weights'], id(_LIVE.model))
    cache = _LIVE.loo_cache
    if cache.get('key') != key:
        _c, _s, _r, _t, value, _info, _res = _CRANIO['fit_identity'](
            _LIVE.model.mu, _LIVE.model.basis, snap['verts'], snap['targets'],
            snap['weights'], lam='auto', loss_cfg=_CRANIO['LossConfig']())
        cache.update(key=key, lam=float(value))
    return float(cache['lam']), 'conditional LOO'


def _on_fit_settings_update(self, context):
    if context is not None:
        _request_refit(context.scene)

def _gerasimov_worker(snap, scale, rot, trans, v_model):
    """Diagnosticul Gerasimov/Ullrich-Stephan (V13.6). WORKER-safe: numpy pur.

    snap["bone"] = pozitiile PE OS ale markerilor nazali (colectate pe main
    thread); constructia Gerasimov lucreaza pe craniu, nu pe tintele de
    piele. Nu influenteaza fitul - pur informativ. Returneaza dict pentru
    res["gerasimov"] sau None daca niciun landmark nazal nu e plasat."""
    bone = snap.get("bone") or {}
    if not any(lbl in bone for lbl in _GERASIMOV_LABELS):
        return None
    ger_fn = _CRANIO.get("gerasimov_pronasale")
    if ger_fn is None:
        return {"ok": False, "reason": "cranio.geometry too old"}
    missing = [lbl for lbl in _GERASIMOV_LABELS if lbl not in bone]
    if missing:
        return {"ok": False, "reason": "missing: " + ", ".join(missing)}
    skull_pts = (_LIVE.skull or {}).get("points")
    # Rotate BONE positions into the pose-aligned anatomical axes, retaining mm.
    bone = {label: (np.asarray(xyz) - trans) @ rot for label, xyz in bone.items()}
    if skull_pts is not None:
        skull_pts = (skull_pts - trans) @ rot
    g = ger_fn(np.asarray(bone["Nasion"]), np.asarray(bone["Rhinion"]),
               np.asarray(bone["Acanthion"]), np.asarray(bone["Piriform_Dr"]),
               np.asarray(bone["Piriform_St"]), profile_pts=skull_pts)
    if not g["ok"]:
        return {"ok": False, "reason": g["reason"]}
    g["pronasale_xyz"] = g["pronasale_xyz"] @ rot.T + trans
    pr_fit = scale * (v_model[_PRONASALE_VID].astype(np.float64) @ rot.T) + trans
    return {"ok": True, "xyz": g["pronasale_xyz"],
            "err_vs_fit": float(np.linalg.norm(g["pronasale_xyz"] - pr_fit)),
            "dist_rhinion": float(g["dist_rhinion_mm"]),
            "angle": float(g["angle_deg"]),
            "fallback": bool(g["upper"]["fallback"])}


def _compute_fit(snap):
    """Numerical preview fit, called serially by the Blender main-thread timer.

    Refoloseste cranio.optimize.fit_identity (aceeasi matematica ca
    pipeline-ul offline): alternare Umeyama ponderat <-> ridge LSQ
    augmentat (forma primala; vezi nota din antet), Huber IRLS, clip +-3
    sigma. Fitting partial: lucreaza pe orice subset (L,).
    Priorul demografic (daca e incarcat) inlocuieste shrink-ul la beta=0
    cu shrink spre media demografica (vezi ipoteza 8 din antet)."""
    n = len(snap["labels"])
    if _LIVE.model is None:
        return {"status": "error", "error": "model not loaded"}
    dense_on = bool(snap.get("dense")) and _LIVE.skull is not None
    if n < 3 and not dense_on:
        # Sub 3 puncte, rotatia din Umeyama e subdeterminata - nu fitam.
        return {"status": "min3", "n": n}
    fit_identity = _CRANIO["fit_identity"]
    LossConfig = _CRANIO["LossConfig"]
    model = _LIVE.model
    # V13.2: randuri "pseudo-marker" din constrangerile dense de craniu.
    # Lambda se calculeaza DOAR pe markeri (randurile dense nu schimba
    # schedule-ul); ponderile dense = 0.5 x media ponderilor markerilor
    # (echivalentul lui dense_weight=0.5 din offline). V13.3: x multiplicatorul
    # din UI (dense_strength), x ponderile per regiune (nas = soft prior).
    verts_all, tgts_all = snap["verts"], snap["targets"]
    ws_all = snap["weights"]
    dense_keep = dense_mean = dense_rstats = None
    if dense_on and _LIVE.dense_set is not None:
        c_prev = _LIVE.last_c
        if c_prev is None:
            c_prev = np.zeros(model.identity_dim, dtype=np.float32)
        v_prev = model.generate(c_prev.astype(np.float32)).astype(np.float64)
        mw = snap.get("m_world", np.eye(4))
        vw = v_prev @ mw[:3, :3].T + mw[:3, 3]
        max_rows = int(_LIVE.cfg.get("dense_max_rows", 1500))
        sidx, dt_w, dense_keep, dense_mean, dinfo = _dense_rows(
            vw, max_rows, region_balance=True)
        if len(sidx) >= 10:
            strength = float(_LIVE.cfg.get("dense_strength", 1.0))
            wd = strength * 0.5 * (
                float(snap["weights"].mean()) if n else 0.7)
            verts_all = np.concatenate([snap["verts"], sidx])
            tgts_all = np.concatenate([snap["targets"], dt_w])
            ws_all = np.concatenate(
                [snap["weights"], wd * dinfo["row_mult"]])
            dense_rstats = dinfo["region_stats"]
        else:
            dense_keep = 0
    # Dense samples never inflate the anatomical landmark count.
    lam, lam_src = _live_lambda(n, snap)
    prior_kwargs = {}
    if _LIVE.prior is not None:
        prior_kwargs = {
            "prior_mean": _LIVE.prior["mean"],
            "prior_scale": _LIVE.prior["scale"],
            "prior_weight": float(_LIVE.cfg.get("prior_weight", 1.0)),
        }
    clip_sigma = float(_LIVE.cfg.get("clip_sigma", 3.0))
    c, scale, rot, trans, lam_used, _info, residuals = fit_identity(
        model.mu, model.basis, verts_all, tgts_all, ws_all,
        lam=lam, max_iter=int(_LIVE.cfg.get("max_iter", 8)), tol=1e-4,
        loss_cfg=LossConfig(clip_sigma=clip_sigma),
        huber_rows=n, pose_rows=n if n >= 3 else None, **prior_kwargs)
    # float32 pentru generare: ~2x mai rapid, eroare sub-micron.
    v_model = np.ascontiguousarray(
        model.generate(c.astype(np.float32)), dtype=np.float32)
    _LIVE.last_c = c
    res_m = residuals[:n] if n else np.array([np.nan])
    return {
        "status": "ok", "n": n,
        "scale": float(scale), "rot": rot, "trans": trans,
        "v_model": v_model,
        "c": c,
        "rms": float(np.sqrt(np.nanmean(res_m ** 2))) if n else 0.0,
        "max_res": float(np.nanmax(res_m)) if n else 0.0,
        "max_label": (snap["labels"][int(np.nanargmax(res_m))] if n else "-"),
        "lam": float(lam_used), "lam_src": lam_src,
        "beta_norm": float(np.linalg.norm(c)),
        "n_clip": int((np.abs(c) >= clip_sigma - 1e-3).sum()),
        "dense_keep": dense_keep, "dense_mean": dense_mean,
        "dense_rstats": dense_rstats,
        "rms_nasal": _nasal_rms(snap["labels"], res_m) if n else None,
        "gerasimov": _gerasimov_worker(snap, scale, rot, trans, v_model),
    }


def _apply_result(scene, res):
    """Aplica un rezultat de fit pe obiectele scenei. MAIN thread only."""
    st = scene.gnm_live
    st.last_fit_ms = res.get("ms", 0.0)
    status = res.get("status")
    if status == "error":
        st.status_text = f"Fit failed: {res.get('error', '?')[:140]}"
        # V13.6 fix: ascundem ghost-ul/statusul Gerasimov si pe calea de
        # eroare (altfel ramanea afisata ultima estimare valida - stale).
        _update_gerasimov_ghost(scene, None)
        st.gerasimov_status = ""
        return
    n = res.get("n", 0)
    st.n_fitted = n
    if status == "min3":
        st.status_text = (
            f"Too few usable markers ({n}) - minimum 3 for alignment "
            f"or dense constraints.")
        _update_gerasimov_ghost(scene, None)
        st.gerasimov_status = ""
        return
    obj = bpy.data.objects.get(GNM_MESH_NAME)
    if obj is not None:
        me = obj.data
        me.vertices.foreach_set("co", res["v_model"].ravel())
        me.update()
        # world = scale * (v @ rot.T) + trans  (conventie rand-vector din
        # cranio)  <=>  matrix_world = Translation(t) @ Scale(s) @ R, cu
        # partea liniara R = rot (v @ rot.T in rand-vector = rot @ v coloana).
        s, rot, t = res["scale"], res["rot"], res["trans"]
        rot4 = Matrix((
            (rot[0, 0], rot[0, 1], rot[0, 2], 0.0),
            (rot[1, 0], rot[1, 1], rot[1, 2], 0.0),
            (rot[2, 0], rot[2, 1], rot[2, 2], 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))
        obj.matrix_world = (Matrix.Translation((t[0], t[1], t[2]))
                            @ Matrix.Scale(s, 4) @ rot4)
        _update_ghosts_from_fit(scene, res["v_model"], s, rot, t)
    st.rms_mm = res["rms"]
    prefix = "ICP+deform: " if status == "icp_done" else "Fit OK: "
    st.status_text = (
        f"{prefix}{n} markers, lambda={res['lam']:.2g}({res.get('lam_src', '?')}), "
        f"RMS={res['rms']:.2f} mm, max={res['max_res']:.1f} ({res['max_label']}) "
        f"| |beta|={res.get('beta_norm', 0.0):.1f}, clip {res.get('n_clip', 0)}")
    if res.get("note"):
        st.status_text = f"{res['note']} | " + st.status_text
    if res.get("dense_keep") is not None:
        dk, dm = res["dense_keep"], res.get("dense_mean")
        st.dense_status = (
            f"Dense: {dk} correspondences" +
            (f", mean dist {dm:.1f} mm" if dm == dm else "")  # NaN-safe
            if dk else "Dense: 0 valid correspondences (check skull "
                       "normals / distance to head)")
        # V13.3: diagnostic dedicat puntii nazale (keep-rate + distanta
        # medie la os fata de tinta de 3 mm) + RMS pe landmark-urile nazale.
        rstats = res.get("dense_rstats")
        if dk and rstats and "punte_nazala" in rstats:
            nk, nt, nd = rstats["punte_nazala"]
            st.dense_status += (f" | nose: {nk}/{nt}" +
                                (f" @{nd:.1f} mm (target 3)"
                                 if nd == nd else ""))
        rn = res.get("rms_nasal")
        if rn is not None:
            st.dense_status += f" | nose RMS {rn:.1f} mm"
    # V13.6: diagnosticul Gerasimov (ghost cyan + linie de status proprie,
    # langa diagnosticele nazale V13.3). Pur informativ - nu atinge fitul.
    ger = res.get("gerasimov")
    _update_gerasimov_ghost(scene, ger)
    if ger is not None:
        if ger.get("ok"):
            st.gerasimov_status = (
                f"Gerasimov: delta fit {ger['err_vs_fit']:.1f} mm | "
                f"Rhinion {ger['dist_rhinion']:.1f} mm, "
                f"{ger['angle']:.0f} deg"
                + (" (no skull: N->R dir.)" if ger.get("fallback") else ""))
        else:
            st.gerasimov_status = (
                f"Gerasimov: n/a - {ger.get('reason', '')[:90]}")
    screen = bpy.context.screen
    if screen is not None:
        for a in screen.areas:
            if a.type == 'VIEW_3D':
                a.tag_redraw()


def _live_timer_tick():
    """Timer main-thread: oglindeste setarile in _LIVE.cfg si aplica
    rezultatele gata. Returneaza intervalul urmator (sau None = stop)."""
    if not _LIVE.enabled:
        return None
    scene = bpy.data.scenes.get(getattr(_LIVE, "scene_name", ""))
    if scene is None or not hasattr(scene, "gnm_live"):
        return 0.5
    st = scene.gnm_live
    _LIVE.cfg.update({
        "lambda_base": float(st.lambda_base),
        "lambda_min": float(st.lambda_min),
        "lambda_max": float(st.lambda_max),
        "loo_auto": bool(st.loo_auto),
        "prior_weight": float(st.prior_weight),
        "dense_strength": float(st.dense_strength),
        "dense_nose_weight": float(st.dense_nose_weight),
        "dense_max_rows": int(st.dense_max_rows),
        "clip_sigma": float(st.clip_sigma),
    })
    with _LIVE.pending_lock:
        snap = _LIVE.pending
        _LIVE.pending = None
    if snap is not None:
        started = time.perf_counter()
        try:
            result = _icp_deform_job(snap) if snap.get("job") == "icp_deform" else _compute_fit(snap)
        except Exception as exc:
            result = {"status": "error", "error": str(exc)}
        result["ms"] = (time.perf_counter() - started) * 1000.0
        _push_worker_result(result)
    res = None
    with _LIVE.result_lock:
        res = _LIVE.result
        _LIVE.result = None
    if res is not None:
        try:
            _apply_result(scene, res)
        except Exception as exc:
            st.status_text = f"Error applying fit: {exc}"
    return 1.0 / max(float(st.update_hz), 0.1)


@bpy.app.handlers.persistent
def _gnm_live_on_depsgraph(scene, depsgraph):
    """Trigger de refit la adaugare/mutare/stergere markeri (fara polling):
    fingerprint pe pozitiile empty-urilor; ignora orice alta schimbare."""
    if not _LIVE.enabled or _LIVE.model is None:
        return
    try:
        fp = _fingerprint(scene)
    except Exception:
        return
    if fp == _LIVE.fingerprints.get(scene.name):
        return
    _LIVE.fingerprints[scene.name] = fp
    _request_refit(scene)


@bpy.app.handlers.persistent
def _gnm_live_on_load_post(_dummy):
    """La deschiderea unui .blend nou, fingerprint-urile vechi nu mai au
    sens; modelul numpy si firul de lucru raman valabile."""
    _stop_live()
    _stop_offline()
    _LIVE.fingerprints.clear()


def _add_live_handler():
    _remove_live_handler()
    bpy.app.handlers.depsgraph_update_post.append(_gnm_live_on_depsgraph)


def _remove_live_handler():
    for h in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(h, "__name__", "") == "_gnm_live_on_depsgraph":
            bpy.app.handlers.depsgraph_update_post.remove(h)


def _start_live(scene):
    """Start the serial preview timer and handler (idempotent)."""
    _LIVE.scene_name = scene.name
    _LIVE.stop_event = threading.Event()
    with _LIVE.result_lock:
        _LIVE.result = None  # golim rezultatele vechi (igiena la repornire)
    _LIVE.worker = None
    _LIVE.enabled = True
    if not bpy.app.timers.is_registered(_live_timer_tick):
        bpy.app.timers.register(
            _live_timer_tick, first_interval=0.1, persistent=True)
    _add_live_handler()
    _request_refit(scene)  # fit initial imediat


def _stop_live():
    """Opreste toate serviciile live (sigur la unregister/reload F8)."""
    _LIVE.enabled = False
    _LIVE.stop_event.set()
    w = _LIVE.worker
    if w is not None and w.is_alive():
        w.join(timeout=1.0)
    _LIVE.worker = None
    for scene in bpy.data.scenes:
        if hasattr(scene, "gnm_live"):
            scene.gnm_live.live_active = False
    _remove_live_handler()
    if bpy.app.timers.is_registered(_live_timer_tick):
        bpy.app.timers.unregister(_live_timer_tick)


# -----------------------------------------------------------------------
# V13: viewport-uri (split + local-view per area)
# -----------------------------------------------------------------------
def _view3d_areas_sorted():
    screen = bpy.context.screen
    if screen is None:
        return []
    areas = [a for a in screen.areas if a.type == 'VIEW_3D']
    areas.sort(key=lambda a: (a.x, -a.y))
    return areas


def _sync_gnm_to_right_local_view(context):
    """Adauga obiectele GNM-live in local-view-ul din dreapta (daca layoutul
    dual e deja configurat); altfel, utilizatorul ruleaza Setup/Repara."""
    areas = _view3d_areas_sorted()
    if len(areas) < 2:
        return
    right = areas[-1]
    region = next((r for r in right.regions if r.type == 'WINDOW'), None)
    win = context.window
    if region is None or win is None:
        return
    gnm_objs = list(_gnm_live_objects())
    if not gnm_objs:
        return
    bpy.ops.object.select_all(action='DESELECT')
    for o in gnm_objs:
        try:
            o.select_set(True)
        except Exception:
            pass
    try:
        with context.temp_override(
                window=win, screen=win.screen, area=right, region=region):
            bpy.ops.view3d.localview_add_selected()
    except Exception:
        pass


class GNM_OT_setup_dual_viewports(Operator):
    """Split vertical al zonei in doua VIEW_3D (stanga=craniu, dreapta=GNM).

    Idempotent: la rerulare reconstruieste local-view-urile de la zero
    ("Repara Layout", ex. dupa ce utilizatorul a iesit din local view).
    """
    bl_idname = "gnm.setup_dual_viewports"
    bl_label = "Setup / Repair Dual Layout"
    bl_description = (
        "Splits the area into two side-by-side 3D viewports: left = skull + "
        "markers, right = live GNM mesh + ghosts (local-view per area, same "
        "scene). Run again to repair the layout")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        win = context.window
        if win is None or win.screen is None:
            self.report({"ERROR"},
                        "Requires a Blender window (does not run in background).")
            return {"CANCELLED"}
        screen = win.screen
        areas = [a for a in screen.areas if a.type == 'VIEW_3D']
        if not areas:
            self.report({"ERROR"}, "There is no 3D viewport in the current screen.")
            return {"CANCELLED"}
        if len(areas) < 2:
            area = areas[0]
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            try:
                with context.temp_override(
                        window=win, screen=screen, area=area, region=region):
                    bpy.ops.screen.area_split(direction='VERTICAL', factor=0.5)
            except Exception as exc:
                self.report({"ERROR"}, f"area_split failed: {exc}")
                return {"CANCELLED"}
        areas = _view3d_areas_sorted()
        left, right = areas[0], areas[-1]

        saved_sel = list(context.selected_objects)
        saved_act = context.view_layer.objects.active
        gnm_objs = _gnm_live_objects()
        left_objs = [o for o in context.scene.objects if o not in gnm_objs]
        self._config_area(context, win, screen, left, left_objs)
        self._config_area(context, win, screen, right, list(gnm_objs))
        # Restauram selectia utilizatorului (setup-ul o modifica).
        bpy.ops.object.select_all(action='DESELECT')
        for o in saved_sel:
            try:
                o.select_set(True)
            except Exception:
                pass
        context.view_layer.objects.active = saved_act

        context.scene.gnm_live.layout_ok = True
        self.report({"INFO"},
                    "Dual layout: left=skull, right=GNM live. "
                    "Re-run to repair.")
        return {"FINISHED"}

    def _config_area(self, context, win, screen, area, objects):
        """Forteaza local-view-ul unei area sa contina exact `objects`."""
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        space = area.spaces.active
        if region is None or space is None:
            return
        with context.temp_override(
                window=win, screen=screen, area=area, region=region):
            # Iesim dintr-un eventual local-view existent (revenire la
            # vederea globala), apoi intram din nou cu selectia dorita.
            try:
                if space.local_view:
                    bpy.ops.view3d.localview(frame_selected=False)
            except Exception:
                pass
            bpy.ops.object.select_all(action='DESELECT')
            n_sel = 0
            for o in objects:
                if o is not None and o.name in context.view_layer.objects:
                    try:
                        o.select_set(True)
                        n_sel += 1
                    except Exception:
                        pass
            if n_sel:
                try:
                    context.view_layer.objects.active = objects[0]
                except Exception:
                    pass
            try:
                bpy.ops.view3d.localview(frame_selected=False)
            except Exception as exc:
                print("GNM V13: localview esuat:", exc)
            try:
                if n_sel:
                    bpy.ops.view3d.view_selected()
                else:
                    bpy.ops.view3d.view_all()
            except Exception:
                pass
        try:
            space.shading.type = 'SOLID'
            # Necesar ca ghost-urile sa apara colorate pe confidence.
            space.shading.color_type = 'OBJECT'
        except Exception:
            pass


class GNM_OT_toggle_skull_overlay(Operator):
    """Adauga/elimina obiectele GNM-live in/din local-view-ul STANG (overlay
    real craniu <-> cap GNM, posibil tocmai pentru ca impart aceeasi lume)."""
    bl_idname = "gnm.toggle_skull_overlay"
    bl_label = "Overlay GNM in Left Viewport"
    bl_description = (
        "Shows/hides the GNM head and ghosts in the left viewport too "
        "(direct overlay on the skull, for alignment verification)")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        st = context.scene.gnm_live
        areas = _view3d_areas_sorted()
        if len(areas) < 2:
            self.report({"ERROR"},
                        "Set up the dual layout first (Setup / Repair).")
            return {"CANCELLED"}
        left = areas[0]
        region = next((r for r in left.regions if r.type == 'WINDOW'), None)
        win = context.window
        if region is None or win is None:
            return {"CANCELLED"}
        gnm_objs = list(_gnm_live_objects())
        if not gnm_objs:
            self.report({"ERROR"}, "Load the GNM model first.")
            return {"CANCELLED"}
        st.overlay_skull = not st.overlay_skull
        bpy.ops.object.select_all(action='DESELECT')
        for o in gnm_objs:
            try:
                o.select_set(True)
            except Exception:
                pass
        try:
            with context.temp_override(
                    window=win, screen=win.screen, area=left, region=region):
                if st.overlay_skull:
                    bpy.ops.view3d.localview_add_selected()
                else:
                    bpy.ops.view3d.localview_remove_selected()
        except Exception as exc:
            st.overlay_skull = not st.overlay_skull  # revert
            self.report({"ERROR"}, f"Overlay failed: {exc}")
            return {"CANCELLED"}
        bpy.ops.object.select_all(action='DESELECT')
        return {"FINISHED"}


# -----------------------------------------------------------------------
# V13: incarcarea modelului + servicii live
# -----------------------------------------------------------------------
def _autodetect_paths(scene):
    """Default-uri pentru npz/json/priori relativ la fisierul addon-ului
    (layoutul repo-ului de dezvoltare); utilizatorul le poate suprascrie."""
    st = scene.gnm_live
    root = os.path.dirname(os.path.abspath(__file__))
    if not st.npz_path and os.environ.get("GNM_MODEL_PATH"):
        st.npz_path = os.environ["GNM_MODEL_PATH"]
    if not st.npz_path:
        cand = os.path.join(root, "gnm", "shape", "data", "versions",
                            "v3_0", "gnm_head.npz")
        if os.path.isfile(cand):
            st.npz_path = cand
    if not st.json_path:
        cand = os.path.join(root, "landmark_vertex_map.json")
        if os.path.isfile(cand):
            st.json_path = cand
    if not st.prior_dir:
        st.prior_dir = os.path.join(root, "priors")


def _load_prior(scene):
    """Incarca npz-ul de prior demografic pentru combinatia sex/etnie aleasa.

    Ruleaza pe MAIN thread (fisier de cativa KB); workerul citeste doar
    _LIVE.prior (dictionar numpy sau None). Fisierele sunt generate offline
    cu make_demographic_prior.py (IdentitySampler necesita TensorFlow).
    """
    st = scene.gnm_live
    _LIVE.prior = None
    if st.prior_sex == 'NONE' or st.prior_ethnicity == 'NONE':
        st.prior_status = "inactive"
        return
    # Self-healing: priorul apeleaza fit_identity cu argumente noi; ne
    # asiguram ca cranio importat e proaspat (vezi docstring-ul
    # _ensure_cranio) chiar daca sesiunea Blender e veche.
    ok, msg = _ensure_cranio(st.npz_path)
    if not ok:
        st.prior_status = f"cranio: {msg[:80]}"
        return
    _autodetect_paths(scene)
    path = os.path.join(
        st.prior_dir, f"prior_{st.prior_sex}_{st.prior_ethnicity}.npz")
    if not os.path.isfile(path):
        st.prior_status = "missing (run make_demographic_prior.py)"
        return
    try:
        d = np.load(path, allow_pickle=False)
        mean = np.ascontiguousarray(d["mean"], dtype=np.float64).ravel()
        scale = np.clip(
            np.ascontiguousarray(d["scale"], dtype=np.float64).ravel(),
            0.25, 4.0)
        if mean.shape != (253,) or scale.shape != (253,):
            raise ValueError(f"unexpected dimensions: {mean.shape}")
        _LIVE.prior = {"mean": mean, "scale": scale}
        n_sam = int(d["n_samples"]) if "n_samples" in d else 0
        st.prior_status = (
            f"{st.prior_sex}/{st.prior_ethnicity}"
            + (f" (n={n_sam})" if n_sam else ""))
    except Exception as exc:
        _LIVE.prior = None
        st.prior_status = f"error: {exc}"


def _on_prior_selection_update(self, context):
    """La schimbarea sexului/etniei: reincarcam priorul si refitam."""
    if context and getattr(context, "scene", None):
        _load_prior(context.scene)
        _request_refit(context.scene)


def _on_dense_toggle_update(self, context):
    """La comutarea dense continuu / doar-scalp: reimprospatam setul dens
    activ si cerem un refit (snapshot-ul preia noul flag dense)."""
    if context and getattr(context, "scene", None):
        _refresh_dense_set(context.scene.gnm_live.dense_scalp_only)
        _request_refit(context.scene)


def _on_dense_param_update(self, context):
    """La schimbarea parametrilor dense/clip (V13.3): cerem un refit cu
    noile valori (oglindirea lor in _LIVE.cfg o face timerul la tick)."""
    if context and getattr(context, "scene", None):
        _request_refit(context.scene)


class GNM_OT_load_live_model(Operator):
    """Incarca gnm_head.npz (float32, mm) + landmark_vertex_map.json si
    creeaza obiectele din viewport-ul drept (mesh GNM + ghost-uri)."""
    bl_idname = "gnm.load_live_model"
    bl_label = "Load GNM Model & Map"
    bl_description = (
        "Loads the GNM Head model (npz) and the landmark->vertex map (JSON), "
        "then creates/updates the mesh in the right viewport")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        st = scene.gnm_live
        _autodetect_paths(scene)
        st.npz_path = bpy.path.abspath(st.npz_path)
        if not st.npz_path or not os.path.isfile(st.npz_path):
            self.report({"ERROR"},
                        "The path to gnm_head.npz is not set correctly.")
            return {"CANCELLED"}
        ok, msg = _ensure_cranio(st.npz_path)
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        t0 = time.perf_counter()
        try:
            _LIVE.model = _load_gnm_model(st.npz_path)
        except Exception as exc:
            self.report({"ERROR"}, f"Cannot load the npz: {exc}")
            return {"CANCELLED"}
        _LIVE.label_to_vertex = _label_to_vertex_map()
        _LIVE.loo_cache = {"key": None, "lam": None}
        # V13.2: setul dens (scalp + regiuni) depinde de model; orientarea
        # fetelor GNM se determina deterministic din volumul semnat.
        _LIVE.dense_full = None
        _LIVE.dense_scalp = None
        _LIVE.flip = bool(_signed_volume(
            _LIVE.model.mu, _LIVE.model.triangles) < 0)
        _refresh_dense_set(st.dense_scalp_only)
        if st.json_path and os.path.isfile(st.json_path):
            try:
                with open(st.json_path, "r", encoding="utf-8") as f:
                    _LIVE.json_map = json.load(f)
            except Exception as exc:
                _LIVE.json_map = None
                self.report({"WARNING"},
                            f"Could not read the JSON ({exc}); "
                            f"continuing without confidence colors.")
        else:
            _LIVE.json_map = None

        _ensure_gnm_mesh_object(context)
        _ensure_ghosts(context)
        _sync_gnm_to_right_local_view(context)

        n_json = len(_LIVE.json_map or {})
        st.model_status = (
            f"loaded ({_LIVE.model.vertex_count}v, "
            f"{time.perf_counter() - t0:.1f}s, JSON:{n_json})")
        # Daca live-ul e deja pornit, refitam cu noul model.
        _request_refit(scene)
        self.report({"INFO"}, f"GNM model loaded: {st.model_status}")
        return {"FINISHED"}


class GNM_OT_toggle_live(Operator):
    """Toggle serialized main-thread preview; use external fitting for long jobs."""
    bl_idname = "gnm.toggle_live"
    bl_label = "Start / Stop Preview (may pause UI)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        st = context.scene.gnm_live
        if _LIVE.enabled:
            _stop_live()
            st.live_active = False
            st.status_text = "Live stopped."
            self.report({"INFO"}, "Live fitting stopped.")
        else:
            if _LIVE.model is None:
                self.report({"ERROR"},
                            "Load the GNM model first (button above).")
                return {"CANCELLED"}
            _start_live(context.scene)
            st.live_active = True
            st.status_text = "Live started - move/add markers on the left."
            self.report({"INFO"}, "Live fitting started.")
        return {"FINISHED"}


class GNM_OT_delete_marker(Operator):
    """Sterge obiectele markerului activ (mutarea = re-plasare cu operatorul
    existent 'Plaseaza Marker')."""
    bl_idname = "gnm.delete_marker"
    bl_label = "Delete Active Marker"
    bl_description = (
        "Deletes the active marker's empties and peg from the list; to move "
        "it, use 'Place Marker' again (replaces the position)")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.gnm_markers)

    def execute(self, context):
        scene = context.scene
        item = scene.gnm_markers[scene.gnm_marker_active_index]
        for old in (item.bone_empty, item.target_empty, item.peg_object):
            if old is not None:
                bpy.data.objects.remove(old, do_unlink=True)
        item.bone_empty = None
        item.target_empty = None
        item.peg_object = None
        _request_refit(scene)
        self.report({"INFO"}, f"Marker deleted: {item.label}")
        return {"FINISHED"}


class GNM_OT_pick_gnm_vertex(Operator):
    """Picking manual de vertex pe mesh-ul GNM (panoul drept).

    Destinat landmark-urilor fara correspondenta in harta (ex. puncte de pe
    bolta craniana adaugate ulterior) sau corectarii fine a candidatilor cu
    confidence 'low'. Click stanga pe capul GNM -> cel mai apropiat vertex
    devine override-ul markerului activ. ESC/click-dreapta anuleaza.
    """
    bl_idname = "gnm.pick_gnm_vertex"
    bl_label = "Pick GNM Vertex (active marker)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (_LIVE.model is not None
                and bpy.data.objects.get(GNM_MESH_NAME) is not None
                and bool(context.scene.gnm_markers))

    def invoke(self, context, event):
        scene = context.scene
        item = scene.gnm_markers[scene.gnm_marker_active_index]
        self._label = item.label
        self._gnm = bpy.data.objects.get(GNM_MESH_NAME)
        scene.gnm_live.status_text = (
            f"Picking '{item.label}': click on the GNM head (right); "
            f"ESC cancels.")
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"RIGHTMOUSE", "ESC"}:
            return {"CANCELLED"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            hit = self._cast_on_gnm(context, event)
            if hit is None:
                return {"RUNNING_MODAL"}
            vid = self._nearest_vertex(hit)
            item = _marker_item(context.scene, self._label)
            if item is not None:
                item.gnm_vertex_override = vid
                item.mapping_reviewed = True
                _refresh_ghosts(context.scene)
                _request_refit(context.scene)
                self.report({"INFO"},
                            f"{self._label}: manual vertex #{vid} "
                            f"(override).")
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def _cast_on_gnm(self, context, event):
        """Raycast care accepta DOAR hit-uri pe mesh-ul GNM (ray-marching
        peste craniu/markeri, max ~8 hopuri)."""
        region = context.region
        rv3d = context.region_data
        coord = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        depsgraph = context.evaluated_depsgraph_get()
        o = origin.copy()
        for _ in range(8):
            result, location, _n, _i, hit_obj, _m = context.scene.ray_cast(
                depsgraph, o, direction)
            if not result:
                return None
            if hit_obj == self._gnm:
                return location
            o = location + direction * 0.05
        return None

    def _nearest_vertex(self, world_pt):
        """Cel mai apropiat vertex GNM (in world) de punctul lovit.

        Regenereaza pozitiile curente (ultimii coeficienti cunoscuti) si le
        trece prin matrix_world; ~15 ms o data pe click, acceptabil."""
        model = _LIVE.model
        c = _LIVE.last_c
        if c is None:
            c = np.zeros(model.identity_dim, dtype=np.float32)
        v = model.generate(c.astype(np.float32)).astype(np.float64)
        m_world = np.array(self._gnm.matrix_world, dtype=np.float64)
        vw = v @ m_world[:3, :3].T + m_world[:3, 3]
        d2 = ((vw - np.asarray(world_pt, dtype=np.float64)) ** 2).sum(axis=1)
        return int(np.argmin(d2))


class GNM_OT_clear_gnm_override(Operator):
    """Sterge override-ul manual de vertex al markerului activ (revine la
    lantul V12 > JSON)."""
    bl_idname = "gnm.clear_gnm_override"
    bl_label = "Clear Vertex Override"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.gnm_markers)

    def execute(self, context):
        scene = context.scene
        item = scene.gnm_markers[scene.gnm_marker_active_index]
        item.gnm_vertex_override = -1
        item.mapping_reviewed = False
        _refresh_ghosts(scene)
        _request_refit(scene)
        self.report({"INFO"}, f"{item.label}: override cleared (back to V12/JSON).")
        return {"FINISHED"}


class GNM_OT_export_landmark_json(Operator):
    """Face merge al picking-urilor manuale in landmark_vertex_map.json.

    Completeaza harta partajata cu pipeline-ul offline: fiecare override
    devine o intrare cu source='manual_picked_blender', confidence='manual'.
    Pozitia salvata este cea din TEMPLATE (spatiul modelului, in METRI -
    aceeasi conventie ca intrarile existente). Fisierul original primeste
    backup .bak inainte de rescriere.
    """
    bl_idname = "gnm.export_landmark_json"
    bl_label = "Export Updated JSON Map"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _LIVE.model is not None and bool(context.scene.gnm_markers)

    def execute(self, context):
        scene = context.scene
        st = scene.gnm_live
        if not st.json_path:
            self.report({"ERROR"}, "The JSON path is not set.")
            return {"CANCELLED"}
        try:
            with open(st.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        model = _LIVE.model
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        n_merged = 0
        for item in scene.gnm_markers:
            if item.gnm_vertex_override < 0:
                continue
            vid = int(item.gnm_vertex_override)
            key = ADDON_TO_JSON_KEY.get(item.label) or item.label.lower()
            data[key] = {
                "vertex_index": vid,
                "position": (model.mu[vid].astype(np.float64) / 1000.0).tolist(),
                "source": "manual_picked_blender",
                "confidence": "manual",
                "note": (f"Manually picked in Blender (addon {bl_info['version'][0]}) on {stamp}; "
                         f"addon label: {item.label}"),
            }
            n_merged += 1
        if not n_merged:
            self.report({"WARNING"},
                        "No manual override to export (use 'Pick GNM Vertex' "
                        "first).")
            return {"CANCELLED"}
        if os.path.isfile(st.json_path):
            shutil.copy2(st.json_path, st.json_path + ".bak")
        with open(st.json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _LIVE.json_map = data
        _refresh_ghosts(scene)
        self.report({"INFO"},
                    f"{n_merged} manual picks saved to "
                    f"{os.path.basename(st.json_path)} (.bak backup).")
        return {"FINISHED"}


# -----------------------------------------------------------------------
# V13: proprietati si panou
# -----------------------------------------------------------------------
def _on_show_ghosts_update(self, context):
    if context and context.scene:
        _refresh_ghosts(context.scene)


class GNMLiveSettings(PropertyGroup):
    """Setari si stare (read-only din UI) pentru reconstructia live."""
    npz_path: StringProperty(
        name="Path gnm_head.npz", subtype="FILE_PATH", default="",
        description="Path to gnm_head.npz (gnm/shape/data/versions/v3_0)")
    json_path: StringProperty(
        name="Path landmark_vertex_map.json", subtype="FILE_PATH", default="",
        description="Path to the landmark->vertex map (confidence/colors)")
    live_active: BoolProperty(default=False)
    show_ghosts: BoolProperty(
        name="Show GNM Ghosts", default=True,
        update=_on_show_ghosts_update,
        description="Overlay of empties colored by confidence at the GNM "
                    "landmark positions (right viewport)")
    overlay_skull: BoolProperty(default=False)
    layout_ok: BoolProperty(default=False)
    update_hz: FloatProperty(
        name="Update Rate (Hz)", default=10.0, min=1.0, max=30.0,
        description="How many result applications per second (the fit itself "
                    "runs serially in the main-thread timer and may pause the UI)")
    lambda_base: FloatProperty(
        name="Lambda at 48 landmarks", default=1.0, min=0.05, max=1000.0,
        soft_min=0.3, soft_max=30.0, update=_on_fit_settings_update,
        description="Count heuristic: base * 48 / actual included landmarks; not an accuracy calibration")
    lambda_min: FloatProperty(name="Lambda Min", default=0.3, min=0.01, update=_on_fit_settings_update)
    lambda_max: FloatProperty(name="Lambda Max", default=1000.0, min=1.0, update=_on_fit_settings_update)
    loo_auto: BoolProperty(name="Conditional LOO tuning (slower)", default=False,
        update=_on_fit_settings_update,
        description="Tune with current positions, vertices and weights; cached only while inputs stay identical. Runs on the main thread")


    prior_sex: EnumProperty(
        name="Sex (prior)", default='NONE',
        items=[
            ('NONE', "Unknown", "No demographic prior"),
            ('FEMALE', "Female", "Prior on the female mean (IdentitySampler)"),
            ('MALE', "Male", "Prior on the male mean (IdentitySampler)"),
        ],
        update=_on_prior_selection_update,
        description="Demographic prior: shrink towards the chosen sex mean "
                    "(from IdentitySampler, precomputed offline)")
    prior_ethnicity: EnumProperty(
        name="Ethnicity (prior)", default='NONE',
        items=[
            ('NONE', "Unknown", "No demographic prior"),
            ('MIDDLE_EASTERN', "Middle Eastern", "Middle-Eastern prior"),
            ('ASIAN', "Asian", "Asian prior"),
            ('WHITE', "White / Caucasian", "White prior"),
            ('BLACK', "Black / African", "Black prior"),
        ],
        update=_on_prior_selection_update,
        description="Ethnicity for the demographic prior (the GNM CVAE "
                    "categories)")
    prior_weight: FloatProperty(
        name="Prior Strength", default=1.0, min=0.1, max=4.0,
        description="Multiplier of the demographic prior precision "
                    "(1.0 = exact Gaussian MAP; >1 = stronger shrinkage "
                    "towards the demographic mean)")
    prior_dir: StringProperty(
        name="Priors Folder", subtype="DIR_PATH", default="",
        description="Folder with prior_<SEX>_<ETHNICITY>.npz files "
                    "(generated with make_demographic_prior.py)")
    prior_status: StringProperty(default="inactive")
    dense_enabled: BoolProperty(
        name="Continuous Dense", default=False,
        update=_on_dense_toggle_update,
        description="Dense skull constraints at every fit (scalp + thin-"
                    "tissue regions, like --skull offline). The general "
                    "deformation follows skull morphology; rate drops to "
                    "~2-3 Hz. Requires 'Prepare Skull'")
    dense_scalp_only: BoolProperty(
        name="Scalp only (conservative)", default=False,
        update=_on_dense_toggle_update,
        description="Dense constraints on the scalp only (equivalent to "
                    "--no-face-dense offline); recommended for skulls with "
                    "a damaged face")
    dense_strength: FloatProperty(
        name="Dense Strength", default=1.0, min=0.1, max=10.0,
        update=_on_dense_param_update,
        description="Multiplier of the ICP/dense attraction force "
                    "(1.0 = calibrated default). Increase if skull areas "
                    "remain uncovered after alignment; decrease if the head "
                    "sticks too aggressively to the bone")
    dense_nose_weight: FloatProperty(
        name="Dense Nose Weight", default=0.7, min=0.0, max=2.0,
        update=_on_dense_param_update,
        description="Weight of the dense constraint on the nasal bridge, as "
                    "a 'soft prior' (0.7 default): below 1.0 lets the nasal "
                    "landmarks (Nasion/Rhinion/Nasospinale/Alare) and the "
                    "statistical model decide the nose shape; 0 = nose not "
                    "densely constrained at all")
    dense_max_rows: IntProperty(
        name="Max Dense Rows", default=1500, min=400, max=3000,
        update=_on_dense_param_update,
        description="Maximum number of dense rows per fit, with a 50/50 "
                    "face/scalp budget; more = denser constraint (better "
                    "coverage), slower fit")
    clip_sigma: FloatProperty(
        name="Clip Sigma", default=3.0, min=2.5, max=4.0,
        update=_on_dense_param_update,
        description="Hard limit of identity coefficients (+-sigma). "
                    "WARNING: above 3.0 the head can leave the model's "
                    "plausible domain - watch the 'clip N' indicator in "
                    "the status line")
    skull_status: StringProperty(default="not prepared")
    dense_status: StringProperty(default="")
    # V13.6: linia de status a diagnosticului Gerasimov/Ullrich-Stephan
    gerasimov_status: StringProperty(default="")
    model_status: StringProperty(default="not loaded")
    status_text: StringProperty(default="")
    rms_mm: FloatProperty(default=0.0)
    n_fitted: IntProperty(default=0)
    last_fit_ms: FloatProperty(default=0.0)


def _draw_live_section(layout, context):
    """Sectiunea V13 din panoul principal (apelata la finalul lui draw)."""
    scene = context.scene
    st = scene.gnm_live
    layout.separator()
    box = layout.box()
    box.label(text="GNM Live Reconstruction (V13):")

    row = box.row(align=True)
    row.operator("gnm.setup_dual_viewports", icon="WINDOW",
                 text="Setup / Repair Layout")
    row.operator("gnm.toggle_skull_overlay", text="",
                 icon="RESTRICT_VIEW_ON" if st.overlay_skull
                 else "RESTRICT_VIEW_OFF", depress=st.overlay_skull)

    box.prop(st, "npz_path")
    box.prop(st, "json_path")
    row = box.row(align=True)
    row.operator("gnm.load_live_model", icon="FILE_3D", text="Load Model & Map")
    row.label(text=st.model_status)

    if not scene.gnm_markers:
        box.label(text="Load the marker list first (step 2).")
        return

    row = box.row(align=True)
    row.operator("gnm.toggle_live",
                 icon="PAUSE" if st.live_active else "PLAY",
                 text="Stop Live" if st.live_active else "Start Live",
                 depress=st.live_active)
    row.prop(st, "show_ghosts", text="",
             icon="HIDE_OFF" if st.show_ghosts else "HIDE_ON")

    # Preview regularisation heuristic; see docs/SCIENCE.md.
    box.prop(st, "lambda_base", slider=True)
    box.prop(st, "loo_auto")
    row = box.row(align=True)
    row.prop(st, 'lambda_min')
    row.prop(st, 'lambda_max')
    try:
        used = len(_build_snapshot(scene)['labels'])
        value = _adaptive_lambda(used, st.lambda_base, st.lambda_min, st.lambda_max)
        box.label(text=f"Included: {used}; conditional LOO tuning" if st.loo_auto
                       else f"Included: {used}; adaptive lambda = {value:.4g}")
    except ValueError as exc:
        box.label(text=str(exc)[:80], icon='ERROR')

    if st.status_text:
        box.label(text=st.status_text[:170])
    box.label(text=(
        f"Fit: {st.n_fitted}/{len(scene.gnm_markers)} markers  |  "
        f"RMS {st.rms_mm:.2f} mm  |  {st.last_fit_ms:.0f} ms"))

    pr = box.box()
    pr.label(text="Demographic prior (optional):")
    rowp = pr.row(align=True)
    rowp.prop(st, "prior_sex", text="")
    rowp.prop(st, "prior_ethnicity", text="")
    rowp2 = pr.row(align=True)
    rowp2.prop(st, "prior_weight")
    rowp2.label(text=st.prior_status)

    db = box.box()
    db.label(text="Skull Alignment & Deformation (V13.2):")
    rowd = db.row(align=True)
    rowd.operator("gnm.prepare_skull", icon="MESH_DATA",
                  text="Prepare Skull")
    rowd.label(text=st.skull_status)
    db.operator("gnm.icp_deform", icon="SNAP_FACE",
                text="Align & Deform from Skull (ICP)")
    rowd2 = db.row(align=True)
    rowd2.prop(st, "dense_enabled")
    rowd2.prop(st, "dense_scalp_only")
    rowd3 = db.row(align=True)
    rowd3.prop(st, "dense_strength")
    rowd3.prop(st, "dense_nose_weight")
    if st.dense_status:
        db.label(text=st.dense_status[:170])
    if st.gerasimov_status:
        db.label(text=st.gerasimov_status[:170])
    db.label(text="Workflow: prepare skull -> ICP (0+ markers) -> markers")

    row = box.row(align=True)
    row.operator("gnm.pick_gnm_vertex", icon="RESTRICT_SELECT_OFF",
                 text="Pick GNM Vertex")
    row.operator("gnm.clear_gnm_override", text="", icon="X")
    row.operator("gnm.delete_marker", text="", icon="TRASH")

    box.operator("gnm.export_landmark_json", icon="EXPORT",
                 text="Export Updated JSON Map")

    sub = box.box()
    sub.label(text="Advanced:")
    sub.prop(st, "update_hz")
    sub.prop(st, "lambda_min")
    sub.prop(st, "lambda_max")
    sub.prop(st, "dense_max_rows")
    sub.prop(st, "clip_sigma")
    sub.prop(st, "prior_dir")
    box.label(text="Green=reviewed map; orange=needs review;")
    box.label(text="purple=manual; grey=documentation only;")
    box.label(text="red=no correspondence, cyan=Gerasimov pronasale (diag).")


def _is_mm_scene(scene):
    return scene.unit_settings.system == 'METRIC' and abs(scene.unit_settings.scale_length - 0.001) < 1e-8


def _export_markers(scene, path):
    if not _is_mm_scene(scene):
        raise ValueError("Expected metric scene scale 0.001: 1 Blender coordinate = 1 mm")
    ok, message = _ensure_cranio(scene.gnm_live.npz_path)
    if not ok:
        raise ValueError(message)
    model_path = bpy.path.abspath(scene.gnm_live.npz_path)
    if not os.path.isfile(model_path):
        raise ValueError("Select the local gnm_head.npz before exporting")
    model_digest = _core_module('validation').sha256_file(model_path)
    if model_digest != _core_module('backend.gnm_backend').OFFICIAL_V3_SHA256:
        raise ValueError("The built-in marker map requires the reviewed GNM v3 asset")
    rows = []
    for item in scene.gnm_markers:
        vid = _resolve_vertex(item)
        row = dict(label=item.label, vertex=vid if vid is not None else '',
                   placed=int(item.is_placed), x='', y='', z='', weight=_weight_of(item.label, item),
                   tissue_source=item.tissue_source, use_for_fit=int(item.use_for_fit),
                   bone_status=item.bone_status, mapping_reviewed=int(item.mapping_reviewed),
                   mapping_source='operator-selected' if item.gnm_vertex_override >= 0 else _VERTEX_DATA.MAPPING_REVISION,
                   marker_notes=item.marker_notes)
        if item.is_placed:
            if vid is None:
                raise ValueError(f"No model correspondence: {item.label}")
            bone = item.bone_empty.matrix_world.translation
            target = item.target_empty.matrix_world.translation
            if abs((target - bone).length - item.tissue_depth_mm) > 0.05:
                raise ValueError(f"{item.label}: target distance differs from tissue depth; review or re-place marker")
            row.update(x=target.x, y=target.y, z=target.z,
                       bone_x=bone.x, bone_y=bone.y, bone_z=bone.z,
                       tissue_depth_mm=item.tissue_depth_mm)
        rows.append(row)
    meta = {"addon_version": '.'.join(map(str, bl_info['version'])),
            "blender_version": bpy.app.version_string,
            "model_sha256": model_digest,
            "skull_source": scene.gnm_settings.sursa_fisier,
            "scene_scale_length": scene.unit_settings.scale_length,
            "requested_marker_set": scene.gnm_settings.marker_set,
            "marker_count": len(scene.gnm_markers),
            "mapping_revision": _VERTEX_DATA.MAPPING_REVISION,
            "tissue_reference": _core_module('paper_reference').reference_metadata(),
            "cranial_modification": scene.gnm_settings.cranial_modification,
            "case_notes": scene.gnm_settings.case_notes,
            "plane_marker_labels": [item.label for item in _plane_markers(scene)],
            "restoration_regions": _restoration_records(scene),
            "target_construction": "bone plus operator-reviewed depth/direction; local normal is initial heuristic"}
    _core_module('io_csv').write_marker_csv_v3(path, rows, meta)
    # Validate exactly what the CLI will consume, including manual overrides.
    backend = _core_module('backend').GNMBackend(model_path)
    _core_module('io_csv').read_marker_csv(path, backend.index_to_label, backend.landmark_vertex_map)


_OFFLINE = {"process": None, "log": None, "scene": None, "folder": None}


def _stop_offline():
    process = _OFFLINE.get('process')
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except Exception:
            process.kill()
            process.wait(timeout=2)
    if _OFFLINE.get('log') is not None:
        _OFFLINE['log'].close()
    _OFFLINE.update(process=None, log=None)
    if bpy.app.timers.is_registered(_offline_poll):
        bpy.app.timers.unregister(_offline_poll)


def _offline_poll():
    from pathlib import Path
    process = _OFFLINE.get('process')
    if process is None:
        return None
    code = process.poll()
    if code is None:
        return 0.5
    _OFFLINE['log'].close()
    _OFFLINE.update(process=None, log=None)
    scene = bpy.data.scenes.get(_OFFLINE['scene'])
    if scene is None:
        return None
    folder = Path(_OFFLINE['folder'])
    if code != 0:
        scene.gnm_settings.offline_status = f"Failed ({code}); see {folder / 'run.log'}"
        return None
    try:
        report = json.loads((folder / 'face_report.json').read_text(encoding='utf-8'))
        if report.get('status') != 'completed':
            raise ValueError('Incomplete run report')
        if report['outputs']['output']['sha256'] != _core_module('validation').sha256_file(folder / 'face.obj'):
            raise ValueError('Output checksum mismatch')
        # Our OBJ writer uses world-mm v/f records; do not invoke an importer
        # whose axis/unit defaults may silently rotate or rescale the result.
        vertices, faces = [], []
        with (folder / 'face.obj').open(encoding='utf-8') as stream:
            for line in stream:
                parts = line.split()
                if parts and parts[0] == 'v':
                    vertices.append(tuple(map(float, parts[1:4])))
                elif parts and parts[0] == 'f':
                    faces.append(tuple(int(x) - 1 for x in parts[1:4]))
        mesh = bpy.data.meshes.new('GNM Offline Result')
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new('GNM_Offline_' + folder.name, mesh)
        obj['gnm_report'] = str(folder / 'face_report.json')
        scene.collection.objects.link(obj)
        scene.gnm_settings.offline_status = f"Completed; RMSE {report['metrics']['final_fit']['rmse_mm']:.2f} mm"
    except Exception as exc:
        scene.gnm_settings.offline_status = f"Result import failed: {exc}"
    return None


def _selected_python(scene):
    selection = os.path.expandvars(os.path.expanduser(scene.gnm_settings.python_executable.strip().strip('"')))
    return bpy.path.abspath(selection) if selection.startswith('//') else selection


def _check_external_python(scene):
    info = _core_module('external_python').inspect_python(_selected_python(scene))
    scene.gnm_settings.python_executable = info['executable']
    version = '.'.join(map(str, info['version']))
    scene.gnm_settings.python_status = f"Python {version}, {info['bits']}-bit; numpy/scipy/trimesh OK"
    return info


class GNM_OT_check_python(Operator):
    bl_idname = 'gnm.check_python'
    bl_label = 'Check Python Environment'

    def execute(self, context):
        try:
            _check_external_python(context.scene)
            self.report({'INFO'}, context.scene.gnm_settings.python_status)
            return {'FINISHED'}
        except ValueError as exc:
            context.scene.gnm_settings.python_status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class GNM_OT_run_offline(Operator):
    bl_idname = 'gnm.run_offline'
    bl_label = 'Run Offline Fit and Import'

    @classmethod
    def poll(cls, context):
        return (_OFFLINE.get('process') is None and
                sum(item.is_placed and item.use_for_fit for item in context.scene.gnm_markers) >= 4)

    def execute(self, context):
        import uuid
        from pathlib import Path
        scene = context.scene
        settings = scene.gnm_settings
        try:
            if not settings.python_executable or not settings.case_directory:
                raise ValueError('Select the external Python executable and case output folder')
            # Fail before creating a case folder or launching the fit. In
            # particular, .py/ELF files cannot be executed by Windows.
            info = _check_external_python(scene)
            root = Path(__file__).resolve().parent
            folder = Path(bpy.path.abspath(settings.case_directory)) / (
                datetime.datetime.now().strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8])
            folder.mkdir(parents=True, exist_ok=False)
            _export_markers(scene, str(folder / 'markers.csv'))
            arguments = ['--input', str(folder / 'markers.csv'),
                       '--npz', bpy.path.abspath(scene.gnm_live.npz_path),
                       '--output', str(folder / 'face.obj'),
                       '--regularization', 'auto' if scene.gnm_live.loo_auto else 'adaptive',
                       '--lambda-base', str(scene.gnm_live.lambda_base),
                       '--lambda-min', str(scene.gnm_live.lambda_min),
                       '--lambda-max', str(scene.gnm_live.lambda_max)]
            log = (folder / 'run.log').open('w', encoding='utf-8')
            try:
                process = _core_module('external_python').start_pipeline(
                    info, root / 'gnm_reconstruct.py', arguments, log)
            except Exception:
                log.close()
                raise
            _OFFLINE.update(process=process, log=log, folder=str(folder), scene=scene.name)
            settings.offline_status = 'Running; ' + str(folder)
            bpy.app.timers.register(_offline_poll, first_interval=0.5)
            return {'FINISHED'}
        except (ValueError, OSError, ImportError) as exc:
            settings.offline_status = 'Cannot start: ' + str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class GNM_OT_cancel_offline(Operator):
    bl_idname = 'gnm.cancel_offline'
    bl_label = 'Cancel Offline Fit'

    @classmethod
    def poll(cls, context):
        return _OFFLINE.get('process') is not None

    def execute(self, context):
        _stop_offline()
        context.scene.gnm_settings.offline_status = 'Cancelled; partial files retained in case folder'
        return {'FINISHED'}


_classes = (
    GNMSettings, GNMMarkerItem, GNMRestorationRegion,
    GNM_OT_region_add, GNM_OT_region_remove, GNM_UL_restoration_regions, GNM_OT_audit_landmarks,
    GNM_OT_import_setup, GNM_OT_init_markers,
    GNM_OT_place_marker, GNM_OT_next_unplaced, GNM_OT_toggle_plane_preview,
    GNM_OT_recenter_on_plane, GNM_OT_asymmetry_report, GNM_OT_session_report,
    GNM_OT_capturi_standardizate, GNM_OT_mirror_reconstruct, GNM_OT_export_csv,
    GNM_UL_markers, GNM_PT_panel, GNM_OT_run_offline, GNM_OT_cancel_offline,
    GNM_OT_check_python, GNM_OT_apply_paper_tissues,
    # V13:
    GNMLiveSettings, GNM_OT_setup_dual_viewports, GNM_OT_toggle_skull_overlay,
    GNM_OT_load_live_model, GNM_OT_toggle_live, GNM_OT_delete_marker,
    GNM_OT_pick_gnm_vertex, GNM_OT_clear_gnm_override,
    GNM_OT_export_landmark_json,
    # V13.2:
    GNM_OT_prepare_skull, GNM_OT_icp_deform,
)

def register():
    for cls in _classes: bpy.utils.register_class(cls)
    bpy.types.Scene.gnm_settings = PointerProperty(type=GNMSettings)
    bpy.types.Scene.gnm_markers = CollectionProperty(type=GNMMarkerItem)
    bpy.types.Scene.gnm_marker_active_index = IntProperty(default=0)
    bpy.types.Scene.gnm_live = PointerProperty(type=GNMLiveSettings)
    bpy.types.Scene.gnm_restoration_regions = CollectionProperty(type=GNMRestorationRegion)
    bpy.types.Scene.gnm_restoration_active_index = IntProperty(default=0)
    # V13: reset fingerprint-uri la incarcarea unui .blend (persistent +
    # dedup, pentru a supravietui reload-ului F8 fara dubluri).
    for h in list(bpy.app.handlers.load_post):
        if getattr(h, "__name__", "") == "_gnm_live_on_load_post":
            bpy.app.handlers.load_post.remove(h)
    bpy.app.handlers.load_post.append(_gnm_live_on_load_post)

def unregister():
    # Stop the external process, preview timer and handlers first.
    _stop_offline()
    try:
        _stop_live()
    except Exception:
        pass
    for h in list(bpy.app.handlers.load_post):
        if getattr(h, "__name__", "") == "_gnm_live_on_load_post":
            bpy.app.handlers.load_post.remove(h)
    if hasattr(bpy.types.Scene, "gnm_live"):
        del bpy.types.Scene.gnm_live
    del bpy.types.Scene.gnm_restoration_regions
    del bpy.types.Scene.gnm_restoration_active_index
    for cls in reversed(_classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.gnm_settings
    del bpy.types.Scene.gnm_markers
    del bpy.types.Scene.gnm_marker_active_index

if __name__ == "__main__":
    register()
