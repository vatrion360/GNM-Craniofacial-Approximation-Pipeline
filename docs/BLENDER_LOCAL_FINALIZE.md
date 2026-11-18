# Finalize Local Fit (New Mesh)

Use **GNM Live Reconstruction → Finalize Local Fit (New Mesh)** to compute a
neutral corrected face directly in Blender, without exporting markers, starting
an external interpreter, or enabling continuous preview. This command performs a
fresh statistical fit: its inputs are the current placed markers and live settings,
not the displayed mesh, previous ICP result or a presentation copy.

1. Load the official GNM v3 model and map for this case. Use Object Mode and the
   metric scene scale 0.001. Review marker placements, weights and tissue sources.
2. Include at least four mapped markers. Bone/target distances must still match
   recorded depths. If using mandibular constraints, review the articulation.
3. To use dense constraints, enable the live dense option and prepare the enabled
   bone sources with reviewed normals. Re-prepare after changes. Missing regions
   are not completed; a requested dense mode without accepted rows is refused.
4. Press **Finalize Local Fit (New Mesh)** once. In the Outliner, locate the new
   object ending in `_Finalized`. It overlaps the live face; hide either object
   to inspect the other, or choose the new mesh as the post-fit presentation
   source. Each click creates an independent copy. Blender Undo/Redo removes or
   restores the operation. The original face, bones and markers remain available.

The action runs synchronously on click and may pause the UI, particularly with
dense sampling or LOO. It never runs during panel redraw or marker dragging.
Finalization rebuilds the identity from model data, with the live subspace,
lambda settings, prior and enabled craniometric skin controls. It then uses the
shared B1.2 centre preparation and the NumPy B1.1 solver. Caps, damping, centre
budgets and random seed use existing pipeline defaults. It does not inherit the
offline panel's switches, profile refinement, manually sculpted vertices or an
ICP-only pose. A supplied prior or source that cannot be verified is not silently
replaced with a different fit.

The neutral output uses the original triangular topology, world-mm coordinates,
identity object transform and Blender float32 vertex storage. Its fit transform
and identity coefficients are retained for GNM presentation copies. The mesh's
object property `gnm_local_finalize_record` contains the JSON record: model/map
and selected prior hashes, case and marker/source data, active settings,
measurements, lambda and solver diagnostics, ordered centres and prescribed
vectors, per-marker residuals, stored-coordinate SHA-256 and storage rounding.
To inspect it in Blender's Python Console, select the finalized copy and run:

```python
import bpy, json
r = json.loads(bpy.context.object["gnm_local_finalize_record"])
print(r["geometry_quality"]["status"], r["local_displacement"], r["scope"])
```

Geometry QC checks collapsed triangles and reversed normals relative to the
pose-aligned reference on the statistical and stored final surfaces.
`needs_review` retains the copy for inspection and is shown as a warning. Basic
checks are not a contact/penetration or anatomical test. Unbound legacy markers
have null source identifiers; review flags and tissue notes are recorded as
supplied. Bound markers whose geometry cannot be verified are refused. The
result is a scene object with a research record, not a gated scientific export
or an offline completion report. Use the offline workflow for full geometry QC
and saved-fit export policies. CT evaluation remains manual.

## Verification

The installed-ZIP Blender integration compares every stored vertex with a
separate CLI fit using the same synthetic marker fixture, adaptive lambda and
local correction. The engineering acceptance limit is 0.01 mm; the test also
checks unchanged source geometry, rollback on invalid provenance, stale-source
refusal, and Blender Undo/Redo. NumPy tests exercise sparse dense support,
refitting after edits and incomplete inputs. These fixtures test software, not
accuracy on people. Dense Blender and CLI acquisition use different bone samples;
identical dense inputs are required for a numerical backend comparison.
