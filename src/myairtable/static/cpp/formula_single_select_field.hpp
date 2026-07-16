#pragma once

#include "formula_text_ops.hpp"

namespace myairtable {

/// Filter builder for single-select fields (choice names compare as text).
class FormulaSingleSelectField final : public FormulaTextOps {
  public:
    using FormulaTextOps::FormulaTextOps;
};

} // namespace myairtable
