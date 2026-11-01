import hashlib
import time
from datetime import datetime

from valutatrade_hub.core import utils
from valutatrade_hub.core.models import User

_current_user = None


def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def _user_from_dict(data: dict) -> User:
    return User(
        user_id=data['user_id'],
        username=data['username'],
        hashed_password=data['hashed_password'],
        salt=data['salt'],
        registration_date=datetime.fromisoformat(data['registration_date']))


def register_user(username: str, password: str) -> User:
    if username is None or not username.strip():
        raise ValueError('Имя пользователя не может быть пустым')
    if password is None or len(password) < 4:
        raise ValueError(f'Пароль должен быть не короче '
                     f'{utils.MIN_PASSWORD_LEN} символов')

    users = utils.load_json(utils.USERS_PATH, [])
    for existing in users:
        if existing.get('username') == username:
            raise ValueError(f"Имя пользователя '{username}' уже занято")

    user_id = max((u['user_id'] for u in users), default=0) + 1

    salt = hashlib.sha256(
        f'{username}|{time.time()}|{user_id}'.encode()
    ).hexdigest()[:16]
    hashed_password = _hash(password, salt)
    registration_date = datetime.now()

    user = User(user_id, username, hashed_password, salt, registration_date)

    users.append({
        'user_id': user.user_id,
        'username': user.username,
        'hashed_password': user.hashed_password,
        'salt': user.salt,
        'registration_date': user.registration_date.isoformat(),
    })
    utils.save_json(utils.USERS_PATH, users)

    portfolios = utils.load_json(utils.PORTFOLIOS_PATH, [])
    portfolios.append({'user_id': user_id, 'wallets': {}})
    utils.save_json(utils.PORTFOLIOS_PATH, portfolios)

    return user


def login_user(username: str, password: str) -> User:
    global _current_user

    if username is None or not username.strip():
        raise ValueError('Имя пользователя не может быть пустым')
    if password is None or password == '':
        raise ValueError('Пароль не может быть пустым')

    users = utils.load_json(utils.USERS_PATH, [])
    found = None
    for data in users:
        if data.get('username') == username:
            found = data
            break
    if found is None:
        raise ValueError(f"Пользователь '{username}' не найден")

    if _hash(password, found['salt']) != found['hashed_password']:
        raise ValueError('Неверный пароль')

    _current_user = _user_from_dict(found)
    return _current_user


def get_current_user() -> User | None:
    return _current_user


def _usd_rate(code: str, rates: dict):
    if code == 'USD':
        return 1.0
    direct = rates.get(f'{code}_USD')
    if isinstance(direct, dict):
        return float(direct['rate'])
    inverse = rates.get(f'USD_{code}')
    if isinstance(inverse, dict):
        return 1.0 / float(inverse['rate'])
    return None


def _rate(currency: str, base: str, rates: dict):
    if currency == base:
        return 1.0
    c = _usd_rate(currency, rates)
    b = _usd_rate(base, rates)
    if c is None or b is None:
        return None
    return c / b


def get_portfolio_view(base: str = 'USD') -> dict:
    user = get_current_user()
    if user is None:
        raise ValueError('Сначала выполните вход')

    base = base.upper()
    rates = utils.load_json(utils.RATES_PATH, {})
    if _usd_rate(base, rates) is None:
        raise ValueError(f"Неизвестная базовая валюта '{base}'")

    portfolios = utils.load_json(utils.PORTFOLIOS_PATH, [])
    portfolio = None
    for p in portfolios:
        if p.get('user_id') == user.user_id:
            portfolio = p
            break

    wallets = {} if portfolio is None else portfolio.get('wallets', {})

    view = {
        'username': user.username,
        'base': base,
        'wallets': [],
        'total': 0.0,
    }
    for code, w in wallets.items():
        balance = float(w['balance'])
        rate = _rate(code, base, rates)
        if rate is None:
            continue
        value = balance * rate
        view['wallets'].append(
            {'currency': code, 'balance': balance, 'value': value}
        )
        view['total'] += value
    return view


def _validate_currency(code: str) -> str:
    if code is None:
        raise ValueError('Некорректный код валюты')
    code = code.strip().upper()
    if not code:
        raise ValueError('Некорректный код валюты')
    return code


def _validate_amount(amount) -> float:
    if isinstance(amount, str):
        try:
            amount = float(amount)
        except ValueError:
            raise ValueError("'amount' должен быть положительным числом")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise TypeError("'amount' должен быть положительным числом")
    amount = float(amount)
    if amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return amount


def _find_portfolio(portfolios: list, user_id: int):
    for p in portfolios:
        if p.get('user_id') == user_id:
            return p
    return None


def buy_currency(currency: str, amount) -> dict:
    user = get_current_user()
    if user is None:
        raise ValueError('Сначала выполните вход')

    code = _validate_currency(currency)
    amount = _validate_amount(amount)

    base = 'USD'
    rates = utils.load_json(utils.RATES_PATH, {})
    rate = _rate(code, base, rates)
    if rate is None:
        raise ValueError(f'Не удалось получить курс для {code}→{base}')

    cost = amount * rate

    portfolios = utils.load_json(utils.PORTFOLIOS_PATH, [])
    portfolio = _find_portfolio(portfolios, user.user_id)
    if portfolio is None:
        portfolio = {'user_id': user.user_id, 'wallets': {}}
        portfolios.append(portfolio)

    wallets = portfolio.setdefault('wallets', {})

    usd_before = None
    usd_after = None
    if code != 'USD':
        usd = wallets.get('USD')
        usd_balance = 0.0 if usd is None else float(usd['balance'])
        if usd_balance < cost:
            raise ValueError('Недостаточно средств на балансе')
        usd_before = usd_balance
        usd_after = usd_balance - cost
        if usd is None:
            wallets['USD'] = {'currency_code': 'USD', 'balance': usd_after}
        else:
            usd['balance'] = usd_after

    if code not in wallets:
        wallets[code] = {'currency_code': code, 'balance': 0.0}
    before = float(wallets[code]['balance'])
    after = before + amount
    wallets[code]['balance'] = after
    wallets[code]['currency_code'] = code

    utils.save_json(utils.PORTFOLIOS_PATH, portfolios)

    return {
        'currency': code,
        'base': base,
        'amount': amount,
        'rate': rate,
        'before': before,
        'after': after,
        'value': cost,
        'usd_before': usd_before,
        'usd_after': usd_after,
    }


def sell_currency(currency: str, amount) -> dict:
    user = get_current_user()
    if user is None:
        raise ValueError('Сначала выполните вход')

    code = _validate_currency(currency)
    amount = _validate_amount(amount)

    portfolios = utils.load_json(utils.PORTFOLIOS_PATH, [])
    portfolio = _find_portfolio(portfolios, user.user_id)
    wallets = {} if portfolio is None else portfolio.get('wallets', {})

    if code not in wallets:
        raise ValueError(
            f"У вас нет кошелька '{code}'. "
            f'Добавьте валюту: она создаётся автоматически при первой покупке.'
        )

    current = float(wallets[code]['balance'])
    if current < amount:
        raise ValueError(
            f'Недостаточно средств: доступно {current:.4f} {code}, '
            f'требуется {amount:.4f} {code}'
        )

    base = 'USD'
    rates = utils.load_json(utils.RATES_PATH, {})
    rate = _rate(code, base, rates)
    if rate is None:
        raise ValueError(f'Не удалось получить курс {code} к {base}')

    proceeds = amount * rate

    before = current
    after = current - amount
    wallets[code]['balance'] = after
    wallets[code]['currency_code'] = code

    usd_before = None
    usd_after = None
    if code != 'USD':
        usd = wallets.get('USD')
        usd_balance = 0.0 if usd is None else float(usd['balance'])
        usd_before = usd_balance
        usd_after = usd_balance + proceeds
        if usd is None:
            wallets['USD'] = {'currency_code': 'USD', 'balance': usd_after}
        else:
            usd['balance'] = usd_after

    utils.save_json(utils.PORTFOLIOS_PATH, portfolios)

    return {'currency': code,
            'base': base,
            'amount': amount,
            'rate': rate,
            'before': before,
            'after': after,
            'value': proceeds,
            'usd_before': usd_before,
            'usd_after': usd_after}


def _is_cache_fresh(rates: dict) -> bool:
    last = rates.get('last_refresh')
    if not last:
        return False
    try:
        dt = datetime.fromisoformat(last)
    except (TypeError, ValueError):
        return False
    age = (datetime.now() - dt).total_seconds()
    return 0 <= age < utils.CACHE_TTL_SECONDS


def _refresh_from_stub(rates: dict) -> bool:
    if not utils.STUB_EXCHANGE_RATES:
        return False
    now = datetime.now().isoformat()
    for pair, value in utils.STUB_EXCHANGE_RATES.items():
        rates[pair] = {'rate': value, 'updated_at': now}
    rates['source'] = 'ParserService'
    rates['last_refresh'] = now
    utils.save_json(utils.RATES_PATH, rates)
    return True


def get_rate(from_currency: str, to_currency: str) -> dict:
    code_from = _validate_currency(from_currency)
    code_to = _validate_currency(to_currency)

    rates = utils.load_json(utils.RATES_PATH, {})

    rate = _rate(code_from, code_to, rates)
    if ((rate is None or not _is_cache_fresh(rates)) 
                     and _refresh_from_stub(rates)):
            rate = _rate(code_from, code_to, rates)

    if rate is None:
        raise ValueError(
            f'Курс {code_from} к {code_to} недоступен. Повторите попытку позже.'
        )

    reverse = _rate(code_to, code_from, rates)

    return {
        'from': code_from,
        'to': code_to,
        'rate': rate,
        'reverse': reverse,
        'updated_at': rates.get('last_refresh', '—')}