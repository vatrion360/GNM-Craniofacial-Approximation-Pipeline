# A6 — First increment: paired prior audit

Base: `2c8b9428553447c47eaaa6456fc589040b9ccb77` (merged PR #34).
Branch: `feature/prior-comparison-audit`.

## Implemented

- `cranio/prior_compare.py`: two independent runs through the existing pipeline,
  no external prior versus explicit prior; mandatory operator rationale for this
  audit, input pinning, child artifact checks, shared target checks, final and
  statistical difference PLYs, JSON/TXT summary and explicit nonconvergence state.
- `cranio/config.py`, `gnm_reconstruct.py`, `cranio/pipeline.py`: opt-in flag and
  rationale plumbing; reason retained in ordinary prior-enabled JSON/TXT reports.
  The solver/default fitting path is unchanged.
- `cranio/protocol.py`: a case rationale is descriptive metadata, not a frozen
  numerical setting. Numerical prior weight/settings retain their existing role.
- `cranio/tissue_compare.py`: reuse the existing difference writer with an optional
  caption; default tissue-comparison caption/format remains unchanged.
- `tests/test_prior_compare.py`: 25 regression cases, including one official-model
  integration; `tests/test_packaging.py` verifies the module is in the addon ZIP.
- README and `docs/PRIOR_COMPARISON.md`: options, artifacts, interpretation and
  compatibility limits. This file records the task outcome.

## Verification — 2026-11-04

| Gate | Before source edits | After |
|---|---|---|
| Python suite with official model | 870 passed, 1 Windows-only skip (18.90 s) | 895 passed, 1 Windows-only skip (22.10 s) |
| Blender 4.5.0 Linux ZIP/model/external Python | Passed | Passed |
| Ruff / whitespace | — | Passed |
| Wheel, sdist, addon ZIP | — | Built |
| Installed wheel outside checkout | — | Complete CLI paired run passed with the official model, head subspace and synthetic unit prior |

Runtime: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0, pytest 9.2.0.
Model SHA-256 verified:
`e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
Blender archive verified against its official checksum manifest. The workspace
had reverted to an older checkout; published changes were recovered from GitHub,
and both baseline suites were rerun before these edits.

Regressions verify bit-identical child OBJ meshes versus corresponding standalone
runs at the same settings; identical geometry/metrics on repeated runs; zero
differences for a zero-mean/unit-scale synthetic prior with ordinary ridge;
unmodified input files and caller config; invalid/missing intent and priors;
no summary after nonzero QC exit, input drift or child mesh modification; explicit
nonconvergence status; separate statistical/final differences with local correction;
CLI Unicode rationale; and head-only inactivity of eye/teeth coefficients.
These are engineering checks, not validation of any demographic prior.

No CT or local Windows/interactive assessment was performed. Hosted Windows/Linux
CI reports separately. No prior weights, scientific reference values or human scans
are added to the repository.

## Deviations and pending A6 work

This completes the opt-in offline comparison/rationale portion, not all of A6.
Neutral/no-external-prior behavior was already the default; no default-changing PR
is needed. Existing standalone and Blender prior selection remain compatible and
do not automatically create this audit or require its rationale. A dedicated
Blender control and justification migration are pending.

Structured age-at-death metadata and reviewed tissue-table age-range handling are
also pending. No age parameter, age-conditioned depth change, demographic
classification or simulated ageing is introduced. Summary records explicitly
state the lack of an ageing model. Case/cohort applicability and legacy prior
component-order provenance remain human review responsibilities.

The comparison retains existing QC gates and reports algorithmic convergence;
neither implies scientific validity. It does not support a frozen protocol, nested
tissue comparison, profile refinement or automatic marker exclusion. Partial
outputs can remain after failure but lack the completed summary. Canonical A7
record consolidation, normal fit-report links and timestamps separated from
deterministic metrics remain future work. Existing per-run records are retained
and referenced by hashes, not replaced by a competing reconstruction record.
