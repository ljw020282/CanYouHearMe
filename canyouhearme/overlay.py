"""Command-bar overlay: input, phrase list, pin, status."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

BAR_STYLE = """
QWidget#Root {
    background: #1c1710;
    border: 1px solid #8a6a28;
    border-radius: 8px;
}
QLineEdit, QComboBox {
    background: #2a2218;
    color: #f3e6c8;
    border: 1px solid #6b5428;
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: #8a6a28;
}
QComboBox QAbstractItemView {
    background: #2a2218;
    color: #f3e6c8;
    selection-background-color: #8a6a28;
}
QPushButton {
    background: #3a2e1c;
    color: #e8d5a3;
    border: 1px solid #8a6a28;
    border-radius: 4px;
    padding: 4px 10px;
}
QPushButton:hover { background: #4a3a24; }
QPushButton:checked {
    background: #8a6a28;
    color: #1c1710;
}
QLabel#Hint {
    color: #a89468;
    font-size: 11px;
}
"""


class StatusDot(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._color = QColor("#6b7c4a")
        self.setToolTip("待命")

    def set_state(self, state: str) -> None:
        colors = {
            "idle": ("#6b7c4a", "待命"),
            "cached": ("#3dcc6d", "命中缓存"),
            "generating": ("#e6c84a", "正在合成"),
            "timeout": ("#d98a3a", "合成超过 5 秒"),
            "playing": ("#3dcc6d", "播放中"),
            "error": ("#c45c4a", "出错"),
        }
        hex_color, tip = colors.get(state, ("#6b7c4a", state))
        self._color = QColor(hex_color)
        self.setToolTip(tip)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 10, 10)


class OverlayBar(QWidget):
    speak_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    pin_changed = pyqtSignal(bool)
    moved_to = pyqtSignal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Root")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(BAR_STYLE)
        self._drag: QPoint | None = None

        self.dot = StatusDot()
        self.pin_btn = QPushButton("钉住")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(True)
        self.pin_btn.setToolTip("城里钉住；开战后取消，说完自动收起")
        self.input = QLineEdit()
        self.input.setPlaceholderText("打字，回车朗读；空则读常用语")
        self.phrases = QComboBox()
        self.phrases.setMinimumWidth(220)
        self.speak_btn = QPushButton("说")
        self.settings_btn = QPushButton("设置")
        hint = QLabel("Caps 显隐 · Alt+Caps 说/停")
        hint.setObjectName("Hint")

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(8)
        row.addWidget(self.dot)
        row.addWidget(self.pin_btn)
        row.addWidget(self.input, 1)
        row.addWidget(self.phrases)
        row.addWidget(self.speak_btn)
        row.addWidget(self.settings_btn)
        row.addWidget(hint)

        self.pin_btn.toggled.connect(self._on_pin)
        self.speak_btn.clicked.connect(self.speak_requested.emit)
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        self.input.returnPressed.connect(self.speak_requested.emit)
        self.setFixedHeight(52)
        self.setMinimumWidth(780)

    def _on_pin(self, on: bool) -> None:
        self.pin_btn.setText("钉住" if on else "收起")
        self.pin_changed.emit(on)

    def set_phrases(self, phrases: list[str]) -> None:
        current = self.phrases.currentText()
        self.phrases.blockSignals(True)
        self.phrases.clear()
        self.phrases.addItems(phrases)
        idx = self.phrases.findText(current)
        if idx >= 0:
            self.phrases.setCurrentIndex(idx)
        self.phrases.blockSignals(False)

    def draft_text(self) -> str:
        typed = self.input.text().strip()
        if typed:
            return typed
        return self.phrases.currentText().strip()

    def clear_input(self) -> None:
        self.input.clear()

    def set_status(self, state: str) -> None:
        self.dot.set_state(state)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._drag is not None:
            self._drag = None
            self.moved_to.emit(self.x(), self.y())
        super().mouseReleaseEvent(event)
