"""
Elliot — Главное окно приложения.

Frameless окно 450×700 с кастомным title bar, чатом,
визуализацией голоса и кнопкой микрофона.
"""

from __future__ import annotations

import logging
import math
from typing import Final

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QSize,
    QTimer,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.chat_view import ChatView
from ui.widgets.status_indicator import StatusIndicator
from ui.widgets.waveform import VoiceWaveWidget

log = logging.getLogger(__name__)

_WINDOW_WIDTH: Final[int] = 450
_WINDOW_HEIGHT: Final[int] = 700
_MIC_BUTTON_SIZE: Final[int] = 56
_FPS_MIC_GLOW: Final[int] = 60


# ── Кнопка микрофона с анимацией ────────────────────────────────
class _MicButton(QPushButton):
    """Круглая кнопка микрофона с анимацией свечения."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("🎤", parent)
        self.setObjectName("micButton")
        self.setFixedSize(_MIC_BUTTON_SIZE, _MIC_BUTTON_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Ctrl+Space — начать/остановить запись")

        self._state: str = "idle"
        self._glow_phase: float = 0.0

        # Таймер для свечения при активных состояниях
        self._glow_timer = QTimer(self)
        self._glow_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._glow_timer.timeout.connect(self._tick_glow)

    def set_state(self, state: str) -> None:
        """Установить состояние кнопки (влияет на цвет и анимацию)."""
        self._state = state
        self.setProperty("state", state)
        # Перечитать стили
        self.style().unpolish(self)
        self.style().polish(self)

        if state in ("listening", "thinking", "speaking"):
            if not self._glow_timer.isActive():
                self._glow_timer.start(1000 // _FPS_MIC_GLOW)
        else:
            self._glow_timer.stop()
            # Убираем эффект
            self.setGraphicsEffect(None)

    def _tick_glow(self) -> None:
        """Обновление эффекта свечения."""
        self._glow_phase += 0.03
        pulse = 0.5 + 0.5 * math.sin(self._glow_phase * math.pi * 2)

        color_map = {
            "listening": QColor(0, 212, 255),
            "thinking":  QColor(124, 58, 237),
            "speaking":  QColor(34, 197, 94),
        }
        color = color_map.get(self._state, QColor(0, 212, 255))
        color.setAlpha(int(80 + 80 * pulse))

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(int(15 + 10 * pulse))
        shadow.setOffset(0, 0)
        shadow.setColor(color)
        self.setGraphicsEffect(shadow)


# ── Кастомный Title Bar ─────────────────────────────────────────
class _TitleBar(QWidget):
    """Кастомный title bar с перетаскиванием окна."""

    def __init__(self, main_window: QMainWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(40)
        self._window = main_window
        self._drag_pos: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        # Иконка / название
        self._title = QLabel("Elliot", self)
        self._title.setObjectName("titleLabel")
        layout.addWidget(self._title)

        layout.addStretch()

        # Кнопка сворачивания
        btn_min = QPushButton("─", self)
        btn_min.setObjectName("btnMinimize")
        btn_min.clicked.connect(main_window.showMinimized)
        layout.addWidget(btn_min)

        # Кнопка закрытия (скрыть в трей)
        btn_close = QPushButton("✕", self)
        btn_close.setObjectName("btnClose")
        btn_close.clicked.connect(main_window.close)
        layout.addWidget(btn_close)

    # ── Перетаскивание окна ─────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_pos = None
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Двойной клик — свернуть/развернуть."""
        event.accept()


# ── Главное окно ────────────────────────────────────────────────
class MainWindow(QMainWindow):
    """
    Главное окно голосового ассистента Elliot.

    Frameless, 450×700, тёмная тема.
    """

    # ── Сигналы → Controller ────────────────────────────────────
    mic_toggled = pyqtSignal()             # Нажатие кнопки микрофона
    text_submitted = pyqtSignal(str)       # Отправка текста через input

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Elliot")
        self.setFixedSize(_WINDOW_WIDTH, _WINDOW_HEIGHT)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._hide_to_tray: bool = True  # Закрытие → в трей

        self._build_ui()
        log.info("MainWindow создано (%dx%d)", _WINDOW_WIDTH, _WINDOW_HEIGHT)

    # ── Построение интерфейса ───────────────────────────────────
    def _build_ui(self) -> None:
        """Собрать все виджеты."""
        # Центральный виджет с фоном и скруглёнными углами
        central = QWidget(self)
        central.setObjectName("centralWidget")
        central.setStyleSheet(
            "#centralWidget {"
            "  background-color: #0f0f23;"
            "  border: 1px solid #2a2a4a;"
            "  border-radius: 12px;"
            "}"
        )
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 1. Title Bar
        self._title_bar = _TitleBar(self)
        root.addWidget(self._title_bar)

        # Статус-индикатор под title bar
        status_row = QHBoxLayout()
        status_row.setContentsMargins(16, 0, 16, 4)
        self._status = StatusIndicator()
        status_row.addWidget(self._status)
        status_row.addStretch()
        root.addLayout(status_row)

        # Разделитель
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #1e1e3f; max-height: 1px;")
        root.addWidget(sep)

        # 2. Chat View (основная область)
        self._chat = ChatView()
        root.addWidget(self._chat, 1)  # stretch=1

        # 3. Waveform
        self._waveform = VoiceWaveWidget()
        root.addWidget(self._waveform)

        # 4. Нижняя панель
        bottom = QWidget()
        bottom.setObjectName("bottomPanel")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(12, 8, 12, 12)
        bottom_layout.setSpacing(10)

        # Текстовое поле ввода
        self._text_input = QLineEdit()
        self._text_input.setObjectName("textInput")
        self._text_input.setPlaceholderText("Введите сообщение...")
        self._text_input.returnPressed.connect(self._on_text_submit)
        bottom_layout.addWidget(self._text_input, 1)

        # Кнопка микрофона
        self._mic_btn = _MicButton()
        self._mic_btn.clicked.connect(self._on_mic_clicked)
        bottom_layout.addWidget(self._mic_btn)

        root.addWidget(bottom)

        # Баннер ошибок (скрыт по умолчанию)
        self._error_banner = QLabel()
        self._error_banner.setObjectName("errorBanner")
        self._error_banner.setWordWrap(True)
        self._error_banner.setVisible(False)
        root.addWidget(self._error_banner)

    # ── Обработчики UI-действий ─────────────────────────────────
    def _on_mic_clicked(self) -> None:
        """Нажатие кнопки микрофона."""
        self.mic_toggled.emit()

    def _on_text_submit(self) -> None:
        """Отправка текста через Enter."""
        text = self._text_input.text().strip()
        if text:
            self._text_input.clear()
            self.text_submitted.emit(text)

    # ── Слоты для AppController (worker → UI) ──────────────────
    @pyqtSlot(str)
    def on_state_changed(self, state: str) -> None:
        """Обновить UI при смене состояния ассистента."""
        self._status.set_state(state)
        self._mic_btn.set_state(state)

        if state == "idle":
            self._waveform.set_amplitude(0.0)
        log.debug("Состояние: %s", state)

    @pyqtSlot(float)
    def on_audio_level(self, level: float) -> None:
        """Обновить визуализацию уровня громкости."""
        self._waveform.set_amplitude(level)

    @pyqtSlot(str)
    def on_user_text(self, text: str) -> None:
        """Показать распознанный текст пользователя в чате."""
        # Если текст был введён вручную, он уже добавлен в _on_text_submit
        # Для голосового ввода добавляем здесь
        self._chat.add_user_message(text)

    @pyqtSlot(str)
    def on_assistant_text(self, text: str) -> None:
        """Показать ответ ассистента в чате."""
        self._chat.add_assistant_message(text)

    @pyqtSlot(str, str)
    def on_tool_executed(self, tool_name: str, result: str) -> None:
        """Показать результат выполнения инструмента."""
        self._chat.add_tool_message(tool_name, result)

    @pyqtSlot(str)
    def on_error(self, message: str) -> None:
        """Показать сообщение об ошибке."""
        log.error("UI Error: %s", message)
        self._error_banner.setText(f"⚠ {message}")
        self._error_banner.setVisible(True)

        # Автоскрытие через 8 секунд
        QTimer.singleShot(8000, lambda: self._error_banner.setVisible(False))

    # ── Переопределения окна ────────────────────────────────────
    def closeEvent(self, event) -> None:  # noqa: N802
        """Закрытие окна → сворачивание в трей."""
        if self._hide_to_tray:
            event.ignore()
            self.hide()
            log.info("Окно скрыто в трей")
        else:
            event.accept()

    def set_allow_close(self, allow: bool) -> None:
        """Разрешить реальное закрытие окна (при выходе через трей)."""
        self._hide_to_tray = not allow

    # ── Доступ к виджетам (для Controller) ──────────────────────
    @property
    def chat_view(self) -> ChatView:
        return self._chat

    @property
    def waveform(self) -> VoiceWaveWidget:
        return self._waveform

    @property
    def status_indicator(self) -> StatusIndicator:
        return self._status
