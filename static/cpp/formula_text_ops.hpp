#pragma once

#include <string>
#include <vector>

#include "formula_field.hpp"
#include "formulas.hpp"

namespace myairtable {

/// Text comparison/search operations shared by text-like fields (text, select,
/// lookup). `eq`/`neq` are named terse (cf. std::ranges::equal_to) — column
/// parity with the C#/Java `Eq`/`Neq`.
class FormulaTextOps : public FormulaField {
  public:
    using FormulaField::FormulaField;

    std::string eq(const std::string& value, bool case_sensitive = true, bool trim = false) const {
        return Formulas::wrap_field(field(), case_sensitive, trim) + "=" +
               Formulas::wrap_value_str(value, case_sensitive, trim);
    }

    std::string equals_any(const std::vector<std::string>& values, bool case_sensitive = true,
                           bool trim = false) const {
        std::vector<std::string> parts;
        parts.reserve(values.size());
        for (const auto& value : values) {
            parts.push_back(eq(value, case_sensitive, trim));
        }
        return Formulas::or_(parts);
    }

    std::string neq(const std::string& value, bool case_sensitive = true, bool trim = false) const {
        return Formulas::wrap_field(field(), case_sensitive, trim) +
               "!=" + Formulas::wrap_value_str(value, case_sensitive, trim);
    }

    std::string contains(const std::string& value, bool case_sensitive = true,
                         bool trim = false) const {
        return "FIND(" + Formulas::wrap_value_str(value, case_sensitive, trim) + "," +
               Formulas::wrap_field(string_field(), case_sensitive, trim) + ")>0";
    }

    std::string contains_any(const std::vector<std::string>& values, bool case_sensitive = true,
                             bool trim = false) const {
        std::vector<std::string> parts;
        parts.reserve(values.size());
        for (const auto& value : values) {
            parts.push_back(contains(value, case_sensitive, trim));
        }
        return Formulas::or_(parts);
    }

    std::string contains_all(const std::vector<std::string>& values, bool case_sensitive = true,
                             bool trim = false) const {
        std::vector<std::string> parts;
        parts.reserve(values.size());
        for (const auto& value : values) {
            parts.push_back(contains(value, case_sensitive, trim));
        }
        return Formulas::and_(parts);
    }

    std::string not_contains(const std::string& value, bool case_sensitive = true,
                             bool trim = false) const {
        return Formulas::not_(contains(value, case_sensitive, trim));
    }

    std::string starts_with(const std::string& value, bool case_sensitive = true,
                            bool trim = false) const {
        return "FIND(" + Formulas::wrap_value_str(value, case_sensitive, trim) + "," +
               Formulas::wrap_field(string_field(), case_sensitive, trim) + ")=1";
    }

    std::string not_starts_with(const std::string& value, bool case_sensitive = true,
                                bool trim = false) const {
        return "FIND(" + Formulas::wrap_value_str(value, case_sensitive, trim) + "," +
               Formulas::wrap_field(string_field(), case_sensitive, trim) + ")!=1";
    }

    std::string ends_with(const std::string& value, bool case_sensitive = true,
                          bool trim = false) const {
        const std::string f = Formulas::wrap_field(string_field(), case_sensitive, trim);
        const std::string v = Formulas::wrap_value_str(value, case_sensitive, trim);
        return "FIND(" + v + "," + f + ")=LEN(" + f + ")-LEN(" + v + ")+1";
    }

    std::string not_ends_with(const std::string& value, bool case_sensitive = true,
                              bool trim = false) const {
        const std::string f = Formulas::wrap_field(string_field(), case_sensitive, trim);
        const std::string v = Formulas::wrap_value_str(value, case_sensitive, trim);
        return "FIND(" + v + "," + f + ")!=LEN(" + f + ")-LEN(" + v + ")+1";
    }

    /// Compare phone numbers ignoring separators (spaces, dashes, parens, +, .).
    std::string phone_equals(const std::string& value) const {
        std::string normalized;
        for (const char c : value) {
            if (std::string(" -().+").find(c) == std::string::npos) {
                normalized.push_back(c);
            }
        }
        const std::string stripped =
            "SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(" + field() +
            ",\" \",\"\"),\"-\",\"\"),\"(\",\"\"),\")\",\"\"),\"+\",\"\"),\".\",\"\")";
        return stripped + "=\"" + Formulas::escape_formula_string(normalized) + "\"";
    }

    std::string regex_match(const std::string& pattern) const {
        return "REGEX_MATCH(" + field() + ",\"" + Formulas::escape_formula_string(pattern) + "\")";
    }

  protected:
    /// The expression text operations run against; lookups override with an
    /// ARRAYJOIN so multi-value fields search across all elements.
    virtual std::string string_field() const { return field(); }
};

} // namespace myairtable
