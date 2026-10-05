"""ORM field descriptors for the generated models, where pyairtable's own are too strict.

Airtable's schema gives a formula or rollup a result type of `date` or `dateTime`, but
that only records how the field is DISPLAYED (with or without a time). The API returns
whatever the formula evaluated to, which for a "date" can be any of:

    "2026-10-03"                  IF({Date}, {Date})
    "2026-10-03T00:00:00.000Z"    DATETIME_PARSE(...), LAST_MODIFIED_TIME(...)
    ["2026-10-03"]                {a lookup of dates}
    {"error": "#ERROR!"}          the formula failed for this record

pyairtable's DateField parses the first and raises on the rest, and since pyairtable
parses every field while building a model, one such value makes the whole RECORD
unreadable -- whether or not anyone wanted that field. A computed field must never do
that: it is read-only, and nothing a caller does can make Airtable return another shape.
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from pyairtable import utils
from pyairtable.orm.fields import DateField, DatetimeField


def _read(value: Any, parse: Callable[[str], Any]) -> Any:
    """`value` as the API returned it, parsed wherever it holds a date. Never raises."""
    if isinstance(value, list):
        return [_read(item, parse) for item in value]
    if isinstance(value, dict):
        # An error or special value. The table classes blank these before a model is
        # built; a record fetched through a link field arrives with them still in place.
        return None
    if not isinstance(value, str):
        return value
    try:
        return parse(value)
    except ValueError:
        return value


def _write(value: Any) -> Any:
    """The inverse of `_read`, for `to_record()`, which serializes read-only fields too."""
    if isinstance(value, list):
        return [_write(item) for item in value]
    if isinstance(value, datetime):  # before `date`: a datetime is one
        return utils.datetime_to_iso_str(value)
    if isinstance(value, date):
        return utils.date_to_iso_str(value)
    return value


def _date_or_datetime(value: str) -> date | datetime:
    try:
        return utils.date_from_iso_str(value)
    except ValueError:
        return utils.datetime_from_iso_str(value)


class ComputedDateField(DateField):
    """
    A formula or rollup whose result Airtable calls a `date`.

    Reads as a `date` when the API returns one, as DateField does. A date-time reads as a
    `datetime`, a list as a list of either, and anything unparseable is left as it came.
    """

    def to_internal_value(self, value: Any) -> Any:
        return _read(value, _date_or_datetime)

    def to_record_value(self, value: Any) -> Any:
        return _write(value)


class ComputedDatetimeField(DatetimeField):
    """
    A formula or rollup whose result Airtable calls a `dateTime`.

    Reads as a `datetime`, as DatetimeField does. A list reads as a list of them, and
    anything unparseable is left as it came.
    """

    def to_internal_value(self, value: Any) -> Any:
        return _read(value, utils.datetime_from_iso_str)

    def to_record_value(self, value: Any) -> Any:
        return _write(value)
