#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python -m grpc_tools.protoc -I "$ROOT/trustann/rpc" --python_out="$ROOT/trustann/rpc" --grpc_python_out="$ROOT/trustann/rpc" "$ROOT/trustann/rpc/worker.proto"
