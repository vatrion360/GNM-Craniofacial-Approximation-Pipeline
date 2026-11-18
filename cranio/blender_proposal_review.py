"""Explicit, per-scene review decisions for generated bone landmark proposals."""
import hashlib
import json

import bpy
from bpy.props import (CollectionProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)
import numpy as np

from . import blender_proposals as proposals

RECEIPT = 'gnm_bone_proposal_review'


class GNMProposalItem(bpy.types.PropertyGroup):
    label: StringProperty()
    score: FloatProperty()
    decision: StringProperty(default='pending')


class GNMProposalQueue(bpy.types.PropertyGroup):
    rows: CollectionProperty(type=GNMProposalItem)
    index: IntProperty(default=0)
    text: PointerProperty(type=bpy.types.Text)
    digest: StringProperty()
    case_id: StringProperty()
    target: PointerProperty(type=bpy.types.Object)
    reference: PointerProperty(type=bpy.types.Object)


def _hash(text):
    return hashlib.sha256(text.as_string().encode('utf8')).hexdigest()


def initialize(context, record, text):
    """Freeze the eligible list. UI sorting uses geometric support, not probability."""
    scene = context.scene
    q = scene.gnm_proposal_queue
    q.rows.clear()
    q.text, q.digest = text, _hash(text)
    q.case_id = proposals._api._case_token(scene)[1]
    q.target, q.reference = context.active_object, scene.gnm_atlas_skull
    for score, label in sorted((r['support_score'], label) for label,r in record['sites'].items()
                               if r['status'] == 'needs_review'):
        row = q.rows.add()
        row.label, row.score = label, score
    q.index = 0


class GNM_UL_proposal_queue(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        layout.label(text=item.label)
        layout.label(text=f'{item.score:.2f} | {item.decision}')


def _selection(context):
    scene = context.scene
    q = scene.gnm_proposal_queue
    if (not q.text or not q.case_id or q.case_id != scene.gnm_settings.case_id
            or not 0 <= q.index < len(q.rows)):
        raise ValueError('Generate a proposal snapshot for this case first')
    row = q.rows[q.index]
    if row.decision != 'pending':
        raise ValueError('This proposal has already been reviewed')
    if _hash(q.text) != q.digest:
        raise ValueError('Proposal text has changed; regenerate the queue')
    record = json.loads(q.text.as_string())
    site = record['sites'].get(row.label, {})
    if site.get('status') != 'needs_review':
        raise ValueError('Unsupported or missing proposal; no placement possible')
    return q, row, record, site


def _advance(q):
    q.index = next((i for i,r in enumerate(q.rows) if r.decision == 'pending'), q.index)


def review(context, action):
    scene = context.scene
    q, row, record, site = _selection(context)
    if action == 'SKIP':
        row.decision = 'rejected'
        _advance(q)
        return
    if (not q.target or context.active_object != q.target or not q.reference
            or scene.gnm_atlas_skull != q.reference):
        raise ValueError('Activate the original registered target and select the original atlas')
    # Recheck sources, annotations, anchors, patch masks, limits and articulation
    # on explicit actions only. Never re-fit ICP or infer validity on panel redraw.
    binding, surface, available = proposals.snapshot(context, review_inputs=True)
    if any(record.get(key) != value for key,value in binding.items()):
        raise ValueError('Registration inputs changed; generate new proposals')
    item = next((m for m in scene.gnm_markers if m.label == row.label), None)
    if item is None or row.label not in available or item.bone_empty or item.target_empty or item.peg_object:
        raise ValueError('Marker is already occupied; no existing placement will be replaced')
    if action == 'LOCATE':
        scene.cursor.location = site['world_mm']
        return
    adjusted = action == 'ADJUST'
    xyz = np.asarray(scene.cursor.location if adjusted else site['world_mm'], dtype=float)
    if not np.isfinite(xyz).all():
        raise ValueError('Invalid world coordinates')
    w, tf, tree, full, boundary, polygons = surface
    point, _, ix, gap = tree.find_nearest(xyz)
    closest = full.find_nearest(xyz)[0]
    tol = proposals.bvh_precision(w[tf[ix]])
    if gap > (binding['limits_mm']['surface_gap'] if adjusted else tol):
        raise ValueError('Point is off the observed patch; put the cursor on its surface')
    if np.linalg.norm(np.array(point)-closest) > tol:
        raise ValueError('Cursor hits a different bone surface; choose the matched patch')
    if proposals.open_edge(point, w, tf[ix], boundary):
        raise ValueError('Point lies on an open patch boundary; review on intact bone')
    # Scientific marker fields are left to the same placement path as a manual click.
    xyz = list(point)
    receipt = dict(label=row.label, decision='adjusted' if adjusted else 'confirmed',
        snapshot_sha256=q.digest, case_id=q.case_id, target_id=binding['target_id'],
        target_geometry_sha256=binding['target_geometry_sha256'], patch=binding['patch'],
        proposed_world_mm=site['world_mm'], accepted_world_mm=xyz, geometric_support=site['support_score'],
        observer_id=scene.gnm_settings.observer_id or None)
    encoded = json.dumps(receipt, allow_nan=False, sort_keys=True)
    normal = proposals._api._place_marker_at(context, item, point, q.target, int(polygons[ix]))
    item.bone_empty[RECEIPT] = encoded
    row.decision = receipt['decision']
    _advance(q)
    return normal['warnings']


class GNM_OT_review_proposal(bpy.types.Operator):
    bl_idname = 'gnm.review_proposal'
    bl_label = 'Review Selected Landmark Proposal'
    bl_options = {'UNDO'}
    action: EnumProperty(items=[(key,label,'') for key,label in [
        ('LOCATE','Show at 3D Cursor'), ('CONFIRM','Confirm Proposed Site'),
        ('ADJUST','Confirm Adjusted Cursor Site'), ('SKIP','Reject Without Placement')]])

    def execute(self, context):
        try:
            warnings = review(context, self.action)
            if warnings:
                self.report({'WARNING'}, '; '.join(warnings))
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def export_receipts(scene):
    """Attach the placement-time evidence only when a reviewed marker exists."""
    records = {}
    for m in scene.gnm_markers:
        if m.is_placed and RECEIPT in m.bone_empty:
            record = json.loads(m.bone_empty[RECEIPT])
            record['current_world_mm'] = list(m.bone_empty.matrix_world.translation)
            records[m.label] = record
    return {'proposal_reviews_at_placement': records} if records else {}


def draw(box, scene):
    q = scene.gnm_proposal_queue
    if not q.text:
        return
    box.label(text='Snapshot: '+q.text.name)
    if not q.rows:
        box.label(text='No supported candidates')
        return
    pending = sum(r.decision == 'pending' for r in q.rows)
    box.label(text=f'{pending}/{len(q.rows)} pending | lowest geometric support first')
    box.template_list('GNM_UL_proposal_queue','',q,'rows',q,'index',rows=3)
    if 0 <= q.index < len(q.rows) and q.rows[q.index].decision == 'pending':
        for key,label in [('LOCATE','Show at 3D Cursor'),('CONFIRM','Confirm Proposed Site'),
                          ('ADJUST','Confirm Adjusted Cursor Site'),('SKIP','Reject Without Placement')]:
            box.operator('gnm.review_proposal',text=label).action = key


_CLASSES = (GNMProposalItem, GNMProposalQueue, GNM_UL_proposal_queue, GNM_OT_review_proposal)


def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.gnm_proposal_queue = PointerProperty(type=GNMProposalQueue)


def unregister():
    del bpy.types.Scene.gnm_proposal_queue
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)
