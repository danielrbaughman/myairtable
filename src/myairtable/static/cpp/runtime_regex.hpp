#pragma once

#include <regex>
#include <string>

#include "airtable_json.hpp"
#include "runtime.hpp"

namespace myairtable::runtime {

// Transpiled-formula regex functions (std::regex, ECMAScript grammar).
// A malformed pattern DEGRADES like the other targets (C# catches
// ArgumentException) instead of throwing: std::regex_error is swallowed and
// the no-match result returned — formula evaluation must never abort.

inline json REGEX_EXTRACT(const json& text, const json& pattern) {
    const std::string subject = s(text);
    try {
        const std::regex re(s(pattern));
        std::smatch match;
        if (std::regex_search(subject, match, re)) {
            return json(match.str(0));
        }
        return json("");
    } catch (const std::regex_error&) {
        return json("");
    }
}

inline json REGEX_MATCH(const json& text, const json& pattern) {
    try {
        const std::regex re(s(pattern));
        return json(std::regex_search(s(text), re));
    } catch (const std::regex_error&) {
        return json(false);
    }
}

inline json REGEX_REPLACE(const json& text, const json& pattern, const json& replacement) {
    const std::string subject = s(text);
    try {
        const std::regex re(s(pattern));
        return json(std::regex_replace(subject, re, s(replacement)));
    } catch (const std::regex_error&) {
        return json(subject);
    }
}

} // namespace myairtable::runtime
