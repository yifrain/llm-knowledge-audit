#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
# This script does not imply paid approval. Pass --approve-paid only after explicit approval.
uv run --frozen llmka run-all --config configs/pilot.yaml "$@"
