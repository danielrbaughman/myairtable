"""Tests for the formula.py module - Airtable formula generation."""

import sys
from datetime import datetime
from pathlib import Path

import pytest
from pyairtable import formulas as F  # noqa: N812

sys.path.insert(0, str(Path(__file__).parent.parent / "static" / "python"))

from formula import (  # type: ignore[attr-defined]
    AND,
    ID,
    NOT,
    OR,
    XOR,
    AttachmentsField,
    BooleanField,
    DateComparison,
    DateField,
    Field,
    MultiSelectField,
    NumberField,
    SingleSelectField,
    TextField,
    _parse_date,
)


class TestID:
    """Test ID class for record ID formulas."""

    def test_equals_valid_id(self):
        """ID.equals returns correct formula for valid record ID."""
        result = ID.equals("rec12345678901234")
        assert "RECORD_ID()" in str(result)
        assert "rec12345678901234" in str(result)

    def test_equals_returns_formula(self):
        """ID.equals returns a Formula object."""
        result = ID.equals("rec12345678901234")
        assert isinstance(result, F.Formula)

    def test_in_list_empty_returns_false(self):
        """Empty list returns FALSE() formula."""
        result = ID.in_list([])
        assert "FALSE()" in str(result)

    def test_in_list_single_id(self):
        """Single ID in list delegates to equals."""
        result = ID.in_list(["rec12345678901234"])
        assert "RECORD_ID()" in str(result)
        assert "rec12345678901234" in str(result)

    def test_in_list_multiple_ids(self):
        """Multiple IDs produce OR formula."""
        result = ID.in_list(["rec12345678901234", "rec56789012345678"])
        result_str = str(result)
        assert "OR(" in result_str
        assert "rec12345678901234" in result_str
        assert "rec56789012345678" in result_str


class TestField:
    """Test base Field class."""

    def test_empty_returns_blank_formula(self):
        """empty() returns {field}=BLANK() formula."""
        field = Field("Name")
        result = field.empty()
        assert "BLANK()" in str(result)

    def test_not_empty_returns_self(self):
        """not_empty() returns the field itself."""
        field = Field("Name")
        result = field.not_empty()
        assert result is field

    def test_dunder_eq(self):
        """__eq__ uses parent eq method."""
        field = Field("Name")
        result = field == "value"
        assert "Name" in str(result)
        assert "value" in str(result)

    def test_dunder_ne(self):
        """__ne__ uses parent ne method."""
        field = Field("Name")
        result = field != "value"
        assert "Name" in str(result)

    def test_dunder_lt(self):
        """__lt__ comparison operator."""
        field = Field("Amount")
        result = field < 100
        assert "Amount" in str(result)
        assert "<" in str(result)

    def test_dunder_le(self):
        """__le__ comparison operator."""
        field = Field("Amount")
        result = field <= 100
        assert "Amount" in str(result)
        assert "<=" in str(result)

    def test_dunder_gt(self):
        """__gt__ comparison operator."""
        field = Field("Amount")
        result = field > 100
        assert "Amount" in str(result)
        assert ">" in str(result)

    def test_dunder_ge(self):
        """__ge__ comparison operator."""
        field = Field("Amount")
        result = field >= 100
        assert "Amount" in str(result)
        assert ">=" in str(result)


class TestTextField:
    """Test TextField string comparison formulas."""

    # equals() tests - all 4 combinations of case_sensitive and trim
    def test_equals_case_sensitive_no_trim(self):
        """Default: case_sensitive=True, trim=False uses LOWER."""
        field = TextField("Name")
        result = field.equals("John", case_sensitive=True, trim=False)
        result_str = str(result)
        assert "LOWER(" in result_str
        assert "Name" in result_str

    def test_equals_case_sensitive_with_trim(self):
        """case_sensitive=True, trim=True uses LOWER and TRIM."""
        field = TextField("Name")
        result = field.equals("John", case_sensitive=True, trim=True)
        result_str = str(result)
        assert "LOWER(" in result_str
        assert "TRIM(" in result_str

    def test_equals_case_insensitive_no_trim(self):
        """case_sensitive=False, trim=False uses direct comparison."""
        field = TextField("Name")
        result = field.equals("John", case_sensitive=False, trim=False)
        result_str = str(result)
        assert "Name" in result_str

    def test_equals_case_insensitive_with_trim(self):
        """case_sensitive=False, trim=True uses TRIM."""
        field = TextField("Name")
        result = field.equals("John", case_sensitive=False, trim=True)
        result_str = str(result)
        assert "TRIM(" in result_str

    # phone_equals tests
    def test_phone_equals_normalizes_spaces(self):
        """phone_equals removes spaces from phone numbers."""
        field = TextField("Phone")
        result = field.phone_equals("555 123 4567")
        result_str = str(result)
        assert "SUBSTITUTE" in result_str
        assert "TRIM(" in result_str

    def test_phone_equals_normalizes_dashes(self):
        """phone_equals removes dashes."""
        field = TextField("Phone")
        result = field.phone_equals("555-123-4567")
        assert "SUBSTITUTE" in str(result)

    def test_phone_equals_normalizes_parentheses(self):
        """phone_equals removes parentheses."""
        field = TextField("Phone")
        result = field.phone_equals("(555) 123-4567")
        assert "SUBSTITUTE" in str(result)

    def test_phone_equals_normalizes_plus(self):
        """phone_equals removes plus sign."""
        field = TextField("Phone")
        result = field.phone_equals("+1 555 123 4567")
        assert "SUBSTITUTE" in str(result)

    def test_phone_equals_normalizes_dots(self):
        """phone_equals removes dots."""
        field = TextField("Phone")
        result = field.phone_equals("555.123.4567")
        assert "SUBSTITUTE" in str(result)

    # _find helper tests (via contains)
    def test_find_case_sensitive_with_trim(self):
        """_find with case_sensitive=True, trim=True."""
        field = TextField("Name")
        result = field.contains("test", case_sensitive=True, trim=True)
        result_str = str(result)
        assert "FIND(" in result_str
        assert "TRIM(" in result_str
        assert ">0" in result_str

    def test_find_case_sensitive_no_trim(self):
        """_find with case_sensitive=True, trim=False."""
        field = TextField("Name")
        result = field.contains("test", case_sensitive=True, trim=False)
        result_str = str(result)
        assert "FIND(" in result_str
        assert "TRIM(" not in result_str

    def test_find_case_insensitive_with_trim(self):
        """_find with case_sensitive=False, trim=True (default)."""
        field = TextField("Name")
        result = field.contains("test")
        result_str = str(result)
        assert "FIND(" in result_str
        assert "LOWER(" in result_str
        assert "TRIM(" in result_str

    def test_find_case_insensitive_no_trim(self):
        """_find with case_sensitive=False, trim=False."""
        field = TextField("Name")
        result = field.contains("test", case_sensitive=False, trim=False)
        result_str = str(result)
        assert "FIND(" in result_str
        assert "LOWER(" in result_str
        assert "TRIM(" not in result_str

    # contains tests
    def test_contains_basic(self):
        """contains returns FIND > 0 formula."""
        field = TextField("Description")
        result = field.contains("keyword")
        result_str = str(result)
        assert "FIND(" in result_str
        assert ">0" in result_str

    # contains_any tests
    def test_contains_any_empty_array(self):
        """contains_any with empty array raises ValueError (pyairtable requires at least one component)."""
        field = TextField("Tags")
        with pytest.raises(ValueError, match="requires at least one component"):
            field.contains_any([])

    def test_contains_any_single_value(self):
        """contains_any with single value."""
        field = TextField("Tags")
        result = field.contains_any(["tag1"])
        assert "FIND(" in str(result)

    def test_contains_any_multiple_values(self):
        """contains_any with multiple values produces OR."""
        field = TextField("Tags")
        result = field.contains_any(["tag1", "tag2"])
        result_str = str(result)
        assert "OR(" in result_str

    # contains_all tests
    def test_contains_all_empty_array(self):
        """contains_all with empty array raises ValueError (pyairtable requires at least one component)."""
        field = TextField("Tags")
        with pytest.raises(ValueError, match="requires at least one component"):
            field.contains_all([])

    def test_contains_all_multiple_values(self):
        """contains_all produces AND formula."""
        field = TextField("Tags")
        result = field.contains_all(["tag1", "tag2"])
        result_str = str(result)
        assert "AND(" in result_str

    # not_contains tests
    def test_not_contains_basic(self):
        """not_contains returns FIND = 0 formula."""
        field = TextField("Description")
        result = field.not_contains("keyword")
        result_str = str(result)
        assert "FIND(" in result_str
        assert "=0" in result_str

    # starts_with tests
    def test_starts_with_basic(self):
        """starts_with returns FIND = 1 formula."""
        field = TextField("Name")
        result = field.starts_with("prefix")
        result_str = str(result)
        assert "FIND(" in result_str
        assert "=1" in result_str

    # not_starts_with tests
    def test_not_starts_with_basic(self):
        """not_starts_with returns FIND != 1 formula."""
        field = TextField("Name")
        result = field.not_starts_with("prefix")
        result_str = str(result)
        assert "FIND(" in result_str
        assert "!=1" in result_str

    # _ends_with helper tests - all 4 combinations
    def test_ends_with_case_sensitive_with_trim(self):
        """_ends_with with case_sensitive=True, trim=True."""
        field = TextField("Name")
        result = field.ends_with("suffix", case_sensitive=True, trim=True)
        result_str = str(result)
        assert "FIND(" in result_str
        assert "LEN(" in result_str
        assert "TRIM(" in result_str

    def test_ends_with_case_sensitive_no_trim(self):
        """_ends_with with case_sensitive=True, trim=False."""
        field = TextField("Name")
        result = field.ends_with("suffix", case_sensitive=True, trim=False)
        result_str = str(result)
        assert "FIND(" in result_str
        assert "LEN(" in result_str
        assert "TRIM(" not in result_str

    def test_ends_with_case_insensitive_with_trim(self):
        """_ends_with with case_sensitive=False, trim=True (default)."""
        field = TextField("Name")
        result = field.ends_with("suffix")
        result_str = str(result)
        assert "FIND(" in result_str
        assert "LEN(" in result_str
        assert "LOWER(" in result_str
        assert "TRIM(" in result_str

    def test_ends_with_case_insensitive_no_trim(self):
        """_ends_with with case_sensitive=False, trim=False."""
        field = TextField("Name")
        result = field.ends_with("suffix", case_sensitive=False, trim=False)
        result_str = str(result)
        assert "FIND(" in result_str
        assert "LEN(" in result_str
        assert "LOWER(" in result_str
        assert "TRIM(" not in result_str

    # ends_with comparison operator
    def test_ends_with_uses_equals_comparison(self):
        """ends_with uses = comparison."""
        field = TextField("Name")
        result = field.ends_with("suffix")
        assert " = " in str(result)

    # not_ends_with tests
    def test_not_ends_with_uses_not_equals_comparison(self):
        """not_ends_with uses != comparison."""
        field = TextField("Name")
        result = field.not_ends_with("suffix")
        assert " != " in str(result)

    # regex_match tests
    def test_regex_match_basic(self):
        """regex_match produces REGEX_MATCH formula."""
        field = TextField("Email")
        result = field.regex_match(r"^[a-z]+@[a-z]+\.com$")
        assert "REGEX_MATCH(" in str(result)


class TestSingleSelectField:
    """Test SingleSelectField comparison formulas."""

    def test_equals_delegates_to_text_field(self):
        """equals delegates to TextField.equals."""
        field = SingleSelectField("Status")
        result = field.equals("Active")
        result_str = str(result)
        assert "Status" in result_str
        assert "Active" in result_str

    def test_eq_method(self):
        """eq method for typed comparisons."""
        field = SingleSelectField("Status")
        result = field.eq("Active")
        result_str = str(result)
        assert "Status" in result_str

    def test_ne_method(self):
        """ne method for typed comparisons."""
        field = SingleSelectField("Status")
        result = field.ne("Inactive")
        result_str = str(result)
        assert "Status" in result_str


class TestMultiSelectField:
    """Test MultiSelectField comparison formulas."""

    def test_contains_option_basic(self):
        """contains_option checks for substring."""
        field = MultiSelectField("Tags")
        result = field.contains_option("Option1")
        assert "FIND(" in str(result)

    def test_contains_option_with_case_sensitivity(self):
        """contains_option respects case_sensitive flag."""
        field = MultiSelectField("Tags")
        result = field.contains_option("Option1", case_sensitive=False, trim=True)
        result_str = str(result)
        assert "LOWER(" in result_str

    def test_contains_all_options(self):
        """contains_all_options produces AND formula."""
        field = MultiSelectField("Tags")
        result = field.contains_all_options(["A", "B"])
        assert "AND(" in str(result)

    def test_contains_any_options(self):
        """contains_any_options produces OR formula."""
        field = MultiSelectField("Tags")
        result = field.contains_any_options(["A", "B"])
        assert "OR(" in str(result)

    def test_not_contains_option(self):
        """not_contains_option checks for absence."""
        field = MultiSelectField("Tags")
        result = field.not_contains_option("Option1")
        result_str = str(result)
        assert "FIND(" in result_str
        assert "=0" in result_str

    def test_not_contains_options_multiple(self):
        """not_contains_options produces AND of negations."""
        field = MultiSelectField("Tags")
        result = field.not_contains_options(["A", "B"])
        assert "AND(" in str(result)


class TestNumberField:
    """Test NumberField comparison formulas."""

    def test_between_inclusive(self):
        """between with inclusive=True uses >= and <=."""
        field = NumberField("Amount")
        result = field.between(10, 100, inclusive=True)
        result_str = str(result)
        assert "AND(" in result_str
        assert ">=" in result_str
        assert "<=" in result_str

    def test_between_exclusive(self):
        """between with inclusive=False uses > and <."""
        field = NumberField("Amount")
        result = field.between(10, 100, inclusive=False)
        result_str = str(result)
        assert "AND(" in result_str

    def test_between_boundary_same_value(self):
        """between with min == max still works."""
        field = NumberField("Amount")
        result = field.between(50, 50)
        result_str = str(result)
        assert "AND(" in result_str

    def test_between_with_floats(self):
        """between works with float values."""
        field = NumberField("Amount")
        result = field.between(10.5, 100.5)
        result_str = str(result)
        assert "10.5" in result_str
        assert "100.5" in result_str


class TestBooleanField:
    """Test BooleanField comparison formulas."""

    def test_eq_true(self):
        """eq(True) returns TRUE() formula."""
        field = BooleanField("Active")
        result = field.eq(True)
        assert "TRUE()" in str(result)

    def test_eq_false(self):
        """eq(False) returns FALSE() formula."""
        field = BooleanField("Active")
        result = field.eq(False)
        assert "FALSE()" in str(result)

    def test_true_method(self):
        """true() returns TRUE() formula."""
        field = BooleanField("Active")
        result = field.true()
        assert "TRUE()" in str(result)

    def test_false_method(self):
        """false() returns FALSE() formula."""
        field = BooleanField("Active")
        result = field.false()
        assert "FALSE()" in str(result)

    def test_dunder_call(self):
        """__call__() returns true() formula."""
        field = BooleanField("Active")
        result = field()
        assert "TRUE()" in str(result)

    def test_dunder_invert(self):
        """__invert__ (~field) returns false() formula."""
        field = BooleanField("Active")
        result = ~field
        assert "FALSE()" in str(result)


class TestAttachmentsField:
    """Test AttachmentsField comparison formulas."""

    def test_count_zero(self):
        """count(0) checks for empty attachments."""
        field = AttachmentsField("Files")
        result = field.count(0)
        result_str = str(result)
        assert "LEN(" in result_str
        assert "0" in result_str

    def test_count_positive(self):
        """count(n) checks for specific count."""
        field = AttachmentsField("Files")
        result = field.count(5)
        result_str = str(result)
        assert "LEN(" in result_str
        assert "5" in result_str


class TestParseDate:
    """Test _parse_date helper function."""

    def test_parse_datetime_object(self):
        """datetime object passes through unchanged."""
        dt = datetime(2024, 1, 15, 12, 0, 0)
        result = _parse_date(dt)
        assert result == dt

    def test_parse_iso_string(self):
        """ISO string is parsed to datetime."""
        result = _parse_date("2024-01-15")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_natural_language(self):
        """Natural language dates are parsed by dateparser."""
        result = _parse_date("yesterday")
        assert isinstance(result, datetime)

    def test_parse_invalid_string_raises(self):
        """Invalid date string raises ValueError."""
        with pytest.raises(ValueError, match="Could not parse date"):
            _parse_date("not a date xyz123")


class TestDateComparison:
    """Test DateComparison class for time-ago comparisons."""

    def test_date_method(self):
        """_date produces DATETIME_PARSE comparison."""
        dc = DateComparison("Created", "=")
        result = dc._date(datetime(2024, 1, 15))
        result_str = str(result)
        assert "DATETIME_PARSE" in result_str

    def test_ago_method(self):
        """_ago produces DATETIME_DIFF comparison."""
        dc = DateComparison("Created", ">=")
        result = dc._ago("days", 7)
        result_str = str(result)
        assert "DATETIME_DIFF" in result_str
        assert "NOW()" in result_str

    def test_compare_attribute_stored(self):
        """Comparison operator is stored correctly."""
        dc = DateComparison("Created", ">=")
        assert dc.compare == ">="

    @pytest.mark.parametrize(
        "method,unit",
        [
            ("milliseconds_ago", "milliseconds"),
            ("seconds_ago", "seconds"),
            ("minutes_ago", "minutes"),
            ("hours_ago", "hours"),
            ("days_ago", "days"),
            ("weeks_ago", "weeks"),
            ("months_ago", "months"),
            ("quarters_ago", "quarters"),
            ("years_ago", "years"),
        ],
    )
    def test_time_ago_methods(self, method, unit):
        """All time_ago methods produce correct unit."""
        dc = DateComparison("Created", ">=")
        result = getattr(dc, method)(10)
        result_str = str(result)
        assert unit in result_str


class TestDateField:
    """Test DateField datetime comparison formulas."""

    # on() tests
    def test_on_without_date_returns_comparison(self):
        """on() without date returns DateComparison object."""
        field = DateField("Created")
        result = field.on()
        assert isinstance(result, DateComparison)
        assert result.compare == "="

    def test_on_with_date_returns_formula(self):
        """on(date) returns formula string."""
        field = DateField("Created")
        result = field.on("2024-01-15")
        assert "DATETIME_PARSE" in str(result)

    def test_on_with_datetime_object(self):
        """on() accepts datetime object."""
        field = DateField("Created")
        result = field.on(datetime(2024, 1, 15))
        assert "DATETIME_PARSE" in str(result)

    def test_dunder_eq_for_date(self):
        """__eq__ delegates to on()."""
        field = DateField("Created")
        result = field == "2024-01-15"
        assert "DATETIME_PARSE" in str(result)

    # on_or_after() tests
    def test_on_or_after_without_date(self):
        """on_or_after() returns DateComparison with >=."""
        field = DateField("Created")
        result = field.on_or_after()
        assert isinstance(result, DateComparison)
        assert result.compare == ">="

    def test_on_or_after_with_date(self):
        """on_or_after(date) returns formula."""
        field = DateField("Created")
        result = field.on_or_after("2024-01-15")
        assert "DATETIME_PARSE" in str(result)

    def test_dunder_ge_for_date(self):
        """__ge__ delegates to on_or_after()."""
        field = DateField("Created")
        result = field >= "2024-01-15"
        assert "DATETIME_PARSE" in str(result)

    # on_or_before() tests
    def test_on_or_before_without_date(self):
        """on_or_before() returns DateComparison with <=."""
        field = DateField("Created")
        result = field.on_or_before()
        assert isinstance(result, DateComparison)
        assert result.compare == "<="

    def test_on_or_before_with_date(self):
        """on_or_before(date) returns formula."""
        field = DateField("Created")
        result = field.on_or_before("2024-01-15")
        assert "DATETIME_PARSE" in str(result)

    def test_dunder_le_for_date(self):
        """__le__ delegates to on_or_before()."""
        field = DateField("Created")
        result = field <= "2024-01-15"
        assert "DATETIME_PARSE" in str(result)

    # after() tests - NOTE: after uses "<" comparison (reversed semantics)
    def test_after_without_date(self):
        """after() returns DateComparison with < (reversed comparison)."""
        field = DateField("Created")
        result = field.after()
        assert isinstance(result, DateComparison)
        assert result.compare == "<"

    def test_after_with_date(self):
        """after(date) returns formula."""
        field = DateField("Created")
        result = field.after("2024-01-15")
        assert "DATETIME_PARSE" in str(result)

    def test_dunder_gt_for_date(self):
        """__gt__ delegates to after()."""
        field = DateField("Created")
        result = field > "2024-01-15"
        assert "DATETIME_PARSE" in str(result)

    # before() tests - NOTE: before uses ">" comparison (reversed semantics)
    def test_before_without_date(self):
        """before() returns DateComparison with > (reversed comparison)."""
        field = DateField("Created")
        result = field.before()
        assert isinstance(result, DateComparison)
        assert result.compare == ">"

    def test_before_with_date(self):
        """before(date) returns formula."""
        field = DateField("Created")
        result = field.before("2024-01-15")
        assert "DATETIME_PARSE" in str(result)

    def test_dunder_lt_for_date(self):
        """__lt__ delegates to before()."""
        field = DateField("Created")
        result = field < "2024-01-15"
        assert "DATETIME_PARSE" in str(result)

    # not_on() tests
    def test_not_on_without_date(self):
        """not_on() returns DateComparison with !=."""
        field = DateField("Created")
        result = field.not_on()
        assert isinstance(result, DateComparison)
        assert result.compare == "!="

    def test_not_on_with_date(self):
        """not_on(date) returns formula."""
        field = DateField("Created")
        result = field.not_on("2024-01-15")
        assert "DATETIME_PARSE" in str(result)

    def test_dunder_ne_for_date(self):
        """__ne__ delegates to not_on()."""
        field = DateField("Created")
        result = field != "2024-01-15"
        assert "DATETIME_PARSE" in str(result)

    # between() tests
    def test_between_inclusive(self):
        """between with inclusive=True uses >= and <=."""
        field = DateField("Created")
        result = field.between("2024-01-01", "2024-12-31", inclusive=True)
        result_str = str(result)
        assert "AND(" in result_str

    def test_between_exclusive(self):
        """between with inclusive=False uses > and <."""
        field = DateField("Created")
        result = field.between("2024-01-01", "2024-12-31", inclusive=False)
        result_str = str(result)
        assert "AND(" in result_str

    def test_between_with_datetime_objects(self):
        """between accepts datetime objects."""
        field = DateField("Created")
        result = field.between(datetime(2024, 1, 1), datetime(2024, 12, 31))
        result_str = str(result)
        assert "AND(" in result_str

    # Chaining test
    def test_on_chaining_with_days_ago(self):
        """on() can be chained with time-ago methods."""
        field = DateField("Created")
        comparison = field.on()
        result = comparison.days_ago(5)
        result_str = str(result)
        assert "DATETIME_DIFF" in result_str
        assert "days" in result_str


class TestLogicFunctions:
    """Test logic function re-exports."""

    def test_and_function_exists(self):
        """AND function is exported."""
        assert callable(AND)

    def test_or_function_exists(self):
        """OR function is exported."""
        assert callable(OR)

    def test_xor_function_exists(self):
        """XOR function is exported."""
        assert callable(XOR)

    def test_not_function_exists(self):
        """NOT function is exported."""
        assert callable(NOT)

    def test_and_combines_formulas(self):
        """AND combines multiple formulas."""
        field1 = TextField("Name")
        field2 = NumberField("Amount")
        result = AND(field1.contains("test"), field2 > 100)
        assert "AND(" in str(result)

    def test_or_combines_formulas(self):
        """OR combines multiple formulas."""
        field1 = TextField("Name")
        field2 = NumberField("Amount")
        result = OR(field1.contains("test"), field2 > 100)
        assert "OR(" in str(result)


class TestComplexFormulas:
    """Integration tests for complex formula compositions."""

    def test_and_with_three_field_types(self):
        """AND combining text, number, and date fields."""
        name = TextField("Name")
        amount = NumberField("Amount")
        created = DateField("Created")

        result = AND(
            name.contains("test"),
            amount > 100,
            created.on_or_after("2024-01-01"),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "FIND(" in formula  # text contains
        assert "{Amount}" in formula
        assert "DATETIME_PARSE" in formula

    def test_or_with_multiple_select_and_boolean(self):
        """OR combining select fields and boolean."""
        status = SingleSelectField("Status")
        urgent = BooleanField("Urgent")

        result = OR(
            status.eq("Active"),
            status.eq("Pending"),
            urgent.true(),
        )

        formula = str(result)
        assert "OR(" in formula
        assert "{Status}" in formula
        assert "{Urgent}" in formula
        assert "TRUE()" in formula

    def test_nested_or_within_and(self):
        """Nested OR inside AND logic."""
        name = TextField("Name")
        amount = NumberField("Amount")

        result = AND(
            OR(
                name.contains("John"),
                name.contains("Jane"),
            ),
            amount.between(100, 1000),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "OR(" in formula
        assert "John" in formula
        assert "Jane" in formula
        assert "{Amount}>=100" in formula
        assert "{Amount}<=1000" in formula

    def test_nested_and_within_or(self):
        """Nested AND inside OR logic."""
        type_field = TextField("Type")
        value = NumberField("Value")

        result = OR(
            AND(
                type_field.equals("A"),
                value > 50,
            ),
            AND(
                type_field.equals("B"),
                value < 25,
            ),
        )

        formula = str(result)
        assert "OR(" in formula
        assert formula.count("AND(") == 2
        assert "'A'" in formula
        assert "'B'" in formula
        assert "{Value}>50" in formula
        assert "{Value}<25" in formula

    def test_not_with_compound_condition(self):
        """NOT combined with AND for exclusion logic."""
        status = TextField("Status")
        tags = TextField("Tags")

        result = AND(
            status.equals("Active"),
            NOT(tags.contains("archived")),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "NOT(" in formula
        assert "'Active'" in formula
        assert "archived" in formula

    def test_date_range_with_other_filters(self):
        """Date range combined with text and number filters."""
        created = DateField("Created")
        status = TextField("Status")
        score = NumberField("Score")

        result = AND(
            created.between("2024-01-01", "2024-12-31"),
            status.equals("Complete"),
            score >= 80,
        )

        formula = str(result)
        assert "AND(" in formula
        assert "DATETIME_PARSE" in formula
        assert "'Complete'" in formula
        assert "{Score}>=80" in formula

    def test_time_relative_with_status(self):
        """Time-relative date comparison with status filter."""
        modified = DateField("Modified")
        status = SingleSelectField("Status")

        result = AND(
            modified.on_or_after().days_ago(7),
            status.eq("Active"),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "DATETIME_DIFF" in formula
        assert "days" in formula
        assert ">=7" in formula
        assert "'Active'" in formula

    def test_multiselect_complex_conditions(self):
        """MultiSelect with contains_all and NOT contains."""
        tags = MultiSelectField("Tags")

        result = AND(
            tags.contains_all_options(["urgent", "reviewed"]),
            NOT(tags.contains_option("archived")),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "NOT(" in formula
        assert "urgent" in formula
        assert "reviewed" in formula
        assert "archived" in formula

    def test_deeply_nested_three_levels(self):
        """Three levels of nesting: OR(AND(...), AND(...))."""
        category = TextField("Category")
        priority = NumberField("Priority")
        active = BooleanField("Active")

        result = OR(
            AND(
                category.equals("Sales"),
                priority > 5,
            ),
            AND(
                category.equals("Support"),
                active.true(),
            ),
        )

        formula = str(result)
        assert "OR(" in formula
        assert formula.count("AND(") == 2
        assert "'Sales'" in formula
        assert "'Support'" in formula
        assert "{Priority}>5" in formula
        assert "TRUE()" in formula

    def test_xor_with_field_comparisons(self):
        """XOR combining field comparisons."""
        status_a = BooleanField("StatusA")
        status_b = BooleanField("StatusB")

        result = XOR(
            status_a.true(),
            status_b.true(),
        )

        formula = str(result)
        assert "XOR(" in formula
        assert "{StatusA}=TRUE()" in formula
        assert "{StatusB}=TRUE()" in formula

    def test_multiple_not_conditions(self):
        """Multiple NOT conditions in AND."""
        tags = TextField("Tags")
        status = TextField("Status")

        result = AND(
            NOT(tags.contains("deleted")),
            NOT(status.equals("Archived")),
        )

        formula = str(result)
        assert "AND(" in formula
        assert formula.count("NOT(") == 2
        assert "deleted" in formula
        assert "'Archived'" in formula

    def test_complex_date_with_number_range(self):
        """Complex date comparison with number range."""
        created = DateField("Created")
        amount = NumberField("Amount")
        count = NumberField("Count")

        result = AND(
            created.after().weeks_ago(4),
            amount.between(1000, 5000),
            count > 0,
        )

        formula = str(result)
        assert "AND(" in formula
        assert "DATETIME_DIFF" in formula
        assert "weeks" in formula
        assert "{Amount}>=1000" in formula
        assert "{Amount}<=5000" in formula
        assert "{Count}>0" in formula

    def test_phone_normalization_with_other_conditions(self):
        """Phone normalization combined with status and date filters."""
        phone = TextField("Phone")
        status = SingleSelectField("Status")
        created = DateField("Created")

        result = AND(
            phone.phone_equals("555-123-4567"),
            status.eq("Active"),
            created.on_or_after("2024-01-01"),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "SUBSTITUTE" in formula
        assert "{Status}" in formula
        assert "DATETIME_PARSE" in formula

    def test_string_ops_with_case_trim_combinations(self):
        """String operations with different case/trim flag combinations."""
        name = TextField("Name")
        code = TextField("Code")

        result = AND(
            name.starts_with("Dr.", case_sensitive=True, trim=False),
            code.ends_with("-v2", case_sensitive=False, trim=True),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "FIND(" in formula
        assert "Dr." in formula
        assert "-v2" in formula

    def test_id_in_list_with_field_conditions(self):
        """Combine record ID list with status filter."""
        status = SingleSelectField("Status")

        result = AND(
            ID.in_list(["rec12345678901234", "rec98765432109876"]),
            status.eq("Active"),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "RECORD_ID()" in formula
        assert "OR(" in formula
        assert "'Active'" in formula

    def test_id_single_in_list_with_conditions(self):
        """Single ID in list with other conditions."""
        amount = NumberField("Amount")

        result = AND(
            ID.in_list(["rec12345678901234"]),
            amount > 100,
        )

        formula = str(result)
        assert "AND(" in formula
        assert "rec12345678901234" in formula
        assert "{Amount}>100" in formula

    def test_attachment_field_in_complex_formulas(self):
        """Attachment count combined with status and boolean."""
        files = AttachmentsField("Files")
        verified = BooleanField("Verified")
        status = TextField("Status")

        result = AND(
            files.count(3),
            verified.true(),
            status.equals("Complete"),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "LEN({Files})=3" in formula
        assert "TRUE()" in formula
        assert "Complete" in formula

    def test_attachment_not_empty_with_date(self):
        """NotEmpty attachments with date filter."""
        docs = AttachmentsField("Documents")
        submitted = DateField("Submitted")

        result = AND(
            docs.not_empty(),
            submitted.on_or_before("2024-06-30"),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "{Documents}" in formula
        assert "DATETIME_PARSE" in formula

    def test_empty_with_or_alternatives(self):
        """Empty check combined with OR alternatives."""
        notes = TextField("Notes")
        status = SingleSelectField("Status")

        result = OR(
            notes.empty(),
            status.eq("Draft"),
        )

        formula = str(result)
        assert "OR(" in formula
        assert "BLANK()" in formula
        assert "'Draft'" in formula

    def test_not_empty_with_not_contains(self):
        """NotEmpty combined with NOT contains."""
        description = TextField("Description")
        tags = TextField("Tags")

        result = AND(
            description.not_empty(),
            NOT(tags.contains("archived")),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "{Description}" in formula
        assert "NOT(" in formula

    def test_regex_with_other_conditions(self):
        """Regex match combined with number and boolean."""
        email = TextField("Email")
        score = NumberField("Score")
        active = BooleanField("Active")

        result = AND(
            email.regex_match(r"^[a-z]+@company\.com$"),
            score >= 90,
            active.true(),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "REGEX_MATCH(" in formula
        assert "{Score}>=90" in formula
        assert "TRUE()" in formula

    def test_four_level_deep_nesting(self):
        """Deeply nested logic with four levels."""
        type_field = TextField("Type")
        priority = NumberField("Priority")
        active = BooleanField("Active")
        status = SingleSelectField("Status")

        result = OR(
            AND(
                OR(
                    type_field.equals("A"),
                    type_field.equals("B"),
                ),
                priority > 5,
            ),
            AND(
                active.true(),
                status.eq("Urgent"),
            ),
        )

        formula = str(result)
        assert "OR(" in formula
        assert formula.count("AND(") == 2
        assert formula.count("OR(") == 2
        assert "'A'" in formula
        assert "'B'" in formula
        assert "{Priority}>5" in formula

    def test_multiple_time_units_in_date_comparisons(self):
        """Combine different time-ago units."""
        created = DateField("Created")
        modified = DateField("Modified")

        result = AND(
            created.after().days_ago(30),
            modified.on_or_after().hours_ago(24),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "days" in formula
        assert "hours" in formula
        assert formula.count("DATETIME_DIFF") == 2

    def test_quote_escaping_in_complex_scenarios(self):
        """Handle quotes in text values with other conditions."""
        title = TextField("Title")
        count = NumberField("Count")

        result = AND(
            title.equals('Say "Hello"'),
            count > 0,
        )

        formula = str(result)
        assert "AND(" in formula
        assert '"Hello"' in formula
        assert "{Count}>0" in formula

    def test_exclusive_number_range_with_date(self):
        """Exclusive number range with date filter."""
        amount = NumberField("Amount")
        date = DateField("Date")

        result = AND(
            amount.between(100, 500, inclusive=False),
            date.on_or_after("2024-01-01"),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "{Amount}>100" in formula
        assert "{Amount}<500" in formula
        assert "{Amount}>=100" not in formula
        assert "{Amount}<=500" not in formula

    def test_exclusive_date_range_with_status(self):
        """Exclusive date range with status filter."""
        created = DateField("Created")
        status = SingleSelectField("Status")

        result = AND(
            created.between("2024-01-01", "2024-12-31", inclusive=False),
            status.eq("Active"),
        )

        formula = str(result)
        assert "AND(" in formula
        assert "DATETIME_PARSE" in formula
        assert "'Active'" in formula
