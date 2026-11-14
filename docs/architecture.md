# Architecture

mieru is an Anki add-on. The user types an English word, picks one of the Japanese words the dictionary returns, picks a picture, writes a personal connection to the word, and mieru adds a note with three cards: comprehension (word without furigana → picture and pronunciation, with the reading on the back), production (picture → word and pronunciation) and writing (picture and pronunciation → the word drawn by hand).

## Layout

| Path | Role |
| --- | --- |
| `src/mieru/__init__.py` | Entry point Anki imports. Adds **Tools › mieru…** (W) once the main window exists. |
| `src/mieru/core/` | Pure Python, no `aqt` imports: dictionary, furigana, audio, picture sources, HTTP. Tested with pytest. |
| `src/mieru/ui/` | Everything that touches Anki's Qt UI or the collection: the dialog and the note type. |
| `scripts/build.py` | Zips `src/mieru` into `mieru.ankiaddon`. |

Inside the add-on, modules import each other relatively (`from ..core import …`): an add-on installed from AnkiWeb lives in a folder named after its numeric ID, not `mieru`.

## Flow

1. **Search.** The search field takes one English word or a list separated by commas or line breaks. On Enter, every word of the list starts loading at once, and the user moves between words with Previous/Next or by clicking a word in the list under the field. Each word keeps what was loaded and chosen for it (candidates, audio, pictures, picture search term, selections), so going back shows it as it was left. For each word, the Jisho lookup starts in the background, keyed by the English word. The word is also the initial picture search term, which starts one background search per picture source with a key configured (plus thumbnail downloads, eight at a time per source); each source's results are appended as they arrive, so with several sources a slow or failing one doesn't hold back the others. Editing that field and searching again replaces only the pictures, keeping the chosen candidate and its audio: abstract words like "nice to meet you" often need a concrete term ("handshake").
2. **Candidate.** Each word's first candidate has its audio fetched as soon as the lookup returns, so it plays on reaching the word. Selecting another candidate fetches its audio in the background, once per candidate, and plays it when it arrives.
3. **Add.** Add stays disabled until the word has a candidate, a picture and a personal connection; the connection is kept per word like the other choices. The full-size picture and the word's stroke order diagrams are downloaded; picture and audio are written to the collection's media folder as `mieru_<word>.<ext>`, each diagram as `mieru_stroke_order_<character>.svg` (shared by every word with that character), and the note is added to the chosen deck through Anki's undoable `add_note` operation. The word is marked added and the window moves to the next word not yet added (wrapping around, so skipped words come back), or resets once every word is added.

Every network call runs in a `QueryOp(...).without_collection()`, so the UI never blocks and requests don't queue behind collection access. Results are stored on the word they belong to and shown only if it is the current word; pictures for a superseded picture search term are dropped. Offline, every word of a list fails at once, so only one network warning is shown at a time. The dialog is created once and reused, so late results land on a hidden window rather than a deleted one.

## Note type

`mieru`, created on first use if missing. When it already exists, its templates and CSS are reset to the add-on's whenever they differ, so layout changes reach existing collections; hand edits to them in Anki don't survive. Missing fields and templates are added too, which is a schema change: Anki asks the user to confirm the full sync it forces, and nothing is added if they decline. Anki then generates the new cards for existing notes.

Templates, matched by position:

- `Comprehension`: front shows the word without furigana; back shows the word with furigana and the audio button beside it, the picture, and the personal connection.
- `Production`: front shows the picture; back adds the word with the audio button beside it and the personal connection.
- `Writing`: front shows the picture with the audio button under it, plays the audio and has a drawing area with a Clear button; back keeps the drawing (read-only) over the word's stroke order, faded, inside the same area, and adds the personal connection, for the user to compare and grade themselves. The word itself is left out, since the stroke order already shows it; it appears only on notes without stroke order (added before it existed), which would otherwise have no answer. The stroke order is part of the front's HTML, hidden by CSS, because the back's drawing area comes from `{{FrontSide}}`; the script reveals it on the back. `{{FrontSide}}` recreates the canvas empty, so the template's script saves the drawing as a data URL in `sessionStorage` after each stroke and redraws it on the back; the front starts by clearing it. The drawing area's classes are prefixed `mieru-` because Anki's reviewer CSS styles `.drawing` with `zoom: 50%`.

The backs of comprehension and production separate their blocks with a thin divider: word, picture and personal connection. The writing card separates the picture (with its audio button) from the drawing area, and the drawing area from the personal connection.

Fields, in order:

- `Word`: the word in Anki furigana syntax (`食[た]べる`), rendered with `{{furigana:Word}}`, the reading in blue (lighter in night mode) so it stands apart from the kanji. It is the first field, so Anki's duplicate check applies to it; adding a duplicate asks for confirmation.
- `Audio`: `[sound:…]`, beside the word on the back of comprehension and production, under the picture on the front of writing.
- `Image`: `<img>`.
- `English`: the searched word (not the picture search term). Not shown on the cards; kept so notes can be found in the Browser.
- `Personal Connection`: what the user wrote, HTML-escaped, at the bottom of every back, set in the system font and light gray (lighter in night mode) to stand apart from the Japanese text.
- `Stroke Order`: one `<img>` per distinct character of the word, behind the drawing on the back of the writing card only. KanjiVG draws in black, like the pencil, so a CSS filter turns the diagrams red in both light and night mode; the files themselves stay unchanged. Empty for notes added before it existed, and the card then shows none.

Fields added after the first release come last because Anki appends fields added to an existing note type, so new and older collections share the field order.

## External sources

- **Jisho** (`jisho.org/api/v1/search/words?keyword=`): JMdict-based, no key. Candidates are sorted common-first, keeping Jisho's order within each group, because Jisho ranks phrases containing the query (犬の顔) above the word itself (犬). Entries without a reading (imported from Wikipedia) are skipped.
- **JapanesePod101** (`assets.languagepod101.com/dictionary/japanese/audiomp3.php?kanji=&kana=`): native recordings. A missing word still returns HTTP 200 with a fixed "audio not available" clip, recognised by its MD5 `7e2c2f954ef6051373ba916f000168dc`.
- **Google Translate TTS** (`translate.google.com/translate_tts`, `client=tw-ob`): unofficial; fallback when JapanesePod101 has no recording or fails. Requires a browser-like User-Agent. If it also fails, the note is added without audio.
- **KanjiVG** (`raw.githubusercontent.com/KanjiVG/kanjivg/master/kanji/<code point, 5 hex digits>.svg`): stroke order diagrams for kanji and kana, strokes numbered. CC BY-SA 3.0; the SVGs are stored unchanged, so each keeps its copyright header. A character it lacks (404) or that fails to download is left out rather than blocking the note.

Picture sources are listed in `core/images.py` `SOURCES`; each needs the user's own free API key in the add-on config and is skipped when its key is empty. A rejected key is reported under the picture label for that source only. Each thumbnail's tooltip credits its author.

- **Pixabay** (`pixabay.com/api/`, `pixabay_api_key`): a bad key comes back as a plain-text HTTP 400 mentioning "API key". Thumbnails use `previewURL`; the card stores `webformatURL` (640 px), downloaded at add time because Pixabay's URLs expire after 24 hours. The API terms require showing Pixabay as the source next to results.

## Furigana

`core/furigana.py` attaches readings to kanji runs only. The word is split into kana and non-kana runs; kana runs become literal anchors and non-kana runs lazy groups in a regex matched against the reading, both normalised to hiragana. Each non-kana run after the first character gets a leading space, because Anki's ruby base extends back to the previous space. If the reading can't be aligned, the whole word gets the whole reading (`食べる[くう]`).

## Decisions

- **Jisho for the dictionary, user picks the candidate.** Free, no key, and English → Japanese is ambiguous (bank → 銀行, 土手), so choosing automatically would often be wrong.
- **JapanesePod101 first, Google TTS fallback.** Native recordings cover most common words; TTS guarantees audio for the rest. Forvo was rejected because it needs a paid key.
- **Pixabay for pictures.** Royalty-free and good for illustrating nouns; the cost is that each user needs a free key. It is weak on people and situations (greetings, actions); the picture search term covers most of that. Pexels was tried as a second source but stopped issuing API keys (November 2026). Openverse needs no key but returns less illustrative results and was slow and timing out when re-evaluated; Irasutoya has no API.
- **Picture search term separate from the dictionary word.** The English word is often a poor image query for abstract vocabulary; refining it shouldn't discard the chosen Japanese candidate.
- **Word list in the search field.** Commas or line breaks in the same field instead of a separate list widget, so adding a single word works as before.
- **Whole list loaded up front.** Moving between words never waits, at the cost of requests for words that end up skipped. Pixabay allows 100 requests a minute per key, so a list of more than about 100 words would hit its limit.
- **Comprehension and production cards on one note type.** Recognising the word and recalling it from the picture are different skills, so each note is reviewed in both directions. One note type keeps a single note per word, and older notes gain the production card automatically, at the cost of one full sync. The English word stays hidden on every card so it can't be read instead of recalling the meaning.
- **Audio on the back of comprehension and production.** Hearing the word on the front would give away the production answer and let the comprehension card be answered by ear instead of by reading. On the writing card the audio is the cue, as in a dictation: the skill tested is writing the word, not recalling it.
- **Furigana on the comprehension back only.** The reading on the front would give away the pronunciation, turning recognition of the word into reading its ruby. Hiding the `<rt>` elements with a class on the front template needs no field, no script and no schema change, and works on every client.
- **Drawing canvas in the writing template.** Writing by hand fixes the shape of the kanji. A canvas in the template works in Anki desktop, AnkiDroid and AnkiMobile without another add-on. `{{type:}}` was rejected because it tests typing through an IME, not writing; the mobile apps' whiteboards because desktop has none. There is no automatic check: the user compares the drawing with the stroke order laid behind it.
- **KanjiVG stored in the media folder.** Downloaded at add time, the diagrams work offline and sync to mobile like the picture and audio. Loading them from a CDN in the card script was rejected because reviews often happen offline; a stroke order font because it shows only static numbers and would have to be shipped in every collection.
- **Personal connection required.** Linking the word to something of one's own makes it stick; making it optional would let it be skipped every time.
- **W opens the window.** A single key like Anki's own A (Add) and B (Browse), reachable with the left hand alone. M was rejected because the reviewer already uses it for its More menu, and two shortcuts on one key make Qt fire neither.
- **`requests` over `urllib`.** Anki already bundles it, so it adds nothing to the package.
- **PyQt6 pinned to Anki's bundled version in dev.** Type stubs then match what runs, and PyQt6 6.12's stubs don't parse under mypy.
