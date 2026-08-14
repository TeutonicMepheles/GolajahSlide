# 构建期 SVG 图表方案

## 结论

GolajahSlide 把 Mermaid、Diagram Design HTML 和 Excalidraw 视为可编辑源格式，把内联 SVG 视为唯一正式交付格式：

```text
Mermaid 定义 ─ Mermaid CLI ──────────────────┐
Mermaid 定义 ─ Agent 重绘 ─ Diagram HTML ───┼─ SVG + 质量报告 ─ 内联 HTML ─ Slide
Excalidraw 场景 ─ exportToSvg ───────────────┘
```

图表源码变化时显式运行渲染；普通构建只读取已经提交的 SVG。默认 Mermaid CLI 保留自动布局；`renderer: diagram-design` 保留 Mermaid 结构语义，同时让 Agent 用编辑式 HTML/SVG 精修层级、路径和留白；Excalidraw 继续承担自由拖拽。三条路径都避免演示现场的字体加载、运行时排版、脚本下载和首次闪烁。

Archscribe 仍用于确实需要路径动画的页面，不再承担默认流程图交付。

## 安装

需要 Node.js 20 以上及 Chrome、Chromium 或 Edge：

```bash
npm install
```

依赖版本锁定在 `package-lock.json`。构建器按顺序寻找：

1. `--diagram-chrome` 指定路径。
2. `DIAGRAM_CHROME` 或 `PUPPETEER_EXECUTABLE_PATH`。
3. 常见的 Chrome、Edge、Chromium 安装路径。
4. Puppeteer 管理的浏览器。

如果 Node 不在 `PATH`，使用 `--diagram-node` 指定。

## 构建

重新渲染所有 Mermaid 和 Excalidraw：

```bash
python3 build_slides.py slides.md -o index.html --render-diagrams --strict
```

内容与工具链哈希未变化时会使用缓存。强制重建：

```bash
python3 build_slides.py slides.md -o index.html --render-diagrams --force-diagrams --strict
```

发布或普通预览只需要：

```bash
python3 build_slides.py slides.md -o index.html --strict
```

## Mermaid 围栏

````markdown
```mermaid
@slide
src: assets/build-flow.svg
title: 构建流程
alt: 图表定义经过渲染和质量门禁后成为内联 SVG
caption: 可选图注
min-font-size: 28
safe-margin: 24
@end
flowchart LR
    source[图表定义] --> render[锁定版本渲染]
    render --> gate{质量门禁}
    gate --> slide[清晰 Slide]
```
````

`@slide` 元数据与 Mermaid 自己的 YAML frontmatter 分离，因此 Mermaid 定义中仍可使用官方 frontmatter。`src` 必须显式声明，避免内容变化后产生无法追踪的散列文件。

全局 Mermaid 规范位于：

- `tools/mermaid.config.json`：中文字体、28px 基准字号、颜色、节点间距、层级间距、曲线和画布留白。
- `tools/mermaid-slide.css`：节点描边、连线和字体补充约束。

主题使用 `base`，项目级样式优先写入全局配置；单图语义颜色可通过 Mermaid `classDef` 设置。

## Mermaid + Diagram Design

当自动布局正确但视觉层级仍像“默认 Mermaid”时，在同一个 Mermaid 围栏中显式选择编辑式渲染器：

````markdown
```mermaid
@slide
renderer: diagram-design
source: assets/build-flow.diagram.html
src: assets/build-flow.svg
title: 构建流程
alt: Mermaid 语义进入编辑式重绘，通过门禁后成为内联 SVG
detail: faithful
audience: mixed
min-font-size: 28
safe-margin: 40
@end
flowchart LR
    source[图表定义] --> design[编辑式重绘]
    design --> gate{质量门禁}
    gate --> slide[清晰 Slide]
```
````

项目级 Skill 位于 `.agents/skills/golajah-diagram-design/`。在 Codex 中要求“优化这张 Mermaid”或显式调用 `$golajah-diagram-design`，它会：

1. 用只解析文本、不执行 Mermaid 或链接的脚本提取节点与关系。
2. 保留 Mermaid 定义作为语义源，生成自包含的 `.diagram.html` 编辑源。
3. 使用 1840×800 画布、至少 28px 字号、40px 安全区和 GolajahSlide 主题 token 重绘。
4. 运行 `--render-diagrams`，从 HTML 提取首个 SVG 并生成质量报告。

`source` HTML 不得包含脚本、远程字体、外部样式或图片。构建报告同时记录 Mermaid 定义哈希、HTML SHA-256 和 SVG SHA-256；任一来源变化而未重建时，普通构建都会失败。`.diagram.html` 是手工/Agent 编辑源，`.svg` 与 `.diagram-build.json` 由构建器生成，不应直接修改。

Diagram Design 是 Agent 驱动的有意构图流程，不是 Mermaid CLI 的另一套主题；因此 `--render-diagrams` 只负责确定性提取、校验和缓存，不会自动替你重新设计几何布局。仓库适配来源于 [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design)，使用 MIT 许可并固定记录上游 commit。

## Excalidraw 围栏

````markdown
```excalidraw
source: assets/editable-flow.excalidraw
src: assets/editable-flow.svg
title: 可编辑流程
alt: Mermaid 与 Excalidraw 汇入统一质量门禁
caption: 可选图注
min-font-size: 28
safe-margin: 24
```
````

`source` 是可继续编辑的场景，`src` 是官方 `exportToSvg` 的输出。构建器使用 `roughness`、位置、颜色和字号等场景属性生成 SVG，再统一使用 Slide 中文字体栈。需要严格品牌化的 Excalidraw 图应采用 `roughness: 0`、足够宽的文本容器和至少 28px 的源字号。

## SVG 质量门禁

每个 SVG 旁边会生成同名 `.diagram-build.json`，记录：

- 渲染引擎与构建输入哈希。
- Diagram Design 路径的 Mermaid 语义哈希与 HTML 编辑源 SHA-256。
- SVG SHA-256，防止场景和质量报告错配。
- `viewBox` 尺寸。
- 源文件最小字号。
- 渲染器安全边距。

Markdown 解析时还会根据页面是否隐藏页脚，使用真实的 1840×800 或 1700×716 图表区域计算投影字号。默认要求投影后不低于 28px，安全边距不低于 24px。

为保证换算与实际版面一致，每页最多放置一个 Mermaid 或 Excalidraw 图表，且不与正文卡片混排；补充说明应写入副标题或 `caption`。

内联前会：

- 给所有 SVG ID 加页面级前缀，避免多个图表的 marker、gradient 和 filter 冲突。
- 同步更新 CSS 选择器和 `url(#id)` 引用。
- 移除固定宽高，保留 `viewBox` 与 `preserveAspectRatio`。
- 移除脚本、`foreignObject`、事件属性与外部 URL。
- 写入 `<title>`、`<desc>`、ARIA 属性和项目字体栈。

## 选择原则

- 自动布局、快速迭代、节点较多的规整流程：默认 Mermaid CLI。
- 面向演示的架构、流程、时序、状态和 ER 图，且需要更强视觉层级：Mermaid + `renderer: diagram-design`。
- 自由构图、人工拖拽、特殊强调与批注：Excalidraw。
- Mermaid 转 Excalidraw：只作为一次性编辑起点，转换后以 `.excalidraw` 为唯一源。
- 路径动画：Archscribe，且必须提供静态 poster。
- 柱状图、折线图和统计图：继续使用内置 `chart`，复杂数据可视化后续应接入 ECharts 或 Vega-Lite，而不是 Mermaid。
