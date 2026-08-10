#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$GITHUB_WORKSPACE"
OUT="$ROOT/worldseal_output"
TARGET="${WORLDSEAL_TARGET:?WORLDSEAL_TARGET is required}"
rm -rf "$OUT"
mkdir -p "$OUT/logs"

bash "$ROOT/worldseal_clean/smoke.sh" 2>&1 | tee "$OUT/logs/00_smoke.log"
python "$ROOT/worldseal_clean/parallel_target.py" "$TARGET" 2>&1 | tee "$OUT/logs/50_parallel_${TARGET}.log"
python "$ROOT/worldseal_clean/verify_target.py" "$TARGET" 2>&1 | tee "$OUT/logs/90_verify_${TARGET}.log"
find "$OUT" -type f -print0 | sort -z | xargs -0 sha256sum > "$OUT/SHA256SUMS.txt"
