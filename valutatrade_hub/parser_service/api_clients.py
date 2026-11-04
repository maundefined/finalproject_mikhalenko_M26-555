import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import parser_config


class BaseApiClient(ABC):
    """Базовый класс клиента API.

    Реализации возвращают стандартизированный словарь {PAIR: rate}."""

    source_key: str = ""
    source_name: str = ""

    def __init__(self, config=None) -> None:
        self._config = config or parser_config
        self.last_status_code: int = 0
        self.last_request_ms: int = 0
        self.last_etag: str = ""

    @abstractmethod
    def fetch_rates(self) -> dict:
        """Вернуть {PAIR: rate}; бросить ApiRequestError при сбое."""

    def _get_json(self, url: str) -> dict:
        start = time.time()
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(
                req, timeout=self._config.REQUEST_TIMEOUT
            ) as resp:
                self.last_status_code = resp.status
                self.last_etag = resp.headers.get("ETag", "") or ""
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise ApiRequestError(
                    f"{self.source_name}: лимит запросов (429)"
                ) from exc
            raise ApiRequestError(
                f"{self.source_name}: HTTP {exc.code} {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ApiRequestError(
                f"{self.source_name}: network error ({exc.reason})"
            ) from exc
        except TimeoutError as exc:
            raise ApiRequestError(f"{self.source_name}: timeout") from exc
        except Exception as exc:
            raise ApiRequestError(
                f"{self.source_name}: request failed ({exc})"
            ) from exc
        finally:
            self.last_request_ms = int((time.time() - start) * 1000)

        if self.last_status_code != 200:
            raise ApiRequestError(f"{self.source_name}: HTTP {self.last_status_code}")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ApiRequestError(f"{self.source_name}: invalid JSON ({exc})") from exc
        if not isinstance(payload, dict):
            raise ApiRequestError(f"{self.source_name}: unexpected response type")
        return payload


class CoinGeckoClient(BaseApiClient):
    source_key = "coingecko"
    source_name = "CoinGecko"

    def fetch_rates(self) -> dict:
        ids = [
            self._config.CRYPTO_ID_MAP[c]
            for c in self._config.CRYPTO_CURRENCIES
            if c in self._config.CRYPTO_ID_MAP
        ]
        if not ids:
            return {}
        vs = self._config.BASE_CURRENCY.lower()
        params = {"ids": ",".join(ids), "vs_currencies": vs}
        url = f"{self._config.COINGECKO_URL}?{urllib.parse.urlencode(params)}"
        payload = self._get_json(url)

        result = {}
        for code in self._config.CRYPTO_CURRENCIES:
            cg_id = self._config.CRYPTO_ID_MAP.get(code)
            if not cg_id:
                continue
            entry = payload.get(cg_id)
            if not isinstance(entry, dict):
                continue
            rate = entry.get(vs)
            if (
                isinstance(rate, bool)
                or not isinstance(rate, (int, float))
                or not math.isfinite(float(rate))
                or rate <= 0
            ):
                continue
            result[f"{code}_{self._config.BASE_CURRENCY}"] = float(rate)
        return result


class ExchangeRateApiClient(BaseApiClient):
    source_key = "exchangerate"
    source_name = "ExchangeRate-API"

    def fetch_rates(self) -> dict:
        if not self._config.EXCHANGERATE_API_KEY:
            raise ApiRequestError(
                "ExchangeRate-API: ключ не задан (EXCHANGERATE_API_KEY)"
            )
        base = self._config.BASE_CURRENCY
        url = (
            f"{self._config.EXCHANGERATE_API_URL}/"
            f"{self._config.EXCHANGERATE_API_KEY}/latest/{base}"
        )
        payload = self._get_json(url)

        if payload.get("result") != "success":
            raise ApiRequestError(
                f"ExchangeRate-API: {payload.get('error-type', 'unknown')}"
            )

        rates = payload.get("conversion_rates")
        if not isinstance(rates, dict):
            rates = payload.get("rates")
        if not isinstance(rates, dict):
            raise ApiRequestError(
                "ExchangeRate-API: в ответе нет conversion_rates/rates"
            )

        result = {}
        for code in self._config.FIAT_CURRENCIES:
            rate = rates.get(code)
            if (
                isinstance(rate, bool)
                or not isinstance(rate, (int, float))
                or not math.isfinite(float(rate))
                or rate <= 0
            ):
                continue
            result[f"{code}_{base}"] = 1.0 / float(rate)

        if not result:
            raise ApiRequestError(
                "ExchangeRate-API: пустой ответ, "
                f"не найдено ни одной из {self._config.FIAT_CURRENCIES}"
            )
        return result
