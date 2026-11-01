import hashlib
from datetime import datetime

MIN_PASSWORD_LEN = 4

exchange_rates = {'EUR_USD': 1.0786,
                  'BTC_USD': 59337.21,              
                  'RUB_USD': 0.01016,                 
                  'ETH_USD': 3720.00}

class User:
    def __init__(self, user_id: int, username: str,
        hashed_password: str, salt: str, registration_date: datetime,):
        self._user_id = user_id
        self._username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

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
        if not value or not value.strip():
            raise ValueError('Имя пользователя не может быть пустым')
        self._username = value

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @hashed_password.setter
    def hashed_password(self, value: str) -> None:
        self._hashed_password = value

    @property
    def salt(self) -> str:
        return self._salt

    @salt.setter
    def salt(self, value: str) -> None:
        self._salt = value

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    @registration_date.setter
    def registration_date(self, value: datetime) -> None:
        self._registration_date = value

    def get_user_info(self) -> None:
        print(f'ID: {self._user_id}')
        print(f'Имя пользователя: {self._username}')
        print(f'Дата регистрации: {self._registration_date.isoformat()}')

    def change_password(self, new_password: str) -> None:
        if len(new_password) < MIN_PASSWORD_LEN:
            raise ValueError(f'Пароль не соответсвует парольной политике: новый пароль '
                             f'должен быть содержать больше {MIN_PASSWORD_LEN} символов')
        self._hashed_password = self._hash_password(new_password)

    def verify_password(self, password: str) -> bool:
        return self._hash_password(password) == self._hashed_password

class Wallet:
    def __init__(self, currency_code: str, balance: float = 0.0):
        self._currency_code = currency_code
        self._balance = balance

    @property
    def currency_code(self) -> str:
        return self._currency_code

    @currency_code.setter
    def currency_code(self, value: str) -> None:
        if not value or not value.strip():
            raise ValueError('Код валюты не может быть пустым')
        self._currency_code = value

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError('Баланс должен быть числом')
        if value < 0:
            raise ValueError('Баланс не может быть отрицательным')
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise TypeError('Сумма должна быть числом')
        if amount <= 0:
            raise ValueError('Сумма пополнения должна быть положительной')
        self._balance += float(amount)

    def withdraw(self, amount: float) -> None:
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise TypeError('Сумма должна быть числом')
        if amount <= 0:
            raise ValueError('Сумма снятия должна быть положительной')
        if amount > self._balance:
            raise ValueError('Недостаточно средств на балансе')
        self._balance -= float(amount)

    def get_balance_info(self) -> None:
        print(f'Валюта: {self._currency_code}')
        print(f'Текущий баланс: {self._balance}')

class Portfolio:
    def __init__(self, user_id: int, wallets: dict[str, Wallet] | None = None, 
                                            user: User | None = None) -> None:
        self._user_id = user_id
        self._wallets = wallets if wallets is not None else {}
        self._user = user

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def user(self):
        return self._user

    @property
    def wallets(self) -> dict:
        return dict(self._wallets)

    def add_currency(self, currency_code: str) -> None:
        if not currency_code or not currency_code.strip():
            raise ValueError('Код валюты не может быть пустым')
        if currency_code in self._wallets:
            raise ValueError(f'Кошелёк для валюты {currency_code} уже существует')
        self._wallets[currency_code] = Wallet(currency_code)

    def get_wallet(self, currency_code: str):
        return self._wallets.get(currency_code)

    def get_total_value(self, base_currency: str = "USD") -> float:
        if base_currency not in self.exchange_rates:
            raise ValueError(f'Неизвестная валюта: {base_currency}')
        base_rate = self.exchange_rates[base_currency]
        total_in_usd = 0.0
        for code, wallet in self._wallets.items():
            rate = self.exchange_rates.get(code, 0.0)
            total_in_usd += wallet.balance * rate
        return total_in_usd / base_rate