#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
uv run --frozen llmka build-report "$@"
