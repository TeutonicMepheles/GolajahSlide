# Global Logo

Global Logo owns the optional presentation-wide brand mark shown at the upper-right of every slide.

## Contract

- The feature inserts one `[data-global-logo]` node into each slide and keeps every instance synchronized.
- The default is disabled, preserving decks built before the feature existed.
- Enabling without an uploaded image shows a `LOGO` placeholder.
- Uploaded PNG, JPEG, and WebP images up to 2 MB are represented as data URLs so downloaded HTML remains self-contained.
- In editor mode, a lower-left resize handle adjusts global width (80–420 px) and height (36–180 px) while preserving the right anchor and title-region center line.
- The Layout Editor owns the controls and persistence surface. It exchanges `{enabled, src}` through `branding.logo` and calls the public `GlobalLogo` methods.

## Validation

- Focused source: `harnesses/global-logo/slides.md`
- Browser test: `tests/test_global_logo.mjs`
- Generator contract: `tests/test_build_slides.py`
