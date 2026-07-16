#pragma once

#include "formula_text_ops.hpp"

namespace myairtable {

/// Filter builder for multiple-select fields (joined choice names compare as text).
class FormulaMultiSelectField final : public FormulaTextOps {
  public:
    using FormulaTextOps::FormulaTextOps;
};

} // namespace myairtable
