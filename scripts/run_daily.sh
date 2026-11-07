#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

log_dir="$root/data/outputs/pipeline_runs"
mkdir -p "$log_dir"
log="$log_dir/console_$(date +%Y%m%d_%H%M%S).txt"

has_trigger=0
for arg in "$@"; do
    case "$arg" in
        --trig*) has_trigger=1 ;;
    esac
done
if [ "$has_trigger" -eq 0 ]; then
    set -- --trigger daily "$@"
fi

export PYTHONUTF8=1
echo "[run_daily] logging to $log"
set +e
python scripts/run_pipeline.py "$@" 2>&1 | tee "$log"
code=${PIPESTATUS[0]}
set -e
exit "$code"
