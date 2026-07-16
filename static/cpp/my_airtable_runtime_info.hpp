#pragma once

#include <string_view>

namespace myairtable {

/// Version handle for the MyAirtable C++ static runtime.
///
/// Bumped alongside runtime behaviour changes; surfaced by the integration
/// harness smoke test to prove the generated output is wired into consumers.
inline constexpr std::string_view kVersion = "0.1.0";

}  // namespace myairtable
