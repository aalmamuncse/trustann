#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 -m pip install -r "$ROOT/requirements.txt"
chmod +x "$ROOT/macctl/trustannctl"
echo "Installed Mac control dependencies."
echo "Use: $ROOT/macctl/trustannctl bootstrap"
