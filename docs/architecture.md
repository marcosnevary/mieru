# Architecture

mieru is an Anki add-on. The user types an English word, picks one of the Japanese words the dictionary returns, picks a picture, and mieru adds a note whose front shows the word with furigana and plays its pronunciation, and whose back shows only the picture.

## Layout

| Path | Role |
| --- | --- |
| `src/mieru/__init__.py` | Entry point Anki imports. Adds **Tools › mieru…** (W) once the main window exists. |
| `src/mieru/core/` | Pure Python, no `aqt` imports: dictionary, furigana, audio, picture sources, HTTP. Tested with pytest. |
| `src/mieru/ui/` | Everything that touches Anki's Qt UI or the collection: the dialog and the note type. |
| `scripts/build.py` | Zips `src/mieru` into `mieru.ankiaddon`. |

Inside the add-on, modules import each other relatively (`from ..core import …`): an add-on installed from AnkiWeb lives in a folder named after its numeric ID, not `mieru`.

## Flow

1. **Search.** On Enter, the Jisho lookup starts in the background, keyed by the English word. The word is also copied into a separate picture search field, which starts one background search per picture source with a key configured (plus thumbnail downloads, eight at a time per source); each source's results are appended as they arrive, so with several sources a slow or failing one doesn't hold back the others. Editing that field and searching again replaces only the pictures, keeping the chosen candidate and its audio: abstract words like "nice to meet you" often need a concrete term ("handshake").
2. **Candidate.** Selecting a candidate fetches its audio in the background and plays it when it arrives.
3. **Add.** The full-size picture is downloaded, picture and audio are written to the collection's media folder as `mieru_<word>.<ext>`, and the note is added to the chosen deck through Anki's undoable `add_note` operation. The window then resets for the next word.

Every network call runs in a `QueryOp(...).without_collection()`, so the UI never blocks and requests don't queue behind collection access. Results that arrive after the user has moved on (new search, new picture search, different candidate, window closed) are dropped by comparing them to the current query, picture query or candidate. The dialog is created once and reused, so late results land on a hidden window rather than a deleted one.

## Note type

`mieru`, created on first use if missing. When it already exists, its template and CSS are reset to the add-on's whenever they differ, so layout changes reach existing collections; hand edits to them in Anki don't survive. Fields, in order:

- `Word`: the word in Anki furigana syntax (`食[た]べる`), rendered with `{{furigana:Word}}`. It is the first field, so Anki's duplicate check applies to it; adding a duplicate asks for confirmation.
- `Audio`: `[sound:…]`, played on the front by the button next to the word.
- `Image`: `<img>`, the only thing on the back.
- `English`: the searched word (not the picture search term). Not shown on the card; kept so notes can be found in the Browser.

## External sources

- **Jisho** (`jisho.org/api/v1/search/words?keyword=`): JMdict-based, no key. Candidates are sorted common-first, keeping Jisho's order within each group, because Jisho ranks phrases containing the query (犬の顔) above the word itself (犬). Entries without a reading (imported from Wikipedia) are skipped.
- **JapanesePod101** (`assets.languagepod101.com/dictionary/japanese/audiomp3.php?kanji=&kana=`): native recordings. A missing word still returns HTTP 200 with a fixed "audio not available" clip, recognised by its MD5 `7e2c2f954ef6051373ba916f000168dc`.
- **Google Translate TTS** (`translate.google.com/translate_tts`, `client=tw-ob`): unofficial; fallback when JapanesePod101 has no recording or fails. Requires a browser-like User-Agent. If it also fails, the note is added without audio.
Picture sources are listed in `core/images.py` `SOURCES`; each needs the user's own free API key in the add-on config and is skipped when its key is empty. A rejected key is reported under the picture label for that source only. Each thumbnail's tooltip credits its author.

- **Pixabay** (`pixabay.com/api/`, `pixabay_api_key`): a bad key comes back as a plain-text HTTP 400 mentioning "API key". Thumbnails use `previewURL`; the card stores `webformatURL` (640 px), downloaded at add time because Pixabay's URLs expire after 24 hours. The API terms require showing Pixabay as the source next to results.

## Furigana

`core/furigana.py` attaches readings to kanji runs only. The word is split into kana and non-kana runs; kana runs become literal anchors and non-kana runs lazy groups in a regex matched against the reading, both normalised to hiragana. Each non-kana run after the first character gets a leading space, because Anki's ruby base extends back to the previous space. If the reading can't be aligned, the whole word gets the whole reading (`食べる[くう]`).

## Decisions

- **Jisho for the dictionary, user picks the candidate.** Free, no key, and English → Japanese is ambiguous (bank → 銀行, 土手), so choosing automatically would often be wrong.
- **JapanesePod101 first, Google TTS fallback.** Native recordings cover most common words; TTS guarantees audio for the rest. Forvo was rejected because it needs a paid key.
- **Pixabay for pictures.** Royalty-free and good for illustrating nouns; the cost is that each user needs a free key. It is weak on people and situations (greetings, actions); the picture search term covers most of that. Pexels was tried as a second source but stopped issuing API keys (November 2026). Openverse needs no key but returns less illustrative results and was slow and timing out when re-evaluated; Irasutoya has no API.
- **Picture search term separate from the dictionary word.** The English word is often a poor image query for abstract vocabulary; refining it shouldn't discard the chosen Japanese candidate.
- **Back shows only the picture.** The picture is the answer; the English word is stored but hidden so it can't be read instead of recalling the meaning.
- **W opens the window.** A single key like Anki's own A (Add) and B (Browse), reachable with the left hand alone. M was rejected because the reviewer already uses it for its More menu, and two shortcuts on one key make Qt fire neither.
- **`requests` over `urllib`.** Anki already bundles it, so it adds nothing to the package.
- **PyQt6 pinned to Anki's bundled version in dev.** Type stubs then match what runs, and PyQt6 6.12's stubs don't parse under mypy.
