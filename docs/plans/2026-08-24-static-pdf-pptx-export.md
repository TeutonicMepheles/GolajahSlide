# Static PDF and PowerPoint Export

- Plan ID: `20260824-static-pdf-pptx-export`
- Status: `Implemented`
- Created: `2026-08-24`
- Last updated: `2026-08-24`

## Goal

在编辑模式中提供一键 PDF 与 PowerPoint (`.pptx`) 导出。默认直接输出所有内容均已显示、无转场与无逐项动画的静态版本，并保持 GolajahSlide 的 Python-only 构建、单 HTML 交付和浏览器离线运行合同。

## Scope

- 在“文件与高级操作”中提供“导出 PDF”和“导出 PowerPoint”按钮。
- 使用浏览器内静态页面快照生成 16:9 PDF；点击后直接下载文件，不依赖系统打印对话框。
- 生成标准 OOXML `.pptx`，每页使用一张全画幅静态图以保持 HTML 版式一致。
- 导出时显示全部 reveal 内容，移除编辑器、查看器控件、焦点效果和动画状态。
- 视频使用 poster 或当前可用静态帧；动画图片优先使用 poster 或 ImageDecoder 首帧，旧浏览器回退到导出时的静态帧。
- 构建期为本地 PNG、JPEG、WebP、GIF 与 SVG 生成内容哈希去重的导出素材清单，避免 `file://` 图片污染 Canvas。
- Tab Gallery 的每个选项展开为连续导出页，避免静态文件静默遗漏隐藏图片。
- 导出过程提供忙碌、逐页进度、成功与错误状态，并防止重复并行导出。
- 增加独立 Feature、Harness、构建契约测试和真实浏览器下载测试。

## Non-goals

- 首版不把 HTML 中的文字、图形和图片拆解为可逐项编辑的 PowerPoint 对象。
- 不转换 CSS 动画、页面转场、视频或 GIF 动效为 PowerPoint 动画或媒体对象。
- 不依赖在线服务、浏览器扩展、运行时 npm 包或外部 CDN。
- 不修改 Markdown 内容、布局 sidecar 或本地内容编辑草稿。

## Ownership and boundaries

- `src/web/features/static-export/` 负责快照清理、媒体冻结、PDF 编码、OOXML/ZIP 打包、下载和进度状态。
- `templates/deck.html` 只提供 Feature 样式/运行时组合点、编辑器挂载点和实例构造。
- `build_slides.py` 内联 Feature 源文件并生成本地静态导出素材清单，继续保持标准库构建。
- Static Export 通过构造参数接收 Slide 列表与现有查看器清理回调；不读取 Python 内部模型，也不修改其他 Feature 状态。

## Acceptance gates

- [x] PDF 与 PPTX 按钮位于低频“文件与高级操作”分组，默认说明明确标注“无动效”。
- [x] 点击任一按钮可直接下载以演示文稿标题命名的文件，无需网络或额外运行时依赖。
- [x] 每个导出文件包含全部页面，尺寸为 16:9，所有 reveal 内容可见且不存在编辑器/聚焦/动画覆盖层。
- [x] 视频与动画图片不会继续播放；PPTX 不包含 timing/transition 动画节点。
- [x] PDF 可由标准 PDF 工具解析并逐页渲染；PPTX ZIP、关系和 XML 完整，可由 Office 兼容渲染器打开并渲染。
- [x] Focused Harness、浏览器下载/格式回归、窄屏编辑器和严格构建通过。
- [x] 官方示例由当前源码重建，`npm test` 与 `git diff --check` 通过。

## Validation evidence

- `npm test`：112 个 Python 单元测试与 8 组浏览器回归全部通过；覆盖普通链接/正文不会触发本地素材嵌入、逐页内存预算、真实 Blob 下载、4 页 Gallery 展开、1920×1080 JPEG、PDF xref/page tree、合法 OOXML Layout ID、PPTX ZIP/关系/XML、无 timing/transition、无视频媒体、导出前后演示状态不变，以及 375×800 编辑器。
- `python3 build_slides.py harnesses/static-export/slides.md ... --strict`：3 个源页面严格构建通过，静态计划生成 4 个输出页面。
- `pdfinfo` 与 `pdftoppm`：PDF 1.4、4 页、每页 960×540 pt，可逐页渲染；4 页渲染图均完成视觉检查，无裁切、空白素材或覆盖层。
- `unzip -t`、PowerPoint 渲染脚本与 Slide 越界检查：PPTX 全部 ZIP part/CRC 通过，可渲染为 4 页且无越界；4 页渲染图均完成视觉检查。
- 在一份未纳入仓库的真实长稿上完成交付级验收：114 个源 Slide 因 Gallery Tab 展开为 116 个静态页；PDF 为 116 页 960×540 pt，PPTX 为 116 页 12192000×6858000 EMU。
- 长稿 PDF 可全页渲染；PPTX 的 ZIP/XML/关系完整，不含 `timing`、`transition` 或外部引用。全页联络表、代表页细查、overflow 检查与 PDF/PPTX 栅格一致性均通过，导出前后源码 SHA-256 不变。
- 真实编辑器交互：375×800 下展开“文件与高级操作”，分别点击 PDF 与 PowerPoint 后均显示“4 页无动效静态画面”，浏览器无 warning/error。
- `examples/basic`、`examples/diagrams` 与 `examples/archscribe` 已从当前源码严格重建；`git diff --check` 通过。
