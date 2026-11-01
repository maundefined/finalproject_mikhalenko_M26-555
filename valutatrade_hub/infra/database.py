import json
import os

from valutatrade_hub.core.exceptions import StorageError


class DatabaseManager:
    """Singleton-абстракция над JSON-хранилищем.

    Почему ``__new__``: те же причины, что у ``SettingsLoader`` — минимальный
    код, один экземпляр на процесс, никакой возни с метаклассами.

    Все операции — «безопасные»:
      * ``read``   — не падает на отсутствующем файле (возвращает ``default``);
      * ``write``  — атомарная запись через ``*.tmp`` + ``os.replace``,
                     чтобы не оставить файл в «полу-записанном» состоянии;
      * ``transaction`` — read → mutator → write; при исключении в mutator
                     файл **не** изменяется.
    """

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
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return default
        except OSError as exc:
            raise StorageError(
                f"Не удалось прочитать {path}: {exc}"
            ) from exc

        if not content.strip():
            return default

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise StorageError(
                f"Не удалось прочитать {path}: {exc}"
            ) from exc

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
        """Read → mutator(data) → write.

        Если ``mutator`` бросает исключение — файл не перезаписывается,
        а исключение пробрасывается вызывающему.
        """
        data = self.read(path, default)
        new_data = mutator(data)
        self.write(path, new_data)
        return new_data


db = DatabaseManager()
