#pragma once

#include <string>
#include <vector>

#include "formulas.hpp"

namespace myairtable {

/// Record-id filters: `RECORD_ID()='rec...'` and id-list membership.
class FormulaId {
  public:
    std::string eq(const std::string& id) const {
        return "RECORD_ID()='" + Formulas::escape_formula_string_single(id) + "'";
    }

    std::string in_list(const std::vector<std::string>& ids) const {
        if (ids.empty()) {
            return "FALSE()";
        }
        if (ids.size() == 1) {
            return eq(ids.front());
        }
        std::vector<std::string> parts;
        parts.reserve(ids.size());
        for (const auto& id : ids) {
            parts.push_back(eq(id));
        }
        return Formulas::or_(parts);
    }
};

} // namespace myairtable
