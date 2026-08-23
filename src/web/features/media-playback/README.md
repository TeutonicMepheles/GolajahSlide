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
- The runtime adds no network or package dependency.

## Validation

- Focused source: `harnesses/media-playback/slides.md`
- Browser test: `tests/test_media_playback.mjs`
- Generator contract: `tests/test_build_slides.py`
