# ValutaTrade Hub

Консольное учебное приложение для регистрации пользователей, управления валютным портфелем, покупки и продажи валют, просмотра курсов и их обновления через отдельный Parser Service.

## Демонстрация

[![asciicast](https://asciinema.org/a/se02AYWqe4cnHMkL.svg)](https://asciinema.org/a/se02AYWqe4cnHMkL)

Запись сессии CLI: регистрация, обновление курсов через Parser Service,
покупка/продажа валют, обработка ошибок.

## Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Для фиатных курсов — API-ключ ExchangeRate-API (необязательно для работы с локальным кешем и учебными курсами-заглушками).

## Установка и запуск

```bash
uv sync
uv run python main.py
```

Либо после установки пакетной команды:

```bash
uv run valutatrade
```

Проверка стиля:

```bash
uv run ruff check .
uv run ruff format --check .
```

## Структура проекта

```text
.
├── data/
│   ├── users.json
│   ├── portfolios.json
│   ├── rates.json
│   └── exchange_rates.json
├── logs/
├── valutatrade_hub/
│   ├── core/              # модели, валюты, usecases и исключения
│   ├── infra/             # настройки и JSON-хранилище
│   ├── parser_service/    # API-клиенты, updater, история курсов
│   ├── cli/               # консольный интерфейс
│   ├── decorators.py
│   └── logging_config.py
├── main.py
├── pyproject.toml
└── uv.lock
```

## Команды

В интерактивном режиме доступны:

```text
register --username alice --password 1234
login --username alice --password 1234
show-portfolio
buy --currency BTC --amount 0.01
sell --currency BTC --amount 0.005
get-rate --from BTC --to USD
update-rates
show-rates
help
exit
```

Покупка валюты списывает её оценочную стоимость с USD-кошелька. Продажа начисляет выручку в USD-кошелёк. Для покупки требуется достаточный баланс USD; для продажи — достаточный баланс продаваемой валюты.

## Хранение данных и кеш

Пользователи, портфели и кеш хранятся в `data/users.json`, `data/portfolios.json` и `data/rates.json`. История обновлений Parser Service записывается в `data/exchange_rates.json`. Записи JSON выполняются атомарно через временный файл и `os.replace`.

Время жизни кеша Core Service задаётся параметром `rates_ttl_seconds` в секции `[tool.valutatrade]` файла `pyproject.toml` (по умолчанию 300 секунд). Учебные курсы-заглушки используются, когда требуется заполнить отсутствующий/устаревший кеш. Команда `update-rates` запрашивает внешние источники и обновляет кеш.

## Parser Service и API-ключ

Parser Service использует CoinGecko для криптовалют и ExchangeRate-API для фиатных валют. Списки валют, URL, базовая валюта, таймауты и пути находятся в `valutatrade_hub/parser_service/config.py`.

Для фиатных курсов задайте ключ через переменную окружения `EXCHANGERATE_API_KEY`. Локально можно создать `.env` в корне проекта:

```dotenv
EXCHANGERATE_API_KEY=ваш_ключ
```


Примеры:

```text
update-rates
update-rates --source coingecko
show-rates
show-rates --currency BTC
show-rates --top 3
```

## Логирование

Операции `REGISTER`, `LOGIN`, `BUY` и `SELL` журналируются декоратором `@log_action`. Основной журнал — `logs/actions.log`, журнал Parser Service — `logs/parser.log`. Используется строковый формат и ротация файлов по размеру. Уровень логирования по умолчанию — `INFO`; его можно изменить через `log_level` в `[tool.valutatrade]`.
