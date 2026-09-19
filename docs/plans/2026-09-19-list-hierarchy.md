# Preserve Markdown list hierarchy

Status: Implemented

## Scope

Fix the shared list parser, which currently discards indentation and flattens
children into their parents' list. Preserve ordered/unordered nesting, sibling
order, indented continuation text and ordered-list starting numbers. Keep ordinary
flat-list output compatible. No content rewriting or cloud document changes.

## Validation

- Parser regression cases for multiple levels, mixed list kinds, tabs, blank
  lines, continuation text and list boundaries.
- Focused browser harness and actual 30-page lab-mocap delivery: nested DOM,
  visible indentation, child counts, media loading and overflow.
- Regenerate changed HTML/build reports, including self-contained delivery.
- Run npm test and the course delivery QA; record screenshots.

## Evidence — 2026-09-19

- Source Markdown already contains child indentation; old parser discarded it.
  Changed only shared parsing, not the course wording, page IDs or media.
- Rebuilt `examples/lab-mocap-course/index.html` with `build_delivery.py`.
  Preserved 30 pages and 39 embedded images. Existing long-title warnings remain.
- `npm test`: 47 Python tests and all five browser suites pass.
- Focused harness and all four affected course pages verified at 1920×1080 and
  1280×720: direct child counts, real horizontal indentation and no card overflow.
- Actual course QA: failedImages=0, consoleErrors=[], diagnostics.issues=[],
  overflowSlides=[]. Screenshot review of both reported safety pages passed.
- Evidence: `work/list-hierarchy/verification.json`, PNGs in that directory,
  `work/list-hierarchy-tests.log`; full-course report under the OS temporary
  `golajahslide-lab-mocap-qa` directory.

## Archive separation — 2026-09-19

- Removed the browser test dependency on the private, evolving course. The standalone list hierarchy harness passes at both viewport widths.
- All 11 browser suites passed before tool commit. Full npm test ran 134 Python tests and retained 10 failures / 32 errors in Windows locking, filesystem and hash checks (work/archive-npm-test.log).
- Course sources are being moved to the private GolajahSlideArchive/Mocap-Tutorial repository; the old local example is ignored and retained as a backup.
