"""
Модуль захвата аудио с микрофона.

Использует sounddevice для потокового захвата звука
с callback-механизмом для передачи чанков в VAD.
"""

import logging
from collections.abc import Callable
from typing import Any

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioRecorder:
    """
    Потоковый захват аудио с микрофона через sounddevice InputStream.

    Использует callback-механизм для передачи аудио-чанков
    внешним обработчикам (VAD, визуализация и т.д.).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        blocksize: int = 512,
        dtype: str = "float32",
    ) -> None:
        """
        Инициализация рекордера.

        Args:
            sample_rate: Частота дискретизации (Гц).
            channels: Количество каналов (1 = моно).
            blocksize: Размер блока в сэмплах.
            dtype: Тип данных аудио.
        """
        self._sample_rate = sample_rate
        self._channels = channels
        self._blocksize = blocksize
        self._dtype = dtype
        self._stream: sd.InputStream | None = None
        self._is_recording = False
        self._callbacks: list[Callable[[np.ndarray], Any]] = []

        logger.info(
            "AudioRecorder инициализирован: rate=%d, channels=%d, blocksize=%d",
            sample_rate, channels, blocksize,
        )

    def add_callback(self, callback: Callable[[np.ndarray], Any]) -> None:
        """
        Зарегистрировать callback для получения аудио-чанков.

        Args:
            callback: Функция, принимающая np.ndarray (float32, shape=(blocksize, 1)).
        """
        self._callbacks.append(callback)
        logger.debug("Добавлен audio callback: %s", callback.__qualname__)

    def remove_callback(self, callback: Callable[[np.ndarray], Any]) -> None:
        """
        Удалить зарегистрированный callback.

        Args:
            callback: Ранее зарегистрированная функция.
        """
        try:
            self._callbacks.remove(callback)
            logger.debug("Удалён audio callback: %s", callback.__qualname__)
        except ValueError:
            logger.warning("Callback не найден для удаления: %s", callback.__qualname__)

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        """Внутренний callback sounddevice — вызывается из аудио-потока."""
        if status:
            logger.warning("Статус аудиопотока: %s", status)

        # Копируем данные, т.к. буфер будет переиспользован sounddevice
        chunk = indata.copy()

        for cb in self._callbacks:
            try:
                cb(chunk)
            except Exception:
                logger.exception("Ошибка в audio callback %s", cb.__qualname__)

    def start(self) -> None:
        """Начать запись с микрофона."""
        if self._is_recording:
            logger.warning("Запись уже идёт")
            return

        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                blocksize=self._blocksize,
                dtype=self._dtype,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_recording = True
            logger.info("Запись с микрофона начата")
        except Exception:
            self._is_recording = False
            logger.exception("Не удалось начать запись")
            raise

    def stop(self) -> None:
        """Остановить запись."""
        if not self._is_recording:
            return

        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            self._is_recording = False
            logger.info("Запись остановлена")
        except Exception:
            logger.exception("Ошибка при остановке записи")
            self._is_recording = False

    @property
    def is_recording(self) -> bool:
        """Идёт ли запись в данный момент."""
        return self._is_recording

    @property
    def sample_rate(self) -> int:
        """Частота дискретизации."""
        return self._sample_rate

    def __del__(self) -> None:
        """Гарантированная остановка при удалении объекта."""
        self.stop()
