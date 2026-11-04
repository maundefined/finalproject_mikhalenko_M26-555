import logging
from datetime import UTC, datetime

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import parser_config
from valutatrade_hub.parser_service.storage import ParserStorage

logger = logging.getLogger("valutatrade.parser")


class RatesUpdater:
    """Координатор обновления."""

    def __init__(
        self,
        clients: list[BaseApiClient],
        storage: ParserStorage,
        config=None,
    ) -> None:
        self._clients = clients
        self._storage = storage
        self._config = config or parser_config

    def run_update(self, source: str | None = None) -> dict:
        source = source.lower() if source else None
        if source and source not in ("coingecko", "exchangerate"):
            raise ApiRequestError(f"неизвестный источник '{source}'")

        logger.info("Starting rates update...")

        all_rates: dict[str, float] = {}
        sources_used: dict[str, str] = {}
        meta_by_pair: dict[str, dict] = {}
        errors: list[str] = []

        for client in self._clients:
            if source and client.source_key != source:
                logger.info("Skipping %s (filtered by --source)", client.source_name)
                continue
            label = client.source_name
            try:
                rates = client.fetch_rates()
            except ApiRequestError as exc:
                logger.error("Failed to fetch from %s: %s", label, exc)
                errors.append(f"{label}: {exc}")
                continue
            logger.info("Fetching from %s... OK (%d rates)", label, len(rates))
            for pair, rate in rates.items():
                all_rates[pair] = rate
                sources_used[pair] = label
                meta = {
                    "raw_id": self._raw_id(pair, label),
                    "request_ms": client.last_request_ms,
                    "status_code": client.last_status_code,
                }
                if client.last_etag:
                    meta["etag"] = client.last_etag
                meta_by_pair[pair] = meta

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        if all_rates:
            snapshot = {
                pair: {
                    "rate": rate,
                    "updated_at": now,
                    "source": sources_used[pair],
                }
                for pair, rate in all_rates.items()
            }
            logger.info(
                "Writing %d rates to %s...",
                len(snapshot),
                self._config.RATES_FILE_PATH,
            )
            written = self._storage.update_rates(snapshot, now)

            records = []
            for pair, rate in all_rates.items():
                try:
                    from_code, to_code = pair.split("_", 1)
                except ValueError:
                    continue
                records.append(
                    {
                        "id": f"{pair}_{now}",
                        "from_currency": from_code,
                        "to_currency": to_code,
                        "rate": rate,
                        "timestamp": now,
                        "source": sources_used[pair],
                        "meta": meta_by_pair.get(pair, {}),
                    }
                )
            history_added = self._storage.record_history(records)
        else:
            written = 0
            history_added = 0
            logger.warning("No rates received from any source.")

        return {
            "total_rates": len(all_rates),
            "written_to_cache": written,
            "history_added": history_added,
            "last_refresh": now,
            "errors": errors,
        }

    def _raw_id(self, pair: str, source: str) -> str:
        from_code = pair.split("_", 1)[0]
        if source == "CoinGecko":
            return self._config.CRYPTO_ID_MAP.get(from_code, from_code.lower())
        return from_code


def build_default_updater() -> RatesUpdater:
    clients = [CoinGeckoClient(), ExchangeRateApiClient()]
    storage = ParserStorage(
        parser_config.RATES_FILE_PATH, parser_config.HISTORY_FILE_PATH
    )
    return RatesUpdater(clients, storage)
