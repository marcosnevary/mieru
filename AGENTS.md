# mieru

Anki add-on: English word → Japanese card (word on the front; furigana, audio and a chosen picture on the back). Product: `PRODUCT.md`. Architecture and external APIs: `docs/architecture.md`.

## Commands

```sh
uv run ruff format src tests scripts && uv run ruff check src tests scripts
uv run mypy
uv run pytest
uv run python scripts/build.py   # mieru.ankiaddon
```

## Rules

- `src/mieru/core/` must not import `aqt`; anything touching Qt or the collection goes in `src/mieru/ui/`.
- Inside `src/mieru`, import relatively: the installed add-on folder is not always named `mieru`.
- Add-on code must run on Python 3.9 (ruff's `target-version`); the dev environment's newer Python doesn't change that.
- Network calls go through `core/http.py` and run in `QueryOp(...).without_collection()`, never on the UI thread.
- UI text is in English.
- The name is styled all lowercase — "mieru" — in UI text, docs and the note type name, even at the start of a sentence. Python class names stay PascalCase (`MieruDialog`).
- Manual testing happens in the user's Anki: the checkout is symlinked into `~/Library/Application Support/Anki2/addons21/mieru`, and Anki must be restarted to pick up changes.
