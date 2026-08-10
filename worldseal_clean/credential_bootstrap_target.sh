#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ISSUE_NUMBER="${WORLDSEAL_ISSUE_NUMBER:?WORLDSEAL_ISSUE_NUMBER required}"
TARGET="${WORLDSEAL_TARGET:?WORLDSEAL_TARGET required}"
NONCE="${GITHUB_RUN_ID:-local}-${TARGET}-${GITHUB_RUN_ATTEMPT:-1}-$(date +%s)-$RANDOM"
TMP="$(mktemp -d /tmp/worldseal-target-key-XXXXXX)"
PRIV="$TMP/private.pem"
PUB="$TMP/public.pem"
CT_B64="$TMP/ciphertext.b64"
CT_BIN="$TMP/ciphertext.bin"
KEY_FILE="$TMP/deepseek.key"
CID_FILE="$TMP/comment_id"
RESULT_DIR="$GITHUB_WORKSPACE/worldseal_output"
mkdir -p "$RESULT_DIR"

cleanup() {
  set +e
  unset DEEPSEEK_API_KEY
  for f in "$KEY_FILE" "$CT_BIN" "$CT_B64" "$PRIV" "$PUB"; do
    [ -f "$f" ] && (shred -u "$f" 2>/dev/null || rm -f "$f")
  done
  rm -rf "$TMP"
}
trap cleanup EXIT

post_comment() {
  GH_TOKEN="$GITHUB_TOKEN" gh issue comment "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --body-file "$1" >/dev/null
}

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$PRIV" 2>/dev/null
openssl pkey -in "$PRIV" -pubout -out "$PUB"
{
  echo "WORLDSEAL_TARGET_PUBLIC_KEY_V1"
  echo "nonce=$NONCE"
  echo "target=$TARGET"
  echo "run_id=${GITHUB_RUN_ID:-unknown}"
  echo "WORLDSEAL_TARGET_PUBLIC_KEY_BEGIN"
  cat "$PUB"
  echo "WORLDSEAL_TARGET_PUBLIC_KEY_END"
} > "$TMP/public_comment.txt"
post_comment "$TMP/public_comment.txt"

extract_ciphertext() {
  GH_TOKEN="$GITHUB_TOKEN" gh api "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/comments?per_page=100" --paginate > "$TMP/comments.json"
  python - "$TMP/comments.json" "$NONCE" "$CT_B64" "$CID_FILE" <<'PY'
import json,re,sys
source,nonce,out,idout=sys.argv[1:]
items=json.load(open(source,encoding='utf-8'))
pat=re.compile(r"WORLDSEAL_TARGET_CIPHERTEXT_V1\s*\nnonce="+re.escape(nonce)+r"\s*\nWORLDSEAL_TARGET_CIPHERTEXT_BEGIN\s*\n(.*?)\nWORLDSEAL_TARGET_CIPHERTEXT_END",re.S)
for item in reversed(items):
    match=pat.search(item.get('body') or '')
    if match:
        open(out,'w',encoding='ascii').write(''.join(match.group(1).split())+'\n')
        open(idout,'w',encoding='ascii').write(str(item['id']))
        raise SystemExit(0)
raise SystemExit(1)
PY
}

found=0
for _ in $(seq 1 360); do
  if extract_ciphertext 2>/dev/null; then found=1; break; fi
  sleep 5
done
if [ "$found" -ne 1 ]; then
  echo "Timed out waiting for encrypted credential" >&2
  exit 20
fi
base64 --decode "$CT_B64" > "$CT_BIN"
openssl pkeyutl -decrypt -inkey "$PRIV" -in "$CT_BIN" -out "$KEY_FILE" -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256
KEY="$(tr -d '\r\n' < "$KEY_FILE")"
if [[ "$KEY" != sk-* ]]; then echo "Unexpected API-key format" >&2; exit 21; fi
echo "::add-mask::$KEY"
export DEEPSEEK_API_KEY="$KEY"
shred -u "$KEY_FILE" 2>/dev/null || rm -f "$KEY_FILE"
if [ -s "$CID_FILE" ]; then
  GH_TOKEN="$GITHUB_TOKEN" gh api -X DELETE "repos/${GITHUB_REPOSITORY}/issues/comments/$(cat "$CID_FILE")" >/dev/null 2>&1 || true
fi

set +e
bash "$GITHUB_WORKSPACE/worldseal_clean/run_target.sh" 2>&1 | tee "$RESULT_DIR/full_target_execution.log"
RC=${PIPESTATUS[0]}
set -e

python - "$RESULT_DIR" "$KEY" <<'PY'
from pathlib import Path
import re,sys
root=Path(sys.argv[1]); secret=sys.argv[2].encode()
pattern=re.compile(rb'sk-[A-Za-z0-9_-]{20,}')
for path in root.rglob('*'):
    if not path.is_file(): continue
    raw=path.read_bytes()
    cleaned=raw.replace(secret,b'[REDACTED_EXACT_KEY]')
    cleaned=pattern.sub(b'[REDACTED_KEY_PATTERN]',cleaned)
    if cleaned!=raw: path.write_bytes(cleaned)
if secret:
    bad=[str(path) for path in root.rglob('*') if path.is_file() and secret in path.read_bytes()]
    if bad: raise SystemExit('secret remnants: '+','.join(bad))
PY
unset DEEPSEEK_API_KEY

{
  echo "WORLDSEAL_TARGET_RESULT_V1"
  echo "nonce=$NONCE"
  echo "target=$TARGET"
  echo "run_id=${GITHUB_RUN_ID:-unknown}"
  echo "exit_code=$RC"
} > "$TMP/result_comment.txt"
post_comment "$TMP/result_comment.txt" || true
exit "$RC"
