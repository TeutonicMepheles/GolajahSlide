# Global Logo

Global Logo owns the optional presentation-wide brand mark shown at the upper-right of every slide.

## Contract

- The feature inserts one `[data-global-logo]` node into each slide and keeps every instance synchronized.
- A slide with `global-logo: hidden` keeps the shared image and size configuration but suppresses its own Logo instance.
- The default is disabled, preserving decks built before the feature existed.
- Enabling without an uploaded image shows a `LOGO` placeholder.
- Uploaded PNG, JPEG, and WebP images up to 2 MB are represented as data URLs so downloaded HTML remains self-contained.
- In editor mode, a lower-left resize handle adjusts global width (80–420 px) and height (36–180 px) while preserving the right anchor and title-region center line.
- The Layout Editor owns the global controls and persistence surface. It exchanges `{enabled, src, width, height}` through `branding.logo`; per-slide visibility remains authored Markdown metadata.

## Validation

- Focused source: `harnesses/global-logo/slides.md`
- Browser test: `tests/test_global_logo.mjs`
- Generator contract: `tests/test_build_slides.py`
