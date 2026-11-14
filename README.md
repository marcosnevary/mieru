# mieru

Anki add-on that turns an English word into a Japanese flashcard: the front shows the word with furigana and plays its pronunciation, the back shows a picture you choose.

## Using it

1. Install the add-on (see below) and restart Anki.
2. Get a free Pixabay API key: create an account at [pixabay.com](https://pixabay.com/accounts/register/), then open [pixabay.com/api/docs](https://pixabay.com/api/docs/) while logged in.
3. In Anki, open **Tools › Add-ons**, select mieru, click **Config** and paste the key into `pixabay_api_key`.
4. Open **Tools › mieru…** (or press W on the main window), choose the deck, type an English word, pick the Japanese word and a picture and click **Add**. If no picture fits, type a more concrete term in the picture search field (handshake for nice to meet you) and search again.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync                      # dev environment (Anki's aqt for types, pytest, ruff, mypy)
uv run ruff format --check src tests scripts
uv run ruff check src tests scripts
uv run mypy
uv run pytest
```

Run the checkout inside Anki by symlinking it into the add-ons folder, then restart Anki:

```sh
ln -s "$PWD/src/mieru" ~/Library/Application\ Support/Anki2/addons21/mieru
```

Build the installable package (`mieru.ankiaddon`, installed via **Tools › Add-ons › Install from file**):

```sh
uv run python scripts/build.py
```

How it works: [docs/architecture.md](docs/architecture.md).
