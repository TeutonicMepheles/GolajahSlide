# Presenter Focus — Configurable Global Shortcut

- Plan ID: `20260821-presenter-focus-shortcut`
- Status: `Implemented`
- Created: `2026-08-21`
- Last updated: `2026-08-21`

## Goal

允许用户在页面编辑器中为悬浮聚焦设置整份演示文稿通用的开关键，随本地编辑状态和布局 JSON 持久化，方便随时关闭容易造成视觉干扰的 Hover 效果。

## Scope

- 保留 `H` 作为默认开关键，并让工具栏提示反映当前配置。
- 在页面编辑器中捕获并显示单键或带修饰键的全局快捷键。
- 拒绝与翻页、编辑器和视觉控件已有键位冲突的配置。
- 将键位写入本地编辑状态、导出 JSON、导入 JSON 和重建后的单文件 HTML。
- 扩展 Presenter Focus Harness 浏览器测试和构建器契约测试。

## Non-goals

- 不提供整套演示控制的键位重映射。
- 不允许在输入框、可编辑内容或交互控件中触发悬浮聚焦。
- 不改变悬浮聚焦的视觉设计、默认启用状态或编辑模式暂停行为。

## Ownership and boundaries

- `src/web/features/presenter-focus/` 负责快捷键规范化、匹配、显示和 Feature 开关。
- `templates/deck.html` 的 Layout Editor 负责配置 UI 与全局编辑配置的持久化。
- 构建器只验证并透传全局快捷键配置，不复制浏览器交互状态机。

## Acceptance gates

- [x] 默认 `H` 可切换悬浮聚焦。
- [x] 编辑模式可录入并立即启用新的无冲突快捷键。
- [x] 输入控件中不会误触快捷键，冲突键不会覆盖当前配置。
- [x] 键位可经本地状态、导出/导入 JSON 和重新构建保留。
- [x] 工具栏 title 与 `aria-keyshortcuts` 反映当前键位。
- [x] `npm test` 通过。
- [x] Presenter Focus Harness 严格构建成功。
- [x] 受影响示例重新生成。
- [x] `git diff --check` 通过。

## Outcome and validation

Implemented on 2026-08-21.

- 页面编辑器新增整份演示文稿级别的“演示快捷键”录入框与恢复默认按钮；支持字母、数字、F1–F12 和修饰键组合。
- Presenter Focus 独立负责规范化、冲突判定、键盘事件匹配以及工具栏 title / `aria-keyshortcuts` 同步；输入框、按钮和可编辑内容聚焦时不会误触。
- `shortcuts.presenterFocus` 会进入本地编辑状态和布局 JSON，构建器验证后内嵌到自包含 HTML；浏览器测试验证了改键、拒绝冲突、旧键失效、新键开关和刷新恢复。
- Validation: `npm test` passed（Python `31/31` + Footer Chapter Navigation、Presenter Focus、Diagram Design Chromium Harness）；`basic`、`diagrams`、`archscribe` 均以 `--strict` 构建成功；页面编辑器原生布局下拉框的深色选项可读性回归通过；`git diff --check` passed。
