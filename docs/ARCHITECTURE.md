# GolajahSlide Architecture

## Product contracts

- A normal Markdown build requires Python 3.10+ and the standard library only.
- The delivered deck is a single self-contained HTML document.
- The generated browser runtime does not fetch framework code, styles, fonts, or feature modules at runtime.
- Optional Mermaid, Excalidraw, and Archscribe generation remains a build-time concern.
- `build_slides.py` remains the compatible user-facing CLI.

## Runtime boundaries

GolajahSlide has two runtimes:

1. **Build runtime** — Python parses Markdown, validates content, resolves layouts, renders slide HTML, and composes the final artifact.
2. **Browser runtime** — HTML, CSS, and JavaScript present the deck, manage interaction, edit layouts, and report visual diagnostics.

The boundary between them is generated HTML plus embedded JSON and `data-*` attributes. Browser features must not depend on Python implementation details, and Python features must not reproduce browser state machines.

## Source ownership

| Path | Ownership |
|---|---|
| `build_slides.py` | Compatible CLI and current build-runtime composition root |
| `src/web/features/<feature>/` | Browser Feature behavior, styles, public contract, and local documentation |
| `templates/deck.html` | Browser composition shell and shared markup only |
| `harnesses/<feature>/` | Minimal executable scenario for one Feature |
| `tests/` | Unit, integration, contract, and browser validation |
| `examples/` | User-facing examples and generated showcase artifacts |
| `docs/plans/` | Feature execution plans and validation history |

Feature source fragments are composed into `templates/deck.html` during the Python build. This keeps development ownership separate while preserving the Python-only, single-file delivery contract.

## Dependency direction

```text
composition shell -> features -> shared browser primitives
build orchestration -> compiler capabilities -> core models/diagnostics
```

- Feature internals are private by default.
- Cross-Feature access must use an explicit public API and be recorded in both Feature READMEs.
- Shared code is extracted only after two real consumers exist or an independently testable stable contract is clear.
- Shared primitives must not import Feature code.
- The composition shell may construct Features but must not contain their state machines or full style implementations.

## Feature completion contract

A browser Feature is complete when it has:

1. A Plan with goal, non-goals, ownership, and acceptance gates.
2. A Feature directory with behavior, styles, and README.
3. A focused Harness that does not rely on a previously generated example HTML file.
4. Unit or contract coverage for generator integration where applicable.
5. A real browser test for observable interaction.
6. A strict sample build and an up-to-date generated-output check.

## Deliberate non-goals

The current architecture does not require React, Vue, a monorepo, a browser package loader, or a generic plug-in framework. ES module bundling may be introduced when multiple extracted browser Features need imports; it is not required merely to move cohesive source out of the composition shell.
