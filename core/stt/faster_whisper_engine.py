"""
Движок распознавания речи на основе faster-whisper.

Обеспечивает быстрое локальное распознавание речи
с поддержкой CPU и GPU (CUDA).
"""

import logging

import numpy as np

from config.settings import get_settings
from core.stt.base import BaseSTT

logger = logging.getLogger(__name__)


class FasterWhisperSTT(BaseSTT):
    """
    STT-движок на основе faster-whisper.

    Автоматически определяет доступность GPU и выбирает
    оптимальный compute_type.
    """

    def __init__(
        self,
        model_size: str | None = None,
        language: str | None = None,
        device: str | None = None,
    ) -> None:
        """
        Инициализация движка faster-whisper.

        Args:
            model_size: Размер модели (tiny/base/small/medium/large).
                        По умолчанию берётся из настроек.
            language: Язык распознавания. По умолчанию из настроек.
            device: Устройство (cpu/cuda). По умолчанию автоопределение.
        """
        settings = get_settings()
        self._model_size = model_size or settings.WHISPER_MODEL
        self._language = language or settings.WHISPER_LANGUAGE
        self._device = device or self._detect_device()
        self._compute_type = "float16" if self._device == "cuda" else "int8"
        self._model = None

        logger.info(
            "FasterWhisperSTT: model=%s, device=%s, compute=%s, lang=%s",
            self._model_size, self._device, self._compute_type, self._language,
        )

    @staticmethod
    def _detect_device() -> str:
        """Автоопределение доступности CUDA."""
        try:
            import torch
            if torch.cuda.is_available():
                logger.info("CUDA доступна, используем GPU")
                return "cuda"
        except ImportError:
            pass
        logger.info("CUDA недоступна, используем CPU")
        return "cpu"

    def _ensure_model(self) -> None:
        """Ленивая загрузка модели при первом вызове."""
        if self._model is not None:
            return

        try:
            from faster_whisper import WhisperModel

            logger.info("Загрузка модели faster-whisper '%s'...", self._model_size)
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            logger.info("Модель faster-whisper загружена успешно")
        except Exception:
            logger.exception("Не удалось загрузить модель faster-whisper")
            raise

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """
        Распознать речь из аудио-массива.

        Args:
            audio: NumPy массив с аудиоданными (float32, моно).
            sample_rate: Частота дискретизации в Гц.

        Returns:
            Распознанный текст.
        """
        self._ensure_model()

        try:
            # faster-whisper ожидает float32 одномерный массив
            audio_flat = audio.flatten().astype(np.float32)

            segments, info = self._model.transcribe(
                audio_flat,
                language=self._language,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=300,
                    speech_pad_ms=200,
                ),
            )

            # Собираем текст из всех сегментов
            text_parts: list[str] = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            result = " ".join(text_parts).strip()

            logger.info(
                "Распознано [%.1fs, lang=%s, prob=%.2f]: %s",
                info.duration,
                info.language,
                info.language_probability,
                result[:100],
            )

            return result

        except Exception:
            logger.exception("Ошибка распознавания речи")
            return ""
