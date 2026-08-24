# Global Logo / 全局 Logo

[中文](#中文) · [English](#english)

## 中文

全局 Logo 在每页右上角显示统一品牌标识，默认关闭。

### 使用方式

1. 按 `E` 打开编辑器。
2. 在全局设置中启用 Logo，并上传 PNG、JPEG 或 WebP。
3. 在页面中拖动左下角手柄调整尺寸。

- 图片最大 2 MB，会内嵌到 HTML 中。
- 宽度范围为 80–420 px，高度范围为 36–180 px。
- Logo 始终以右侧为锚点，并与标题区域垂直居中。
- 如只想隐藏某一页，在该页 Markdown 配置中加入：

```markdown
<!-- slide
global-logo: hidden
-->
```

单页隐藏不会删除全局图片或尺寸设置。

### 验证

```bash
npm run test:global-logo
```

专项示例：`harnesses/global-logo/slides.md`

## English

Global Logo places one consistent brand mark at the upper-right of every slide. It is off by default.

### Use

1. Press `E` to open the editor.
2. Enable the logo in Global settings and upload a PNG, JPEG, or WebP file.
3. Drag the lower-left handle to resize it.

- Maximum upload size: 2 MB. The image is embedded in the HTML.
- Width: 80–420 px; height: 36–180 px.
- The right edge stays anchored and the logo remains centered on the title region.
- To hide it on one page only, add:

```markdown
<!-- slide
global-logo: hidden
-->
```

Per-page hiding keeps the shared image and size settings.

### Validation

```bash
npm run test:global-logo
```

Focused example: `harnesses/global-logo/slides.md`
