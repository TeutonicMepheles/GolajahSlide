# Static Export

Static Export owns direct, browser-native PDF and PowerPoint downloads. It renders the current live Slide DOM to deterministic 1920×1080 static JPEG frames, then encodes those frames without a runtime package or network dependency.

## User contract

- The Layout Editor exposes one-click `导出 PDF` and `导出 PowerPoint` actions in the low-frequency file/advanced category.
- Both formats are static by default: reveal content is fully visible, CSS animation and transitions are disabled, and editor/focus/viewer overlays are removed.
- PDF pages use a 960×540 pt 16:9 MediaBox and download directly instead of opening the browser print dialog.
- PPTX pages use the standard wide 12192000×6858000 EMU canvas. Every page contains one full-bleed JPEG and no `p:timing` or `p:transition` nodes.
- A Tab Gallery is expanded into consecutive export pages so hidden media is not silently lost. Multiple tab shells use their bounded Cartesian product, with a 32-variant safety limit per source Slide.
- Video uses its poster, then an already available frame, then a deterministic placeholder. Animated GIF/WebP images prefer a reduced-motion poster or `ImageDecoder` first frame; older browsers freeze the currently decoded frame.
- The first version prioritizes fidelity over editability. PDF text is not searchable/selectable, PPTX elements cannot be ungrouped, and links/video/animation are not preserved.

## Construction

The composition shell supplies only public collaborators:

```js
const staticExport = new StaticDeckExport({
  slides: presentation.slides,
  deckTitle: layoutEditor.deckTitle,
  mount: "#editorStaticExportMount",
  assetManifest: JSON.parse(document.getElementById("deckStaticExportAssets").textContent),
  sanitizeClone: clone => {
    layoutEditor.prepareClone(clone);
    visualWidgetManager.sanitizeClone(clone);
  }
});
window.__SLIDE_STATIC_EXPORT__ = staticExport;
```

Static Export does not read Layout Editor persistence or Python build models. It clones only live Slide elements and never changes the current page, Gallery selection, playback state, localStorage, Markdown, or layout sidecars.

## Public API

- `snapshotPlan()` returns the ordered source-slide and Gallery-variant manifest.
- `renderFrames(plan?)` creates static JPEG byte arrays without packaging or downloading.
- `exportPdf({download = true})` returns the PDF Blob and result metadata.
- `exportPptx({download = true})` returns the PPTX Blob and result metadata.
- `lastResult` records format, filename, page count, byte size, source Slide count, and the static manifest.
- `prepareClone(clone)` clears transient busy/progress/result UI before the existing HTML-download path serializes a deck.

The mount emits bubbling `static-export:start`, `progress`, `complete`, and `error` events.

## Resource boundary

The Python build embeds a deduplicated, content-hashed data-URI manifest for local PNG/JPEG/WebP/GIF/SVG resources because `file://` images cannot safely cross the SVG/Canvas boundary. Browser-created Blob images are inlined during export. An HTTP(S), unmanifested `file:` or otherwise external image is rejected with a page-specific error rather than producing a silently blank frame.

## Required validation

- Focused source: `harnesses/static-export/slides.md`
- Browser test: `tests/test_static_export.mjs`
- Build composition contract: `tests/test_build_slides.py`

Browser validation must exercise real Blob downloads, ZIP/XML/PDF structure, Tab expansion, final reveal state, media freezing, unchanged live presentation state, direct offline operation, and a 375×800 editor viewport. Final handoff also requires rendering the PDF with Poppler and opening/rendering the PPTX with an Office-compatible renderer.
