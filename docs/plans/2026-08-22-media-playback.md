# Native Media Playback

- Plan ID: `20260822-native-media-playback`
- Status: `Implemented`
- Created: `2026-08-22`
- Last updated: `2026-08-24`

## Goal

让 Markdown 中的本地 MP4 / WebM 以原生视频呈现，并保持单 HTML 自包含交付；自动循环模式只在所属 Slide 与 Gallery 面板可见时播放。

## Scope

- 构建期识别 MP4 / WebM，并将本地视频和同名 Poster 转成 data URI。
- 默认提供原生播放控件；`video-playback: autoplay-loop` 启用静音循环。
- Media Playback 同时响应页面与 Gallery 面板激活状态。
- 提供独立、无示例稿依赖的 Harness 与浏览器回归测试。

## Non-goals

- 不引入第三方播放器或媒体转码流程。
- 不替用户决定自动播放；默认仍为手动播放。
- 不引入网络或运行时包依赖。

## Acceptance gates

- [x] 本地 MP4 / WebM 与同名 Poster 内嵌到最终 HTML。
- [x] 默认视频保留原生控件，离开页面后暂停。
- [x] 自动循环视频仅在所属页面与 Gallery 面板可见时播放。
- [x] 切换 Tab 或离开页面后视频暂停。
- [x] 严格构建无 warning / error。
- [x] Media Playback Harness 与浏览器测试通过。
- [x] `npm test` 与 `git diff --check` 通过。

## Validation evidence

- Generator contract 覆盖本地视频、Poster、默认控件与单页自动循环属性。
- MutationObserver 同时响应 Slide 与 `data-media-panel` 的激活变化。
- Focused Harness 使用自有小型测试媒体，不依赖 `examples/` 或用户素材。
- 2026-08-24：完整 `npm test` 与 `git diff --check` 通过。
