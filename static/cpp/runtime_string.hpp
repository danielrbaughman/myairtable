#pragma once

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <string>
#include <vector>

#include "airtable_json.hpp"
#include "runtime.hpp"

namespace myairtable::runtime {

// Transpiled-formula string functions. Position/length semantics are UTF-8
// CODE POINTS (the Rust/Go precedent), not bytes: LEN("héllo") == 5.
// Case folding is ASCII-only (no ICU dependency); the live parity suites
// exercise unicode through concatenation/positional ops, not case mapping.

namespace detail {

/// Code-point count of a UTF-8 string (continuation bytes don't count).
inline size_t cp_length(const std::string& text) {
    size_t count = 0;
    for (const unsigned char c : text) {
        if ((c & 0xC0) != 0x80) {
            ++count;
        }
    }
    return count;
}

/// Byte index of the cp_offset-th code point (clamped to text.size()).
inline size_t cp_index(const std::string& text, size_t cp_offset) {
    size_t index = 0;
    size_t cp = 0;
    while (cp < cp_offset && index < text.size()) {
        ++index;
        while (index < text.size() && (static_cast<unsigned char>(text[index]) & 0xC0) == 0x80) {
            ++index;
        }
        ++cp;
    }
    return index;
}

inline std::string ascii_lower(std::string text) {
    std::transform(text.begin(), text.end(), text.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return text;
}

inline std::string ascii_upper(std::string text) {
    std::transform(text.begin(), text.end(), text.begin(),
                   [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
    return text;
}

} // namespace detail

inline json LEN(const json& value) {
    return json(static_cast<int64_t>(detail::cp_length(s(value))));
}

inline json LEFT(const json& text, const json& count) {
    const std::string str = s(text);
    const auto want = static_cast<size_t>(std::max(0, static_cast<int>(n(count))));
    const size_t end = detail::cp_index(str, std::min(want, detail::cp_length(str)));
    return json(str.substr(0, end));
}

inline json RIGHT(const json& text, const json& count) {
    const std::string str = s(text);
    const auto want = static_cast<size_t>(std::max(0, static_cast<int>(n(count))));
    const size_t total = detail::cp_length(str);
    const size_t start = detail::cp_index(str, total - std::min(want, total));
    return json(str.substr(start));
}

inline json MID(const json& text, const json& start, const json& count) {
    const std::string str = s(text);
    const auto start_cp = static_cast<size_t>(std::max(0, static_cast<int>(n(start)) - 1));
    const auto len = static_cast<size_t>(std::max(0, static_cast<int>(n(count))));
    const size_t total = detail::cp_length(str);
    if (start_cp >= total) {
        return json("");
    }
    const size_t begin = detail::cp_index(str, start_cp);
    const size_t end = detail::cp_index(str, std::min(start_cp + len, total));
    return json(str.substr(begin, end - begin));
}

inline json FIND(const json& needle, const json& haystack, const json& start = json(nullptr)) {
    const std::string hay = s(haystack);
    const std::string nee = s(needle);
    const auto offset = start.is_null()
                            ? size_t{0}
                            : static_cast<size_t>(std::max(0, static_cast<int>(n(start)) - 1));
    if (offset >= detail::cp_length(hay)) {
        return json(int64_t{0});
    }
    const size_t idx = hay.find(nee, detail::cp_index(hay, offset));
    if (idx == std::string::npos) {
        return json(int64_t{0});
    }
    return json(static_cast<int64_t>(detail::cp_length(hay.substr(0, idx)) + 1));
}

inline json SEARCH(const json& needle, const json& haystack, const json& start = json(nullptr)) {
    const std::string hay = detail::ascii_lower(s(haystack));
    const std::string nee = detail::ascii_lower(s(needle));
    const auto offset = start.is_null()
                            ? size_t{0}
                            : static_cast<size_t>(std::max(0, static_cast<int>(n(start)) - 1));
    if (offset >= detail::cp_length(hay)) {
        return json(int64_t{0});
    }
    const size_t idx = hay.find(nee, detail::cp_index(hay, offset));
    if (idx == std::string::npos) {
        return json(int64_t{0});
    }
    return json(static_cast<int64_t>(detail::cp_length(hay.substr(0, idx)) + 1));
}

inline json SUBSTITUTE(const json& text, const json& old_text, const json& new_text,
                       const json& occurrence = json(nullptr)) {
    const std::string str = s(text);
    const std::string from = s(old_text);
    const std::string to = s(new_text);
    if (from.empty()) {
        return json(str);
    }
    if (occurrence.is_null()) {
        std::string out;
        size_t pos = 0;
        while (true) {
            const size_t idx = str.find(from, pos);
            if (idx == std::string::npos) {
                out += str.substr(pos);
                break;
            }
            out += str.substr(pos, idx - pos);
            out += to;
            pos = idx + from.size();
        }
        return json(out);
    }
    const int target = static_cast<int>(n(occurrence));
    int current = 1;
    size_t search_from = 0;
    while (true) {
        const size_t idx = str.find(from, search_from);
        if (idx == std::string::npos) {
            break;
        }
        if (current == target) {
            return json(str.substr(0, idx) + to + str.substr(idx + from.size()));
        }
        ++current;
        search_from = idx + 1;
    }
    return json(str);
}

inline json REPLACE(const json& text, const json& start, const json& count,
                    const json& replacement) {
    const std::string str = s(text);
    const auto start_cp = static_cast<size_t>(std::max(0, static_cast<int>(n(start)) - 1));
    const auto len = static_cast<size_t>(std::max(0, static_cast<int>(n(count))));
    const std::string repl = s(replacement);
    const size_t total = detail::cp_length(str);
    if (start_cp > total) {
        return json(str + repl);
    }
    const size_t begin = detail::cp_index(str, start_cp);
    const size_t end = detail::cp_index(str, std::min(start_cp + len, total));
    return json(str.substr(0, begin) + repl + str.substr(end));
}

inline json LOWER(const json& value) {
    return json(detail::ascii_lower(s(value)));
}

inline json UPPER(const json& value) {
    return json(detail::ascii_upper(s(value)));
}

inline json TRIM(const json& value) {
    const std::string str = s(value);
    const auto begin = str.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) {
        return json("");
    }
    const auto end = str.find_last_not_of(" \t\r\n");
    return json(str.substr(begin, end - begin + 1));
}

inline json REPT(const json& text, const json& count) {
    const std::string str = s(text);
    const int times = std::max(0, static_cast<int>(n(count)));
    std::string out;
    out.reserve(str.size() * static_cast<size_t>(times));
    for (int i = 0; i < times; ++i) {
        out += str;
    }
    return json(out);
}

inline json CONCATENATE(const std::vector<json>& args) {
    std::string out;
    for (const json& arg : args) {
        out += s(arg);
    }
    return json(out);
}

inline json ENCODE_URL_COMPONENT(const json& value) {
    static constexpr char hex[] = "0123456789ABCDEF";
    const std::string allowed_extra = "-_.!~*'()";
    std::string out;
    for (const unsigned char c : s(value)) {
        if (c < 0x80 &&
            (std::isalnum(c) || allowed_extra.find(static_cast<char>(c)) != std::string::npos)) {
            out.push_back(static_cast<char>(c));
        } else {
            out.push_back('%');
            out.push_back(hex[c >> 4]);
            out.push_back(hex[c & 0x0F]);
        }
    }
    return json(out);
}

/// T(): the string itself for strings, "" for everything else.
inline json T(const json& value) {
    return value.is_string() ? value : json("");
}

} // namespace myairtable::runtime
