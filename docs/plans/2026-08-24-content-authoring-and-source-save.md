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
- 打开布局编辑器或在编辑器开启时切页，优先选择可编辑的图像区域，其次选择文字区域；整体内容区域保留为显式的低频选项。
- 编辑器选项按内容、布局、样式、全局和文件操作分组；高频内容与布局默认展开，低频分组默认折叠。
- 文本块与 Callout 可在当前页通过拖拽重新排序。
- 支持上传、拖入或粘贴 PNG、JPEG、WebP，以替换占位图、替换现有图片或向当前页追加图片。
- 两张及以上图片可在编辑器中选择 Tab Gallery 或并列展示。
- 选中的图片、文本块或 Callout 可移动到上一页或下一页，并同步重算两页布局。
- 当前页可在编辑模式中选择所属 Chapter item，或输入新名称并把当前页归入新 item；空值恢复为页面标题。
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
- [x] 布局编辑器在文字页默认进入文字范围，在图文、Gallery 与纯图页默认进入图像范围；同页提交不覆盖用户手动选择的整体内容范围。
- [x] 高频编辑分组默认展开，低频分组默认折叠；折叠标题支持键盘操作且窄屏无横向溢出。
- [x] `npm test`、生成物 freshness 与桌面/窄屏浏览器 QA 通过。
- [x] Chapter item 选择、新增、标题回退、草稿恢复和 Markdown 安全序列化通过浏览器回归。
- [x] 切页会清理上一页内容选择，上传、拖放和粘贴不会误替换上一页图片。

## Validation evidence

- `python3 -m unittest discover -s tests -v`: 112 项通过，覆盖 Agent CLI/MCP、源码模型、稳定 ID、UTF-16/CRLF 往返、有效 Section 继承、显式布局文件名与指纹、布局冲突和显式多图布局。
- `npm run test:content-authoring`: Focused Harness 严格构建并通过浏览器回归，覆盖旧文字/布局缓存隔离、新增/重排、Gallery 切换、跨页移动、Chapter 选择/新增/标题回退、同 Section 投影、IME 与 Unicode/标量/directive 安全、净零草稿清理、切页与异步图片导入选择隔离、保存后 strict 重建、布局指令与 sidecar 同步、文件写回及源码/布局冲突拒绝；同时验证文字/图像默认区域、五类选项归属与展开规则和 375×800 窄屏滚动/溢出。
- `env PATH="<temporary-python3-shim>:$PATH" PUPPETEER_EXECUTABLE_PATH="<Chrome-for-Testing>" npm test`: 112 项 Python 与 8 组浏览器/图表测试全部通过；临时 shim 与浏览器路径仅用于本机验证，未加入仓库。
- 从当前源重新生成 `examples/basic`、`examples/diagrams` 与 `examples/archscribe` 的 `index.html` / `index.build.json`；三组 strict 构建通过，其中 diagrams 使用 `--render-diagrams`。
- 真实浏览器检查通过：1920×1080 下新增文本、选中、双图并列/Tab Gallery 与图片显示正常；820×900 和 375×800 下编辑面板无横向溢出；控制台无 error/warning。
- 应用内浏览器真实点击检查通过：文字页首次打开选中“文字范围”；手动选择“内容范围”并重套预设后保持不变；编辑器开启时翻到 Gallery 自动选中“图像范围”，再回到文字页恢复“文字范围”；控制台无 error/warning。
- 应用内浏览器真实点击与截图检查通过：内容/布局默认展开，样式/全局/高级默认折叠；打开低频分组可见完整控件，折叠活动内容或动画分组会退出对应模式；控制台无 error/warning。
