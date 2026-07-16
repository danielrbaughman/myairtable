# Unit tests for the hand-written C++ static runtime at ../../static/cpp.
# The runtime is header-only: this project compiles ONLY the test sources and
# points the include path at the runtime (same in-place pattern as the C#
# <Compile Include="../../static/csharp/**"> and Kotlin/Java srcDir harnesses).
cmake_minimum_required(VERSION 3.25)
project(cpp_static_tests CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)
FetchContent_Declare(
    Catch2
    GIT_REPOSITORY https://github.com/catchorg/Catch2.git
    GIT_TAG        v3.7.1
)
FetchContent_MakeAvailable(Catch2)

find_package(CURL REQUIRED)

file(GLOB TEST_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/test_*.cpp")
add_executable(cpp_static_tests ${TEST_SOURCES})
target_include_directories(cpp_static_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../static/cpp")
target_link_libraries(cpp_static_tests PRIVATE Catch2::Catch2WithMain CURL::libcurl)

list(APPEND CMAKE_MODULE_PATH ${catch2_SOURCE_DIR}/extras)
include(CTest)
include(Catch)
catch_discover_tests(cpp_static_tests)
