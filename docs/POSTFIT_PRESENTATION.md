# Post-fit presentation: native GNM controls and UVs

Available in add-on 19.0.0 / package 5.0.0rc10. This Blender-only stage makes
an independent presentation copy after a completed live or offline fit. It
does not change the reconstruction objective, marker measurements or offline
exports. The retained neutral fit is the surface to use for scientific evaluation.

## Workflow

1. Finish and inspect the fit. Choose the final GNM surface, including local
   correction if used. Keep the reviewed `gnm_head.npz` selected in the add-on.
2. Open **GNM Markers → Post-fit Presentation / GNM UV**. Set **Fitted source**
   to that object and press **Create Presentation Copy**. An empty source field
   uses the active object. Live fitting stops. The original is retained and
   hidden in the viewport and render; use the Outliner to unhide it when needed.
3. Under **Controls**, choose expression/tongue/pupils, teeth shape or eye shape.
   Search the native component names in the list. Adjust one or more **Offset**
   values; optionally edit either eye's axis-angle vector, in radians.
4. Choose **Max combined shift (mm)** and press **Apply Preview**. Changes are
   computed only on this action, not on every slider movement. The status reports
   the applied maximum and attenuation factor. Inspect lips, teeth and eyelids.
5. **Reset to Frozen Neutral** zeros the controls and restores the saved neutral
   coordinates exactly at Blender mesh precision. Repeated Apply operations start
   from this same neutral; they do not accumulate deformation.
6. Choose **Texture region**, then **Load GNM UV Texture**. Select a local image
   that matches the GNM UV layout. Use Material Preview or Rendered shading.
   Repeat for other regions as needed. Images and model weights are not bundled.
7. Save the `.blend`, original fit report and scientific exports. For portable
   image paths, use Blender's Pack Resources. The local model is required to
   apply new controls after reopening. Export the evaluated presentation through
   Blender separately; ordinary OBJ export does not preserve the edit metadata.

If the model moves, update **Presentation model** to its new local path.
Keep its transform unchanged and do not add modifiers, parent it, edit its Basis,
reorder vertices or change its shape-key structure before applying controls.
An older live scene needs one successful refit to capture identity/transform
metadata. An imported offline result uses its completed JSON report; retain that
report until the presentation is created. Remeshed/decimated surfaces are rejected.

## Controls actually present in the reviewed asset

The supported asset is the checksum-pinned GNM Head v3 archive documented in
[INSTALL](INSTALL.md). Its arrays contain the following controls:

| Control family | Exposed components | Interpretation |
| --- | ---: | --- |
| Left eye-region expression | 100 | Native statistical expression offsets |
| Right eye-region expression | 100 | Native statistical expression offsets |
| Lower-face expression | 150 | Native statistical expression offsets |
| Tongue | 32 | `tongue_mean` plus 31 numbered offsets |
| Pupils | 1 | Native `pupils_000` expression component |
| Teeth identity | 80 | Offsets from fitted teeth shape, limited to teeth/gums |
| Eye identity | 3 | Offsets from fitted eye shape, limited to eyes |
| Eye rotation | Two three-component vectors | Axis-angle rotations about fitted eye pivots |

The 170 head-identity coefficients and head/neck rotation are locked. There is
no separate jaw joint in this asset. These are numbered statistical components,
not named emotions or independently calibrated anatomical dimensions. The
upstream emotion sampler and its separate learned assets are not integrated.
The control intervals (offsets ±3; each axis-angle component ±π/6 rad) are
engineering restrictions, not validated physiological ranges. Teeth/eye offsets
are relative to the fitted coefficients, not new absolute coefficients.

## Preservation and bounded deformation

Let the final neutral world surface be `F`, the fitted similarity transform
`T(x) = s R x + t`, and `C = inverse(T)(F)`. The full `C` is retained, including
non-statistical corrections; it is not replaced by a newly generated GNM surface.
The editor adds native expression offsets and locally masked teeth/eye identity
offsets to `C`, then applies GNM hierarchical linear blend skinning for the eyes.
Head/neck transforms stay fixed. Eye pivots follow the fitted identity and the
final residual through the asset's joint regressor. That residual transport is
an implementation choice for attaching native controls to the corrected surface,
not an independently validated anatomical estimate of the eye centres.

If the candidate posed canonical surface is `P`, the world displacement is
`D = s R (P - C)`. For selected bound `L`, all controls share one attenuation:

```text
alpha = min(1, L / max_vertex(norm(D_vertex)))
preview = F + alpha * D
```

With no displacement, `alpha = 1`. Zero controls or a zero bound return `F`
directly. The default bound is 3 mm; the UI permits 0–20 mm. This bound applies
to the combined result in world millimetres, subject to Blender float32 storage
precision. Attenuating a rotation blends its displacement toward neutral; it is
not equivalent to scaling its angle. UVs and vertex connectivity stay unchanged.

The native teeth basis has very small effects outside teeth/gums. This editor
masks those offsets to the corresponding components. The native expression
bases retain their full support. Therefore presentation expressions can move
landmark vertices away from their fitted targets. Marker objects and original
measurement values are unchanged, but landmark agreement is not enforced on
the expressive copy. The cap is not collision detection, skull clearance,
preservation of every cranial chord, or evidence that the appearance is correct.
Review dental occlusion, lips, eyelids and eye placement visually. Dental status,
skin/iris colour, scars and historical appearance are not inferred by this stage.

## UV topology and materials

The `GNM_UV` layer is copied from `triangle_uvs` by **face corner**, preserving
seams; a per-vertex UV assignment would lose them. Both vertex count and ordered
triangle indices must match the pinned model (17,821 vertices; 35,324 triangles).
Native eye UV overlap is intentional. Independent material slots distinguish
skin, teeth/gums, tongue, eye interiors and eye exteriors. The eye-exterior
material uses transmission; the others use simple Principled shaders. These
are presentation defaults, not measured reflectance models.

To prepare a paint template, select the copy in Blender's UV Editing workspace,
select the relevant faces/material, and use **UV → Export UV Layout**. Paint or
supply a legally usable image against that layout, then load it for the same
region. Loading an image supplies base colour only; it does not synthesize a
texture, estimate appearance from the skull, or import a full PBR material set.

## Persistence, implementation and evidence

`cranio/postfit.py` contains the NumPy geometry; `cranio/blender_postfit.py`
handles main-thread Blender access. The latter stores a frozen Basis shape key,
one preview shape key, component offsets, source name, model hash, fitted
identity, transform, neutral-coordinate SHA-256 and last applied displacement
statistics/timestamp. No download, TensorFlow runtime, fit worker or additional
offline deformation stage is introduced. These records live in the `.blend`;
the original scientific JSON/OBJ exports are not rewritten. Keep both records
when disseminating a presentation scenario.

The asset has zero pose-corrective coefficients. The loader verifies its SHA-256,
uses `allow_pickle=False` and refuses an unsupported nonzero corrective regressor.
The model is cached after first load; panel drawing does not read model files or
evaluate deformation. Explicit Apply still computes on Blender's main thread.

See [revision-specific validation](VALIDATION.md). Tests establish software
invariants and agreement with upstream skinning, not subject-level accuracy.
For manual acceptance on the target workstation, compare the copy to its neutral
source, inspect each control family, verify the image seam layout, test Undo and
save/reopen, and inspect the evaluated exported mesh in the destination software.
