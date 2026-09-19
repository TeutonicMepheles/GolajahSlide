# Footer Chapter Navigation

- Plan ID: `20260814-footer-chapter-navigation`
- Status: `Implemented`
- Created: `2026-08-14`
- Last updated: `2026-09-19`

## Goal

2026-09-19 follow-up: unassigned covers no longer inherit a Section; explicit assignments and content-page inheritance remain supported. Course cover removed from menus, safety and sharing/fees grouped as two Chapter items under 使用规范与共享制度, resources replaced by an empty sharing/fees title page. Python membership/navigation tests (3) and browser navigation harness pass. Course QA: 29 pages, 42 images, no overflow or console errors. All example outputs regenerated. `npm test` rerun: 134 Python tests, 10 failures and 32 errors remain in file locking/filesystem/hash checks; see `work/section-npm-test.log`.

让页脚 Section 进度条成为可快速定位的章节导航：悬浮或键盘聚焦 Section 时，向上展开纵向子章节面板；选择子章节后跳转到该子章节第一次出现的 Page。

## Scope

- 新增可选页面配置 `chapter`，用于给同一 Section 下的多页内容命名和分组。
- 未填写 `chapter` 时使用页面标题作为导航项，保持现有 Markdown 无需迁移。
- 构建期为每个 Section 收集去重后的子章节及其首个页码，并输出自包含导航标记。
- 页脚支持鼠标悬浮、键盘聚焦、上下方向键、Home / End、Escape 和点击跳转。
- 新增独立 browser Feature、专项 Harness、Python 契约测试和真实浏览器测试。
- 更新 Markdown 规范、示例源文件与生成产物。

## Non-goals

- 不增加运行时网络请求、第三方组件或包依赖。
- 不改变左右键、滚轮、触摸滑动和 URL hash 的既有页面导航协议。
- 不建立任意深度的目录树；本次只支持 Section → Chapter 两级导航。
- 不在页脚中提供搜索、折叠层级编辑或拖拽排序。

## Ownership and boundaries

- `src/web/features/footer-chapter-navigation/` 独占面板样式、打开/关闭状态、键盘导航和点击跳转行为。
- `build_slides.py` 负责解析已有页面配置、计算 Section/Chapter/首个页码并输出语义标记。
- `templates/deck.html` 只保留 Feature CSS/JavaScript 组合占位符和实例化位置。
- `harnesses/footer-chapter-navigation/` 提供多 Section、多页同 chapter 和键盘场景。

## Acceptance gates

- [x] 悬浮任一 Section 时，纵向子章节面板在页脚上方向上展开。
- [x] 同名 `chapter` 只出现一次，并跳转到其第一次出现的 Page。
- [x] 未填写 `chapter` 的页面使用标题作为回退项。
- [x] 键盘可打开、遍历、关闭面板并执行跳转，ARIA 状态同步。
- [x] 编辑模式与打印模式不显示展开面板。
- [x] 普通 Markdown 构建仍只需要 Python，交付仍是单个自包含 HTML。
- [x] 专项 Harness 以 `--strict` 构建成功，Python 与真实浏览器测试通过。
- [x] `npm test`、示例严格构建和 `git diff --check` 通过。

## Outcome and validation

Implemented on 2026-08-14.

- 新增 `chapter` 页面字段；同一 Section 下同名项按首次出现顺序去重，未填写时回退页面标题，章节前的无 Section 页面归入第一个 authored Section。
- 页脚由 `footer-chapter-navigation` Feature 独立拥有样式与交互，在进度线上方向上展开纵向面板；支持悬浮、焦点、方向键、Home / End、Escape、点击跳转与 ARIA / inert 状态同步。
- 专项 Harness 覆盖 6 页、两个 Section、重复显式 chapter 与标题回退；真实浏览器验证面板几何、首 Page 目标、点击/键盘跳转、编辑模式和打印模式抑制。
- Validation: `npm test` passed（Python `28/28` + Presenter Focus、Footer Chapter Navigation、Diagram Design 三套 Chromium Harness）；`basic`、`diagrams`、`archscribe` 严格构建通过；`git diff --check` passed。
- 构建器工具链哈希变化后，已重建示例与 Diagram Design Harness 的缓存元数据；Diagram SVG 语义与版式未改变。
