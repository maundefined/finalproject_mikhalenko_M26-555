import logging
import os
from logging.handlers import RotatingFileHandler

from valutatrade_hub.infra.settings import settings


def setup_logging() -> None:
    """Настроить корневой логгер проекта."""
    level_name = str(settings.get("log_level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    log_path = settings.get("log_path", "logs/actions.log")
    log_format = settings.get("log_format", "%(levelname)s %(asctime)s %(message)s")
    log_datefmt = settings.get("log_datefmt", "%Y-%m-%dT%H:%M:%S")
    max_bytes = int(settings.get("log_max_bytes", 1_000_000))
    backup_count = int(settings.get("log_backup_count", 5))

    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    formatter = logging.Formatter(log_format, datefmt=log_datefmt)

    directory = os.path.dirname(log_path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root.addHandler(console_handler)

    parser_path = settings.get("parser_log_path", "logs/parser.log")
    parser_dir = os.path.dirname(parser_path)
    if parser_dir and not os.path.isdir(parser_dir):
        os.makedirs(parser_dir, exist_ok=True)

    parser_logger = logging.getLogger("valutatrade.parser")
    for h in list(parser_logger.handlers):
        parser_logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    parser_file = RotatingFileHandler(
        parser_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    parser_file.setFormatter(formatter)
    parser_file.setLevel(level)
    parser_logger.addHandler(parser_file)

    parser_console = logging.StreamHandler()
    parser_console.setFormatter(formatter)
    parser_console.setLevel(level)
    parser_logger.addHandler(parser_console)

    parser_logger.setLevel(level)
    parser_logger.propagate = False
