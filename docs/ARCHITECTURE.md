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

`golajah_slide_agent.py` is an adapter around the build runtime, not a third rendering runtime. Its CLI and stdio MCP interfaces reuse the lossless authoring model and builder, add revision/path guards, and never become an alternate Markdown parser.

## Authoring and derived-output boundaries

The build runtime embeds an exact-source authoring model containing UTF-16 source ranges, stable Slide/item/field IDs, effective Section membership, and source/layout SHA-256 values. Content Authoring may use that model to preview structured edits in the live DOM, but persistence is expressed as typed operations against stable identities rather than cached DOM order or edited `innerHTML`.

A browser source save requires explicit directory permission and matching source/layout hashes. It writes content-addressed assets before layout and Markdown, refuses stale or externally changed files, and exports a recovery bundle when a direct transaction cannot finish safely. A successful save still requires the Python builder to regenerate the self-contained HTML and `.build.json`; the browser does not become a second compiler.

Static Export is a flattened derivative of a sanitized live-DOM clone, not an editable source model. It cannot modify Markdown, layout sidecars, authoring drafts, or presentation state. Content Authoring, the Layout Editor, Media Playback, and Static Export collaborate only through their documented public bridges; for example, Media Playback exits fullscreen and sanitizes transient controls before a clone is captured.

## Source ownership

| Path | Ownership |
|---|---|
| `build_slides.py` | Compatible CLI and current build-runtime composition root |
| `golajah_slide_agent.py` | JSON-first Agent service, CLI, safe edit transaction, and local stdio MCP adapter |
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
Agent adapters -> lossless authoring model + build orchestration
browser authoring -> embedded source model + typed operations
static export -> sanitized live DOM + build-time asset manifest
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
