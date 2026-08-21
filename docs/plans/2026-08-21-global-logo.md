# Global Logo — Editor Upload and Global Visibility

- Plan ID: `20260821-global-logo`
- Status: `Implemented`
- Created: `2026-08-21`
- Last updated: `2026-08-21`

## Goal

在每页右上角、与内容页标题区对齐的位置提供可选的全局 Logo；用户可在页面编辑器中统一开关、显示占位符并上传 Logo，下载后的单文件 HTML 与重新构建结果都能保留设置。

## Scope

- Logo 默认关闭，启用且尚未上传图片时显示占位符。
- 支持上传不超过 2 MB 的 PNG、JPEG、WebP，并以内嵌 data URL 交付。
- 设置进入本地编辑状态、布局 JSON、JSON 导入以及当前 HTML 下载。
- 增加独立 Feature、Harness、构建器契约测试和浏览器测试。

## Non-goals

- 不提供每页独立 Logo。
- 不支持远程 URL、SVG 脚本内容或运行时网络读取。
- 不提供 Logo 位置的自由拖拽；尺寸调整保持右侧锚点与标题区中心线不变。

## Ownership and boundaries

- `src/web/features/global-logo/` 负责 Logo DOM、样式、图片校验和同步状态。
- `templates/deck.html` 的 Layout Editor 负责全局控件与持久化编排。
- 构建器只验证并透传 `branding.logo`，保持 Python-only 与单 HTML 合同。

## Acceptance gates

- [x] 默认关闭；全局启用后每页出现占位符。
- [x] 上传合法图片后所有页面即时同步，关闭与重新打开不丢失图片。
- [x] 非法类型和超过 2 MB 的文件被拒绝。
- [x] JSON 导出/导入、重建和当前 HTML 下载保留 Logo。
- [x] 编辑模式可拖动左下角手柄调整全局宽高，并可恢复 190×72。
- [x] Focused Harness 与浏览器测试通过。
- [x] `npm test` 和 `git diff --check` 通过。

## Outcome and validation

Implemented on 2026-08-21.

- 每页右上角新增默认 190×72 的全局 Logo 区域，中心线与内容页标题区一致；编辑模式可拖动左下角手柄在 80–420 × 36–180 px 范围内调整尺寸，右侧锚点与中心线保持不变。
- 页面编辑器可全局开关、上传 PNG/JPEG/WebP 或恢复 `LOGO` 占位符；上传后自动启用并同步所有页面。
- `branding.logo` 的图片和宽高进入 localStorage、布局 JSON、JSON 导入和下载的单文件 HTML；构建器验证 data URL 与尺寸后继续内嵌，运行时不发起网络请求。
- Validation: `npm test` passed（Python `36/36` + Presenter Focus、Footer Chapter Navigation、Citations、Global Logo、Diagram Design Chromium Harness）；`basic`、`diagrams`、`archscribe` 均以 `--strict` 重建成功；`git diff --check` passed。
