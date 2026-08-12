# GolajahSlide agent guidance

- Read `docs/ARCHITECTURE.md` before changing project structure or browser runtime behavior.
- Check `docs/plans/README.md` before starting a feature. Keep the matching Plan status and validation evidence current while executing it.
- Preserve the product contracts: ordinary Markdown builds require only Python, the delivered deck is one self-contained HTML file, and browser runtime features add no network or package dependency.
- Treat `src/` and Markdown/assets under `examples/` or `harnesses/` as source. Generated example `index.html` and `index.build.json` files must be regenerated from current source when their output changes.
- Browser features own their behavior and styles under `src/web/features/<feature>/`. `templates/deck.html` is the composition shell; do not place a new feature's full implementation back into the shell.
- A browser feature must expose a focused Harness and browser test before it is considered implemented.
- Keep `build_slides.py` as the compatible CLI entry point. Refactor its internals only behind behavior-preserving tests.
- Run `npm test` before implementation handoff. Report any validation that was not run.
