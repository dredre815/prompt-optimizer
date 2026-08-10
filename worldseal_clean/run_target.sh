#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$GITHUB_WORKSPACE"
OUT="$ROOT/worldseal_output"
TARGET="${WORLDSEAL_TARGET:?WORLDSEAL_TARGET is required}"
rm -rf "$OUT"
mkdir -p "$OUT/logs"

bash "$ROOT/worldseal_clean/smoke.sh" 2>&1 | tee "$OUT/logs/00_smoke.log"
case "$TARGET" in
  tradingagents)
    python "$ROOT/worldseal_clean/tradingagents_experiment.py" --mode full 2>&1 | tee "$OUT/logs/10_tradingagents_full.log"
    ;;
  broker)
    python "$ROOT/worldseal_clean/broker_experiment.py" --mode full 2>&1 | tee "$OUT/logs/20_broker_full.log"
    ;;
  rdagent)
    python "$ROOT/worldseal_clean/rdagent_experiment.py" --mode full 2>&1 | tee "$OUT/logs/30_rdagent_full.log"
    ;;
  *)
    echo "unknown target: $TARGET" >&2
    exit 64
    ;;
esac
python "$ROOT/worldseal_clean/verify_target.py" "$TARGET" 2>&1 | tee "$OUT/logs/90_verify_${TARGET}.log"
find "$OUT" -type f -print0 | sort -z | xargs -0 sha256sum > "$OUT/SHA256SUMS.txt"
