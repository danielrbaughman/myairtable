#pragma once

#include <string>

#include "formula_field.hpp"
#include "formulas.hpp"

namespace myairtable {

/// Filter builder for numeric fields (number, currency, percent, duration).
class FormulaNumberField final : public FormulaField {
  public:
    using FormulaField::FormulaField;

    std::string eq(double value) const { return field() + "=" + Formulas::num(value); }
    std::string neq(double value) const { return field() + "!=" + Formulas::num(value); }
    std::string greater_than(double value) const { return field() + ">" + Formulas::num(value); }
    std::string less_than(double value) const { return field() + "<" + Formulas::num(value); }
    std::string greater_than_or_equals(double value) const {
        return field() + ">=" + Formulas::num(value);
    }
    std::string less_than_or_equals(double value) const {
        return field() + "<=" + Formulas::num(value);
    }

    std::string between(double min, double max, bool inclusive = true) const {
        return inclusive ? Formulas::and_({greater_than_or_equals(min), less_than_or_equals(max)})
                         : Formulas::and_({greater_than(min), less_than(max)});
    }
};

} // namespace myairtable
