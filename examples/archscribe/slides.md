---
title: Archscribe 动态中文流程图示例
subtitle: JSON 驱动、构建期生成、Slide 内动态播放
author: GolajahSlide
date: 2026-08
lang: zh-CN
density: speaking
sections: ["流程图"]
---

<!-- slide
id: archscribe-build-flow
type: content
layout: chart
section: 流程图
footer: false
-->
# 动态流程图必须服从 Slide 的字号与安全区
## 标题由 Slide 排版，Archscribe 专注呈现流程主体

```archscribe
spec: assets/slide-build-flow.spec.json
src: assets/slide-build-flow.gif
poster: assets/slide-build-flow.png
title: GolajahSlide 动态流程图
alt: 演示内容分别生成内置图表与动态流程图，检查失败时返回动态流程重新生成
crop: 50,160,1110,330
mask: 895,0,215,42
min-font-size: 28
safe-margin: 24
```
