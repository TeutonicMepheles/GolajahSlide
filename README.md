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
├── templates/
│   └── deck.html
├── docs/
│   ├── MARKDOWN-SPEC.md
│   └── LAYOUT-SPEC.md
├── examples/
│   └── basic/
│       ├── slides.md
│       ├── slides.layout.json
│       ├── index.html
│       ├── index.build.json
│       └── assets/
└── tests/
    └── test_build_slides.py
```

## 工作方式

1. 按照 [Markdown 内容规范](docs/MARKDOWN-SPEC.md) 编写页面。
2. 构建并在浏览器中打开 HTML。
3. 按 `E` 打开页面编辑器，调整布局、区域、正文排版与动画顺序。
4. 导出与 Markdown 同名的 `.layout.json` 文件。
5. 重新构建；构建器会自动读取同目录的覆盖文件。
6. 查看 `.build.json`，处理警告和错误。

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
- 页面级布局、坐标、正文样式和动画顺序覆盖
- 构建期内容密度检查与浏览器运行时溢出诊断

## 演示操作

- 下一页：`→`、`↓`、`PageDown`、空格或向左滑动
- 上一页：`←`、`↑`、`PageUp` 或向右滑动
- 首尾页：`Home` / `End`
- 页面编辑器：`E`
- 当前视觉全屏：`F`
- 当前视觉标注：`A`

访问 `index.html?debug=1` 可以标记运行时检测到的溢出区域；诊断结果也可通过 `window.__SLIDE_DIAGNOSTICS__` 读取。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

## 清晰规整的流程图

Mermaid 与 Excalidraw 都作为构建期源格式，统一导出、校验并以内联 SVG 写入 HTML。发布页面不加载图表渲染器；已有预生成 SVG 时仍可零依赖构建。完整协议和取舍见 [构建期 SVG 图表方案](docs/DIAGRAMS.md)，可运行内容见 [中文双引擎示例](examples/diagrams/slides.md)。

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

## License

[MIT](LICENSE)
