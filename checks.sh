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
        # swift-format major version must match the Swift toolchain major to avoid
        # silent drift between local + CI. swift-format 602.x.x ships with Swift 6.
        SWIFT_FORMAT_VERSION=$(swift-format --version | head -1)
        SWIFT_FORMAT_MAJOR=${SWIFT_FORMAT_VERSION%%.*}
        if [ "$SWIFT_FORMAT_MAJOR" -lt 600 ]; then
            echo "[error] swift-format $SWIFT_FORMAT_VERSION is too old. Need 600.x.x+ (Swift 6.0 toolchain)."
            exit 1
        fi
        swift-format format --in-place --recursive --configuration .swift-format static/swift tests/swift_static/Tests
    else
        echo "[warn] swift-format not installed; skipping format step. (brew install swift-format)"
    fi
else
    echo "[warn] Swift not on PATH; skipping Swift checks."
fi