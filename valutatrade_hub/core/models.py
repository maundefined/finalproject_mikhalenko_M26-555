import hashlib
import math
from datetime import datetime

from valutatrade_hub.core import utils
from valutatrade_hub.core.exceptions import InsufficientFundsError


class User:
    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id должен быть положительным целым числом")
        self._user_id = user_id
        self.username = username
        self.hashed_password = hashed_password
        self.salt = salt
        self.registration_date = registration_date

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256((password + self._salt).encode("utf-8")).hexdigest()

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @hashed_password.setter
    def hashed_password(self, value: str) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError("Хеш пароля должен быть непустой строкой")
        self._hashed_password = value

    @property
    def salt(self) -> str:
        return self._salt

    @salt.setter
    def salt(self, value: str) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError("Соль должна быть непустой строкой")
        self._salt = value

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    @registration_date.setter
    def registration_date(self, value: datetime) -> None:
        if not isinstance(value, datetime):
            raise TypeError("registration_date должен быть datetime")
        self._registration_date = value

    def get_user_info(self) -> None:
        print(f"ID: {self._user_id}")
        print(f"Имя пользователя: {self._username}")
        print(f"Дата регистрации: {self._registration_date.isoformat()}")

    def change_password(self, new_password: str) -> None:
        if len(new_password) < utils.MIN_PASSWORD_LEN:
            raise ValueError(
                f"Пароль не соответсвует парольной политике: новый пароль "
                f"должен содержать больше {utils.MIN_PASSWORD_LEN} символов"
            )
        self._hashed_password = self._hash_password(new_password)

    def verify_password(self, password: str) -> bool:
        return self._hash_password(password) == self._hashed_password


class Wallet:
    def __init__(self, currency_code: str, balance: float = 0.0):
        self.currency_code = currency_code
        self.balance = balance

    @property
    def currency_code(self) -> str:
        return self._currency_code

    @currency_code.setter
    def currency_code(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Код валюты должен быть непустой строкой")
        self._currency_code = value.strip().upper()

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if not math.isfinite(float(value)):
            raise ValueError("Баланс должен быть конечным числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise TypeError("Сумма должна быть числом")
        if not math.isfinite(float(amount)) or amount <= 0:
            raise ValueError(
                "Сумма пополнения должна быть положительным конечным числом"
            )
        self._balance += float(amount)

    def withdraw(self, amount: float) -> None:
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise TypeError("Сумма должна быть числом")
        if not math.isfinite(float(amount)) or amount <= 0:
            raise ValueError("Сумма снятия должна быть положительным конечным числом")
        if amount > self._balance:
            raise InsufficientFundsError(
                available=self._balance,
                code=self._currency_code,
                required=float(amount),
            )
        self._balance -= float(amount)

    def get_balance_info(self) -> None:
        print(f"Валюта: {self._currency_code}")
        print(f"Текущий баланс: {self._balance}")


class Portfolio:
    """Портфель одного пользователя с уникальными валютными кошельками."""

    STUB_RATES = utils._to_usd_rates(utils.STUB_EXCHANGE_RATES)

    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ) -> None:
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id должен быть положительным целым числом")
        self._user_id = user_id
        self._wallets = dict(wallets) if wallets is not None else {}
        self._user = user

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def user(self) -> User | None:
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Вернуть поверхностную копию словаря кошельков."""
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> None:
        """Создать кошелёк, если валюта ещё не представлена в портфеле."""
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты должен быть непустой строкой")
        code = currency_code.strip().upper()
        if code in self._wallets:
            raise ValueError(f"Кошелёк для валюты {code} уже существует")
        self._wallets[code] = Wallet(code)

    def get_wallet(self, currency_code: str) -> Wallet | None:
        """Вернуть кошелёк по коду валюты."""
        if not isinstance(currency_code, str):
            return None
        return self._wallets.get(currency_code.strip().upper())

    def get_total_value(self, base_currency: str = "USD") -> float:
        """Рассчитать стоимость портфеля в базовой валюте по курсам к USD."""
        if not isinstance(base_currency, str):
            raise TypeError("base_currency должен быть строкой")
        base = base_currency.strip().upper()
        if base not in self.STUB_RATES:
            raise ValueError(f"Неизвестная валюта: {base}")
        base_rate = self.STUB_RATES[base]
        total_in_usd = sum(
            wallet.balance * self.STUB_RATES.get(code, 0.0)
            for code, wallet in self._wallets.items()
        )
        return total_in_usd / base_rate
