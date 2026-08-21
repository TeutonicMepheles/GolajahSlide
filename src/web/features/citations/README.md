# Citations

Citations turns standard Markdown footnote markers into numbered, accessible source links with a presentation-friendly tooltip.

## Authoring contract

```markdown
正文结论[^source].

[^source]: 来源标题 — https://example.com/original
```

- IDs contain letters, numbers, `_`, or `-`, up to 64 characters.
- Definitions are deck-global and may appear after the slide that cites them.
- A definition must end in either a bare HTTP(S) URL or a Markdown link.
- Numbers follow first-use order across the deck; repeated IDs reuse their number.
- Definitions do not render as slide content.

## Runtime contract

- Hovering or focusing a citation marker opens one shared `role="tooltip"` element attached to `body` so slide overflow cannot clip it.
- The tooltip shows the citation text and original link. Both the marker and tooltip link open the source in a new tab.
- The tooltip flips above its marker near the viewport bottom and is clamped to viewport edges.
- Escape, pointer departure, or focus departure closes it; reduced-motion and print modes receive static fallbacks.
- `window.__SLIDE_CITATIONS__` is the debugging surface.

The Feature does not fetch citation metadata and introduces no runtime network or package dependency.
