# Content Authoring / 内容编辑

[中文](#中文) · [English](#english)

## 中文

内容编辑让浏览器中的修改在重新构建后仍然存在。它编辑 Markdown、布局 sidecar 和本地资产，而不是把临时 HTML 当作源文件。

### 设计师可以做什么

按 `E` 打开编辑器并进入“内容”模式：

内容模式开启期间暂停演示快捷键（包括 `E`、聚焦与翻页），即使文本字段失焦也不会误触发。`Esc` 保留取消选择和关闭编辑器的行为；输入法组合输入期间不处理这些快捷键。

- 新增文本卡片或 Note Callout。
- 编辑受控的标题、正文和图注。
- 拖拽或使用上下按钮调整文本与 Callout 顺序。
- 把文字、Callout 或图片移到相邻内容页。
- 上传、拖放或粘贴 PNG、JPEG、WebP。
- 替换当前选中的图片，或向当前页追加图片。
- 在多图并列 `grid` 与 Gallery `tabs` 之间切换。
- 选择当前页已有的 Chapter，或创建新的 Chapter 名称。

封面页、章节页和锁定的表格/代码/图表舞台会限制不安全的跨页移动或媒体追加。

### 保存方式

点击“保存改动”后：

1. 浏览器请求选择文稿目录。
2. GolajahSlide 检查打开 HTML 时记录的 `slides.md` 和布局文件 SHA-256。
3. 只有文件未被其他程序修改时，才依次写入新资产、布局 JSON 和 Markdown。
4. 保存成功后会要求重新构建；在重建前不会继续写源文件。

如果浏览器不支持目录写入、用户取消授权、文件冲突或保存失败，会下载 `.golajah-edit.json` 恢复包。它包含原始源文件、操作记录、布局数据和待写资产，方便找回工作。

编辑默认使用稳定的 Slide / 内容 ID，不依赖页面 DOM 顺序；在前面新增内容不会把旧编辑错配到其他区域。

### 作者注意事项

- 每页建议设置唯一且稳定的 `id`。
- 保存前不要在另一个编辑器里同时修改同一份 Markdown。
- 保存后必须重新运行构建器，再检查新的 HTML 和 `.build.json`。
- Git 仍是最可靠的版本回退方式。
- 只导出布局时，可继续使用与 Markdown 同名的 `.layout.json`。

### 验证

```bash
npm run test:content-authoring
```

专项示例：`harnesses/content-authoring/slides.md`

调试入口：`window.__SLIDE_CONTENT_AUTHORING__`

## English

Content Authoring makes browser edits survive a rebuild. It updates Markdown, the layout sidecar, and local assets instead of treating temporary DOM HTML as the source.

### What designers can do

Press `E` and enter Content mode:

- Add a text card or Note callout.
- Edit controlled titles, body copy, and captions.
- Reorder text and callouts by drag-and-drop or accessible buttons.
- Move text, callouts, or images to an adjacent content page.
- Upload, drop, or paste PNG, JPEG, and WebP files.
- Replace the selected image or append media to the current page.
- Switch a multi-image page between `grid` and Gallery `tabs`.
- Choose an existing Chapter or create a new Chapter name.

Cover pages, section pages, and locked table/code/diagram stages reject moves that cannot be recomposed safely in the browser.

### Saving

When you select “Save changes”:

1. The browser asks for the deck directory.
2. GolajahSlide checks the `slides.md` and layout-file SHA-256 values captured when the HTML was built.
3. It writes new assets, layout JSON, and Markdown only if those files were not changed elsewhere.
4. A successful save requires a rebuild and blocks further source writes until then.

If direct directory saving is unsupported, cancelled, denied, conflicting, or unsuccessful, the browser downloads a `.golajah-edit.json` recovery bundle with the base source, operation log, layout data, and pending assets.

Stable Slide and content IDs are used instead of DOM position, so inserting earlier content does not redirect an old edit to another region.

### Author notes

- Give every page a unique, stable `id`.
- Do not edit the same Markdown in another app while saving from the browser.
- Rebuild after every save, then review the new HTML and `.build.json`.
- Keep Git history for dependable rollback.
- Layout-only work may still be exported as a same-basename `.layout.json` file.

### Validation

```bash
npm run test:content-authoring
```

Focused example: `harnesses/content-authoring/slides.md`

Debug surface: `window.__SLIDE_CONTENT_AUTHORING__`
