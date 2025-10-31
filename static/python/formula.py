from datetime import datetime
from typing import Any, Optional, overload

import dateparser
from pyairtable import formulas as F  # noqa: N812
from pyairtable.formulas import AND, NOT, OR, XOR


class ID:
    """Record ID formulas"""

    @staticmethod
    def equals(id: str) -> F.Formula:
        """RECORD_ID()='id'"""
        return F.EQ(F.RECORD_ID(), id)

    def __eq__(self, id: str) -> F.Formula:
        return self.equals(id)

    @staticmethod
    def in_list(ids: list[str]) -> F.Formula:
        if not ids:
            return F.FALSE()
        elif len(ids) == 1:
            return ID.equals(ids[0])
        else:
            return OR(*[ID.equals(id) for id in ids])


class Field(F.Field):
    def __eq__(self, value: Any) -> F.Comparison:
        return super().eq(value)

    def __ne__(self, value: Any) -> F.Comparison:
        return super().ne(value)

    def __lt__(self, value: Any) -> F.Comparison:
        return super().lt(value)

    def __le__(self, value: Any) -> F.Comparison:
        return super().lte(value)

    def __gt__(self, value: Any) -> F.Comparison:
        return super().gt(value)

    def __ge__(self, value: Any) -> F.Comparison:
        return super().gte(value)

    def empty(self) -> F.Formula:
        """{field}=BLANK()"""
        return F.EQ(self, F.BLANK())

    def not_empty(self) -> F.Formula:
        """{field}"""
        return self


class TextField(Field):
    """String comparison formulas"""

    def _find(
        self,
        value: str,
        comparison: str,
        case_sensitive: bool = False,
        trim: bool = True,
    ) -> F.Formula:
        """case-insensitive"""
        formula: str

        if case_sensitive:
            if trim:
                formula = str(F.FIND(F.TRIM(value), F.TRIM(self))) + comparison
            else:
                formula = str(F.FIND(value, self)) + comparison
        else:
            if trim:
                formula = str(F.FIND(F.TRIM(F.LOWER(value)), F.TRIM(F.LOWER(self)))) + comparison
            else:
                formula = str(F.FIND(F.LOWER(value), F.LOWER(self))) + comparison

        return F.Formula(formula)

    def contains(self, value: str, case_sensitive: bool = False, trim: bool = True) -> F.Formula:
        """
        Checks if field contains a substring

        Args:
            value (str): The substring to search for within the field.
            case_sensitive (bool, optional): Whether the search should be case-sensitive. Defaults to False.
            trim (bool, optional): Whether to trim whitespace from the field and value before searching. Defaults to True.

        Returns:
            str: An Airtable formula string that evaluates to True if the field contains the substring, otherwise False.
        """
        return self._find(value, ">0", case_sensitive=case_sensitive, trim=trim)

    def contains_any(self, values: list[str], case_sensitive: bool = False, trim: bool = True) -> F.Formula:
        """
        Checks if field contains any of the substrings in the provided list.

        Args:
            values (list[str]): The list of substrings to search for within the field.
            case_sensitive (bool, optional): Whether the search should be case-sensitive. Defaults to False.
            trim (bool, optional): Whether to trim whitespace from the field and values before searching. Defaults to True.

        Returns:
            str: An Airtable formula string that evaluates to True if the field contains any of the substrings, otherwise False.
        """
        return OR(*[self.contains(value, case_sensitive=case_sensitive, trim=trim) for value in values])

    def contains_all(self, values: list[str], case_sensitive: bool = False, trim: bool = True) -> F.Formula:
        """
        Checks if field contains all of the substrings in the provided list.

        Args:
            values (list[str]): The list of substrings to search for within the field.
            case_sensitive (bool, optional): Whether the search should be case-sensitive. Defaults to False.
            trim (bool, optional): Whether to trim whitespace from the field and values before searching. Defaults to True.

        Returns:
            str: An Airtable formula string that evaluates to True if the field contains all of the substrings, otherwise False.
        """
        return AND(*[self.contains(value, case_sensitive=case_sensitive, trim=trim) for value in values])

    def not_contains(self, value: str, case_sensitive: bool = False, trim: bool = True) -> F.Formula:
        """
        Checks if field does not contain a substring

        Args:
            value (str): The substring to check for absence in the field.
            case_sensitive (bool, optional): Whether the check should be case-sensitive. Defaults to False.
            trim (bool, optional): Whether to trim whitespace from the field before checking. Defaults to True.

        Returns:
            str: An Airtable formula string that evaluates to True if the field does not contain the value.
        """
        return self._find(value, "=0", case_sensitive=case_sensitive, trim=trim)

    def starts_with(self, value: str, case_sensitive: bool = False, trim: bool = True) -> F.Formula:
        """
        Checks if the field value starts with the specified substring.

        Args:
            value (str): The substring to check at the start of the field value.
            case_sensitive (bool, optional): Whether the comparison should be case-sensitive. Defaults to False.
            trim (bool, optional): Whether to trim whitespace from the field value before checking. Defaults to True.

        Returns:
            str: The Airtable formula string representing the 'starts with' condition.
        """
        return self._find(value, "=1", case_sensitive=case_sensitive, trim=trim)

    def not_starts_with(self, value: str, case_sensitive: bool = False, trim: bool = True) -> F.Formula:
        """
        Checks if the field value does not start with the specified substring.

        Args:
            value (str): The substring to check at the start of the field value.
            case_sensitive (bool, optional): Whether the comparison should be case-sensitive. Defaults to False.
            trim (bool, optional): Whether to trim whitespace from the field value before checking. Defaults to True.

        Returns:
            str: The Airtable formula string representing the 'not starts with' condition.
        """
        return self._find(value, "!=1", case_sensitive=case_sensitive, trim=trim)

    def _ends_with(
        self,
        value: str,
        comparison: str,
        case_sensitive: bool = False,
        trim: bool = True,
    ) -> F.Formula:
        actual_index: F.Formula
        field_length: F.Formula
        value_length: F.Formula

        if case_sensitive:
            if trim:
                actual_index = F.FIND(F.TRIM(value), F.TRIM(self))
                field_length = F.LEN(F.TRIM(self))
                value_length = F.LEN(F.TRIM(value))
            else:
                actual_index = F.FIND(value, self)
                field_length = F.LEN(self)
                value_length = F.LEN(value)
        else:
            if trim:
                actual_index = F.FIND(F.TRIM(F.LOWER(value)), F.TRIM(F.LOWER(self)))
                field_length = F.LEN(F.TRIM(F.LOWER(self)))
                value_length = F.LEN(F.TRIM(F.LOWER(value)))
            else:
                actual_index = F.FIND(F.LOWER(value), F.LOWER(self))
                field_length = F.LEN(F.LOWER(self))
                value_length = F.LEN(F.LOWER(value))

        expected_index = F.Formula(f"{field_length} - {value_length} + 1")
        return F.Formula(f"{actual_index} {comparison} {expected_index}")

    def ends_with(self, value: str, case_sensitive: bool = False, trim: bool = True) -> F.Formula:
        """
        Checks if the target string ends with the specified substring.

        Args:
            value (str): The substring to check for at the end of the target string.
            case_sensitive (bool, optional): Whether the comparison should be case-sensitive. Defaults to False.
            trim (bool, optional): Whether to trim whitespace from the target string before checking. Defaults to True.

        Returns:
            str: The formula or expression representing the ends-with check.

        Note:
            The comparison is case-insensitive by default.
        """
        return self._ends_with(value, "=", case_sensitive=case_sensitive, trim=trim)

    def not_ends_with(self, value: str, case_sensitive: bool = False, trim: bool = True) -> F.Formula:
        """
        Checks if the field value does not end with the specified substring.

        Args:
            value (str): The substring to check against the end of the field value.
            case_sensitive (bool, optional): Whether the comparison should be case-sensitive. Defaults to False.
            trim (bool, optional): Whether to trim whitespace from the field value before comparison. Defaults to True.

        Returns:
            str: The Airtable formula string representing the 'not ends with' condition.
        """
        return self._ends_with(value, "!=", case_sensitive=case_sensitive, trim=trim)

    def regex_match(self, pattern: str) -> F.Formula:
        """
        Tests field against a regular expression pattern.

        Args:
            pattern (str): The regular expression pattern to match against the field's value.

        Returns:
            str: An Airtable formula string using REGEX_MATCH with the field name and the provided pattern.
        """
        return F.REGEX_MATCH(self, pattern)


class NumberField(Field):
    """Number comparison formulas"""

    def between(self, min_value: int | float, max_value: int | float, inclusive: bool = True) -> F.Formula:
        """AND({field}>=min_value, {field}<=max_value)"""
        if inclusive:
            return AND(
                self.gte(min_value),
                self.lte(max_value),
            )
        else:
            return AND(
                self.gt(min_value),
                self.lt(max_value),
            )


class BooleanField(Field):
    """Boolean comparison formulas"""

    def eq(self, value: bool) -> F.Formula:
        """{field}=TRUE()|FALSE()"""
        return F.EQ(self, F.TRUE() if value else F.FALSE())

    def true(self) -> F.Formula:
        """{field}=TRUE()"""
        return F.EQ(self, F.TRUE())

    def false(self) -> F.Formula:
        """{field}=FALSE()"""
        return F.EQ(self, F.FALSE())

    def __call__(self) -> F.Formula:
        return self.true()

    def __invert__(self):
        return self.false()


class AttachmentsField(Field):
    """Attachment comparison formulas"""

    def count(self, count: int) -> F.Formula:
        """LEN({field})=count"""
        return F.EQ(F.LEN(self), count)


def _parse_date(date: datetime | str) -> datetime:
    if isinstance(date, datetime):
        parsed_date = date
    else:
        result: datetime | None = dateparser.parse(date)
        if result is None:
            raise ValueError(f"Could not parse date: {date}")
        parsed_date: datetime = result
    return parsed_date


class DateComparison(Field):
    compare: str

    def __init__(self, name: str, compare: str) -> None:
        super().__init__(name)
        self.compare = compare

    def _date(self, date: datetime) -> F.Formula:
        left_side = F.DATETIME_PARSE(date.isoformat())
        right_side = F.DATETIME_PARSE(self)
        return F.Formula(f"{left_side}{self.compare}{right_side}")

    def _ago(self, unit: str, value: int) -> F.Formula:
        time_ago = F.DATETIME_DIFF(F.NOW(), F.DATETIME_PARSE(self), unit)
        return F.Formula(f"{time_ago}{self.compare}{value}")

    def milliseconds_ago(self, milliseconds: int) -> F.Formula:
        """Compare to time ago in milliseconds"""
        return self._ago("milliseconds", milliseconds)

    def seconds_ago(self, seconds: int) -> F.Formula:
        """Compare to time ago in seconds"""
        return self._ago("seconds", seconds)

    def minutes_ago(self, minutes: int) -> F.Formula:
        """Compare to time ago in minutes"""
        return self._ago("minutes", minutes)

    def hours_ago(self, hours: int) -> F.Formula:
        """Compare to time ago in hours"""
        return self._ago("hours", hours)

    def days_ago(self, days: int) -> F.Formula:
        """Compare to time ago in days"""
        return self._ago("days", days)

    def weeks_ago(self, weeks: int) -> F.Formula:
        """Compare to time ago in weeks"""
        return self._ago("weeks", weeks)

    def months_ago(self, months: int) -> F.Formula:
        """Compare to time ago in months"""
        return self._ago("months", months)

    def quarters_ago(self, quarters: int) -> F.Formula:
        """Compare to time ago in quarters"""
        return self._ago("quarters", quarters)

    def years_ago(self, years: int) -> F.Formula:
        """Compare to time ago in years"""
        return self._ago("years", years)


class DateField(Field):
    """DateTime comparison formulas"""

    @overload
    def on(self) -> DateComparison: ...
    @overload
    def on(self, date: str | datetime) -> F.Formula: ...

    def on(self, date: Optional[str | datetime] = None) -> DateComparison | F.Formula:
        """
        Checks if the object's date matches the specified date.

        Args:
            date (Optional[str | datetime], optional): The date to compare against. Can be a string or a datetime object.
                If None, returns a DateComparison object without a specific date.

        Returns:
            DateComparison | str: A DateComparison object set to compare equality with the specified date,
                or the DateComparison object itself if no date is provided.
        """
        date_comparison = DateComparison(name=self.value, compare="=")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)

    def __eq__(self, date: str | datetime) -> F.Formula:
        return self.on(date)

    @overload
    def on_or_after(self) -> DateComparison: ...
    @overload
    def on_or_after(self, date: str | datetime) -> F.Formula: ...

    def on_or_after(self, date: Optional[str | datetime] = None) -> DateComparison | F.Formula:
        """
        Checks if the date associated with this instance is on or after the specified date.

        Args:
            date (Optional[str | datetime]): The date to compare against. Can be a string or a datetime object.
                If None, returns a DateComparison object for further configuration.

        Returns:
            DateComparison | str: A DateComparison object if no date is provided, otherwise the result of the comparison as a string.
        """
        date_comparison = DateComparison(name=self.value, compare=">=")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)

    def __ge__(self, date: str | datetime) -> str:
        return self.on_or_after(date)

    @overload
    def on_or_before(self) -> DateComparison: ...
    @overload
    def on_or_before(self, date: str | datetime) -> F.Formula: ...

    def on_or_before(self, date: Optional[str | datetime] = None) -> DateComparison | F.Formula:
        """
        Checks if the date associated with this instance is on or before the specified date.

        Args:
            date (Optional[str | datetime], optional): The date to compare against. Can be a string or a datetime object.
                If None, returns a DateComparison object for further configuration. Defaults to None.

        Returns:
            DateComparison | str: If no date is provided, returns a DateComparison object configured for 'on or before' comparison.
                If a date is provided, returns the result of the comparison as a string.
        """
        date_comparison = DateComparison(name=self.value, compare="<=")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)

    def __le__(self, date: str | datetime) -> str:
        return self.on_or_before(date)

    @overload
    def after(self) -> DateComparison: ...
    @overload
    def after(self, date: str | datetime) -> F.Formula: ...

    def after(self, date: Optional[str | datetime] = None) -> DateComparison | F.Formula:
        """
        Checks if the date associated with this instance is after the specified date.

        Args:
            date (Optional[str | datetime]): The date to compare against. Can be a string or a datetime object.
                If None, returns a DateComparison object for further comparison.

        Returns:
            DateComparison | str: A DateComparison object if no date is provided, or the result of the comparison as a string.

        """
        date_comparison = DateComparison(name=self.value, compare="<")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)

    def __lt__(self, date: str | datetime) -> F.Formula:
        return self.after(date)

    @overload
    def before(self) -> DateComparison: ...
    @overload
    def before(self, date: str | datetime) -> F.Formula: ...

    def before(self, date: Optional[str | datetime] = None) -> DateComparison | F.Formula:
        """
        Checks if the date associated with this instance is before the specified date.

        Args:
            date (Optional[str | datetime]): The date to compare against. Can be a string or a datetime object.
                If None, returns a DateComparison object for further configuration.

        Returns:
            DateComparison | str: A DateComparison object if no date is provided, otherwise the result of the comparison.
        """
        date_comparison = DateComparison(name=self.value, compare=">")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)

    def __gt__(self, date: str | datetime) -> F.Formula:
        return self.before(date)

    @overload
    def not_on(self) -> DateComparison: ...
    @overload
    def not_on(self, date: str | datetime) -> F.Formula: ...

    def not_on(self, date: Optional[str | datetime] = None) -> DateComparison | F.Formula:
        """
        Checks if the field's date is not equal to the specified date.

        Args:
            date (Optional[str | datetime], optional): The date to compare against. Can be a string or a datetime object.
                If not provided, returns a DateComparison object for further configuration.

        Returns:
            DateComparison | str: A DateComparison object with the '!=' operator if no date is provided,
                otherwise returns the result of comparing the field's date to the parsed date.
        """
        date_comparison = DateComparison(name=self.value, compare="!=")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)

    def __ne__(self, date: str | datetime) -> F.Formula:
        return self.not_on(date)

    def between(self, start_date: str | datetime, end_date: str | datetime, inclusive: bool = True) -> F.Formula:
        """
        Check if the date falls between two given dates.

        Args:
            start_date (str | datetime): The start date for the range comparison.
                Can be a string or datetime object.
            end_date (str | datetime): The end date for the range comparison.
                Can be a string or datetime object.
            inclusive (bool, optional): Whether to include the boundary dates in the comparison.
                If True, uses >= and <= operators. If False, uses > and < operators.
                Defaults to True.

        Returns:
            str: A formula string that evaluates to True if the date is between
                 the start and end dates according to the inclusive parameter.
        """
        parsed_start_date: datetime = _parse_date(start_date)
        parsed_end_date: datetime = _parse_date(end_date)
        if inclusive:
            return AND(
                self.gte(parsed_start_date),
                self.lte(parsed_end_date),
            )
        else:
            return AND(
                self.gt(parsed_start_date),
                self.lt(parsed_end_date),
            )


__all__ = [
    "AND",
    "OR",
    "XOR",
    "NOT",
    "ID",
    "TextField",
    "NumberField",
    "BooleanField",
    "AttachmentsField",
    "DateField",
]
