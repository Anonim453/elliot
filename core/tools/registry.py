"""
Реестр инструментов (tools) для Function Calling.

Предоставляет декоратор @register_tool для автоматической регистрации
функций и генерации JSON-схем для Gemini API.
"""

import inspect
import logging
from collections.abc import Callable
from typing import Any, get_type_hints

logger = logging.getLogger(__name__)

# Маппинг Python-типов в JSON Schema типы
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


class ToolRegistry:
    """
    Глобальный реестр инструментов для Function Calling.

    Хранит зарегистрированные функции и генерирует
    JSON-схемы для Gemini API.
    """

    def __init__(self) -> None:
        """Инициализация реестра."""
        self._tools: dict[str, Callable[..., str]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        func: Callable[..., str] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable:
        """
        Декоратор для регистрации функции как инструмента.

        Может использоваться как:
            @registry.register
            def my_tool(...): ...

            @registry.register(name="custom_name", description="...")
            def my_tool(...): ...

        Args:
            func: Декорируемая функция.
            name: Пользовательское имя (по умолчанию — имя функции).
            description: Описание (по умолчанию — из docstring).

        Returns:
            Декорированная функция.
        """
        def decorator(f: Callable[..., str]) -> Callable[..., str]:
            tool_name = name or f.__name__
            tool_description = description or self._extract_description(f)

            self._tools[tool_name] = f
            self._metadata[tool_name] = {
                "name": tool_name,
                "description": tool_description,
                "parameters": self._extract_parameters(f),
            }

            logger.debug("Инструмент зарегистрирован: %s", tool_name)
            return f

        # Поддержка обоих вариантов: @register и @register(...)
        if func is not None:
            return decorator(func)
        return decorator

    @staticmethod
    def _extract_description(func: Callable) -> str:
        """Извлечь описание из docstring функции."""
        doc = inspect.getdoc(func)
        if not doc:
            return f"Инструмент {func.__name__}"
        # Берём первую строку/абзац до пустой строки или Args:
        lines: list[str] = []
        for line in doc.split("\n"):
            stripped = line.strip()
            if stripped.lower().startswith(("args:", "returns:", "raises:")):
                break
            if not stripped and lines:
                break
            if stripped:
                lines.append(stripped)
        return " ".join(lines) if lines else doc.split("\n")[0]

    @staticmethod
    def _extract_parameters(func: Callable) -> dict[str, Any]:
        """
        Извлечь параметры и их типы из сигнатуры функции.

        Returns:
            JSON Schema совместимая структура параметров.
        """
        sig = inspect.signature(func)
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}

        properties: dict[str, dict[str, str]] = {}
        required: list[str] = []

        # Парсим описания параметров из docstring
        param_docs = ToolRegistry._parse_param_docs(func)

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            # Тип параметра
            param_type = hints.get(param_name, str)
            json_type = _TYPE_MAP.get(param_type, "string")

            prop: dict[str, str] = {
                "type": json_type,
                "description": param_docs.get(param_name, f"Параметр {param_name}"),
            }

            properties[param_name] = prop

            # Обязательность (нет значения по умолчанию = обязательный)
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        result: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            result["required"] = required

        return result

    @staticmethod
    def _parse_param_docs(func: Callable) -> dict[str, str]:
        """
        Извлечь описания параметров из docstring (формат Google-style).

        Returns:
            Словарь {имя_параметра: описание}.
        """
        doc = inspect.getdoc(func)
        if not doc:
            return {}

        param_docs: dict[str, str] = {}
        in_args = False

        for line in doc.split("\n"):
            stripped = line.strip()

            if stripped.lower().startswith("args:"):
                in_args = True
                continue

            if in_args:
                if stripped.lower().startswith(("returns:", "raises:", "example:")):
                    break
                if not stripped:
                    continue

                # Формат: "param_name: описание" или "param_name (type): описание"
                if ":" in stripped:
                    parts = stripped.split(":", 1)
                    pname = parts[0].strip()
                    # Убираем тип в скобках, если есть
                    if "(" in pname:
                        pname = pname.split("(")[0].strip()
                    # Убираем маркер дефис
                    pname = pname.lstrip("- ")
                    pdesc = parts[1].strip().rstrip(".")
                    if pname:
                        param_docs[pname] = pdesc

        return param_docs

    def execute(self, tool_name: str, **kwargs: Any) -> str:
        """
        Выполнить зарегистрированный инструмент.

        Args:
            tool_name: Имя инструмента.
            **kwargs: Аргументы для инструмента.

        Returns:
            Результат выполнения (строка).

        Raises:
            KeyError: Если инструмент не найден.
        """
        if tool_name not in self._tools:
            error_msg = f"Инструмент '{tool_name}' не найден"
            logger.error(error_msg)
            raise KeyError(error_msg)

        try:
            logger.info("Выполнение инструмента: %s(%s)", tool_name, kwargs)
            result = self._tools[tool_name](**kwargs)
            logger.info("Результат %s: %s", tool_name, str(result)[:200])
            return str(result)
        except Exception as e:
            error_msg = f"Ошибка выполнения '{tool_name}': {e}"
            logger.exception(error_msg)
            return error_msg

    def get_schemas(self) -> list[dict[str, Any]]:
        """
        Получить JSON-схемы всех инструментов для Gemini API.

        Returns:
            Список function declarations в формате Gemini.
        """
        declarations: list[dict[str, Any]] = []

        for tool_name, meta in self._metadata.items():
            declarations.append({
                "name": meta["name"],
                "description": meta["description"],
                "parameters": meta["parameters"],
            })

        return declarations

    def get_gemini_tools(self) -> list[dict[str, Any]]:
        """
        Получить инструменты в формате, готовом для передачи в Gemini.

        Returns:
            Список с объектом function_declarations.
        """
        schemas = self.get_schemas()
        if not schemas:
            return []
        return [{"function_declarations": schemas}]

    @property
    def tool_names(self) -> list[str]:
        """Список имён зарегистрированных инструментов."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# Глобальный экземпляр реестра
registry = ToolRegistry()

# Удобный алиас для декоратора
register_tool = registry.register
