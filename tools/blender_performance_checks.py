"""Real Blender RNA/handler checks; layout facade needs no visible window."""
from types import SimpleNamespace
import bpy
import numpy as np


class HeadlessLayout:
    """Execute the production draw callback without a GPU UI region."""
    def __init__(self):
        self.labels = []
        self.props = []

    def box(self):
        return self

    def row(self, **kwargs):
        return self

    def label(self, **kwargs):
        self.labels.append(kwargs.get('text', ''))

    def operator(self, *args, **kwargs):
        return SimpleNamespace()

    def prop(self, *args, **kwargs):
        self.props.append(args[:2])

    def prop_search(self, *args, **kwargs):
        pass

    def template_list(self, *args, **kwargs):
        pass

    def separator(self):
        pass


def run_performance_checks(addon):
    previous = bpy.context.window.scene
    scene = bpy.data.scenes.new('Preview scheduling regression')
    bpy.context.window.scene = scene
    module = addon._core_module('blender_craniometry')
    original_snapshot, original_compute = addon._build_snapshot, addon._compute_fit
    original_hash = addon._core_module('validation').sha256_file
    original_manifest = addon._source_manifest
    try:
        addon._bind_case(scene)
        scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
        scene.gnm_settings.mandible_aligned = True
        module.initialize(scene)
        for i in range(4):
            marker = scene.gnm_markers.add()
            marker.label, marker.gnm_vertex_override = 'Test'+str(i), i
            for attr in ('bone_empty', 'target_empty'):
                obj = bpy.data.objects.new(marker.label+attr, None)
                scene.collection.objects.link(obj)
                obj.location = [i*10, i % 2*10, i % 3*10]
                setattr(marker, attr, obj)
        bpy.context.view_layer.update()
        scene.gnm_craniometry.weight = .5
        def forbidden(*args, **kwargs):
            raise AssertionError('Draw/drag callback accessed geometry or a model file')
        addon._build_snapshot = forbidden
        addon._core_module('validation').sha256_file = forbidden
        for enabled in (False, True):
            addon._LIVE.enabled = enabled
            layout = HeadlessLayout()
            addon._draw_live_section(layout, bpy.context)
            assert 'Included: 4; adaptive lambda = 12' in layout.labels
        # Endpoint review must expose the existing RNA fields and actual blockers
        # for both markers, without a source read or automatic case-data review.
        binding = scene.gnm_cranial_bindings['eu-eu']
        scene.gnm_craniometry.active_measurement = list(module.core.BY_KEY).index('eu-eu')
        binding.marker_a, binding.marker_b = 'Test0', 'Test1'
        binding.enabled = True
        for marker in list(scene.gnm_markers)[:2]:
            marker.bone_status = 'observed'
        before_review = [module._skin_marker_record(m) for m in scene.gnm_markers]
        addon._source_manifest = forbidden
        layout = HeadlessLayout()
        module.GNM_PT_craniometry.draw(SimpleNamespace(layout=layout), bpy.context)
        assert 'A: Test0' in layout.labels and 'B: Test1' in layout.labels
        assert layout.labels.count('Skin correspondence reviewed is not confirmed') == 2
        assert 'legacy-unvalidated' in ' '.join(layout.labels)
        for marker in list(scene.gnm_markers)[:2]:
            for field in ('bone_status', 'mapping_reviewed', 'tissue_source'):
                assert (marker, field) in layout.props
        assert [module._skin_marker_record(m) for m in scene.gnm_markers] == before_review
        addon._source_manifest = original_manifest
        binding.enabled = False
        print('BLENDER_CRANIOMETRY_DIAGNOSTICS_PASS: endpoint RNA controls, both blockers, no geometry reads or metadata changes')
        # A burst of 50 edits is cheap and deferred. The snapshot must read the
        # final positions, not the position of the first scheduling callback.
        addon._LIVE.model = SimpleNamespace()
        addon._LIVE.model_hash = 'a'*64
        addon._LIVE.scene_name = scene.name
        scene.gnm_live.settle_delay = 2.
        for i in range(50):
            scene.gnm_markers[0].target_empty.location.x = float(i)
            addon._request_refit(scene)
        assert addon._LIVE.pending is None
        addon._live_timer_tick()  # still inside the quiet interval
        assert addon._LIVE.refit_requested_at is not None
        bpy.context.view_layer.update()
        calls, fits = [], []
        def snapshot(current):
            calls.append(current.name)
            return original_snapshot(current)
        def fit(snap):
            fits.append(snap)
            return dict(status='min3', n=0)
        addon._build_snapshot, addon._compute_fit = snapshot, fit
        addon._LIVE.refit_requested_at -= 3.
        addon._live_timer_tick()
        assert len(calls) == len(fits) == 1
        assert fits[0]['targets'][0, 0] == 49.
        addon._live_timer_tick()
        assert len(calls) == 1  # no perpetual refit on timer ticks
        # The loaded model hash must be used; the forbidden disk hash remains.
        assert fits[0]['measurement_weight'] == .5
        # Bone-only annotations with disabled skin controls cannot queue a fit.
        scene.gnm_craniometry.weight = 0.
        addon._LIVE.refit_requested_at = None
        before = addon._fingerprint(scene)
        point = scene.gnm_cranial_points[0]
        point.notes = 'Annotation only'
        point.bone_status = 'observed'
        assert addon._fingerprint(scene) == before
        assert addon._LIVE.refit_requested_at is None
        # Re-enabling and disabling controls must each request a new fit.
        scene.gnm_craniometry.weight = .5
        assert addon._LIVE.refit_requested_at is not None
        addon._LIVE.refit_requested_at = None
        scene.gnm_craniometry.weight = 0.
        assert addon._LIVE.refit_requested_at is not None
        # A validation error is reported after settling and never reaches fit.
        def invalid(current):
            raise ValueError('Synthetic stale source geometry')
        addon._build_snapshot = invalid
        addon._LIVE.refit_requested_at -= 3.
        addon._live_timer_tick()
        assert 'stale source geometry' in scene.gnm_live.status_text
        assert len(fits) == 1
        addon._request_refit(scene)
        addon._stop_live()
        assert addon._LIVE.refit_requested_at is None
        np.testing.assert_equal(len(fits), 1)
        print('BLENDER_PREVIEW_RESPONSIVENESS_PASS: redraw, debounce, latest edit, disabled controls, hash, stop')
    finally:
        addon._build_snapshot, addon._compute_fit = original_snapshot, original_compute
        addon._core_module('validation').sha256_file = original_hash
        addon._source_manifest = original_manifest
        addon._gnm_live_on_load_post(None)
        bpy.context.window.scene = previous
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)
