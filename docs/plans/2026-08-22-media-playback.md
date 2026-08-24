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
- 所有视频均提供一致的全屏入口，不依赖原生 controls 是否可见；覆盖单独放置、Gallery Tab 与 Gallery 并列布局。
- 全屏优先使用浏览器 Fullscreen API，iOS/Safari 使用原生视频全屏，不可用时回退到同页遮罩层。
- 切换 Slide、切换 Gallery Tab 或进入编辑模式时退出视频全屏并保持播放状态同步。
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
- [x] 手动视频与自动循环视频均显示可键盘操作的“全屏播放”入口。
- [x] 单独视频与 Gallery 视频均可进入、退出全屏，并正确同步 `aria` 与焦点状态。
- [x] 隐藏 Gallery Tab、离开 Slide 或进入编辑模式时不会遗留全屏遮罩或继续错误播放。
- [x] 全屏控件不会进入静态 PDF/PPTX 或下载后的瞬态 DOM 状态。

## Validation evidence

- Generator contract 覆盖本地视频、Poster、默认控件与单页自动循环属性。
- MutationObserver 同时响应 Slide 与 `data-media-panel` 的激活变化。
- Focused Harness 使用自有小型测试媒体，不依赖 `examples/` 或用户素材。
- 2026-08-24：Harness 覆盖独立手动视频、独立自动循环视频、Gallery Tab 与 Gallery grid 双视频。
- 2026-08-24：浏览器回归覆盖标准 Fullscreen mock、iOS/Safari `webkitEnterFullscreen`、超时遮罩回退、ESC/按钮退出、换页/Tab/编辑同步、原 DOM/播放位置恢复、HTML 保存与静态导出清理。
- 2026-08-24：全屏请求使用 pending token；ESC、换页、切 Tab 与编辑会取消未完成请求，迟到的 native 成功会升级当前 fallback 或被安全退出。
- 2026-08-24：fallback 具备 modal/inert 语义与焦点循环；Static Export 在生成 Gallery 计划和克隆页面前恢复 live fullscreen 视频。
- 2026-08-24：1280×720 与 375×800 下，全屏入口的实际屏幕点击区域均不小于 44×44 CSS px。
- 2026-08-24：最终分支完整 `npm test`（112 项 Python 及 8 组浏览器/图表测试）与 `git diff --check` 通过。
