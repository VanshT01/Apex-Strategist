from datetime import timedelta

import numpy as np
import pandas as pd
from app.utils.serialization import is_missing, json_safe, timedelta_ms


def test_timedelta_values_convert_to_milliseconds() -> None:
    assert timedelta_ms(pd.Timedelta(seconds=91.234)) == 91_234
    assert timedelta_ms(timedelta(milliseconds=2500)) == 2500
    assert timedelta_ms(np.timedelta64(1500, "ms")) == 1500


def test_missing_and_numpy_values_are_json_safe() -> None:
    assert is_missing(np.nan)
    assert timedelta_ms(pd.NaT) is None
    assert json_safe({"missing": np.nan, "position": np.int64(3)}) == {
        "missing": None,
        "position": 3,
    }
