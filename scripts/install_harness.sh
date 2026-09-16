#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
"$PY" -m pip install -U grpcio numpy matplotlib
echo "Installed harness dependencies."
echo "Make sure the TrustANN RPC package is importable from PYTHONPATH."
