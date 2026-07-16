#pragma once

#include <string>
#include <utility>

#include "formula_field.hpp"
#include "formulas.hpp"

namespace myairtable {

/// Anything usable as a date operand: another date field or a literal string.
class FormulaDateOperand {
  public:
    virtual ~FormulaDateOperand() = default;
    virtual std::string datetime_parse_expr() const = 0;
};

/// A literal date string wrapped for DATETIME_PARSE.
class FormulaDateLiteral final : public FormulaDateOperand {
  public:
    explicit FormulaDateLiteral(std::string value) : value_(std::move(value)) {}

    std::string datetime_parse_expr() const override {
        return "DATETIME_PARSE('" + Formulas::escape_formula_string_single(value_) + "')";
    }

  private:
    std::string value_;
};

/// A pending date comparison: complete with `.date(...)` or a relative
/// `.days_ago(n)`-style anchor.
class FormulaDateComparison {
  public:
    FormulaDateComparison(std::string field_id, std::string op)
        : field_id_(std::move(field_id)), op_(std::move(op)) {}

    std::string date(const FormulaDateOperand& other) const {
        return other.datetime_parse_expr() + op_ + "DATETIME_PARSE({" + field_id_ + "})";
    }
    std::string date(const std::string& other) const { return date(FormulaDateLiteral(other)); }

    std::string milliseconds_ago(int n) const { return ago(n, "milliseconds"); }
    std::string seconds_ago(int n) const { return ago(n, "seconds"); }
    std::string minutes_ago(int n) const { return ago(n, "minutes"); }
    std::string hours_ago(int n) const { return ago(n, "hours"); }
    std::string days_ago(int n) const { return ago(n, "days"); }
    std::string weeks_ago(int n) const { return ago(n, "weeks"); }
    std::string months_ago(int n) const { return ago(n, "months"); }
    std::string quarters_ago(int n) const { return ago(n, "quarters"); }
    std::string years_ago(int n) const { return ago(n, "years"); }

  private:
    std::string ago(int n, const std::string& unit) const {
        return "DATETIME_DIFF(NOW(),{" + field_id_ + "},\"" + unit + "\")" + op_ +
               std::to_string(n);
    }

    std::string field_id_;
    std::string op_;
};

/// Filter builder for date fields; also usable as an operand against another
/// date field.
class FormulaDateField final : public FormulaField, public FormulaDateOperand {
  public:
    using FormulaField::FormulaField;

    std::string datetime_parse_expr() const override { return "DATETIME_PARSE(" + field() + ")"; }

    std::string on(const FormulaDateOperand& date) const { return comparison("=").date(date); }
    std::string on(const std::string& date) const { return on(FormulaDateLiteral(date)); }
    FormulaDateComparison on() const { return comparison("="); }

    std::string not_on(const FormulaDateOperand& date) const { return comparison("!=").date(date); }
    std::string not_on(const std::string& date) const { return not_on(FormulaDateLiteral(date)); }
    FormulaDateComparison not_on() const { return comparison("!="); }

    std::string on_or_after(const FormulaDateOperand& date) const {
        return comparison("<=").date(date);
    }
    std::string on_or_after(const std::string& date) const {
        return on_or_after(FormulaDateLiteral(date));
    }
    FormulaDateComparison on_or_after() const { return comparison("<="); }

    std::string on_or_before(const FormulaDateOperand& date) const {
        return comparison(">=").date(date);
    }
    std::string on_or_before(const std::string& date) const {
        return on_or_before(FormulaDateLiteral(date));
    }
    FormulaDateComparison on_or_before() const { return comparison(">="); }

    std::string after(const FormulaDateOperand& date) const { return comparison("<").date(date); }
    std::string after(const std::string& date) const { return after(FormulaDateLiteral(date)); }
    FormulaDateComparison after() const { return comparison("<"); }

    std::string before(const FormulaDateOperand& date) const { return comparison(">").date(date); }
    std::string before(const std::string& date) const { return before(FormulaDateLiteral(date)); }
    FormulaDateComparison before() const { return comparison(">"); }

    std::string between(const FormulaDateOperand& start, const FormulaDateOperand& end,
                        bool inclusive = true) const {
        return inclusive ? Formulas::and_({on_or_after(start), on_or_before(end)})
                         : Formulas::and_({after(start), before(end)});
    }
    std::string between(const std::string& start, const std::string& end,
                        bool inclusive = true) const {
        return between(FormulaDateLiteral(start), FormulaDateLiteral(end), inclusive);
    }
    std::string between(const std::string& start, const FormulaDateOperand& end,
                        bool inclusive = true) const {
        return between(FormulaDateLiteral(start), end, inclusive);
    }
    std::string between(const FormulaDateOperand& start, const std::string& end,
                        bool inclusive = true) const {
        return between(start, FormulaDateLiteral(end), inclusive);
    }

  private:
    FormulaDateComparison comparison(const std::string& op) const {
        return FormulaDateComparison(field_id(), op);
    }
};

} // namespace myairtable
