---
title: Diagram Design Harness
subtitle: Mermaid semantics with editorial SVG delivery
author: GolajahSlide
lang: zh-CN
density: speaking
sections: ["图表"]
---

<!-- slide
id: editorial-mermaid
type: content
layout: chart
section: 图表
footer: false
-->
# Mermaid 语义与视觉分工
## 语义源、编辑源与交付产物各自可追踪

```mermaid
@slide
renderer: diagram-design
source: assets/editorial-flow.diagram.html
src: assets/editorial-flow.svg
title: Mermaid 编辑式重绘链路
alt: Mermaid 语义源进入编辑式构图，再由构建器输出内联 SVG
detail: faithful
audience: mixed
min-font-size: 28
safe-margin: 40
@end
flowchart LR
    source[Mermaid 语义源] --> design[编辑式构图]
    design --> slide[内联 SVG Slide]
```
