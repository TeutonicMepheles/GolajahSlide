# 演示者悬浮聚焦方案

## 目标

演讲者把鼠标移到文字容器上时，容器立即成为视觉主角：目标保持明亮、出现主题色轮廓并轻微抬升，其余页面覆盖柔和暗幕。鼠标移开后自动恢复，不改变 Slide 布局，也不阻断容器内的链接或表格交互。

## 同类方案与匹配度

| 方案 | 现有实现 | 优点 | 对 GolajahSlide 的匹配度 |
| --- | --- | --- | --- |
| 激光点 | [PowerPoint 激光笔](https://support.microsoft.com/en-US/PowerPoint/turn-your-mouse-into-a-laser-pointer) | 能指向任意像素，用户熟悉 | 中。目标点小，需要按键或拖动；无法利用工程已有的文字容器语义 |
| 鼠标 Spotlight | [Reveal.js Spotlight](https://github.com/denniskniep/reveal.js-plugin-spotlight)、[Quarto Spotlight](https://github.com/mcanouil/quarto-revealjs-spotlight) | 聚光区域醒目，半径与淡入可配置 | 中低。需要持续跟踪指针并渲染遮罩，容易与图片拖拽、缩放、标注争用事件 |
| 容器级悬浮聚焦 | CSS `:hover`、`:has()` 与输入能力媒体查询 | 零依赖、零指针跟踪、目标稳定，能直接复用标题/卡片结构 | 高。最符合单文件 HTML、语义化容器和现有编辑器架构 |

最终采用容器级悬浮聚焦。`:has()` 已是现代浏览器广泛可用能力；选择器只锚定当前 `.slide`，避免在 `body` 或根节点上做大范围关系查询。输入能力通过 `@media (hover: hover) and (pointer: fine)` 限制为鼠标或触控板，避免触屏设备出现粘滞悬浮态。参考：[MDN `:has()`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Selectors/:has)、[MDN `hover`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/hover)。

## 交互设计

- 默认关闭；工具栏的 `◎` 或键盘 `H` 可随时开启/关闭。
- 当前 Slide 内会显示一个不拦截交互的圆形鼠标示意；系统鼠标仍然保留。关闭聚焦、进入编辑器、离开 Slide 或窗口失焦时圆圈隐藏。
- 第一层可聚焦对象：封面/章节文字、页面标题、正文卡片、callout、代码块和表格。
- 第二层文本片段：容器内的标题、段落、列表项、代码正文和表格单元格会自动响应悬浮；Markdown 中可用 `==重点短语==` 精确标记行内片段。
- 颜色遵循语义深度：容器使用较浅的主题色混合，鼠标圆圈使用中等强度，文本片段使用更重的主题色；三者全部由 `--accent`、`--accent-soft` 和 `--ink` 派生，会随 Slide 主题自动变化。
- 悬浮时目标提升到暗幕之上，并添加主题色轮廓、白色光晕和轻微缩放。
- 聚焦期间只放开目标祖先链上的裁切，确保轮廓和阴影完整，同时保留页面平时的溢出诊断与保护。
- 页面编辑器打开时自动暂停，避免干扰区域拖拽、文字编辑和动画顺序编排。
- 图片、图表和流程图不属于文字悬浮目标，继续使用已有的缩放、拖拽、全屏和标注交互。
- 全屏表格不应用缩放，打印输出不包含聚焦效果。
- `prefers-reduced-motion: reduce` 下保留明暗与轮廓，但取消缩放。参考：[MDN `prefers-reduced-motion`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion)。

## 实现结构

构建器为语义文字容器输出 `data-presenter-focus`。[Presenter Focus Feature](../src/web/features/presenter-focus/README.md) 的样式用 `:hover` 提亮目标，并用当前 Slide 上受限范围的 `:has()` 打开暗幕；`PresenterFocus` 负责工具栏与全局快捷键开关、文本目标注册和指针圆圈状态。快捷键默认是 `H`，可在页面编辑器的“演示快捷键”中录入新键位，并随布局 JSON 保存。圆圈的位置更新以 `requestAnimationFrame` 合并，只写入一个不接收指针事件的展示节点，不改变既有指针事件顺序。构建时 Feature CSS/JavaScript 会被内联进模板，最终产物仍是单文件 HTML。

不支持 `:has()` 的旧浏览器会自然降级：目标仍有轮廓和光晕，但不会显示整页暗幕；内容、导航和编辑能力不受影响。

专项可运行场景位于 [`harnesses/presenter-focus`](../harnesses/presenter-focus/slides.md)，浏览器验证运行 `npm run test:presenter-focus`。
