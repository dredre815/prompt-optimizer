#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ISSUE_NUMBER="${TRADELEAK_ISSUE_NUMBER:-27}"
ATA_COMMIT="${ATA_COMMIT:-6b49ee837ebc1fa0d5bf99d655dc3adc352a77d3}"
NONCE="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-$(date +%s)"
ROOT="$(mktemp -d /tmp/tradeleak-ata-XXXXXX)"
PRIVATE_KEY="$ROOT/private.pem"
PUBLIC_KEY="$ROOT/public.pem"
CIPHERTEXT_B64="$ROOT/ciphertext.b64"
CIPHERTEXT_BIN="$ROOT/ciphertext.bin"
PLAINTEXT_KEY="$ROOT/deepseek_key.txt"
RESULTS="$GITHUB_WORKSPACE/tradeleak_ata_output"
mkdir -p "$RESULTS"
rm -rf "$RESULTS"/*

cleanup() {
  set +e
  unset DEEPSEEK_API_KEY OPENAI_API_KEY
  for f in "$PLAINTEXT_KEY" "$CIPHERTEXT_BIN" "$CIPHERTEXT_B64" "$PRIVATE_KEY" "$PUBLIC_KEY"; do
    [ -f "$f" ] && (shred -u "$f" 2>/dev/null || rm -f "$f")
  done
  rm -rf "$ROOT" 2>/dev/null || true
}
trap cleanup EXIT

comment_file() {
  GH_TOKEN="$GITHUB_TOKEN" gh issue comment "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --body-file "$1" >/dev/null
}

publish_public_key() {
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$PRIVATE_KEY" 2>/dev/null
  openssl pkey -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY"
  {
    echo "TRADELEAK_ATA_PUBLIC_KEY_V2"
    echo "nonce=$NONCE"
    echo "run_id=${GITHUB_RUN_ID:-unknown}"
    echo "requested_model=deepseek-v4-flash"
    echo "ata_commit=$ATA_COMMIT"
    echo "TRADELEAK_ATA_PUBLIC_KEY_BEGIN"
    cat "$PUBLIC_KEY"
    echo "TRADELEAK_ATA_PUBLIC_KEY_END"
  } > "$ROOT/public_comment.txt"
  comment_file "$ROOT/public_comment.txt"
}

extract_ciphertext() {
  GH_TOKEN="$GITHUB_TOKEN" gh api "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/comments?per_page=100" --paginate > "$ROOT/comments.json"
  python - "$ROOT/comments.json" "$NONCE" "$CIPHERTEXT_B64" "$ROOT/cid" <<'PY'
import json,re,sys
src,nonce,out,cid=sys.argv[1:]
comments=json.load(open(src,encoding='utf-8'))
pat=re.compile(r'TRADELEAK_ATA_CIPHERTEXT_V2\s*\nnonce='+re.escape(nonce)+r'\s*\nTRADELEAK_ATA_CIPHERTEXT_BEGIN\s*\n(.*?)\nTRADELEAK_ATA_CIPHERTEXT_END',re.S)
for item in reversed(comments):
    m=pat.search(item.get('body') or '')
    if m:
        open(out,'w',encoding='ascii').write(''.join(m.group(1).split())+'\n')
        open(cid,'w').write(str(item['id']))
        raise SystemExit(0)
raise SystemExit(1)
PY
}

wait_for_credential() {
  local found=0
  for _ in $(seq 1 360); do
    if extract_ciphertext 2>/dev/null; then found=1; break; fi
    sleep 5
  done
  [ "$found" -eq 1 ] || { echo "Timed out waiting for encrypted credential" >&2; return 2; }
  base64 --decode "$CIPHERTEXT_B64" > "$CIPHERTEXT_BIN"
  openssl pkeyutl -decrypt -inkey "$PRIVATE_KEY" -in "$CIPHERTEXT_BIN" -out "$PLAINTEXT_KEY" \
    -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -pkeyopt rsa_mgf1_md:sha256
  local key
  key="$(cat "$PLAINTEXT_KEY")"
  [[ "$key" == sk-* ]] || { echo "Unexpected credential format" >&2; return 3; }
  echo "::add-mask::$key"
  export DEEPSEEK_API_KEY="$key"
  export OPENAI_API_KEY="$key"
  shred -u "$PLAINTEXT_KEY" 2>/dev/null || rm -f "$PLAINTEXT_KEY"
  if [ -s "$ROOT/cid" ]; then
    GH_TOKEN="$GITHUB_TOKEN" gh api -X DELETE "repos/${GITHUB_REPOSITORY}/issues/comments/$(cat "$ROOT/cid")" >/dev/null 2>&1 || true
  fi
}

prepare_runtime() {
  python -m venv "$ROOT/venv"
  source "$ROOT/venv/bin/activate"
  python -m pip install --upgrade --quiet pip wheel setuptools
  python -m pip install --quiet openai numpy pandas matplotlib mplfinance timeout-decorator eventlet
  git clone --quiet https://github.com/MTMQuantAI/Agent-Trading-Arena.git "$ROOT/ata"
  git -C "$ROOT/ata" checkout --quiet "$ATA_COMMIT"
  test "$(git -C "$ROOT/ata" rev-parse HEAD)" = "$ATA_COMMIT"
  git -C "$ROOT/ata" rev-parse HEAD > "$RESULTS/ata_commit.txt"
  sha256sum "$GITHUB_WORKSPACE/tradeleak_ata/runner.py" > "$RESULTS/runner_sha256.txt"
}

redact_outputs() {
  local key="${DEEPSEEK_API_KEY:-}"
  python - "$RESULTS" "$key" <<'PY'
from pathlib import Path
import re,sys
root=Path(sys.argv[1]); secret=sys.argv[2].encode(); pat=re.compile(rb'sk-[A-Za-z0-9_-]{12,}')
for p in root.rglob('*'):
    if p.is_file():
        raw=p.read_bytes(); new=raw.replace(secret,b'[REDACTED]') if secret else raw; new=pat.sub(b'[REDACTED_KEY_PATTERN]',new)
        if new!=raw: p.write_bytes(new)
if secret:
    hits=[str(p) for p in root.rglob('*') if p.is_file() and secret in p.read_bytes()]
    if hits: raise SystemExit('credential remnants: '+','.join(hits))
PY
}

publish_result() {
  local rc="$1"
  if [ -f "$RESULTS/summary.json" ]; then
    python - "$RESULTS/summary.json" "$ROOT/result_comment.txt" "${GITHUB_RUN_ID:-unknown}" "$rc" <<'PY'
import json,sys
s=json.load(open(sys.argv[1])); m=s['metrics']
lines=['TRADELEAK_ATA_RESULT_V2',f'run_id={sys.argv[3]}',f'exit_code={sys.argv[4]}',f'verdict={s["verdict"]}',f'model={s["model"]}',f'ata_commit={s["ata_commit"]}',f'active_accuracy={m["active_accuracy"]:.4f}',f'passive_accuracy={m["passive_accuracy"]:.4f}',f'random_accuracy={m["random_accuracy"]:.4f}',f'active_gain_over_passive={m["active_gain_over_passive"]:.4f}',f'active_gain_over_random={m["active_gain_over_random"]:.4f}',f'valid_response_rate={m["valid_response_rate"]:.4f}',f'median_active_price_impact_pct={m["median_active_price_impact_pct"]:.4f}',f'median_active_probe_cost={m["median_active_probe_cost"]:.2f}',f'selected_active_probes={json.dumps(s["selected_active_probes"],sort_keys=True)}','go_rule='+s['go_rule'],'Artifact contains calibration/test JSONL and non-secret execution log.']
open(sys.argv[2],'w').write('\n'.join(lines)+'\n')
PY
  else
    { echo 'TRADELEAK_ATA_RESULT_V2'; echo "run_id=${GITHUB_RUN_ID:-unknown}"; echo "exit_code=$rc"; echo 'verdict=INCONCLUSIVE-INFRA'; echo 'summary_missing=true'; tail -n 50 "$RESULTS/run.log" 2>/dev/null || true; } > "$ROOT/result_comment.txt"
  fi
  comment_file "$ROOT/result_comment.txt" || true
}

main() {
  publish_public_key
  wait_for_credential
  prepare_runtime
  source "$ROOT/venv/bin/activate"
  export ATA_ROOT="$ROOT/ata"
  export ATA_COMMIT="$ATA_COMMIT"
  local rc=0
  set +e
  python "$GITHUB_WORKSPACE/tradeleak_ata/runner.py" "$RESULTS" 2>&1 | tee "$RESULTS/run.log"
  rc=${PIPESTATUS[0]}
  set -e
  redact_outputs
  publish_result "$rc"
  unset DEEPSEEK_API_KEY OPENAI_API_KEY
  return "$rc"
}

main "$@"
