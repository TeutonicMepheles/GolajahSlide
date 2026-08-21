# Content Typography and Divider

- Plan ID: `20260821-plain-content-typography`
- Status: `Implemented`
- Created: `2026-08-21`
- Last updated: `2026-08-21`

## Goal

让页面主标题、副标题之外的文字内容采用统一的编辑式排版：内容标题使用思源宋体粗体，正文使用思源黑体 Regular；普通文本块使用透明背景和底部细横线，callout 则以主题色底板和反白文字维持强调层级。

## Scope

- 覆盖普通段落、三级标题、callout、表头、表格数据和媒体图注。
- 普通文本块使用无圆角、透明背景和底部细分隔线。
- Callout 使用主题紫色直角底板、白色标题、浅色正文和内部底部分隔线。
- Callout 与普通内容块共享同一套标题和正文字号规则，包括重点页与 speaking 模式的字号变化。
- 普通内容块与 Callout 的默认标题字号统一为 36px。
- Callout 内的行内代码使用深色半透明底、白色半粗文字和浅色边界，避免与浅色正文产生低对比度。
- 为思源宋体与思源黑体提供本地字体族和可靠的系统字体回退，不引入网络字体依赖。
- 保留现有字号、行高、自动网格、正文编辑覆盖和 Presenter Focus 行为。
- 更新 Markdown 规范与构建器样式契约测试。

## Non-goals

- 不改变页面主标题、封面标题或章节页标题。
- 不改变图表内部文字与代码块的专用排版。
- 不移除表格的单元格结构线或媒体视觉框架。
- 不将字体文件打包进生成的 HTML。

## Acceptance gates

- [x] 普通块标题、callout 标签和表头优先使用思源宋体并保持粗体。
- [x] 正文、列表、callout 正文、表格数据与媒体图注优先使用思源黑体 Regular。
- [x] 普通文本块无圆角矩形边框和卡片底色，仅显示底部 1px 分隔线。
- [x] Callout 使用主题紫色直角底板、反白标题与浅色正文，并保留内部 1px 分隔线。
- [x] Callout 标题与正文在所有密度模式下均与普通内容块字号一致。
- [x] Callout 内行内代码在主题紫色底板上保持清晰对比，独立代码块样式不受影响。
- [x] 图表内部文字与代码块样式不受影响。
- [x] 样式契约测试覆盖字体、字重、边框、圆角和背景。

## Outcome and validation

Implemented on 2026-08-21.

- `.section-card` 使用透明背景、无圆角与底部 1px 分隔线；`.callout-card` 使用主题紫色直角底板和内部浅色分隔线。
- 内容标题、callout 标签和表头使用衬线中文字体栈；正文、列表、表格数据和媒体图注使用无衬线中文字体栈；图表和代码块保持专用排版。
- `npm test` passed：Python `31/31`，Footer Chapter Navigation、Presenter Focus、Diagram Design Chromium Harness 全部通过。
- `examples/basic`、`examples/diagrams`、`examples/archscribe` 已从当前源重新生成，其中 diagrams 与 archscribe 通过 strict 构建。
- Chrome 视觉检查确认普通内容块保持轻量分隔，callout 以紫色底板和反白文字形成明确强调层级。
- `git diff --check` passed（仅有工作区既有的 LF/CRLF 转换提示）。
