"""Tests for the Python AirtableRuntime functions."""

import math

from static.python.airtable_runtime import AirtableRuntime as _r  # noqa: N813


class TestBlankSemantics:
    """BLANK() handling is central to Airtable formula behavior."""

    def test_blank_returns_none(self):
        assert _r.BLANK() is None

    def test_blank_plus_number(self):
        """BLANK() + 5 = 5 (BLANK treated as 0 in numeric context)."""
        assert _r.ADD(None, 5) == 5

    def test_blank_concat_string(self):
        """BLANK() & "hello" = "hello" (BLANK treated as "" in string context)."""
        assert _r.CONCAT(None, "hello") == "hello"

    def test_blank_is_falsy(self):
        """IF(BLANK(), "yes", "no") = "no"."""
        assert _r.IF(None, "yes", "no") == "no"

    def test_blank_equals_blank(self):
        """BLANK() = BLANK() = true."""
        assert _r.EQ(None, None) is True

    def test_blank_not_equal_to_value(self):
        assert _r.EQ(None, 5) is False
        assert _r.EQ(5, None) is False


class TestArithmeticOperators:
    def test_add(self):
        assert _r.ADD(3, 4) == 7

    def test_sub(self):
        assert _r.SUB(10, 3) == 7

    def test_mul(self):
        assert _r.MUL(3, 4) == 12

    def test_div(self):
        assert _r.DIV(10, 2) == 5.0

    def test_div_by_zero(self):
        assert math.isnan(_r.DIV(5, 0))

    def test_neg(self):
        assert _r.NEG(5) == -5

    def test_string_coercion_in_add(self):
        """'5' + 3 should coerce to 8."""
        assert _r.ADD("5", 3) == 8


class TestComparisonOperators:
    def test_eq(self):
        assert _r.EQ(5, 5) is True
        assert _r.EQ(5, 6) is False

    def test_neq(self):
        assert _r.NEQ(5, 6) is True

    def test_lt(self):
        assert _r.LT(3, 5) is True
        assert _r.LT(5, 3) is False

    def test_gt(self):
        assert _r.GT(5, 3) is True

    def test_lte(self):
        assert _r.LTE(3, 3) is True
        assert _r.LTE(3, 4) is True

    def test_gte(self):
        assert _r.GTE(5, 5) is True


class TestLogicalFunctions:
    def test_if_true(self):
        assert _r.IF(True, "yes", "no") == "yes"

    def test_if_false(self):
        assert _r.IF(False, "yes", "no") == "no"

    def test_and(self):
        assert _r.AND(True, True) is True
        assert _r.AND(True, False) is False

    def test_or(self):
        assert _r.OR(False, True) is True
        assert _r.OR(False, False) is False

    def test_not(self):
        assert _r.NOT(True) is False
        assert _r.NOT(False) is True

    def test_xor(self):
        assert _r.XOR(True, False) is True
        assert _r.XOR(True, True) is False

    def test_switch(self):
        assert _r.SWITCH("a", "a", 1, "b", 2, 99) == 1
        assert _r.SWITCH("b", "a", 1, "b", 2, 99) == 2
        assert _r.SWITCH("c", "a", 1, "b", 2, 99) == 99

    def test_ifs(self):
        assert _r.IFS(False, 1, True, 2, True, 3) == 2


class TestNumericFunctions:
    def test_sum(self):
        assert _r.SUM(1, 2, 3) == 6

    def test_sum_with_array(self):
        assert _r.SUM([1, 2, 3]) == 6

    def test_average(self):
        assert _r.AVERAGE(2, 4, 6) == 4.0

    def test_min_max(self):
        assert _r.MIN(3, 1, 2) == 1
        assert _r.MAX(3, 1, 2) == 3

    def test_count(self):
        assert _r.COUNT(1, "a", 3, None) == 2

    def test_counta(self):
        assert _r.COUNTA(1, "a", None, "") == 2

    def test_countall(self):
        assert _r.COUNTALL(1, None, "", 0) == 4

    def test_round(self):
        assert _r.ROUND(3.456, 2) == 3.46

    def test_roundup(self):
        assert _r.ROUNDUP(3.451, 2) == 3.46

    def test_rounddown(self):
        assert _r.ROUNDDOWN(3.459, 2) == 3.45

    def test_int(self):
        assert _r.INT(3.9) == 3

    def test_abs(self):
        assert _r.ABS(-5) == 5

    def test_sqrt(self):
        assert _r.SQRT(16) == 4.0

    def test_power(self):
        assert _r.POWER(2, 3) == 8.0

    def test_mod(self):
        assert _r.MOD(7, 3) == 1

    def test_even(self):
        assert _r.EVEN(3) == 4
        assert _r.EVEN(4) == 4

    def test_odd(self):
        assert _r.ODD(4) == 5
        assert _r.ODD(3) == 3

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
        assert _r.LEN("hello") == 5

    def test_find(self):
        assert _r.FIND("ll", "hello") == 3

    def test_search_case_insensitive(self):
        assert _r.SEARCH("LL", "hello") == 3

    def test_substitute(self):
        assert _r.SUBSTITUTE("aaa", "a", "b") == "bbb"

    def test_replace(self):
        assert _r.REPLACE("hello", 2, 3, "XY") == "hXYo"

    def test_lower_upper(self):
        assert _r.LOWER("Hello") == "hello"
        assert _r.UPPER("Hello") == "HELLO"

    def test_trim(self):
        assert _r.TRIM("  hello  ") == "hello"

    def test_rept(self):
        assert _r.REPT("ab", 3) == "ababab"

    def test_t(self):
        assert _r.T("hello") == "hello"
        assert _r.T(42) == ""

    def test_regex_match(self):
        assert _r.REGEX_MATCH("hello123", r"\d+") is True
        assert _r.REGEX_MATCH("hello", r"\d+") is False

    def test_regex_extract(self):
        assert _r.REGEX_EXTRACT("hello123", r"\d+") == "123"

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
        assert _r.CONCAT("hello", " world") == "hello world"

    def test_number_to_string_concat(self):
        assert _r.CONCAT(5, " items") == "5 items"

    def test_blank_concat(self):
        assert _r.CONCAT(None, "hello") == "hello"
