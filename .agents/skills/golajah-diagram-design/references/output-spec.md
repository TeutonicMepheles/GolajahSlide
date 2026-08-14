# GolajahSlide Output Specification

## Canvas

Use a single output preset:

| Preset | SVG viewBox | Destination |
|---|---:|---|
| `golajah-slide` | `0 0 1840 800` | Full-stage diagram below the Slide header |

The header, subtitle, footer, caption, and navigation belong to GolajahSlide,
not to the diagram. Keep the SVG free of a duplicate title block.

## Safe area

- Keep every meaningful node, connector, arrowhead, label, and annotation at
  least 40px from all four edges.
- A full-canvas background rectangle is allowed and ignored by the margin
  measurement.
- Do not reserve a legend strip by default. If a legend is essential, place it
  inside the 40px safe area and include it in the density budget.

## Type scale

The SVG is shown one-to-one inside an 1840×800 Slide region.

| Role | Size | Weight |
|---|---:|---:|
| Node name | 32px | 650–700 |
| Secondary label | 28px | 500 |
| Connector label | 28px | 600 |
| Zone / eyebrow | 28px | 700 |
| Editorial annotation | 30px | 500 italic |

Never use visible text below 28px. Shorten wording, remove nonessential labels,
or split the diagram instead.

## Density

| Detail | Nodes | Edges | Rule |
|---|---:|---:|---|
| `faithful` | up to 12 | up to 16 | Zone above 9 nodes; split if type cannot remain 28px |
| `balanced` | up to 9 | up to 12 | Collapse repeated leaves and move detail to narration |
| `simplified` | up to 6 | up to 8 | Keep only the audience's primary story |

The default is `faithful`; optimization must not imply silent simplification.

## Delivery

The authored `.diagram.html` is self-contained and contains a single primary
inline SVG. `build_slides.py --render-diagrams` extracts that SVG, measures it,
writes `.svg`, and records a `.diagram-build.json` sidecar. The final deck then
inlines a sanitized, namespaced SVG and adds no browser dependency.
