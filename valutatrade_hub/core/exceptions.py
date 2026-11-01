class ValutaTradeError(Exception):
    """Базовое исключение проекта."""


class CurrencyNotFoundError(ValutaTradeError):
    def __init__(self, code) -> None:
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class InsufficientFundsError(ValutaTradeError):
    def __init__(self, available: float, code: str, required: float) -> None:
        self.available = available
        self.code = code
        self.required = required
        super().__init__(
            f"Недостаточно средств: доступно {available:.4f} {code}, "
            f"требуется {required:.4f} {code}"
        )


class ApiRequestError(ValutaTradeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")


class StorageError(ValutaTradeError):
    """Ошибка чтения/записи JSON-хранилища.

    Возникает в ``DatabaseManager.read``/``write`` и пробрасывается
    вызывающему коду как есть (``dispatch`` ловит ``ValutaTradeError``).
    """
