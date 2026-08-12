# Presenter Focus — Pointer Cue and Theme Depth

- Plan ID: `20260812-presenter-focus-pointer-theme`
- Status: `Implemented`
- Created: `2026-08-12`
- Last updated: `2026-08-12`

## Goal

让观众更容易看见演讲者当前鼠标位置，并通过由浅到深的主题色层级清楚区分“容器聚焦”和“容器内文本聚焦”。

## Scope

- 在 Slide 范围内显示不拦截交互的鼠标圆形示意。
- 让圆圈、容器聚焦和文本聚焦全部从当前设计系统主题 token 派生颜色。
- 容器使用较浅的主题色，文本片段使用更重的主题色，表达语义深度。
- 保留现有 `H` 开关、编辑模式暂停、触屏保护、打印清理与减少动态效果行为。
- 扩展 Presenter Focus Harness 与真实浏览器测试，覆盖指针位置、可见性和主题色响应。

## Non-goals

- 不隐藏或替换操作系统鼠标形状。
- 不记录、同步或回放指针轨迹。
- 不引入 Canvas、第三方指针库或运行时网络依赖。
- 不改变 Markdown 内容语义、布局覆盖格式或图片交互协议。
- 不新增独立工具栏按钮；指针提示与 Presenter Focus 共用现有开关。

## Ownership and boundaries

- `src/web/features/presenter-focus/` 独占指针状态机、聚焦深度 token 和样式。
- `templates/deck.html` 只负责构造 Feature，不能承载指针实现。
- Harness 提供容器、块级文本和行内文本三个深度场景。

## Acceptance gates

- [x] 指针圆圈跟随鼠标并以系统指针为圆心，不拦截点击或悬浮。
- [x] 指针离开当前 Slide、窗口失焦、关闭 Feature 或进入编辑模式时隐藏。
- [x] 容器聚焦色明显浅于文本聚焦色。
- [x] 修改 `--accent` 后，圆圈、容器与文本聚焦颜色同步变化。
- [x] `python -m unittest discover -s tests -v` 通过。
- [x] `npm run test:presenter-focus` 通过。
- [x] `npm test` 通过。
- [x] Presenter Focus Harness 严格构建成功。
- [x] `basic`、`diagrams`、`archscribe` 严格构建成功并更新生成产物。
- [x] `git diff --check` 通过。

## Outcome and validation

Implemented on 2026-08-12.

- Presenter Focus 在当前 Slide 内绘制不接管系统光标、且 `pointer-events: none` 的主题色圆圈；指针位置通过 `requestAnimationFrame` 合并更新。
- 容器、文本与指针分别使用从 `--accent` / `--accent-soft` 派生的语义 token；浏览器测试验证文本层级显著重于容器，并验证运行时换主题后全部同步变色。
- Feature 继续独立位于 `src/web/features/presenter-focus/`，构建时内联到单 HTML；无新增运行时网络或包依赖。
- Validation: `npm test` passed（Python `22/22` + Presenter Focus Chromium Harness）；`basic`、`diagrams`、`archscribe` 均以 `--strict` 构建成功；`git diff --check` passed。
