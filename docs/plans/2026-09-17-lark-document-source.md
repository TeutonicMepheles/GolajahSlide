# Lark document source

Status: Implemented

## Goal

Build a deck directly from a Feishu/Lark docx or Wiki URL using the installed,
user-authenticated `lark-cli`. Create a native editable Feishu document from the
basic example and verify the full document → HTML round trip.

## Boundaries

- Keep local Markdown builds Python-standard-library-only and unchanged.
- Own the source adapter under `src/importers/`; no new browser runtime feature.
- Fetch at build time only; keep CLI credentials outside the repository/output.
- Preserve page metadata through supported YAML code blocks; ordinary headings,
  paragraphs, lists, tables and images remain native editable document blocks.
- Download document images/whiteboard previews and embed imported images in HTML.
- Reject unsupported document constructs explicitly rather than silently omit them.
- Do not modify existing cloud documents or unrelated working-tree changes.

## Acceptance

- Unit/integration coverage: pagination, Wiki type checking, metadata round trip,
  tables/callouts, media, unsupported blocks, failed CLI calls and CLI routing.
- Native sample created as the user; cloud content fetched back, strict build passes.
- Browser checks all imported sample pages, media loading, offline requests and overflow.
- `npm test` passes. Record remaining limitations and commands in user documentation.

## Evidence

- Initial inspection: user authentication expired; scoped login started.
- 2026-09-17: user reauthorized; created the native sample as `user`:
  https://www.feishu.cn/docx/HUzTdcJX8oB33jxRXLZcpKfun1f .
- Uploaded the two basic-example images as PNG; 8 pages retain original IDs,
  requested layouts, native text/table content, chart data and emphasis semantics.
- Live `--lark ... -o examples/lark/index.html --strict`: 8 slides, no warnings/errors.
- Live pagination comparison (1000-character pages vs full fetch) is identical.
- `npm test`: 39 Python tests and Presenter Focus, Diagram Design, Layout Editor,
  Lark browser suites pass. New importer adds 13 Python cases.
- Lark browser test rebuilds from the checked-in snapshot and verifies generated
  HTML is current. 8 pages × 2 viewport widths; all images embedded and loaded;
  table/chart/highlight/callout assertions pass; no JS errors, HTTP requests or
  runtime diagnostic overflow. Evidence: `work/lark-browser/verification.json`,
  `page-1.png` through `page-8.png`, `npm-test.log`.
- Visual review of image and table screenshots completed.
- Wiki resolution, unsupported-type handling and CLI failures are covered by
  automated tests; live end-to-end verification used the created docx URL.
- Known limitation: CLI did not export the sample images' captions; generic image
  labels are documented. Complex native blocks fail explicitly. No automatic sync.
- Existing unrelated working-tree edits retained. No commit or push performed.
