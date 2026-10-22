"""
Конфигурация приложения Elliot.

Загрузка настроек из переменных окружения и .env файла
с использованием Pydantic BaseSettings.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Корневая директория проекта
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Основные настройки голосового ассистента Elliot."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Google Gemini ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # --- STT (faster-whisper) ---
    WHISPER_MODEL: str = "small"
    WHISPER_LANGUAGE: str = "ru"

    # --- TTS (edge-tts) ---
    TTS_VOICE: str = "ru-RU-DmitryNeural"

    # --- Управление ---
    HOTKEY: str = "ctrl+space"

    # --- Аудио ---
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1
    AUDIO_BLOCKSIZE: int = 512

    # --- VAD ---
    VAD_SILENCE_THRESHOLD: float = 0.5

    # --- LLM ---
    LLM_MAX_HISTORY: int = 20


def get_settings() -> Settings:
    """Получить экземпляр настроек (singleton-паттерн через кеш)."""
    return _cached_settings


_cached_settings: Settings = Settings()
