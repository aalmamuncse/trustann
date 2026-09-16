#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import importlib
for m in ["numpy","grpc","matplotlib"]:
    importlib.import_module(m)
    print(m, "OK")
PY
python3 -m trustann.rpc.worker_server --help >/dev/null
echo "TrustANN RPC package OK"
