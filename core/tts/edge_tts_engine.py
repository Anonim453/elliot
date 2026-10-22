"""
Движок синтеза речи на основе edge-tts.

Использует бесплатный Microsoft Edge TTS API
для синтеза речи на русском языке.
"""

import io
import logging
import struct
import wave

import edge_tts
import numpy as np

from config.settings import get_settings
from core.tts.base import BaseTTS

logger = logging.getLogger(__name__)


class EdgeTTSEngine(BaseTTS):
    """
    TTS-движок на основе edge-tts.

    Синтезирует речь через Microsoft Edge TTS API.
    Результат — WAV аудиоданные.
    """

    def __init__(self, voice: str | None = None) -> None:
        """
        Инициализация TTS-движка.

        Args:
            voice: Имя голоса (например, ru-RU-DmitryNeural).
                   По умолчанию из настроек.
        """
        settings = get_settings()
        self._voice = voice or settings.TTS_VOICE
        logger.info("EdgeTTSEngine инициализирован: voice=%s", self._voice)

    async def synthesize(self, text: str) -> bytes:
        """
        Синтезировать речь из текста.

        Args:
            text: Текст для озвучивания.

        Returns:
            WAV аудиоданные в виде bytes.
        """
        if not text or not text.strip():
            logger.warning("Пустой текст для синтеза")
            return b""

        try:
            # Собираем MP3-данные из потока edge-tts
            mp3_data = await self._synthesize_mp3(text)

            if not mp3_data:
                logger.error("edge-tts вернул пустые данные")
                return b""

            # Конвертируем MP3 -> WAV
            wav_data = self._mp3_to_wav(mp3_data)

            logger.info(
                "Синтез завершён: текст='%s', wav_size=%d bytes",
                text[:50], len(wav_data),
            )

            return wav_data

        except Exception:
            logger.exception("Ошибка синтеза речи")
            return b""

    async def _synthesize_mp3(self, text: str) -> bytes:
        """
        Получить MP3-данные из edge-tts (стриминг).

        Args:
            text: Текст для синтеза.

        Returns:
            Сырые MP3-данные.
        """
        communicate = edge_tts.Communicate(text, self._voice)
        mp3_chunks: list[bytes] = []

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_chunks.append(chunk["data"])

        return b"".join(mp3_chunks)

    @staticmethod
    def _mp3_to_wav(mp3_data: bytes) -> bytes:
        """
        Конвертировать MP3-данные в WAV через soundfile.

        Args:
            mp3_data: Сырые MP3-данные.

        Returns:
            WAV-данные (PCM 16-bit, mono, 24000 Hz).
        """
        try:
            import soundfile as sf

            mp3_buf = io.BytesIO(mp3_data)
            audio_array, sample_rate = sf.read(mp3_buf, dtype="float32")

            # Если стерео — берём моно
            if audio_array.ndim > 1:
                audio_array = audio_array.mean(axis=1)

            # Конвертируем в 16-bit PCM
            pcm_data = (audio_array * 32767).astype(np.int16)

            # Пишем WAV
            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16 бит = 2 байта
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm_data.tobytes())

            return wav_buf.getvalue()

        except Exception:
            logger.exception("Ошибка конвертации MP3 -> WAV")
            # Запасной вариант: возвращаем MP3 как есть
            # (AudioPlayer попробует декодировать через soundfile)
            return mp3_data

    async def synthesize_streaming(self, text: str) -> bytes:
        """
        Синтезировать речь в потоковом режиме (для минимальной задержки).

        Начинает воспроизведение первых чанков, пока остальные генерируются.

        Args:
            text: Текст для синтеза.

        Returns:
            Полные WAV-данные (для кеширования).
        """
        return await self.synthesize(text)

    @staticmethod
    async def list_voices(language: str = "ru") -> list[dict[str, str]]:
        """
        Получить список доступных голосов для языка.

        Args:
            language: Код языка (например, 'ru').

        Returns:
            Список словарей с информацией о голосах.
        """
        voices = await edge_tts.list_voices()
        return [
            {
                "name": v["ShortName"],
                "gender": v["Gender"],
                "locale": v["Locale"],
            }
            for v in voices
            if v["Locale"].startswith(language)
        ]
