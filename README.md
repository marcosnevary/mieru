# 🎴 mieru - Japanese vocabulary cards with pictures

Learn Japanese vocabulary by linking each word to a picture instead of its English translation. mieru is an Anki add-on that creates the cards for you.

## Features

- **Three cards per word**
  - *Comprehension*: the Japanese word on the front, its picture and reading on the back.
  - *Production*: the picture on the front, the Japanese word on the back.
  - *Writing*: draw the word by hand, then compare it with the stroke order.
- **Native audio** for every card, with synthesized speech when no recording exists.
- **Furigana** added automatically.
- **Pictures from Pixabay** or from image files on your computer. Use one or more per word. Cards show no English.
- **Concrete search terms**: when a word makes a poor picture search (such as *nice to meet you*), search for a more specific term (such as *handshake*) and keep the Japanese word.
- **Personal note** on every card (a memory, a place, a person), which helps you remember the word.
- **Batch mode**: enter a list of English words and go through them one by one. You can move back, skip words, or stop at any time.

## Requirements

- Anki 2.1.31 or newer.
- A free [Pixabay](https://pixabay.com/accounts/register/) API key.

## Installation

1. Install mieru from AnkiWeb, or from a `.ankiaddon` file via **Tools › Add-ons › Install from file…**.
2. Restart Anki.
3. Get your Pixabay key from [pixabay.com/api/docs](https://pixabay.com/api/docs/) while logged in.
4. In **Tools › Add-ons**, select mieru, click **Config**, paste the key into `pixabay_api_key`, and save.

## Usage

1. Open **Tools › mieru…** (or press **W** in the main window).
2. Choose the deck.
3. Type an English word and pick the Japanese word.
4. Choose one or more pictures, write your note, and click **Add**.

## Development

See [docs/architecture.md](docs/architecture.md) for how the add-on works. To run the checkout inside Anki, symlink `src/mieru` into your add-ons folder and restart Anki. Checks: `uv run ruff check src tests scripts`, `uv run mypy`, `uv run pytest`.
