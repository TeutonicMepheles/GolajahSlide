# Markdown Slides 编辑规范

这套规范的目标不是兼容所有 Markdown 方言，而是让“内容意图 → 页面布局”稳定、可预测。遵循规范的任意 `.md` 文件都可以由 `build_slides.py` 转换为固定 1920×1080 的 HTML 演示稿。

## 1. 文档结构

文件由三部分组成：文档级配置、页面分隔线、页面级配置与内容。

```markdown
---
title: 演示文稿标题
author: 作者
date: 2026-08
lang: zh-CN
density: reading
sections: ["背景", "方案", "结果"]
---

<!-- slide
type: cover
-->
# 演示文稿标题
## 一句副标题

---

<!-- slide
id: background-summary
type: content
layout: auto
section: 背景
-->
# 页面标题
## 页面副标题

页面内容……
```

第一组 `---` 是文档配置边界；之后每一条单独成行的 `---` 都会创建新页面。

## 2. 文档级配置

| 字段 | 是否必需 | 可选值 / 写法 | 用途 |
|---|---:|---|---|
| `title` | 建议 | 文本 | 浏览器标题与默认演示标题 |
| `author` | 否 | 文本 | 封面元信息 |
| `date` | 否 | 文本 | 封面元信息 |
| `lang` | 否 | `zh-CN` 等 | HTML 语言，默认 `zh-CN` |
| `density` | 否 | `reading` / `speaking` | 全稿默认内容密度，默认 `reading` |
| `kicker` | 否 | 短文本 | 封面标题上方的小标签 |
| `sections` | 建议 | JSON 数组 | 页脚章节导航，建议不超过 7 项 |
| `default-section` | 否 | 文本 | 未单独填写 `section` 时的默认章节 |

`reading` 适合异步阅读、报告和留档；`speaking` 适合现场演讲，会采用更大的正文和更严格的内容量建议。单页可用页面配置覆盖。

## 3. 页面级配置

页面开头使用 HTML 注释形式的配置块：

```markdown
<!-- slide
type: content
layout: auto
section: 方案
density: speaking
image-position: right
image-fit: contain
footer: true
-->
```

| 字段 | 默认值 | 可选值 | 含义 |
|---|---|---|---|
| `id` | `p<页码>` | 字母、数字、`-`、`_` | 页面稳定标识；使用编辑器时强烈建议每页唯一填写 |
| `type` | `content` | `cover` / `section` / `content` | 页面语义类型 |
| `layout` | `auto` | `auto` / `text` / `split` / `media` / `gallery` / `table` / `chart` | 布局策略 |
| `section` | 空 | 章节名 | 决定页脚高亮项 |
| `density` | 文档默认值 | `reading` / `speaking` | 本页内容密度 |
| `image-position` | `left` | `left` / `right` | 左右图文页的图片位置 |
| `image-fit` | `contain` | `contain` / `cover` | 图片完整显示或裁切填充 |
| `footer` | 内容页为 `true` | `true` / `false` | 是否显示章节页脚 |

`layout: auto` 是推荐用法；手动指定布局只用于表达特殊叙事意图。构建报告会同时记录 requested 和 resolved layout，方便排查自动回退。

`id` 是 Markdown 页面与编辑器覆盖配置之间的主键。增加或删除前面的页面时，显式 `id` 不会变化；若省略而使用默认页码 ID，页面顺序变化可能让旧覆盖应用到错误页面。

## 4. 页面编辑器与布局覆盖

构建后的 HTML 自带页面编辑器。按 `E` 或点击控制条中的 `✦`，可以选择布局、调整内容区域、设置正文排版并编排内容出现顺序。编辑结果可导出为与 Markdown 同名的 `.layout.json` 文件，重建时会自动应用。

坐标体系、文件结构、字段范围、优先级和动画键的完整说明见 [Slide 布局覆盖规范](LAYOUT-SPEC.md)。

## 5. 页面标题与副标题

- `#` 是页面标题，每页必须且只能有一个。
- `##` 是页面副标题，每页最多一个。
- 内容页标题与副标题统一左对齐。
- 标题区位置固定：`top: 66px; height: 118px`，内容区仍从 `214px` 开始。
- 建议标题不超过 28 个中英文字符，副标题不超过 38 个字符；构建器会对超长内容给出警告。

封面页和章节页没有图片时自动显示中性视觉占位框；在相应页面加入项目自己的图片引用即可替换占位。

## 6. 图片写法与自动布局

图片必须独占一行：

```markdown
![说明图片的内容](assets/example.png "显示在画面上的简短图注")
```

- `alt` 必须描述图片实际表达的内容，用于可访问性与图片加载失败时的替代信息。
- 引号中的 `caption` 可选，应说明来源、数据范围或阅读方式，不要重复页面标题。
- 本地路径相对于 Markdown 文件所在目录解析；输出 HTML 会自动改写为相对于输出文件的路径。
- 支持 PNG、JPEG、GIF、WebP、SVG 的尺寸识别。远程图片无法在构建期读取尺寸，会按 16:9 处理并给出警告。

### 自动布局决策表

| 图片数量 / 宽高比 | 条件 | 自动布局 | 内容要求 |
|---|---|---|---|
| 0 张 | — | `text`，单表格时为 `table` | 按卡片数量自动排成 1–3 列 |
| 1 张竖图 | `< 0.72` | `split`，窄图片栏 | 说明放在另一侧 |
| 1 张近方图 | `0.72–1.35` | `split` | 适合图解、界面局部、人物或物体 |
| 1 张近屏幕图 | `1.35–2.20` 且文字 ≤ 96 字、内容块 ≤ 1 | `media` | 图片占满主要展示区，下方说明最多两行 |
| 1 张横图但文字较多 | 任意 | `split` | 不会为了保留满幅图而截断文字 |
| 2 张图片 | — | `gallery` 双图并列 | 图片应有可比较关系 |
| 3 张及以上 | — | `gallery` 单图舞台 + 切换按钮 | 避免缩成不可读缩略图 |

这些阈值以内容区而不是文件像素数为依据。像素尺寸只用于计算比例；清晰度仍需要作者自己保证。

### 何时手动指定布局

- `layout: split`：即使图片接近 16:9，也希望保留较多解释文字。
- `layout: media`：明确需要大图主导。若文字超过两行容量，构建器仍会回退为 `split`。
- `layout: gallery`：希望把两张以上图片视为同一组。
- `image-fit: cover`：允许裁切边缘，常用于照片；界面截图、图表和文字型图片应使用 `contain`。

## 7. 正文与卡片

三级标题会开启一个内容卡片，后续段落或列表进入该卡片，直到下一个三级标题或特殊块。

```markdown
### 核心结论

先写结论，再补充证据。

- 证据一
- 证据二
```

没有三级标题的普通段落也会形成卡片。页面会按内容块数量自动充实版面：

- 1 个普通内容块：扩大内边距和正文，形成重点页。
- 2 个内容块：两列。
- 3 个内容块：三列。
- 4 个内容块：2×2。
- 5–6 个内容块：三列网格；超过 6 个会提示拆页。

演示时可在已聚焦的文字容器内继续悬停标题、段落或列表项，进一步引导观众视线。需要把焦点精确到一句或短语时，使用双等号：

```markdown
- 图片宽高比合适时，==优先使用图文左右布局==。
```

`==...==` 会保留轻微的主题色标记，悬停时提升为片段级高亮；它不会改变构建期布局判断或文字内容。

建议容量：

| 类型 | 演讲型 `speaking` | 阅读型 `reading` |
|---|---:|---:|
| 正文总量 | 约 430 字以内 | 约 760 字以内 |
| 普通要点 | 1–3 条 | 4–8 条 |
| 内容卡片 | 1–4 个 | 1–6 个 |
| 表格数据行 | 6 行以内 | 8 行以内 |

这些是预警线，不是自动缩字号的触发线。超过时优先拆页。

## 8. 提示与引用

使用兼容常见 Markdown 工具的 callout 写法：

```markdown
> [!TIP]
> 这是方法提示。

> [!WARNING]
> 这是风险提示。
```

支持 `TIP`、`NOTE`、`WARNING`、`QUOTE`、`QUESTION`。标签会转为中文，字号低于同级卡片标题，避免提示语抢夺层级。

## 9. 表格

使用标准 GFM 表格：

```markdown
| 方案 | 优点 | 风险 |
|---|---|---|
| A | 速度快 | 需要校验 |
| B | 控制强 | 成本较高 |
```

- 表格使用自动列宽，不强制等宽。
- 中文按语义自然换行；英文标识符不会被 `anywhere` 任意切断。
- 行内代码会优先在下划线后产生可控换行机会。
- 表格默认复用视觉控件：悬停后可缩放、全屏和临时矩形标注。
- 超过 8 个数据行应拆成两页，或改为突出重点的图表。

## 10. 图表

轻量数据图表使用 `chart` 围栏：

````markdown
```chart
type: line
title: 月活变化
labels: 1月 | 2月 | 3月 | 4月
values: 22 | 31 | 28 | 41
unit: 万
```
````

支持：

- `type: bar`：分类比较。
- `type: line`：趋势变化。
- `type: donut`：构成关系。

内置图表适合单序列、少量分类。多序列、散点、地图、复杂标注或严谨统计图应在外部工具完成后导出 SVG，再以图片引用；SVG 同样会获得视觉控件。

### 10.1 Mermaid 流程图

规整流程、架构、时序与状态图优先使用 Mermaid。`@slide` / `@end` 之间是 GolajahSlide 元数据，之后才是原始 Mermaid 定义：

````markdown
```mermaid
@slide
src: assets/order-flow.svg
title: 订单处理流程
alt: 订单经过校验、支付与发货，失败时返回人工复核
min-font-size: 28
safe-margin: 24
@end
flowchart LR
    order[收到订单] --> check{校验通过？}
    check -->|是| pay[支付]
    pay --> ship[发货]
    check -.->|否| review[人工复核]
```
````

首次生成或源码变化后运行：

```bash
python3 build_slides.py slides.md -o index.html --render-diagrams --strict
```

构建器调用锁定版本的 Mermaid CLI 生成 SVG，同时写入同名 `.diagram-build.json`。普通构建会检查 SVG 哈希、投影字号和安全边距，然后把 SVG 直接内联到 HTML；成品页面不加载 Mermaid JavaScript。

### 10.2 Excalidraw 流程图

需要人工拖拽、批注或自由构图时保留 `.excalidraw` 场景，并引用构建后的 SVG：

````markdown
```excalidraw
source: assets/system-flow.excalidraw
src: assets/system-flow.svg
title: 系统交付流程
alt: 两种输入经过质量门禁后交付 Slide
min-font-size: 28
safe-margin: 24
```
````

`--render-diagrams` 会通过官方 `exportToSvg` 生成矢量产物。Excalidraw 编辑器不进入发布 HTML，场景文件仍可继续编辑。Mermaid 转 Excalidraw 只建议用作一次性的初稿转换，不作为双向同步链路。

Mermaid 与 Excalidraw 默认都要求：

- `src` 是本地 `.svg`，禁止远程运行时依赖。
- `min-font-size` 默认 28，按实际 Slide 图表区域换算。
- `safe-margin` 默认 24，渲染器输出使用 32px。
- SVG 与 `.diagram-build.json` 哈希必须一致。
- `<script>`、`foreignObject`、事件属性和外部引用不会进入内联 HTML。

完整设计和安装说明见 [构建期 SVG 图表方案](DIAGRAMS.md)。

### 10.3 动态流程图（Archscribe，可选）

复杂流程、判断节点与失败回路可以使用 `archscribe` 围栏：

````markdown
```archscribe
spec: assets/order-flow.spec.json
src: assets/order-flow.gif
poster: assets/order-flow.png
title: 订单处理动态流程图
alt: 从接单到发货，失败时返回人工复核的中文流程图
caption: 动画由 Archscribe 生成
crop: 50,160,1110,330
mask: 895,0,215,42
min-font-size: 28
safe-margin: 24
```
````

`spec` 与 `src` 必填；`poster` 强烈建议提供，系统开启“减少动态效果”时会自动显示 PNG。围栏会自动采用 `chart` 布局，并复用图表的缩放、全屏与标注控件。

用于 Slide 时应让 Slide 标题承担页面结论，使用 `crop` 移除 Archscribe 自带的标题和页脚，只保留流程主体。`crop` 的格式是源画布上的 `x,y,width,height`；若签名与内容安全区重叠，可用裁切后坐标的 `mask` 遮罩品牌角。`min-font-size` 默认 28，构建器会读取 Excalidraw 的实际字号并按 Slide 展示尺寸换算；`safe-margin` 默认 24 源像素，用于确保节点、连线和回路没有贴住裁切边界。任一门禁不满足都会直接报错。

普通构建只嵌入已有文件。需要根据 JSON 重新生成 GIF、PNG 与 Excalidraw 时，安装 [Archscribe](https://github.com/lazypay/Archscribe) 后使用 `--render-archscribe`；完整说明见 [Archscribe 动态流程图接入方案](ARCHSCRIBE-INTEGRATION.md)。

## 11. 中文排版规则

- 不使用连续空格人工对齐；交给网格与卡片布局。
- 标题不要用手动换行控制位置；需要换页时使用 `---`。
- 卡片标题、callout 标签、代码标签和表头的字号必须大于同块正文，不能用颜色代替字号层级。
- 中文与英文、数字之间保持自然间距，不用全角空格填充。
- 一段只表达一个观点，长段落拆成短段或列表。
- 避免把完整文档原封不动贴进单页；Slide 不是滚动页面。
- 图注用于来源或阅读提示，不能承担第三段正文。
- 对 URL、snake_case、代码等使用反引号包裹，以获得更安全的断行。

## 12. 构建与质量门槛

```bash
python3 build_slides.py slides.md -o index.html
```

构建会同时输出 `index.build.json`，包含页数、每页最终布局、警告和错误。

```bash
python3 build_slides.py slides.md -o index.html --strict
```

`--strict` 会把所有设计警告也视为失败，适合 CI 或正式交付前检查。

浏览器加载后可在控制台读取：

```js
window.__SLIDE_DIAGNOSTICS__
```

访问 `index.html?debug=1` 会用红色边框标出检测到溢出的容器。检查至少覆盖：

- 1920×1080 或 1280×720 的 16:9 视口。
- 一个手机竖屏视口，确认舞台整体缩放且不重排。
- 图片加载、切换、缩放、全屏、标注。
- 标题、副标题、正文卡片、表格和图注没有裁切。

## 13. 素材治理建议

模板本身只提供中性比例示意图，不带入参考演示稿的业务图片。实际项目建议为每个素材维护：

- 文件来源与原始链接。
- 作者、授权范围和到期时间。
- 截图日期与产品版本。
- 数据图表的时间范围、单位和口径。
- 替代文本与是否允许裁切。

可以在仓库增加 `SOURCES.md`，并让图注只保留面向观众的简短信息。

## 14. 与 AI 协作编写 Slide

不要只向 AI 提出“做三页 PPT”。先说明这段内容对观众要完成的沟通任务，再提供事实、素材与限制。推荐至少给出：

- 观众及其背景知识。
- 期望观众理解、相信、选择或执行什么。
- 整段内容最重要的一句话。
- 必须使用且不可虚构的事实、数据和来源。
- 已有图片路径、图片含义以及是否允许裁切。
- 页数、所属章节以及 `speaking` 或 `reading` 场景。

推荐让 AI 分两步工作：先给页面规划，确认每页只有一个主要结论；再生成可直接构建的 Markdown。

可以复制下面的提示词：

```text
请按照 GolajahSlide 的 Markdown 规范设计一段演示文稿。

观众：[观众及其背景]
沟通目标：[希望观众理解、相信、决定或执行什么]
核心结论：[整段内容最重要的一句话]
页数与场景：[页数；现场演讲 speaking / 异步阅读 reading]
所属章节：[章节名称]

必须使用的事实与素材：
- [事实、数据或案例]
- [图片路径、含义及是否允许裁切]

限制：
- 不虚构数据、案例、引用或素材来源
- 一页只表达一个主要结论
- 使用结论式标题，标题不超过 28 个中英文字符
- 副标题不超过 38 个字符
- 每页生成稳定、唯一、语义化的 id
- 默认使用 layout: auto，只有明确叙事理由时手动指定布局
- speaking 页面优先保留 1–3 个要点，内容过多时拆页

第一步先输出页面规划：每页的沟通任务、结论式标题、证据、推荐视觉和布局理由。
结构确认后，再输出完整 Markdown；不要附加无法被构建器识别的语法。
```

修改已有页面时，应提供原 Markdown，并明确指出当前问题、需要保留的事实、期望的视觉主次以及是否必须保留页面 `id`。已有布局覆盖时必须保留 `id`，否则 `.layout.json` 无法继续关联该页。
