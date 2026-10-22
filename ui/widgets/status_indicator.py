"""
Elliot — Индикатор текущего состояния ассистента.

Цветная точка + текстовая метка с анимацией пульсации / вращения.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Final

from PyQt6.QtCore import (
    QPropertyAnimation,
    QTimer,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


# ── Состояния ───────────────────────────────────────────────────
class AssistantState(Enum):
    """Перечисление состояний ассистента."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


_STATE_META: Final[dict[AssistantState, tuple[str, str]]] = {
    AssistantState.IDLE:      ("#64748b", "Нажмите Ctrl+Space"),
    AssistantState.LISTENING: ("#00d4ff", "Слушаю..."),
    AssistantState.THINKING:  ("#7c3aed", "Думаю..."),
    AssistantState.SPEAKING:  ("#22c55e", "Отвечаю..."),
}

_DOT_SIZE: Final[int] = 10
_FPS: Final[int] = 60


class _DotWidget(QWidget):
    """Виджет цветной точки-индикатора с анимацией."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 20)

        self._color = QColor("#64748b")
        self._pulse_phase: float = 0.0     # 0..1 для пульсации
        self._spin_angle: float = 0.0      # Угол вращения (thinking)
        self._state = AssistantState.IDLE

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // _FPS)

    # ── Анимация ────────────────────────────────────────────────
    def _tick(self) -> None:
        dt = 1.0 / _FPS
        if self._state == AssistantState.LISTENING:
            self._pulse_phase = (self._pulse_phase + dt * 2.0) % 1.0
        elif self._state == AssistantState.THINKING:
            self._spin_angle = (self._spin_angle + dt * 360.0) % 360.0
        self.update()

    def set_state(self, state: AssistantState) -> None:
        """Переключить состояние индикатора."""
        self._state = state
        color_hex, _ = _STATE_META[state]
        self._color = QColor(color_hex)
        self._pulse_phase = 0.0
        self._spin_angle = 0.0

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx, cy = self.width() / 2.0, self.height() / 2.0
        r = _DOT_SIZE / 2.0

        if self._state == AssistantState.LISTENING:
            # Пульсирующее кольцо
            pulse = 0.5 + 0.5 * math.sin(self._pulse_phase * 2 * math.pi)
            ring_r = r + 3.0 * pulse
            ring_color = QColor(self._color)
            ring_color.setAlpha(int(80 * (1.0 - pulse)))
            pen = QPen(ring_color, 2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                int(cx - ring_r), int(cy - ring_r),
                int(ring_r * 2), int(ring_r * 2),
            )

        if self._state == AssistantState.THINKING:
            # Вращающаяся дуга
            arc_color = QColor(self._color)
            arc_color.setAlpha(140)
            pen = QPen(arc_color, 2.0, Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            arc_r = r + 3
            rect_x = cx - arc_r
            rect_y = cy - arc_r
            start_angle = int(self._spin_angle * 16)
            span_angle = 120 * 16
            from PyQt6.QtCore import QRectF
            painter.drawArc(
                QRectF(rect_x, rect_y, arc_r * 2, arc_r * 2),
                start_angle, span_angle,
            )

        # Точка
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(
            int(cx - r), int(cy - r),
            int(r * 2), int(r * 2),
        )

        painter.end()


class StatusIndicator(QWidget):
    """Виджет-индикатор состояния ассистента (точка + текст)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusIndicator")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = _DotWidget(self)
        layout.addWidget(self._dot)

        self._label = QLabel(_STATE_META[AssistantState.IDLE][1], self)
        self._label.setObjectName("statusText")
        layout.addWidget(self._label)

        self._state = AssistantState.IDLE

    # ── Публичный API ───────────────────────────────────────────
    def set_state(self, state_str: str) -> None:
        """Установить состояние по строке ('idle', 'listening' и т.д.)."""
        try:
            state = AssistantState(state_str)
        except ValueError:
            state = AssistantState.IDLE

        self._state = state
        self._dot.set_state(state)
        _, text = _STATE_META[state]
        self._label.setText(text)

    @property
    def current_state(self) -> AssistantState:
        return self._state
