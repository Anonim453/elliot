"""
Elliot — Чат-виджет с пузырями сообщений.

Отображает диалог: пузыри пользователя (справа), ассистента (слева),
уведомления о вызове инструментов (по центру).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QTimer,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)

_MAX_BUBBLE_WIDTH: Final[int] = 300
_ANIMATION_DURATION: Final[int] = 300  # мс


# ── Вспомогательные виджеты ─────────────────────────────────────
class _AvatarLabel(QLabel):
    """Круглый аватар с буквой «E»."""

    def __init__(self, letter: str = "E", parent: QWidget | None = None) -> None:
        super().__init__(letter, parent)
        self.setObjectName("avatarLabel")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(30, 30)


class _BubbleFrame(QFrame):
    """Базовый фрейм-пузырь сообщения."""

    def __init__(
        self,
        object_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMaximumWidth(_MAX_BUBBLE_WIDTH)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum,
        )

        self._inner = QVBoxLayout(self)
        self._inner.setContentsMargins(0, 0, 0, 0)
        self._inner.setSpacing(4)

    def add_text(self, text: str, object_name: str = "bubbleText") -> QLabel:
        """Добавить текстовую метку в пузырь."""
        label = QLabel(text, self)
        label.setObjectName(object_name)
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._inner.addWidget(label)
        return label

    def add_timestamp(self) -> None:
        """Добавить метку времени."""
        now = datetime.now().strftime("%H:%M")
        ts = QLabel(now, self)
        ts.setObjectName("timestampLabel")
        ts.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._inner.addWidget(ts)


def _fade_in(widget: QWidget) -> None:
    """Анимация появления (fade-in) для виджета."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(_ANIMATION_DURATION)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


# ── ChatView ────────────────────────────────────────────────────
class ChatView(QScrollArea):
    """Область прокручиваемого диалога с пузырями."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatView")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.setFrameShape(QFrame.Shape.NoFrame)

        # Контейнер
        self._container = QWidget()
        self._container.setObjectName("chatContainer")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(10)
        self._layout.addStretch()  # «пружина» сверху — сообщения прижаты вниз

        self.setWidget(self._container)

    # ── Публичный API ───────────────────────────────────────────
    def add_user_message(self, text: str) -> None:
        """Добавить сообщение пользователя (справа, цветной градиент)."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        row.addStretch()  # Прижимаем вправо

        bubble = _BubbleFrame("userBubble")
        bubble.add_text(text)
        bubble.add_timestamp()
        row.addWidget(bubble)

        self._append_row(row, bubble)
        log.debug("Сообщение пользователя добавлено: %s", text[:40])

    def add_assistant_message(self, text: str) -> None:
        """Добавить сообщение ассистента (слева, тёмный фон + аватар)."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        avatar = _AvatarLabel("E")
        row.addWidget(avatar, 0, Qt.AlignmentFlag.AlignBottom)

        bubble = _BubbleFrame("assistantBubble")
        bubble.add_text(text)
        bubble.add_timestamp()
        row.addWidget(bubble)

        row.addStretch()  # Прижимаем влево

        self._append_row(row, bubble)
        log.debug("Ответ ассистента добавлен: %s", text[:40])

    def add_tool_message(self, tool_name: str, result: str) -> None:
        """Добавить уведомление об инструменте (по центру, компактное)."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        row.addStretch()

        bubble = _BubbleFrame("toolBubble")
        bubble.setMaximumWidth(350)
        tool_text = f"⚙️ {tool_name}"
        bubble.add_text(tool_text, "toolText")
        if result:
            # Ограничиваем длину результата
            short = result[:120] + ("…" if len(result) > 120 else "")
            bubble.add_text(short, "toolText")

        row.addWidget(bubble)
        row.addStretch()

        self._append_row(row, bubble)
        log.debug("Инструмент: %s", tool_name)

    def clear(self) -> None:
        """Очистить весь чат."""
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    # ── Внутренние методы ───────────────────────────────────────
    def _append_row(self, row_layout: QHBoxLayout, animate_widget: QWidget) -> None:
        """Добавить строку сообщения в конец и прокрутить вниз."""
        # Вставляем перед последним stretch
        index = self._layout.count() - 1
        self._layout.insertLayout(index, row_layout)

        # Fade-in анимация
        _fade_in(animate_widget)

        # Автоскролл (с небольшой задержкой, чтобы layout обновился)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        """Прокрутить чат до самого конца."""
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    @staticmethod
    def _clear_layout(layout) -> None:
        """Рекурсивно очистить layout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                ChatView._clear_layout(item.layout())
