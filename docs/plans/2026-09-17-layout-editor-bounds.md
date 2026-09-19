# Layout editor option contrast and bounds

Status: Implemented

## Goal and ownership

Fix unreadable native layout options and editor outlines that show preset geometry instead of the generated page. Own geometry and option styles in `src/web/features/layout-editor/`; the existing shell calls its focused measurement API.

## Non-goals

Do not redesign the editor, change saved overrides, or add browser dependencies. Preserve Python-only builds and single-file delivery.

## Acceptance

- Native select options have explicit contrasting foreground/background colors.
- Untouched cover and content outlines match actual containers at 1920 and 1280 viewport widths, independently of reveal transforms and stage scaling.
- Opening the editor does not persist a layout override; preset switching remains available.
- Regenerate examples, run the focused Harness and `npm test`.

## Validation

- 2026-09-17: focused browser test passed; all example HTML rebuilt, including the local lab-mocap-course self-contained delivery.
- Initial full suite found stale diagram-design HTML/SVG provenance; refreshed it with the supported `--render-diagrams` build path before rerunning.
- Full `npm test` passed: 26 Python tests plus presenter-focus, diagram-design, and layout-editor browser suites. The same geometry checks passed against the regenerated lab-mocap-course HTML. Explicit layout selection survives reload.
