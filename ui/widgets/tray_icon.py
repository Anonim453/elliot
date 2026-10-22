"""
Elliot — Иконка в системном трее.

Контекстное меню, двойной клик для показа/скрытия окна,
уведомления через showMessage.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow

log = logging.getLogger(__name__)


def _create_elliot_icon() -> QIcon:
    """Создать программную иконку «E» для трея (без внешних файлов)."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))  # прозрачный фон

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Круг
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#7c3aed"))
    painter.drawEllipse(2, 2, size - 4, size - 4)

    # Буква «E»
    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", 30, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "E")
    painter.end()

    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    """Иконка Elliot в системном трее с контекстным меню."""

    def __init__(self, main_window: QMainWindow) -> None:
        super().__init__(_create_elliot_icon(), main_window)
        self._window = main_window

        self._build_menu()
        self.activated.connect(self._on_activated)
        self.setToolTip("Elliot — голосовой ассистент")

        log.info("Иконка в трее создана")

    # ── Меню ────────────────────────────────────────────────────
    def _build_menu(self) -> None:
        """Построить контекстное меню трея."""
        menu = QMenu()

        self._action_toggle = QAction("Скрыть", self)
        self._action_toggle.triggered.connect(self._toggle_window)
        menu.addAction(self._action_toggle)

        menu.addSeparator()

        action_about = QAction("О программе", self)
        action_about.triggered.connect(self._show_about)
        menu.addAction(action_about)

        menu.addSeparator()

        action_quit = QAction("Выход", self)
        action_quit.triggered.connect(self._quit)
        menu.addAction(action_quit)

        self.setContextMenu(menu)

    # ── Обработчики ─────────────────────────────────────────────
    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Двойной клик — показать/скрыть окно."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window()

    def _toggle_window(self) -> None:
        """Показать или скрыть главное окно."""
        if self._window.isVisible():
            self._window.hide()
            self._action_toggle.setText("Показать")
        else:
            self._window.showNormal()
            self._window.activateWindow()
            self._action_toggle.setText("Скрыть")

    def _show_about(self) -> None:
        """Показать уведомление «О программе»."""
        self.showMessage(
            "Elliot",
            "Голосовой ИИ-ассистент v0.1\nPowered by Gemini + Whisper",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _quit(self) -> None:
        """Полный выход из приложения."""
        log.info("Выход из приложения через трей")
        if hasattr(self._window, "set_allow_close"):
            self._window.set_allow_close(True)
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.quit()

    def notify(self, title: str, message: str, duration_ms: int = 3000) -> None:
        """Показать произвольное уведомление."""
        self.showMessage(
            title, message,
            QSystemTrayIcon.MessageIcon.Information,
            duration_ms,
        )
