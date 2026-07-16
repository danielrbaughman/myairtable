#pragma once

#include <initializer_list>
#include <string>
#include <vector>

namespace myairtable {

/// Combinators + escaping for the generated filterByFormula DSL.
///
/// `and`/`or`/`xor`/`not` are C++ alternative tokens (operators), so the
/// combinators carry the codebase's trailing-underscore keyword escape:
/// `Formulas::and_(...)`, `Formulas::or_(...)`, `Formulas::not_(...)`.
struct Formulas {
    static std::string and_(const std::vector<std::string>& args) { return combine("AND", args); }
    static std::string and_(std::initializer_list<std::string> args) {
        return combine("AND", std::vector<std::string>(args));
    }
    static std::string or_(const std::vector<std::string>& args) { return combine("OR", args); }
    static std::string or_(std::initializer_list<std::string> args) {
        return combine("OR", std::vector<std::string>(args));
    }
    static std::string xor_(const std::vector<std::string>& args) { return combine("XOR", args); }
    static std::string xor_(std::initializer_list<std::string> args) {
        return combine("XOR", std::vector<std::string>(args));
    }
    static std::string not_(const std::string& formula) { return "NOT(" + formula + ")"; }

    // ---- internals shared by the Formula*Field classes -----------------------

    static std::string escape_formula_string(const std::string& value) {
        return replace_all(replace_all(value, "\\", "\\\\"), "\"", "\\\"");
    }

    static std::string escape_formula_string_single(const std::string& value) {
        return replace_all(replace_all(value, "\\", "\\\\"), "'", "\\'");
    }

    /// Render a number the way Airtable formulas expect (no trailing zeros).
    static std::string num(double value) {
        if (value == static_cast<long long>(value)) {
            return std::to_string(static_cast<long long>(value));
        }
        std::string text = std::to_string(value);
        while (!text.empty() && text.back() == '0') {
            text.pop_back();
        }
        if (!text.empty() && text.back() == '.') {
            text.pop_back();
        }
        return text;
    }

    static std::string wrap_field(const std::string& field, bool case_sensitive, bool trim) {
        std::string wrapped = field;
        if (trim) {
            wrapped = "TRIM(" + wrapped + ")";
        }
        if (!case_sensitive) {
            wrapped = "LOWER(" + wrapped + ")";
        }
        return wrapped;
    }

    static std::string wrap_value_str(const std::string& value, bool case_sensitive, bool trim) {
        std::string wrapped = "\"" + escape_formula_string(value) + "\"";
        if (trim) {
            wrapped = "TRIM(" + wrapped + ")";
        }
        if (!case_sensitive) {
            wrapped = "LOWER(" + wrapped + ")";
        }
        return wrapped;
    }

  private:
    static std::string combine(const std::string& fn, const std::vector<std::string>& args) {
        std::vector<std::string> filtered;
        for (const auto& arg : args) {
            if (!arg.empty()) {
                filtered.push_back(arg);
            }
        }
        if (filtered.empty()) {
            return "";
        }
        if (filtered.size() == 1) {
            return filtered.front();
        }
        std::string out = fn + "(";
        for (size_t i = 0; i < filtered.size(); ++i) {
            if (i > 0) {
                out.push_back(',');
            }
            out += filtered[i];
        }
        out.push_back(')');
        return out;
    }

    static std::string replace_all(std::string text, const std::string& from,
                                   const std::string& to) {
        size_t pos = 0;
        while ((pos = text.find(from, pos)) != std::string::npos) {
            text.replace(pos, from.size(), to);
            pos += to.size();
        }
        return text;
    }
};

} // namespace myairtable
