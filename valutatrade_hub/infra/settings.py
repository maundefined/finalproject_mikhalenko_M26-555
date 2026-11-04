import json
import os

try:
    import tomllib
except ImportError:
    tomllib = None


class SettingsLoader:
    """Singleton-загрузчик конфигурации проекта."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._data: dict = {}
        self.reload()

    def get(self, key: str, default=None):
        """Вернуть значение конфигурации или default, если ключа нет."""
        return self._data.get(key, default)

    def reload(self) -> None:
        """Перечитать конфигурацию из всех источников."""
        config: dict = {}
        config.update(self._defaults())
        config.update(self._load_config_json())
        config.update(self._load_pyproject())
        self._data = config

    @staticmethod
    def _defaults() -> dict:
        return {
            "data_dir": "data",
            "users_path": "data/users.json",
            "portfolios_path": "data/portfolios.json",
            "rates_path": "data/rates.json",
            "rates_ttl_seconds": 300,
            "default_base_currency": "USD",
            "log_path": "logs/actions.log",
            "parser_log_path": "logs/parser.log",
            "log_format": "%(levelname)s %(asctime)s %(message)s",
            "log_datefmt": "%Y-%m-%dT%H:%M:%S",
            "log_level": "INFO",
            "log_max_bytes": 1_000_000,
            "log_backup_count": 5,
        }

    @staticmethod
    def _load_config_json() -> dict:
        path = "config.json"
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _load_pyproject() -> dict:
        path = "pyproject.toml"
        if tomllib is None or not os.path.isfile(path):
            return {}
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, ValueError):
            return {}
        section = data.get("tool", {}).get("valutatrade", {})
        return section if isinstance(section, dict) else {}


settings = SettingsLoader()
