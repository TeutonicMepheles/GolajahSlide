# Citations / 引用角标

[中文](#中文) · [English](#english)

## 中文

引用角标把标准 Markdown 脚注变成适合演示的编号来源。观众悬浮或用键盘聚焦角标时，可以看到来源说明并打开原始链接。

### 写法

```markdown
正文结论[^source].

[^source]: 来源标题 — https://example.com/original
```

- ID 可使用字母、数字、 `_` 和 `-`，最长 64 个字符。
- 来源定义可放在整份文稿的任意位置；重复使用同一 ID 会复用编号。
- 来源末尾必须是 HTTP(S) 地址或 Markdown 链接。
- 来源定义不会作为页面正文显示。
- 演示时按 `Escape`、移开指针或移走焦点即可关闭提示。

本功能不会联网抓取标题或摘要，成品 HTML 仍可离线使用。

### 验证

```bash
npm run test:citations
```

## English

Citation markers turn standard Markdown footnotes into numbered, presentation-friendly sources. Hover or keyboard-focus a marker to read the source and open its original link.

### Authoring

```markdown
Key finding[^source].

[^source]: Source title — https://example.com/original
```

- IDs may contain letters, numbers, `_`, and `-`, up to 64 characters.
- Definitions are deck-wide and may appear anywhere; repeated IDs reuse one number.
- A definition must end with an HTTP(S) URL or Markdown link.
- Definitions do not appear as slide content.
- `Escape`, pointer departure, or focus departure closes the tooltip.

The feature never fetches citation metadata, so the delivered HTML remains offline-ready.

### Validation

```bash
npm run test:citations
```
