# Diagram Design – Editorial Mermaid Pipeline

## Status

Implemented

## Goal

Integrate the agent-authored editorial drawing workflow from
[`cathrynlavery/diagram-design`](https://github.com/cathrynlavery/diagram-design)
with GolajahSlide so a Mermaid fence can keep its semantic source while using a
reviewable, hand-composed HTML/SVG artifact for slide delivery.

The default Mermaid CLI path remains compatible. Authors opt in with
`renderer: diagram-design`; ordinary builds continue to require only Python and
the delivered deck remains one self-contained HTML file.

## Non-goals

- Reimplement the full 29-type upstream skill as a deterministic layout engine.
- Call an LLM, fetch fonts, or load a diagram runtime from the delivered deck.
- Replace Mermaid CLI for existing fences that do not opt in.
- Add interactive editing of diagram geometry in the browser runtime.

## Ownership

- `.agents/skills/golajah-diagram-design/`: repository-scoped authoring workflow,
  Mermaid extractor, selected design references, template, and attribution.
- `build_slides.py`: renderer selection, HTML-to-SVG extraction, provenance,
  cache invalidation, and quality-report integration.
- `harnesses/diagram-design/`: focused editorial Mermaid scenario and checked-in
  authoring/delivery assets.
- `tests/`: build contracts and observable browser delivery checks.
- `docs/DIAGRAMS.md` and `README.md`: user-facing syntax and workflow.

## Acceptance gates

- [x] Existing Mermaid fences still use the pinned Mermaid CLI and retain their
  current output contract.
- [x] `renderer: diagram-design` requires a local self-contained HTML source,
  extracts its first inline SVG, and records both Mermaid and HTML provenance.
- [x] A normal Python-only build detects a stale editorial asset when the Mermaid
  definition changes.
- [x] The extracted SVG passes the existing minimum-font-size, safe-margin,
  sanitization, namespacing, and accessibility gates.
- [x] The repository-scoped skill is discoverable, concise at entry, customized
  to GolajahSlide's palette/type scale, and passes `quick_validate.py`.
- [x] A focused harness builds without relying on a generated example deck, and
  a browser test confirms the final deck contains an inline, offline SVG.
- [x] Generated diagram example artifacts are rebuilt from current source.
- [x] `npm test` passes.

## Validation history

- 2026-08-12: implementation started after reviewing `docs/ARCHITECTURE.md`, the
  plan index, the current Mermaid/Excalidraw pipeline, upstream commit
  `4da4dfb80b1f3d2f11678726b0db58c33c1d7e9d`, and its MIT license.
- 2026-08-12: `python -X utf8 .../quick_validate.py
  .agents/skills/golajah-diagram-design` passed; the bundled Mermaid extractor
  was also exercised against GolajahSlide `@slide` metadata and an inert click
  target in the Python suite.
- 2026-08-12: strict forced builds passed for `examples/diagrams/slides.md` and
  `harnesses/diagram-design/slides.md`. The editorial example measured 28px
  minimum projected type and 70px minimum safe margin; the Harness measured
  28px and 82px.
- 2026-08-12: `npm test` passed 26 Python tests, the Presenter Focus browser
  suite, and the Diagram Design browser suite. The new browser suite verified
  a 1840×800 inline SVG, resolving accessible name/description, minimum 28px
  rendered type, no Mermaid runtime, and zero remote resources.
- 2026-08-12: a 1920×1080 browser screenshot was inspected for visual hierarchy,
  legibility, stage fit, and connector clarity. `git diff --check` passed.
- 2026-08-14: release validation passed `npm test` (26 Python tests plus both
  browser suites), repository Skill `quick_validate.py`, and `git diff --check`.
