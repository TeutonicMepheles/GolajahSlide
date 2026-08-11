# 构建期 SVG 图表方案

## 结论

GolajahSlide 把 Mermaid 和 Excalidraw 视为可编辑源格式，把内联 SVG 视为唯一正式交付格式：

```text
Mermaid 定义 ─ Mermaid CLI ─────┐
                               ├─ SVG + 质量报告 ─ 内联 HTML ─ Slide
Excalidraw 场景 ─ exportToSvg ─┘
```

图表源码变化时显式运行渲染；普通构建只读取已经提交的 SVG。这样既保留 Mermaid 自动布局和 Excalidraw 人工精修能力，也避免演示现场的字体加载、运行时排版、脚本下载和首次闪烁。

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

- 自动布局、规整流程、架构、时序和状态图：Mermaid。
- 自由构图、人工拖拽、特殊强调与批注：Excalidraw。
- Mermaid 转 Excalidraw：只作为一次性编辑起点，转换后以 `.excalidraw` 为唯一源。
- 路径动画：Archscribe，且必须提供静态 poster。
- 柱状图、折线图和统计图：继续使用内置 `chart`，复杂数据可视化后续应接入 ECharts 或 Vega-Lite，而不是 Mermaid。
