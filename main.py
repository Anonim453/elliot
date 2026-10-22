"""
Elliot — Главная точка входа в приложение голосового ИИ-помощника.

Запуск GUI на PyQt6, инициализация фонового worker-потока,
подключение глобальных горячих клавиш и иконки в трее.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication

# Добавляем корневую директорию проекта в sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from ui.controller import AppController
from ui.main_window import MainWindow
from ui.widgets.tray_icon import TrayIcon

# ── Настройка логирования ───────────────────────────────────────
logs_dir = PROJECT_ROOT / "logs"
logs_dir.mkdir(exist_ok=True)
log_file = logs_dir / "elliot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
log = logging.getLogger("elliot")


class HotkeyBridge(QObject):
    """Потокобезопасный мост для глобальных хоткеев Windows."""
    hotkey_triggered = pyqtSignal()


def setup_global_hotkey(hotkey_str: str, callback_signal: pyqtSignal) -> None:
    """Регистрация глобального хоткея через модуль keyboard."""
    try:
        import keyboard

        def _on_press():
            callback_signal.emit()

        keyboard.add_hotkey(hotkey_str, _on_press)
        log.info("Глобальная горячая клавиша зарегистрирована: %s", hotkey_str)
    except Exception as e:
        log.warning("Не удалось зарегистрировать глобальный хоткей '%s': %s", hotkey_str, e)


def load_stylesheet(app: QApplication) -> None:
    """Загрузить и применить QSS-стили к приложению."""
    qss_path = PROJECT_ROOT / "assets" / "styles" / "dark_theme.qss"
    if qss_path.exists():
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                stylesheet = f.read()
            app.setStyleSheet(stylesheet)
            log.info("Стили dark_theme.qss успешно применены")
        except Exception as e:
            log.warning("Ошибка загрузки стилей: %s", e)
    else:
        log.warning("Файл стилей не найден: %s", qss_path)


def main() -> int:
    """Главная функция запуска приложения."""
    log.info("Запуск голосового ассистента Elliot...")

    # Проверка настроек и API ключа
    settings = get_settings()
    if not settings.GEMINI_API_KEY or "your_gemini_api_key_here" in settings.GEMINI_API_KEY:
        log.warning(
            "ВНИМАНИЕ: GEMINI_API_KEY не задан в .env файле! "
            "Получите бесплатный ключ на https://aistudio.google.com/apikey"
        )

    # Инициализация Qt приложения
    app = QApplication(sys.argv)
    app.setApplicationName("Elliot")
    app.setApplicationDisplayName("Elliot Voice Assistant")
    app.setQuitOnLastWindowClosed(False)

    # Применение темы
    load_stylesheet(app)

    # Создание окна и контроллера
    main_window = MainWindow()
    controller = AppController(main_window)
    tray = TrayIcon(main_window)
    tray.show()

    # Глобальный хоткей для активации микрофона (Ctrl+Space)
    hotkey_bridge = HotkeyBridge()
    hotkey_bridge.hotkey_triggered.connect(main_window.mic_toggled)
    setup_global_hotkey(settings.HOTKEY, hotkey_bridge.hotkey_triggered)

    # Корректное завершение при выходе
    def _cleanup():
        log.info("Завершение приложения...")
        try:
            import keyboard
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        controller.shutdown()

    app.aboutToQuit.connect(_cleanup)

    # Запуск фонового потока ядра и показ окна
    controller.start()
    main_window.show()

    log.info("Elliot готов к работе!")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
