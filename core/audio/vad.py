"""
Детектор голосовой активности (VAD) на основе Silero VAD.

Анализирует аудио-чанки в реальном времени, накапливает буфер
пока обнаруживается речь, и вызывает callback при окончании фразы.
"""

import logging
from collections.abc import Callable
from typing import Any

import numpy as np
import torch

logger = logging.getLogger(__name__)


class VoiceActivityDetector:
    """
    Детектор голосовой активности на основе Silero VAD.

    Принимает аудио-чанки, определяет наличие речи,
    накапливает буфер и вызывает on_speech_end когда
    обнаруживается достаточная пауза.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        silence_threshold: float = 0.5,
        speech_threshold: float = 0.5,
        min_speech_duration: float = 0.3,
    ) -> None:
        """
        Инициализация VAD.

        Args:
            sample_rate: Частота дискретизации входного аудио.
            silence_threshold: Длительность тишины (сек) для определения конца фразы.
            speech_threshold: Порог вероятности для детекции речи (0.0-1.0).
            min_speech_duration: Минимальная длительность речи (сек) для срабатывания.
        """
        self._sample_rate = sample_rate
        self._silence_threshold = silence_threshold
        self._speech_threshold = speech_threshold
        self._min_speech_duration = min_speech_duration

        # Загрузка модели Silero VAD
        self._model: Any = None
        self._load_model()

        # Состояние детектора
        self._speech_buffer: list[np.ndarray] = []
        self._is_speech_active = False
        self._silence_samples = 0
        self._silence_samples_threshold = int(sample_rate * silence_threshold)
        self._min_speech_samples = int(sample_rate * min_speech_duration)

        # Callback при окончании речи
        self._on_speech_end: Callable[[np.ndarray], Any] | None = None

        logger.info(
            "VAD инициализирован: silence=%.1fs, threshold=%.2f",
            silence_threshold, speech_threshold,
        )

    def _load_model(self) -> None:
        """Загрузить модель Silero VAD."""
        try:
            self._model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                trust_repo=True,
            )
            self._model.eval()
            logger.info("Модель Silero VAD загружена")
        except Exception:
            logger.exception("Не удалось загрузить Silero VAD")
            raise

    @property
    def on_speech_end(self) -> Callable[[np.ndarray], Any] | None:
        """Callback, вызываемый при окончании фразы."""
        return self._on_speech_end

    @on_speech_end.setter
    def on_speech_end(self, callback: Callable[[np.ndarray], Any] | None) -> None:
        """
        Установить callback для окончания речи.

        Args:
            callback: Функция, принимающая np.ndarray с полным аудио-сегментом.
        """
        self._on_speech_end = callback

    def process_chunk(self, audio_chunk: np.ndarray) -> bool:
        """
        Обработать аудио-чанк и определить наличие речи.

        Args:
            audio_chunk: NumPy массив с аудиоданными (float32).

        Returns:
            True если в чанке обнаружена речь, False иначе.
        """
        try:
            # Убедимся что данные одномерные
            chunk = audio_chunk.flatten().astype(np.float32)

            # Silero VAD ожидает чанки определённого размера (512 для 16kHz)
            # Передаём как tensor
            tensor = torch.from_numpy(chunk)
            speech_prob = self._model(tensor, self._sample_rate).item()

            is_speech = speech_prob >= self._speech_threshold

            if is_speech:
                self._handle_speech(chunk)
            else:
                self._handle_silence(chunk)

            return is_speech

        except Exception:
            logger.exception("Ошибка обработки аудио-чанка в VAD")
            return False

    def _handle_speech(self, chunk: np.ndarray) -> None:
        """Обработка чанка с речью."""
        if not self._is_speech_active:
            self._is_speech_active = True
            logger.debug("Начало речи обнаружено")

        self._speech_buffer.append(chunk)
        self._silence_samples = 0

    def _handle_silence(self, chunk: np.ndarray) -> None:
        """Обработка чанка с тишиной."""
        if not self._is_speech_active:
            return

        # Добавляем тишину в буфер (для естественного звучания)
        self._speech_buffer.append(chunk)
        self._silence_samples += len(chunk)

        # Проверяем, достаточно ли тишины для окончания фразы
        if self._silence_samples >= self._silence_samples_threshold:
            self._finalize_speech()

    def _finalize_speech(self) -> None:
        """Завершить накопление речи и вызвать callback."""
        if not self._speech_buffer:
            self._reset()
            return

        # Собираем полный аудио-сегмент
        full_audio = np.concatenate(self._speech_buffer)

        # Проверяем минимальную длительность
        if len(full_audio) < self._min_speech_samples:
            logger.debug(
                "Речевой сегмент слишком короткий (%.2fs), пропускаем",
                len(full_audio) / self._sample_rate,
            )
            self._reset()
            return

        logger.info(
            "Речевой сегмент завершён: %.2f сек",
            len(full_audio) / self._sample_rate,
        )

        # Вызываем callback
        if self._on_speech_end is not None:
            try:
                self._on_speech_end(full_audio)
            except Exception:
                logger.exception("Ошибка в on_speech_end callback")

        self._reset()

    def _reset(self) -> None:
        """Сбросить состояние детектора."""
        self._speech_buffer.clear()
        self._is_speech_active = False
        self._silence_samples = 0
        # Сброс скрытого состояния модели Silero
        self._model.reset_states()

    @property
    def is_speech_active(self) -> bool:
        """Обнаружена ли речь в данный момент."""
        return self._is_speech_active

    def reset(self) -> None:
        """Публичный метод сброса состояния."""
        self._reset()
        logger.debug("VAD состояние сброшено")
