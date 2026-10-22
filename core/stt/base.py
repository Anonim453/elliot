"""
Абстрактный базовый класс для движков распознавания речи (STT).
"""

from abc import ABC, abstractmethod

import numpy as np


class BaseSTT(ABC):
    """Базовый класс для модулей Speech-to-Text."""

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """
        Распознать речь из аудио-массива.

        Args:
            audio: NumPy массив с аудиоданными (float32, моно).
            sample_rate: Частота дискретизации в Гц.

        Returns:
            Распознанный текст.
        """
        ...
