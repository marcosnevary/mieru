"""The "mieru" note type: a comprehension card (word → picture), a production card
(picture → word) and a writing card (picture and audio → the word drawn by hand,
checked against its stroke order), all with the user's personal connection on the
back."""

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
# KanjiVG diagrams (<img> tags) for the writing card.
STROKE_ORDER_FIELD = "Stroke Order"
# Later additions come last because Anki appends fields added to an existing note
# type, so new and migrated note types end up in the same order.
FIELDS = (
    WORD_FIELD,
    AUDIO_FIELD,
    IMAGE_FIELD,
    ENGLISH_FIELD,
    PERSONAL_CONNECTION_FIELD,
    STROKE_ORDER_FIELD,
)

_WORD = f'<span class="word">{{{{furigana:{WORD_FIELD}}}}}</span>'
_AUDIO = f"{{{{{AUDIO_FIELD}}}}}"
_AUDIO_ROW = f'<div class="audio">{_AUDIO}</div>'
_PICTURE = f"{{{{{IMAGE_FIELD}}}}}"
_CONNECTION = f'<div class="connection">{{{{{PERSONAL_CONNECTION_FIELD}}}}}</div>'

# {{FrontSide}} recreates the canvas empty on the back, so the drawing is saved
# after each stroke and redrawn there. sessionStorage survives the page reload some
# mobile clients do between sides; the window fallback covers clients that block it.
# The class is prefixed because Anki's reviewer CSS already styles .drawing
# (zoom: 50%, for its LaTeX images), which shrank the area and threw off pointers.
# Pages can still be zoomed (Anki zooms the body on high-DPI Windows and Linux) or
# resized, so pointer positions are mapped through the canvas's on-screen box and a
# ResizeObserver keeps its bitmap matching that box. Anki sets the night mode class
# only after running card scripts, so the stroke color is read when drawing.
# The IIFE keeps the constants out of the page's global scope, which desktop Anki
# keeps across cards. The button is blurred after a click so Space shows the
# answer instead of clicking it again.
_DRAWING_SCRIPT = """<script>
(() => {
  const KEY = "mieru-drawing";
  const LINE_WIDTH = 6;
  const area = document.querySelector(".mieru-drawing");
  const canvas = area.querySelector("canvas");
  const button = area.querySelector("button");
  const context = canvas.getContext("2d");
  const isBack = document.getElementById("answer") !== null;

  const save = (value) => {
    window.mieruDrawing = value;
    try {
      if (value) sessionStorage.setItem(KEY, value);
      else sessionStorage.removeItem(KEY);
    } catch (error) {}
  };
  const load = () => {
    try {
      return sessionStorage.getItem(KEY) || window.mieruDrawing;
    } catch (error) {
      return window.mieruDrawing;
    }
  };

  let drawing = isBack ? load() : null;
  const fit = () => {
    const box = canvas.getBoundingClientRect();
    const scale = window.devicePixelRatio || 1;
    const width = Math.round(box.width * scale);
    const height = Math.round(box.height * scale);
    if (width === 0 || (width === canvas.width && height === canvas.height)) return;
    canvas.width = width;
    canvas.height = height;
    if (drawing) {
      const image = new Image();
      image.onload = () => context.drawImage(image, 0, 0, canvas.width, canvas.height);
      image.src = drawing;
    }
  };
  fit();
  if (window.ResizeObserver) new ResizeObserver(fit).observe(canvas);

  if (isBack) {
    area.classList.add("mieru-answer");
    button.hidden = true;
    return;
  }

  save(null);
  let last = null;
  const pointAt = (event) => {
    const box = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - box.left) * canvas.width) / box.width,
      y: ((event.clientY - box.top) * canvas.height) / box.height,
    };
  };
  const strokeTo = (point) => {
    context.lineWidth = (LINE_WIDTH * canvas.width) / canvas.getBoundingClientRect().width;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.strokeStyle = getComputedStyle(canvas).color;
    context.beginPath();
    context.moveTo(last.x, last.y);
    context.lineTo(point.x, point.y);
    context.stroke();
    last = point;
  };
  canvas.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    fit();
    canvas.setPointerCapture(event.pointerId);
    last = pointAt(event);
    strokeTo(last);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (last === null) return;
    event.preventDefault();
    strokeTo(pointAt(event));
  });
  const end = () => {
    if (last === null) return;
    last = null;
    drawing = canvas.toDataURL();
    save(drawing);
  };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  button.addEventListener("click", () => {
    context.clearRect(0, 0, canvas.width, canvas.height);
    drawing = null;
    save(null);
    button.blur();
  });
})();
</script>"""

# The stroke order sits behind the canvas so the drawing can be laid over it. It is
# part of the front, where CSS hides it, because the back's copy of the canvas
# comes from {{FrontSide}}; the script reveals it there.
_DRAWING = (
    '<div class="mieru-drawing">\n'
    '<div class="mieru-surface">\n'
    f'<div class="mieru-guide">{{{{{STROKE_ORDER_FIELD}}}}}</div>\n'
    "<canvas></canvas>\n"
    "</div>\n"
    '<button type="button">Clear</button>\n'
    "</div>\n"
    f"{_DRAWING_SCRIPT}"
)

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
    (
        "Writing",
        f'<div class="picture">{_PICTURE}</div>\n{_AUDIO_ROW}\n{_DRAWING}',
        # The stroke order behind the drawing is the answer; the word stands in only
        # for notes added before stroke order existed. The empty #answer is also how
        # the drawing script knows it is on the back.
        f'{{{{FrontSide}}}}\n<div id="answer"></div>\n'
        f"{{{{^{STROKE_ORDER_FIELD}}}}}"
        f'<div class="heading">{_WORD}</div>'
        f"{{{{/{STROKE_ORDER_FIELD}}}}}\n"
        f"{_CONNECTION}",
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

.mieru-drawing {
  margin-top: 0.5em;
}

.mieru-surface {
  position: relative;
  max-width: 480px;
  margin: 0 auto;
}

.mieru-drawing canvas {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 3 / 2;
  /* An outline rather than a border, so the box pointers are mapped through is
     exactly the drawing surface. */
  outline: 1px solid rgba(128, 128, 128, 0.5);
  border-radius: 8px;
  touch-action: none;
}

.mieru-drawing button {
  margin-top: 0.4em;
  font-size: 16px;
}

.mieru-guide {
  display: none;
  position: absolute;
  inset: 0;
  justify-content: center;
  align-items: center;
  opacity: 0.7;
  pointer-events: none;
}

.mieru-answer .mieru-guide {
  display: flex;
}

.mieru-guide img {
  flex: 0 1 auto;
  min-width: 0;
  height: 100%;
  object-fit: contain;
  /* KanjiVG draws in black, like the pencil; this turns it red (#e5494d), which
     stands out from the pencil in light and night mode alike. */
  filter: brightness(0) invert(49%) sepia(82%) saturate(5914%) hue-rotate(338deg)
    brightness(101%) contrast(79%);
}

/* The word when it follows the picture and audio, on the production and writing backs. */
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
