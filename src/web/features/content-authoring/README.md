# Content Authoring

Content Authoring owns structured browser edits that must survive a Markdown rebuild. It does not use DOM position as identity and never stores edited `innerHTML`.

## User contract

- Content mode can add a text card with the default title `标题` and body `正文`, or add a Note Callout with `补充说明` and `正文`.
- Text cards and Callouts can be reordered by drag-and-drop or the accessible up/down buttons.
- Images, text cards, and Callouts can move to the immediately previous or next content slide. The first/last page does not wrap, and structural cover/section pages are not valid destinations. A specialized table/code/diagram page can still receive text, but deliberately does not accept newly appended or moved media because its locked visual stage cannot be recomposed safely in-browser.
- Two or more images can use `grid` (side-by-side) or `tabs` (Gallery). Tab targets use stable media IDs rather than numeric DOM positions, and the currently visible choice is persisted even when a media move crosses the default three-image threshold.
- PNG, JPEG, and WebP can be uploaded, dropped, or pasted. The built-in importer checks MIME plus file magic, an 8 MB byte limit, successful decode, a 12,000 px edge limit, and a 40-million-pixel limit. A selected image is replaced; otherwise images are appended.
- `保存改动` asks for a directory with the File System Access API. It verifies the exact UTF-8 `slides.md` SHA-256 and the layout file's hash plus presence/absence before writing anything, then writes content-addressed assets, layout JSON, and Markdown last. A source/layout conflict never overwrites the disk file.
- Structural layout changes are written to the Markdown directive and rebased into an existing layout sidecar. The sidecar keeps its content bounds and typography/animation settings while incompatible visual/copy regions are regenerated for the new layout.
- Unsupported, denied, cancelled, conflicting, or failed direct saves export a `.golajah-edit.json` recovery bundle containing the base source, operation log, target Markdown when serializable, layout payload, and pending assets.
- A successful source save reports `needsRebuild: true` and locks further source writes until the deck is rebuilt. Browser code cannot truthfully regenerate Python validation or `index.build.json`.

## Build-time DOM/model contract

The build embeds JSON in `#deckAuthoringModel`:

```json
{
  "schemaVersion": "1.0",
  "source": {
    "name": "slides.md",
    "sha256": "...",
    "text": "exact source",
    "newline": "\n",
    "bom": false,
    "offsetEncoding": "utf-16"
  },
  "slides": [{
    "id": "stable-slide-id",
    "baseHash": "...",
    "source": "exact slide source",
    "sourceRange": {"start": 0, "end": 100},
    "galleryDisplay": "grid",
    "items": [{
      "id": "stable-item-id",
      "kind": "text",
      "markdown": "### 标题\n\n正文",
      "baseHash": "...",
      "sourceRange": {"start": 20, "end": 35},
      "fieldRanges": {}
    }]
  }]
}
```

Offsets are JavaScript UTF-16 code-unit offsets so emoji cannot shift a browser `slice()`. The exact embedded source must hash to `source.sha256`; otherwise serialization and disk writes are rejected.

Rendered markup exposes:

- `.slide[data-slide-id][data-author-base-hash]`
- `[data-author-item-id][data-author-item-kind][data-author-base-hash]`
- item leaves with `[data-author-field="title|body|caption"]`
- slide headings may use `slide-title` and `slide-subtitle`; they are deliberately outside this Feature's movable-item scope.

Stable item IDs are mandatory. Existing nodes without an ID are not assigned whole-deck numeric fallbacks.

## Construction

The composition shell constructs the Feature after `SlidePresentation` and publishes the instance:

```js
const contentAuthoring = new ContentAuthoring({
  stage: document.getElementById("deckStage"),
  manifest: JSON.parse(document.getElementById("deckAuthoringModel").textContent),
  presentation,
  layoutEditor,
  widgetManager: visualWidgetManager,
  mediaTabsManager,
  mediaPlayback
});
window.__SLIDE_CONTENT_AUTHORING__ = contentAuthoring;
```

The runtime creates its Layout Editor group if no `[data-content-authoring-mount]` exists. The template should still provide an explicit mount for predictable panel order.

## Public API

- `setActive(active)` enters/leaves the mutually exclusive content interaction mode.
- `addTextBlock(slideId, values?)` / `addCallout(slideId, values?)` create stable items.
- `updateField(itemId, field, value)` edits controlled text fields as text, never HTML.
- `reorderItem(slideId, itemId, beforeItemId)` reorders text/Callout items.
- `moveItem(itemId, targetSlideId, beforeItemId?)` moves a supported item without wrapping page boundaries.
- `setGalleryDisplay(slideId, "grid"|"tabs")` changes the authored Gallery choice.
- `importRasterFiles(files, context)` validates and appends/replaces raster images.
- `replaceMediaItem(...)`, `appendMediaItem(...)`, and `registerPendingAsset(...)` support a custom media UI.
- `snapshot()` and `buildChangeSet()` return JSON-safe structural state (pending asset Blob objects are excluded from localStorage but included in a live change set).
- `serializeMarkdown(assetPaths?)` applies changed slide replacements to the exact embedded source. A `serializeMarkdown` constructor bridge can replace the built-in serializer.
- `save()` runs the user-facing adapter/picker/bundle flow.
- `saveToDirectory(directoryHandle, changeSet?)` is the deterministic direct-write entry point and accepts fake File System handles in tests.

## Cross-Feature bridge

The preferred bridge is `domBridge.reconcileSlide({slide, state, nodes, feature})`, returning `true` when it composed the live layout. As a compatibility path, Layout Editor may expose:

- `reconcileAuthoringSlide(slide, snapshot, {nodes}) -> true`
- `onAuthoringContentChange(slide, snapshot)`
- `setInteractionMode("content"|"layout")`

After every structural transaction Content Authoring calls, when present:

- `widgetManager.reconcile(slide)` and `widgetManager.unregister(oldRoot)`
- `mediaTabsManager.reconcile(slide)`
- `mediaPlayback.reconcile(slide)` and `mediaPlayback.sync()`

The fallback composer covers ordinary content pages: 0 media -> `text`, 1 media plus blocks -> `split`, 1 media without blocks -> `media`, and 2+ media -> `gallery`. Pages containing locked table/chart/Mermaid/Excalidraw/Archscribe items keep their specialized layout. Layout Editor remains responsible for preserving or invalidating manual regions and for rebuilding stable animation candidates.

## Persistence and save adapter

Draft localStorage contains only `{baseSourceSha256, revision, operations}` under a source-specific key. Drafts are replayed only when the current embedded SHA-256 matches. The older Layout Editor cache uses the same source-hash gate for page entries, so ordinal page overrides from a prior build are ignored. A mismatched draft emits `content-authoring:draft-conflict` and is never applied by guessed position. Raster Blob bytes remain in memory (or a supplied media store), not localStorage; therefore a reloaded draft containing unsaved media operations is kept as a conflict record and is not partially replayed.

An optional `saveAdapter.save(changeSet, feature)` may replace the native directory flow. It returns:

```js
{
  status: "saved" | "exported",
  sourceSha256: "...",
  changedFiles: [{path, kind, sha256}],
  needsRebuild: true
}
```

An empty or incomplete adapter response is treated as `WRITE_FAILED`; the UI never reports a source save without a returned source fingerprint and changed-file list.

Recognized error codes are `SOURCE_CONFLICT`, `PERMISSION_DENIED`, `UNSUPPORTED`, `WRITE_FAILED`, `INVALID_PATH`, and `USER_CANCELLED`.

## Events

All events bubble from the deck stage and use the `content-authoring:` prefix:

- `mode-change`, `selection-change`, `change`, and `structure-change`
- `media-import-request` (supports `detail.respondWith(promise)`) and `media-imported`
- `save-request` (supports `detail.respondWith(promise)`), `save-state`, and `saved`
- `draft-conflict` and `error`

## Required validation

- Focused source: `harnesses/content-authoring/slides.md`
- Browser test: `tests/test_content_authoring.mjs`
- Generator/source-model contracts: `tests/test_build_slides.py`

The browser matrix must cover add/edit, drag and keyboard reorder, grid/tabs switching, text and image moves in both directions, automatic 0/1/2-media layout changes, dynamic Visual Widget/Media Tabs registration without duplicate controls, plain-text paste, raster validation, matching-hash save, source/layout conflicts, write rollback, recovery-bundle fallback, stable-cache rebuild regression, and overflow checks at desktop and narrow viewports.
