#!/bin/bash
set -e

uv sync
uv run ruff check
uv run ty check
uv run pytest
uv run ruff format

yarn install
yarn lint
yarn test:ts
yarn format