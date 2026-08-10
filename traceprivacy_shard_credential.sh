#!/usr/bin/env bash
set -Eeuo pipefail
set +x
umask 077
ISSUE_NUMBER="${TRACEPRIVACY_ISSUE_NUMBER:?required}"
TARGET="${TRACEPRIVACY_TARGET:?required}"
SCENARIO="${TRACEPRIVACY_SCENARIO_ID:?required}"
NONCE="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-${TARGET}-${SCENARIO}-$(date +%s)-$RANDOM"
TMP="$(mktemp -d /tmp/traceprivacy-shard-key-XXXXXX)"
PRIV="$TMP/private.pem"; PUB="$TMP/public.pem"; CT_B64="$TMP/ciphertext.b64"; CT_BIN="$TMP/ciphertext.bin"; KEY_FILE="$TMP/deepseek.key"; CID_FILE="$TMP/comment_id"
OUT="$GITHUB_WORKSPACE/traceprivacy_output"; mkdir -p "$OUT"
cleanup(){ set +e; unset DEEPSEEK_API_KEY; for f in "$KEY_FILE" "$CT_BIN" "$CT_B64" "$PRIV" "$PUB"; do [ -f "$f" ] && (shred -u "$f" 2>/dev/null || rm -f "$f"); done; rm -rf "$TMP"; }
trap cleanup EXIT
post_comment(){ GH_TOKEN="$GITHUB_TOKEN" gh issue comment "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --body-file "$1" >/dev/null; }
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$PRIV" 2>/dev/null
openssl pkey -in "$PRIV" -pubout -out "$PUB"
{
 echo TRACEPRIVACY_SHARD_PUBLIC_KEY_V1; echo "nonce=$NONCE"; echo "target=$TARGET"; echo "scenario=$SCENARIO"; echo "run_id=${GITHUB_RUN_ID:-unknown}"; echo TRACEPRIVACY_SHARD_PUBLIC_KEY_BEGIN; cat "$PUB"; echo TRACEPRIVACY_SHARD_PUBLIC_KEY_END;
} > "$TMP/public_comment.txt"
post_comment "$TMP/public_comment.txt"
extract_ciphertext(){ GH_TOKEN="$GITHUB_TOKEN" gh api "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/comments?per_page=100" --paginate > "$TMP/comments.json"; python - "$TMP/comments.json" "$NONCE" "$CT_B64" "$CID_FILE" <<'PY'
import json,re,sys
source,nonce,out,idout=sys.argv[1:]
items=json.load(open(source,encoding='utf-8'))
pat=re.compile(r"TRACEPRIVACY_SHARD_CIPHERTEXT_V1\s*\nnonce="+re.escape(nonce)+r"\s*\nTRACEPRIVACY_SHARD_CIPHERTEXT_BEGIN\s*\n(.*?)\nTRACEPRIVACY_SHARD_CIPHERTEXT_END",re.S)
for item in reversed(items):
 m=pat.search(item.get('body') or '')
 if m:
  open(out,'w',encoding='ascii').write(''.join(m.group(1).split())+'\n'); open(idout,'w').write(str(item['id'])); raise SystemExit(0)
raise SystemExit(1)
PY
}
found=0; for _ in $(seq 1 360); do if extract_ciphertext 2>/dev/null; then found=1; break; fi; sleep 5; done
[ "$found" -eq 1 ] || { echo timed-out >&2; exit 20; }
base64 --decode "$CT_B64" > "$CT_BIN"
openssl pkeyutl -decrypt -inkey "$PRIV" -in "$CT_BIN" -out "$KEY_FILE" -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256
KEY="$(tr -d '\r\n' < "$KEY_FILE")"; [[ "$KEY" == sk-* ]] || exit 21; echo "::add-mask::$KEY"; export DEEPSEEK_API_KEY="$KEY"; shred -u "$KEY_FILE" 2>/dev/null || rm -f "$KEY_FILE"
[ -s "$CID_FILE" ] && GH_TOKEN="$GITHUB_TOKEN" gh api -X DELETE "repos/${GITHUB_REPOSITORY}/issues/comments/$(cat "$CID_FILE")" >/dev/null 2>&1 || true
set +e
python "$GITHUB_WORKSPACE/traceprivacy_shard_runner.py" --target "$TARGET" --scenario-id "$SCENARIO" --output "$OUT" --tradingagents-repo "$GITHUB_WORKSPACE/repos/TradingAgents" --swarm-repo "$GITHUB_WORKSPACE/repos/swarm-trader" 2>&1 | tee "$OUT/execution.log"
RC=${PIPESTATUS[0]}; set -e
python - "$OUT" "$KEY" <<'PY'
from pathlib import Path
import re,sys
root=Path(sys.argv[1]); secret=sys.argv[2].encode(); pat=re.compile(rb'sk-[A-Za-z0-9_-]{20,}')
for p in root.rglob('*'):
 if not p.is_file(): continue
 raw=p.read_bytes(); new=pat.sub(b'[REDACTED_KEY_PATTERN]',raw.replace(secret,b'[REDACTED_EXACT_KEY]'))
 if new!=raw: p.write_bytes(new)
if any(secret in p.read_bytes() for p in root.rglob('*') if p.is_file()): raise SystemExit('secret remnant')
PY
unset DEEPSEEK_API_KEY
{ echo TRACEPRIVACY_SHARD_RESULT_V1; echo "nonce=$NONCE"; echo "target=$TARGET"; echo "scenario=$SCENARIO"; echo "exit_code=$RC"; } > "$TMP/result.txt"; post_comment "$TMP/result.txt" || true
exit "$RC"
