# Archscribe 动态流程图接入方案

## 结论

GolajahSlide 当前并未集成 Mermaid。现有 `chart` 代码围栏由 `build_slides.py` 在构建期直接生成内联 SVG，只覆盖单序列柱状图、折线图与环形图；复杂流程图只能在外部生成 SVG，再按普通图片嵌入。

本分支把 [Archscribe](https://github.com/lazypay/Archscribe) 接成可选的构建期能力：Markdown 中的 `archscribe` 围栏声明 JSON 配置和目标产物，`--render-archscribe` 负责按需生成 GIF、PNG、Excalidraw，之后沿现有 HTML 模板、视觉控件和布局编辑器进入 Slide。默认构建不会安装或调用第三方依赖，仓库中存在预生成产物时仍保持原来的零依赖体验。

## 当前图表链路

```text
Markdown chart 围栏
  → parse_blocks()
  → parse_chart()
  → render_chart_svg()
  → chart 布局
  → 单文件 HTML
  → 缩放 / 全屏 / 标注
```

这条链路的优点是确定、离线、没有浏览器端依赖；限制是图形类型固定，没有节点、边、判断与回路模型，也没有路径动画。仓库中没有 Mermaid 脚本、Mermaid CLI、`mermaid` 围栏或 Mermaid AST 转换代码。

## 新增 Archscribe 链路

```text
Archscribe JSON spec
  → 可选 --render-archscribe
  → Archscribe CLI
  → GIF + PNG + Excalidraw
  → archscribe Markdown 围栏
  → chart 布局
  → 单文件 Slide 外壳 + 相对路径媒体
```

产物职责如下：

| 产物 | Slide 中的用途 |
|---|---|
| GIF | 默认动态播放，表达路径传播和回路 |
| PNG | `prefers-reduced-motion: reduce` 时自动降级 |
| Excalidraw | 保留可编辑源文件，便于人工微调 |
| JSON spec | 流程语义的唯一来源，进入版本控制 |

## 安装与构建

Archscribe 采用 MIT 许可证，但本仓库不复制其源码。把一个独立 checkout 的路径传给构建器，或设置 `ARCHSCRIBE_HOME`：

```powershell
git clone https://github.com/lazypay/Archscribe.git C:\Tools\Archscribe
python -m venv C:\Tools\Archscribe\.venv
C:\Tools\Archscribe\.venv\Scripts\python.exe -m pip install -r C:\Tools\Archscribe\requirements.txt

python build_slides.py examples/archscribe/slides.md `
  -o examples/archscribe/index.html `
  --render-archscribe `
  --archscribe-home C:\Tools\Archscribe `
  --archscribe-python C:\Tools\Archscribe\.venv\Scripts\python.exe
```

首次渲染会生成三个同名文件。后续仅当 spec 比三个产物新时才重新渲染；使用 `--force-archscribe` 可以强制刷新。`--archscribe-renderer auto` 优先使用 Archscribe 的浏览器渲染器，不可用时回退 Pillow；也可以显式选择 `browser` 或 `pillow`。

只复用已提交产物时无需 Archscribe：

```powershell
python build_slides.py examples/archscribe/slides.md -o examples/archscribe/index.html
```

## Markdown 语法

````markdown
```archscribe
spec: assets/order-flow.spec.json
src: assets/order-flow.gif
poster: assets/order-flow.png
title: 订单处理动态流程图
alt: 从接单到发货，失败时返回人工复核的流程图
caption: 动画由 Archscribe 生成
crop: 50,160,1110,330
mask: 895,0,215,42
min-font-size: 28
safe-margin: 24
```
````

- `spec`、`src` 必填；构建期渲染只接受本地路径。
- `src` 使用 GIF；`poster` 使用同目录、同文件名的 PNG。
- `title` 是视觉控件的无障碍名称，`alt` 描述图中实际信息，`caption` 面向观众。
- `crop` 使用 Archscribe 原始画布坐标裁出流程主体；重渲染时会同时裁切 GIF 与 PNG，不修改 Excalidraw。
- `mask` 使用裁切后坐标遮罩与流程主体重叠的品牌角；GIF 每一帧与 PNG 使用同一遮罩。
- `min-font-size` 默认 28px。构建器读取 Excalidraw 的实际文字大小并换算到 1840×800 的 Slide 流程图区，低于下限会阻止交付。
- `safe-margin` 默认 24 源像素。构建器检查裁切视口内的节点、箭头和回路，任何内容贴近边界都会阻止交付。
- `layout: auto` 会把 `archscribe` 块识别为通栏图表；也可显式写 `layout: chart`。

### Slide 专用排版约束

- 页面结论与副标题由 Slide 原生标题区承担，不能在图内重复。
- 图内只保留 4–6 个短标签节点；说明文字移到讲稿或拆成下一页。
- 流程图页设置 `footer: false` 后使用 1840×800 安全视口，为图内文字争取足够投影字号。
- 边标签不是必需信息时应删除；Archscribe 的边标签字号低于节点标签，容易成为整页最小字号。
- `crop` 必须保留节点、箭头和回路至少 24px 的源画布安全边距，不能仅以“内容仍可见”为标准。

## 为什么不在浏览器端直接运行 Mermaid 或 Archscribe

Archscribe 是 Python/Chromium 构建工具，不是可直接放进模板的浏览器组件。构建期生成能保留 GolajahSlide 的离线交付方式，避免演示现场下载脚本、字体或图标，也让 GIF、PNG、Excalidraw 与 JSON 一起接受版本审查。

当前方案优先嵌入 GIF，而不直接嵌入 Archscribe 的交互 HTML。后者会引入 iframe 焦点、键盘翻页冲突、全屏嵌套和本地文件权限问题；如果未来确实需要点击节点探索，可在第二阶段增加显式的 `mode: interactive`，而不是改变默认行为。

## 风险与后续

- GIF 与 Slide 的逐项出现动画尚未共享时间轴；进入页面后 GIF 独立循环。
- 浏览器渲染器需要 Playwright Chromium；MP4 还需要 ffmpeg。Pillow 路径只需 `Pillow` 与 `svg.path`。
- Archscribe 的自定义 `icon_file` 会读取本地 SVG/PNG，只应使用可信资产。
- CI 建议固定 Archscribe commit，并缓存 Python/Chromium 依赖；正式构建使用 `--strict` 和 Archscribe 自带的 `--check`（本接入已自动传递）。
- Mermaid 与 Excalidraw 已作为独立视觉块统一归入 `chart` 布局，并在构建期输出内联 SVG；见 [构建期 SVG 图表方案](DIAGRAMS.md)。不要把 Mermaid 文本先转换为 Archscribe JSON，两者的布局与动画语义不同。
