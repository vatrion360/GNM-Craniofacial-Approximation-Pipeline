# A7.1 — Derived approximation record (first increment)

Base: `be6c2fcbe684e6df8c0eaaf896b02436fe11a7db` (PR #37 merged).
Target: `feature/uncertainty-calibration-harness`.

## Changes

- `cranio/record.py`: explicit standalone export of a derived view of the canonical
  schema-2 pipeline report. Verify the four output hashes; preserve scientific
  data/provenance; separate timestamps, paths and volatile TXT hashes.
- `tests/test_record.py`: 44 synthetic/software cases covering integrity,
  determinism, moved Windows/POSIX bundles, malformed data, source/output drift,
  unknown assessments, prior/case metadata and operator-approved RO/EN text.
- `tests/test_packaging.py`: require the module in the Blender ZIP.
- README, changelog, task comparison and `APPROXIMATION_RECORD.md`: opt-in usage,
  options, scientific interpretation, determinism and integrity limits.

The fit, model asset, defaults, CSV formats and Blender operators are unchanged.
The existing run report remains authoritative. No new scientific values or assets.

## Verification

- Before feature tests: existing suite **976 passed, 1 skipped** (37.10 s).
  The earlier pre-edit baseline was also 976 passed / 1 skipped.
- After: **1020 passed, 1 skipped** (36.46 s), including the 44 new cases.
  One host-installed pytest plugin emits a CallSpec2 deprecation warning.
- Both runs used the official GNM v3.0 asset:
  `e3710378cbf8c765f79a9cef5732376fc995f52b5541195e8945dacaaa5c43de`.
- Ruff passed. Wheel, sdist and Blender ZIP builds succeeded.
- Runtime: Python 3.12; NumPy 2.3.5, SciPy 1.17.0, trimesh 5.2.0,
  pytest 9.2.0. Linux; OPENBLAS_NUM_THREADS=1.
- Local Blender startup was unavailable (the supplied/extracted executable failed
  before tests, exit 139). No local Blender success is claimed.
- Base GitHub Actions runs 42012700525 (Python and packaging) and 42012700589
  (Blender integration) succeeded. Feature-specific Windows/Linux CI is required
  on this PR and its status is reported in the PR.

## Scope and remaining work

This is the first A7.1 increment, not completion of all A7 acceptance criteria.
It produces a derived JSON, concise TXT and provenance envelope without replacing
or automatically modifying pipeline reports. Automatic Blender integration,
explicit uncertainty/calibration links, validity-domain comparison, export modes
and scientific blocking/override policies remain separate work.

No limitations paragraph has been approved by the user. The optional manifest
requires supplied RO/EN wording, revision and explicit operator declaration;
otherwise the record says not_configured. Unknown assessment fields remain
not_assessed. No independent scientific authorization is inferred.

Input/model hashes are copied, not revalidated. The four output files are checked
against the supplied report; this is integrity checking, not authentication or CT
validation. CT evaluation remains manual and no new subject-level claims are made.
