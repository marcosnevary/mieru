"""List widgets of the mieru window, painted by hand where Qt's defaults fall short."""

from __future__ import annotations

from aqt.qt import (
    QAbstractItemView,
    QColor,
    QEvent,
    QFont,
    QFontMetrics,
    QListView,
    QListWidget,
    QListWidgetItem,
    QModelIndex,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPoint,
    QRect,
    QRectF,
    QSize,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    Qt,
    QWidget,
)

from ..core.dictionary import Candidate

_MEANINGS_SHOWN = 3
_ROWS_SHOWN = 3
_WORD_SCALE = 1.5
_ROW_PADDING = QSize(8, 6)
_LINE_GAP = 2
_PART_GAP = 10
_SECONDARY_OPACITY = 0.6

_THUMBNAIL_SIZE = QSize(150, 150)
_CELL_PADDING = 8
_SELECTION_WIDTH = 3


class CandidateList(QListWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setItemDelegate(_CandidateDelegate(self))
        self.setMinimumHeight(_ROWS_SHOWN * _row_height(self.font()) + 2 * self.frameWidth())

    def add_candidate(self, candidate: Candidate) -> None:
        item = QListWidgetItem(candidate.word)
        item.setData(Qt.ItemDataRole.UserRole, candidate)
        self.addItem(item)


class _CandidateDelegate(QStyledItemDelegate):
    """The word large, then its reading and meanings in a quieter color."""

    def paint(
        self, painter: QPainter | None, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        assert painter is not None
        candidate: Candidate = index.data(Qt.ItemDataRole.UserRole)
        palette = option.palette
        if option.state & QStyle.StateFlag.State_Selected:
            # Active even when the list loses focus: the highlight marks the word
            # that goes on the card, and the inactive macOS one is unreadable.
            painter.fillRect(
                option.rect, palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)
            )
            primary = secondary = palette.color(
                QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText
            )
        else:
            primary = palette.color(QPalette.ColorRole.Text)
            secondary = QColor(primary)
            secondary.setAlphaF(_SECONDARY_OPACITY)
        fonts = _CandidateFonts(option.font)
        area = option.rect.adjusted(
            _ROW_PADDING.width(), _ROW_PADDING.height(), -_ROW_PADDING.width(), 0
        )

        painter.save()
        baseline = area.top() + fonts.word_metrics.ascent()
        x = area.left()
        for text, font, color in _first_line_parts(candidate, fonts, primary, secondary):
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(QPoint(x, baseline), text)
            x += QFontMetrics(font).horizontalAdvance(text) + _PART_GAP

        meanings = "; ".join(candidate.meanings[:_MEANINGS_SHOWN])
        painter.setFont(fonts.base)
        painter.setPen(secondary)
        painter.drawText(
            QPoint(
                area.left(),
                area.top() + fonts.word_metrics.height() + _LINE_GAP + fonts.base_metrics.ascent(),
            ),
            fonts.base_metrics.elidedText(meanings, Qt.TextElideMode.ElideRight, area.width()),
        )
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(0, _row_height(option.font))


def _row_height(font: QFont) -> int:
    fonts = _CandidateFonts(font)
    return (
        2 * _ROW_PADDING.height()
        + fonts.word_metrics.height()
        + _LINE_GAP
        + fonts.base_metrics.height()
    )


class _CandidateFonts:
    def __init__(self, base: QFont) -> None:
        self.base = base
        self.word = _scaled(base, _WORD_SCALE)
        self.base_metrics = QFontMetrics(self.base)
        self.word_metrics = QFontMetrics(self.word)


def _first_line_parts(
    candidate: Candidate, fonts: _CandidateFonts, primary: QColor, secondary: QColor
) -> list[tuple[str, QFont, QColor]]:
    parts = [(candidate.word, fonts.word, primary)]
    # Kana-only words have the reading as their word; showing it twice is noise.
    if candidate.reading != candidate.word:
        parts.append((candidate.reading, fonts.base, secondary))
    return parts


def _scaled(font: QFont, scale: float) -> QFont:
    scaled = QFont(font)
    scaled.setPointSizeF(font.pointSizeF() * scale)
    return scaled


class PictureGrid(QListWidget):
    """Thumbnails in equal columns that span the whole width, so the grid stays
    centered instead of leaving a gap on the right. Several can be selected."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._delegate = _PictureDelegate(self)
        self.setItemDelegate(self._delegate)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def add_picture(self, thumbnail: QPixmap, tooltip: str) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
        item.setToolTip(tooltip)
        self.addItem(item)

    def selected_rows(self) -> list[int]:
        return sorted(index.row() for index in self.selectedIndexes())

    def select_rows(self, rows: list[int]) -> None:
        self.clearSelection()
        for row in rows:
            item = self.item(row)
            if item is not None:
                item.setSelected(True)

    def viewportEvent(self, event: QEvent | None) -> bool:
        # The viewport also narrows when the scroll bar appears, which the
        # widget's own resize event doesn't report.
        if event is not None and event.type() == QEvent.Type.Resize:
            self._fit_columns()
        return super().viewportEvent(event)

    def _fit_columns(self) -> None:
        width = self.viewport().width()  # type: ignore[union-attr]
        columns = max(1, width // _PictureDelegate.min_cell_width)
        cell_width = max(_PictureDelegate.min_cell_width, width // columns)
        if cell_width != self._delegate.cell_width:
            self._delegate.cell_width = cell_width
            self.scheduleDelayedItemsLayout()


class _PictureDelegate(QStyledItemDelegate):
    """Centers each thumbnail in its cell and frames the selected one: Qt's icon
    mode highlights the (empty) caption area instead of the picture."""

    min_cell_width = _THUMBNAIL_SIZE.width() + 2 * _CELL_PADDING

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.cell_width = self.min_cell_width

    def paint(
        self, painter: QPainter | None, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        assert painter is not None
        frame = QRect(QPoint(), _THUMBNAIL_SIZE)
        frame.moveCenter(option.rect.center())
        thumbnail = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(thumbnail, QPixmap) and not thumbnail.isNull():
            size = thumbnail.size()
            if size.width() > frame.width() or size.height() > frame.height():
                size = size.scaled(frame.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRect(QPoint(), size)
            target.moveCenter(frame.center())
            painter.drawPixmap(target, thumbnail)
            frame = target

        if option.state & QStyle.StateFlag.State_Selected:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            # Active even when the grid loses focus: the frame marks the picture
            # that goes on the card, not keyboard focus.
            color = option.palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)
            painter.setPen(QPen(color, _SELECTION_WIDTH))
            offset = _SELECTION_WIDTH
            painter.drawRoundedRect(QRectF(frame).adjusted(-offset, -offset, offset, offset), 4, 4)
            painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(self.cell_width, _THUMBNAIL_SIZE.height() + 2 * _CELL_PADDING)
