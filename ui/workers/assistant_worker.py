"""
Elliot — Worker ассистента, работающий в отдельном QThread.

Объединяет pipeline: Запись → VAD → STT → LLM → TTS → Воспроизведение.
Все тяжёлые операции выполняются вне GUI-потока.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

log = logging.getLogger(__name__)


class AssistantWorker(QObject):
    """
    Worker-объект для голосового pipeline Elliot.

    Создаётся в главном потоке и перемещается в QThread через moveToThread().
    Связь с GUI только через сигналы/слоты.
    """

    # ── Сигналы → UI ───────────────────────────────────────────
    state_changed = pyqtSignal(str)        # "idle" | "listening" | "thinking" | "speaking"
    audio_level = pyqtSignal(float)        # 0.0–1.0
    user_text = pyqtSignal(str)            # Текст пользователя
    assistant_text = pyqtSignal(str)       # Ответ ассистента
    tool_executed = pyqtSignal(str, str)   # (tool_name, result)
    error = pyqtSignal(str)                # Сообщение об ошибке

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._is_listening: bool = False
        self._loop: asyncio.AbstractEventLoop | None = None

        # Core-модули
        self._recorder = None
        self._player = None
        self._vad = None
        self._stt = None
        self._tts = None
        self._llm = None
        self._memory = None
        self._tools = None

    # ── Инициализация core-модулей ──────────────────────────────
    @pyqtSlot()
    def initialize(self) -> None:
        """Инициализировать core-модули. Вызывается после moveToThread()."""
        log.info("Инициализация AssistantWorker...")
        try:
            from config.settings import get_settings
            settings = get_settings()

            from core.audio.recorder import AudioRecorder
            from core.audio.player import AudioPlayer
            from core.audio.vad import VoiceActivityDetector
            from core.stt.faster_whisper_engine import FasterWhisperSTT
            from core.tts.edge_tts_engine import EdgeTTSEngine
            from core.llm.client import GeminiClient
            from core.llm.memory import ConversationMemory
            import core.tools.system_tools  # noqa: F401 (регистрирует системные инструменты)
            from core.tools.registry import registry

            self._recorder = AudioRecorder(
                sample_rate=settings.AUDIO_SAMPLE_RATE,
                channels=settings.AUDIO_CHANNELS,
                blocksize=settings.AUDIO_BLOCKSIZE,
            )
            self._player = AudioPlayer()
            self._vad = VoiceActivityDetector(
                sample_rate=settings.AUDIO_SAMPLE_RATE,
                silence_threshold=settings.VAD_SILENCE_THRESHOLD,
            )
            # Привязываем callback окончания речи к обработчику
            self._vad.on_speech_end = self._on_speech_finalized

            self._stt = FasterWhisperSTT()
            self._tts = EdgeTTSEngine()
            self._memory = ConversationMemory(max_messages=settings.LLM_MAX_HISTORY)
            self._tools = registry

            self._llm = GeminiClient()
            # Регистрируем схемы всех системных инструментов в Gemini
            tool_declarations = self._tools.get_gemini_tools()
            if tool_declarations:
                self._llm.register_tools(tool_declarations)

            # Добавляем слушателя входящих чанков звука
            self._recorder.add_callback(self._on_audio_chunk)

            # Event loop для выполнения async-запросов (Gemini, edge-tts)
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            log.info("AssistantWorker инициализирован успешно, зарегистрировано инструментов: %d", len(self._tools))
            self.state_changed.emit("idle")

        except Exception as e:
            error_msg = f"Ошибка инициализации ядра: {e}"
            log.error(error_msg)
            log.debug(traceback.format_exc())
            self.error.emit(error_msg)
            self.state_changed.emit("idle")

    # ── Аудио колбэки ──────────────────────────────────────────
    def _on_audio_chunk(self, chunk: np.ndarray) -> None:
        """Получение аудио-чанка от AudioRecorder в реальном времени."""
        if not self._is_listening:
            return

        try:
            # Расчёт RMS уровня звука (0.0 .. 1.0)
            rms = float(np.sqrt(np.mean(chunk**2)))
            level = min(1.0, rms * 8.0)
            self.audio_level.emit(level)

            # Передача чанка в Silero VAD
            if self._vad:
                self._vad.process_chunk(chunk)
        except Exception as e:
            log.debug("Ошибка обработки аудио чанка: %s", e)

    def _on_speech_finalized(self, full_audio: np.ndarray) -> None:
        """Вызывается VAD когда пользователь закончил говорить."""
        log.info("Речь завершена, переход к транскрибации...")
        # Останавливаем запись
        self.stop_listening()

        self.state_changed.emit("thinking")
        self.audio_level.emit(0.0)

        try:
            if not self._stt:
                self.error.emit("Модуль STT не готов")
                self.state_changed.emit("idle")
                return

            # Распознавание речи через faster-whisper
            recognized_text = self._stt.transcribe(full_audio)

            if not recognized_text or not recognized_text.strip():
                log.info("Речь не распознана или пуста")
                self.state_changed.emit("idle")
                return

            log.info("Распознанный текст: %s", recognized_text)
            self.user_text.emit(recognized_text)

            # Передаём в пайплайн LLM
            self._process_llm_and_respond(recognized_text)

        except Exception as e:
            self._handle_error("Ошибка распознавания речи", e)

    # ── Слоты управления ────────────────────────────────────────
    @pyqtSlot()
    def start_listening(self) -> None:
        """Начать запись и распознавание речи."""
        if self._is_listening:
            return
        log.info("Запуск прослушивания...")
        self._is_listening = True
        self.state_changed.emit("listening")

        try:
            if self._vad:
                self._vad.reset()
            if self._recorder:
                self._recorder.start()
        except Exception as e:
            self._handle_error("Ошибка запуска микрофона", e)

    @pyqtSlot()
    def stop_listening(self) -> None:
        """Остановить запись."""
        if not self._is_listening:
            return
        log.info("Остановка прослушивания")
        self._is_listening = False

        try:
            if self._recorder:
                self._recorder.stop()
        except Exception as e:
            log.warning("Ошибка при остановке записи: %s", e)

        self.audio_level.emit(0.0)
        self.state_changed.emit("idle")

    @pyqtSlot()
    def toggle_listening(self) -> None:
        """Переключить прослушивание (вкл/выкл)."""
        if self._is_listening:
            self.stop_listening()
        else:
            self.start_listening()

    @pyqtSlot(str)
    def process_text_input(self, text: str) -> None:
        """Обработать текстовый ввод."""
        cleaned = text.strip()
        if not cleaned:
            return
        log.info("Текстовый запрос: %s", cleaned)
        self.user_text.emit(cleaned)
        self._process_llm_and_respond(cleaned)

    # ── Внутренний pipeline LLM + Tools + TTS ───────────────────
    def _process_llm_and_respond(self, user_message: str) -> None:
        """Обработка запроса через Gemini с Function Calling и озвучкой."""
        self.state_changed.emit("thinking")

        try:
            if not self._llm or not self._memory:
                self.error.emit("LLM или память не инициализированы")
                self.state_changed.emit("idle")
                return

            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)

            # Добавляем сообщение пользователя в память
            history = self._memory.get_history()

            # Отправляем сообщение в Gemini
            response = self._loop.run_until_complete(
                self._llm.send_message(user_message, history)
            )

            # Фиксируем запрос пользователя в истории
            self._memory.add_user_message(user_message)

            reply_text = ""

            # Обрабатываем вызовы инструментов (Function Calling)
            tool_calls = response.get("tool_calls", []) if isinstance(response, dict) else []

            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.get("name", "")
                    tool_args = tc.get("args", {})

                    log.info("Вызов инструмента: %s с аргументами: %s", tool_name, tool_args)
                    result_str = ""
                    if self._tools:
                        try:
                            result_str = self._tools.execute(tool_name, **tool_args)
                        except Exception as e:
                            result_str = f"Ошибка выполнения {tool_name}: {e}"

                    self.tool_executed.emit(tool_name, result_str)

                    # Записываем вызов и результат в память диалога
                    self._memory.add_tool_call(tool_name, tool_args)
                    self._memory.add_tool_result(tool_name, result_str)

                # Запрашиваем финальный ответ у Gemini с учётом результатов тулов
                final_response = self._loop.run_until_complete(
                    self._llm.send_tool_result(self._memory.get_history())
                )
                reply_text = final_response.get("text", "")
            else:
                reply_text = response.get("text", "") if isinstance(response, dict) else str(response)

            if reply_text and reply_text.strip():
                # Сохраняем ответ ассистента в памяти
                self._memory.add_assistant_message(reply_text)
                self.assistant_text.emit(reply_text)

                # Синтезируем и воспроизводим речь
                self.state_changed.emit("speaking")
                self._speak(reply_text)

            self.state_changed.emit("idle")

        except Exception as e:
            self._handle_error("Ошибка при обработке запроса", e)

    def _speak(self, text: str) -> None:
        """Синтезировать и воспроизвести речь через edge-tts и AudioPlayer."""
        try:
            if not self._tts or not self._player:
                return

            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)

            # Получаем WAV байты
            audio_data = self._loop.run_until_complete(
                self._tts.synthesize(text)
            )

            if audio_data and len(audio_data) > 0:
                self._player.play(audio_data, blocking=True)

        except Exception as e:
            log.warning("Ошибка воспроизведения TTS: %s", e)

    # ── Утилиты ─────────────────────────────────────────────────
    def _handle_error(self, context: str, exc: Exception) -> None:
        """Обработать и залогировать ошибку."""
        msg = f"{context}: {exc}"
        log.error(msg)
        log.debug(traceback.format_exc())
        self.error.emit(msg)
        self.state_changed.emit("idle")
        self.audio_level.emit(0.0)

    @pyqtSlot()
    def cleanup(self) -> None:
        """Освободить ресурсы при завершении."""
        log.info("Очистка AssistantWorker...")
        self._is_listening = False
        try:
            if self._recorder:
                self._recorder.stop()
            if self._player:
                self._player.stop()
            if self._loop and not self._loop.is_closed():
                self._loop.close()
        except Exception as e:
            log.warning("Ошибка при очистке: %s", e)
