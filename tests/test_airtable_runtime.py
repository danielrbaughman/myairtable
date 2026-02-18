"""Tests for the Python AirtableRuntime functions."""

import math

from static.python.airtable_runtime import AirtableRuntime as _r  # noqa: N813


class TestBlankSemantics:
    """BLANK() handling is central to Airtable formula behavior."""

    def test_blank_plus_number(self):
        """BLANK() + 5 = 5 (BLANK treated as 0 in numeric context)."""
        assert _r.N(None) + 5 == 5

    def test_blank_concat_string(self):
        """BLANK() & "hello" = "hello" (BLANK treated as "" in string context)."""
        assert _r.S(None) + "hello" == "hello"

    def test_blank_is_falsy(self):
        """BLANK is falsy in native truthiness checks."""
        assert not None

    def test_blank_equals_blank(self):
        """BLANK() = BLANK() = true."""
        assert (None == None) is True  # noqa: E711

    def test_blank_not_equal_to_value(self):
        assert (None == 5) is False
        assert (5 == None) is False  # noqa: E711


class TestArithmeticOperators:
    def test_n_coercion(self):
        """N() coerces values to numbers like the old ADD/SUB/MUL/NEG did."""
        assert _r.N(3) + _r.N(4) == 7
        assert _r.N(10) - _r.N(3) == 7
        assert _r.N(3) * _r.N(4) == 12
        assert -_r.N(5) == -5

    def test_n_string_coercion(self):
        """'5' + 3 should coerce to 8 via N()."""
        assert _r.N("5") + 3 == 8

    def test_n_blank_coercion(self):
        """BLANK coerces to 0 via N()."""
        assert _r.N(None) == 0

    def test_div(self):
        assert _r.N(10) / _r.N(2) == 5.0


class TestComparisonOperators:
    def test_eq(self):
        assert (5 == 5) is True
        assert (5 == 6) is False

    def test_neq(self):
        assert (5 != 6) is True

    def test_lt(self):
        assert (_r.N(3) < _r.N(5)) is True
        assert (_r.N(5) < _r.N(3)) is False

    def test_gt(self):
        assert (_r.N(5) > _r.N(3)) is True

    def test_lte(self):
        assert (_r.N(3) <= _r.N(3)) is True
        assert (_r.N(3) <= _r.N(4)) is True

    def test_gte(self):
        assert (_r.N(5) >= _r.N(5)) is True


class TestNumericFunctions:
    def test_average(self):
        assert _r.AVERAGE(2, 4, 6) == 4.0

    def test_count(self):
        assert _r.COUNT(1, "a", 3, None) == 2

    def test_counta(self):
        assert _r.COUNTA(1, "a", None, "") == 2

    def test_roundup(self):
        assert _r.ROUNDUP(3.451, 2) == 3.46

    def test_rounddown(self):
        assert _r.ROUNDDOWN(3.459, 2) == 3.45

    def test_even(self):
        assert _r.EVEN(3) == 4
        assert _r.EVEN(4) == 4

    def test_odd(self):
        assert _r.ODD(4) == 5
        assert _r.ODD(3) == 3

    def test_s_strips_decimal_zero_from_whole_floats(self):
        """Airtable strips .0 from whole-number floats in string context."""
        assert _r.S(15.0) == "15"
        assert _r.S(100.0) == "100"
        assert _r.S(0.0) == "0"
        assert _r.S(2.5) == "2.5"
        assert _r.S(2.718281828459045) == "2.718281828459045"
        assert _r.S(float("nan")) == "nan"
        assert _r.S(float("inf")) == "inf"

    def test_value(self):
        assert _r.VALUE("42") == 42
        assert math.isnan(_r.VALUE("abc"))


class TestStringFunctions:
    def test_concatenate(self):
        assert _r.CONCATENATE("a", "b", "c") == "abc"

    def test_left(self):
        assert _r.LEFT("hello", 3) == "hel"

    def test_right(self):
        assert _r.RIGHT("hello", 3) == "llo"

    def test_mid(self):
        assert _r.MID("hello", 2, 3) == "ell"

    def test_len(self):
        assert len(_r.S("hello")) == 5

    def test_find(self):
        assert _r.FIND("ll", "hello") == 3

    def test_search_case_insensitive(self):
        assert _r.SEARCH("LL", "hello") == 3

    def test_substitute(self):
        assert _r.SUBSTITUTE("aaa", "a", "b") == "bbb"

    def test_replace(self):
        assert _r.REPLACE("hello", 2, 3, "XY") == "hXYo"

    def test_lower_upper(self):
        assert _r.S("Hello").lower() == "hello"
        assert _r.S("Hello").upper() == "HELLO"

    def test_trim(self):
        assert _r.S("  hello  ").strip() == "hello"

    def test_rept(self):
        assert _r.REPT("ab", 3) == "ababab"

    def test_t(self):
        assert _r.T("hello") == "hello"
        assert _r.T(42) == ""

    def test_regex_match(self):
        assert _r.REGEX_MATCH("hello123", r"\d+") is True
        assert _r.REGEX_MATCH("hello", r"\d+") is False

    def test_regex_replace(self):
        assert _r.REGEX_REPLACE("hello123", r"\d+", "X") == "helloX"


class TestArrayFunctions:
    def test_arrayjoin(self):
        assert _r.ARRAYJOIN(["a", "b", "c"]) == "a, b, c"
        assert _r.ARRAYJOIN(["a", "b"], "-") == "a-b"

    def test_arrayunique(self):
        assert _r.ARRAYUNIQUE([1, 2, 2, 3]) == [1, 2, 3]

    def test_arraycompact(self):
        assert _r.ARRAYCOMPACT([1, None, "", 2]) == [1, 2]

    def test_arrayflatten(self):
        assert _r.ARRAYFLATTEN([1, [2, [3, 4]]]) == [1, 2, 3, 4]


class TestConcatOperator:
    def test_string_concat(self):
        assert _r.S("hello") + _r.S(" world") == "hello world"

    def test_number_to_string_concat(self):
        assert _r.S(5) + _r.S(" items") == "5 items"

    def test_blank_concat(self):
        assert _r.S(None) + _r.S("hello") == "hello"
