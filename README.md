# GolajahSlide

一个零第三方依赖的 Markdown → HTML Slides 构建器。它将结构化 Markdown 编译为固定 1920×1080 的单文件演示页面，并提供自动布局、演示控制、页面编辑器、布局覆盖和构建诊断。

## 快速开始

需要 Python 3.10 或更高版本，不需要安装 npm 或 Python 包。

```bash
python3 build_slides.py
```

默认读取 `examples/basic/slides.md`，生成：

- `examples/basic/index.html`
- `examples/basic/index.build.json`

也可以构建自己的演示：

```bash
python3 build_slides.py path/to/slides.md -o path/to/index.html
```

正式交付前使用严格模式：

```bash
python3 build_slides.py path/to/slides.md -o path/to/index.html --strict
```

## 仓库结构

```text
.
├── build_slides.py
├── golajah_slide_agent.py      # JSON-first Agent CLI 与 stdio MCP 入口
├── src/
│   └── web/
│       └── features/       # 浏览器 Feature 的行为、样式和契约
├── templates/
│   └── deck.html           # 最终 HTML 的组合壳
├── docs/
│   ├── ARCHITECTURE.md
│   ├── AGENT-TOOLS.md
│   ├── plans/
│   ├── MARKDOWN-SPEC.md
│   └── LAYOUT-SPEC.md
├── harnesses/              # 每个交互 Feature 的最小可运行场景
├── examples/
│   └── basic/
│       ├── slides.md
│       ├── slides.layout.json
│       ├── index.html
│       ├── index.build.json
│       └── assets/
└── tests/                   # Python 契约/集成测试与真实浏览器测试
```

工程边界、依赖方向和 Feature 完成条件见[架构说明](docs/ARCHITECTURE.md)；实施中的功能及状态见 [Plan 索引](docs/plans/README.md)。

## 工作方式

1. 按照 [Markdown 内容规范](docs/MARKDOWN-SPEC.md) 编写页面。
2. 构建并在浏览器中打开 HTML。
3. 按 `E` 打开页面编辑器，编辑文本/Callout/图片与 Chapter 归属，或调整布局、区域、正文排版与动画顺序。
4. 点击“保存改动”安全写回 Markdown、同名 `.layout.json` 与新增资产；也可仅导出布局覆盖。
5. 重新构建；构建器会自动读取同目录的覆盖文件。
6. 查看 `.build.json`，处理警告和错误。

编辑器打开时优先选中当前页的图片或文字区域；内容和布局是高频分组并默认展开，样式、全局和文件操作默认折叠。整体内容区域的移动与缩放保留为显式的低频选项。

`slides.layout.json` 只描述一份演示文稿的页面覆盖，不是全局主题配置。布局文件的完整结构见 [布局覆盖规范](docs/LAYOUT-SPEC.md)。

## 已支持的内容

- 封面页、章节页和内容页
- 标题、副标题、段落、列表和内容卡片
- GFM 表格、callout 和代码块
- PNG、JPEG、GIF、WebP、SVG 与远程图片
- `bar`、`line`、`donut` 单序列轻量图表
- 可选 Archscribe 动态流程图（GIF 动画、PNG 减少动态效果降级、Excalidraw 可编辑源文件）
- 自动选择文字、左右图文、大图、画廊、表格和图表布局
- 图片缩放、拖拽、全屏和临时标注
- 独立视频、Gallery Tab 和 Gallery 并列视频的统一全屏播放入口
- 页面级布局、坐标、正文样式和动画顺序覆盖
- 编辑模式新增/排序/跨页移动文本块与 Callout，上传/拖放/粘贴图片，并切换多图并列或 Gallery
- 编辑模式调整当前页 Chapter item，保存后安全写回 Markdown、布局 sidecar 与新增资产
- 默认无动效的 PDF 与 PowerPoint 静态导出；Gallery 隐藏 Tab 展开为附加页，PPTX 每页为保真的全画幅静态图
- 构建期内容密度检查与浏览器运行时溢出诊断
- 页脚 Section 子章节导航（悬浮向上展开，点击跳转到子章节首个 Page）

## 演示操作

- 下一页：`→`、`↓`、`PageDown`、空格或向左滑动
- 上一页：`←`、`↑`、`PageUp` 或向右滑动
- 首尾页：`Home` / `End`
- 页面编辑器：`E`
- 当前视觉全屏：`F`
- 视频全屏：使用视频右上角的“全屏播放”按钮；换页、切换 Gallery Tab 或进入编辑模式会安全退出
- 当前视觉标注：`A`
- 悬浮聚焦开关：`H`（默认开启；Slide 内显示主题色鼠标圆圈，容器使用浅色聚焦，再悬停段落或列表项时使用更深的主题色强调）
- 页脚章节导航：悬浮或聚焦 Section，使用 `↑` / `↓` 浏览子章节，`Enter` 跳转，`Escape` 关闭
- 静态导出：页面编辑器的“高级 · 文件”中选择 PDF 或 PowerPoint

访问 `index.html?debug=1` 可以标记运行时检测到的溢出区域；诊断结果也可通过 `window.__SLIDE_DIAGNOSTICS__` 读取。

悬浮聚焦的技术选型、交互边界与浏览器降级策略见 [演示者悬浮聚焦方案](docs/PRESENTER-FOCUS.md)。

## 测试

完整开发验证（Python + 浏览器 Harness）：

```bash
npm test
```

也可以分别运行：

```bash
python3 -m unittest discover -s tests -v
npm run test:presenter-focus
npm run test:media-playback
npm run test:content-authoring
npm run test:static-export
```

## 清晰规整的流程图

Mermaid、Diagram Design HTML 与 Excalidraw 都作为构建期源格式，统一导出、校验并以内联 SVG 写入 HTML。发布页面不加载图表渲染器；已有预生成 SVG 时仍可零依赖构建。默认 Mermaid CLI 适合自动布局；在围栏里声明 `renderer: diagram-design`，可保留 Mermaid 语义源，同时使用仓库级 `$golajah-diagram-design` Skill 做面向 Slide 的编辑式重绘。完整协议见 [构建期 SVG 图表方案](docs/DIAGRAMS.md)，可运行内容见 [中文图表示例](examples/diagrams/slides.md)。

安装锁定的构建工具并重新生成 SVG：

```bash
npm install
python3 build_slides.py examples/diagrams/slides.md -o examples/diagrams/index.html --render-diagrams --strict
```

普通构建只读取已提交的 SVG 与质量报告：

```bash
python3 build_slides.py examples/diagrams/slides.md -o examples/diagrams/index.html --strict
```

Archscribe 保留为特殊动画能力，不再作为默认流程图渲染器；见 [Archscribe 动态流程图接入方案](docs/ARCHSCRIBE-INTEGRATION.md)和[动画中文示例](examples/archscribe/slides.md)。

```bash
python3 build_slides.py examples/archscribe/slides.md -o examples/archscribe/index.html
```

## 与 AI 协作

向 AI 提供观众、沟通目标、核心结论、已知证据、素材路径、页数和使用场景，再要求它先规划每页的沟通任务，确认后生成 Markdown。可直接复用的提示词见 [Markdown 内容规范：与 AI 协作](docs/MARKDOWN-SPEC.md#14-与-ai-协作编写-slide)。

需要让 Hermes 等 Agent 直接盘点、检索、生成质量报告或安全修改演示稿时，使用 JSON-first Agent CLI；同一入口也可作为本地 stdio MCP server：

```bash
python3 golajah_slide_agent.py inspect examples/basic/slides.md
python3 golajah_slide_agent.py audit examples/basic/slides.md
python3 golajah_slide_agent.py mcp --root /absolute/path/to/deck-directory
```

内容写入默认只返回 diff；实际保存必须提供刚读取到的源文件 SHA-256，存在布局 sidecar 时还需提供其 SHA-256。完整命令、operation schema、Hermes 配置和安全边界见 [Agent CLI and MCP](docs/AGENT-TOOLS.md)。

## License

[MIT](LICENSE)
