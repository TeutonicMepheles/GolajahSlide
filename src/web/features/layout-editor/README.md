# Layout editor geometry

`measureLayoutRegions(slide, parts)` seeds untouched editor entries from actual layout boxes in slide coordinates. It ignores reveal transforms and stage scaling. Hero content is the union of its copy and visual containers. Existing saved regions and explicit preset actions keep their authored values.

The composition shell supplies semantic parts and owns existing editing interactions. Styles explicitly theme native select options. No runtime dependencies.

Validation: `node tests/test_layout_editor.mjs`; focused source: `harnesses/layout-editor/slides.md`.
