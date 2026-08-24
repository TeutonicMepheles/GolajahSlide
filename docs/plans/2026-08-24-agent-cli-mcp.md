# Agent CLI and MCP Bridge

- Plan ID: `20260824-agent-cli-mcp`
- Status: `Implemented`
- Created: `2026-08-24`
- Last updated: `2026-08-24`

## Goal

为 Hermes 等 Agent 提供稳定、结构化、可审计的 GolajahSlide 操作入口，使 Agent 能高频完成演示稿盘点、检索、页面读取、质量报告、内容新增/替换和构建，同时复用浏览器内容编辑器的稳定 ID 与源码 SHA-256 合同，避免旧上下文覆盖或按易漂移页码误改正文。

## Scope

- 提供一个 Python 标准库 CLI，输出默认采用机器可读 JSON，并可生成 Markdown 质量报告。
- 提供同进程 stdio MCP server，将 CLI 能力映射为 `tools/list` / `tools/call`。
- 支持 deck inspect、search、slide get、audit、edit 与 build 六类高频操作。
- edit 支持插入页面、替换页面、追加页面内容以及更新标题/副标题/页面指令。
- 所有 edit 默认 dry-run 并返回 unified diff；实际写入必须同时传 `write=true`、当前源文件 SHA-256，并在布局 sidecar 存在时传其当前 SHA-256。
- 所有 mutation 只接受页面的显式稳定 ID；页码选择器仅用于只读 `get`，不会在写操作中回退匹配。
- MCP server 通过固定 `--root` 限制可访问路径，拒绝 `..` 或符号链接逃逸。
- MCP 的 source 校验与构建共享同一 Markdown 快照；root 内资产的哈希与嵌入复用同一次 no-follow 读取，并在实际读取 SVG 时拒绝嵌套本地引用。
- 复用 `build_slides.py` 的 lossless authoring document、稳定 slide ID、严格构建和诊断报告，不复制 Markdown 方言解析逻辑。
- 为 Hermes/MCP host 提供可复制的 stdio 配置示例与 Agent 调用建议。

## Non-goals

- 首版不让 MCP server 自行调用模型生成文案、图片或引用。
- 不开放删除页面、任意文件写入、Shell 执行、Git 提交或远端发布。
- 不实现网络 MCP transport；本机 Agent 优先使用边界更小的 stdio。
- 不改变 `build_slides.py` 的兼容 CLI，也不为普通 Markdown 构建增加包依赖。
- 不尝试从 Agent 侧重现浏览器布局编辑状态机。

## Ownership and boundaries

- `golajah_slide_agent.py` 负责 Agent CLI、变更计划应用、安全写入、审计封装与 stdio MCP 协议适配。
- `build_slides.py` 继续独占 Markdown 解析、authoring source map、布局解析、构建与诊断语义。
- `tests/test_agent_cli.py` 覆盖 CLI、源码冲突、路径边界、编辑操作和 MCP 生命周期/工具调用。
- `docs/AGENT-TOOLS.md` 负责用户、Hermes 与其他 MCP host 的配置及调用契约。

## Acceptance gates

- [x] inspect/search/get 对中文、稳定 ID、页码选择器与结构化内容返回一致结果。
- [x] audit 在临时目录构建，不污染源目录，并返回构建 warnings/errors 与页面布局摘要。
- [x] edit dry-run 不写磁盘；写入缺失或使用错误 source/layout SHA-256 时拒绝；正确哈希写入后分文件原子替换并返回新哈希。
- [x] 插入页面必须具有唯一显式 ID；替换页面保留原显式 ID；所有操作后重新解析并拒绝重复 ID 或缺失标题。
- [x] MCP 完成 initialize、initialized、ping、tools/list 与 tools/call；stdout 只输出逐行 JSON-RPC。
- [x] MCP `--root` 拒绝根目录外直接或间接读取与写入；不暴露删除、Shell、Git 或发布工具。
- [x] 构建 HTML 与 `.build.json` 成对 staging/提交并按目标加锁，提交后校验内容哈希，后一个产物失败时仅在目标仍属于本事务时恢复原产物；源码与 sidecar 的正常异常路径具备哈希所有权回滚。
- [x] CLI/MCP focused tests、`npm test`、实际 0822 deck 只读 inspect/audit 和 `git diff --check` 通过。

## Validation evidence

- `python3 -m unittest tests.test_agent_cli -v`：52 项 Agent 契约、路径边界、双哈希、并发恢复、布局迁移与 MCP lifecycle 测试通过。
- `python3 -m unittest discover -s tests -p 'test_*.py' -v`：111 项全量 Python 测试通过。
- `PATH=<temporary python3 shim>:$PATH npm test`：全量 Python 与 presenter-focus、footer-chapter-navigation、citations、global-logo、media-playback、content-authoring、static-export、diagram-design 八组浏览器测试通过。
- Hermes Agent v0.20.5 `hermes mcp test golajah_contract_test`：stdio 连接成功并发现 6 个工具；仅使用 `work/` 下临时 `HERMES_HOME`，未改用户全局 Hermes 配置。
- 实际 `examples/ai-interaction/slides.md`（0822）：只读 inspect 得到 114 页、114 个显式 ID、267 个内容项、0 个结构问题；strict audit 为 0 warning / 0 error，且前后 SHA-256 均为 `2a88d41931e3a3468fe4dcaf868029cd417ac9e817597912307d67ba5e0d9b27`。
- `python3 -m py_compile build_slides.py golajah_slide_agent.py tests/test_agent_cli.py tests/test_build_slides.py` 与 `git diff --check` 通过。
