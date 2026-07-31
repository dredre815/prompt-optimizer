#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ISSUE_NUMBER="${PAPER1_ISSUE_NUMBER:-4}"
RESULT_BRANCH="${PAPER1_RESULT_BRANCH:-paper1-real-gpt54mini-results-20260731}"
CASE_LIMIT="${PAPER1_CASE_LIMIT:-6}"
REPLICATES="${PAPER1_REPLICATES:-1}"
MODEL_ID="gpt-5.4-mini-2026-03-17"
PINNED_COMMIT="01477f9afb7a47b849ed4c9259d3a9a4738d9fda"
NONCE="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-$(date +%s)"
ROOT="$(mktemp -d /tmp/paper1-copilot-XXXXXX)"
PRIVATE_KEY="$ROOT/private.pem"
PUBLIC_KEY="$ROOT/public.pem"
CIPHERTEXT_B64="$ROOT/ciphertext.b64"
CIPHERTEXT_BIN="$ROOT/ciphertext.bin"
PLAINTEXT_KEY="$ROOT/openai_key.txt"
RESULTS="$ROOT/paper1_results"
RUN_LOG="$RESULTS/execution.log"
STATUS="$RESULTS/runtime_status.json"
mkdir -p "$RESULTS"

cleanup() {
  set +e
  unset OPENAI_API_KEY
  for f in "$PLAINTEXT_KEY" "$CIPHERTEXT_BIN" "$CIPHERTEXT_B64" "$PRIVATE_KEY"; do
    if [ -f "$f" ]; then
      shred -u "$f" 2>/dev/null || rm -f "$f"
    fi
  done
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
    echo "PAPER1_PUBLIC_KEY_V1"
    echo "nonce=$NONCE"
    echo "model=$MODEL_ID"
    echo "The private key exists only in this ephemeral setup process."
    echo "PAPER1_PUBLIC_KEY_BEGIN"
    cat "$PUBLIC_KEY"
    echo "PAPER1_PUBLIC_KEY_END"
  } > "$ROOT/public_comment.txt"
  comment_file "$ROOT/public_comment.txt"
}

extract_ciphertext() {
  GH_TOKEN="$GITHUB_TOKEN" gh api \
    "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/comments?per_page=100" \
    --paginate > "$ROOT/comments.json"
  python - "$ROOT/comments.json" "$NONCE" "$CIPHERTEXT_B64" <<'PY'
import json, re, sys
source, nonce, out = sys.argv[1:]
comments = json.load(open(source, encoding="utf-8"))
pat = re.compile(
    r"PAPER1_CIPHERTEXT_V1\s*\n"
    + r"nonce=" + re.escape(nonce) + r"\s*\n"
    + r"PAPER1_CIPHERTEXT_BEGIN\s*\n(.*?)\nPAPER1_CIPHERTEXT_END",
    re.S,
)
for item in reversed(comments):
    m = pat.search(item.get("body") or "")
    if m:
        data = "".join(m.group(1).split())
        open(out, "w", encoding="ascii").write(data + "\n")
        raise SystemExit(0)
raise SystemExit(1)
PY
}

wait_for_ciphertext() {
  local found=0
  for _ in $(seq 1 180); do
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
    -pkeyopt rsa_oaep_md:sha256
  local key
  key="$(cat "$PLAINTEXT_KEY")"
  if [[ "$key" != sk-* ]]; then
    echo "Decrypted payload does not look like an OpenAI API key" >&2
    return 3
  fi
  echo "::add-mask::$key"
  export OPENAI_API_KEY="$key"
  shred -u "$PLAINTEXT_KEY" 2>/dev/null || rm -f "$PLAINTEXT_KEY"
}

run_experiment() {
  local work="$ROOT/work"
  mkdir -p "$work"
  python -m venv "$ROOT/venv"
  # shellcheck disable=SC1091
  source "$ROOT/venv/bin/activate"
  python -m pip install --upgrade --quiet pip wheel setuptools
  git clone --quiet https://github.com/TauricResearch/TradingAgents.git "$work/TradingAgents"
  git -C "$work/TradingAgents" checkout --quiet "$PINNED_COMMIT"
  python -m pip install --quiet -e "$work/TradingAgents"
  python -m pip install --quiet "openai>=2.0"
  base64 --decode "$GITHUB_WORKSPACE/paper1_runtime/runner.py.gz.b64" | gzip --decompress > "$ROOT/run_real_tradingagents.py"
  python -m py_compile "$ROOT/run_real_tradingagents.py"
  python "$ROOT/run_real_tradingagents.py" \
    --repo "$work/TradingAgents" \
    --out-dir "$RESULTS" \
    --replicates "$REPLICATES" \
    --case-limit "$CASE_LIMIT" \
    2>&1 | tee "$RUN_LOG"
}

redact_outputs() {
  local key="${OPENAI_API_KEY:-}"
  python - "$RESULTS" "$key" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
secret = sys.argv[2]
if secret:
    for p in root.rglob("*"):
        if p.is_file():
            try:
                raw = p.read_bytes()
            except OSError:
                continue
            if secret.encode() in raw:
                p.write_bytes(raw.replace(secret.encode(), b"[REDACTED_OPENAI_KEY]"))
PY
  unset OPENAI_API_KEY
}

write_status() {
  local rc="$1"
  python - "$STATUS" "$RESULTS/summary.json" "$RESULTS/model_probe.json" "$rc" "$NONCE" <<'PY'
import json, sys
from pathlib import Path
status_path, summary_path, probe_path, rc, nonce = sys.argv[1:]
out = {"completed": int(rc) == 0, "exit_code": int(rc), "nonce": nonce}
for label, path in (("summary", summary_path), ("model_probe", probe_path)):
    p = Path(path)
    if p.exists():
        try:
            out[label] = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            out[label + "_read_error"] = str(e)
Path(status_path).write_text(json.dumps(out, indent=2), encoding="utf-8")
PY
}

publish_results() {
  local pub="$ROOT/publish-repo"
  git clone --quiet "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" "$pub"
  git -C "$pub" config user.name "paper1-experiment-bot"
  git -C "$pub" config user.email "paper1-experiment-bot@users.noreply.github.com"
  git -C "$pub" checkout --orphan "$RESULT_BRANCH"
  git -C "$pub" rm -rf . >/dev/null 2>&1 || true
  mkdir -p "$pub/paper1_results"
  cp -a "$RESULTS/." "$pub/paper1_results/"
  (cd "$RESULTS" && zip -q -r "$pub/paper1_results.zip" .)
  cat > "$pub/README.md" <<EOF
# Paper1 real GPT-5.4-mini experiment results

- Requested model: \`$MODEL_ID\`
- TradingAgents commit: \`$PINNED_COMMIT\`
- Source task: issue #$ISSUE_NUMBER
- Credential material is not included.
EOF
  git -C "$pub" add README.md paper1_results paper1_results.zip
  git -C "$pub" commit -m "paper1: publish real GPT-5.4-mini experiment results" >/dev/null
  git -C "$pub" push --force origin "HEAD:${RESULT_BRANCH}" >/dev/null
}

publish_completion_comment() {
  python - "$STATUS" "$ROOT/result_comment.txt" "$RESULT_BRANCH" <<'PY'
import json, sys
status_path, out_path, branch = sys.argv[1:]
s = json.load(open(status_path, encoding="utf-8"))
lines = [
    "PAPER1_RESULT_V1",
    f"nonce={s.get('nonce')}",
    f"completed={str(bool(s.get('completed'))).lower()}",
    f"exit_code={s.get('exit_code')}",
    f"result_branch={branch}",
]
probe = s.get("model_probe") or {}
if isinstance(probe, dict):
    lines.append(f"model_returned={probe.get('model_returned')}")
summary = s.get("summary") or {}
agg = summary.get("aggregate") if isinstance(summary, dict) else None
if isinstance(agg, dict):
    for key in (
        "n_runs", "n_successful_runs", "n_errors",
        "laundered_target_success_rate", "tagged_target_success_rate",
        "defended_target_success_rate", "laundered_flip_from_clean_rate",
        "defended_matches_clean_rate", "total_llm_calls_observed",
        "total_input_tokens_observed", "total_output_tokens_observed",
    ):
        lines.append(f"{key}={agg.get(key)}")
open(out_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
  comment_file "$ROOT/result_comment.txt"
}

main() {
  publish_public_key
  wait_for_ciphertext
  local rc=0
  set +e
  run_experiment
  rc=$?
  set -e
  redact_outputs
  write_status "$rc"
  publish_results || true
  publish_completion_comment || true
  return 0
}

main "$@"
