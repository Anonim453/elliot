"""
Elliot — Виджет визуализации голосовых волн.

Три наложенные синусоиды с неоновым свечением, огибающая Гаусса,
плавная анимация 60 FPS.
"""

from __future__ import annotations

import math
import time
from typing import Final

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget


# ── Параметры волн ──────────────────────────────────────────────
_WAVE_CONFIGS: Final = [
    # (цвет,         альфа, частота_множитель, фаза_сдвиг, скорость)
    ("#00d4ff",      180,   1.0,               0.0,        2.0),   # Голубой
    ("#7c3aed",      120,   1.6,               1.0,        2.8),   # Фиолетовый
    ("#06b6d4",      100,   2.3,               2.0,        3.5),   # Бирюзовый
]

_FPS: Final[int] = 60
_LERP_FACTOR: Final[float] = 0.08            # Скорость сглаживания амплитуды
_BASE_FREQUENCY: Final[float] = 0.02         # Базовая пространственная частота
_BASE_AMPLITUDE_PX: Final[float] = 28.0      # Макс. амплитуда в пикселях
_IDLE_AMPLITUDE: Final[float] = 0.05         # Минимальная «дыхательная» амплитуда
_GLOW_RADIUS: Final[int] = 6                 # Ширина свечения линий


class VoiceWaveWidget(QWidget):
    """Виджет визуализации голосовой волны с тремя синусоидами."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("waveformWidget")
        self.setMinimumHeight(80)
        self.setMaximumHeight(100)

        # ── Состояние анимации ──
        self._target_amplitude: float = 0.0   # Целевая амплитуда (0..1)
        self._current_amplitude: float = 0.0  # Текущая (сглажённая)
        self._start_time: float = time.monotonic()

        # ── Таймер отрисовки ──
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // _FPS)

    # ── Публичный API ───────────────────────────────────────────
    def set_amplitude(self, value: float) -> None:
        """Установить целевую амплитуду (0.0 — тишина, 1.0 — максимум)."""
        self._target_amplitude = max(0.0, min(1.0, value))

    # ── Внутренние методы ───────────────────────────────────────
    def _tick(self) -> None:
        """Обновление кадра анимации."""
        # lerp к целевой амплитуде
        self._current_amplitude += (
            (self._target_amplitude - self._current_amplitude) * _LERP_FACTOR
        )
        self.update()

    @staticmethod
    def _gaussian_envelope(x_norm: float) -> float:
        """Огибающая Гаусса: затухание к краям (x_norm ∈ [0, 1])."""
        # Центр — 0.5, σ ~ 0.22
        return math.exp(-((x_norm - 0.5) ** 2) / (2 * 0.22 ** 2))

    def paintEvent(self, event) -> None:  # noqa: N802
        """Отрисовка волн."""
        w = self.width()
        h = self.height()
        if w < 2 or h < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        elapsed = time.monotonic() - self._start_time
        mid_y = h / 2.0
        amp = max(self._current_amplitude, _IDLE_AMPLITUDE)

        for color_hex, alpha, freq_mult, phase_offset, speed in _WAVE_CONFIGS:
            base_color = QColor(color_hex)
            # Яркость свечения зависит от амплитуды
            effective_alpha = int(alpha * min(1.0, amp * 2.5))
            base_color.setAlpha(effective_alpha)

            path = QPainterPath()
            first_point = True

            step = max(1, w // 200)  # Количество точек
            for px in range(0, w + step, step):
                x_norm = px / w
                envelope = self._gaussian_envelope(x_norm)

                # Суперпозиция: основная + гармоника
                angle = (px * _BASE_FREQUENCY * freq_mult
                         + elapsed * speed + phase_offset)
                y_offset = (
                    math.sin(angle) * 0.7
                    + math.sin(angle * 2.1 + 0.5) * 0.3
                )
                y = mid_y + y_offset * _BASE_AMPLITUDE_PX * amp * envelope

                if first_point:
                    path.moveTo(float(px), y)
                    first_point = False
                else:
                    path.lineTo(float(px), y)

            # Свечение (широкая полупрозрачная линия)
            if amp > _IDLE_AMPLITUDE + 0.01:
                glow_color = QColor(base_color)
                glow_color.setAlpha(max(10, effective_alpha // 3))
                glow_pen = QPen(glow_color, _GLOW_RADIUS, Qt.PenStyle.SolidLine)
                glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(glow_pen)
                painter.drawPath(path)

            # Основная линия
            pen = QPen(base_color, 2.0, Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)

        painter.end()
