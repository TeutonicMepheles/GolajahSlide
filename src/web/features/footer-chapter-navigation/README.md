# Footer Chapter Navigation / 页脚章节导航

[中文](#中文) · [English](#english)

## 中文

页脚中的 Section 可展开 Chapter 列表，帮助观众在长演示中快速跳转。悬浮或键盘聚焦 Section，即可在其上方打开菜单。

### 内容写法

```markdown
<!-- slide
section: 方案
chapter: 设计原则
-->
```

- 同一 Section 下重复的 Chapter 名称只显示一次，并跳到第一次出现的页面。
- 未填写 `chapter` 时，使用页面标题作为菜单项。
- 未填写 Section 的开头页面会归入第一个已声明的 Section。
- 键盘支持 `↑`、`↓`、`Home`、`End`、`Enter` 和 `Escape`。
- 编辑模式和打印模式会自动隐藏浮动菜单。

### 验证

```bash
npm run test:footer-chapter-navigation
```

专项示例：`harnesses/footer-chapter-navigation/slides.md`

## English

Footer Sections open a Chapter menu for quick navigation through long decks. Hover or keyboard-focus a Section to open the menu above the footer.

### Authoring

```markdown
<!-- slide
section: Solution
chapter: Design principles
-->
```

- Repeated Chapter names within one Section become one entry targeting the first matching page.
- If `chapter` is omitted, the slide title becomes the menu label.
- Leading pages without a Section belong to the first authored Section.
- Keyboard controls: `↑`, `↓`, `Home`, `End`, `Enter`, and `Escape`.
- Editor and print modes hide the floating menu.

### Validation

```bash
npm run test:footer-chapter-navigation
```

Focused example: `harnesses/footer-chapter-navigation/slides.md`
