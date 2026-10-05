"""Hermetic guards on the computed date fields the Python generator emits.

A formula or rollup that Airtable's schema types as a `date` does not reliably come
back from the API as one: the result type records how the field is displayed. Found in
production, where three such fields made every shipped Box and most Box Shipments
unreadable -- pyairtable parses every field while building a model, so a single value
its DateField rejects fails the whole `from_record`.

Each shape below was observed on a real "date" formula. The live suite in
`myairtable-tests` proves Airtable still returns them; this pins what the fields do
with each, with no network.
"""

from datetime import date, datetime, timezone
from typing import Any

import pytest
from pyairtable.orm import Model, fields

from myairtable.static.python.orm_fields import ComputedDateField, ComputedDatetimeField
from myairtable.static.python.table_helpers import copy_model

TEXT_FIELD = "fldText00000000001"
DATE_FORMULA = "fldDateFormula0001"
DATETIME_FORMULA = "fldDatetimeForm001"
STRICT_DATE_FORMULA = "fldStrictDate00001"

DATE_ONLY = "2026-10-03"
DATE_TIME = "2026-10-03T19:04:05.000Z"
ERROR = {"error": "#ERROR!"}


class Computed(Model):
    """Stands in for a generated ORM model: field ids as field names, computed fields
    marked readonly -- exactly what the Python generator emits."""

    class Meta:
        api_key = "keyFAKE0000000000"
        base_id = "appFAKE0000000000"
        table_name = "tblFAKE0000000001"
        use_field_ids = True
        memoize = True

    text = fields.TextField(TEXT_FIELD)
    as_date = ComputedDateField(DATE_FORMULA, readonly=True)
    as_datetime = ComputedDatetimeField(DATETIME_FORMULA, readonly=True)


class Strict(Model):
    """The same computed date on pyairtable's own DateField, as the generator used to emit it."""

    class Meta:
        api_key = "keyFAKE0000000000"
        base_id = "appFAKE0000000000"
        table_name = "tblFAKE0000000002"
        use_field_ids = True
        memoize = True

    text = fields.TextField(TEXT_FIELD)
    as_date = fields.DateField(STRICT_DATE_FORMULA, readonly=True)


def _record(**record_fields: Any) -> Computed:
    return Computed.from_record(
        {"id": "recSOURCE000000001", "createdTime": "2026-01-01T00:00:00.000Z", "fields": {TEXT_FIELD: "hello", **record_fields}},
        memoize=False,
    )


class TestTheBugBeingFixed:
    """What pyairtable's DateField does with the same values, so the fix is not vacuous."""

    @pytest.mark.parametrize("value", [DATE_TIME, [DATE_ONLY], ERROR])
    def test_strict_date_field_makes_the_whole_record_unreadable(self, value: Any) -> None:
        with pytest.raises((TypeError, ValueError)):
            Strict.from_record(
                {"id": "recSOURCE000000001", "createdTime": "2026-01-01T00:00:00.000Z", "fields": {TEXT_FIELD: "hello", STRICT_DATE_FORMULA: value}},
                memoize=False,
            )


class TestComputedDateField:
    def test_date_string_reads_as_a_date(self) -> None:
        value = _record(**{DATE_FORMULA: DATE_ONLY}).as_date
        assert value == date(2026, 10, 3)
        assert not isinstance(value, datetime), "a date-only value must stay a date, as DateField read it"

    def test_date_time_string_reads_as_a_datetime(self) -> None:
        assert _record(**{DATE_FORMULA: DATE_TIME}).as_date == datetime(2026, 10, 3, 19, 4, 5, tzinfo=timezone.utc)

    def test_list_reads_as_a_list_of_dates(self) -> None:
        assert _record(**{DATE_FORMULA: [DATE_ONLY, "2026-10-04"]}).as_date == [date(2026, 10, 3), date(2026, 10, 4)]

    def test_list_of_date_times_reads_as_a_list_of_datetimes(self) -> None:
        assert _record(**{DATE_FORMULA: [DATE_TIME]}).as_date == [datetime(2026, 10, 3, 19, 4, 5, tzinfo=timezone.utc)]

    def test_error_value_reads_as_none(self) -> None:
        assert _record(**{DATE_FORMULA: ERROR}).as_date is None

    def test_error_value_inside_a_list_reads_as_none(self) -> None:
        assert _record(**{DATE_FORMULA: [DATE_ONLY, ERROR]}).as_date == [date(2026, 10, 3), None]

    def test_unparseable_string_is_left_as_it_came(self) -> None:
        assert _record(**{DATE_FORMULA: "not a date"}).as_date == "not a date"

    def test_missing_value_reads_as_none(self) -> None:
        assert _record().as_date is None

    @pytest.mark.parametrize("value", [DATE_ONLY, DATE_TIME, [DATE_ONLY], [DATE_TIME], ERROR, "not a date", 5])
    def test_no_value_makes_the_rest_of_the_record_unreadable(self, value: Any) -> None:
        assert _record(**{DATE_FORMULA: value}).text == "hello"

    def test_is_still_read_only(self) -> None:
        record = _record(**{DATE_FORMULA: DATE_ONLY})
        with pytest.raises(AttributeError):
            record.as_date = date(2026, 1, 1)


class TestComputedDatetimeField:
    def test_date_time_string_reads_as_a_datetime(self) -> None:
        assert _record(**{DATETIME_FORMULA: DATE_TIME}).as_datetime == datetime(2026, 10, 3, 19, 4, 5, tzinfo=timezone.utc)

    def test_date_string_reads_as_a_datetime(self) -> None:
        # What DatetimeField has always made of a date-only string; unchanged.
        assert _record(**{DATETIME_FORMULA: DATE_ONLY}).as_datetime == datetime(2026, 10, 3)

    def test_list_reads_as_a_list_of_datetimes(self) -> None:
        assert _record(**{DATETIME_FORMULA: [DATE_TIME]}).as_datetime == [datetime(2026, 10, 3, 19, 4, 5, tzinfo=timezone.utc)]

    def test_error_value_reads_as_none(self) -> None:
        assert _record(**{DATETIME_FORMULA: ERROR}).as_datetime is None

    @pytest.mark.parametrize("value", [DATE_ONLY, DATE_TIME, [DATE_TIME], ERROR, "not a date", 5])
    def test_no_value_makes_the_rest_of_the_record_unreadable(self, value: Any) -> None:
        assert _record(**{DATETIME_FORMULA: value}).text == "hello"


class TestSerializing:
    """`to_record()` serializes read-only fields too, and `ORMTable.update()` and `copy()`
    both call it -- so a value that reads must also write back out without raising."""

    @pytest.mark.parametrize("value", [DATE_ONLY, DATE_TIME, [DATE_ONLY], [DATE_TIME], "not a date"])
    def test_computed_date_round_trips_through_to_record(self, value: Any) -> None:
        assert _record(**{DATE_FORMULA: value}).to_record()["fields"][DATE_FORMULA] == value

    @pytest.mark.parametrize("value", [DATE_TIME, [DATE_TIME], "not a date"])
    def test_computed_datetime_round_trips_through_to_record(self, value: Any) -> None:
        assert _record(**{DATETIME_FORMULA: value}).to_record()["fields"][DATETIME_FORMULA] == value

    def test_error_value_serializes_as_none(self) -> None:
        assert _record(**{DATE_FORMULA: ERROR}).to_record()["fields"][DATE_FORMULA] is None

    def test_computed_fields_are_left_out_of_a_writable_record(self) -> None:
        record = _record(**{DATE_FORMULA: [DATE_ONLY], DATETIME_FORMULA: DATE_TIME})
        assert set(record.to_record(only_writable=True)["fields"]) == {TEXT_FIELD}

    def test_copy_carries_a_list_valued_computed_date(self) -> None:
        copied = copy_model(_record(**{DATE_FORMULA: [DATE_ONLY], DATETIME_FORMULA: DATE_TIME}))
        assert copied.as_date == [date(2026, 10, 3)]
        assert copied.as_datetime == datetime(2026, 10, 3, 19, 4, 5, tzinfo=timezone.utc)
