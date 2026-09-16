#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:?remote harness root}"
PY="${2:?python}"
INDEX="${3:?index}"
META="${4:?metadata}"
SHARD="${5:?shard}"
REPLICA="${6:?replica}"
PORT="${7:?port}"
LOG="${8:-/tmp/trustann-worker.log}"
mkdir -p "$(dirname "$LOG")"
pkill -f "trustann.rpc.worker_server.*--shard ${SHARD}.*--replica ${REPLICA}" || true
nohup bash -lc "cd '$ROOT' && PYTHONPATH='$ROOT':\$PYTHONPATH '$PY' -m trustann.rpc.worker_server --index '$INDEX' --metadata '$META' --shard '$SHARD' --replica '$REPLICA' --port '$PORT'" > "$LOG" 2>&1 < /dev/null &
echo $!
