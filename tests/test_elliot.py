"""
Тестовый набор для голосового ассистента Elliot.

Проверяет работоспособность:
- Загрузки настроек (Settings)
- Реестра инструментов (ToolRegistry)
- Выполнения безопасных системных команд
- Памяти диалога (ConversationMemory)
- Генерации схем для Gemini Function Calling
"""

import os
import sys
from pathlib import Path

import pytest

# Добавляем корневую директорию проекта в sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings, get_settings
from core.llm.memory import ConversationMemory
from core.tools.registry import ToolRegistry, register_tool
import core.tools.system_tools as system_tools
from core.tools.registry import registry


def test_settings_load():
    """Проверка создания и загрузки настроек."""
    settings = get_settings()
    assert settings.WHISPER_LANGUAGE == "ru"
    assert settings.AUDIO_SAMPLE_RATE == 16000
    assert settings.TTS_VOICE.startswith("ru-RU")
    assert settings.HOTKEY == "ctrl+space"


def test_conversation_memory():
    """Проверка работы памяти диалога и скользящего окна."""
    memory = ConversationMemory(max_messages=4)

    memory.add_user_message("Привет")
    memory.add_assistant_message("Здравствуйте!")
    memory.add_user_message("Как дела?")
    memory.add_assistant_message("Отлично!")

    history = memory.get_history()
    assert len(history) == 4
    assert history[0]["parts"][0]["text"] == "Привет"
    assert history[-1]["parts"][0]["text"] == "Отлично!"

    # Добавляем 5-е сообщение, самое старое должно выпасть
    memory.add_user_message("Сколько время?")
    history_after = memory.get_history()
    assert len(history_after) == 4
    assert history_after[0]["parts"][0]["text"] == "Здравствуйте!"
    assert history_after[-1]["parts"][0]["text"] == "Сколько время?"


def test_tool_registry():
    """Проверка регистрации инструментов и генерации схем."""
    test_reg = ToolRegistry()

    @test_reg.register
    def sample_func(text: str, count: int = 1) -> str:
        """Повторить текст заданное количество раз.

        Args:
            text: Исходная строка.
            count: Количество повторов.
        """
        return text * count

    assert "sample_func" in test_reg
    assert len(test_reg) == 1

    # Проверка исполнения
    res = test_reg.execute("sample_func", text="Hi", count=3)
    assert res == "HiHiHi"

    # Проверка схемы Gemini
    schemas = test_reg.get_schemas()
    assert len(schemas) == 1
    decl = schemas[0]
    assert decl["name"] == "sample_func"
    assert "Повторить текст" in decl["description"]
    assert decl["parameters"]["properties"]["text"]["type"] == "string"
    assert decl["parameters"]["properties"]["count"]["type"] == "integer"
    assert decl["parameters"]["required"] == ["text"]


def test_system_tools_registered():
    """Проверка, что все основные системные инструменты зарегистрированы в глобальном реестре."""
    names = registry.tool_names
    assert "get_time" in names
    assert "get_system_stats" in names
    assert "set_volume" in names
    assert "open_application" in names
    assert "close_application" in names
    assert "open_website" in names
    assert "search_web" in names
    assert "execute_command" in names
    assert "control_media" in names
    assert "system_power" in names
    assert "file_operations" in names


def test_get_time_tool():
    """Проверка вызова безопасного инструмента get_time."""
    time_str = registry.execute("get_time")
    assert "Сейчас" in time_str
    assert "года" in time_str


def test_get_system_stats_tool():
    """Проверка получения статистики ПК."""
    stats = registry.execute("get_system_stats")
    assert "Процессор" in stats
    assert "Оперативная память" in stats
    assert "Диск C" in stats


def test_gemini_tools_format():
    """Проверка формата выгрузки инструментов для Gemini SDK."""
    tools_payload = registry.get_gemini_tools()
    assert len(tools_payload) == 1
    assert "function_declarations" in tools_payload[0]
    declarations = tools_payload[0]["function_declarations"]
    assert len(declarations) >= 10


def test_ui_components():
    """Проверка создания UI компонентов без показа окна."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(["--platform", "offscreen"])

    from ui.widgets.waveform import VoiceWaveWidget
    from ui.widgets.status_indicator import StatusIndicator, AssistantState
    from ui.widgets.chat_view import ChatView
    from ui.main_window import MainWindow

    wave = VoiceWaveWidget()
    wave.set_amplitude(0.5)
    assert wave._target_amplitude == 0.5

    status = StatusIndicator()
    status.set_state("listening")
    assert status.current_state == AssistantState.LISTENING

    chat = ChatView()
    chat.add_user_message("Привет от пользователя")
    chat.add_assistant_message("Ответ от Elliot")
    chat.add_tool_message("get_time", "Сейчас 17:00")
    assert chat._layout.count() >= 4

    win = MainWindow()
    assert win.windowTitle() == "Elliot"
    assert win.chat_view is not None
    assert win.waveform is not None
