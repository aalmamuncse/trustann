#!/usr/bin/env bash
set -euo pipefail
pkill -f "trustann.rpc.worker_server" || true
