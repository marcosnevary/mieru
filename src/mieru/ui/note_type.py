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

_FRONT_TEMPLATE = (
    f'<div class="heading"><span class="word">{{{{furigana:{WORD_FIELD}}}}}</span>'
    f"{{{{{AUDIO_FIELD}}}}}</div>"
)

# No <hr> divider, but id="answer" stays: Anki scrolls to it when showing the answer.
_BACK_TEMPLATE = f"""{{{{FrontSide}}}}
<div id="answer" class="picture">{{{{{IMAGE_FIELD}}}}}</div>"""

_CSS = """.card {
  font-family: "Hiragino Sans", "Noto Sans JP", "Yu Gothic", sans-serif;
  font-size: 48px;
  text-align: center;
}

.heading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.3em;
}

.word rt {
  font-size: 0.45em;
}

.picture {
  margin-top: 0.5em;
}

.picture img {
  max-width: 100%;
  max-height: 60vh;
}"""


def ensure_note_type(col: Collection) -> NotetypeDict:
    """Return the mieru note type, creating it the first time.

    An existing note type gets the add-on's current template and CSS back, so
    layout changes reach collections created by older versions.
    """
    if existing := col.models.by_name(NOTE_TYPE_NAME):
        template = existing["tmpls"][0]
        if (template["qfmt"], template["afmt"], existing["css"]) != (
            _FRONT_TEMPLATE,
            _BACK_TEMPLATE,
            _CSS,
        ):
            template["qfmt"] = _FRONT_TEMPLATE
            template["afmt"] = _BACK_TEMPLATE
            existing["css"] = _CSS
            col.models.update_dict(existing)
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
