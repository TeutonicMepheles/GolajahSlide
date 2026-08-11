---
title: 构建期 SVG 图表示例
subtitle: Mermaid 负责自动布局，Excalidraw 负责自由精修
author: GolajahSlide
date: 2026-08
lang: zh-CN
density: speaking
sections: ["流程图"]
---

<!-- slide
id: mermaid-svg-flow
type: content
layout: chart
section: 流程图
footer: false
-->
# Mermaid 保持流程结构清晰规整
## 构建期生成 SVG，发布页面不加载 Mermaid 运行时

```mermaid
@slide
src: assets/mermaid-build-flow.svg
title: GolajahSlide 图表构建流程
alt: Markdown 中的 Mermaid 定义经过主题约束、SVG 质量门禁后内联到 Slide
min-font-size: 28
safe-margin: 24
@end
flowchart LR
    source[Markdown 图表定义] --> renderer[锁定版本渲染]
    renderer --> gate{质量门禁}
    gate -->|通过| inline[内联 SVG]
    inline --> slide[清晰 Slide]
    gate -.->|失败| source

    classDef source fill:#E8F0F8,stroke:#2C8C99,color:#151515,stroke-width:2px
    classDef process fill:#D9E9DF,stroke:#24836D,color:#151515,stroke-width:2px
    classDef decision fill:#F1EEFF,stroke:#6F60E5,color:#151515,stroke-width:2px
    classDef result fill:#FFFFFF,stroke:#24836D,color:#151515,stroke-width:2px
    class source source
    class renderer,inline process
    class gate decision
    class slide result
```

---

<!-- slide
id: excalidraw-svg-flow
type: content
layout: chart
section: 流程图
footer: false
-->
# Excalidraw 用于需要人工精修的自由构图
## 保留可编辑场景，构建时使用官方 exportToSvg 输出矢量成品

```excalidraw
source: assets/editable-diagram.excalidraw
src: assets/editable-diagram.svg
title: Mermaid 与 Excalidraw 的统一交付流程
alt: Mermaid 和 Excalidraw 两种源格式汇入 SVG 规范化与质量门禁，最后交付到 Slide
min-font-size: 28
safe-margin: 24
```
