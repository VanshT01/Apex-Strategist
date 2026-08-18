from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
        return bool(missing) if not isinstance(missing, (np.ndarray, pd.Series)) else False
    except (TypeError, ValueError):
        return False


def optional_str(value: Any) -> str | None:
    return None if is_missing(value) else str(value)


def optional_float(value: Any) -> float | None:
    return None if is_missing(value) else float(value)


def optional_int(value: Any) -> int | None:
    return None if is_missing(value) else int(float(value))


def optional_bool(value: Any) -> bool | None:
    return None if is_missing(value) else bool(value)


def timedelta_ms(value: Any) -> int | None:
    if is_missing(value):
        return None
    if isinstance(value, pd.Timedelta):
        return round(value.total_seconds() * 1000)
    if isinstance(value, np.timedelta64):
        return round(pd.Timedelta(value).total_seconds() * 1000)
    if isinstance(value, timedelta):
        return round(value.total_seconds() * 1000)
    raise TypeError(f"Expected timedelta-like value, received {type(value).__name__}")


def optional_datetime(value: Any) -> datetime | None:
    if is_missing(value):
        return None
    timestamp = pd.Timestamp(value)
    return timestamp.to_pydatetime()


def optional_date(value: Any) -> date | None:
    parsed = optional_datetime(value)
    return parsed.date() if parsed else None


def json_safe(value: Any) -> Any:
    if is_missing(value):
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, (pd.Timedelta, np.timedelta64, timedelta)):
        return timedelta_ms(value)
    if isinstance(value, np.generic):
        return value.item()
    return value


def field(row: Any, name: str, default: Any = None) -> Any:
    """Read a pandas row only when the provider supplied the named column."""
    try:
        value = row[name]
    except (KeyError, TypeError, IndexError):
        return default
    return default if is_missing(value) else value
