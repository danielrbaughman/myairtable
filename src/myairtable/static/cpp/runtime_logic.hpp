#pragma once

#include <cmath>
#include <initializer_list>
#include <string>

#include "airtable_json.hpp"
#include "runtime.hpp"

namespace myairtable::runtime {

// Transpiled-formula logic functions (BLANK/TRUE/FALSE/IF/SWITCH/ISERROR/ERROR).
// System headers may #define TRUE/FALSE (e.g. mach/boolean.h) — guard them.
// The transpiler never calls TRUE()/FALSE() (it emits v(true)); these exist for
// runtime-library parity and direct use.

#pragma push_macro("TRUE")
#pragma push_macro("FALSE")
#ifdef TRUE
#undef TRUE
#endif
#ifdef FALSE
#undef FALSE
#endif

/// The blank/empty sentinel — a JSON null value.
inline json BLANK() {
    return json(nullptr);
}

inline json TRUE() {
    return json(true);
}

inline json FALSE() {
    return json(false);
}

#pragma pop_macro("FALSE")
#pragma pop_macro("TRUE")

inline json IF(const json& condition, const json& if_true, const json& if_false) {
    return is_truthy(condition) ? if_true : if_false;
}

/// SWITCH with the flat shape the transpiler emits: `pairs` alternates
/// (pattern, value); the default comes SECOND (so the trailing braced list can
/// hold the pairs). Patterns match by s() coercion (cross-numeric-shape parity).
inline json SWITCH(const json& expr, const json& default_value, std::initializer_list<json> pairs) {
    const std::string key = s(expr);
    auto it = pairs.begin();
    while (it != pairs.end()) {
        const json& pattern = *it++;
        if (it == pairs.end()) {
            break;
        }
        const json& value = *it++;
        if (s(pattern) == key) {
            return value;
        }
    }
    return default_value;
}

/// ISERROR returns true for NaN numbers — the in-memory computation-error signal.
inline json ISERROR(const json& value) {
    const bool is_nan = value.is_number() && std::isnan(value.get<double>());
    return json(is_nan);
}

/// Surface as NaN so ISERROR picks it up.
inline json ERROR() {
    return json(std::nan(""));
}
inline json ERROR(const json& /*message*/) {
    return ERROR();
}

} // namespace myairtable::runtime
