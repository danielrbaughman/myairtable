from datetime import datetime
from typing import Literal, Optional, overload

import dateparser
from pydantic import BaseModel

COMPARISON = Literal["=", "!=", ">", "<", ">=", "<="]


# region LOGIC
def AND(*args: str) -> str:  # noqa: N802
    """AND(arg1, arg2, ...)"""
    non_empty_args = [arg for arg in args if arg != ""]
    return f"AND({','.join(non_empty_args)})"


def OR(*args: str) -> str:  # noqa: N802
    """OR(arg1, arg2, ...)"""
    non_empty_args = [arg for arg in args if arg != ""]
    return f"OR({','.join(non_empty_args)})"


def XOR(*args: str) -> str:  # noqa: N802
    """XOR(arg1, arg2, ...)"""
    non_empty_args = [arg for arg in args if arg != ""]
    return f"XOR({','.join(non_empty_args)})"


def NOT(*args: str) -> str:  # noqa: N802
    """NOT(arg)"""
    non_empty_args = [arg for arg in args if arg != ""]
    return f"NOT({','.join(non_empty_args)})"


def IF(condition: str) -> "THEN":  # noqa: N802
    """IF(condition, valueIfTrue, valueIfFalse)"""
    return THEN(condition=condition)


class THEN(BaseModel):
    condition: str

    def THEN(self, value_if_true: str, string: bool = False) -> "ELSE":  # noqa: N802
        return ELSE(condition=self.condition, true_value=value_if_true, is_true_string=string)


class ELSE(THEN):
    true_value: str
    is_true_string: bool = False

    def ELSE(self, value_if_false: str, string: bool = False) -> str:  # noqa: N802
        true_val = f'"{self.true_value}"' if self.is_true_string else self.true_value
        false_val = f'"{value_if_false}"' if string else value_if_false
        return f"IF({self.condition}, {true_val}, {false_val})"


# endregion


# region HELPERS
def id_equals(id: str) -> str:
    """RECORD_ID()='id'"""
    return f"RECORD_ID()='{id}'"


def id_in_list(ids: list[str]) -> str:
    if not ids:
        return "FALSE()"
    elif len(ids) == 1:
        return id_equals(ids[0])
    else:
        return OR(*[id_equals(id) for id in ids])


class Field(BaseModel):
    """Base class for all Airtable field types"""

    name: str
    id: str = ""
    name_to_id_map: dict[str, str] = {}

    def __init__(self, **data):
        super().__init__(**data)
        if not self.name:
            raise ValueError("Field name cannot be empty.")
        self.id = self.name_to_id_map.get(self.name) or self.name
        self.name = self.name.replace("{", "").replace("}", "").replace("\n", "").replace("\t", "").replace("\r", "")

    def is_empty(self) -> str:
        """{field}=BLANK()"""
        return f"{{{self.id}}}=BLANK()"

    def is_not_empty(self) -> str:
        """{field}"""
        return f"{{{self.id}}}"


# endregion


# region TEXT
class TextField(Field):
    """String comparison formulas"""

    def equals(self, value: str) -> str:
        """{field}="value\" """
        escaped_value = value.replace('"', '\\"')
        return f'{{{self.id}}}="{escaped_value}"'

    def not_equals(self, value: str) -> str:
        """{field}!="value\" """
        return f'{{{self.id}}}!="{value}"'

    def _find(
        self,
        value: str,
        comparison: str,
        case_sensitive: bool = False,
        trim: bool = True,
    ) -> str:
        """case-insensitive"""
        if case_sensitive:
            if trim:
                return f'FIND(TRIM("{value}"), TRIM({{{self.id}}})){comparison}'
            else:
                return f'FIND("{value}", {{{self.id}}}){comparison}'
        else:
            if trim:
                return f'FIND(TRIM(LOWER("{value}")), TRIM(LOWER({{{self.id}}}))){comparison}'
            else:
                return f'FIND(LOWER("{value}"), LOWER({{{self.id}}})){comparison}'

    def contains(self, value: str, case_sensitive: bool = False, trim: bool = True) -> str:
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

    def contains_any(self, values: list[str], case_sensitive: bool = False, trim: bool = True) -> str:
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

    def contains_all(self, values: list[str], case_sensitive: bool = False, trim: bool = True) -> str:
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

    def not_contains(self, value: str, case_sensitive: bool = False, trim: bool = True) -> str:
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

    def starts_with(self, value: str, case_sensitive: bool = False, trim: bool = True) -> str:
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

    def not_starts_with(self, value: str, case_sensitive: bool = False, trim: bool = True) -> str:
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
    ) -> str:
        if case_sensitive:
            if trim:
                return f'FIND(TRIM("{value}"), TRIM({{{self.id}}})) {comparison} LEN(TRIM({{{self.id}}})) - LEN(TRIM("{value}")) + 1'
            else:
                return f'FIND("{value}", {{{self.id}}}) {comparison} LEN({{{self.id}}}) - LEN("{value}") + 1'
        else:
            if trim:
                return f'FIND(TRIM(LOWER("{value}")), TRIM(LOWER({{{self.id}}}))) {comparison} LEN(TRIM(LOWER({{{self.id}}}))) - LEN(TRIM(LOWER("{value}"))) + 1'
            else:
                return f'FIND(LOWER("{value}"), LOWER({{{self.id}}})) {comparison} LEN(LOWER({{{self.id}}})) - LEN(LOWER("{value}")) + 1'

    def ends_with(self, value: str, case_sensitive: bool = False, trim: bool = True) -> str:
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

    def not_ends_with(self, value: str, case_sensitive: bool = False, trim: bool = True) -> str:
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

    def regex_match(self, pattern: str) -> str:
        """
        Tests field against a regular expression pattern.

        Args:
            pattern (str): The regular expression pattern to match against the field's value.

        Returns:
            str: An Airtable formula string using REGEX_MATCH with the field name and the provided pattern.
        """
        return f'REGEX_MATCH({{{self.id}}}, "{pattern}")'


# endregion


# region NUMBER
class NumberField(Field):
    """Number comparison formulas"""

    def _compare(self, comparison: COMPARISON, value: int | float) -> str:
        return f"{{{self.id}}}{comparison}{value}"

    def equals(self, value: int | float) -> str:
        """{field}=value"""
        return self._compare("=", value)

    def not_equals(self, value: int | float) -> str:
        """{field}!=value"""
        return self._compare("!=", value)

    def greater_than(self, value: int | float) -> str:
        """{field}>value"""
        return self._compare(">", value)

    def less_than(self, value: int | float) -> str:
        """{field}<value"""
        return self._compare("<", value)

    def greater_than_or_equals(self, value: int | float) -> str:
        """{field}>value"""
        return self._compare(">=", value)

    def less_than_or_equals(self, value: int | float) -> str:
        """{field}<value"""
        return self._compare("<=", value)
    
    def between(self, min_value: int | float, max_value: int | float, inclusive: bool = True) -> str:
        """AND({field}>=min_value, {field}<=max_value)"""
        return AND(
            self.greater_than_or_equals(min_value),
            self.less_than_or_equals(max_value),
        ) if inclusive else AND(
            self.greater_than(min_value),
            self.less_than(max_value),
        )


# endregion


# region BOOLEAN
class BooleanField(Field):
    """Boolean comparison formulas"""

    def equals(self, value: bool) -> str:
        """{field}=TRUE()|FALSE()"""
        return f"{{{self.id}}}={'TRUE()' if value else 'FALSE()'}"

    def is_true(self) -> str:
        """{field}=TRUE()"""
        return f"{{{self.id}}}=TRUE()"

    def is_false(self) -> str:
        """{field}=FALSE()"""
        return f"{{{self.id}}}=FALSE()"


# endregion


# region ATTACHMENTS
class AttachmentsField(Field):
    """Attachment comparison formulas"""

    def is_not_empty(self) -> str:
        """LEN({field})>0"""
        return f"LEN({{{self.id}}})>0"

    def is_empty(self) -> str:
        """LEN({field})=0"""
        return f"LEN({{{self.id}}})=0"

    def count_is(self, count: int) -> str:
        """LEN({field})=count"""
        return f"LEN({{{self.id}}})={count}"


# endregion


# region DATE
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
    compare: COMPARISON

    def _date(self, date: str | datetime) -> str:
        parsed_date = _parse_date(date)
        return f"DATETIME_PARSE('{parsed_date}'){self.compare}DATETIME_PARSE({{{self.id}}})"

    def _ago(self, unit: str, value: int) -> str:
        return f"DATETIME_DIFF(NOW(), {{{self.id}}}, '{unit}'){self.compare}{value}"

    def milliseconds_ago(self, milliseconds: int) -> str:
        """Compare to time ago in milliseconds"""
        return self._ago("milliseconds", milliseconds)

    def seconds_ago(self, seconds: int) -> str:
        """Compare to time ago in seconds"""
        return self._ago("seconds", seconds)

    def minutes_ago(self, minutes: int) -> str:
        """Compare to time ago in minutes"""
        return self._ago("minutes", minutes)

    def hours_ago(self, hours: int) -> str:
        """Compare to time ago in hours"""
        return self._ago("hours", hours)

    def days_ago(self, days: int) -> str:
        """Compare to time ago in days"""
        return self._ago("days", days)

    def weeks_ago(self, weeks: int) -> str:
        """Compare to time ago in weeks"""
        return self._ago("weeks", weeks)

    def months_ago(self, months: int) -> str:
        """Compare to time ago in months"""
        return self._ago("months", months)

    def quarters_ago(self, quarters: int) -> str:
        """Compare to time ago in quarters"""
        return self._ago("quarters", quarters)

    def years_ago(self, years: int) -> str:
        """Compare to time ago in years"""
        return self._ago("years", years)


class DateField(Field):
    """DateTime comparison formulas"""

    @overload
    def is_on(self) -> DateComparison: ...
    @overload
    def is_on(self, date: str | datetime) -> str: ...

    def is_on(self, date: Optional[str | datetime] = None) -> DateComparison | str:
        """
        Checks if the object's date matches the specified date.

        Args:
            date (Optional[str | datetime], optional): The date to compare against. Can be a string or a datetime object.
                If None, returns a DateComparison object without a specific date.

        Returns:
            DateComparison | str: A DateComparison object set to compare equality with the specified date,
                or the DateComparison object itself if no date is provided.
        """
        date_comparison = DateComparison(name=self.id, compare="=")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)

    @overload
    def is_on_or_after(self) -> DateComparison: ...
    @overload
    def is_on_or_after(self, date: str | datetime) -> str: ...

    def is_on_or_after(self, date: Optional[str | datetime] = None) -> DateComparison | str:
        """
        Checks if the date associated with this instance is on or after the specified date.

        Args:
            date (Optional[str | datetime]): The date to compare against. Can be a string or a datetime object.
                If None, returns a DateComparison object for further configuration.

        Returns:
            DateComparison | str: A DateComparison object if no date is provided, otherwise the result of the comparison as a string.
        """
        date_comparison = DateComparison(name=self.id, compare=">=")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)

    @overload
    def is_on_or_before(self) -> DateComparison: ...
    @overload
    def is_on_or_before(self, date: str | datetime) -> str: ...

    def is_on_or_before(self, date: Optional[str | datetime] = None) -> DateComparison | str:
        """
        Checks if the date associated with this instance is on or before the specified date.

        Args:
            date (Optional[str | datetime], optional): The date to compare against. Can be a string or a datetime object.
                If None, returns a DateComparison object for further configuration. Defaults to None.

        Returns:
            DateComparison | str: If no date is provided, returns a DateComparison object configured for 'on or before' comparison.
                If a date is provided, returns the result of the comparison as a string.
        """
        date_comparison = DateComparison(name=self.id, compare="<=")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)

    @overload
    def is_after(self) -> DateComparison: ...
    @overload
    def is_after(self, date: str | datetime) -> str: ...

    def is_after(self, date: Optional[str | datetime] = None) -> DateComparison | str:
        """
        Checks if the date associated with this instance is after the specified date.

        Args:
            date (Optional[str | datetime]): The date to compare against. Can be a string or a datetime object.
                If None, returns a DateComparison object for further comparison.

        Returns:
            DateComparison | str: A DateComparison object if no date is provided, or the result of the comparison as a string.

        """
        date_comparison = DateComparison(name=self.id, compare="<")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)

    @overload
    def is_before(self) -> DateComparison: ...
    @overload
    def is_before(self, date: str | datetime) -> str: ...

    def is_before(self, date: Optional[str | datetime] = None) -> DateComparison | str:
        """
        Checks if the date associated with this instance is before the specified date.

        Args:
            date (Optional[str | datetime]): The date to compare against. Can be a string or a datetime object.
                If None, returns a DateComparison object for further configuration.

        Returns:
            DateComparison | str: A DateComparison object if no date is provided, otherwise the result of the comparison.
        """
        date_comparison = DateComparison(name=self.id, compare=">")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)

    @overload
    def is_not_on(self) -> DateComparison: ...
    @overload
    def is_not_on(self, date: str | datetime) -> str: ...

    def is_not_on(self, date: Optional[str | datetime] = None) -> DateComparison | str:
        """
        Checks if the field's date is not equal to the specified date.

        Args:
            date (Optional[str | datetime], optional): The date to compare against. Can be a string or a datetime object.
                If not provided, returns a DateComparison object for further configuration.

        Returns:
            DateComparison | str: A DateComparison object with the '!=' operator if no date is provided,
                otherwise returns the result of comparing the field's date to the parsed date.
        """
        date_comparison = DateComparison(name=self.id, compare="!=")
        if date is None:
            return date_comparison

        parsed_date: datetime = _parse_date(date)
        return date_comparison._date(parsed_date)
    
    def is_between(self, start_date: str | datetime, end_date: str | datetime, inclusive: bool = True) -> str:
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
        return AND(
            self.is_on_or_after(parsed_start_date),
            self.is_on_or_before(parsed_end_date),
        ) if inclusive else AND(
            self.is_after(parsed_start_date),
            self.is_before(parsed_end_date),
        )


# endregion
