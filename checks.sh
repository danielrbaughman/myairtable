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
# Requires swift-format from the Swift 6.0 toolchain (brew install swift-format).
# The static runtime tests live in their own SPM package at tests/swift_static/
# which symlinks static/swift/ into its Sources tree.
if command -v swift &> /dev/null; then
    echo "--- Swift checks ---"
    (cd tests/swift_static && swift build)
    (cd tests/swift_static && swift test)
    if command -v swift-format &> /dev/null; then
        swift-format format --in-place --recursive --configuration .swift-format static/swift tests/swift_static/Tests
    else
        echo "[warn] swift-format not installed; skipping format step. (brew install swift-format)"
    fi
else
    echo "[warn] Swift not on PATH; skipping Swift checks."
fi