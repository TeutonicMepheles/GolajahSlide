# Modular Foundation — Stable First Slice

- Plan ID: `20260812-modular-foundation`
- Status: `Implemented`
- Created: `2026-08-12`
- Last updated: `2026-08-12`

## Goal

建立一个低风险、可复制的浏览器 Feature 开发闭环：Feature 独立拥有 CSS、JavaScript、当前契约、专项 Harness 和真实浏览器验证，同时继续由 Python 生成零运行时依赖的单文件 HTML。

## Scope

- 记录构建期与浏览器运行时边界、依赖方向和 Feature 完成条件。
- 将 Presenter Focus 的 CSS 和 JavaScript 从 `templates/deck.html` 移入独立 Feature 目录。
- 在 Python 构建期间内联 Feature 源码，保持最终 HTML 自包含。
- 建立只包含 Presenter Focus 所需内容的专项 Harness。
- 让浏览器测试每次从 Harness 源码重新构建临时 HTML，不读取可能过期的已提交示例产物。
- 提供一个运行 Python 与浏览器验证的统一命令。

## Non-goals

- 不引入 React、Vue、Vite 或新的运行时依赖。
- 不重写或整体拆分 `build_slides.py`。
- 不迁移 Layout Editor、Presentation、Visual Widget 或 Diagram 功能。
- 不建立通用插件系统、依赖注入框架或跨 Feature 事件总线。
- 不改变 Presenter Focus 的视觉、快捷键、可访问性或公开调试对象。
- 不改变示例、布局覆盖或图表协议。

## Ownership and boundaries

- `src/web/features/presenter-focus/` 是 Presenter Focus 行为和样式的唯一源码所有者。
- `templates/deck.html` 仅保留该 Feature 的组合占位符和控制按钮。
- `build_slides.py` 只读取并内联已登记的 Feature 源片段，不解释其内部行为。
- `harnesses/presenter-focus/` 是专项场景源；浏览器测试负责构建临时产物。

## Milestones

- [x] 完成现状审计并确认 Python 22 项测试、Presenter Focus 浏览器测试和 Git 工作区基线正常。
- [x] 建立架构规则、Plan 索引和仓库协作入口。
- [x] 抽取 Presenter Focus Feature 源码并补齐组合契约测试。
- [x] 建立自包含 Harness，移除浏览器测试对 `examples/basic/index.html` 的依赖。
- [x] 增加统一验证命令，运行完整回归并更新最终证据。

## Acceptance gates

- `python -m unittest discover -s tests -v`
- `npm run test:presenter-focus`
- `npm test`
- Presenter Focus Harness 使用 `--strict` 构建成功。
- 构建后的 HTML 不包含未解析的 Feature 占位符。
- 浏览器测试覆盖容器聚焦、文本二级聚焦、开关、编辑模式暂停和减少动态效果。
- 正常构建仍不要求 npm，产物仍为单一 HTML。

## Outcome and validation

- Presenter Focus 的 95 行 CSS 与 42 行 JavaScript 已由 `templates/deck.html` 迁移到独立 Feature 目录；模板只保留两个组合占位符。
- Python 构建器直接读取并内联 Feature 源片段，不增加普通构建依赖，重新生成的三个已提交示例产物与迁移前逐字一致。
- 浏览器测试会用 `--strict` 将专项 Harness 构建到忽略的临时目录，完成后自动清理，不再读取 `examples/basic/index.html`。
- `npm test` 成为统一入口，并顺序运行 22 项 Python 测试和 Presenter Focus 的真实浏览器场景。
- Validation passed on 2026-08-12: Python `22/22`; Presenter Focus browser Harness passed; `basic`, `diagrams`, and `archscribe` strict example builds passed; `git diff --check` passed.
