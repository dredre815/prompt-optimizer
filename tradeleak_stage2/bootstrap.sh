#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ISSUE_NUMBER="${TRADELEAK_STAGE2_ISSUE_NUMBER:-29}"
ATA_COMMIT="${ATA_COMMIT:-6b49ee837ebc1fa0d5bf99d655dc3adc352a77d3}"
NONCE="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-$(date +%s)"
ROOT="$(mktemp -d /tmp/tradeleak-stage2-XXXXXX)"
PRIVATE_KEY="$ROOT/private.pem"
PUBLIC_KEY="$ROOT/public.pem"
CIPHERTEXT_B64="$ROOT/ciphertext.b64"
CIPHERTEXT_BIN="$ROOT/ciphertext.bin"
PLAINTEXT_KEY="$ROOT/deepseek_key.txt"
CID_FILE="$ROOT/cid"
RESULTS="$GITHUB_WORKSPACE/tradeleak_stage2_output"
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

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$PRIVATE_KEY" 2>/dev/null
openssl pkey -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY"
{
  echo "TRADELEAK_STAGE2_PUBLIC_KEY_V1"
  echo "nonce=$NONCE"
  echo "run_id=${GITHUB_RUN_ID:-unknown}"
  echo "requested_model=deepseek-v4-flash"
  echo "ata_commit=$ATA_COMMIT"
  echo "TRADELEAK_STAGE2_PUBLIC_KEY_BEGIN"
  cat "$PUBLIC_KEY"
  echo "TRADELEAK_STAGE2_PUBLIC_KEY_END"
} > "$ROOT/public_comment.txt"
comment_file "$ROOT/public_comment.txt"

found=0
for _ in $(seq 1 360); do
  GH_TOKEN="$GITHUB_TOKEN" gh api "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/comments?per_page=100" --paginate > "$ROOT/comments.json"
  if python - "$ROOT/comments.json" "$NONCE" "$CIPHERTEXT_B64" "$CID_FILE" <<'PY'
import json,re,sys
src,nonce,out,cid=sys.argv[1:]
comments=json.load(open(src,encoding='utf-8'))
pat=re.compile(r'TRADELEAK_STAGE2_CIPHERTEXT_V1\s*\nnonce='+re.escape(nonce)+r'\s*\nTRADELEAK_STAGE2_CIPHERTEXT_BEGIN\s*\n(.*?)\nTRADELEAK_STAGE2_CIPHERTEXT_END',re.S)
for item in reversed(comments):
    m=pat.search(item.get('body') or '')
    if m:
        open(out,'w',encoding='ascii').write(''.join(m.group(1).split())+'\n')
        open(cid,'w').write(str(item['id']))
        raise SystemExit(0)
raise SystemExit(1)
PY
  then found=1; break; fi
  sleep 5
done
[ "$found" -eq 1 ] || { echo "Timed out waiting for encrypted credential" >&2; exit 2; }

base64 --decode "$CIPHERTEXT_B64" > "$CIPHERTEXT_BIN"
openssl pkeyutl -decrypt -inkey "$PRIVATE_KEY" -in "$CIPHERTEXT_BIN" -out "$PLAINTEXT_KEY" \
  -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -pkeyopt rsa_mgf1_md:sha256
key="$(cat "$PLAINTEXT_KEY")"
[[ "$key" == sk-* ]] || { echo "Unexpected credential format" >&2; exit 3; }
echo "::add-mask::$key"
export DEEPSEEK_API_KEY="$key"
export OPENAI_API_KEY="$key"
shred -u "$PLAINTEXT_KEY" 2>/dev/null || rm -f "$PLAINTEXT_KEY"
if [ -s "$CID_FILE" ]; then
  GH_TOKEN="$GITHUB_TOKEN" gh api -X DELETE "repos/${GITHUB_REPOSITORY}/issues/comments/$(cat "$CID_FILE")" >/dev/null 2>&1 || true
fi

python -m pip install --quiet --upgrade pip wheel setuptools
python -m pip install --quiet 'openai>=2,<3' numpy pandas matplotlib mplfinance timeout-decorator eventlet

git clone --quiet https://github.com/MTMQuantAI/Agent-Trading-Arena.git "$ROOT/ata"
git -C "$ROOT/ata" checkout --quiet "$ATA_COMMIT"
test "$(git -C "$ROOT/ata" rev-parse HEAD)" = "$ATA_COMMIT"
printf '%s\n' "$ATA_COMMIT" > "$RESULTS/ata_commit.txt"

export ATA_ROOT="$ROOT/ata"
export OUTDIR="$RESULTS"
set +e
python "$GITHUB_WORKSPACE/tradeleak_stage2/runner.py" 2>&1 | tee "$RESULTS/execution.log"
RC=${PIPESTATUS[0]}
set -e

# Redact any credential-like remnants from outputs, then fail if the exact key remains.
python - "$RESULTS" "$key" <<'PY'
from pathlib import Path
import re,sys
root=Path(sys.argv[1]); secret=sys.argv[2].encode()
pat=re.compile(rb'sk-[A-Za-z0-9_\-]{12,}')
for p in root.rglob('*'):
    if not p.is_file(): continue
    raw=p.read_bytes()
    new=raw.replace(secret,b'[REDACTED_DEEPSEEK_KEY]') if secret else raw
    new=pat.sub(b'[REDACTED_API_KEY_PATTERN]',new)
    if new!=raw: p.write_bytes(new)
if secret:
    hits=[str(p) for p in root.rglob('*') if p.is_file() and secret in p.read_bytes()]
    if hits: raise SystemExit('credential remnant: '+','.join(hits))
PY

python - "$RESULTS/summary.json" "$ROOT/result_comment.txt" "$RC" "$ATA_COMMIT" <<'PY'
import json,sys
summary_path,out,rc,commit=sys.argv[1:]
lines=['TRADELEAK_STAGE2_RESULT_V1',f'run_id={__import__("os").environ.get("GITHUB_RUN_ID")}',f'exit_code={rc}',f'ata_commit={commit}']
try:
    s=json.load(open(summary_path,encoding='utf-8'))
    for k in ['verdict','model','matched_pairs','selected_probes','mean_passive_accuracy','mean_random_accuracy','mean_active_accuracy','active_gain_over_passive','active_gain_over_random','valid_response_rate','median_active_price_impact_pct']:
        lines.append(f'{k}={json.dumps(s.get(k),ensure_ascii=False) if isinstance(s.get(k),(dict,list)) else s.get(k)}')
    lines.append('pair_metrics='+json.dumps(s.get('pair_metrics'),ensure_ascii=False,separators=(',',':')))
except Exception as e:
    lines.append('summary_error='+repr(e))
open(out,'w',encoding='utf-8').write('\n'.join(lines)+'\n')
PY
comment_file "$ROOT/result_comment.txt" || true
unset DEEPSEEK_API_KEY OPENAI_API_KEY
exit "$RC"
