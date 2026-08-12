# Presenter Focus

Presenter Focus is a browser-only presentation Feature. It provides a theme-aware pointer cue, emphasizes one semantic text container on pointer hover, and optionally emphasizes one nested text fragment without changing slide content or layout data.

## Runtime contract

- Focus is enabled by default and toggled by the `H` shortcut or `#focus` control.
- A non-interactive `aria-hidden` pointer cue follows mouse/pen movement inside the active Slide. It keeps the system cursor visible and batches position updates with `requestAnimationFrame`.
- The Feature owns `body.presenter-focus-enabled`, the control's active/ARIA state, and automatic `data-presenter-text="block"` registration.
- The Feature owns its theme-derived tokens: container focus uses the lightest accent mix, pointer cue uses the middle mix, and nested text uses the strongest accent mix.
- The generator marks semantic containers with `data-presenter-focus` and explicit inline emphasis with `data-presenter-text="inline"`.
- Layout Editor mode, window blur, leaving the Slide, or disabling the Feature hides the pointer cue without destroying the enabled preference.
- Fine pointer and hover capability are required for visual activation.
- Reduced-motion mode removes focus scaling.
- `window.__SLIDE_PRESENTER_FOCUS__` remains the current debugging surface.

## Dependencies

- Shared deck theme tokens such as `--accent`, `--accent-soft`, `--ink`, and `--ease`. All focus and pointer colors are derived from these tokens and update when the deck theme changes.
- The existing `#focus` control supplied by the deck composition shell.
- The `editor-open` body class owned by Layout Editor.

The Feature does not own slide navigation, layout editing, generator parsing, or content semantics.

## Harness and validation

`harnesses/presenter-focus/slides.md` is the minimal executable scenario. `tests/test_presenter_focus.mjs` builds it into a temporary ignored directory before launching a real browser, so validation never depends on an already generated example HTML file.

Run:

```bash
npm run test:presenter-focus
```
