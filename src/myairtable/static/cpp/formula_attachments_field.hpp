#pragma once

#include <string>

#include "formula_field.hpp"

namespace myairtable {

/// Filter builder for attachment fields (LEN-based emptiness/count checks).
class FormulaAttachmentsField final : public FormulaField {
  public:
    using FormulaField::FormulaField;

    std::string count(int n) const { return "LEN(" + field() + ")=" + std::to_string(n); }
    std::string is_empty() const override { return "LEN(" + field() + ")=0"; }
    std::string is_not_empty() const override { return "LEN(" + field() + ")>0"; }
};

} // namespace myairtable
