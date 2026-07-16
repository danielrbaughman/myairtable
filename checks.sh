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
# which symlinks static/swift/ into its Sources tree.
if command -v swift &> /dev/null; then
    echo "--- Swift checks ---"
    # Swift toolchain version gate — require Swift 6 for @Observable + macros.
    SWIFT_VERSION=$(swift --version | head -1 | awk -F' ' '{for(i=1;i<=NF;i++) if ($i=="Swift" && $(i+1)=="version") print $(i+2)}')
    SWIFT_MAJOR=${SWIFT_VERSION%%.*}
    if [ -n "$SWIFT_MAJOR" ] && [ "$SWIFT_MAJOR" -lt 6 ]; then
        echo "[error] Swift 6+ required (got $SWIFT_VERSION). @Observable + strict concurrency need the Swift 6 toolchain."
        exit 1
    fi

    (cd tests/swift_static && swift build)
    (cd tests/swift_static && swift test)
    if command -v swift-format &> /dev/null; then
        # Require a swift-format from the Swift 6.0+ toolchain. Two version
        # schemes exist: the old swift-syntax numbering (5xx = Swift 5.x,
        # 6xx = Swift 6.x, e.g. 600.x/602.x) and the newer semantic scheme that
        # tracks the Swift release directly (6.x.x = Swift 6.x). Accept either.
        SWIFT_FORMAT_VERSION=$(swift-format --version | head -1)
        SWIFT_FORMAT_MAJOR=${SWIFT_FORMAT_VERSION%%.*}
        # OK when: new scheme major >= 6 (and < 100), or old scheme major >= 600.
        if { [ "$SWIFT_FORMAT_MAJOR" -ge 6 ] && [ "$SWIFT_FORMAT_MAJOR" -lt 100 ]; } || [ "$SWIFT_FORMAT_MAJOR" -ge 600 ]; then
            :
        else
            echo "[error] swift-format $SWIFT_FORMAT_VERSION is too old. Need Swift 6.0+ (6.x.x or 600.x.x+)."
            exit 1
        fi
        swift-format format --in-place --recursive --configuration .swift-format static/swift tests/swift_static/Tests
    else
        echo "[warn] swift-format not installed; skipping format step. (brew install swift-format)"
    fi
else
    echo "[warn] Swift not on PATH; skipping Swift checks."
fi

# Kotlin
# The static runtime unit tests live in a Gradle project at tests/kotlin_static/
# whose main source set points directly at static/kotlin/.
if [ -x tests/kotlin_static/gradlew ] && command -v java &> /dev/null; then
    echo "--- Kotlin checks ---"
    (cd tests/kotlin_static && ./gradlew test)
    if command -v ktlint &> /dev/null; then
        # Format the hand-written runtime + tests; generated output is exempt by design.
        ktlint --format "static/kotlin/**/*.kt" "tests/kotlin_static/src/**/*.kt"
    else
        echo "[warn] ktlint not installed; skipping format step. (brew install ktlint)"
    fi
else
    echo "[warn] Java/gradlew not available; skipping Kotlin checks."
fi

# Java
# The static runtime unit tests live in a Gradle project at tests/java_static/
# whose main source set points directly at static/java/.
if [ -x tests/java_static/gradlew ] && command -v java &> /dev/null; then
    echo "--- Java checks ---"
    (cd tests/java_static && ./gradlew test)
    if command -v google-java-format &> /dev/null; then
        # Format the hand-written runtime + tests; generated output is exempt by design.
        JAVA_SOURCES=$(find static/java tests/java_static/src -name '*.java')
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
# The static runtime + its unit tests live in-place at static/go/ (a self-contained
# module; *_test.go and go.mod are excluded from the generator's flat static copy).
if command -v go &> /dev/null; then
    echo "--- Go checks ---"
    (cd static/go && go vet ./...)
    (cd static/go && go test ./...)
    # gofmt is part of the toolchain and deterministic; format the hand-written runtime.
    GO_UNFORMATTED=$(gofmt -l static/go)
    if [ -n "$GO_UNFORMATTED" ]; then
        echo "[info] gofmt-formatting: $GO_UNFORMATTED"
        gofmt -w static/go
    fi
    if command -v golangci-lint &> /dev/null; then
        (cd static/go && golangci-lint run ./...)
    else
        echo "[warn] golangci-lint not installed; skipping lint step. (brew install golangci-lint)"
    fi
else
    echo "[warn] Go not on PATH; skipping Go checks."
fi

# C#
# The static runtime + its unit tests live in tests/csharp_static/ (an xUnit project
# whose .csproj compiles static/csharp/ directly via <Compile Include>). Target net8.0;
# RollForward=Major lets the test host run on a newer installed runtime (e.g. SDK 9).
if command -v dotnet &> /dev/null; then
    echo "--- C# checks ---"
    (cd tests/csharp_static && dotnet test --nologo)
    # csharpier is the opinionated formatter (global dotnet tool, installed to ~/.dotnet/tools).
    # Format the hand-written runtime + tests; generated output is exempt by design.
    export PATH="$PATH:$HOME/.dotnet/tools"
    if command -v csharpier &> /dev/null; then
        CS_FMT_TARGETS="tests/csharp_static"
        [ -d static/csharp ] && CS_FMT_TARGETS="static/csharp $CS_FMT_TARGETS"
        csharpier format $CS_FMT_TARGETS
    else
        echo "[warn] csharpier not installed; skipping format step. (dotnet tool install -g csharpier)"
    fi
else
    echo "[warn] dotnet not on PATH; skipping C# checks."
fi
# C++
# The static runtime is header-only at static/cpp/; its Catch2 unit tests live in
# tests/cpp_static/ (a CMake project whose include path points at static/cpp directly).
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
        find static/cpp tests/cpp_static -name '*.hpp' -o -name '*.cpp' \
            | grep -v '/vendor/' | grep -v '/build/' \
            | xargs "$CLANG_FORMAT" -i --style=file
    else
        echo "[warn] clang-format not found; skipping format step. (xcode toolchain or brew install clang-format)"
    fi
else
    echo "[warn] cmake not on PATH; skipping C++ checks. (brew install cmake ninja)"
fi
