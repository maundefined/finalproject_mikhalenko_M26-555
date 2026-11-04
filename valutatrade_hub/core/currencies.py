from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError


class Currency(ABC):
    """Базовый класс валюты."""

    def __init__(self, name: str, code: str) -> None:
        self.name = name
        self.code = code

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("name должен быть строкой")
        if not value.strip():
            raise ValueError("name не может быть пустым")
        self._name = value.strip()

    @property
    def code(self) -> str:
        return self._code

    @code.setter
    def code(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("code должен быть строкой")
        normalized = value.strip().upper()
        if any(ch.isspace() for ch in normalized):
            raise ValueError("code не должен содержать пробелов")
        if not (2 <= len(normalized) <= 5):
            raise ValueError("code должен состоять из 2–5 символов")
        self._code = normalized

    @abstractmethod
    def get_display_info(self) -> str:
        """Строковое представление валюты для UI и логов."""


class FiatCurrency(Currency):
    def __init__(self, name: str, code: str, issuing_country: str) -> None:
        super().__init__(name, code)
        self.issuing_country = issuing_country

    @property
    def issuing_country(self) -> str:
        return self._issuing_country

    @issuing_country.setter
    def issuing_country(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("issuing_country должен быть строкой")
        if not value.strip():
            raise ValueError("issuing_country не может быть пустым")
        self._issuing_country = value.strip()

    def get_display_info(self) -> str:
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    def __init__(
        self,
        name: str,
        code: str,
        algorithm: str,
        market_cap: float,
    ) -> None:
        super().__init__(name, code)
        self.algorithm = algorithm
        self.market_cap = market_cap

    @property
    def algorithm(self) -> str:
        return self._algorithm

    @algorithm.setter
    def algorithm(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("algorithm должен быть строкой")
        if not value.strip():
            raise ValueError("algorithm не может быть пустым")
        self._algorithm = value.strip()

    @property
    def market_cap(self) -> float:
        return self._market_cap

    @market_cap.setter
    def market_cap(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("market_cap должен быть числом")
        if value < 0:
            raise ValueError("market_cap не может быть отрицательным")
        self._market_cap = float(value)

    def get_display_info(self) -> str:
        mcap = f"{self.market_cap:.2e}".replace("e+", "e")
        return (
            f"[CRYPTO] {self.code} — {self.name} (Algo: {self.algorithm}, MCAP: {mcap})"
        )


_REGISTRY: dict[str, Currency] = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "GBP": FiatCurrency("British Pound", "GBP", "United Kingdom"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Ethash", 3.5e11),
    "SOL": CryptoCurrency("Solana", "SOL", "Proof of History", 6.7e10),
}


def get_currency(code: str) -> Currency:
    if not isinstance(code, str):
        raise CurrencyNotFoundError(code)
    key = code.strip().upper()
    if key not in _REGISTRY:
        raise CurrencyNotFoundError(key)
    return _REGISTRY[key]


def supported_codes() -> list[str]:
    """Список поддерживаемых кодов валют (для подсказок в CLI)."""
    return sorted(_REGISTRY.keys())
