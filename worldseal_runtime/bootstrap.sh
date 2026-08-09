#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ISSUE_NUMBER="${WORLDSEAL_ISSUE_NUMBER:-22}"
NONCE="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-$(date +%s)"
ROOT="$(mktemp -d /tmp/worldseal-XXXXXX)"
PRIVATE_KEY="$ROOT/private.pem"
PUBLIC_KEY="$ROOT/public.pem"
CIPHERTEXT_B64="$ROOT/ciphertext.b64"
CIPHERTEXT_BIN="$ROOT/ciphertext.bin"
CIPHERTEXT_COMMENT_ID="$ROOT/ciphertext_comment_id"
PLAINTEXT_KEY="$ROOT/deepseek_key.txt"
RESULTS="$GITHUB_WORKSPACE/worldseal_runtime/output"
STATUS="$RESULTS/bootstrap_status.json"
LOG="$RESULTS/execution.log"
mkdir -p "$RESULTS"
rm -rf "$RESULTS"/*

cleanup() {
  set +e
  unset DEEPSEEK_API_KEY
  for f in "$PLAINTEXT_KEY" "$CIPHERTEXT_BIN" "$CIPHERTEXT_B64" "$PRIVATE_KEY" "$PUBLIC_KEY"; do
    if [ -f "$f" ]; then
      shred -u "$f" 2>/dev/null || rm -f "$f"
    fi
  done
  rm -rf "$ROOT" 2>/dev/null || true
}
trap cleanup EXIT

comment_file() {
  local file="$1"
  GH_TOKEN="$GITHUB_TOKEN" gh issue comment "$ISSUE_NUMBER" \
    --repo "$GITHUB_REPOSITORY" --body-file "$file" >/dev/null
}

publish_public_key() {
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 \
    -out "$PRIVATE_KEY" 2>/dev/null
  openssl pkey -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY"
  {
    echo "WORLDSEAL_PUBLIC_KEY_V1"
    echo "nonce=$NONCE"
    echo "run_id=${GITHUB_RUN_ID:-unknown}"
    echo "requested_model=deepseek-v4-flash"
    echo "The private key exists only in this ephemeral GitHub Actions process."
    echo "WORLDSEAL_PUBLIC_KEY_BEGIN"
    cat "$PUBLIC_KEY"
    echo "WORLDSEAL_PUBLIC_KEY_END"
  } > "$ROOT/public_comment.txt"
  comment_file "$ROOT/public_comment.txt"
}

extract_ciphertext() {
  GH_TOKEN="$GITHUB_TOKEN" gh api \
    "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/comments?per_page=100" \
    --paginate > "$ROOT/comments.json"
  python - "$ROOT/comments.json" "$NONCE" "$CIPHERTEXT_B64" "$CIPHERTEXT_COMMENT_ID" <<'PY'
import json, re, sys
source, nonce, out, id_out = sys.argv[1:]
comments = json.load(open(source, encoding="utf-8"))
pat = re.compile(
    r"WORLDSEAL_CIPHERTEXT_V1\s*\n"
    + r"nonce=" + re.escape(nonce) + r"\s*\n"
    + r"WORLDSEAL_CIPHERTEXT_BEGIN\s*\n(.*?)\nWORLDSEAL_CIPHERTEXT_END",
    re.S,
)
for item in reversed(comments):
    m = pat.search(item.get("body") or "")
    if m:
        data = "".join(m.group(1).split())
        open(out, "w", encoding="ascii").write(data + "\n")
        open(id_out, "w", encoding="ascii").write(str(item.get("id")) + "\n")
        raise SystemExit(0)
raise SystemExit(1)
PY
}

wait_for_ciphertext() {
  local found=0
  for _ in $(seq 1 360); do
    if extract_ciphertext 2>/dev/null; then
      found=1
      break
    fi
    sleep 5
  done
  if [ "$found" -ne 1 ]; then
    echo "Timed out waiting for encrypted credential" >&2
    return 2
  fi
  base64 --decode "$CIPHERTEXT_B64" > "$CIPHERTEXT_BIN"
  openssl pkeyutl -decrypt \
    -inkey "$PRIVATE_KEY" \
    -in "$CIPHERTEXT_BIN" \
    -out "$PLAINTEXT_KEY" \
    -pkeyopt rsa_padding_mode:oaep \
    -pkeyopt rsa_oaep_md:sha256 \
    -pkeyopt rsa_mgf1_md:sha256
  local key
  key="$(cat "$PLAINTEXT_KEY")"
  if [[ "$key" != sk-* ]]; then
    echo "Decrypted payload does not match expected key format" >&2
    return 3
  fi
  echo "::add-mask::$key"
  export DEEPSEEK_API_KEY="$key"
  shred -u "$PLAINTEXT_KEY" 2>/dev/null || rm -f "$PLAINTEXT_KEY"
  if [ -s "$CIPHERTEXT_COMMENT_ID" ]; then
    local cid
    cid="$(cat "$CIPHERTEXT_COMMENT_ID")"
    GH_TOKEN="$GITHUB_TOKEN" gh api -X DELETE \
      "repos/${GITHUB_REPOSITORY}/issues/comments/${cid}" >/dev/null 2>&1 || true
  fi
}

prepare_runtime() {
  cat "$GITHUB_WORKSPACE"/worldseal_runtime/runner_parts/part* > "$ROOT/runner.py.gz.b64"
  base64 --decode "$ROOT/runner.py.gz.b64" | gzip --decompress > "$ROOT/worldseal_runner.py"
  echo "989b3d9964b73b0b0752fe8a3f262e5b84455cab8587647542940f82e8dba3d7  $ROOT/worldseal_runner.py" | sha256sum --check --strict
  python -m py_compile "$ROOT/worldseal_runner.py"

  python -m venv "$ROOT/venv"
  source "$ROOT/venv/bin/activate"
  python -m pip install --upgrade --quiet pip wheel setuptools

  git clone --quiet https://github.com/TauricResearch/TradingAgents.git "$ROOT/TradingAgents"
  git -C "$ROOT/TradingAgents" checkout --quiet a33fd4c0f134485a43553a2c23a63cb14adbd88f
  python -m pip install --quiet -e "$ROOT/TradingAgents"
}

run_experiment() {
  source "$ROOT/venv/bin/activate"
  python "$ROOT/worldseal_runner.py" \
    --outdir "$RESULTS" \
    --replicates 3 \
    --seed 20260809 \
    2>&1 | tee "$LOG"
}

redact_and_scan_outputs() {
  local key="${DEEPSEEK_API_KEY:-}"
  python - "$RESULTS" "$key" <<'PY'
from pathlib import Path
import re, sys
root = Path(sys.argv[1])
secret = sys.argv[2].encode()
pattern = re.compile(rb"sk-[A-Za-z0-9_\-]{12,}")
for p in root.rglob("*"):
    if not p.is_file():
        continue
    raw = p.read_bytes()
    new = raw.replace(secret, b"[REDACTED_DEEPSEEK_KEY]") if secret else raw
    new = pattern.sub(b"[REDACTED_API_KEY_PATTERN]", new)
    if new != raw:
        p.write_bytes(new)
if secret:
    hits = [str(p) for p in root.rglob("*") if p.is_file() and secret in p.read_bytes()]
    if hits:
        raise SystemExit("credential-remnant files: " + ",".join(hits))
PY
}

write_status() {
  local rc="$1"
  python - "$STATUS" "$RESULTS/summary.json" "$rc" "$NONCE" <<'PY'
import json, sys
from pathlib import Path
status_path, summary_path, rc, nonce = sys.argv[1:]
out = {
    "bootstrap_exit_code": int(rc),
    "nonce": nonce,
    "runner_completed": int(rc) == 0,
    "github_run_id": __import__("os").environ.get("GITHUB_RUN_ID"),
}
p = Path(summary_path)
if p.exists():
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
        out["n_successful"] = s.get("n_successful")
        out["strict_counterexample_established"] = s.get("strict_counterexample_established")
        out["clean_control_passed"] = s.get("clean_control_passed")
    except Exception as exc:
        out["summary_read_error"] = str(exc)
Path(status_path).write_text(json.dumps(out, indent=2), encoding="utf-8")
PY
}

publish_completion_comment() {
  python - "$STATUS" "$ROOT/result_comment.txt" <<'PY'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
lines = [
    "WORLDSEAL_RESULT_V1",
    f"nonce={s.get('nonce')}",
    f"runner_completed={str(bool(s.get('runner_completed'))).lower()}",
    f"bootstrap_exit_code={s.get('bootstrap_exit_code')}",
    f"run_id={s.get('github_run_id')}",
    f"n_successful={s.get('n_successful')}",
    f"strict_counterexample_established={s.get('strict_counterexample_established')}",
    f"clean_control_passed={s.get('clean_control_passed')}",
    "The encrypted credential comment was removed after decryption; the artifact was scanned for key remnants.",
]
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
  comment_file "$ROOT/result_comment.txt"
}

main() {
  publish_public_key
  wait_for_ciphertext
  prepare_runtime
  local rc=0
  set +e
  run_experiment
  rc=$?
  set -e
  redact_and_scan_outputs
  write_status "$rc"
  publish_completion_comment || true
  unset DEEPSEEK_API_KEY
  return 0
}

main "$@"
