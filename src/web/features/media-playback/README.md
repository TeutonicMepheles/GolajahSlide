# Media Playback

Media Playback owns native MP4/WebM presentation inside GolajahSlide media layouts.

## Contract

- A standalone Markdown media line whose source ends in `.mp4` or `.webm` is rendered as a native `<video controls playsinline>` element.
- A slide with `video-playback: autoplay-loop` renders its video as muted, inline, control-free autoplaying media that loops while the slide is active.
- Local video and poster bytes are embedded as data URIs so the delivered HTML stays self-contained.
- Video uses the same `split`, `media`, and `gallery` layout decisions as images, with a default 16:9 ratio.
- A same-basename PNG, JPEG, or WebP beside a local video becomes its native poster image.
- Playback is user-initiated by default. Autoplay-loop videos start when their slide and, when applicable, Gallery panel are active. Hiding the containing Tab or leaving the slide pauses either mode without resetting its position.
- Pointer, touch, and wheel interaction with video controls does not trigger slide navigation.
- Every video receives the same keyboard-operable fullscreen button, whether it is standalone, in a Gallery Tab, or in a Gallery grid. The authored stage scale is compensated so the visible hit target remains at least 44×44 CSS pixels on narrow screens.
- Fullscreen prefers the element Fullscreen API, uses `HTMLVideoElement.webkitEnterFullscreen()` on supporting iOS/Safari builds, and otherwise moves the original shell (never a cloned video) into a feature-owned viewport overlay.
- The entry request is tokenized: changing Slide/Tab or opening the editor cancels a pending request, while a late native success is either reconciled with the active fallback or immediately exited.
- Fullscreen keeps the same video node and playback position. Autoplay-loop videos temporarily receive native controls in fullscreen and return to their original control-free state after exit.
- The fallback is an accessible modal dialog: background presentation roots become inert, focus stays between the video and exit control, and all prior `inert`/`aria-hidden` state is restored exactly.
- Changing Slide, hiding the containing Gallery Tab, or entering edit mode exits fullscreen without returning focus to hidden content. Explicit exit restores focus to the originating button when it remains visible.
- Runtime controls, overlays, placeholders, temporary controls, and fullscreen state are removed by `sanitizeClone()` before saved HTML or static PDF/PPTX frames are produced.
- The runtime adds no network or package dependency.

## Public API

- `fullscreenShell` exposes the active video surface; `isFullscreen` also covers pending entry and browser-owned exit state so presentation navigation stays blocked throughout the transition.
- `toggleFullscreen(shellOrRecord)` and `exitFullscreen(options?)` own entry, exit, fallback, ARIA state, and focus restoration.
- `handleSlideChange()`, `setEditing(editing)`, and `sync()` synchronize fullscreen and playback with the composition shell.
- `reconcile(scope?)` mounts controls for authoring-created or moved videos without duplicating them.
- `syncControlScale()` keeps the authored-stage control at a usable screen-space size.
- `sanitizeClone(clone)` is the save/static-export boundary and must run after an HTML clone is created.

## Validation

- Focused source: `harnesses/media-playback/slides.md`
- Browser test: `tests/test_media_playback.mjs`
- Generator contract: `tests/test_build_slides.py`
