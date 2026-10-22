"""
Модуль воспроизведения аудио.

Неблокирующее воспроизведение аудио через sounddevice
с поддержкой bytes и numpy array.
"""

import io
import logging
import threading
from typing import Any

import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger(__name__)


class AudioPlayer:
    """
    Неблокирующий аудиоплеер на основе sounddevice.

    Поддерживает воспроизведение из bytes (WAV/PCM) и numpy array.
    Воспроизведение выполняется в отдельном потоке.
    """

    def __init__(self) -> None:
        """Инициализация аудиоплеера."""
        self._is_playing = False
        self._play_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        logger.info("AudioPlayer инициализирован")

    def play(
        self,
        audio_data: bytes | np.ndarray,
        sample_rate: int = 24000,
        blocking: bool = False,
    ) -> None:
        """
        Воспроизвести аудио.

        Args:
            audio_data: Аудиоданные — bytes (WAV) или numpy array (float32).
            sample_rate: Частота дискретизации (используется если audio_data — numpy).
            blocking: Если True, блокирует до конца воспроизведения.
        """
        # Остановить предыдущее воспроизведение
        self.stop()

        self._stop_event.clear()

        if blocking:
            self._play_internal(audio_data, sample_rate)
        else:
            self._play_thread = threading.Thread(
                target=self._play_internal,
                args=(audio_data, sample_rate),
                daemon=True,
                name="audio-player",
            )
            self._play_thread.start()

    def _play_internal(
        self,
        audio_data: bytes | np.ndarray,
        sample_rate: int,
    ) -> None:
        """Внутренний метод воспроизведения (запускается в потоке)."""
        try:
            with self._lock:
                self._is_playing = True

            # Конвертация bytes -> numpy через soundfile
            if isinstance(audio_data, bytes):
                audio_array, sample_rate = self._decode_audio(audio_data)
            else:
                audio_array = audio_data

            if audio_array.size == 0:
                logger.warning("Пустой аудио-массив, пропускаем воспроизведение")
                return

            # Нормализация в float32 если нужно
            if audio_array.dtype != np.float32:
                audio_array = audio_array.astype(np.float32)

            logger.debug(
                "Воспроизведение: samples=%d, rate=%d, duration=%.1fs",
                len(audio_array), sample_rate,
                len(audio_array) / sample_rate,
            )

            # Воспроизведение через sounddevice с проверкой stop_event
            sd.play(audio_array, samplerate=sample_rate)
            # Ждём завершения или сигнала остановки
            while sd.get_stream().active and not self._stop_event.is_set():
                sd.sleep(50)

            if self._stop_event.is_set():
                sd.stop()
                logger.debug("Воспроизведение прервано")
            else:
                logger.debug("Воспроизведение завершено")

        except Exception:
            logger.exception("Ошибка воспроизведения аудио")
        finally:
            with self._lock:
                self._is_playing = False

    @staticmethod
    def _decode_audio(data: bytes) -> tuple[np.ndarray, int]:
        """
        Декодировать аудио из bytes (WAV, MP3 и др.) через soundfile.

        Args:
            data: Сырые аудиоданные.

        Returns:
            Кортеж (numpy array, sample_rate).
        """
        buf = io.BytesIO(data)
        try:
            audio_array, sample_rate = sf.read(buf, dtype="float32")
            return audio_array, sample_rate
        except Exception:
            logger.exception("Не удалось декодировать аудио")
            return np.array([], dtype=np.float32), 24000

    def stop(self) -> None:
        """Остановить текущее воспроизведение."""
        self._stop_event.set()
        sd.stop()

        if self._play_thread is not None and self._play_thread.is_alive():
            self._play_thread.join(timeout=2.0)
            self._play_thread = None

        with self._lock:
            self._is_playing = False

    @property
    def is_playing(self) -> bool:
        """Идёт ли воспроизведение в данный момент."""
        with self._lock:
            return self._is_playing

    def __del__(self) -> None:
        """Гарантированная остановка при удалении объекта."""
        self.stop()
