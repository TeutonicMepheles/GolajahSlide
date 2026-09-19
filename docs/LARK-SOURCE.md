# 从飞书文档构建课件

飞书作为内容源；构建时调用已登录的 `lark-cli`，将文档转换为现有 Markdown
方言，再使用原有布局、模板和浏览器功能。浏览器不连接飞书。
本地 `.md` 构建仍只需要 Python 标准库，不要求安装飞书 CLI。

## 已创建的示例

- [GolajahSlide · 飞书文档构建示例](https://www.feishu.cn/docx/HUzTdcJX8oB33jxRXLZcpKfun1f)
- 源内容来自 `examples/basic/slides.md`，共 8 页。
- `examples/lark/authoring.md` 是创建时使用的飞书格式文本。
- `examples/lark/index.html` 是实际从该文档回读构建的离线课件。
- 图片为原示例 SVG 的 PNG 渲染版，因为飞书图片块不支持 SVG 上传。
- 文档以用户身份创建在个人空间；没有创建分享权限或公开链接权限。

## 使用

安装并登录 `lark-cli` 后，在项目目录运行：

```bash
python build_slides.py --lark "https://www.feishu.cn/docx/HUzTdcJX8oB33jxRXLZcpKfun1f" -o examples/lark/index.html --strict
```

也可以直接传入链接：

```bash
python build_slides.py "https://your-team.feishu.cn/docx/DOCUMENT_TOKEN" -o work/my-deck/index.html
```

支持 `/docx/` 和 `/wiki/` 链接；Wiki 会先解析真实对象，拒绝表格等非 docx 节点。
裸文档 token 使用 `--lark DOCUMENT_TOKEN`。默认 `--lark-as user`，只有明确需要
应用身份且应用可访问文档时才使用 `--lark-as bot`。可用 `--lark-cli` 指定可执行文件。
未指定输出路径时，飞书构建输出到 `work/lark/index.html`。

如果登录过期，按 CLI 报错重新授权。读取通常需要
`docx:document:readonly docs:document.media:download`，Wiki 还需要 `wiki:node:read`。
构建器不会自动发起登录，也不会把访问凭证写入输出。

**在飞书修改内容后，重新运行构建命令即可更新 HTML。当前没有自动监听或双向同步。**

## 在飞书中如何组织页面

| 飞书内容 | Slide 解释 |
|---|---|
| 分割线 | 分页；若全文没有分割线，则每个一级标题开始新页 |
| 一级标题 | 页面标题 |
| 二级标题 | 页面副标题 |
| 三级标题 | 新的文字卡片 |
| 正文、列表、粗体、行内代码、链接 | 使用现有 Markdown 渲染规则 |
| 文字背景高亮 | 转成 Slide 的 `==高亮==` |
| 简单表格 | 转成 Markdown 表格，首行作为表头 |
| 提示块 / 引用中的 `[!TIP]` 等 | 提示卡片 |
| 图片 | 下载原图片，按尺寸选布局，并嵌入最终 HTML |
| 画板 | 下载静态预览图片，不保留画板编辑能力 |
| 普通代码块 | 代码卡片 |

没有一级标题的简单文档会用文档名称作为第一页标题。显式分割后的每页仍需要一级标题。
页面仍受原有字数、图表布局和投影可读性检查约束。

## 页面配置：使用 YAML 代码块

飞书不保证保留 HTML 注释，因此把原来的 frontmatter 和 `<!-- slide -->`
写成原生代码块。它们在飞书可见、可编辑，导入时会变成配置，不显示为课件内容。

文档顶部的 YAML 代码块：

````markdown
```yaml
golajahslide: deck
title: 我的课件
author: 作者
density: reading
sections: ["开始", "内容", "总结"]
```
````

每页标题前的 YAML 代码块（建议明确放在上一条分割线之后）：

````markdown
```yaml
golajahslide: slide
id: introduction
type: content
layout: auto
section: 内容
```
````

`id` 保持稳定，可继续使用现有 `--overrides path/to/layout.json` 布局覆盖。
也会自动查找导入快照旁的 `slides.layout.json`，重新获取文档不会覆盖该文件。

轻量图表用普通文本代码块，并在第一行写标记：

````markdown
```text
golajahslide: chart
type: bar
title: 各阶段投入
labels: 调研 | 设计 | 开发 | 验证
values: 22 | 31 | 28 | 19
unit: %
```
````

标记独立于代码块语言名称，飞书将 `text` 改名为 `plaintext` 不影响导入。

## 输出与离线能力

`-o output/index.html` 会生成：

```text
output/
  index.html                 # 图片、CSS、JS 已嵌入，可单独离线打开
  index.build.json           # 原构建报告 + sourceImport 来源信息
  index.lark/
    source.json              # 文档 ID、来源链接、标题、媒体数量
    source.lark.md           # CLI 回读原文，方便核查
    slides.md                # 转换后的现有 Slide 方言
    assets/                  # 下载的图片 / 画板预览
```

每次构建会重新获取文档和媒体；分页文本按游标无缝拼接，避免代码块被截断破坏。
`index.lark/` 是可检查的快照，同时包含实际文档内容；按源文档的访问要求保管。
普通本地 Markdown 构建的图片引用行为不变。

## 当前边界

- 不是完整飞书排版复制：分栏、附件、电子表格、嵌入页面、合并单元格、复杂表格
  单元格等会明确报错；请先改写为简单文字、表格或图片。
- 按导出缩进保留有序/无序列表嵌套；任意富文本样式仍不保证与飞书完全相同。
- CLI 当前回读示例图片时未返回 caption / alt，因此这两张图片使用通用“图片”标签。
  返回值有 caption / alt 的图片会保留；重要图片说明建议写成普通正文。
- Mermaid / Excalidraw / Archscribe 不是飞书画板的自动转换目标，仍需原来的构建资源流程。
- 构建时需网络、文档访问权限和 CLI 登录；生成后的示例 HTML 已验证无需网络。

## 验证

`npm test` 包含导入单元测试和浏览器测试。测试从仓库里的真实回读快照构建，
不连接飞书、不创建文档、不依赖登录。`npm run test:lark` 单独检查 8 页、两个窗口宽度、
图片加载、表格、图表、高亮、提示块、运行时错误和网络请求。
截图和浏览器结果存于 `work/lark-browser/`。
