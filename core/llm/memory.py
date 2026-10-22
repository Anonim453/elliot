"""
Управление историей диалога для LLM.

Реализует скользящее окно сообщений для поддержания контекста
без превышения лимитов токенов.
"""

import logging
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


class ConversationMemory:
    """
    Хранилище истории диалога со скользящим окном.

    Поддерживает фиксированное максимальное количество сообщений,
    автоматически удаляя самые старые при переполнении.
    """

    def __init__(self, max_messages: int = 20) -> None:
        """
        Инициализация памяти диалога.

        Args:
            max_messages: Максимальное количество сообщений в истории.
        """
        self._max_messages = max_messages
        self._history: deque[dict[str, Any]] = deque(maxlen=max_messages)
        logger.debug("ConversationMemory инициализирована (max=%d)", max_messages)

    def add_user_message(self, text: str) -> None:
        """
        Добавить сообщение пользователя.

        Args:
            text: Текст сообщения пользователя.
        """
        self._history.append({
            "role": "user",
            "parts": [{"text": text}],
        })
        logger.debug("Добавлено сообщение пользователя: %s", text[:80])

    def add_assistant_message(self, text: str) -> None:
        """
        Добавить ответ ассистента.

        Args:
            text: Текст ответа ассистента.
        """
        self._history.append({
            "role": "model",
            "parts": [{"text": text}],
        })
        logger.debug("Добавлен ответ ассистента: %s", text[:80])

    def add_tool_call(self, name: str, args: dict[str, Any]) -> None:
        """
        Добавить вызов инструмента от ассистента.

        Args:
            name: Имя вызванного инструмента.
            args: Аргументы вызова.
        """
        self._history.append({
            "role": "model",
            "parts": [{"functionCall": {"name": name, "args": args}}],
        })
        logger.debug("Добавлен вызов инструмента: %s", name)

    def add_tool_result(self, name: str, result: str) -> None:
        """
        Добавить результат выполнения инструмента.

        Args:
            name: Имя инструмента.
            result: Результат выполнения (строка).
        """
        self._history.append({
            "role": "user",
            "parts": [{
                "functionResponse": {
                    "name": name,
                    "response": {"result": result},
                }
            }],
        })
        logger.debug("Добавлен результат инструмента %s: %s", name, result[:80])

    def get_history(self) -> list[dict[str, Any]]:
        """
        Получить текущую историю диалога.

        Returns:
            Список сообщений в формате Gemini API.
        """
        return list(self._history)

    def clear(self) -> None:
        """Очистить всю историю диалога."""
        self._history.clear()
        logger.info("История диалога очищена")

    @property
    def message_count(self) -> int:
        """Текущее количество сообщений в истории."""
        return len(self._history)

    def __len__(self) -> int:
        return len(self._history)

    def __repr__(self) -> str:
        return (
            f"ConversationMemory(messages={len(self._history)}, "
            f"max={self._max_messages})"
        )
