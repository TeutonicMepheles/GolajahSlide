# GolajahSlide Agent CLI and MCP

`golajah_slide_agent.py` provides a JSON-first command-line interface and a local stdio MCP server for Hermes and other agents. Both interfaces reuse GolajahSlide's lossless Markdown source map, stable slide IDs, source and layout SHA-256 checks, strict builder, and build diagnostics. They do not replace `build_slides.py`, the browser editor, or Git.

The intended split is:

- Use the CLI from shell-capable agents, scripts, CI, and one-off local automation.
- Use stdio MCP when the host supports tool discovery and typed tool calls, especially Hermes conversations reached through Feishu or another gateway.
- Keep one MCP server rooted at one deck directory when possible. A narrower root produces a smaller failure and authorization boundary than the whole repository.

## Requirements

- Python 3.10 or newer.
- A local GolajahSlide checkout containing `golajah_slide_agent.py` and `build_slides.py`.
- No package installation is needed for the CLI or MCP server. The MCP transport is implemented with the Python standard library.
- Diagram rendering and browser-based export retain their existing optional Node.js/Chromium requirements; merely inspecting, searching, editing, auditing, or building an ordinary Markdown deck does not add those dependencies.

Use absolute paths in long-running agent configuration. On this Mac, discover the interpreter rather than assuming its location:

```bash
command -v python3
```

## JSON-first CLI

Run commands from the GolajahSlide repository. In the default JSON format, every command writes one JSON document to stdout; diagnostics and usage details go to stderr. This keeps stdout safe for pipes and agent parsing. Use `--format markdown` only when a human-readable report is the desired final output.

Successful JSON commands use `{"ok": true, "result": {...}}`. Argument, conflict, and I/O failures use `{"ok": false, "error": {"code": "...", "message": "..."}}` and exit 2. A completed strict `audit` or `build` whose diagnostics fail uses `{"ok": false, "result": {...}}` and exit 1 so callers retain the full report. Branch on top-level `ok`; when `error` is present, branch on `error.code` rather than localized message text.

Every deck source must end with `.md`. Build output must end with `.html`; the adjacent `.build.json` report is derived automatically. `audit` and `build` are strict by default. Use `--no-strict` only when a diagnostic run should return non-strict builder results; `--strict` remains accepted but is normally redundant. MCP uses the same default and accepts `strict: false` for the equivalent override.

```bash
python3 golajah_slide_agent.py inspect examples/basic/slides.md
python3 golajah_slide_agent.py search examples/basic/slides.md --query "布局"
python3 golajah_slide_agent.py get examples/basic/slides.md --slide-id wide-image
python3 golajah_slide_agent.py audit examples/basic/slides.md
python3 golajah_slide_agent.py build examples/basic/slides.md --output examples/basic/index.html
```

`search` also accepts its query positionally. `get --slide` is an alias of `get --slide-id`. Selectors that accept either a stable slide ID or page number should prefer the stable ID. Page numbers are convenient for reading but shift when slides are inserted.

### Safe edits

Edits use a structured operation rather than an arbitrary shell command. Every edit is a dry run by default and returns the proposed source SHA-256 plus a unified diff. An actual write requires both `--write` and the exact current source hash returned by `inspect`, `get`, or the dry run. If the selected deck has a layout sidecar, the write also requires its current SHA-256 from `inspect.result.layout.sha256`.

```bash
# First inspect and copy result.source.sha256 and result.layout.sha256.
# examples/basic/slides.layout.json exists, so both hashes are required here.
python3 golajah_slide_agent.py inspect examples/basic/slides.md

# Preview an operation; no file is changed.
python3 golajah_slide_agent.py edit examples/basic/slides.md \
  --operations /absolute/path/to/operation.json

# Apply only if the source still has the inspected hash.
python3 golajah_slide_agent.py edit examples/basic/slides.md \
  --operations /absolute/path/to/operation.json \
  --write \
  --expect-source-sha256 SOURCE_SHA256 \
  --expect-layout-sha256 LAYOUT_SHA256
```

`--operation-file` is an alias of `--operations`; `--expected-sha256` is an alias of `--expect-source-sha256`; `--expected-layout-sha256` is an alias of `--expect-layout-sha256`. `--operations -` reads the JSON operation plan from stdin, while `--operations-json` accepts an inline JSON array. If `inspect.result.layout.exists` is false, omit the layout-hash option.

The MCP edit tool uses the same contract with `write: true`, `expected_sha256`, and, when a sidecar exists, `expected_layout_sha256`. Always obtain both applicable values from one fresh inspection of the same source and sidecar.

Supported operations cover the high-frequency structural cases: insert a slide with a unique explicit ID, replace a slide while preserving its ID by default, append content to a slide, and update its title, subtitle, or directive fields. The CLI deliberately does not expose slide deletion, arbitrary file writes, shell execution, Git, push, or publishing.

Every mutation selector must be an exact explicit slide ID. Page numbers and generated `P<n>` identities are accepted only by the read-only `get` command; edit operations never fall back from an unmatched ID to a page number.

An operation file may be a JSON array or an object containing an `operations` array. Operation names and fields are stable snake_case values:

```json
{
  "operations": [
    {
      "op": "set_fields",
      "slide_id": "wide-image",
      "fields": {
        "title": "宽屏图片布局",
        "config": {
          "chapter": "图片布局"
        }
      }
    },
    {
      "op": "append_content",
      "slide_id": "wide-image",
      "markdown": "> [!NOTE] 补充说明\n> 正文"
    }
  ]
}
```

`insert_slide` uses `after_slide_id` plus complete slide Markdown and requires a unique explicit `id`. `replace_slide` uses `slide_id` plus complete slide Markdown and rejects an accidental ID change. Do not assemble operation JSON with shell interpolation when the content contains Markdown, quotes, or newlines; write a normal UTF-8 JSON file and pass its absolute path.

After an applied edit, run `audit` or a strict `build`. A successful source write means the Markdown is internally parseable; it is not a substitute for build diagnostics or browser-visible QA.

### Reports

`inspect`, `search`, and `get` are appropriate for context gathering. `audit` performs an isolated temporary build and returns the builder's warnings, errors, layout summary, source fingerprint, and relevant inventory without replacing the deck's checked-in HTML or `.build.json`. Use it for review reports and before proposing content changes.

Example agent workflow:

1. `inspect` to learn the deck title, stable IDs, sections, and source hash.
2. `search` to find relevant pages without loading the entire Markdown into context.
3. `get` for the exact page source and structured content.
4. `edit` without `--write` to produce a reviewable diff.
5. Apply the reviewed diff with `--write --expect-source-sha256 ...` and, when present, `--expect-layout-sha256 ...`.
6. `audit`, then `build`, then browser QA for audience-visible delivery. Both commands are already strict by default.

## Hermes stdio MCP configuration

The Hermes Agent v0.20.5 currently installed on this Mac supports local stdio MCP servers directly. Register the server through the Hermes CLI so it can probe the tool list and save an allowlist:

```bash
hermes mcp add golajah_basic \
  --command /opt/homebrew/bin/python3 \
  --args \
    /absolute/path/to/GolajahSlide/golajah_slide_agent.py \
    mcp \
    --root \
    /absolute/path/to/deck-directory

hermes mcp test golajah_basic
```

`--args` must be the last `hermes mcp add` option. Replace the interpreter with the output of `command -v python3`, and replace the deck root when configuring another deck.

At the interactive tool-selection prompt, enable only the GolajahSlide tools you expect to use. Start with the read-only inspection, search, slide-read, and audit tools. Add edit/build only when that Hermes profile is meant to author files.

The equivalent `~/.hermes/config.yaml` shape is shown below for review. Prefer `hermes mcp add` and `hermes mcp configure golajah_basic` for normal changes.

```yaml
mcp_servers:
  golajah_basic:
    command: /opt/homebrew/bin/python3
    args:
      - /absolute/path/to/GolajahSlide/golajah_slide_agent.py
      - mcp
      - --root
      - /absolute/path/to/deck-directory
    enabled: true
    trust: untrusted
    connect_timeout: 15
    timeout: 300
    supports_parallel_tool_calls: false
    tools:
      include:
        - golajah_deck_inspect
        - golajah_deck_search
        - golajah_slide_get
        - golajah_deck_audit
      resources: false
      prompts: false
```

Hermes prefixes discovered names as `mcp__golajah_basic__<tool>`. A globally enabled MCP server is available to Hermes gateway platforms by default unless that platform uses `no_mcp` or an explicit MCP-server allowlist. If several MCP servers are installed, restrict Feishu to the intended server instead of exposing all of them:

```yaml
platform_toolsets:
  feishu:
    - hermes-feishu
    - golajah_basic
```

After configuration, start a new Hermes session or run `/reload-mcp`. A Feishu conversation can call the tools only while the Hermes gateway is running; verify with:

```bash
hermes gateway status
hermes mcp test golajah_basic
```

Useful Hermes prompts include:

```text
先用 GolajahSlide 工具盘点 slides.md，按 Section 汇总页数、图片数量和构建警告，输出一份 Markdown 报告，不要修改文件。
```

```text
搜索包含“布局”的页面，读取最相关的三页并提出修改方案。先返回 dry-run diff，不要直接写入。
```

```text
对 slide id=wide-image 追加一段 Callout。先检查当前 source SHA-256 和 layout SHA-256，给我 diff；得到确认后才用相同哈希写入，并运行 audit。
```

For a non-Hermes MCP host that accepts the common `mcpServers` shape:

```json
{
  "mcpServers": {
    "golajah_basic": {
      "command": "/opt/homebrew/bin/python3",
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

## Security model

The boundary is intentionally narrower than giving an agent an unrestricted terminal:

- `mcp --root` is mandatory. Requested `.md` sources, `.html` outputs, layout sidecars, and deck-referenced local media, posters, diagrams, and diagram sidecars must remain inside that root. Resolution rejects `..`, absolute-path escape, unsupported local URI schemes, encoded-path ambiguity, and symlink escape. Source validation and build share one Markdown snapshot; each security-sensitive asset hash/embed uses bytes from one no-follow regular-file read.
- Local SVG assets are inspected before an MCP audit or build. They may not pull in nested local files through `href`, `src`, `srcset`, or CSS `url(...)`; fragment and embedded image-data references remain self-contained. This check prevents the static-export asset collector from reading a second path outside the configured root.
- Read tools do not update generated HTML, reports, layout sidecars, or source files. `audit` builds in a temporary directory.
- `edit` defaults to dry-run. A source write requires an explicit write flag plus the exact current source SHA-256 and, when a sidecar exists, its exact current SHA-256.
- Changing a slide's Markdown `layout` removes the stale sidecar `layout`, `regions.visual`, and `regions.copy` values while retaining a manually adjusted `regions.content` box and unrelated typography/animation settings. This matches the browser editor's preset-change reconciliation and prevents old geometry from overriding the new layout.
- `build` is intentionally not a dry run: it replaces the requested `.html` output and adjacent `.build.json` report immediately, and its MCP annotation is destructive. Use `audit` when no delivery artifact should be written.
- Cooperating Agent writers for the same source are serialized with a POSIX advisory lock. Source and layout files are staged and individually replaced atomically, with snapshot checks and guarded recovery around a multi-file edit. Markdown commits before its source-hash-bound sidecar, so an uncatchable process termination leaves a stale sidecar that the builder rejects rather than deleting its old overrides. Operations are reparsed before commit and reject duplicate slide IDs, missing required structure, or unsupported targets.
- Delivery HTML and its `.build.json` report are staged together. Overlapping destinations are serialized with in-process locks and POSIX advisory locks; if either normal commit step fails, the previous pair is restored. Each committed destination is hash-verified before success, and rollback restores a destination only while it still contains this transaction's bytes, so a non-cooperating external save is reported instead of overwritten. An OS-level crash still cannot make two filesystem paths one indivisible transaction.
- The advisory lock is not an operating-system compare-and-swap. A manual editor or other process that does not take the same lock can still race between a hash check and replacement, so the SHA-256 preconditions do not promise true CAS against non-cooperating writers. Avoid simultaneous external saves and retain Git or another recovery path.
- The server exposes typed GolajahSlide operations only. It has no general shell, delete, Git, commit, push, remote publish, arbitrary URL fetch, or model-call tool.
- Builds use argument arrays rather than shell strings and retain GolajahSlide's existing strict-validation behavior.
- MCP stdout contains protocol JSON only. Human diagnostics are sent to stderr so logging cannot corrupt the stdio session.
- Tool results do not embed generated HTML or binary assets. Search result count and snippets are capped, but `get` returns the selected page's complete Markdown and `edit` returns the complete unified diff; unusually large pages or edits can therefore produce large, not globally bounded, responses.
- `trust: untrusted` asks Hermes to require approval for tools not annotated read-only. Keep `supports_parallel_tool_calls: false` because edits and builds can contend for the same files.
- MCP annotations are hints, not an operating-system sandbox. The fixed root, narrow tool surface, source-hash precondition, and Hermes allowlist remain the primary controls.

Do not configure the repository root as `--root` merely for convenience if one deck directory is enough. Do not put secrets in MCP arguments or config; this server does not need credentials. Keep Git commit/push and external publication as separate, explicit user-authorized workflows after inspecting the generated diff and validation report.

## Failure handling

- `SOURCE_CONFLICT`: inspect again; another process changed `slides.md`. Do not retry with the old hash.
- `EXPECTED_LAYOUT_SHA256_REQUIRED` or `LAYOUT_CONFLICT`: inspect again and pass the current layout hash together with the current source hash. Do not reuse either value after one file changes.
- `PATH_OUTSIDE_ROOT`: correct the configured root or request path. Do not broaden the root unless the additional directory is genuinely in scope.
- `UNSAFE_SVG_REFERENCE`: make the SVG self-contained; embed the nested image or move that composition into a supported deck asset instead of pointing the SVG at another local file.
- `BUILD_OPERATION_FAILED`: the builder could not read or commit its artifacts. Inspect `error.details.logs`, fix the filesystem or output target, and retry; this is exit 2, not a content-diagnostic result.
- `INVALID_SOURCE` or `INVALID_OUTPUT`: use a `.md` deck source and a `.html` build output.
- Validation failure after a dry run: revise the structured operation; do not patch generated HTML.
- MCP probe failure: run the exact configured command in a terminal, then `hermes mcp test <name>`. Confirm that stdout contains no banner or debug log.
- Tools absent in a running Hermes session: run `/reload-mcp` or start a new session, check the server's `tools.include`, and verify that the platform does not use `no_mcp`.
- Gateway conversation cannot call tools: confirm `hermes gateway status`, platform pairing/allowlist, and the platform toolset configuration independently of MCP connectivity.

The MCP process ending when its host closes stdin is normal. It should not be installed as a separate daemon or exposed on a network port.
