# GolajahSlide

[中文](#中文) · [English](#english)

把 Markdown 做成可编辑、可演示、可交付的 16:9 单文件 HTML 幻灯片。

Turn Markdown into an editable, presentation-ready, self-contained 16:9 HTML deck.

---

## 中文

### 适合谁

GolajahSlide 面向希望专注内容与视觉的设计师、讲师和内容创作者。你用 Markdown 整理结构，用浏览器调整版式，最终只需交付一个 HTML 文件。

- 固定 1920×1080 画布，适合投影和录屏
- 自动安排文字、图片、视频、Gallery、表格和图表
- 在浏览器中编辑内容、版式、品牌 Logo 和 Chapter
- 导出单文件 HTML、静态 PDF 或 PowerPoint
- 可用 CLI 或 MCP 让 AI Agent 安全检查和修改文稿
- 演示现场不依赖网络、在线字体或 JavaScript 框架

### 安装

#### 基础安装：只做普通幻灯片

需要：

- macOS、Windows 或 Linux
- Python 3.10 或更高版本
- Chrome、Edge 或 Safari 等现代浏览器

下载项目后进入目录，不需要安装 Python 包：

```bash
git clone https://github.com/TeutonicMepheles/GolajahSlide.git
cd GolajahSlide
python3 build_slides.py
```

默认会把 `examples/basic/slides.md` 生成成：

- `examples/basic/index.html`：可直接打开和交付的演示稿
- `examples/basic/index.build.json`：构建检查报告

构建自己的文稿：

```bash
python3 build_slides.py path/to/slides.md -o path/to/index.html --strict
```

`--strict` 会把设计警告也视为失败，建议在正式交付前使用。

#### 可选安装：从飞书文档构建

安装并登录 `lark-cli` 后，可以直接读取飞书文档或 Wiki 文档链接：

```bash
python build_slides.py --lark "https://www.feishu.cn/docx/HUzTdcJX8oB33jxRXLZcpKfun1f" -o examples/lark/index.html --strict
```

这份[飞书示例文档](https://www.feishu.cn/docx/HUzTdcJX8oB33jxRXLZcpKfun1f)来自基础示例的 8 页内容。
编辑后重新运行即可更新课件；导入图片会嵌入 HTML。完整规则、配置方式和支持边界见
[飞书内容源说明](docs/LARK-SOURCE.md)。本地 Markdown 构建无需飞书 CLI。

#### 可选安装：重新生成 Mermaid / Excalidraw 图表

只有在图表源码发生变化时，才需要 Node.js 20+ 和项目锁定的 Mermaid CLI 等工具：

```bash
npm install
python3 build_slides.py path/to/slides.md -o path/to/index.html --render-diagrams --strict
```

平时构建会直接使用已经生成的 SVG，不需要 Node.js。

### 推荐搭配

| 工具 | 推荐用途 | 是否必需 |
|---|---|---:|
| [Obsidian](https://obsidian.md/) | 管理 Markdown、图片、视频和资料；适合用文件夹组织一套演示稿 | 否 |
| [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) | 从 Mermaid 文本生成规整流程图；已由 `npm install` 按项目版本安装 | 仅重新生成图表时 |
| Chrome / Edge | 预览、编辑、全屏演示和导出 | 建议 |
| Codex / Hermes 等 AI Agent | 盘点内容、查找页面、审校和生成可审阅的修改 | 否 |
| Git | 保存版本、审阅差异和协作 | 建议 |

Obsidian 很适合管理源文件，但图片请使用标准 Markdown 写法：

```markdown
![界面操作示意](assets/demo.png "可选图注")
```

不要使用 Obsidian 专有的 `![[demo.png]]` 嵌入语法；GolajahSlide 需要明确、可移植的相对路径。

### 设计师工作流

1. 复制 `examples/basic/`，把 `slides.md` 和 `assets/` 放在同一项目文件夹中。
2. 按 [Markdown 内容规范](docs/MARKDOWN-SPEC.md) 编写页面；通常让 `layout: auto` 自动排版。
3. 运行严格构建，打开生成的 `index.html`。
4. 按 `E` 打开编辑器，调整文字、图片、Callout、Chapter、布局和样式。
5. 点击“保存改动”写回 Markdown、布局文件和新增资产，然后重新构建。
6. 检查 `.build.json`，并在电脑和手机尺寸下浏览重点页面。
7. 交付单个 HTML；如需要评审稿，再从编辑器导出 PDF 或 PowerPoint。

编辑器保存前会校验源文件，避免覆盖在别处已经修改过的 Markdown。保存后必须重新构建，新的 HTML 和检查报告才会更新。

### 常用 CLI

```bash
# 查看全部参数
python3 build_slides.py --help

# 构建默认示例
python3 build_slides.py

# 构建指定文稿
python3 build_slides.py slides.md -o index.html

# 正式交付检查
python3 build_slides.py slides.md -o index.html --strict

# 图表源码变化后重新生成 SVG
python3 build_slides.py slides.md -o index.html --render-diagrams --strict
```

图表详细写法见 [DIAGRAMS.md](docs/DIAGRAMS.md)，布局覆盖见 [LAYOUT-SPEC.md](docs/LAYOUT-SPEC.md)。

### Agent CLI 与 MCP

`golajah_slide_agent.py` 为 Codex、Hermes 或其他 Agent 提供结构化工具。它适合在不把整份长文稿放进对话的情况下查找、审校和修改页面。

常用 CLI：

```bash
# 盘点标题、页面、Section、稳定 ID 和文件哈希
python3 golajah_slide_agent.py inspect examples/basic/slides.md

# 检查内容与构建问题，不改文件
python3 golajah_slide_agent.py audit examples/basic/slides.md

# 查找相关页面
python3 golajah_slide_agent.py search examples/basic/slides.md --query "设计原则"

# 查看 Agent CLI 帮助
python3 golajah_slide_agent.py --help
```

启动本地 stdio MCP Server：

```bash
python3 golajah_slide_agent.py mcp --root /absolute/path/to/deck-directory
```

常见 MCP Host 配置：

```json
{
  "mcpServers": {
    "golajah_slide": {
      "command": "/absolute/path/to/python3",
      "args": [
        "/absolute/path/to/GolajahSlide/golajah_slide_agent.py",
        "mcp",
        "--root",
        "/absolute/path/to/deck-directory"
      ]
    }
  }
}
```

建议先只开放 inspect、search、get 和 audit 等只读工具。编辑默认返回 diff；真正写入时需要最新的源文件 SHA-256，避免覆盖他人的改动。完整命令和 Hermes 配置见 [Agent CLI and MCP](docs/AGENT-TOOLS.md)。

### 演示与导出

- 下一页：`→`、`↓`、`PageDown`、空格或向左滑动
- 上一页：`←`、`↑`、`PageUp` 或向右滑动
- 首尾页：`Home` / `End`
- 页面编辑器：`E`
- 当前视觉全屏：`F`
- 当前视觉标注：`A`
- 悬浮聚焦：`H`，默认关闭，可在编辑器中改快捷键
- Chapter 导航：悬浮或聚焦页脚 Section
- PDF / PowerPoint：在编辑器“高级 · 文件”中导出

PDF 和默认 PowerPoint 是高保真的静态页面。实验性 PowerPoint 只增加页面间 Fade 转场；两种 PPTX 都不会把 HTML 内容转换成可解组编辑的对象，也不会保留视频或逐对象动画。

### 项目导航

- [Markdown 内容规范](docs/MARKDOWN-SPEC.md)
- [图表与 Mermaid](docs/DIAGRAMS.md)
- [布局覆盖规范](docs/LAYOUT-SPEC.md)
- [Agent CLI 与 MCP](docs/AGENT-TOOLS.md)
- [项目架构](docs/ARCHITECTURE.md)
- [功能计划索引](docs/plans/README.md)
- [基础示例](examples/basic/slides.md)
- [图表示例](examples/diagrams/slides.md)

### 开发与验证

普通用户不需要 npm。只有开发项目、重新生成图表或运行完整测试时才需要：

```bash
npm install
npm test
```

---

## English

### Who it is for

GolajahSlide is for designers, educators, and content creators who want to focus on story and visuals. Structure the deck in Markdown, refine it in the browser, and deliver one HTML file.

- Fixed 1920×1080 stage for projection and recording
- Automatic layouts for text, images, video, galleries, tables, and diagrams
- Browser editing for content, layout, branding, and chapters
- Self-contained HTML plus static PDF and PowerPoint export
- CLI and MCP tools for safe AI-assisted review and editing
- No network, web-font, or framework dependency during a presentation

### Installation

#### Basic setup: regular decks

Requirements:

- macOS, Windows, or Linux
- Python 3.10+
- A modern browser such as Chrome, Edge, or Safari

No Python package installation is required:

```bash
git clone https://github.com/TeutonicMepheles/GolajahSlide.git
cd GolajahSlide
python3 build_slides.py
```

The default command turns `examples/basic/slides.md` into:

- `examples/basic/index.html`: the presentation and delivery file
- `examples/basic/index.build.json`: the build report

Build your own deck:

```bash
python3 build_slides.py path/to/slides.md -o path/to/index.html --strict
```

`--strict` treats design warnings as failures and is recommended before delivery.

#### Optional setup: regenerate Mermaid / Excalidraw diagrams

Node.js 20+ and the pinned Mermaid CLI toolchain are needed only when diagram sources change:

```bash
npm install
python3 build_slides.py path/to/slides.md -o path/to/index.html --render-diagrams --strict
```

Regular builds reuse generated SVG files and do not need Node.js.

### Recommended tools

| Tool | Best for | Required |
|---|---|---:|
| [Obsidian](https://obsidian.md/) | Organizing Markdown, media, and research in one deck folder | No |
| [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) | Turning Mermaid text into clean flow diagrams; installed at the pinned version by `npm install` | Only for diagram rendering |
| Chrome / Edge | Previewing, editing, presenting, and exporting | Recommended |
| Codex / Hermes or another AI Agent | Inventory, search, review, and reviewable deck edits | No |
| Git | Version history, diff review, and collaboration | Recommended |

Obsidian works well as the source editor, but use portable Markdown image syntax:

```markdown
![Interface walkthrough](assets/demo.png "Optional caption")
```

Avoid Obsidian-only `![[demo.png]]` embeds. GolajahSlide expects explicit, portable relative paths.

### Designer workflow

1. Copy `examples/basic/`; keep `slides.md` and `assets/` in one project folder.
2. Follow the [Markdown guide](docs/MARKDOWN-SPEC.md). Keep `layout: auto` unless the story needs a specific composition.
3. Run a strict build and open `index.html`.
4. Press `E` to edit text, images, callouts, chapters, layout, and styles.
5. Use “Save changes,” then rebuild to refresh the HTML and report.
6. Review `.build.json` and check important pages at desktop and mobile sizes.
7. Deliver the single HTML file; export PDF or PowerPoint when a review format is needed.

The editor checks source hashes before saving, so it will not silently overwrite Markdown changed elsewhere.

### Common CLI commands

```bash
python3 build_slides.py --help
python3 build_slides.py
python3 build_slides.py slides.md -o index.html
python3 build_slides.py slides.md -o index.html --strict
python3 build_slides.py slides.md -o index.html --render-diagrams --strict
```

See [DIAGRAMS.md](docs/DIAGRAMS.md) for diagram authoring and [LAYOUT-SPEC.md](docs/LAYOUT-SPEC.md) for layout overrides.

### Agent CLI and MCP

`golajah_slide_agent.py` gives Codex, Hermes, and other agents a structured way to inspect, search, audit, and edit a deck without loading the full Markdown into one conversation.

```bash
python3 golajah_slide_agent.py inspect examples/basic/slides.md
python3 golajah_slide_agent.py audit examples/basic/slides.md
python3 golajah_slide_agent.py search examples/basic/slides.md --query "design principles"
python3 golajah_slide_agent.py --help
```

Start the local stdio MCP server:

```bash
python3 golajah_slide_agent.py mcp --root /absolute/path/to/deck-directory
```

Typical MCP host configuration:

```json
{
  "mcpServers": {
    "golajah_slide": {
      "command": "/absolute/path/to/python3",
      "args": [
        "/absolute/path/to/GolajahSlide/golajah_slide_agent.py",
        "mcp",
        "--root",
        "/absolute/path/to/deck-directory"
      ]
    }
  }
}
```

Start with read-only inspect, search, get, and audit tools. Edits are dry-run diffs by default; a real write requires the latest source SHA-256 to prevent accidental overwrite. See [Agent CLI and MCP](docs/AGENT-TOOLS.md) for the full command set and Hermes setup.

### Presenting and export

- Next: `→`, `↓`, `PageDown`, Space, or swipe left
- Previous: `←`, `↑`, `PageUp`, or swipe right
- First / last: `Home` / `End`
- Editor: `E`
- Current visual fullscreen: `F`
- Annotation: `A`
- Presenter focus: `H`; off by default and configurable in the editor
- Chapter navigation: hover or focus a footer Section
- PDF / PowerPoint: Editor → Advanced → File

PDF and the default PowerPoint export are high-fidelity static pages. Experimental PowerPoint adds page-level Fade transitions only. PPTX output remains flattened and does not preserve video or object animation.

### Project guide

- [Markdown authoring](docs/MARKDOWN-SPEC.md)
- [Diagrams and Mermaid](docs/DIAGRAMS.md)
- [Layout overrides](docs/LAYOUT-SPEC.md)
- [Agent CLI and MCP](docs/AGENT-TOOLS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Feature plan index](docs/plans/README.md)
- [Basic example](examples/basic/slides.md)
- [Diagram example](examples/diagrams/slides.md)

### Development and validation

Regular users do not need npm. Install it only for project development, diagram regeneration, or the full test suite:

```bash
npm install
npm test
```

## License

[MIT](LICENSE)
