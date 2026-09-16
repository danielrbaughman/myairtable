#!/bin/bash
set -e

# Python
uv sync
uv run ruff check
uv run ty check
uv run pytest
uv run ruff format

# TypeScript / JavaScript
if ! command -v nvm &> /dev/null; then
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
fi
nvm use
yarn install
yarn lint
yarn test:ts
yarn format

# Rust
cargo check
cargo test
cargo fmt

# Swift
# Requires swift-format from the Swift 6.0+ toolchain (brew install swift-format).
# The static runtime tests live in their own SPM package at tests/swift_static/
# which symlinks src/myairtable/static/swift/ into its Sources tree.
# On macOS, always build with the Xcode-selected toolchain (xcrun) rather than
# whatever `swift` is first on PATH. swiftly's open-source toolchains cannot
# compile against a newer Xcode SDK: e.g. Swift 6.3.x + the macOS 27 SDK fails
# with "unknown argument: '-target-arch-variant'" and Foundation never imports.
SWIFT=swift
if [ "$(uname -s)" = "Darwin" ] && command -v xcrun &> /dev/null; then
    XCODE_SWIFT=$(xcrun --find swift 2>/dev/null || true)
    if [ -n "$XCODE_SWIFT" ]; then
        SWIFT="$XCODE_SWIFT"
    fi
fi
if command -v "$SWIFT" &> /dev/null; then
    echo "--- Swift checks ---"
    # Swift toolchain version gate — require Swift 6 for @Observable + macros.
    SWIFT_VERSION=$("$SWIFT" --version | head -1 | awk -F' ' '{for(i=1;i<=NF;i++) if ($i=="Swift" && $(i+1)=="version") print $(i+2)}')
    SWIFT_MAJOR=${SWIFT_VERSION%%.*}
    if [ -n "$SWIFT_MAJOR" ] && [ "$SWIFT_MAJOR" -lt 6 ]; then
        echo "[error] Swift 6+ required (got $SWIFT_VERSION). @Observable + strict concurrency need the Swift 6 toolchain."
        exit 1
    fi

    (cd tests/swift_static && "$SWIFT" build)
    (cd tests/swift_static && "$SWIFT" test)
    # Resolve swift-format from the same toolchain as $SWIFT, so a git hook and
    # an interactive shell agree no matter which shim swiftly puts first on PATH.
    # (Both Homebrew's 603.0.0 and Xcode's bundled build format this tree
    # byte-for-byte identically, so this only pins *which* binary runs.)
    SWIFT_FORMAT=$(command -v swift-format 2>/dev/null || true)
    if [ "$(uname -s)" = "Darwin" ] && command -v xcrun &> /dev/null; then
        XCODE_SWIFT_FORMAT=$(xcrun --find swift-format 2>/dev/null || true)
        if [ -n "$XCODE_SWIFT_FORMAT" ]; then
            SWIFT_FORMAT="$XCODE_SWIFT_FORMAT"
        fi
    fi
    if [ -n "$SWIFT_FORMAT" ]; then
        # Require a swift-format from the Swift 6.0+ toolchain. Three version
        # strings show up in the wild: the old swift-syntax numbering (5xx =
        # Swift 5.x, 6xx = Swift 6.x, e.g. 600.x/602.x), the newer semantic
        # scheme that tracks the Swift release directly (6.x.x = Swift 6.x),
        # and a bare "main" from toolchain-bundled dev builds (Xcode ships one).
        # Only a numeric version can be too old; "main" is always newer than 6.0.
        SWIFT_FORMAT_VERSION=$("$SWIFT_FORMAT" --version | head -1)
        SWIFT_FORMAT_MAJOR=${SWIFT_FORMAT_VERSION%%.*}
        case "$SWIFT_FORMAT_MAJOR" in
            '' | *[!0-9]*)
                : # non-numeric (e.g. "main"): a dev build from a modern toolchain
                ;;
            *)
                # OK when: new scheme major >= 6 (and < 100), or old scheme major >= 600.
                if { [ "$SWIFT_FORMAT_MAJOR" -ge 6 ] && [ "$SWIFT_FORMAT_MAJOR" -lt 100 ]; } || [ "$SWIFT_FORMAT_MAJOR" -ge 600 ]; then
                    :
                else
                    echo "[error] swift-format $SWIFT_FORMAT_VERSION is too old. Need Swift 6.0+ (6.x.x or 600.x.x+)."
                    exit 1
                fi
                ;;
        esac
        "$SWIFT_FORMAT" format --in-place --recursive --configuration .swift-format src/myairtable/static/swift tests/swift_static/Tests
    else
        echo "[warn] swift-format not installed; skipping format step. (brew install swift-format)"
    fi
else
    echo "[warn] Swift not on PATH; skipping Swift checks."
fi

# Kotlin
# The static runtime unit tests live in a Gradle project at tests/kotlin_static/
# whose main source set points directly at src/myairtable/static/kotlin/.
if [ -x tests/kotlin_static/gradlew ] && command -v java &> /dev/null; then
    echo "--- Kotlin checks ---"
    (cd tests/kotlin_static && ./gradlew test)
    if command -v ktlint &> /dev/null; then
        # Format the hand-written runtime + tests; generated output is exempt by design.
        ktlint --format "src/myairtable/static/kotlin/**/*.kt" "tests/kotlin_static/src/**/*.kt"
    else
        echo "[warn] ktlint not installed; skipping format step. (brew install ktlint)"
    fi
else
    echo "[warn] Java/gradlew not available; skipping Kotlin checks."
fi

# Java
# The static runtime unit tests live in a Gradle project at tests/java_static/
# whose main source set points directly at src/myairtable/static/java/.
if [ -x tests/java_static/gradlew ] && command -v java &> /dev/null; then
    echo "--- Java checks ---"
    (cd tests/java_static && ./gradlew test)
    if command -v google-java-format &> /dev/null; then
        # Format the hand-written runtime + tests; generated output is exempt by design.
        JAVA_SOURCES=$(find src/myairtable/static/java tests/java_static/src -name '*.java')
        if [ -n "$JAVA_SOURCES" ]; then
            echo "$JAVA_SOURCES" | xargs google-java-format --replace
        fi
    else
        echo "[warn] google-java-format not installed; skipping format step. (brew install google-java-format)"
    fi
else
    echo "[warn] Java/gradlew not available; skipping Java checks."
fi

# Go
# The static runtime + its unit tests live in-place at src/myairtable/static/go/ (a self-contained
# module; *_test.go and go.mod are excluded from the generator's flat static copy).
if command -v go &> /dev/null; then
    echo "--- Go checks ---"
    (cd src/myairtable/static/go && go vet ./...)
    (cd src/myairtable/static/go && go test ./...)
    # gofmt is part of the toolchain and deterministic; format the hand-written runtime.
    GO_UNFORMATTED=$(gofmt -l src/myairtable/static/go)
    if [ -n "$GO_UNFORMATTED" ]; then
        echo "[info] gofmt-formatting: $GO_UNFORMATTED"
        gofmt -w src/myairtable/static/go
    fi
    if command -v golangci-lint &> /dev/null; then
        (cd src/myairtable/static/go && golangci-lint run ./...)
    else
        echo "[warn] golangci-lint not installed; skipping lint step. (brew install golangci-lint)"
    fi
else
    echo "[warn] Go not on PATH; skipping Go checks."
fi

# C#
# The static runtime + its unit tests live in tests/csharp_static/ (an xUnit project
# whose .csproj compiles src/myairtable/static/csharp/ directly via <Compile Include>). Target net8.0;
# RollForward=Major lets the test host run on a newer installed runtime (e.g. SDK 9).
if command -v dotnet &> /dev/null; then
    echo "--- C# checks ---"
    (cd tests/csharp_static && dotnet test --nologo)
    # csharpier is the opinionated formatter (global dotnet tool, installed to ~/.dotnet/tools).
    # Format the hand-written runtime + tests; generated output is exempt by design.
    export PATH="$PATH:$HOME/.dotnet/tools"
    if command -v csharpier &> /dev/null; then
        CS_FMT_TARGETS="tests/csharp_static"
        [ -d src/myairtable/static/csharp ] && CS_FMT_TARGETS="src/myairtable/static/csharp $CS_FMT_TARGETS"
        csharpier format $CS_FMT_TARGETS
    else
        echo "[warn] csharpier not installed; skipping format step. (dotnet tool install -g csharpier)"
    fi
else
    echo "[warn] dotnet not on PATH; skipping C# checks."
fi
# C++
# The static runtime is header-only at src/myairtable/static/cpp/; its Catch2 unit tests live in
# tests/cpp_static/ (a CMake project whose include path points at src/myairtable/static/cpp directly).
if command -v cmake &> /dev/null; then
    echo "--- C++ checks ---"
    CPP_GEN="-G Ninja"
    command -v ninja &> /dev/null || CPP_GEN=""
    (cd tests/cpp_static && cmake -B build $CPP_GEN -DCMAKE_BUILD_TYPE=Debug > /dev/null && cmake --build build && (cd build && ctest --output-on-failure))
    # clang-format the hand-written runtime + tests; vendored headers and generated
    # output are exempt by design. Apple ships clang-format inside the Xcode
    # toolchain (not on PATH) — fall back to xcrun discovery.
    CLANG_FORMAT="$(command -v clang-format || xcrun --find clang-format 2>/dev/null || true)"
    if [ -n "$CLANG_FORMAT" ]; then
        find src/myairtable/static/cpp tests/cpp_static -name '*.hpp' -o -name '*.cpp' \
            | grep -v '/vendor/' | grep -v '/build/' \
            | xargs "$CLANG_FORMAT" -i --style=file
    else
        echo "[warn] clang-format not found; skipping format step. (xcode toolchain or brew install clang-format)"
    fi
else
    echo "[warn] cmake not on PATH; skipping C++ checks. (brew install cmake ninja)"
fi
