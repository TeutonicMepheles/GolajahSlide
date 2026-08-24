# Content Authoring and Source Save

- Plan ID: `20260824-content-authoring-source-save`
- Status: `Implemented`
- Created: `2026-08-24`
- Last updated: `2026-08-24`

## Goal

把现有页面布局编辑器扩展为可重建的结构化内容编辑器：在浏览器中新增、编辑、排序和跨页移动文本块、Callout 与图片，并把改动安全写回 Markdown、布局覆盖和新增资产。

## Scope

- 用稳定的 Slide / 内容项 / 字段 ID 替代全稿 DOM 数字序号，消除同路径重建后的文字串位。
- 编辑模式可新增默认包含标题与一段正文的文本块。
- 文本块与 Callout 可在当前页通过拖拽重新排序。
- 支持上传、拖入或粘贴 PNG、JPEG、WebP，以替换占位图、替换现有图片或向当前页追加图片。
- 两张及以上图片可在编辑器中选择 Tab Gallery 或并列展示。
- 选中的图片、文本块或 Callout 可移动到上一页或下一页，并同步重算两页布局。
- “保存改动”优先通过浏览器文件系统授权写回 `slides.md`、同名 `.layout.json` 与新增资产；不可用时下载可重建文件并明确提示。
- 下载当前 HTML 继续生成单文件、自包含交付物。

## Non-goals

- 首版不移动页面标题、副标题、页脚、表格、代码块、Mermaid、Excalidraw 或 Archscribe 图表。
- 不在浏览器中实现完整 Markdown IDE 或任意富文本 HTML 编辑。
- 不静默覆盖磁盘上已在构建后发生变化的 Markdown。
- 不引入浏览器网络服务、框架或运行时包依赖。

## Ownership

- `build_slides.py`: 生成结构化 authoring model、稳定字段 ID、源码指纹与内容项标记。
- `src/web/features/content-authoring/`: 内容选择、文本编辑、媒体导入、排序、跨页移动、持久化、源码序列化和文件保存。
- `templates/deck.html`: Feature 挂载点、现有 Layout Editor 的公共桥接与构造调用。
- `harnesses/content-authoring/`: 文本、Callout、占位图、单图与双图的独立场景。
- `tests/test_content_authoring.mjs`: 浏览器交互、源码往返和缓存完整性回归。

## Acceptance gates

- [x] 同一路径重建前部新增图注后，旧文字缓存不会覆盖错误标题或正文。
- [x] 新增文本块默认包含可编辑标题和正文，并能写回标准 Markdown。
- [x] 文本块与 Callout 可拖拽换序，刷新和源码序列化后顺序一致。
- [x] 双图可以在并列与 Tab Gallery 间切换，并更新页面指令。
- [x] 图片、文本块和 Callout 可以移到相邻页，两页媒体数、内容块数和布局同步更新。
- [x] 上传、拖入和粘贴图片支持替换与追加；非法类型和超限文件被拒绝。
- [x] 保存时校验源码指纹；匹配时写回 Markdown、布局 JSON 和资产，不匹配时拒绝覆盖。
- [x] 不支持文件系统写入时，可以下载包含 Markdown、布局、操作日志和资产的完整可恢复编辑包。
- [x] Focused Harness 严格构建，Python 合同测试与真实浏览器测试通过。
- [x] `npm test`、生成物 freshness 与桌面/窄屏浏览器 QA 通过。

## Validation evidence

- `python3 -m unittest discover -s tests -v`: 50 项通过，覆盖源码模型、稳定 ID、UTF-16/CRLF 往返、显式布局文件名与指纹、布局冲突和显式多图布局。
- `npm run test:content-authoring`: Focused Harness 严格构建并通过浏览器回归，覆盖旧文字/布局缓存隔离、新增/重排、Gallery 切换、跨页移动、布局指令与 sidecar 同步、图片导入、Markdown 安全序列化、文件写回及源码/布局冲突拒绝。
- `env PATH="<temporary-python3-shim>:$PATH" npm test`: 全量 Python 与 7 组浏览器/图表测试通过；临时 shim 仅用于本机 `python` 命令兼容，未加入仓库。
- 从当前源重新生成 `examples/basic`、`examples/diagrams` 与 `examples/archscribe` 的 `index.html` / `index.build.json`；三组 strict 构建通过，其中 diagrams 使用 `--render-diagrams`。
- 真实浏览器检查通过：1920×1080 下新增文本、选中、双图并列/Tab Gallery 与图片显示正常；820×900 和 375×800 下编辑面板无横向溢出；控制台无 error/warning。
