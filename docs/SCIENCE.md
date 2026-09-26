# Scientific basis and limits

## What the model estimates

The implementation estimates a **conditional geometric approximation**, given a neutral GNM head model, operator-supplied correspondences and tissue-target assumptions. It does not identify an individual. Sparse skull markers cannot determine all facial soft tissue, cartilage, adiposity, age-related changes, ears, hair, pigmentation or expression. A visually plausible GNM head is not evidence of subject-level accuracy.

Google describes GNM as a parametric statistical head model with separate identity, expression and pose controls [1]. This pipeline uses the neutral linear identity basis only. It has no learned, independently validated skull-to-face conditional distribution. The synthetic example tests software consistency, not that missing relationship.

## Anatomical correspondence and tissue targets

The operator constructs target `y_i = b_i + d_i n_i`, with bone point `b_i`, chosen tissue distance `d_i`, and direction `n_i`. A local surface normal is a convenient initial direction; it is **not automatically equivalent** to the direction used by an FSTT study. Bony alare, soft-tissue alare, orbit margins and canthi are not interchangeable definitions. Nasospinale/subnasale and prosthion/labrale-superius relationships need explicit anatomical reasoning. iBUG image landmarks do not establish those correspondences.

The inherited default depths, regional offsets and weights lack row-level study/table/direction/sample provenance. Those depths remain labelled `legacy-unvalidated`; this release does not invent citations or population standard deviations for them. Add-on 15 additionally supplies the explicitly cited Table 2 reference from Rangel-de Lazaro et al. (2026), with 32 positions and case/population qualifications; see [PDF_PROTOCOL](PDF_PROTOCOL.md). Its GNM correspondences are separately developed candidates, not results reported by that paper. The global FSTT synthesis of Hona & Stephan discusses pooled data and heterogeneity [2]. Consult the original study definitions before selecting a reference. A Romanian cohort paper is an additional relevant source, not an automatic default for every Romanian case [3].

Document source, definition, method, cohort applicability and uncertainty. Variation between individuals, placement error and tissue measurement error are distinct. Do not interpret a standard error of a population mean as individual tissue uncertainty. Do not treat broad GNM semantic categories as inferred ancestry or as a validated forensic prior. Optional demographic prior generation remains experimental and untested in this release.

## Implemented numerical stages

1. **Alignment.** Weighted, proper-rotation similarity alignment estimates positive scale, rotation and translation [4]. Collinear/coincident data are rejected; planar noncollinear configurations are permitted. A proper best fit can still have a large error for mirrored/mislabelled data; determinant alone is not a reliable anatomical test.
2. **Identity fitting.** Alternate alignment with weighted ridge least squares on `V(c) = mean + sum(c_k B_k)`. Radial Huber reweighting downweights large landmark residuals using a 10 mm threshold. The ridge objective is evaluated in model-mm coordinates; the Huber threshold is in world mm. Coefficients are clipped to the configured component limit. These are engineering choices, not calibrated probabilities. Coordinate-wise clipping is a heuristic projection, not an exact constrained MAP solver; component bounds do not define a joint credible region.
3. **Regularisation.** `auto` uses landmark-wise LOO while holding an all-marker fitted pose fixed. It also does not reproduce every optional dense/prior term within each fold. Therefore its scores are **conditional tuning diagnostics**, not an independent predictive validation. `cranio.evaluation` offers an outer landmark holdout that refits pose and identity from training points only; `auto` then tunes on that training subset.
4. **Optional dense constraints.** Nearest sampled skull points with normal/distance rejection and manually assigned region offsets. These are heuristic surface constraints, not a dense empirical FSTT field. Sampling is seeded. Missing bone, inner cortical tables, scan artifacts and reflected repairs can produce misleading correspondences. Work by Gietzen et al. explicitly constructs paired skull/skin statistics [5]; the present implementation does not reproduce that trained model.
5. **Optional local correction.** A 3-D polyharmonic interpolant with affine tail uses SciPy's `linear` kernel `-r`. Bookstein discusses the dimensional change from the 2-D thin-plate kernel to the 3-D radial kernel [6]; SciPy documents kernel and rank requirements [7]. The field magnitude is capped by `cap*tanh(magnitude/cap)` and damped in selected protected groups. This is a geometric adjustment: it can leave the GNM identity space and is not proof of improved accuracy. It is disabled by default.
6. **Nasal diagnostic.** The inherited two-tangent construction is informational only. It now uses explicit bone landmarks rotated into the fitted anatomical frame. Ullrich & Stephan discuss interpretation/repeatability [8], and a CT validation study evaluates that interpretation [9]. Those publications do not validate this implementation, its chosen vertices, its PCA tangent fit or its fallback. Treat fallback results as exploratory, not subject-specific prediction.

## Outputs and interpretation

For Euclidean residuals `r_i`, RMSE is `sqrt(mean(r_i^2))`. Mean, median, 95th percentile and maximum are separate quantities. Training-marker residuals measure agreement with the imposed targets, which themselves may be wrong. Outer holdout tests prediction of those targets, not independent face accuracy.

The PLY heatmap is **local displacement magnitude**. It is not tissue thickness, error against a known face, confidence, or an uncertainty interval. Its numeric property and per-run colour scale are recorded. Compare statistical and corrected meshes, and inspect anatomical plausibility beyond the marker sites.

No calibrated uncertainty surface is provided. To establish uncertainty, use repeated observers, plausible tissue/direction perturbations, model alternatives and independent paired skull/face cases. Any Monte Carlo spread must be labelled sensitivity to the chosen perturbation model until empirical coverage is established. A small fit residual or a synthetic round trip cannot substitute for these tests.

## References

1. Google GNM, official source and model schema: https://github.com/google/GNM/tree/915aa356c6a2247083e69a06e40dfe909d42435a . See the upstream technical report and citation there.
2. Hona TWT, Stephan CN. *Global facial soft tissue thicknesses for craniofacial identification (2023): a review of 140 years of data since Welcker's first study*. International Journal of Legal Medicine 138, 519–535 (2024; online 2023). https://doi.org/10.1007/s00414-023-03087-x
3. *Facial Soft Tissue Thickness Values for Romanian Adult Population*. Applied Sciences 13(10), 5949 (2023). https://doi.org/10.3390/app13105949 . Listed for source selection; no numeric table from this paper is embedded.
4. Umeyama S. *Least-squares estimation of transformation parameters between two point patterns*. IEEE TPAMI 13(4), 376–380 (1991). https://doi.org/10.1109/34.88573
5. Gietzen T et al. *A method for automatic forensic facial reconstruction based on dense statistics of soft tissue thickness*. PLOS ONE 14(1), e0210257 (2019). https://doi.org/10.1371/journal.pone.0210257
6. Bookstein FL. *Principal warps: thin-plate splines and the decomposition of deformations*. IEEE TPAMI 11(6), 567–585 (1989). https://doi.org/10.1109/34.24792
7. SciPy `RBFInterpolator` documentation. https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.RBFInterpolator.html
8. Ullrich H, Stephan CN. *On Gerasimov's plastic facial reconstruction technique: new insights to facilitate repeatability*. Journal of Forensic Sciences 56(2), 470–474 (2011). https://doi.org/10.1111/j.1556-4029.2010.01672.x
9. *Validation of the New Interpretation of Gerasimov's Nasal Projection Method for Forensic Facial Approximation Using CT Data*. PubMed PMID 26271796. https://pubmed.ncbi.nlm.nih.gov/26271796/

Primary source review date: 2026-09-25. The references motivate methods and review criteria; they do not constitute validation of this software.
