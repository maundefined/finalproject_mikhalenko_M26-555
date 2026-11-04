import json
import os

from valutatrade_hub.infra.settings import settings

USERS_PATH = settings.get("users_path", "data/users.json")
PORTFOLIOS_PATH = settings.get("portfolios_path", "data/portfolios.json")
RATES_PATH = settings.get("rates_path", "data/rates.json")

MIN_PASSWORD_LEN = 4

CACHE_TTL_SECONDS = 300

STUB_EXCHANGE_RATES = {
    "EUR_USD": 1.0786,
    "BTC_USD": 59337.21,
    "RUB_USD": 0.01016,
    "ETH_USD": 3720.00,
    "USD_USD": 1.0,
    "GBP_USD": 1.25,
    "SOL_USD": 145.12,
}

QUOTE_CURRENCY = "USD"


def _to_usd_rates(pairs: dict) -> dict:
    """Из {'EUR_USD': 1.0786, ...} сделать {'EUR': 1.0786, 'USD': 1.0, ...}."""
    usd = {"USD": 1.0}
    for pair, rate in pairs.items():
        if not isinstance(pair, str) or not pair.endswith("_USD"):
            continue
        code = pair.split("_", 1)[0]
        usd[code] = float(rate)
    return usd


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
