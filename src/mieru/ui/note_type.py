"""The "mieru" note type: Japanese word with furigana and audio, picture as the answer."""

from __future__ import annotations

from anki.collection import Collection
from anki.models import NotetypeDict

NOTE_TYPE_NAME = "mieru"

# Word comes first because Anki sorts and detects duplicates on the first field.
WORD_FIELD = "Word"
AUDIO_FIELD = "Audio"
IMAGE_FIELD = "Image"
# Not shown on the card; kept so notes can be searched by the English word.
ENGLISH_FIELD = "English"
FIELDS = (WORD_FIELD, AUDIO_FIELD, IMAGE_FIELD, ENGLISH_FIELD)

_FRONT_TEMPLATE = f"""<div class="word">{{{{furigana:{WORD_FIELD}}}}}</div>
{{{{{AUDIO_FIELD}}}}}"""

_BACK_TEMPLATE = f"""{{{{FrontSide}}}}
<hr id="answer">
<div class="picture">{{{{{IMAGE_FIELD}}}}}</div>"""

_CSS = """.card {
  font-family: "Hiragino Sans", "Noto Sans JP", "Yu Gothic", sans-serif;
  font-size: 48px;
  text-align: center;
}

.word rt {
  font-size: 0.45em;
}

.picture img {
  max-width: 100%;
  max-height: 60vh;
}"""


def ensure_note_type(col: Collection) -> NotetypeDict:
    """Return the mieru note type, creating it the first time."""
    if existing := col.models.by_name(NOTE_TYPE_NAME):
        return existing

    models = col.models
    notetype = models.new(NOTE_TYPE_NAME)
    for name in FIELDS:
        models.add_field(notetype, models.new_field(name))
    template = models.new_template("Word → Picture")
    template["qfmt"] = _FRONT_TEMPLATE
    template["afmt"] = _BACK_TEMPLATE
    models.add_template(notetype, template)
    notetype["css"] = _CSS
    models.add_dict(notetype)

    created = models.by_name(NOTE_TYPE_NAME)
    assert created is not None
    return created
