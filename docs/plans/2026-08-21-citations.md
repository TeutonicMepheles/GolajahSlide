# Citations — Inline References and Source Tooltip

- Plan ID: `20260821-citations`
- Status: `Implemented`
- Created: `2026-08-21`
- Last updated: `2026-08-21`

## Goal

让 Markdown 正文能够用标准脚注标记添加论文式引用角标，并在演示中通过悬浮或键盘聚焦查看来源说明和原文链接。

## Scope

- 解析 deck 全局 `[^id]` / `[^id]: 来源 — URL`。
- 按首次使用顺序编号，并复用重复引用的编号。
- 提供不受 Slide overflow 裁剪的悬浮卡片、键盘访问、边缘避让和打印降级。
- 对缺失、重复及无 HTTP(S) 链接的定义给出构建错误。
- 提供 Kimi 原文链接示例、Focused Harness 和真实浏览器测试。

## Non-goals

- 不联网抓取网页标题、作者或摘要。
- 不实现 BibTeX、CSL 或自动参考文献格式化。
- 不改变普通 Markdown 链接行为。
- 不增加运行时框架、包或网络依赖。

## Ownership and boundaries

- `build_slides.py` 负责引用定义、引用标记和构建诊断。
- `src/web/features/citations/` 独占悬浮卡片的样式和交互状态。
- `templates/deck.html` 只组合 Feature。

## Acceptance gates

- [x] 标准引用语法生成首次使用顺序编号。
- [x] 重复引用复用编号，定义不会成为页面正文。
- [x] 悬浮、键盘聚焦、Escape 和视口边缘定位通过真实浏览器验证。
- [x] 缺失、重复和无链接定义均有测试。
- [x] Citations Harness 严格构建成功。
- [x] `npm test` 通过。
- [x] `git diff --check` 通过。

## Outcome and validation

Implemented on 2026-08-21.

- 构建器会在拆分页之前提取 deck 全局引用定义，并在正文、列表、表格和 callout 中按首次使用顺序生成可访问角标。
- Citations 浏览器 Feature 使用挂在 `body` 上的共享 tooltip，支持悬浮、键盘聚焦、Escape、边缘避让、减少动态效果和打印降级，不会被 Slide 内容裁剪。
- Kimi AI Agent 框架文章用于 Harness 和真实浏览器测试；测试验证重复编号、完整原文 URL 和底部翻转。
- Validation: `npm test` passed（Python `30/30` + Presenter Focus、Citations、Diagram Design Chromium Harness）；`basic`、`diagrams`、`archscribe` 与 Citations Harness 均以 `--strict` 构建成功；`git diff --check` passed。
