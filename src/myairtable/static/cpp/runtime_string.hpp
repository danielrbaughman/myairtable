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
// Case folding covers ASCII, Latin-1 Supplement, and Latin Extended-A via a
// built-in one-to-one mapping (no ICU dependency) — enough for the live parity
// suites' accented-Latin inputs; other scripts pass through unchanged.

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

/// Simple (one-to-one) lowercase mapping for ASCII, Latin-1 Supplement, and
/// Latin Extended-A. Every mapping preserves UTF-8 byte length, so lowered
/// strings stay offset-compatible (SEARCH relies on this). Other code points
/// are returned unchanged.
inline uint32_t cp_to_lower(uint32_t cp) {
    if (cp >= 'A' && cp <= 'Z') {
        return cp + 0x20;
    }
    if (cp >= 0xC0 && cp <= 0xDE && cp != 0xD7) { // À-Þ except ×
        return cp + 0x20;
    }
    if (cp == 0x178) { // Ÿ -> ÿ
        return 0xFF;
    }
    // Latin Extended-A upper/lower pairs (0x130 İ excluded: its full lowering
    // is multi-code-point, so it passes through).
    if (cp >= 0x100 && cp <= 0x137 && cp != 0x130 && (cp % 2) == 0) {
        return cp + 1;
    }
    if (cp >= 0x139 && cp <= 0x148 && (cp % 2) == 1) {
        return cp + 1;
    }
    if (cp >= 0x14A && cp <= 0x177 && (cp % 2) == 0) {
        return cp + 1;
    }
    if (cp >= 0x179 && cp <= 0x17E && (cp % 2) == 1) {
        return cp + 1;
    }
    return cp;
}

/// Simple uppercase mapping over the same ranges as cp_to_lower.
inline uint32_t cp_to_upper(uint32_t cp) {
    if (cp >= 'a' && cp <= 'z') {
        return cp - 0x20;
    }
    if (cp >= 0xE0 && cp <= 0xFE && cp != 0xF7) { // à-þ except ÷
        return cp - 0x20;
    }
    if (cp == 0xFF) { // ÿ -> Ÿ
        return 0x178;
    }
    if (cp == 0x131) { // ı (dotless i) -> I
        return 'I';
    }
    if (cp == 0x17F) { // ſ (long s) -> S
        return 'S';
    }
    if (cp >= 0x101 && cp <= 0x137 && (cp % 2) == 1) {
        return cp - 1;
    }
    if (cp >= 0x13A && cp <= 0x148 && (cp % 2) == 0) {
        return cp - 1;
    }
    if (cp >= 0x14B && cp <= 0x177 && (cp % 2) == 1) {
        return cp - 1;
    }
    if (cp >= 0x17A && cp <= 0x17E && (cp % 2) == 0) {
        return cp - 1;
    }
    return cp;
}

/// Apply a code-point case mapping across a UTF-8 string. Unmapped code
/// points (and any malformed byte sequences) are copied through verbatim; all
/// mapped results are < U+0800, i.e. encode in 1-2 bytes.
inline std::string map_case(const std::string& text, uint32_t (*map)(uint32_t)) {
    std::string out;
    out.reserve(text.size());
    size_t i = 0;
    while (i < text.size()) {
        const auto lead = static_cast<unsigned char>(text[i]);
        size_t len = 1;
        if ((lead & 0xE0) == 0xC0) {
            len = 2;
        } else if ((lead & 0xF0) == 0xE0) {
            len = 3;
        } else if ((lead & 0xF8) == 0xF0) {
            len = 4;
        }
        if (i + len > text.size()) { // truncated sequence: copy the tail as-is
            out.append(text, i, text.size() - i);
            break;
        }
        uint32_t cp = lead;
        bool valid = true;
        if (len > 1) {
            cp = lead & (0x7Fu >> len);
            for (size_t k = 1; k < len; ++k) {
                const auto cont = static_cast<unsigned char>(text[i + k]);
                if ((cont & 0xC0) != 0x80) {
                    valid = false;
                    break;
                }
                cp = (cp << 6) | (cont & 0x3Fu);
            }
        }
        const uint32_t mapped = valid ? map(cp) : cp;
        if (!valid || mapped == cp) {
            out.append(text, i, len);
        } else if (mapped < 0x80) {
            out.push_back(static_cast<char>(mapped));
        } else {
            out.push_back(static_cast<char>(0xC0 | (mapped >> 6)));
            out.push_back(static_cast<char>(0x80 | (mapped & 0x3F)));
        }
        i += len;
    }
    return out;
}

inline std::string fold_lower(const std::string& text) {
    return map_case(text, cp_to_lower);
}

inline std::string fold_upper(const std::string& text) {
    return map_case(text, cp_to_upper);
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
    const std::string hay = detail::fold_lower(s(haystack));
    const std::string nee = detail::fold_lower(s(needle));
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
    return json(detail::fold_lower(s(value)));
}

inline json UPPER(const json& value) {
    return json(detail::fold_upper(s(value)));
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
