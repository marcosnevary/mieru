"""The "mieru" note type: a comprehension card (word → picture) and a production
card (picture → word), both with audio and the user's personal connection on the back."""

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
PERSONAL_CONNECTION_FIELD = "Personal Connection"
# Last because Anki appends fields added to an existing note type, so new and
# migrated note types end up in the same order.
FIELDS = (WORD_FIELD, AUDIO_FIELD, IMAGE_FIELD, ENGLISH_FIELD, PERSONAL_CONNECTION_FIELD)

_WORD = f'<span class="word">{{{{furigana:{WORD_FIELD}}}}}</span>'
_AUDIO = f"{{{{{AUDIO_FIELD}}}}}"
_AUDIO_ROW = f'<div class="audio">{_AUDIO}</div>'
_PICTURE = f"{{{{{IMAGE_FIELD}}}}}"
_CONNECTION = f'<div class="connection">{{{{{PERSONAL_CONNECTION_FIELD}}}}}</div>'

# No <hr> divider, but id="answer" stays on each back: Anki scrolls to it when
# showing the answer.
_TEMPLATES = (
    (
        "Comprehension",
        f'<div class="heading">{_WORD}</div>',
        f'<div class="heading">{_WORD}</div>\n'
        f'<div id="answer" class="picture">{_PICTURE}</div>\n'
        f"{_AUDIO_ROW}\n{_CONNECTION}",
    ),
    (
        "Production",
        f'<div class="picture">{_PICTURE}</div>',
        f'{{{{FrontSide}}}}\n<div id="answer" class="audio">{_AUDIO}</div>\n'
        f'<div class="heading">{_WORD}</div>\n{_CONNECTION}',
    ),
)

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
  /* Drops the gap an inline image leaves below itself for text descenders. */
  vertical-align: bottom;
}

/* A flex row is as tall as the button, where an inline button would sit in a
   line box sized for the card's 48px text. */
.audio {
  display: flex;
  justify-content: center;
  margin-top: 0.1em;
}

/* The word when it follows the picture and audio, on the production back. */
.audio ~ .heading {
  margin-top: 0.4em;
}

.connection {
  margin-top: 0.25em;
  font-size: 0.4em;
}"""


def ensure_note_type(col: Collection) -> NotetypeDict:
    """Return the mieru note type, creating it the first time.

    An existing note type gets missing fields and templates added, and the
    add-on's current templates and CSS back, so changes reach collections
    created by older versions. Adding fields or templates is a schema change:
    Anki asks the user to confirm the full sync it requires, and raises
    AbortSchemaModification if they decline.
    """
    models = col.models
    if existing := models.by_name(NOTE_TYPE_NAME):
        _update(col, existing)
    else:
        _create(col)

    # Reloaded: fields and templates only get their ordinals once saved.
    notetype = models.by_name(NOTE_TYPE_NAME)
    assert notetype is not None
    return notetype


def _create(col: Collection) -> None:
    models = col.models
    notetype = models.new(NOTE_TYPE_NAME)
    for name in FIELDS:
        models.add_field(notetype, models.new_field(name))
    for name, _front, _back in _TEMPLATES:
        models.add_template(notetype, models.new_template(name))
    _apply_layout(notetype)
    models.add_dict(notetype)


def _update(col: Collection, notetype: NotetypeDict) -> None:
    models = col.models
    missing_fields = [name for name in FIELDS if name not in models.field_names(notetype)]
    missing_templates = [name for name, _front, _back in _TEMPLATES[len(notetype["tmpls"]) :]]
    if missing_fields or missing_templates:
        col.mod_schema(check=True)
    for name in missing_fields:
        models.add_field(notetype, models.new_field(name))
    for name in missing_templates:
        models.add_template(notetype, models.new_template(name))

    layout_changed = _apply_layout(notetype)
    if missing_fields or missing_templates or layout_changed:
        models.update_dict(notetype)


def _apply_layout(notetype: NotetypeDict) -> bool:
    """Set the templates and CSS to the add-on's; return whether anything changed."""
    changed = False
    for template, (name, front, back) in zip(notetype["tmpls"], _TEMPLATES):
        if (template["name"], template["qfmt"], template["afmt"]) != (name, front, back):
            template["name"], template["qfmt"], template["afmt"] = name, front, back
            changed = True
    if notetype["css"] != _CSS:
        notetype["css"] = _CSS
        changed = True
    return changed
