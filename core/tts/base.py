"""
Абстрактный базовый класс для движков синтеза речи (TTS).
"""

from abc import ABC, abstractmethod


class BaseTTS(ABC):
    """Базовый класс для модулей Text-to-Speech."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """
        Синтезировать речь из текста.

        Args:
            text: Текст для озвучивания.

        Returns:
            WAV аудиоданные в виде bytes.
        """
        ...
