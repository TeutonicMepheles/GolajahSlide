# Animated PowerPoint Export (Experimental)

- Plan ID: `20260824-animated-pptx-export`
- Status: `Implemented`
- Created: `2026-08-24`
- Last updated: `2026-08-24`

## Goal

在保留默认无动效 PDF/PPTX 导出的前提下，新增一个明确标注为实验性的 PowerPoint 动效导出：使用 Office 2007+ core PresentationML 的原生 Fade Slide Transition，让进入后续页面时以中速淡化转场，同时保持现有全画幅静态快照的版式保真与离线合同。

## Scope

- 保留“导出 PowerPoint”为默认无动效路径，其公共 API、文件名和无 `p:transition` / `p:timing` 契约不变。
- 在低频“文件与高级操作”中新增“导出带转场 PowerPoint（实验）”按钮。
- 新增 `exportAnimatedPptx()`，输出 `*-animated.pptx`，并在 start/progress/complete/error 事件与 `lastResult` 中区分 `static` / `animated` mode。
- 只为第 2 页及之后的 Slide XML 添加 `<p:transition spd="med"><p:fade thruBlk="0"/></p:transition>`；第 1 页没有前置页，不写 transition。
- 继续将 Gallery Tab 展开为连续页，并复用相同的媒体冻结、资源边界、内存预算、Zip32 和状态不变式。
- 把“Microsoft PowerPoint 无修复提示打开”提升为静态与带转场 PPTX 的共同验收门槛。

## Non-goals

- 本轮不声称保留 HTML/CSS 的逐容器 reveal、移动路径或精确毫秒时长。
- 不生成 `p:timing` 逐对象动画；当前每页仍是一张不可解组的全画幅 JPEG。
- 不把视频、音频或 GIF/WebP 动画媒体写入 PPTX；它们仍使用 poster、首帧或确定性占位。
- 不为了精确 transition duration 引入 Office 2010 `p14:dur`、新 namespace 或兼容性分支。
- 不增加网络、运行时 npm 包、PowerPoint 插件或导出服务依赖。

## Ownership and boundaries

- `src/web/features/static-export/` 负责实验性按钮、mode 状态、PPTX option 与 Slide transition XML。
- `templates/deck.html` 仍只组合 Static Export Feature，不承载动效状态机。
- `tests/test_static_export.mjs` 同时覆盖默认静态契约和实验性原生转场契约。
- 导出结果仅是派生交付物，不反向改写 Markdown、layout sidecar、编辑草稿或 HTML 动画配置。

## Acceptance gates

- [x] 默认 PDF/PPTX 导出的文件名、页数、静态最终状态和无 `p:transition` / `p:timing` 合同不变。
- [x] 实验性按钮、文件名与帮助文字不会让用户误解为逐对象动画或媒体保留。
- [x] 带转场 PPTX 的 slide1 不含 transition，slide2..N 各含且仅含一个 core Fade Transition，所有页不含 `p:timing`。
- [x] 两种 PPTX 的 ZIP/CRC、Content Types、relationships、XML、页尺寸、图片尺寸和状态不变检查通过。
- [x] Microsoft PowerPoint 打开静态与带转场文件时均不出现修复或删除内容提示，实际放映能观察到 Fade。
- [x] Focused Harness、375×800 编辑器、失败恢复、官方示例 freshness、`npm test` 和 `git diff --check` 通过。
- [x] 未纳入仓库的真实长稿能导出带转场 PPTX，源码哈希前后不变，且页数/视觉/overflow 检查与静态路径一致。

## Validation evidence

- `PATH=<temporary python3 shim>:$PATH npm test`：112 项 Python 单元测试与 presenter-focus、footer-chapter-navigation、citations、global-logo、media-playback、content-authoring、static-export、diagram-design 八组浏览器回归全部通过。
- Focused Static Export 浏览器回归真实下载默认 PDF、默认 PPTX 与实验性 PPTX；验证三按钮 busy/失败恢复、mode 事件、375×800 布局、导出前后状态不变、默认无 transition/timing，以及实验性 slide1 无转场、slide2…N 每页一个 Fade 且无 timing。
- PowerPoint 修复根因排查：原生成器在 `viewProps.xml` 写入缺少必需 `restoredLeft` / `restoredTop` 子项的空 `normalViewPr`。该可选节点被省略后，ECMA-376 Transitional XSD 与 PowerPoint 原生读取均通过；此修复同时保护默认静态和实验性 PPTX。
- Microsoft PowerPoint for Mac 原生打开新导出的 0822Slide 时，读取 131 页成功且 telemetry 无 `Data.Repair`；缩略图第 1 页无转场、第 2 页起显示“有过渡”，Slide Show 已从第 1 页正常前进到第 2 页。
- 未纳入仓库的 0822Slide 从 114 个源 Slide 导出为 131 页实验性 PPTX（Gallery 共增加 17 个派生页）、130 个 Fade、32,819,201 bytes。`unzip -t`、131 个 slide/图片关系、130 个 transition、0 个 timing、全页渲染与 `slides_test.py` 越界检查全部通过；联络表未见空白、裁切或全局错位。
- 0822 `slides.md` 在严格构建与导出前后 SHA-256 均为 `2a88d41931e3a3468fe4dcaf868029cd417ac9e817597912307d67ba5e0d9b27`；交付 PPTX SHA-256 为 `a3ba6288550741bb5e76c856fde99f3da80e8e7a36f6cbfe8ab5c717675bd42b`。
- `examples/basic`、`examples/diagrams`（`--render-diagrams`）与 `examples/archscribe` 从当前源码严格重建；`git diff --check` 通过。
