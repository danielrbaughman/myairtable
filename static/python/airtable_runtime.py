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
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


class AirtableRuntime:
    # region Utilities
    @staticmethod
    def A(args: tuple[Any, ...]) -> list[Any]:  # noqa: N802
        """Coerce arguments to a flat array"""
        result: list[Any] = []
        for a in args:
            if isinstance(a, list):
                result.extend(a)
            else:
                result.append(a)
        return result

    @staticmethod
    def AN(args: tuple[Any, ...]) -> list[int | float]:  # noqa: N802
        """Coerce arguments to a flat array of numbers"""
        return [AirtableRuntime.N(v) for v in AirtableRuntime.A(args)]

    @staticmethod
    def AS(args: tuple[Any, ...]) -> list[str]:  # noqa: N802
        """Coerce arguments to a flat array of strings"""
        return [AirtableRuntime.S(v) for v in AirtableRuntime.A(args)]

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
        """Coerce value to string. Airtable strips .0 from whole-number floats."""
        if isinstance(v, list):
            return AirtableRuntime.S(v[0] if v else None)
        if v is None:
            return ""
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, float) and v.is_integer() and not math.isnan(v) and not math.isinf(v):
            return str(int(v))
        return str(v)

    @staticmethod
    def D(v: Any) -> datetime:  # noqa: N802
        """Coerce value to datetime"""
        if isinstance(v, list):
            return AirtableRuntime.D(v[0] if v else None)
        if isinstance(v, datetime):
            return v
        if isinstance(v, date):
            return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc)
        s = AirtableRuntime.S(v) if v is not None else ""
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    # endregion

    # region Numeric functions
    @staticmethod
    def AVERAGE(*args: Any) -> float:  # noqa: N802
        flat = AirtableRuntime.AN(args)
        return sum(flat) / len(flat)

    @staticmethod
    def COUNT(*args: Any) -> int:  # noqa: N802
        flat = AirtableRuntime.A(args)
        return sum(1 for v in flat if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)))

    @staticmethod
    def COUNTA(*args: Any) -> int:  # noqa: N802
        flat = AirtableRuntime.A(args)
        return sum(1 for v in flat if v is not None and v != "")

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
    def LOG(value: Any, base: Any = None) -> float:  # noqa: N802
        n = AirtableRuntime.N(value)
        if base is None:
            return math.log10(n)
        return math.log(n) / math.log(AirtableRuntime.N(base))

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
        if value is None:
            return 0
        try:
            s = str(value)
            return float(s) if "." in s else int(s)
        except (ValueError, TypeError):
            return float("nan")

    # endregion

    # region String functions
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
        start_idx = 0 if start is None else int(AirtableRuntime.N(start)) - 1
        idx = s.find(n, start_idx)
        return 0 if idx == -1 else idx + 1

    @staticmethod
    def SEARCH(needle: Any, haystack: Any, start: Any = None) -> int:  # noqa: N802
        s = AirtableRuntime.S(haystack).lower()
        n = AirtableRuntime.S(needle).lower()
        start_idx = 0 if start is None else int(AirtableRuntime.N(start)) - 1
        idx = s.find(n, start_idx)
        return 0 if idx == -1 else idx + 1

    @staticmethod
    def SUBSTITUTE(text: Any, old_str: Any, new_str: Any, index: Any = None) -> str:  # noqa: N802
        s = AirtableRuntime.S(text)
        o = AirtableRuntime.S(old_str)
        n = AirtableRuntime.S(new_str)
        if index is None:
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
    def T(value: Any) -> str:  # noqa: N802
        return value if isinstance(value, str) else ""

    # endregion

    # region Date/Time functions
    @staticmethod
    def DATEADD(date: Any, count: Any, unit: Any) -> str | None:  # noqa: N802
        if date is None:
            return None
        d = AirtableRuntime.D(date)
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
        if date1 is None or date2 is None:
            return 0
        d1 = AirtableRuntime.D(date1)
        d2 = AirtableRuntime.D(date2)
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
    def DATETIME_FORMAT(date: Any, fmt: Any = None) -> str:  # noqa: N802
        if date is None:
            return ""
        d = AirtableRuntime.D(date)
        if fmt is None:
            return d.isoformat()
        f = AirtableRuntime.S(fmt)
        # Convert Moment.js-style tokens to strftime
        token_map = [
            ("YYYY", "%Y"),
            ("YY", "%y"),
            ("MM", "%m"),
            ("DD", "%d"),
            ("HH", "%H"),
            ("hh", "%I"),
            ("mm", "%M"),
            ("ss", "%S"),
            ("A", "%p"),
            ("a", "%p"),
        ]
        strftime_fmt = f
        for token, replacement in token_map:
            strftime_fmt = strftime_fmt.replace(token, replacement)
        result = d.strftime(strftime_fmt)
        # Handle lowercase am/pm for 'a' token
        if "a" in f and "A" not in f:
            result = result.replace("AM", "am").replace("PM", "pm")
        return result

    @staticmethod
    def DATETIME_PARSE(text: Any, _format: Any = None, _locale: Any = None) -> str | None:  # noqa: N802
        if text is None:
            return None
        return AirtableRuntime.D(text).isoformat()

    @staticmethod
    def SET_LOCALE(date: Any, _locale: Any) -> Any:  # noqa: N802
        return date

    @staticmethod
    def SET_TIMEZONE(date: Any, tz: Any) -> str | None:  # noqa: N802
        if date is None:
            return None
        d = AirtableRuntime.D(date)
        target_tz = ZoneInfo(AirtableRuntime.S(tz))
        local_dt = d.astimezone(target_tz)
        # Replace tzinfo with UTC so UTC-based formatting shows local time values
        adjusted = local_dt.replace(tzinfo=timezone.utc)
        return adjusted.isoformat()

    @staticmethod
    def YEAR(date: Any) -> int:  # noqa: N802
        if date is None:
            return 0
        return AirtableRuntime.D(date).year

    @staticmethod
    def MONTH(date: Any) -> int:  # noqa: N802
        if date is None:
            return 0
        return AirtableRuntime.D(date).month

    @staticmethod
    def DAY(date: Any) -> int:  # noqa: N802
        if date is None:
            return 0
        return AirtableRuntime.D(date).day

    @staticmethod
    def HOUR(date: Any) -> int:  # noqa: N802
        if date is None:
            return 0
        return AirtableRuntime.D(date).hour

    @staticmethod
    def MINUTE(date: Any) -> int:  # noqa: N802
        if date is None:
            return 0
        return AirtableRuntime.D(date).minute

    @staticmethod
    def SECOND(date: Any) -> int:  # noqa: N802
        if date is None:
            return 0
        return AirtableRuntime.D(date).second

    @staticmethod
    def WEEKDAY(date: Any) -> int:  # noqa: N802
        if date is None:
            return 0
        return (AirtableRuntime.D(date).weekday() + 1) % 7  # Sunday=0, Monday=1, ...

    @staticmethod
    def WEEKNUM(date: Any, start_day: Any = None) -> int:  # noqa: N802
        if date is None:
            return 0
        d = AirtableRuntime.D(date)
        day_names = {"sunday": 6, "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5}
        if start_day is None:
            start_dow = 6  # Sunday (Python: Monday=0)
        else:
            start_dow = day_names.get(AirtableRuntime.S(start_day).lower(), 6)
        start_of_year = datetime(d.year, 1, 1, tzinfo=d.tzinfo)
        day_of_year = (d - start_of_year).days
        start_day_of_week = start_of_year.weekday()  # Monday=0
        adjusted = day_of_year + ((start_day_of_week - start_dow + 7) % 7)
        return (adjusted // 7) + 1

    @staticmethod
    def DATESTR(date: Any) -> str:  # noqa: N802
        if date is None:
            return ""
        return AirtableRuntime.D(date).strftime("%Y-%m-%d")

    @staticmethod
    def TIMESTR(date: Any) -> str:  # noqa: N802
        if date is None:
            return ""
        return AirtableRuntime.D(date).strftime("%H:%M:%S")

    @staticmethod
    def TONOW(date: Any, unit: Any = None) -> int | str:  # noqa: N802
        if unit is not None:
            return AirtableRuntime.DATETIME_DIFF(datetime.now(tz=timezone.utc).isoformat(), date, unit)
        return AirtableRuntime._human_duration(date, datetime.now(tz=timezone.utc).isoformat())

    @staticmethod
    def FROMNOW(date: Any, unit: Any = None) -> int | str:  # noqa: N802
        if unit is not None:
            return AirtableRuntime.DATETIME_DIFF(date, datetime.now(tz=timezone.utc).isoformat(), unit)
        return AirtableRuntime._human_duration(date, datetime.now(tz=timezone.utc).isoformat())

    @staticmethod
    def _human_duration(date1: Any, date2: Any) -> str:
        d1 = AirtableRuntime.D(date1)
        d2 = AirtableRuntime.D(date2)
        diff_seconds = abs(int((d1 - d2).total_seconds()))
        minutes = diff_seconds // 60
        hours = minutes // 60
        days = hours // 24
        months = abs((d1.year - d2.year) * 12 + (d1.month - d2.month))
        years = months // 12
        if years > 0:
            return f"{years} year{'s' if years != 1 else ''}"
        if months > 0:
            return f"{months} month{'s' if months != 1 else ''}"
        if days > 0:
            return f"{days} day{'s' if days != 1 else ''}"
        if hours > 0:
            return f"{hours} hour{'s' if hours != 1 else ''}"
        if minutes > 0:
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        return f"{diff_seconds} second{'s' if diff_seconds != 1 else ''}"

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
        if start_date is None:
            return None
        d = AirtableRuntime.D(start_date)
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
        if start_date is None or end_date is None:
            return 0
        d1 = AirtableRuntime.D(start_date)
        d2 = AirtableRuntime.D(end_date)
        count = 0
        current = d1
        direction = 1 if d2 > d1 else -1
        if current.weekday() < 5:
            count += direction
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
        sep = ", " if separator is None else AirtableRuntime.S(separator)
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
            return [] if arr is None else [arr]
        return [v for v in arr if v is not None and v != ""]

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
