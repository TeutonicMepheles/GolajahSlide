# Presenter Focus / 演示者聚焦

[中文](#中文) · [English](#english)

## 中文

演示者聚焦用主题色圆点提示鼠标位置，并在悬浮时强调文字容器与段落，适合讲解复杂页面。它只改变演示效果，不改内容或布局。

### 使用方式

- 按 `H` 或点击聚焦按钮开启；默认关闭。
- 可在页面编辑器中更换整份文稿通用的快捷键。
- 进入编辑模式、鼠标离开页面或窗口失去焦点时，提示会自动隐藏。
- 触摸设备或不支持悬浮的设备不会显示该效果。
- 系统开启“减少动态效果”时会移除缩放动画。
- 所有颜色都从当前主题色生成。

### 验证

```bash
npm run test:presenter-focus
```

专项示例：`harnesses/presenter-focus/slides.md`

## English

Presenter Focus adds a theme-colored pointer cue and highlights text containers or paragraphs on hover. It helps explain dense pages without changing content or layout.

### Use

- Press `H` or select the Focus control. It is off by default.
- The editor can replace `H` with one deck-wide shortcut.
- Editor mode, pointer departure, or window blur hides the cue automatically.
- Touch-only devices and devices without hover do not show the effect.
- Reduced-motion mode removes focus scaling.
- All colors are derived from the active theme.

### Validation

```bash
npm run test:presenter-focus
```

Focused example: `harnesses/presenter-focus/slides.md`

### Content editing shortcut boundary

The shared `body.content-authoring-active` mode marker suppresses the focus shortcut even between editable fields. IME composition events also leave focus state unchanged.
