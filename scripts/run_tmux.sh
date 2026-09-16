#!/usr/bin/env bash
set -euo pipefail
SESSION="${1:-trustann-eval}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
tmux has-session -t "$SESSION" 2>/dev/null || tmux new-session -d -s "$SESSION" "cd '$ROOT' && python3 orchestrator.py --config config/config.json --all"
echo "tmux session: $SESSION"
echo "Attach with: tmux attach -t $SESSION"
