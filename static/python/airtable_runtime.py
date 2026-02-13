"""
AirtableRuntime: Implements Airtable formula functions and operators in Python.

All operators route through this class for correct Airtable semantics:
- BLANK() is None (treated as 0 in numeric context, "" in string context)
- Division by zero returns float('nan')
- Type coercion follows Airtable rules
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any


class AirtableRuntime:
    # region Utilities
    @staticmethod
    def _is_blank(v: Any) -> bool:
        return v is None

    @staticmethod
    def N(v: Any) -> int | float:  # noqa: N802
        """Coerce value to number"""
        if isinstance(v, list):
            return AirtableRuntime.N(v[0] if v else None)
        if v is None:
            return 0
        if isinstance(v, bool):
            return 1 if v else 0
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            try:
                return float(v) if "." in v else int(v)
            except (ValueError, TypeError):
                return 0
        return 0

    @staticmethod
    def S(v: Any) -> str:  # noqa: N802
        """Coerce value to string"""
        if isinstance(v, list):
            return AirtableRuntime.S(v[0] if v else None)
        if v is None:
            return ""
        if isinstance(v, bool):
            return "1" if v else "0"
        return str(v)

    @staticmethod
    def _flat_args(args: tuple[Any, ...]) -> list[Any]:
        result: list[Any] = []
        for a in args:
            if isinstance(a, list):
                result.extend(a)
            else:
                result.append(a)
        return result

    # endregion

    # region Numeric functions
    @staticmethod
    def SUM(*args: Any) -> int | float:  # noqa: N802
        flat = AirtableRuntime._flat_args(args)
        return sum(AirtableRuntime.N(v) for v in flat)

    @staticmethod
    def AVERAGE(*args: Any) -> float:  # noqa: N802
        flat = AirtableRuntime._flat_args(args)
        if not flat:
            return float("nan")
        return AirtableRuntime.SUM(*flat) / len(flat)

    @staticmethod
    def MIN(*args: Any) -> int | float:  # noqa: N802
        flat = AirtableRuntime._flat_args(args)
        if not flat:
            return float("inf")
        return min(AirtableRuntime.N(v) for v in flat)

    @staticmethod
    def MAX(*args: Any) -> int | float:  # noqa: N802
        flat = AirtableRuntime._flat_args(args)
        if not flat:
            return float("-inf")
        return max(AirtableRuntime.N(v) for v in flat)

    @staticmethod
    def COUNT(*args: Any) -> int:  # noqa: N802
        flat = AirtableRuntime._flat_args(args)
        return sum(1 for v in flat if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)))

    @staticmethod
    def COUNTA(*args: Any) -> int:  # noqa: N802
        flat = AirtableRuntime._flat_args(args)
        return sum(1 for v in flat if not AirtableRuntime._is_blank(v) and v != "")

    @staticmethod
    def COUNTALL(*args: Any) -> int:  # noqa: N802
        return len(AirtableRuntime._flat_args(args))

    @staticmethod
    def ROUND(value: Any, precision: Any = 0) -> float:  # noqa: N802
        n = AirtableRuntime.N(value)
        p = int(AirtableRuntime.N(precision))
        return round(n, p)

    @staticmethod
    def ROUNDUP(value: Any, precision: Any = 0) -> float:  # noqa: N802
        n = AirtableRuntime.N(value)
        p = int(AirtableRuntime.N(precision))
        factor = 10**p
        return math.ceil(n * factor) / factor

    @staticmethod
    def ROUNDDOWN(value: Any, precision: Any = 0) -> float:  # noqa: N802
        n = AirtableRuntime.N(value)
        p = int(AirtableRuntime.N(precision))
        factor = 10**p
        return math.floor(n * factor) / factor

    @staticmethod
    def CEILING(value: Any, significance: Any = 1) -> float:  # noqa: N802
        n = AirtableRuntime.N(value)
        s = AirtableRuntime.N(significance) or 1
        return math.ceil(n / s) * s

    @staticmethod
    def FLOOR(value: Any, significance: Any = 1) -> float:  # noqa: N802
        n = AirtableRuntime.N(value)
        s = AirtableRuntime.N(significance) or 1
        return math.floor(n / s) * s

    @staticmethod
    def POWER(base: Any, exponent: Any) -> float:  # noqa: N802
        return math.pow(AirtableRuntime.N(base), AirtableRuntime.N(exponent))

    @staticmethod
    def EXP(value: Any) -> float:  # noqa: N802
        return math.exp(AirtableRuntime.N(value))

    @staticmethod
    def LOG(value: Any, base: Any = None) -> float:  # noqa: N802
        n = AirtableRuntime.N(value)
        if base is None:
            return math.log10(n)
        return math.log(n) / math.log(AirtableRuntime.N(base))

    @staticmethod
    def LOG10(value: Any) -> float:  # noqa: N802
        return math.log10(AirtableRuntime.N(value))

    @staticmethod
    def MOD(value: Any, divisor: Any) -> int | float:  # noqa: N802
        n = AirtableRuntime.N(value)
        d = AirtableRuntime.N(divisor)
        if d == 0:
            return float("nan")
        return n % d

    @staticmethod
    def EVEN(value: Any) -> int:  # noqa: N802
        n = AirtableRuntime.N(value)
        ceil_val = math.ceil(abs(n))
        result = ceil_val if ceil_val % 2 == 0 else ceil_val + 1
        return -result if n < 0 else result

    @staticmethod
    def ODD(value: Any) -> int:  # noqa: N802
        n = AirtableRuntime.N(value)
        ceil_val = math.ceil(abs(n))
        result = ceil_val if ceil_val % 2 == 1 else ceil_val + 1
        return -result if n < 0 else result

    @staticmethod
    def VALUE(value: Any) -> int | float:  # noqa: N802
        if AirtableRuntime._is_blank(value):
            return 0
        try:
            s = str(value)
            return float(s) if "." in s else int(s)
        except (ValueError, TypeError):
            return float("nan")

    # endregion

    # region String functions
    @staticmethod
    def CONCATENATE(*args: Any) -> str:  # noqa: N802
        return "".join(AirtableRuntime.S(a) for a in args)

    @staticmethod
    def LEFT(text: Any, count: Any) -> str:  # noqa: N802
        return AirtableRuntime.S(text)[: int(AirtableRuntime.N(count))]

    @staticmethod
    def RIGHT(text: Any, count: Any) -> str:  # noqa: N802
        s = AirtableRuntime.S(text)
        n = int(AirtableRuntime.N(count))
        return s[max(0, len(s) - n) :]

    @staticmethod
    def MID(text: Any, start: Any, count: Any) -> str:  # noqa: N802
        s = AirtableRuntime.S(text)
        start_idx = int(AirtableRuntime.N(start)) - 1
        length = int(AirtableRuntime.N(count))
        return s[start_idx : start_idx + length]

    @staticmethod
    def FIND(needle: Any, haystack: Any, start: Any = None) -> int:  # noqa: N802
        s = AirtableRuntime.S(haystack)
        n = AirtableRuntime.S(needle)
        start_idx = 0 if AirtableRuntime._is_blank(start) else int(AirtableRuntime.N(start)) - 1
        idx = s.find(n, start_idx)
        return 0 if idx == -1 else idx + 1

    @staticmethod
    def SEARCH(needle: Any, haystack: Any, start: Any = None) -> int:  # noqa: N802
        s = AirtableRuntime.S(haystack).lower()
        n = AirtableRuntime.S(needle).lower()
        start_idx = 0 if AirtableRuntime._is_blank(start) else int(AirtableRuntime.N(start)) - 1
        idx = s.find(n, start_idx)
        return 0 if idx == -1 else idx + 1

    @staticmethod
    def SUBSTITUTE(text: Any, old_str: Any, new_str: Any, index: Any = None) -> str:  # noqa: N802
        s = AirtableRuntime.S(text)
        o = AirtableRuntime.S(old_str)
        n = AirtableRuntime.S(new_str)
        if AirtableRuntime._is_blank(index):
            return s.replace(o, n)
        target = int(AirtableRuntime.N(index))
        count = 0

        def _replacer(match: re.Match[str]) -> str:
            nonlocal count
            count += 1
            return n if count == target else match.group()

        return re.sub(re.escape(o), _replacer, s)

    @staticmethod
    def REPLACE(text: Any, start: Any, count: Any, replacement: Any) -> str:  # noqa: N802
        s = AirtableRuntime.S(text)
        start_idx = int(AirtableRuntime.N(start)) - 1
        length = int(AirtableRuntime.N(count))
        return s[:start_idx] + AirtableRuntime.S(replacement) + s[start_idx + length :]

    @staticmethod
    def REPT(text: Any, count: Any) -> str:  # noqa: N802
        return AirtableRuntime.S(text) * max(0, int(AirtableRuntime.N(count)))

    @staticmethod
    def T(value: Any) -> str:  # noqa: N802
        return value if isinstance(value, str) else ""

    @staticmethod
    def REGEX_MATCH(text: Any, regex: Any) -> bool:  # noqa: N802
        try:
            return bool(re.search(AirtableRuntime.S(regex), AirtableRuntime.S(text)))
        except re.error:
            return False

    @staticmethod
    def REGEX_EXTRACT(text: Any, regex: Any) -> str | None:  # noqa: N802
        try:
            match = re.search(AirtableRuntime.S(regex), AirtableRuntime.S(text))
            return match.group(0) if match else None
        except re.error:
            return None

    @staticmethod
    def REGEX_REPLACE(text: Any, regex: Any, replacement: Any) -> str:  # noqa: N802
        try:
            return re.sub(AirtableRuntime.S(regex), AirtableRuntime.S(replacement), AirtableRuntime.S(text))
        except re.error:
            return AirtableRuntime.S(text)

    # endregion

    # region Date/Time functions
    @staticmethod
    def TODAY() -> str:  # noqa: N802
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def NOW() -> str:  # noqa: N802
        return datetime.now().isoformat()

    @staticmethod
    def DATEADD(date: Any, count: Any, unit: Any) -> str | None:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return None
        try:
            d = datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        n = int(AirtableRuntime.N(count))
        u = AirtableRuntime.S(unit).lower()
        if u == "years":
            d = d.replace(year=d.year + n)
        elif u == "months":
            month = d.month + n
            year = d.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            d = d.replace(year=year, month=month)
        elif u == "weeks":
            d += timedelta(weeks=n)
        elif u == "days":
            d += timedelta(days=n)
        elif u == "hours":
            d += timedelta(hours=n)
        elif u == "minutes":
            d += timedelta(minutes=n)
        elif u == "seconds":
            d += timedelta(seconds=n)
        return d.isoformat()

    @staticmethod
    def DATETIME_DIFF(date1: Any, date2: Any, unit: Any = None) -> int:  # noqa: N802
        if AirtableRuntime._is_blank(date1) or AirtableRuntime._is_blank(date2):
            return 0
        try:
            d1 = datetime.fromisoformat(AirtableRuntime.S(date1).replace("Z", "+00:00"))
            d2 = datetime.fromisoformat(AirtableRuntime.S(date2).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return 0
        u = AirtableRuntime.S(unit or "days").lower()
        diff = d1 - d2
        total_seconds = diff.total_seconds()
        if u == "milliseconds":
            return int(total_seconds * 1000)
        elif u == "seconds":
            return int(total_seconds)
        elif u == "minutes":
            return int(total_seconds / 60)
        elif u == "hours":
            return int(total_seconds / 3600)
        elif u == "days":
            return int(total_seconds / 86400)
        elif u == "weeks":
            return int(total_seconds / (86400 * 7))
        elif u == "months":
            return (d1.year - d2.year) * 12 + (d1.month - d2.month)
        elif u == "years":
            return d1.year - d2.year
        return int(total_seconds / 86400)

    @staticmethod
    def DATETIME_FORMAT(date: Any, _format: Any = None) -> str:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return ""
        try:
            d = datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00"))
            return d.isoformat()
        except (ValueError, TypeError):
            return ""

    @staticmethod
    def DATETIME_PARSE(text: Any, _format: Any = None, _locale: Any = None) -> str | None:  # noqa: N802
        if AirtableRuntime._is_blank(text):
            return None
        try:
            d = datetime.fromisoformat(AirtableRuntime.S(text).replace("Z", "+00:00"))
            return d.isoformat()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def SET_LOCALE(date: Any, _locale: Any) -> Any:  # noqa: N802
        return date

    @staticmethod
    def SET_TIMEZONE(date: Any, _timezone: Any) -> Any:  # noqa: N802
        return date

    @staticmethod
    def YEAR(date: Any) -> int:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return 0
        try:
            return datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00")).year
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def MONTH(date: Any) -> int:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return 0
        try:
            return datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00")).month
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def DAY(date: Any) -> int:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return 0
        try:
            return datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00")).day
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def HOUR(date: Any) -> int:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return 0
        try:
            return datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00")).hour
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def MINUTE(date: Any) -> int:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return 0
        try:
            return datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00")).minute
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def SECOND(date: Any) -> int:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return 0
        try:
            return datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00")).second
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def WEEKDAY(date: Any) -> int:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return 0
        try:
            d = datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00"))
            return (d.weekday() + 1) % 7  # Sunday=0, Monday=1, ...
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def WEEKNUM(date: Any, start_day: Any = None) -> int:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return 0
        try:
            d = datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00"))
            day_names = {"sunday": 6, "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5}
            if AirtableRuntime._is_blank(start_day):
                start_dow = 6  # Sunday (Python: Monday=0)
            else:
                start_dow = day_names.get(AirtableRuntime.S(start_day).lower(), 6)
            start_of_year = datetime(d.year, 1, 1, tzinfo=d.tzinfo)
            day_of_year = (d - start_of_year).days
            start_day_of_week = start_of_year.weekday()  # Monday=0
            adjusted = day_of_year + ((start_day_of_week - start_dow + 7) % 7)
            return (adjusted // 7) + 1
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def DATESTR(date: Any) -> str:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return ""
        try:
            d = datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00"))
            return d.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return ""

    @staticmethod
    def TIMESTR(date: Any) -> str:  # noqa: N802
        if AirtableRuntime._is_blank(date):
            return ""
        try:
            d = datetime.fromisoformat(AirtableRuntime.S(date).replace("Z", "+00:00"))
            return d.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            return ""

    @staticmethod
    def TONOW(date: Any, unit: Any = None) -> int:  # noqa: N802
        return AirtableRuntime.DATETIME_DIFF(datetime.now().isoformat(), date, unit or "days")

    @staticmethod
    def FROMNOW(date: Any, unit: Any = None) -> int:  # noqa: N802
        return AirtableRuntime.DATETIME_DIFF(date, datetime.now().isoformat(), unit or "days")

    @staticmethod
    def IS_SAME(date1: Any, date2: Any, unit: Any = None) -> bool:  # noqa: N802
        return AirtableRuntime.DATETIME_DIFF(date1, date2, unit or "days") == 0

    @staticmethod
    def IS_BEFORE(date1: Any, date2: Any, unit: Any = None) -> bool:  # noqa: N802
        return AirtableRuntime.DATETIME_DIFF(date1, date2, unit or "days") < 0

    @staticmethod
    def IS_AFTER(date1: Any, date2: Any, unit: Any = None) -> bool:  # noqa: N802
        return AirtableRuntime.DATETIME_DIFF(date1, date2, unit or "days") > 0

    @staticmethod
    def WORKDAY(start_date: Any, num_days: Any) -> str | None:  # noqa: N802
        if AirtableRuntime._is_blank(start_date):
            return None
        try:
            d = datetime.fromisoformat(AirtableRuntime.S(start_date).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        remaining = int(AirtableRuntime.N(num_days))
        direction = 1 if remaining > 0 else -1
        remaining = abs(remaining)
        while remaining > 0:
            d += timedelta(days=direction)
            if d.weekday() < 5:  # Monday=0 through Friday=4
                remaining -= 1
        return d.isoformat()

    @staticmethod
    def WORKDAY_DIFF(start_date: Any, end_date: Any) -> int:  # noqa: N802
        if AirtableRuntime._is_blank(start_date) or AirtableRuntime._is_blank(end_date):
            return 0
        try:
            d1 = datetime.fromisoformat(AirtableRuntime.S(start_date).replace("Z", "+00:00"))
            d2 = datetime.fromisoformat(AirtableRuntime.S(end_date).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return 0
        count = 0
        current = d1
        direction = 1 if d2 > d1 else -1
        while (direction == 1 and current < d2) or (direction == -1 and current > d2):
            current += timedelta(days=direction)
            if current.weekday() < 5:
                count += direction
        return count

    # endregion

    # region Array functions
    @staticmethod
    def ARRAYJOIN(arr: Any, separator: Any = None) -> str:  # noqa: N802
        if not isinstance(arr, list):
            return AirtableRuntime.S(arr)
        sep = ", " if AirtableRuntime._is_blank(separator) else AirtableRuntime.S(separator)
        return sep.join(AirtableRuntime.S(v) for v in arr)

    @staticmethod
    def ARRAYUNIQUE(arr: Any) -> list[Any]:  # noqa: N802
        if not isinstance(arr, list):
            return [arr]
        seen: list[Any] = []
        for v in arr:
            if v not in seen:
                seen.append(v)
        return seen

    @staticmethod
    def ARRAYCOMPACT(arr: Any) -> list[Any]:  # noqa: N802
        if not isinstance(arr, list):
            return [] if AirtableRuntime._is_blank(arr) else [arr]
        return [v for v in arr if not AirtableRuntime._is_blank(v) and v != ""]

    @staticmethod
    def ARRAYFLATTEN(arr: Any) -> list[Any]:  # noqa: N802
        if not isinstance(arr, list):
            return [arr]
        result: list[Any] = []

        def _flatten(items: list[Any]) -> None:
            for item in items:
                if isinstance(item, list):
                    _flatten(item)
                else:
                    result.append(item)

        _flatten(arr)
        return result

    # endregion

    # region Record/Special
    @staticmethod
    def ERROR(message: Any = None) -> None:  # noqa: N802
        raise ValueError(AirtableRuntime.S(message or "Error"))

    @staticmethod
    def ISERROR(value: Any) -> bool:  # noqa: N802
        return isinstance(value, Exception) or (isinstance(value, float) and math.isnan(value))

    # endregion
