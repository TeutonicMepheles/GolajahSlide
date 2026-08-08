# Slide 布局覆盖规范

布局覆盖文件用于记录某一份演示稿在浏览器编辑器中的页面级调整。它应与 Markdown 同目录并使用同名主文件，例如：

```text
slides.md
slides.layout.json
```

它不是全局主题或模板配置。全局舞台、基础样式和交互由 `templates/deck.html` 提供，自动布局规则由 `build_slides.py` 提供。

## 1. 自动加载与优先级

普通构建会自动读取同名覆盖文件：

```bash
python3 build_slides.py slides.md -o index.html
```

也可以显式指定其他文件：

```bash
python3 build_slides.py slides.md --overrides review.layout.json -o index.html
```

覆盖配置优先于 Markdown 中的 `layout`。构建器仍会校验内容语义：没有表格的页面不能使用 `table`，没有 `chart` 围栏的页面不能使用 `chart`；不兼容值会回退为 `auto` 并写入构建警告。

## 2. 文件结构

```json
{
  "schemaVersion": "1.0",
  "stage": {"width": 1920, "height": 1080},
  "deckTitle": "演示文稿标题",
  "source": "slides.md",
  "slides": {
    "background-summary": {
      "layout": "split",
      "typography": {
        "lineHeight": 1.55,
        "color": "#222222",
        "bold": false
      },
      "animation": {
        "mode": "custom",
        "order": ["header", "block-1", "visual"],
        "stepMs": 120
      },
      "regions": {
        "content": {"x": 110, "y": 214, "width": 1700, "height": 716},
        "visual": {"x": 110, "y": 214, "width": 702, "height": 716},
        "copy": {"x": 840, "y": 214, "width": 970, "height": 716}
      }
    }
  }
}
```

`slides` 的键必须对应 Markdown 页面配置中的稳定 `id`。不要依赖默认页码 ID，否则在页面前方增删内容后，旧覆盖可能应用到错误页面。

## 3. 布局类型

| 值 | 用途 |
|---|---|
| `auto` | 根据页面语义、图片比例、图片数量和文字密度自动选择 |
| `text` | 无主要视觉的正文或卡片页面 |
| `split` | 图片与说明左右并列 |
| `media` | 横向大图主导，说明文字很短 |
| `gallery` | 两张及以上相关图片 |
| `table` | 以一个 Markdown 表格为主要内容 |
| `chart` | 以一个内置轻量图表为主要内容 |

推荐在 Markdown 中保留 `layout: auto`，只把经过浏览确认的人工调整写入覆盖文件。

## 4. 设计坐标

所有坐标均基于 1920×1080 设计舞台，与浏览器缩放比例无关。区域最小为 48×48；越界坐标会被限制在舞台内。

| 区域 | 含义 |
|---|---|
| `content` | 页面主要内容的总边界，通常避开标题区与页脚 |
| `visual` | 图片、画廊、表格或图表区域 |
| `copy` | 正文、卡片和说明区域 |

导入其他舞台尺寸的覆盖文件时，构建器会按比例换算到 1920×1080，并记录警告。

## 5. 正文排版

`typography` 只影响正文段落、列表项、代码正文和表格数据单元格，不改变页面标题或卡片标题。

| 字段 | 范围 |
|---|---|
| `lineHeight` | `1.10–1.80` |
| `color` | `#RGB` 或 `#RRGGBB`，构建时规范化为六位十六进制 |
| `bold` | `true` 或 `false` |

## 6. 动画顺序

`animation.mode: custom` 启用自定义出现顺序：

- `header`：标题区
- `visual`：图片、画廊或图表区
- `block-1`、`block-2`：按 Markdown 顺序生成的正文容器
- `hero-copy`：封面或章节页文字

重复或非法键会被移除；没有列出的容器会自动追加到自定义顺序之后。`stepMs` 会被限制在构建器允许的范围内。

## 7. 编辑闭环

推荐流程：Markdown 写内容 → 构建 HTML → 按 `E` 打开编辑器 → 调整页面 → 导出布局 JSON → 重新构建 → 检查构建报告与浏览器诊断。

编辑器只导出发生过调整的页面，因此覆盖文件应当保持精简，不需要复制每一页的自动布局结果。
