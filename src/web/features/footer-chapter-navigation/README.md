# Footer Chapter Navigation

Footer Chapter Navigation is a browser Feature layered on the generated Section progress footer. Hovering or focusing a Section opens a vertical panel above the footer; choosing a chapter navigates to the first Page assigned to that chapter.

## Runtime contract

- `chapter` is optional page metadata. Repeated chapter names within one Section collapse to one entry whose target is the first matching Page.
- A page without `chapter` falls back to its Slide title, so existing Markdown receives useful navigation without migration.
- Leading pages without an explicit Section belong to the first authored Section for menu generation.
- Pointer hover and keyboard focus open the panel. Arrow Up/Down, Home, End, Escape and native button activation are supported.
- Clicking a chapter calls the existing `SlidePresentation.show(index)` API; hash, page status and existing navigation behavior remain owned by `SlidePresentation`.
- Layout Editor and print mode suppress the floating panel.
- `window.__SLIDE_FOOTER_CHAPTER_NAVIGATION__` is the debugging surface.

## Dependencies

- Generated `[data-section-nav-item]`, `[data-section-nav-trigger]` and `[data-slide-target]` markup.
- Shared deck theme tokens such as `--accent`, `--accent-soft`, `--ink` and `--ease`.
- The existing `SlidePresentation.show(index)` navigation API supplied by the deck composition shell.

The Feature does not parse Markdown, decide chapter grouping, change Slide layout, or own generic page navigation.

## Harness and validation

`harnesses/footer-chapter-navigation/slides.md` contains repeated explicit chapters and a title-fallback chapter across two Sections. `tests/test_footer_chapter_navigation.mjs` builds it to a temporary ignored directory and validates hover geometry, grouping, click navigation, keyboard behavior, editor suppression and print suppression in a real browser.

Run:

```bash
npm run test:footer-chapter-navigation
```
