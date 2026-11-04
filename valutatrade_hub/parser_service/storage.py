import json
import os
from datetime import datetime

from valutatrade_hub.core.exceptions import StorageError


class ParserStorage:
    """Операции чтения/записи exchange_rates.json и rates.json."""

    def __init__(self, rates_path: str, history_path: str) -> None:
        self._rates_path = rates_path
        self._history_path = history_path

    def record_history(self, records: list) -> int:
        history = self._read_history()
        added = 0
        for record in records:
            rid = record["id"]
            if rid not in history:
                history[rid] = record
                added += 1
        if added:
            self._write_json_atomic(self._history_path, history)
        return added

    def update_rates(self, pairs: dict, refreshed_at: str) -> int:
        current = self._read_rates()
        existing = current.get("pairs", {}) if isinstance(current, dict) else {}
        if not isinstance(existing, dict):
            existing = {}
        written = 0
        for pair, entry in pairs.items():
            prev = existing.get(pair)
            if not isinstance(prev, dict) or self._is_newer(
                entry.get("updated_at"), prev.get("updated_at")
            ):
                existing[pair] = entry
                written += 1
        self._write_json_atomic(
            self._rates_path,
            {
                "pairs": existing,
                "last_refresh": refreshed_at,
            },
        )
        return written

    def read_cache(self) -> dict:
        """Вернуть содержимое rates.json (или {} при отсутствии)."""
        return self._read_rates()

    def _read_history(self) -> dict:
        data = self._read_json(self._history_path, {})
        if not isinstance(data, dict):
            raise StorageError(
                f"Файл {self._history_path} повреждён: ожидался JSON-объект."
            )
        return data

    def _read_rates(self) -> dict:
        data = self._read_json(self._rates_path, {})
        if not isinstance(data, dict):
            raise StorageError(
                f"Файл {self._rates_path} повреждён: ожидался JSON-объект."
            )
        return data

    @staticmethod
    def _read_json(path: str, default):
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
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise StorageError(f"Не удалось прочитать {path}: {exc}") from exc

    @staticmethod
    def _write_json_atomic(path: str, data) -> None:
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

    @staticmethod
    def _is_newer(new_ts, old_ts) -> bool:
        if not new_ts:
            return False
        if not old_ts:
            return True
        try:
            return datetime.fromisoformat(new_ts.rstrip("Z")) > datetime.fromisoformat(
                old_ts.rstrip("Z")
            )
        except ValueError:
            return True
