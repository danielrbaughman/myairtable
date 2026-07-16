#pragma once

#include "formula_text_ops.hpp"

namespace myairtable {

/// Filter builder for single-line/long text, email, url, phone fields.
class FormulaTextField final : public FormulaTextOps {
  public:
    using FormulaTextOps::FormulaTextOps;
};

} // namespace myairtable
