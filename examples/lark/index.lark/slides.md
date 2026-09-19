---
title: 通用 Markdown Slides 工程模板
subtitle: 从结构化内容到可演示 HTML
author: Your Name
date: 2026-08
lang: zh-CN
density: reading
kicker: PRESENTATION TEMPLATE
sections: ["开始", "自动布局", "内容组件", "交付检查"]
---

<!-- slide
id: cover
type: cover
layout: auto
-->
# 通用 Markdown Slides 工程模板
## 固定 16:9、智能图片布局、中文排版与可复用图表控件
---

<!-- slide
id: layout-section
type: section
section: 自动布局
-->
# 让内容决定版式
## 图片比例、文本密度与语义结构共同参与布局选择
---

<!-- slide
id: square-image
type: content
layout: auto
section: 自动布局
image-position: left
image-fit: contain
-->
# 接近 1:1 的图片自动进入左右布局
## 视觉与解释并列，避免图片缩成难以阅读的小图

![图片](assets/ce2b2731f8908acd37d3b777.png)


### 自动判断
- 图片宽高比在 `0.72–1.35` 之间时，==优先使用图文左右布局==
- 竖图使用更窄的图片栏，横图使用更宽的图片栏
### 手动控制
需要改变阅读顺序时，可设置 `image-position: right`。
---

<!-- slide
id: wide-image
type: content
layout: auto
section: 自动布局
image-fit: contain
-->
# 接近 16:9 的图片优先占满展示区域
## 图片下方只保留简短说明，建议不超过两行

![图片](assets/ea976681f4952c351cbd7550.png)


这类页面让视觉成为主角；如果说明文字超过两行容量，构建器会自动回退为图文左右布局并给出提示。
---

<!-- slide
id: chinese-layout
type: content
layout: auto
section: 内容组件
-->
# 中文内容页强调层级与呼吸感
## 标题、副标题保持同一高度，统一左对齐
### 一页一个核心结论
正文先写结论，再补充证据。演讲型页面尽量控制在 1–3 个要点；阅读型页面可以使用更完整的结构，但仍应优先拆页。
### 使用稳定的字号台阶
页面标题、卡片标题、正文、标签和图注各自保持清晰层级，避免所有文字挤在同一字号。
### 避免中文孤字
模板使用更适合中文的断行策略；表格不再允许任意位置切断英文标识符。
> [!TIP]
> 内容不足时会扩大单卡片的视觉权重；内容过多时构建报告会建议拆页。
---

<!-- slide
id: table-controls
type: content
layout: table
section: 内容组件
-->
# 表格沿用现有视觉控件
## 悬停后可缩放、全屏与临时标注

| 页面元素 | Markdown 写法 | 默认行为 |
| --- | --- | --- |
| 标题 / 副标题 | `#` / `##` | 内容页左对齐 |
| 内容卡片 | `###` + 正文 | 依据数量自动排成 1–3 列 |
| 表格 | GFM Table | 自动列宽、避免任意断词 |
| 图片 | `![alt](path "caption")` | 读取宽高比后选择布局 |
| 提示 | `> [!TIP]` | 转换为强调卡片 |

---

<!-- slide
id: chart-controls
type: content
layout: chart
section: 内容组件
-->
# 轻量图表直接写在 Markdown 中
## 图表也复用缩放、全屏和标注控件
```chart
type: bar
title: 各阶段投入占比
labels: 调研 | 设计 | 开发 | 验证
values: 22 | 31 | 28 | 19
unit: %
```
> [!NOTE]
> 内置 `bar`、`line`、`donut` 三种图表；复杂图表建议导出为 SVG 后按图片引用。
---

<!-- slide
id: delivery-check
type: content
layout: auto
section: 交付检查
-->
# 构建报告让问题在交付前暴露
## 版式选择可追踪，风险不会静默被裁掉
### 构建期检查
- 缺失图片、图表字段错误直接报错
- 标题过长、内容过密、表格行数过多给出警告
- `index.build.json` 记录每页最终采用的布局
### 浏览器检查
- `window.__SLIDE_DIAGNOSTICS__` 暴露运行时溢出结果
- 加 `?debug=1` 会在页面上标出发生溢出的容器
- 固定 1920×1080 舞台在宽屏、投影和手机上只做等比缩放
