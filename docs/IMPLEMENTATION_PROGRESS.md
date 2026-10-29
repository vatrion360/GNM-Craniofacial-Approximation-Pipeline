# V19 implementation progress

The roadmap in TASKS_V19_REVIEW.md is a comparison against the audited base,
not a claim that all planned features are available. CT validation remains with
the project author; engineering tests do not establish anatomical accuracy.

## Atomic marker export and source attribution

Base: `6f31258250270f061230ed27f0b053236ee0d767` (PR #12 integrated).

- Changed `cranio/io_csv.py`, `cranio/export.py`, `addon_v13.py`: validate the
  closed temporary v3 file before replacement, retain previous outputs on failure,
  and show actual per-marker sources in the session report. V2 serialization is
  atomic without inventing a legacy mapping for validation.
- Tests: malformed reader fixtures still exercise the reader independently;
  writer tests cover invalid rows/metadata, streaming failures, locked destinations,
  Unicode/multiline notes and unchanged valid serialization. Installed Blender
  verifies failed-export preservation and session-source reporting.
- Before: 216 passed, 1 Windows-only skip; after: 228 passed, 1 Windows-only skip.
  Official GNM asset enabled. Ruff and Blender 4.5.0 Linux ZIP integration passed.
- No anatomical values, numerical defaults or model weights changed. No CT cases
  or interactive Windows acceptance were run. No open scientific choices in this task.
