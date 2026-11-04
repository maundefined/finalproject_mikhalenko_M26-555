import logging
import threading

from valutatrade_hub.parser_service.updater import RatesUpdater

logger = logging.getLogger("valutatrade.parser.scheduler")


class Scheduler:
    """Фоновый планировщик периодического обновления."""

    def __init__(self, updater: RatesUpdater, interval_seconds: int = 600) -> None:
        self._updater = updater
        self._interval = max(1, int(interval_seconds))
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._updater.run_update()
            except Exception as exc:
                logger.exception("scheduled update failed: %s", exc)
            self._stop_event.wait(self._interval)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="parser-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
