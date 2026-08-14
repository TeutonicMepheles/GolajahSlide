# GolajahSlide Diagram Style Guide

Use semantic roles rather than inventing a palette per diagram.

## Tokens

| Role | Value | Purpose |
|---|---|---|
| `paper` | `#FFFFFF` | SVG background and default node fill |
| `paper-2` | `#F8F7FC` | Quiet zone or store fill |
| `ink` | `#111111` | Primary text and strong stroke |
| `muted` | `#5B5965` | Secondary text and default connectors |
| `soft` | `#85828E` | Tertiary structure |
| `rule` | `#D7D6DD` | Hairline borders and zones |
| `accent` | `#6F60E5` | One or two focal elements |
| `accent-strong` | `#4C3BC6` | Accent text on pale backgrounds |
| `accent-tint` | `#F0EEFF` | Focal node fill |
| `link` | `#2F6FCE` | External/API connection when semantically useful |

## Typography

Use the deck's offline font stacks:

```text
Names: "PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif
Code:  "SFMono-Regular", Consolas, "Liberation Mono", monospace
```

Human-readable names use the sans stack. Use mono only for genuinely technical
tokens such as ports, commands, and field types. The build normalizer enforces
the deck sans stack on inline SVG text, so hierarchy must also survive through
size, weight, spacing, and color.

## Geometry

- Use a 4px grid.
- Use 2px default strokes and 3px focal strokes.
- Use 8px node radii and 12px zone radii; avoid pills and large bubbles.
- Do not use shadows, gradients, glow, or decorative dot fields.
- Default nodes are white with an `ink` stroke; stores use `paper-2` with a
  `muted` stroke; focal nodes use `accent-tint` with an `accent` stroke.

## Connectors

- Draw connectors before nodes.
- Use `muted` for ordinary edges, `accent` for the single primary path, and
  dashed edges for return/optional paths.
- Route orthogonally. Round each elbow with an 8px quarter arc.
- Fan multiple edges to distinct attach points at least 16px apart.
- Keep connector labels on an opaque `paper` mask with 8px visual clearance.
