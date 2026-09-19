# 计划索引 / Plan Index

中文 · English

这里记录每项功能的目标、范围、验收结果与最近验证时间。开发状态使用 `Draft`、`Active`、`Implemented`、`Superseded` 或 `Cancelled`。

This index records each feature's goal, scope, acceptance evidence, and latest verification date. Status values are `Draft`, `Active`, `Implemented`, `Superseded`, and `Cancelled`.

| 计划 / Plan | 状态 / Status | 范围与结果 / Scope and outcome | 最近验证 / Last verified |
|---|---|---|---|
| [Markdown List Hierarchy](2026-09-19-list-hierarchy.md) | Implemented | 保留父子列表层级；4 处课件列表及 30 页完整交付验证通过。<br>Preserves nested list hierarchy with course and full-deck validation. | 2026-09-19 |
| [Lark Document Source](2026-09-17-lark-document-source.md) | Implemented | 从飞书文档链接构建现有 Slide HTML；真实 8 页回读、离线媒体及浏览器验证通过。<br>Builds Slide HTML from Feishu links with round-trip, offline-media, and browser validation. | 2026-09-17 |
| [Layout Editor – Option Contrast and Bounds](2026-09-17-layout-editor-bounds.md) | Implemented | 修复选项文字不可见和编辑范围与实际容器错位。<br>Fixes native option contrast and aligns edit bounds with actual containers. | 2026-09-17 |
| [Animated PowerPoint Export (Experimental)](2026-08-24-animated-pptx-export.md) | Implemented | 在默认静态 PPTX 之外，提供明确标注为实验性的原生 Fade 页间转场。<br>Adds an explicitly experimental native Fade transition while keeping static PPTX as the default. | 2026-08-24 |
| [Agent CLI and MCP Bridge](2026-08-24-agent-cli-mcp.md) | Implemented | Agent 可通过 JSON-first CLI 或 stdio MCP 安全盘点、检索、审校、编辑和构建文稿。<br>Safe inventory, search, audit, editing, and builds through a JSON-first CLI and stdio MCP server. | 2026-08-24 |
| [Static PDF and PowerPoint Export](2026-08-24-static-pdf-pptx-export.md) | Implemented | 在浏览器编辑器中一键导出 16:9 静态 PDF 与高保真 PowerPoint。<br>One-click 16:9 static PDF and high-fidelity PowerPoint export from the browser editor. | 2026-08-24 |
| [Content Authoring and Source Save](2026-08-24-content-authoring-and-source-save.md) | Implemented | 编辑文字、媒体与 Chapter，并在哈希校验后安全写回 Markdown、布局和资产；内容模式快捷键隔离回归通过，全量测试限制见计划。<br>Edit text, media, and Chapters with hash-guarded save-back; keyboard isolation verified, full-suite limitations recorded in plan. | 2026-09-19 |
| [Global Logo — Per-slide Visibility Exceptions](2026-08-22-global-logo-page-visibility.md) | Implemented | 保留统一 Logo 配置，同时允许指定页面单独隐藏。<br>Keeps one shared logo configuration while allowing selected pages to hide it. | 2026-08-24 |
| [Native Media Playback](2026-08-22-media-playback.md) | Implemented | 自包含本地视频、统一全屏，以及只在当前页面或 Gallery Tab 可见时播放。<br>Self-contained local video, consistent fullscreen, and visibility-aware playback for slides and Gallery tabs. | 2026-08-24 |
| [Slide Authoring Controls](2026-08-22-slide-authoring-controls.md) | Implemented | 支持纯图结构页、命名 Gallery Tab、自定义 Callout 标题和标题引用。<br>Adds pure-image structural pages, named Gallery tabs, custom callout titles, and heading citations. | 2026-08-24 |
| [Global Logo — Editor Upload and Global Visibility](2026-08-21-global-logo.md) | Implemented | 在编辑器中上传、开关和调整全局右上角品牌 Logo。<br>Upload, toggle, and resize a shared upper-right brand logo in the editor. | 2026-08-21 |
| [Footer Chapter Navigation](2026-08-14-footer-chapter-navigation.md) | Implemented | 页脚 Section 可展开 Chapter 列表并跳到对应内容起点。<br>Footer Sections open a Chapter list; unassigned covers stay outside navigation. | 2026-09-19 |
| [Content Typography and Divider](2026-08-21-plain-content-typography.md) | Implemented | 统一非标题文字层级，并为文本容器加入清晰分隔。<br>Establishes consistent non-heading typography and clear text-container dividers. | 2026-08-21 |
| [Presenter Focus – Configurable Global Shortcut](2026-08-21-presenter-focus-shortcut.md) | Implemented | 在编辑器中设置整份演示通用的聚焦快捷键。<br>Lets authors configure one deck-wide Presenter Focus shortcut. | 2026-08-21 |
| [Citations — Inline References and Source Tooltip](2026-08-21-citations.md) | Implemented | 将标准 Markdown 脚注变成可访问的编号角标和来源提示。<br>Turns standard Markdown footnotes into accessible numbered markers and source tooltips. | 2026-08-21 |
| [Diagram Design – Editorial Mermaid Pipeline](2026-08-12-diagram-design-mermaid.md) | Implemented | 保留 Mermaid 语义源，并以可审阅的编辑式 HTML/SVG 提升演示视觉。<br>Preserves Mermaid semantics while adding reviewable editorial HTML/SVG for presentation-quality visuals. | 2026-08-14 |
| [Presenter Focus – Pointer Cue and Theme Depth](2026-08-12-presenter-focus-pointer-theme.md) | Implemented | 使用主题色鼠标提示与分层文字强调辅助现场讲解。<br>Adds theme-aware pointer cues and layered text emphasis for live explanation. | 2026-08-12 |
| [Modular Foundation — Stable First Slice](2026-08-12-modular-foundation.md) | Implemented | 在 Python-only、单 HTML 交付前提下建立浏览器功能的独立边界与验证闭环。<br>Establishes modular browser-feature boundaries and validation while preserving Python-only, single-HTML delivery. | 2026-08-12 |

## 如何阅读 / How to read a plan

- 设计师可先看 Goal、Non-goals 和 Acceptance gates，快速判断功能能做什么、不能做什么。
- 开发者可继续查看 Ownership、Validation 和已记录的浏览器测试证据。
- `Implemented` 表示计划中的验收门槛已通过，不代表未来不会继续优化。

- Designers can start with Goal, Non-goals, and Acceptance gates to understand the promise and limits.
- Developers can continue with Ownership, Validation, and recorded browser evidence.
- `Implemented` means the plan's acceptance gates passed; it does not mean the feature will never evolve.
