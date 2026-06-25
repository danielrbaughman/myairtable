using System.Text.Json.Nodes;
using MyAirtable;
using Xunit;

namespace MyAirtable.Tests;

/// <summary>
/// CS8.11 — Formula-function semantics of <see cref="AirtableRuntime"/>. Port of the Java/Kotlin/
/// Swift/Rust TestAirtableRuntime suites (~184 cases). Coercion-helper basics (N/S/A/V/IsTruthy)
/// live in TestValueCoercion and are not repeated here.
///
/// <para>Whole-number results are integral (long) nodes; node equality is checked structurally via
/// <see cref="JsonNode.DeepEquals"/> (which compares numbers semantically).</para>
/// </summary>
public class TestAirtableRuntime
{
    private static JsonNode? I(long v) => JsonValue.Create(v);

    private static JsonNode? F(double v) => JsonValue.Create(v);

    private static JsonNode? Str(string v) => JsonValue.Create(v);

    private static JsonNode? B(bool v) => JsonValue.Create(v);

    private static JsonNode? Nul() => null;

    private static JsonNode? Arr(params JsonNode?[] items) => new JsonArray(items);

    private static void Eq(JsonNode? expected, JsonNode? actual)
    {
        if (expected is null)
        {
            Assert.Null(actual);
            return;
        }
        Assert.True(
            actual is not null && JsonNode.DeepEquals(expected, actual),
            $"expected {expected.ToJsonString()}, got {actual?.ToJsonString() ?? "null"}"
        );
    }

    private static void Nan(JsonNode? value) =>
        Assert.True(double.IsNaN(AirtableRuntime.N(value)), "expected NaN");

    // ---- Logic ----

    [Fact]
    public void IfTrue() => Eq(I(1), AirtableRuntime.IF(B(true), I(1), I(2)));

    [Fact]
    public void IfFalse() => Eq(I(2), AirtableRuntime.IF(B(false), I(1), I(2)));

    [Fact]
    public void IfNullIsFalse() => Eq(I(2), AirtableRuntime.IF(null, I(1), I(2)));

    [Fact]
    public void IfZeroIsFalsy() => Eq(Str("no"), AirtableRuntime.IF(I(0), Str("yes"), Str("no")));

    [Fact]
    public void IfNumberIsTruthy() =>
        Eq(Str("yes"), AirtableRuntime.IF(I(1), Str("yes"), Str("no")));

    [Fact]
    public void IfEmptyStringIsFalsy() =>
        Eq(Str("no"), AirtableRuntime.IF(Str(""), Str("yes"), Str("no")));

    [Fact]
    public void SwitchMatch() =>
        Eq(Str("two"), AirtableRuntime.SWITCH(I(2), null, I(1), Str("one"), I(2), Str("two")));

    [Fact]
    public void SwitchDefault() =>
        Eq(Str("other"), AirtableRuntime.SWITCH(I(99), Str("other"), I(1), Str("one")));

    [Fact]
    public void SwitchNoMatchNoDefault() =>
        Eq(Nul(), AirtableRuntime.SWITCH(I(99), null, I(1), Str("one")));

    [Fact]
    public void BlankIsNull() => Eq(Nul(), AirtableRuntime.BLANK());

    [Fact]
    public void TrueIsBool() => Eq(B(true), AirtableRuntime.TRUE());

    [Fact]
    public void FalseIsBool() => Eq(B(false), AirtableRuntime.FALSE());

    [Fact]
    public void IserrorNaN() => Eq(B(true), AirtableRuntime.ISERROR(F(double.NaN)));

    [Fact]
    public void IserrorNormal() => Eq(B(false), AirtableRuntime.ISERROR(I(5)));

    [Fact]
    public void IserrorNullIsFalse()
    {
        Eq(B(false), AirtableRuntime.ISERROR(Nul()));
        Eq(B(false), AirtableRuntime.ISERROR(null));
    }

    [Fact]
    public void ErrorIsNaN()
    {
        Nan(AirtableRuntime.ERROR());
        Eq(B(true), AirtableRuntime.ISERROR(AirtableRuntime.ERROR(Str("boom"))));
    }

    // ---- Math ----

    [Fact]
    public void SumBasic() => Eq(I(6), AirtableRuntime.SUM(I(1), I(2), I(3)));

    [Fact]
    public void SumWithArray() => Eq(I(6), AirtableRuntime.SUM(Arr(I(1), I(2)), I(3)));

    [Fact]
    public void SumWithStrings() => Eq(I(6), AirtableRuntime.SUM(I(1), Str("5")));

    [Fact]
    public void AverageBasic() => Eq(I(3), AirtableRuntime.AVERAGE(I(2), I(4)));

    [Fact]
    public void AverageThree() => Eq(I(20), AirtableRuntime.AVERAGE(I(10), I(20), I(30)));

    [Fact]
    public void AverageEmptyIsNaN() => Nan(AirtableRuntime.AVERAGE());

    [Fact]
    public void MinBasic() => Eq(I(1), AirtableRuntime.MIN(I(3), I(1), I(2)));

    [Fact]
    public void MaxBasic() => Eq(I(3), AirtableRuntime.MAX(I(3), I(1), I(2)));

    [Fact]
    public void MinEmptyIsNaN() => Nan(AirtableRuntime.MIN());

    [Fact]
    public void MaxEmptyIsNaN() => Nan(AirtableRuntime.MAX());

    [Fact]
    public void CountSkipsStrings() => Eq(I(2), AirtableRuntime.COUNT(I(1), Str("x"), I(2)));

    [Fact]
    public void CountSkipsNulls() => Eq(I(2), AirtableRuntime.COUNT(I(1), Str("a"), I(3), Nul()));

    [Fact]
    public void CountBoolsNotCounted() => Eq(I(0), AirtableRuntime.COUNT(B(true), B(false)));

    [Fact]
    public void CountaSkipsNulls() => Eq(I(1), AirtableRuntime.COUNTA(I(1), Nul(), Str("")));

    [Fact]
    public void CountaExcludesNullAndEmpty() =>
        Eq(I(2), AirtableRuntime.COUNTA(I(1), Str(""), Nul(), Str("hi")));

    [Fact]
    public void CountaCountsBools() => Eq(I(2), AirtableRuntime.COUNTA(B(true), B(false)));

    [Fact]
    public void RoundToInt() => Eq(I(4), AirtableRuntime.ROUND(F(3.7)));

    [Fact]
    public void RoundToPrecision() => Eq(F(3.14), AirtableRuntime.ROUND(F(3.14159), I(2)));

    [Fact]
    public void RoundBasic() => Eq(F(3.46), AirtableRuntime.ROUND(F(3.456), I(2)));

    [Fact]
    public void RoundHalfAway() => Eq(I(4), AirtableRuntime.ROUND(F(3.5), I(0)));

    [Fact]
    public void RoundupInt() => Eq(I(4), AirtableRuntime.ROUNDUP(F(3.1)));

    [Fact]
    public void RoundupPrecision() => Eq(F(3.2), AirtableRuntime.ROUNDUP(F(3.14), I(1)));

    [Fact]
    public void RounddownInt() => Eq(I(3), AirtableRuntime.ROUNDDOWN(F(3.9)));

    [Fact]
    public void RounddownPrecision() => Eq(F(3.1), AirtableRuntime.ROUNDDOWN(F(3.19), I(1)));

    [Fact]
    public void CeilingBasic() => Eq(I(4), AirtableRuntime.CEILING(F(3.2)));

    [Fact]
    public void CeilingSignificance() => Eq(I(6), AirtableRuntime.CEILING(F(4.3), I(2)));

    [Fact]
    public void CeilingZeroSignificanceDefaultsToOne() =>
        Eq(I(5), AirtableRuntime.CEILING(F(4.3), I(0)));

    [Fact]
    public void FloorBasic() => Eq(I(3), AirtableRuntime.FLOOR(F(3.8)));

    [Fact]
    public void FloorSignificance() => Eq(I(4), AirtableRuntime.FLOOR(F(4.9), I(2)));

    [Fact]
    public void LogBase10() => Eq(I(2), AirtableRuntime.LOG(I(100)));

    [Fact]
    public void LogBase2() =>
        Assert.Equal(3.0, AirtableRuntime.N(AirtableRuntime.LOG(I(8), I(2))), 9);

    [Fact]
    public void EvenRoundsUp() => Eq(I(4), AirtableRuntime.EVEN(F(3.0)));

    [Fact]
    public void EvenAlreadyEven() => Eq(I(4), AirtableRuntime.EVEN(I(4)));

    [Fact]
    public void EvenNegative() => Eq(I(-4), AirtableRuntime.EVEN(I(-3)));

    [Fact]
    public void OddRoundsUp() => Eq(I(3), AirtableRuntime.ODD(F(2.0)));

    [Fact]
    public void OddAlreadyOdd() => Eq(I(3), AirtableRuntime.ODD(I(3)));

    [Fact]
    public void OddNegative() => Eq(I(-5), AirtableRuntime.ODD(I(-4)));

    [Fact]
    public void ValueString() => Eq(I(42), AirtableRuntime.VALUE(Str("42")));

    [Fact]
    public void ValueStringFloat() => Eq(F(3.14), AirtableRuntime.VALUE(Str("3.14")));

    [Fact]
    public void ValueInvalid() => Nan(AirtableRuntime.VALUE(Str("abc")));

    [Fact]
    public void ValueNullIsZero() => Eq(I(0), AirtableRuntime.VALUE(null));

    [Fact]
    public void PowerBasic() => Eq(I(8), AirtableRuntime.POWER(I(2), I(3)));

    [Fact]
    public void ModBasic() => Eq(I(1), AirtableRuntime.MOD(I(10), I(3)));

    [Fact]
    public void ModNegativeDividendKeepsSign() => Eq(I(-1), AirtableRuntime.MOD(I(-10), I(3)));

    [Fact]
    public void ModDivZeroIsNaN() => Nan(AirtableRuntime.MOD(I(5), I(0)));

    [Fact]
    public void AbsNegative() => Eq(I(5), AirtableRuntime.ABS(I(-5)));

    [Fact]
    public void AbsPositive() => Eq(I(5), AirtableRuntime.ABS(I(5)));

    [Fact]
    public void SqrtBasic() => Eq(I(3), AirtableRuntime.SQRT(I(9)));

    [Fact]
    public void ExpBasic() => Assert.Equal(Math.E, AirtableRuntime.N(AirtableRuntime.EXP(I(1))), 9);

    [Fact]
    public void IntTruncates() => Eq(I(3), AirtableRuntime.INT(F(3.7)));

    [Fact]
    public void IntNegativeFloors() => Eq(I(-4), AirtableRuntime.INT(F(-3.2)));

    // ---- String ----

    [Fact]
    public void LenString() => Eq(I(5), AirtableRuntime.LEN(Str("hello")));

    [Fact]
    public void LenEmpty() => Eq(I(0), AirtableRuntime.LEN(Str("")));

    [Fact]
    public void LenUnicode() => Eq(I(4), AirtableRuntime.LEN(Str("café")));

    [Fact]
    public void LeftBasic() => Eq(Str("hel"), AirtableRuntime.LEFT(Str("hello"), I(3)));

    [Fact]
    public void LeftZero() => Eq(Str(""), AirtableRuntime.LEFT(Str("hello"), I(0)));

    [Fact]
    public void LeftExceeds() => Eq(Str("hi"), AirtableRuntime.LEFT(Str("hi"), I(5)));

    [Fact]
    public void RightBasic() => Eq(Str("llo"), AirtableRuntime.RIGHT(Str("hello"), I(3)));

    [Fact]
    public void RightExceeds() => Eq(Str("hi"), AirtableRuntime.RIGHT(Str("hi"), I(5)));

    [Fact]
    public void MidBasic() => Eq(Str("ell"), AirtableRuntime.MID(Str("hello"), I(2), I(3)));

    [Fact]
    public void MidStartOne() => Eq(Str("he"), AirtableRuntime.MID(Str("hello"), I(1), I(2)));

    [Fact]
    public void MidStartPastEndIsEmpty() =>
        Eq(Str(""), AirtableRuntime.MID(Str("hello"), I(10), I(3)));

    [Fact]
    public void FindFound() => Eq(I(3), AirtableRuntime.FIND(Str("l"), Str("hello")));

    [Fact]
    public void FindMultiChar() => Eq(I(3), AirtableRuntime.FIND(Str("ll"), Str("hello")));

    [Fact]
    public void FindNotFound() => Eq(I(0), AirtableRuntime.FIND(Str("z"), Str("hello")));

    [Fact]
    public void FindCaseSensitive() => Eq(I(0), AirtableRuntime.FIND(Str("LL"), Str("hello")));

    [Fact]
    public void FindWithStart() => Eq(I(4), AirtableRuntime.FIND(Str("l"), Str("hello"), I(4)));

    [Fact]
    public void FindStartPastEndIsZero() =>
        Eq(I(0), AirtableRuntime.FIND(Str("l"), Str("hello"), I(10)));

    [Fact]
    public void FindUnicode()
    {
        Eq(I(3), AirtableRuntime.FIND(Str("f"), Str("café")));
        Eq(I(4), AirtableRuntime.FIND(Str("é"), Str("café"), I(4)));
    }

    [Fact]
    public void SearchCaseInsensitive() => Eq(I(3), AirtableRuntime.SEARCH(Str("L"), Str("hello")));

    [Fact]
    public void SearchMultiChar() => Eq(I(3), AirtableRuntime.SEARCH(Str("LL"), Str("hello")));

    [Fact]
    public void SearchWithStart() => Eq(I(4), AirtableRuntime.SEARCH(Str("l"), Str("hello"), I(4)));

    [Fact]
    public void SubstituteAll() =>
        Eq(Str("a_b_c"), AirtableRuntime.SUBSTITUTE(Str("a-b-c"), Str("-"), Str("_")));

    [Fact]
    public void SubstituteAllOverlapping() =>
        Eq(Str("bbb"), AirtableRuntime.SUBSTITUTE(Str("aaa"), Str("a"), Str("b")));

    [Fact]
    public void SubstituteNth() =>
        Eq(Str("a-b_c"), AirtableRuntime.SUBSTITUTE(Str("a-b-c"), Str("-"), Str("_"), I(2)));

    [Fact]
    public void SubstituteNthRepeated() =>
        Eq(Str("aba"), AirtableRuntime.SUBSTITUTE(Str("aaa"), Str("a"), Str("b"), I(2)));

    [Fact]
    public void SubstituteEmptyOldIsNoop() =>
        Eq(Str("hello"), AirtableRuntime.SUBSTITUTE(Str("hello"), Str(""), Str("x")));

    [Fact]
    public void ReplaceBasic() =>
        Eq(Str("hXXo"), AirtableRuntime.REPLACE(Str("hello"), I(2), I(3), Str("XX")));

    [Fact]
    public void ReplacePastEndAppends() =>
        Eq(Str("hiX"), AirtableRuntime.REPLACE(Str("hi"), I(10), I(2), Str("X")));

    [Fact]
    public void LowerBasic() => Eq(Str("hi"), AirtableRuntime.LOWER(Str("HI")));

    [Fact]
    public void UpperBasic() => Eq(Str("HI"), AirtableRuntime.UPPER(Str("hi")));

    [Fact]
    public void TrimBasic() => Eq(Str("x"), AirtableRuntime.TRIM(Str("  x  ")));

    [Fact]
    public void TrimNoExtra() => Eq(Str("hello"), AirtableRuntime.TRIM(Str("hello")));

    [Fact]
    public void ReptBasic() => Eq(Str("ababab"), AirtableRuntime.REPT(Str("ab"), I(3)));

    [Fact]
    public void ReptZero() => Eq(Str(""), AirtableRuntime.REPT(Str("ab"), I(0)));

    [Fact]
    public void ConcatenateBasic() =>
        Eq(Str("a1b"), AirtableRuntime.CONCATENATE(Str("a"), I(1), Str("b")));

    [Fact]
    public void ConcatenateWithNumbers() =>
        Eq(Str("count: 5"), AirtableRuntime.CONCATENATE(Str("count: "), I(5)));

    [Fact]
    public void TString() => Eq(Str("hello"), AirtableRuntime.T(Str("hello")));

    [Fact]
    public void TNumberIsEmpty() => Eq(Str(""), AirtableRuntime.T(I(42)));

    [Fact]
    public void TNullIsEmpty() => Eq(Str(""), AirtableRuntime.T(Nul()));

    [Fact]
    public void EncodeUrlComponentSpace() =>
        Eq(Str("hello%20world"), AirtableRuntime.ENCODE_URL_COMPONENT(Str("hello world")));

    [Fact]
    public void EncodeUrlComponentPercent() =>
        Eq(Str("100%25"), AirtableRuntime.ENCODE_URL_COMPONENT(Str("100%")));

    [Fact]
    public void EncodeUrlComponentEncodesReservedChars()
    {
        // encodeURIComponent (which Airtable matches) percent-encodes reserved chars like & = + .
        Eq(Str("a%26b%3Dc"), AirtableRuntime.ENCODE_URL_COMPONENT(Str("a&b=c")));
        Eq(Str("a%2Bb"), AirtableRuntime.ENCODE_URL_COMPONENT(Str("a+b")));
    }

    [Fact]
    public void EncodeUrlComponentUnicode() =>
        Eq(Str("caf%C3%A9"), AirtableRuntime.ENCODE_URL_COMPONENT(Str("café")));

    // ---- Date/time ----

    [Fact]
    public void YearOfIsoDate() => Eq(I(2025), AirtableRuntime.YEAR(Str("2025-04-20T10:00:00Z")));

    [Fact]
    public void YearOfNullIsZero() => Eq(I(0), AirtableRuntime.YEAR(Nul()));

    [Fact]
    public void MonthOfIsoDate() => Eq(I(4), AirtableRuntime.MONTH(Str("2025-04-20T10:00:00Z")));

    [Fact]
    public void DayOfIsoDate() => Eq(I(20), AirtableRuntime.DAY(Str("2025-04-20T10:00:00Z")));

    [Fact]
    public void HourOfIsoDate() => Eq(I(10), AirtableRuntime.HOUR(Str("2025-04-20T10:30:00Z")));

    [Fact]
    public void MinuteBasic() => Eq(I(30), AirtableRuntime.MINUTE(Str("2024-01-15T14:30:00Z")));

    [Fact]
    public void SecondBasic() => Eq(I(45), AirtableRuntime.SECOND(Str("2024-01-15T14:30:45Z")));

    [Fact]
    public void WeekdaySunday() => Eq(I(0), AirtableRuntime.WEEKDAY(Str("2024-01-14T00:00:00Z")));

    [Fact]
    public void WeekdayMonday() => Eq(I(1), AirtableRuntime.WEEKDAY(Str("2024-01-15T00:00:00Z")));

    [Fact]
    public void WeekdaySaturday() => Eq(I(6), AirtableRuntime.WEEKDAY(Str("2024-01-20T00:00:00Z")));

    [Fact]
    public void WeeknumBasic() => Eq(I(3), AirtableRuntime.WEEKNUM(Str("2024-01-15T00:00:00Z")));

    [Fact]
    public void DatetimeDiffDays() =>
        Eq(
            I(5),
            AirtableRuntime.DATETIME_DIFF(
                Str("2025-04-20T00:00:00Z"),
                Str("2025-04-15T00:00:00Z"),
                Str("days")
            )
        );

    [Fact]
    public void DatetimeDiffHours() =>
        Eq(
            I(12),
            AirtableRuntime.DATETIME_DIFF(
                Str("2025-04-20T12:00:00Z"),
                Str("2025-04-20T00:00:00Z"),
                Str("hours")
            )
        );

    [Fact]
    public void DatetimeDiffMinutes() =>
        Eq(
            I(90),
            AirtableRuntime.DATETIME_DIFF(
                Str("2024-01-15T13:30:00Z"),
                Str("2024-01-15T12:00:00Z"),
                Str("minutes")
            )
        );

    [Fact]
    public void DatetimeDiffWeeks() =>
        Eq(
            I(2),
            AirtableRuntime.DATETIME_DIFF(
                Str("2024-01-29T00:00:00Z"),
                Str("2024-01-15T00:00:00Z"),
                Str("weeks")
            )
        );

    [Fact]
    public void DatetimeDiffMonths() =>
        Eq(
            I(2),
            AirtableRuntime.DATETIME_DIFF(
                Str("2024-03-15T00:00:00Z"),
                Str("2024-01-15T00:00:00Z"),
                Str("months")
            )
        );

    [Fact]
    public void DatetimeDiffYears() =>
        Eq(
            I(1),
            AirtableRuntime.DATETIME_DIFF(
                Str("2025-01-15T00:00:00Z"),
                Str("2024-06-15T00:00:00Z"),
                Str("years")
            )
        );

    [Fact]
    public void DatetimeDiffDefaultDays() =>
        Eq(
            I(5),
            AirtableRuntime.DATETIME_DIFF(Str("2024-01-20T00:00:00Z"), Str("2024-01-15T00:00:00Z"))
        );

    [Fact]
    public void DatetimeDiffNullIsZero() =>
        Eq(I(0), AirtableRuntime.DATETIME_DIFF(Nul(), Str("2024-01-15T00:00:00Z"), Str("days")));

    [Fact]
    public void DateaddDays() =>
        Eq(
            Str("2024-01-20T00:00:00.000Z"),
            AirtableRuntime.DATEADD(Str("2024-01-15T00:00:00Z"), I(5), Str("days"))
        );

    [Fact]
    public void DateaddMonthsClamp() =>
        Eq(
            Str("2024-02-29T00:00:00.000Z"),
            AirtableRuntime.DATEADD(Str("2024-01-31T00:00:00Z"), I(1), Str("months"))
        );

    [Fact]
    public void DateaddYears() =>
        Eq(
            Str("2025-01-15T00:00:00.000Z"),
            AirtableRuntime.DATEADD(Str("2024-01-15T00:00:00Z"), I(1), Str("years"))
        );

    [Fact]
    public void DateaddHours() =>
        Eq(
            Str("2024-01-15T15:00:00.000Z"),
            AirtableRuntime.DATEADD(Str("2024-01-15T12:00:00Z"), I(3), Str("hours"))
        );

    [Fact]
    public void DateaddNullIsNull() => Eq(Nul(), AirtableRuntime.DATEADD(Nul(), I(5), Str("days")));

    [Fact]
    public void IsSameSameDay() =>
        Eq(
            B(true),
            AirtableRuntime.IS_SAME(
                Str("2025-04-20T10:00:00Z"),
                Str("2025-04-20T15:00:00Z"),
                Str("days")
            )
        );

    [Fact]
    public void IsSameFalse() =>
        Eq(
            B(false),
            AirtableRuntime.IS_SAME(
                Str("2024-01-15T00:00:00Z"),
                Str("2024-01-16T00:00:00Z"),
                Str("days")
            )
        );

    [Fact]
    public void IsBeforeDay() =>
        Eq(
            B(true),
            AirtableRuntime.IS_BEFORE(
                Str("2025-04-20T10:00:00Z"),
                Str("2025-04-21T10:00:00Z"),
                Str("days")
            )
        );

    [Fact]
    public void IsBeforeFalseWhenAfter() =>
        Eq(
            B(false),
            AirtableRuntime.IS_BEFORE(
                Str("2025-04-22T10:00:00Z"),
                Str("2025-04-21T10:00:00Z"),
                Str("days")
            )
        );

    [Fact]
    public void IsAfterTrue() =>
        Eq(
            B(true),
            AirtableRuntime.IS_AFTER(
                Str("2024-01-16T00:00:00Z"),
                Str("2024-01-15T00:00:00Z"),
                Str("days")
            )
        );

    [Fact]
    public void WorkdayBasic() =>
        Eq(
            Str("2024-01-22T00:00:00.000Z"),
            AirtableRuntime.WORKDAY(Str("2024-01-15T00:00:00Z"), I(5))
        );

    [Fact]
    public void WorkdaySkipWeekend() =>
        Eq(
            Str("2024-01-22T00:00:00.000Z"),
            AirtableRuntime.WORKDAY(Str("2024-01-19T00:00:00Z"), I(1))
        );

    [Fact]
    public void WorkdayNegative() =>
        Eq(
            Str("2024-01-19T00:00:00.000Z"),
            AirtableRuntime.WORKDAY(Str("2024-01-22T00:00:00Z"), I(-1))
        );

    [Fact]
    public void WorkdayNullIsNull() => Eq(Nul(), AirtableRuntime.WORKDAY(Nul(), I(5)));

    [Fact]
    public void WorkdayDiffBasic() =>
        Eq(
            I(6),
            AirtableRuntime.WORKDAY_DIFF(Str("2024-01-15T00:00:00Z"), Str("2024-01-22T00:00:00Z"))
        );

    [Fact]
    public void WorkdayDiffReverseIsNegative() =>
        Eq(
            I(-6),
            AirtableRuntime.WORKDAY_DIFF(Str("2024-01-22T00:00:00Z"), Str("2024-01-15T00:00:00Z"))
        );

    [Fact]
    public void WorkdayDiffNullIsZero() =>
        Eq(I(0), AirtableRuntime.WORKDAY_DIFF(Nul(), Str("2024-01-15T00:00:00Z")));

    [Fact]
    public void SetTimezoneBasic() =>
        Eq(
            Str("2024-01-15T07:00:00.000Z"),
            AirtableRuntime.SET_TIMEZONE(Str("2024-01-15T12:00:00Z"), Str("America/New_York"))
        );

    [Fact]
    public void SetTimezoneInvalidZoneReturnsIso() =>
        Eq(
            Str("2024-01-15T12:00:00.000Z"),
            AirtableRuntime.SET_TIMEZONE(Str("2024-01-15T12:00:00Z"), Str("Not/AZone"))
        );

    [Fact]
    public void DatetimeFormatDefault() =>
        Eq(
            Str("2024-01-15T14:30:00.000Z"),
            AirtableRuntime.DATETIME_FORMAT(Str("2024-01-15T14:30:00Z"))
        );

    [Fact]
    public void DatetimeFormatCustomDate() =>
        Eq(
            Str("2024-01-15"),
            AirtableRuntime.DATETIME_FORMAT(Str("2024-01-15T14:30:00Z"), Str("YYYY-MM-DD"))
        );

    [Fact]
    public void DatetimeFormatTime() =>
        Eq(
            Str("14:30"),
            AirtableRuntime.DATETIME_FORMAT(Str("2024-01-15T14:30:00Z"), Str("HH:mm"))
        );

    [Fact]
    public void DatetimeFormatNullIsEmpty() =>
        Eq(Str(""), AirtableRuntime.DATETIME_FORMAT(Nul(), Str("YYYY-MM-DD")));

    [Fact]
    public void DatestrBasic() =>
        Eq(Str("2024-01-15"), AirtableRuntime.DATESTR(Str("2024-01-15T14:30:00Z")));

    [Fact]
    public void DatestrNullIsEmpty() => Eq(Str(""), AirtableRuntime.DATESTR(Nul()));

    [Fact]
    public void TimestrBasic() =>
        Eq(Str("14:30:00"), AirtableRuntime.TIMESTR(Str("2024-01-15T14:30:00Z")));

    [Fact]
    public void DatetimeParseBasic() =>
        Eq(Str("2024-01-15T00:00:00.000Z"), AirtableRuntime.DATETIME_PARSE(Str("2024-01-15")));

    [Fact]
    public void DatetimeParseGarbageIsNull() =>
        Eq(Nul(), AirtableRuntime.DATETIME_PARSE(Str("not a date")));

    [Fact]
    public void NowIsParseableIso() => Assert.NotNull(AirtableRuntime.D(AirtableRuntime.NOW()));

    [Fact]
    public void TodayIsParseableIso() => Assert.NotNull(AirtableRuntime.D(AirtableRuntime.TODAY()));

    [Fact]
    public void TonowWithUnitIsPositiveForPastDate() =>
        Assert.True(
            AirtableRuntime.N(AirtableRuntime.TONOW(Str("2000-01-01T00:00:00Z"), Str("days"))) > 0
        );

    [Fact]
    public void FromnowWithUnitIsNegativeForPastDate() =>
        Assert.True(
            AirtableRuntime.N(AirtableRuntime.FROMNOW(Str("2000-01-01T00:00:00Z"), Str("days"))) < 0
        );

    [Fact]
    public void TonowHumanDurationForOldDateIsYears() =>
        Assert.EndsWith(
            "years",
            AirtableRuntime.S(AirtableRuntime.TONOW(Str("2000-01-01T00:00:00Z")))
        );

    // ---- Array ----

    [Fact]
    public void ArrayJoinDefault() =>
        Eq(Str("1, 2, 3"), AirtableRuntime.ARRAYJOIN(Arr(I(1), I(2), I(3))));

    [Fact]
    public void ArrayJoinCustomSep() =>
        Eq(Str("1-2"), AirtableRuntime.ARRAYJOIN(Arr(I(1), I(2)), Str("-")));

    [Fact]
    public void ArrayJoinNonArray() => Eq(Str("hello"), AirtableRuntime.ARRAYJOIN(Str("hello")));

    [Fact]
    public void ArrayJoinNullIsEmpty() => Eq(Str(""), AirtableRuntime.ARRAYJOIN(null));

    [Fact]
    public void ArrayUniqueBasic() =>
        Eq(Arr(I(1), I(2), I(3)), AirtableRuntime.ARRAYUNIQUE(Arr(I(1), I(2), I(1), I(3))));

    [Fact]
    public void ArrayUniquePreservesOrder() =>
        Eq(Arr(I(3), I(1), I(2)), AirtableRuntime.ARRAYUNIQUE(Arr(I(3), I(1), I(2), I(1), I(3))));

    [Fact]
    public void ArrayCompactStripsNullsAndEmptyStrings() =>
        Eq(Arr(I(1), I(2)), AirtableRuntime.ARRAYCOMPACT(Arr(I(1), Nul(), Str(""), I(2))));

    [Fact]
    public void ArrayCompactKeepsZeroAndFalse() =>
        Eq(Arr(I(0), B(false)), AirtableRuntime.ARRAYCOMPACT(Arr(I(0), Nul(), B(false), Str(""))));

    [Fact]
    public void ArrayCompactNullInputIsEmptyArray() =>
        Eq(Arr(), AirtableRuntime.ARRAYCOMPACT(null));

    [Fact]
    public void ArrayFlattenNested() =>
        Eq(
            Arr(I(1), I(2), I(3), I(4)),
            AirtableRuntime.ARRAYFLATTEN(Arr(I(1), Arr(I(2), I(3)), I(4)))
        );

    [Fact]
    public void ArrayFlattenDeep() =>
        Eq(
            Arr(I(1), I(2), I(3), I(4)),
            AirtableRuntime.ARRAYFLATTEN(Arr(I(1), Arr(I(2), Arr(I(3), I(4)))))
        );

    [Fact]
    public void ArrayFlattenAlreadyFlat() =>
        Eq(Arr(I(1), I(2), I(3)), AirtableRuntime.ARRAYFLATTEN(Arr(I(1), I(2), I(3))));

    [Fact]
    public void ArrayFlattenNonArrayWraps() => Eq(Arr(I(5)), AirtableRuntime.ARRAYFLATTEN(I(5)));

    // ---- Regex ----

    [Fact]
    public void RegexMatchTrue() =>
        Eq(B(true), AirtableRuntime.REGEX_MATCH(Str("hello"), Str("^hel")));

    [Fact]
    public void RegexMatchFalse() =>
        Eq(B(false), AirtableRuntime.REGEX_MATCH(Str("hello"), Str("^xyz")));

    [Fact]
    public void RegexMatchUnanchored() =>
        Eq(B(true), AirtableRuntime.REGEX_MATCH(Str("Hello"), Str("^.e")));

    [Fact]
    public void RegexMatchInvalidPatternIsFalse() =>
        Eq(B(false), AirtableRuntime.REGEX_MATCH(Str("hello"), Str("(")));

    [Fact]
    public void RegexExtractBasic() =>
        Eq(Str("123"), AirtableRuntime.REGEX_EXTRACT(Str("hello123"), Str("\\d+")));

    [Fact]
    public void RegexExtractFirstMatch() =>
        Eq(Str("e"), AirtableRuntime.REGEX_EXTRACT(Str("Hello"), Str("[aeiou]")));

    [Fact]
    public void RegexExtractNoMatchIsEmptyString() =>
        Eq(Str(""), AirtableRuntime.REGEX_EXTRACT(Str("xyz"), Str("[aeiou]")));

    [Fact]
    public void RegexReplaceBasic() =>
        Eq(Str("hexo"), AirtableRuntime.REGEX_REPLACE(Str("hello"), Str("l+"), Str("x")));

    [Fact]
    public void RegexReplaceAllOccurrences() =>
        Eq(Str("H*ll*"), AirtableRuntime.REGEX_REPLACE(Str("Hello"), Str("[aeiou]"), Str("*")));
}
