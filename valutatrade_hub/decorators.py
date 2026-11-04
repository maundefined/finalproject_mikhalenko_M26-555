import functools
import inspect
import logging

logger = logging.getLogger("valutatrade.actions")

_PASSWORD_KEYS = frozenset({"password", "hashed_password", "salt"})


def _safe_repr(value, max_len: int = 64) -> str:
    if value is None:
        return "—"
    text = repr(value)
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def _format_amount(value) -> str:
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return _safe_repr(value)


def _format_rate(value) -> str:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return _safe_repr(value)
    if rate >= 0.01:
        return f"{rate:.2f}"
    if rate >= 0.0001:
        return f"{rate:.6f}"
    return f"{rate:.8f}"


def _extract_inputs(func, args, kwargs) -> dict:
    try:
        signature = inspect.signature(func)
        bound = signature.bind_partial(*args, **kwargs)
        data = dict(bound.arguments)
    except (TypeError, ValueError):
        data = dict(kwargs)
    return {k: v for k, v in data.items() if k not in _PASSWORD_KEYS}


def _current_username():
    try:
        from valutatrade_hub.core.usecases import get_current_user

        user = get_current_user()
        return None if user is None else user.username
    except Exception:
        return None


def _resolve_user(inputs: dict, result, *, with_username: bool):
    username = inputs.get("username") if with_username else None
    user_id = inputs.get("user_id")

    if not username and hasattr(result, "username"):
        username = result.username
    if user_id is None and hasattr(result, "user_id"):
        user_id = result.user_id

    if not username and user_id is not None:
        try:
            from valutatrade_hub.core.usecases import get_current_user

            current = get_current_user()
            if current is not None and current.user_id == user_id:
                username = current.username
        except Exception:
            pass

    return username, user_id


def _format_success(action: str, inputs: dict, result, verbose: bool) -> str:
    parts = [action]

    username, user_id = _resolve_user(inputs, result, with_username=True)
    if username:
        parts.append(f"user={_safe_repr(username)}")
    elif user_id is not None:
        parts.append(f"user_id={user_id}")

    if isinstance(result, dict):
        if result.get("currency"):
            parts.append(f"currency={_safe_repr(result['currency'])}")
        if result.get("amount") is not None:
            parts.append(f"amount={_format_amount(result['amount'])}")
        if result.get("rate") is not None:
            parts.append(f"rate={_format_rate(result['rate'])}")
        if result.get("base"):
            parts.append(f"base={_safe_repr(result['base'])}")
        if (
            verbose
            and result.get("before") is not None
            and result.get("after") is not None
        ):
            parts.append(
                f"wallet={_format_amount(result['before'])}"
                f"->{_format_amount(result['after'])}"
            )
        if (
            verbose
            and result.get("usd_before") is not None
            and result.get("usd_after") is not None
        ):
            parts.append(
                f"usd={float(result['usd_before']):.2f}"
                f"->{float(result['usd_after']):.2f}"
            )

    parts.append("result=OK")
    return " ".join(parts)


def _format_error(action: str, inputs: dict, exc: Exception) -> str:
    parts = [action]

    username, user_id = _resolve_user(inputs, None, with_username=False)
    if username:
        parts.append(f"user={_safe_repr(username)}")
    elif user_id is not None:
        parts.append(f"user_id={user_id}")

    if inputs.get("currency") or inputs.get("currency_code"):
        code = inputs.get("currency_code") or inputs.get("currency")
        parts.append(f"currency={_safe_repr(code)}")
    if inputs.get("amount") is not None:
        parts.append(f"amount={_format_amount(inputs['amount'])}")

    parts.append("result=ERROR")
    parts.append(f"error_type={type(exc).__name__}")
    parts.append(f"error_message={_safe_repr(str(exc), max_len=128)}")
    return " ".join(parts)


def log_action(action: str, *, verbose: bool = False):
    """Декоратор доменных операций.

    Пишет ровно одну INFO-запись на вызов:

      * успех: ``<ACTION> user=... currency=... amount=... rate=...
        base=... result=OK``;
      * ошибка: ``<ACTION> user=... currency=... amount=...
        result=ERROR error_type=... error_message=...``.
    """
    normalized = action.upper()

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            inputs = _extract_inputs(func, args, kwargs)
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                logger.info(_format_error(normalized, inputs, exc))
                raise
            logger.info(_format_success(normalized, inputs, result, verbose))
            return result

        return wrapper

    return decorator
