"""Бизнес-логика проекта.

Синглтон-настройки (settings):
  * rates_ttl_seconds — TTL кеша курсов (_is_cache_fresh);
  * default_base_currency — базовая валюта по умолчанию (get_portfolio_view);
  * пути JSON — в utils.USERS_PATH / PORTFOLIOS_PATH / RATES_PATH.

Синглтон-БД (db из infra.database):
  * все операции чтения/записи идут через DatabaseManager;
  * мутации — через db.transaction (read → mutator → write), что
    гарантирует: при исключении в мутаторе файл не перезаписывается.

Декораторы @log_action:
  * REGISTER, LOGIN — без verbose;
  * BUY, SELL — с verbose=True (плюс wallet=before->after,
    usd=before->after).
"""

import hashlib
import math
import time
from datetime import UTC, datetime

from valutatrade_hub.core import utils
from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
)
from valutatrade_hub.core.models import User, Wallet
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import db
from valutatrade_hub.infra.settings import settings

_current_user = None


def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def _user_from_dict(data: dict) -> User:
    return User(
        user_id=data["user_id"],
        username=data["username"],
        hashed_password=data["hashed_password"],
        salt=data["salt"],
        registration_date=datetime.fromisoformat(data["registration_date"]),
    )


def _wallet_from_dict(code: str, data: dict) -> Wallet:
    return Wallet(code, float(data.get("balance", 0.0)))


def _wallet_to_dict(wallet: Wallet) -> dict:
    return {"currency_code": wallet.currency_code, "balance": wallet.balance}


def _find_portfolio(portfolios: list, user_id: int):
    for p in portfolios:
        if p.get("user_id") == user_id:
            return p
    return None


def _usd_rate(code: str, rates: dict):
    if code == "USD":
        return 1.0
    pairs = rates.get("pairs") if isinstance(rates, dict) else None
    if not isinstance(pairs, dict):
        pairs = rates
    direct = pairs.get(f"{code}_USD")
    if isinstance(direct, dict):
        try:
            value = float(direct["rate"])
            return value if math.isfinite(value) and value > 0 else None
        except (KeyError, TypeError, ValueError):
            return None
    inverse = pairs.get(f"USD_{code}")
    if isinstance(inverse, dict):
        try:
            value = float(inverse["rate"])
            return 1.0 / value if math.isfinite(value) and value > 0 else None
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _rate(currency: str, base: str, rates: dict):
    if currency == base:
        return 1.0
    c = _usd_rate(currency, rates)
    b = _usd_rate(base, rates)
    if c is None or b is None:
        return None
    return c / b


def _require_rate(code: str, base: str, rates: dict) -> float:
    rate = _rate(code, base, rates)
    if rate is None:
        raise ApiRequestError(f"курс {code}→{base} недоступен")
    return rate


def _validate_amount(amount) -> float:
    if isinstance(amount, str):
        try:
            amount = float(amount)
        except ValueError:
            raise ValueError("'amount' должен быть положительным числом") from None
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise TypeError("'amount' должен быть положительным числом")
    amount = float(amount)
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return amount


@log_action("REGISTER")
def register_user(username: str, password: str) -> User:
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя пользователя не может быть пустым")
    username = username.strip()
    if not isinstance(password, str) or len(password) < utils.MIN_PASSWORD_LEN:
        raise ValueError(
            f"Пароль должен быть не короче {utils.MIN_PASSWORD_LEN} символов"
        )

    users = db.read(utils.USERS_PATH, [])
    for existing in users:
        if existing.get("username") == username:
            raise ValueError(f"Имя пользователя '{username}' уже занято")

    user_id = max((u["user_id"] for u in users), default=0) + 1

    salt = hashlib.sha256(f"{username}|{time.time()}|{user_id}".encode()).hexdigest()[
        :16
    ]
    hashed_password = _hash(password, salt)
    registration_date = datetime.now()

    user = User(user_id, username, hashed_password, salt, registration_date)

    def mutate_users(data):
        data.append(
            {
                "user_id": user.user_id,
                "username": user.username,
                "hashed_password": user.hashed_password,
                "salt": user.salt,
                "registration_date": user.registration_date.isoformat(),
            }
        )
        return data

    db.transaction(utils.USERS_PATH, [], mutate_users)

    def mutate_portfolios(data):
        data.append({"user_id": user_id, "wallets": {}})
        return data

    db.transaction(utils.PORTFOLIOS_PATH, [], mutate_portfolios)

    return user


@log_action("LOGIN")
def login_user(username: str, password: str) -> User:
    global _current_user

    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя пользователя не может быть пустым")
    username = username.strip()
    if not isinstance(password, str) or password == "":
        raise ValueError("Пароль не может быть пустым")

    users = db.read(utils.USERS_PATH, [])
    found = None
    for data in users:
        if data.get("username") == username:
            found = data
            break
    if found is None:
        raise ValueError(f"Пользователь '{username}' не найден")

    if _hash(password, found["salt"]) != found["hashed_password"]:
        raise ValueError("Неверный пароль")

    _current_user = _user_from_dict(found)
    return _current_user


def get_current_user() -> User | None:
    return _current_user


def _is_cache_fresh(rates: dict) -> bool:
    last = rates.get("last_refresh")
    if not last:
        return False
    try:
        dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return False
    ttl = max(0, int(settings.get("rates_ttl_seconds", 300)))
    age = (datetime.now(UTC) - dt.astimezone(UTC)).total_seconds()
    return 0 <= age < ttl


def _refresh_from_stub(rates: dict) -> None:
    if not utils.STUB_EXCHANGE_RATES:
        raise ApiRequestError("сервис курсов вернул пустой ответ")
    try:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        pairs = rates.get("pairs", {})
        if not isinstance(pairs, dict):
            pairs = {}
        had_cached_pairs = bool(pairs)
        for pair, value in utils.STUB_EXCHANGE_RATES.items():
            pairs.setdefault(pair, {"rate": value, "updated_at": now, "source": "Stub"})
        rates["pairs"] = pairs
        if not had_cached_pairs:
            rates["last_refresh"] = now
        db.write(utils.RATES_PATH, rates)
    except ApiRequestError:
        raise
    except Exception as exc:
        raise ApiRequestError(str(exc)) from exc


def get_rate(from_currency: str, to_currency: str) -> dict:
    code_from = get_currency(from_currency).code
    code_to = get_currency(to_currency).code

    rates = db.read(utils.RATES_PATH, {})

    rate = _rate(code_from, code_to, rates)
    if rate is None or not _is_cache_fresh(rates):
        try:
            from valutatrade_hub.parser_service.updater import build_default_updater

            build_default_updater().run_update()
            rates = db.read(utils.RATES_PATH, {})
        except (ApiRequestError, OSError, ValueError):
            rates = db.read(utils.RATES_PATH, {})

        rate = _rate(code_from, code_to, rates)
        if rate is None:
            _refresh_from_stub(rates)
            rates = db.read(utils.RATES_PATH, {})
            rate = _rate(code_from, code_to, rates)

    if rate is None:
        raise ApiRequestError(f"курс {code_from}→{code_to} недоступен")

    reverse = _rate(code_to, code_from, rates)

    return {
        "from": code_from,
        "to": code_to,
        "rate": rate,
        "reverse": reverse,
        "updated_at": rates.get("last_refresh", "—"),
    }


def get_portfolio_view(base: str | None = None) -> dict:
    user = get_current_user()
    if user is None:
        raise ValueError("Сначала выполните login")

    if base is None:
        base = settings.get("default_base_currency", "USD")
    base = base.upper()

    rates = db.read(utils.RATES_PATH, {})
    if _usd_rate(base, rates) is None:
        raise ValueError(f"Неизвестная базовая валюта '{base}'")

    portfolios = db.read(utils.PORTFOLIOS_PATH, [])
    portfolio = _find_portfolio(portfolios, user.user_id)
    wallets = {} if portfolio is None else portfolio.get("wallets", {})

    view = {
        "username": user.username,
        "base": base,
        "wallets": [],
        "total": 0.0,
    }
    for code, data in wallets.items():
        wallet = _wallet_from_dict(code, data)
        rate = _rate(code, base, rates)
        if rate is None:
            continue
        value = wallet.balance * rate
        view["wallets"].append(
            {
                "currency": code,
                "balance": wallet.balance,
                "value": value,
            }
        )
        view["total"] += value
    return view


@log_action("BUY", verbose=True)
def buy_currency(user_id: int, currency_code: str, amount) -> dict:
    code = get_currency(currency_code).code
    amount = _validate_amount(amount)

    base = utils.QUOTE_CURRENCY
    rates = db.read(utils.RATES_PATH, {})
    rate = _require_rate(code, base, rates)
    cost = amount * rate

    ctx = {}

    def mutate(portfolios):
        portfolio = _find_portfolio(portfolios, user_id)
        if portfolio is None:
            portfolio = {"user_id": user_id, "wallets": {}}
            portfolios.append(portfolio)
        wallets = portfolio.setdefault("wallets", {})

        usd_before = None
        usd_after = None
        if code != "USD":
            usd_data = wallets.get("USD") or {
                "currency_code": "USD",
                "balance": 0.0,
            }
            usd_wallet = _wallet_from_dict("USD", usd_data)
            usd_before = usd_wallet.balance
            usd_wallet.withdraw(cost)
            usd_after = usd_wallet.balance
            wallets["USD"] = _wallet_to_dict(usd_wallet)

        target_data = wallets.get(code) or {
            "currency_code": code,
            "balance": 0.0,
        }
        target = _wallet_from_dict(code, target_data)
        before = target.balance
        target.deposit(amount)
        after = target.balance
        wallets[code] = _wallet_to_dict(target)

        ctx.update(
            {
                "before": before,
                "after": after,
                "usd_before": usd_before,
                "usd_after": usd_after,
            }
        )

    db.transaction(utils.PORTFOLIOS_PATH, [], mutate)

    return {
        "user_id": user_id,
        "currency": code,
        "base": base,
        "amount": amount,
        "rate": rate,
        "before": ctx["before"],
        "after": ctx["after"],
        "value": cost,
        "usd_before": ctx["usd_before"],
        "usd_after": ctx["usd_after"],
    }


@log_action("SELL", verbose=True)
def sell_currency(user_id: int, currency_code: str, amount) -> dict:
    code = get_currency(currency_code).code
    amount = _validate_amount(amount)

    base = utils.QUOTE_CURRENCY
    rates = db.read(utils.RATES_PATH, {})
    rate = _require_rate(code, base, rates)
    proceeds = amount * rate

    ctx = {}

    def mutate(portfolios):
        portfolio = _find_portfolio(portfolios, user_id)
        wallets = {} if portfolio is None else portfolio.setdefault("wallets", {})

        target_data = wallets.get(code) or {
            "currency_code": code,
            "balance": 0.0,
        }
        target = _wallet_from_dict(code, target_data)
        before = target.balance
        target.withdraw(amount)
        after = target.balance
        wallets[code] = _wallet_to_dict(target)

        usd_before = None
        usd_after = None
        if code != "USD":
            usd_data = wallets.get("USD") or {
                "currency_code": "USD",
                "balance": 0.0,
            }
            usd_wallet = _wallet_from_dict("USD", usd_data)
            usd_before = usd_wallet.balance
            usd_wallet.deposit(proceeds)
            usd_after = usd_wallet.balance
            wallets["USD"] = _wallet_to_dict(usd_wallet)

        ctx.update(
            {
                "before": before,
                "after": after,
                "usd_before": usd_before,
                "usd_after": usd_after,
            }
        )

    db.transaction(utils.PORTFOLIOS_PATH, [], mutate)

    return {
        "user_id": user_id,
        "currency": code,
        "base": base,
        "amount": amount,
        "rate": rate,
        "before": ctx["before"],
        "after": ctx["after"],
        "value": proceeds,
        "usd_before": ctx["usd_before"],
        "usd_after": ctx["usd_after"],
    }
