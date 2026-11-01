import shlex

from valutatrade_hub.core import usecases
from valutatrade_hub.core.currencies import supported_codes
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    ValutaTradeError,
)


def _parse_named_args(args):
    result = {}
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            raise ValueError(f"Ожидался параметр вида --name, получено: {token}")
        key = token[2:]
        if i + 1 >= len(args):
            raise ValueError(f"Не указано значение для параметра --{key}")
        result[key] = args[i + 1]
        i += 2
    return result


def _print_funds_hint(cmd: str, exc: InsufficientFundsError) -> None:
    """Подсказка после InsufficientFundsError — зависит от команды."""
    if cmd == "sell":
        print(
            f"Подсказка: уменьшите --amount до {exc.available:.4f} "
            f"{exc.code} или меньше."
        )
    elif cmd == "buy":
        print(
            f"Подсказка: для покупки требуется {exc.required:,.2f} {exc.code}, "
            f"доступно {exc.available:,.2f}. Уменьшите --amount или пополните "
            f"{exc.code}-кошелёк (например, через sell)."
        )


def _print_currency_hint(cmd: str) -> None:
    """Список кодов + подсказка по команде после CurrencyNotFoundError."""
    print(f"Поддерживаемые коды: {', '.join(supported_codes())}")
    if cmd == "get-rate":
        print("Проверить курс: get-rate --from <код> --to <код>")
    elif cmd == "buy":
        print("Пример: buy --currency BTC --amount 0.01")
    elif cmd == "sell":
        print("Пример: sell --currency BTC --amount 0.01")


def _print_api_hint(cmd: str) -> None:
    """Рекомендация после ApiRequestError — для get-rate или buy/sell."""
    if cmd == "get-rate":
        print("Повторите попытку позже или проверьте сетевое подключение.")
    else:
        print("Повторите попытку позже.")


def _cmd_register(args):
    params = _parse_named_args(args)
    if "username" not in params:
        raise ValueError("Не указан обязательный параметр --username")
    if "password" not in params:
        raise ValueError("Не указан обязательный параметр --password")
    user = usecases.register_user(params["username"], params["password"])
    print(
        f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}). "
        f"Войдите: login --username {user.username} --password ****"
    )


def _cmd_login(args):
    params = _parse_named_args(args)
    if "username" not in params:
        raise ValueError("Не указан обязательный параметр --username")
    if "password" not in params:
        raise ValueError("Не указан обязательный параметр --password")
    user = usecases.login_user(params["username"], params["password"])
    print(f"Вы вошли как '{user.username}'")


def _fmt_balance(value: float) -> str:
    return f"{value:.4f}" if value < 1 else f"{value:.2f}"


def _fmt_rate(rate) -> str:
    if rate is None:
        return "—"
    if rate >= 1:
        return f"{rate:.2f}"
    if rate >= 0.01:
        return f"{rate:.4f}"
    if rate >= 0.0001:
        return f"{rate:.6f}"
    return f"{rate:.8f}"


def _fmt_dt(value: str) -> str:
    if not value or value == "—":
        return "—"
    return value.replace("T", " ").split(".")[0]


def _require_user():
    user = usecases.get_current_user()
    if user is None:
        raise ValueError("Сначала выполните login")
    return user


def _cmd_show_portfolio(args):
    params = _parse_named_args(args)
    base = params.get("base")
    view = usecases.get_portfolio_view(base)

    if not view["wallets"]:
        print(f"Портфель пользователя '{view['username']}' пуст")
        return

    print(f"Портфель пользователя '{view['username']}' (база: {view['base']}):")
    for w in view["wallets"]:
        print(
            f"- {w['currency']}: {_fmt_balance(w['balance'])}  "
            f"→ {w['value']:.2f} {view['base']}"
        )
    print("-" * 33)
    print(f"ИТОГО: {view['total']:,.2f} {view['base']}")


def _cmd_buy(args):
    params = _parse_named_args(args)
    if "currency" not in params:
        raise ValueError("Не указан обязательный параметр --currency")
    if "amount" not in params:
        raise ValueError("Не указан обязательный параметр --amount")
    user = _require_user()
    result = usecases.buy_currency(user.user_id, params["currency"], params["amount"])

    print(
        f"Покупка выполнена: {result['amount']:.4f} {result['currency']} "
        f"по курсу {result['rate']:.2f} {result['base']}/{result['currency']}"
    )
    print("Изменения в портфеле:")
    print(
        f"- {result['currency']}: было {result['before']:.4f} "
        f"→ стало {result['after']:.4f}"
    )
    if result["usd_before"] is not None:
        print(
            f"- {result['base']}: было {result['usd_before']:.2f} "
            f"→ стало {result['usd_after']:.2f}"
        )
    print(f"Оценочная стоимость покупки: {result['value']:,.2f} {result['base']}")


def _cmd_sell(args):
    params = _parse_named_args(args)
    if "currency" not in params:
        raise ValueError("Не указан обязательный параметр --currency")
    if "amount" not in params:
        raise ValueError("Не указан обязательный параметр --amount")
    user = _require_user()
    result = usecases.sell_currency(user.user_id, params["currency"], params["amount"])

    print(
        f"Продажа выполнена: {result['amount']:.4f} {result['currency']} "
        f"по курсу {result['rate']:.2f} {result['base']}/{result['currency']}"
    )
    print("Изменения в портфеле:")
    print(
        f"- {result['currency']}: было {result['before']:.4f} "
        f"→ стало {result['after']:.4f}"
    )
    if result["usd_before"] is not None:
        print(
            f"- {result['base']}: было {result['usd_before']:.2f} "
            f"→ стало {result['usd_after']:.2f}"
        )
    print(f"Оценочная выручка: {result['value']:,.2f} {result['base']}")


def _cmd_get_rate(args):
    params = _parse_named_args(args)
    if "from" not in params:
        raise ValueError("Не указан обязательный параметр --from")
    if "to" not in params:
        raise ValueError("Не указан обязательный параметр --to")
    result = usecases.get_rate(params["from"], params["to"])

    print(
        f"Курс {result['from']}→{result['to']}: {_fmt_rate(result['rate'])} "
        f"(обновлено: {_fmt_dt(result['updated_at'])})"
    )
    print(
        f"Обратный курс {result['to']}→{result['from']}: {_fmt_rate(result['reverse'])}"
    )


_COMMANDS = {
    "register": _cmd_register,
    "login": _cmd_login,
    "show-portfolio": _cmd_show_portfolio,
    "buy": _cmd_buy,
    "sell": _cmd_sell,
    "get-rate": _cmd_get_rate,
}


def dispatch(line: str) -> None:
    parts = shlex.split(line)
    if not parts:
        return
    cmd = parts[0].lower()
    handler = _COMMANDS.get(cmd)
    if handler is None:
        print(f"Неизвестная команда: {cmd}")
        return
    try:
        handler(parts[1:])
    except InsufficientFundsError as e:
        print(str(e))
        _print_funds_hint(cmd, e)
    except CurrencyNotFoundError as e:
        print(str(e))
        _print_currency_hint(cmd)
    except ApiRequestError as e:
        print(str(e))
        _print_api_hint(cmd)
    except ValutaTradeError as e:
        print(str(e))
    except (ValueError, TypeError) as e:
        print(str(e))


def run() -> None:
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            return
        dispatch(line)
