import shlex

from valutatrade_hub.core import usecases
from valutatrade_hub.core.currencies import supported_codes
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    ValutaTradeError,
)
from valutatrade_hub.parser_service.config import parser_config
from valutatrade_hub.parser_service.storage import ParserStorage
from valutatrade_hub.parser_service.updater import build_default_updater


_HELP_ENTRIES = [
    (
        "register",
        "register --username <str> --password <str>",
        "Создать нового пользователя.",
    ),
    (
        "login",
        "login --username <str> --password <str>",
        "Войти в систему. Открывает сессию для buy/sell/show-portfolio.",
    ),
    (
        "show-portfolio",
        "show-portfolio [--base <str>]",
        "Показать все кошельки и итоговую стоимость (по умолчанию USD).",
    ),
    (
        "buy",
        "buy --currency <str> --amount <float>",
        "Купить валюту. Списывает USD, автосоздаёт кошелёк при необходимости.",
    ),
    (
        "sell",
        "sell --currency <str> --amount <float>",
        "Продать валюту. Начисляет выручку в USD.",
    ),
    (
        "get-rate",
        "get-rate --from <str> --to <str>",
        "Курс одной валюты к другой из локального кеша.",
    ),
    (
        "show-rates",
        "show-rates [--currency <str>] [--top <int>] [--base <str>]",
        "Все курсы из кеша с фильтрами.",
    ),
    (
        "update-rates",
        "update-rates [--source coingecko|exchangerate]",
        "Запустить обновление курсов через Parser Service.",
    ),
    (
        "help",
        "help [<command>]",
        "Показать справку по всем командам или по одной.",
    ),
    (
        "exit",
        "exit | quit",
        "Выйти из программы.",
    ),
]


def _print_help(command: str | None = None) -> None:
    if command:
        entry = next((e for e in _HELP_ENTRIES if e[0] == command.lower()), None)
        if entry is None:
            print(f"Неизвестная команда: {command}")
            print("Наберите 'help' без аргументов для списка команд.")
            return
        name, usage, description = entry
        print(f"{name}")
        print(f"  Использование: {usage}")
        print(f"  {description}")
        return

    print("ValutaTrade Hub — доступные команды:")
    for _name, usage, description in _HELP_ENTRIES:
        print(f"  {usage}")
        print(f"      {description}")
    print("Подробнее: help <command>   (например, help buy)")


def _cmd_help(args):
    if not args:
        _print_help()
        return
    if len(args) != 1:
        raise ValueError("Использование: help [<command>]")
    _print_help(args[0])


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
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        return "—"
    if rate >= 100:
        return f"{rate:.2f}"
    if rate >= 1:
        return f"{rate:.4f}"
    if rate >= 0.001:
        return f"{rate:.5f}"
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


def _fmt_iso(value) -> str:
    if not value or value == "—":
        return "—"
    return str(value).split(".")[0].rstrip("Z")


def _cmd_update_rates(args):
    params = _parse_named_args(args)
    source = params.get("source")
    updater = build_default_updater()
    result = updater.run_update(source=source)

    if result["errors"]:
        print("Update completed with errors. Check logs/parser.log for details.")
        for err in result["errors"]:
            print(f"  - {err}")
    elif result["total_rates"] == 0:
        print("Update completed. No rates received.")
    else:
        print(
            f"Update successful. Total rates updated: {result['total_rates']}. "
            f"Last refresh: {_fmt_iso(result['last_refresh'])}"
        )


_EMPTY_CACHE_MSG = (
    "Локальный кеш курсов пуст. Выполните 'update-rates', чтобы загрузить данные."
)


def _cmd_show_rates(args):
    params = _parse_named_args(args)
    storage = ParserStorage(
        parser_config.RATES_FILE_PATH, parser_config.HISTORY_FILE_PATH
    )
    try:
        data = storage.read_cache()
    except ValutaTradeError:
        print(_EMPTY_CACHE_MSG)
        return

    pairs = data.get("pairs", {}) if isinstance(data, dict) else {}
    if not isinstance(pairs, dict) or not pairs:
        print(_EMPTY_CACHE_MSG)
        return

    last_refresh = data.get("last_refresh", "—")
    currency = params.get("currency")
    base = params.get("base")
    top = params.get("top")

    filtered = dict(pairs)

    if currency:
        code = currency.upper()
        filtered = {p: v for p, v in filtered.items() if code in p.split("_")}
        if not filtered:
            print(f"Курс для '{code}' не найден в кеше.")
            return

    if top is not None:
        try:
            n = int(top)
        except ValueError:
            raise ValueError("--top должен быть целым положительным числом") from None
        if n <= 0:
            raise ValueError("--top должен быть целым положительным числом")
        crypto = set(parser_config.CRYPTO_CURRENCIES)
        crypto_pairs = {
            p: v for p, v in filtered.items() if p.split("_", 1)[0] in crypto
        }
        filtered = dict(
            sorted(
                crypto_pairs.items(),
                key=lambda kv: float(kv[1].get("rate", 0.0)),
                reverse=True,
            )[:n]
        )
        if not filtered:
            print("Курсы криптовалют не найдены в кеше.")
            return

    if base:
        base_code = base.upper()
        usd_map = {"USD": 1.0}
        for pair, entry in pairs.items():
            parts = pair.split("_", 1)
            if len(parts) != 2:
                continue
            fc, tc = parts
            if tc == "USD":
                try:
                    usd_map[fc] = float(entry["rate"])
                except (KeyError, TypeError, ValueError):
                    continue
        if base_code not in usd_map:
            print(f"Курс для '{base_code}' не найден в кеше.")
            return
        base_usd = usd_map[base_code]
        converted = {}
        for pair, entry in filtered.items():
            parts = pair.split("_", 1)
            if len(parts) != 2:
                continue
            fc, tc = parts
            if fc == base_code:
                continue
            try:
                rate_usd = float(entry["rate"])
            except (TypeError, ValueError):
                continue
            if tc == "USD":
                converted[f"{fc}_{base_code}"] = {
                    "rate": rate_usd / base_usd,
                    "updated_at": entry.get("updated_at"),
                    "source": entry.get("source"),
                }
        filtered = converted
        if not filtered:
            print(f"Не удалось пересчитать курсы в базу '{base_code}'.")
            return

    print(f"Rates from cache (updated at {_fmt_iso(last_refresh)}):")
    for pair in sorted(filtered.keys()):
        entry = filtered[pair]
        print(f"- {pair}: {_fmt_rate(entry.get('rate'))}")


_COMMANDS = {
    "register": _cmd_register,
    "login": _cmd_login,
    "show-portfolio": _cmd_show_portfolio,
    "buy": _cmd_buy,
    "sell": _cmd_sell,
    "get-rate": _cmd_get_rate,
    "update-rates": _cmd_update_rates,
    "show-rates": _cmd_show_rates,
    "help": _cmd_help,
    "?": _cmd_help,  # алиас
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
    _print_help()
    print("Введите команду (exit/quit — выход).")
    print()
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

def main() -> None:
    from valutatrade_hub.logging_config import setup_logging

    setup_logging()
    run()
