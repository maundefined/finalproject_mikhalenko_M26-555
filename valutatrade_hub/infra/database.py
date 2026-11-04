import json
import os

from valutatrade_hub.core.exceptions import StorageError


class DatabaseManager:
    """Singleton-абстракция над JSON-хранилищем."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

    def read(self, path: str, default):
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return default
        except OSError as exc:
            raise StorageError(f"Не удалось прочитать {path}: {exc}") from exc

        if not content.strip():
            return default

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise StorageError(f"Не удалось прочитать {path}: {exc}") from exc

        if isinstance(default, list):
            if not isinstance(data, list):
                raise StorageError(
                    f"Файл {path} повреждён: ожидался JSON-массив, "
                    f"получено {type(data).__name__}. "
                    f"Удалите файл — он будет создан автоматически."
                )
            if not all(isinstance(x, dict) for x in data):
                raise StorageError(
                    f"Файл {path} повреждён: элементы массива должны быть "
                    f"объектами. Удалите файл — он будет создан автоматически."
                )
        elif isinstance(default, dict) and not isinstance(data, dict):
            raise StorageError(
                f"Файл {path} повреждён: ожидался JSON-объект, "
                f"получено {type(data).__name__}."
            )
        return data

    def write(self, path: str, data) -> None:
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        tmp = f"{path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except (OSError, TypeError) as exc:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise StorageError(f"Не удалось записать {path}: {exc}") from exc

    def transaction(self, path: str, default, mutator):
        """Read → mutator(data) in-place → write(data)."""
        data = self.read(path, default)
        mutator(data)
        self.write(path, data)
        return data


db = DatabaseManager()
