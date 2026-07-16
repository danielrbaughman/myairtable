#pragma once

#include <string>

#include "formula_text_ops.hpp"

namespace myairtable {

/// Filter builder for lookup/rollup fields: text operations search across the
/// joined multi-value contents.
class FormulaLookupField final : public FormulaTextOps {
  public:
    using FormulaTextOps::FormulaTextOps;

  protected:
    std::string string_field() const override { return "ARRAYJOIN(" + field() + ", \", \")"; }
};

} // namespace myairtable
