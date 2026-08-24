# Static Export / 静态导出

[中文](#中文) · [English](#english)

## 中文

静态导出把当前演示稿直接下载为 16:9 PDF 或 PowerPoint。它优先保持 HTML 的视觉效果，因此每页会转成一张 1920×1080 的高保真图片。

### 使用方式

按 `E` 打开编辑器，在“高级 · 文件”中选择：

- “导出 PDF”：固定 16:9 的静态 PDF。
- “导出 PowerPoint”：默认无动效 PPTX。
- “导出带转场 PowerPoint（实验）”：从第 2 页开始加入原生 Fade 转场。

### 重要边界

- 所有逐步出现内容会完整显示，CSS 动画和编辑器界面不会进入导出文件。
- Gallery 中隐藏的 Tab 会展开成附加页，避免漏掉内容。
- 视频优先显示封面或已有画面；GIF / WebP 动图会冻结为静态画面。
- PDF 文字不可选择或搜索；PPTX 页面不能解组编辑。
- 链接、视频、音频和逐对象动画不会保留。
- 实验性 PPTX 只有页面间 Fade，不会还原 HTML 动画。
- 外部或无法安全读取的图片会让导出明确失败，而不是生成空白页。
- 导出过程不会改变当前页、Gallery 选择、播放进度、Markdown 或布局文件。

### 验证

```bash
npm run test:static-export
```

专项示例：`harnesses/static-export/slides.md`

## English

Static Export downloads the current deck as a 16:9 PDF or PowerPoint. It prioritizes visual fidelity by turning every page into one full-frame 1920×1080 image.

### Use

Press `E`, then open Advanced → File:

- “Export PDF”: static 16:9 PDF.
- “Export PowerPoint”: static PPTX with no transitions.
- “Export PowerPoint with transitions (experimental)”: native Fade from page 2 onward.

### Important limits

- Reveals are fully shown; CSS animation and editor UI are removed.
- Hidden Gallery tabs become additional pages so content is not lost.
- Video uses a poster or available frame; GIF / WebP animation is frozen.
- PDF text is not selectable or searchable; PPTX pages cannot be ungrouped.
- Links, video, audio, and object animation are not preserved.
- Experimental PPTX adds page-level Fade only; it does not recreate HTML animation.
- Unsafe or unavailable external images produce a clear error instead of a blank page.
- Export does not change the current page, Gallery selection, playback, Markdown, or layout files.

### Validation

```bash
npm run test:static-export
```

Focused example: `harnesses/static-export/slides.md`
