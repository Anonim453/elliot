"""
Elliot — Контроллер приложения.

Связующий слой между MainWindow и AssistantWorker.
Создаёт QThread, перемещает worker, подключает сигналы.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QThread, pyqtSlot

if TYPE_CHECKING:
    from ui.main_window import MainWindow

from ui.workers.assistant_worker import AssistantWorker

log = logging.getLogger(__name__)


class AppController(QObject):
    """
    Контроллер приложения Elliot.

    Управляет жизненным циклом worker-потока и связывает
    сигналы между worker и UI-виджетами.
    """

    def __init__(self, main_window: MainWindow, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._window = main_window

        # ── Создаём поток и worker ──
        self._thread = QThread(self)
        self._thread.setObjectName("AssistantThread")

        self._worker = AssistantWorker()
        self._worker.moveToThread(self._thread)

        # ── Подключаем сигналы жизненного цикла ──
        self._thread.started.connect(self._worker.initialize)
        self._thread.finished.connect(self._worker.cleanup)
        self._thread.finished.connect(self._thread.deleteLater)

        # ── Подключаем worker → UI ──
        self._connect_worker_to_ui()

        # ── Подключаем UI → worker ──
        self._connect_ui_to_worker()

        log.info("AppController создан")

    # ── Запуск / остановка ──────────────────────────────────────
    def start(self) -> None:
        """Запустить worker-поток."""
        log.info("Запуск worker-потока...")
        self._thread.start()

    def shutdown(self) -> None:
        """Корректно остановить worker-поток."""
        log.info("Остановка worker-потока...")

        # Останавливаем прослушивание
        if self._worker:
            self._worker.stop_listening()
            self._worker.cleanup()

        # Завершаем поток
        self._thread.quit()
        if not self._thread.wait(5000):
            log.warning("Поток не завершился за 5 секунд, принудительное завершение")
            self._thread.terminate()
            self._thread.wait()

        log.info("Worker-поток остановлен")

    # ── Подключение сигналов ────────────────────────────────────
    def _connect_worker_to_ui(self) -> None:
        """Связать сигналы worker → виджеты главного окна."""
        w = self._worker
        win = self._window

        # Состояние ассистента → индикатор + кнопка микрофона + waveform
        w.state_changed.connect(win.on_state_changed)

        # Уровень звука → waveform
        w.audio_level.connect(win.on_audio_level)

        # Текст пользователя → чат
        w.user_text.connect(win.on_user_text)

        # Ответ ассистента → чат
        w.assistant_text.connect(win.on_assistant_text)

        # Вызов инструмента → чат
        w.tool_executed.connect(win.on_tool_executed)

        # Ошибки
        w.error.connect(win.on_error)

    def _connect_ui_to_worker(self) -> None:
        """Связать действия UI → слоты worker."""
        win = self._window

        # Кнопка микрофона
        win.mic_toggled.connect(self._worker.toggle_listening)

        # Текстовый ввод
        win.text_submitted.connect(self._worker.process_text_input)

    # ── Доступ к worker ─────────────────────────────────────────
    @property
    def worker(self) -> AssistantWorker:
        return self._worker
