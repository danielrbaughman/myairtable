#pragma once

// Timezone support for SET_TIMEZONE, via the vendored Howard Hinnant date/tz
// library reading the OS zoneinfo database (`/usr/share/zoneinfo` — present on
// macOS and Linux; no download step).
//
// The tz library needs its implementation (`tz.cpp`) compiled exactly once.
// This runtime is otherwise header-only, so the implementation is exposed
// stb-style: in EXACTLY ONE translation unit, define
// `MYAIRTABLE_TZ_IMPLEMENTATION` before including any myairtable header:
//
//     // tz_impl.cpp (one file in your project)
//     #define MYAIRTABLE_TZ_IMPLEMENTATION
//     #include "static/airtable_tz.hpp"
//
// Every other TU just includes headers normally and links against that one.

#ifndef USE_OS_TZDB
#define USE_OS_TZDB 1
#endif

#include "vendor/date/tz.h"

#ifdef MYAIRTABLE_TZ_IMPLEMENTATION
#include "vendor/date/tz.cpp"
#endif
