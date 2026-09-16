#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"

echo "[1/3] Compile check"
"$PY" -m compileall -q .

echo "[2/3] Unit tests"
"$PY" -m pytest -q tests

echo "[3/3] AWS mandatory experiments"
./macctl/trustannctl run --groups mandatory --no-cleanup
