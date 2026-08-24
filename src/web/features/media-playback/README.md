# Media Playback / 视频播放

[中文](#中文) · [English](#english)

## 中文

GolajahSlide 直接使用浏览器播放本地 MP4 和 WebM。视频、封面图和控制逻辑都会进入单文件 HTML，不依赖第三方播放器。

### 写法

视频与图片一样独占一行：

```markdown
![产品演示](assets/demo.mp4 "操作流程")
```

如需要静音自动循环：

```markdown
<!-- slide
video-playback: autoplay-loop
-->
```

- 默认由观众点击播放。
- 自动循环只在当前页面及当前 Gallery Tab 可见时播放。
- 离开页面或切换 Tab 会暂停，但不会重置进度。
- 同目录下同名 PNG、JPEG 或 WebP 会自动成为封面图。
- 独立视频、Gallery Tab 和并列 Gallery 都有可键盘操作的全屏按钮。
- 换页、隐藏 Tab 或进入编辑模式会安全退出全屏。
- 指针、触摸和滚轮操作视频控件时不会误触发翻页。
- 本功能不增加运行时网络或包依赖。

### 验证

```bash
npm run test:media-playback
```

专项示例：`harnesses/media-playback/slides.md`

## English

GolajahSlide plays local MP4 and WebM with the browser's native video element. Video, posters, and controls are embedded in the single HTML delivery file—no third-party player is required.

### Authoring

Use the same standalone line syntax as an image:

```markdown
![Product demo](assets/demo.mp4 "Walkthrough")
```

For muted autoplay and looping:

```markdown
<!-- slide
video-playback: autoplay-loop
-->
```

- Playback is user-initiated by default.
- Autoplay runs only while the slide and its Gallery tab are visible.
- Leaving the slide or hiding the tab pauses without resetting progress.
- A same-basename PNG, JPEG, or WebP file becomes the poster.
- Standalone, tabbed, and grid videos all receive a keyboard-accessible fullscreen button.
- Slide changes, hidden tabs, and editor mode exit fullscreen safely.
- Pointer, touch, and wheel interaction with video controls never advances the deck.
- The feature adds no runtime network or package dependency.

### Validation

```bash
npm run test:media-playback
```

Focused example: `harnesses/media-playback/slides.md`
