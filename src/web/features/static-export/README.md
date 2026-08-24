# Static Export

Static Export owns direct, browser-native PDF and PowerPoint downloads. It renders the current live Slide DOM to deterministic 1920×1080 static JPEG frames, then encodes those frames without a runtime package or network dependency. The default PDF/PPTX paths remain fully static; a separate, explicitly experimental PPTX path can add native Fade transitions between those flattened pages.

## User contract

- The Layout Editor exposes one-click `导出 PDF`, `导出 PowerPoint`, and `导出带转场 PowerPoint（实验）` actions in the low-frequency file/advanced category.
- Both formats are static by default: reveal content is fully visible, CSS animation and transitions are disabled, and editor/focus/viewer overlays are removed.
- PDF pages use a 960×540 pt 16:9 MediaBox and download directly instead of opening the browser print dialog.
- PPTX pages use the standard wide 12192000×6858000 EMU canvas. Every page contains one full-bleed JPEG and no `p:timing` or `p:transition` nodes.
- Experimental animated PPTX files use the `*-animated.pptx` suffix. Slide 1 has no incoming transition; slide 2 and later each contain exactly one core PresentationML `<p:transition spd="med"><p:fade thruBlk="0"/></p:transition>` node.
- Experimental animation is page-level Fade only. It does not add `p:timing`, recreate HTML reveal/object motion, make flattened content editable, or preserve links, video, animated GIF/WebP, or audio.
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
  beforeCapture: () => mediaPlayback.exitFullscreen({restoreFocus: false}),
  sanitizeClone: clone => {
    layoutEditor.prepareClone(clone);
    visualWidgetManager.sanitizeClone(clone);
    mediaPlayback.sanitizeClone(clone);
  }
});
window.__SLIDE_STATIC_EXPORT__ = staticExport;
```

Static Export does not read Layout Editor persistence or Python build models. It clones only live Slide elements and never changes the current page, Gallery selection, playback state, localStorage, Markdown, or layout sidecars.

## Public API

- `snapshotPlan()` returns the ordered source-slide and Gallery-variant manifest.
- `renderFrames(plan?)` runs `beforeCapture()` before deriving a default Gallery plan, then creates static JPEG byte arrays without packaging or downloading.
- `exportPdf({download = true})` returns the PDF Blob and result metadata.
- `exportPptx({download = true})` returns the PPTX Blob and result metadata.
- `exportAnimatedPptx({download = true})` returns the experimental Fade-transition PPTX Blob and result metadata.
- `lastResult` records format, `static` / `animated` mode, filename, page count, byte size, source Slide count, animation-effect summary, and the static manifest.
- `prepareClone(clone)` clears transient busy/progress/result UI before the existing HTML-download path serializes a deck.
- Media Playback participates through its public `sanitizeClone(clone)` contract so transient video fullscreen controls, overlays, and moved shells never reach PDF/PPTX frames.
- The async `beforeCapture()` collaborator exits a live fallback fullscreen surface before each frame is cloned, so the original video shell is always back under its Slide.

The mount emits bubbling `static-export:start`, `progress`, `complete`, and `error` events. Each event identifies its `static` or `animated` mode so automation can distinguish the default artifact from the experimental derivative.

## Resource boundary

The Python build embeds a deduplicated, content-hashed data-URI manifest for local PNG/JPEG/WebP/GIF/SVG resources because `file://` images cannot safely cross the SVG/Canvas boundary. Browser-created Blob images are inlined during export. An HTTP(S), unmanifested `file:` or otherwise external image is rejected with a page-specific error rather than producing a silently blank frame.

## Required validation

- Focused source: `harnesses/static-export/slides.md`
- Browser test: `tests/test_static_export.mjs`
- Build composition contract: `tests/test_build_slides.py`

Browser validation must exercise real Blob downloads, ZIP/XML/PDF structure, Tab expansion, final reveal state, media freezing, unchanged live presentation state, direct offline operation, and a 375×800 editor viewport. It must prove that default PPTX remains free of both `p:transition` and `p:timing`, while experimental PPTX has no transition on slide 1, exactly one Fade transition on slides 2…N, and no `p:timing` anywhere. Final handoff also requires rendering the PDF with Poppler and opening both PPTX modes in Microsoft PowerPoint without a repair/deleted-content prompt; the experimental deck must show the Fade during Slide Show.
