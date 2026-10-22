"""
Клиент Google Gemini для взаимодействия с LLM.

Обеспечивает отправку сообщений, поддержку Function Calling
и управление историей диалога.
"""

import logging
from typing import Any

import google.generativeai as genai
from google.generativeai.types import (
    ContentType,
    GenerateContentResponse,
)

from config.prompts import SYSTEM_PROMPT
from config.settings import get_settings

logger = logging.getLogger(__name__)


class GeminiClient:
    """
    Клиент для Google Gemini API.

    Поддерживает текстовую генерацию и Function Calling
    с автоматической регистрацией инструментов.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        """
        Инициализация клиента Gemini.

        Args:
            api_key: API ключ Gemini. По умолчанию из настроек.
            model_name: Название модели. По умолчанию из настроек.
            system_prompt: Системный промпт. По умолчанию из prompts.py.
        """
        settings = get_settings()
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model_name = model_name or settings.GEMINI_MODEL
        self._system_prompt = system_prompt or SYSTEM_PROMPT

        if not self._api_key:
            raise ValueError(
                "GEMINI_API_KEY не задан. Укажите его в .env файле или передайте явно."
            )

        # Конфигурация API
        genai.configure(api_key=self._api_key)

        # Инструменты (tools) для Function Calling
        self._tools: list[dict[str, Any]] | None = None
        self._model: genai.GenerativeModel | None = None

        logger.info("GeminiClient инициализирован: model=%s", self._model_name)

    def register_tools(self, tool_schemas: list[dict[str, Any]]) -> None:
        """
        Зарегистрировать инструменты для Function Calling.

        Args:
            tool_schemas: Список JSON-схем инструментов в формате Gemini.
        """
        self._tools = tool_schemas
        self._model = None  # Сбросить модель для пересоздания с инструментами
        logger.info("Зарегистрировано %d инструментов", len(tool_schemas))

    def _ensure_model(self) -> genai.GenerativeModel:
        """Ленивое создание модели при первом вызове."""
        if self._model is not None:
            return self._model

        kwargs: dict[str, Any] = {
            "model_name": self._model_name,
            "system_instruction": self._system_prompt,
        }

        if self._tools:
            kwargs["tools"] = self._tools

        self._model = genai.GenerativeModel(**kwargs)
        logger.debug("Модель Gemini создана: %s", self._model_name)
        return self._model

    async def send_message(
        self,
        user_text: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Отправить сообщение в Gemini и получить ответ.

        Args:
            user_text: Текст сообщения пользователя.
            conversation_history: История диалога в формате Gemini API.

        Returns:
            Словарь с ключами:
                - "text": str — текстовый ответ (может быть пустым если есть tool_calls)
                - "tool_calls": list[dict] — список вызовов инструментов
                  каждый: {"name": str, "args": dict}
        """
        model = self._ensure_model()

        # Формируем содержимое запроса
        contents: list[dict[str, Any]] = []

        if conversation_history:
            contents.extend(conversation_history)

        # Добавляем текущее сообщение
        contents.append({
            "role": "user",
            "parts": [{"text": user_text}],
        })

        try:
            # Асинхронная генерация
            response: GenerateContentResponse = await model.generate_content_async(
                contents=contents,
                generation_config=genai.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=2048,
                ),
            )

            return self._parse_response(response)

        except Exception:
            logger.exception("Ошибка при отправке сообщения в Gemini")
            return {
                "text": "Извини, произошла ошибка при обработке запроса.",
                "tool_calls": [],
            }

    @staticmethod
    def _parse_response(response: GenerateContentResponse) -> dict[str, Any]:
        """
        Разобрать ответ от Gemini API.

        Args:
            response: Ответ от API.

        Returns:
            Словарь с text и tool_calls.
        """
        result: dict[str, Any] = {
            "text": "",
            "tool_calls": [],
        }

        try:
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                # Текстовый ответ
                if hasattr(part, "text") and part.text:
                    result["text"] += part.text

                # Вызов инструмента
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    result["tool_calls"].append({
                        "name": fc.name,
                        "args": dict(fc.args) if fc.args else {},
                    })

        except (IndexError, AttributeError):
            logger.exception("Ошибка разбора ответа Gemini")
            if not result["text"]:
                result["text"] = "Не удалось получить ответ."

        return result

    async def send_tool_result(
        self,
        conversation_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Отправить результат выполнения инструмента и получить финальный ответ.

        Args:
            conversation_history: Полная история включая tool call и результат.

        Returns:
            Словарь с text и tool_calls.
        """
        model = self._ensure_model()

        try:
            response = await model.generate_content_async(
                contents=conversation_history,
                generation_config=genai.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=2048,
                ),
            )
            return self._parse_response(response)

        except Exception:
            logger.exception("Ошибка при отправке результата инструмента")
            return {
                "text": "Произошла ошибка при обработке результата.",
                "tool_calls": [],
            }
