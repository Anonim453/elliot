"""
Системные инструменты для голосового ассистента Elliot.

Набор функций для управления компьютером через голосовые команды:
громкость, приложения, файлы, системная информация и т.д.
"""

import datetime
import logging
import os
import subprocess
import webbrowser
from pathlib import Path

import psutil

from core.tools.registry import register_tool

logger = logging.getLogger(__name__)


# ============================================================
# Маппинг русских названий приложений в исполняемые файлы
# ============================================================
_APP_MAP: dict[str, str] = {
    # Браузеры
    "браузер": "start msedge",
    "хром": "start chrome",
    "chrome": "start chrome",
    "firefox": "start firefox",
    "edge": "start msedge",
    # Системные
    "блокнот": "notepad",
    "notepad": "notepad",
    "калькулятор": "calc",
    "calculator": "calc",
    "проводник": "explorer",
    "explorer": "explorer",
    "диспетчер задач": "taskmgr",
    "task manager": "taskmgr",
    "командная строка": "cmd",
    "cmd": "cmd",
    "powershell": "powershell",
    "терминал": "wt",
    "terminal": "wt",
    # Мультимедиа
    "paint": "mspaint",
    "пайнт": "mspaint",
    "ножницы": "snippingtool",
    # Офис
    "word": "start winword",
    "excel": "start excel",
    "powerpoint": "start powerpnt",
    # Настройки
    "настройки": "start ms-settings:",
    "параметры": "start ms-settings:",
}


# ============================================================
# Инструменты
# ============================================================

@register_tool
def set_volume(level: int) -> str:
    """Установить уровень громкости системы.

    Args:
        level: Уровень громкости от 0 до 100.
    """
    try:
        # Нормализация в допустимый диапазон
        level = max(0, min(100, level))

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)

        # pycaw работает со шкалой 0.0-1.0
        scalar_volume = level / 100.0
        volume.SetMasterVolumeLevelScalar(scalar_volume, None)

        logger.info("Громкость установлена: %d%%", level)
        return f"Громкость установлена на {level}%"

    except Exception as e:
        logger.exception("Ошибка установки громкости")
        return f"Не удалось установить громкость: {e}"


@register_tool
def open_application(app_name: str) -> str:
    """Открыть приложение на компьютере.

    Args:
        app_name: Название приложения (например: блокнот, калькулятор, браузер, chrome).
    """
    try:
        app_key = app_name.lower().strip()
        command = _APP_MAP.get(app_key)

        if command:
            subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Приложение запущено: %s -> %s", app_name, command)
            return f"Приложение '{app_name}' запущено"
        else:
            # Попытка запустить как есть
            subprocess.Popen(
                f"start {app_key}",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Попытка запуска: %s", app_name)
            return f"Попытка запустить '{app_name}'"

    except Exception as e:
        logger.exception("Ошибка запуска приложения '%s'", app_name)
        return f"Не удалось открыть '{app_name}': {e}"


@register_tool
def close_application(app_name: str) -> str:
    """Закрыть приложение на компьютере.

    Args:
        app_name: Название приложения или имя процесса (например: блокнот, chrome).
    """
    # Маппинг названий в имена процессов
    process_map: dict[str, str] = {
        "блокнот": "notepad.exe",
        "notepad": "notepad.exe",
        "калькулятор": "Calculator.exe",
        "calculator": "Calculator.exe",
        "хром": "chrome.exe",
        "chrome": "chrome.exe",
        "firefox": "firefox.exe",
        "edge": "msedge.exe",
        "браузер": "msedge.exe",
        "word": "WINWORD.EXE",
        "excel": "EXCEL.EXE",
        "проводник": "explorer.exe",
        "explorer": "explorer.exe",
    }

    try:
        app_key = app_name.lower().strip()
        process_name = process_map.get(app_key, f"{app_key}.exe")

        # Ищем и завершаем процессы
        killed = 0
        for proc in psutil.process_iter(["name"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == process_name.lower():
                    proc.terminate()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if killed > 0:
            logger.info("Закрыто процессов '%s': %d", process_name, killed)
            return f"Приложение '{app_name}' закрыто ({killed} процессов)"
        else:
            return f"Процесс '{app_name}' не найден"

    except Exception as e:
        logger.exception("Ошибка закрытия приложения '%s'", app_name)
        return f"Не удалось закрыть '{app_name}': {e}"


@register_tool
def get_system_stats() -> str:
    """Получить информацию о системе: загрузка CPU, RAM, диска."""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")

        stats = (
            f"Процессор: {cpu_percent}% загрузки. "
            f"Оперативная память: {memory.percent}% использовано "
            f"({memory.used // (1024**3)} из {memory.total // (1024**3)} ГБ). "
            f"Диск C: {disk.percent}% занято "
            f"({disk.used // (1024**3)} из {disk.total // (1024**3)} ГБ свободно "
            f"{disk.free // (1024**3)} ГБ)."
        )

        logger.info("Статистика системы получена")
        return stats

    except Exception as e:
        logger.exception("Ошибка получения системной статистики")
        return f"Не удалось получить информацию о системе: {e}"


@register_tool
def open_website(url: str) -> str:
    """Открыть веб-сайт в браузере по умолчанию.

    Args:
        url: URL сайта (например: https://google.com).
    """
    try:
        # Добавляем протокол если отсутствует
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        webbrowser.open(url)
        logger.info("Открыт сайт: %s", url)
        return f"Сайт {url} открыт в браузере"

    except Exception as e:
        logger.exception("Ошибка открытия сайта '%s'", url)
        return f"Не удалось открыть сайт: {e}"


@register_tool
def search_web(query: str) -> str:
    """Выполнить поиск в Google.

    Args:
        query: Поисковый запрос.
    """
    try:
        import urllib.parse
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(search_url)
        logger.info("Поиск в Google: %s", query)
        return f"Открыт поиск Google: '{query}'"

    except Exception as e:
        logger.exception("Ошибка поиска '%s'", query)
        return f"Не удалось выполнить поиск: {e}"


@register_tool
def execute_command(command: str) -> str:
    """Выполнить команду PowerShell на компьютере. Используй с осторожностью.

    Args:
        command: Команда PowerShell для выполнения.
    """
    try:
        logger.warning("Выполнение команды: %s", command)

        result = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="cp866",
            errors="replace",
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0:
            response = f"Команда выполнена успешно."
            if output:
                # Ограничиваем длину вывода
                response += f" Результат: {output[:500]}"
            logger.info("Команда выполнена: %s", command)
            return response
        else:
            error_msg = f"Ошибка выполнения (код {result.returncode})"
            if error:
                error_msg += f": {error[:300]}"
            logger.error("Ошибка команды: %s", error_msg)
            return error_msg

    except subprocess.TimeoutExpired:
        logger.error("Таймаут команды: %s", command)
        return "Команда превысила время ожидания (30 секунд)"
    except Exception as e:
        logger.exception("Ошибка выполнения команды '%s'", command)
        return f"Не удалось выполнить команду: {e}"


@register_tool
def control_media(action: str) -> str:
    """Управление медиа-воспроизведением (play, pause, next, prev, stop).

    Args:
        action: Действие — play, pause, next, prev или stop.
    """
    try:
        import keyboard as kb

        action_map: dict[str, tuple[str, str]] = {
            "play": ("play/pause media", "Воспроизведение/пауза"),
            "pause": ("play/pause media", "Воспроизведение/пауза"),
            "play_pause": ("play/pause media", "Воспроизведение/пауза"),
            "next": ("next track", "Следующий трек"),
            "prev": ("previous track", "Предыдущий трек"),
            "previous": ("previous track", "Предыдущий трек"),
            "stop": ("stop media", "Стоп"),
        }

        action_lower = action.lower().strip()
        if action_lower not in action_map:
            return f"Неизвестное действие '{action}'. Доступны: play, pause, next, prev, stop"

        key, description = action_map[action_lower]
        kb.send(key)
        logger.info("Медиа-управление: %s", description)
        return description

    except Exception as e:
        logger.exception("Ошибка управления медиа")
        return f"Не удалось выполнить действие: {e}"


@register_tool
def system_power(action: str) -> str:
    """Управление питанием компьютера (shutdown, restart, sleep, lock).

    Args:
        action: Действие — shutdown (выключить), restart (перезагрузить), sleep (сон), lock (блокировка).
    """
    try:
        action_lower = action.lower().strip()

        if action_lower == "shutdown":
            logger.warning("Выключение компьютера!")
            os.system("shutdown /s /t 5")
            return "Компьютер будет выключен через 5 секунд"

        elif action_lower == "restart":
            logger.warning("Перезагрузка компьютера!")
            os.system("shutdown /r /t 5")
            return "Компьютер будет перезагружен через 5 секунд"

        elif action_lower == "sleep":
            logger.info("Перевод в режим сна")
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            return "Компьютер переведён в режим сна"

        elif action_lower == "lock":
            logger.info("Блокировка экрана")
            os.system("rundll32.exe user32.dll,LockWorkStation")
            return "Экран заблокирован"

        else:
            return f"Неизвестное действие '{action}'. Доступны: shutdown, restart, sleep, lock"

    except Exception as e:
        logger.exception("Ошибка управления питанием")
        return f"Не удалось выполнить действие: {e}"


@register_tool
def get_time() -> str:
    """Получить текущую дату и время."""
    now = datetime.datetime.now()

    # Названия дней недели и месяцев на русском
    days_ru = [
        "понедельник", "вторник", "среда", "четверг",
        "пятница", "суббота", "воскресенье",
    ]
    months_ru = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]

    day_name = days_ru[now.weekday()]
    month_name = months_ru[now.month]

    return (
        f"Сейчас {now.hour}:{now.minute:02d}, "
        f"{now.day} {month_name} {now.year} года, {day_name}."
    )


@register_tool
def file_operations(action: str, path: str, content: str = "") -> str:
    """Операции с файлами: создать, прочитать или удалить файл.

    Args:
        action: Действие — create (создать), read (прочитать), delete (удалить).
        path: Путь к файлу.
        content: Содержимое файла (только для create).
    """
    try:
        file_path = Path(path)
        action_lower = action.lower().strip()

        if action_lower == "create":
            # Создаём директорию если не существует
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            logger.info("Файл создан: %s", path)
            return f"Файл '{path}' создан успешно"

        elif action_lower == "read":
            if not file_path.exists():
                return f"Файл '{path}' не найден"
            text = file_path.read_text(encoding="utf-8")
            # Ограничиваем вывод
            if len(text) > 1000:
                text = text[:1000] + "\n... (файл обрезан, слишком длинный)"
            logger.info("Файл прочитан: %s", path)
            return f"Содержимое файла '{path}':\n{text}"

        elif action_lower == "delete":
            if not file_path.exists():
                return f"Файл '{path}' не найден"
            file_path.unlink()
            logger.info("Файл удалён: %s", path)
            return f"Файл '{path}' удалён"

        else:
            return f"Неизвестное действие '{action}'. Доступны: create, read, delete"

    except PermissionError:
        return f"Нет доступа к файлу '{path}'"
    except Exception as e:
        logger.exception("Ошибка файловой операции")
        return f"Ошибка: {e}"
