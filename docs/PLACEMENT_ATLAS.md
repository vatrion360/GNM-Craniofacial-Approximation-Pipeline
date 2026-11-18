# Placement atlas (B2.1)

In **GNM Scientific Markers**, select a list row and toggle **Placement atlas for
selected marker**. This works with any of the three marker sets, without a GNM
model, a placed marker, or a reference mesh. The card follows the selected row;
the adjustment checkboxes and **Include in fit** are independent of it.

The atlas covers the 48 tissue-marker labels. It reuses the existing paraphrases
for the 32 Table 2 positions and identifies their source and table row. The
other 16 have no sourced definition in this catalogue; project placement notes
are shown separately when available. A missing caveat is not evidence of easy
or repeatable placement. All definitions are marked **needs expert review**.
The atlas does not certify a case marker, assign a depth or change a mapping.

For example, the card distinguishes the Suborbitale inferior-rim site from the
inherited Infraorbitale foramen site, and shows the source caveat for Midphiltrum.
Right and left refer to the catalogue label; a view from a mesh axis does not
establish anatomical orientation. Separate craniometry-only landmarks are not
part of this tissue-marker atlas.

## Optional local 3D reference

No reference skull, annotations or third-party weights are distributed. Use a
skull you have permission to use and annotations reviewed for that exact mesh.
The reference may be partial: you only need to annotate the sites you can locate.

1. Put the reference mesh in **a separate Blender scene in the same file**.
   It must not also be linked into the working case scene. A native polygon
   mesh is required. Finish the intended reference geometry before annotating
   it; modifiers and shape keys are not evaluated. Keep it in Object Mode
   when viewing the atlas. Do not use the fitted GNM head as a reference skull.
2. In the reference object's **Object Properties → Custom Properties**, add a
   string named `gnm_atlas_source`. Record the specimen/asset reference and
   the annotation source or reviewer; include attribution as appropriate.
3. In Edit Mode on the reference, select **one vertex on the reviewed bone
   site**. For each such site, create a vertex group named
   `ATLAS_REVIEWED:<exact marker label>`, and assign that vertex with positive
   weight. Example: `ATLAS_REVIEWED:Nasion`. This name denotes your explicit
   annotation of the reference, not independent validation. Leave uncertain
   and absent sites unassigned. Do not copy GNM facial vertex numbers.
4. Back in the working case, choose the **Reference skull** on the card,
   choose the local mesh axis to view from, and click **Refresh Reference
   View**. The shaded orthographic image is raycast against the actual skull
   polygons. A ring marks the projection of the annotated vertex only if the
   line to the viewer is clear. If the site is hidden, try another axis.
5. After editing a reference mesh or its annotations, refresh the view. The
   displayed image is a **last snapshot**, not a continuous evaluation. Undo,
   redo, file loads and addon shutdown discard cached previews. The optional
   reference assignment can be saved with the blend file.

An absent group, multiple assigned vertices, an invalid mesh or a missing
source produces a diagnostic and no image for that selection. The text card
remains usable. A reference image is a placement aid, not a proposal on the
case skull. It does not reflect, register or transfer a position, certify
missing bone, change the camera or write scene geometry. No fit runs and no
file is downloaded. Rendering is on explicit request and may take longer for
large scans; the mesh and ray tree are not read or rebuilt on panel redraw.

## Software checks

Catalogue tests distinguish source-backed definitions from legacy hints and
verify the orientation of all six local views. The installed-ZIP Blender test
uses only a synthetic tetrahedron to check annotation selection, the projected
highlight, occlusion from the opposite side, text-only fallback, case isolation
and unchanged marker state. No anatomical reference mesh or CT cases were used
for these tests. Placement repeatability and anatomical validation are separate.
