#pragma once

#include <string>

#include "formula_field.hpp"

namespace myairtable {

/// Filter builder for checkbox fields.
class FormulaBooleanField final : public FormulaField {
  public:
    using FormulaField::FormulaField;

    std::string eq(bool value) const { return value ? is_true() : is_false(); }
    std::string is_true() const { return field() + "=TRUE()"; }
    std::string is_false() const { return field() + "=FALSE()"; }
};

} // namespace myairtable
