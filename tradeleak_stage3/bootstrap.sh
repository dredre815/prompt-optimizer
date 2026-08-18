#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ISSUE_NUMBER="${TRADELEAK_STAGE3_ISSUE_NUMBER:-35}"
ATA_COMMIT="${ATA_COMMIT:-6b49ee837ebc1fa0d5bf99d655dc3adc352a77d3}"
NONCE="${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-$(date +%s)"
ROOT="$(mktemp -d /tmp/tl3-XXXXXX)"; PRIV="$ROOT/private.pem"; PUB="$ROOT/public.pem"; C64="$ROOT/cipher.b64"; CBIN="$ROOT/cipher.bin"; KEYF="$ROOT/key.txt"
RESULTS="$GITHUB_WORKSPACE/tradeleak_stage3_output"; mkdir -p "$RESULTS"; rm -rf "$RESULTS"/*
cleanup(){ set +e; unset DEEPSEEK_API_KEY OPENAI_API_KEY; for f in "$KEYF" "$CBIN" "$C64" "$PRIV" "$PUB"; do [ -f "$f" ] && (shred -u "$f" 2>/dev/null || rm -f "$f"); done; rm -rf "$ROOT" 2>/dev/null || true; }; trap cleanup EXIT
comment(){ GH_TOKEN="$GITHUB_TOKEN" gh issue comment "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --body-file "$1" >/dev/null; }
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$PRIV" 2>/dev/null; openssl pkey -in "$PRIV" -pubout -out "$PUB"
{ echo TRADELEAK_STAGE3_PUBLIC_KEY_V1; echo "nonce=$NONCE"; echo "run_id=$GITHUB_RUN_ID"; echo requested_model=deepseek-v4-flash; echo "ata_commit=$ATA_COMMIT"; echo TRADELEAK_STAGE3_PUBLIC_KEY_BEGIN; cat "$PUB"; echo TRADELEAK_STAGE3_PUBLIC_KEY_END; } > "$ROOT/pub.txt"; comment "$ROOT/pub.txt"
found=0
for _ in $(seq 1 360); do
 GH_TOKEN="$GITHUB_TOKEN" gh api "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/comments?per_page=100" --paginate > "$ROOT/comments.json"
 if python - "$ROOT/comments.json" "$NONCE" "$C64" "$ROOT/cid" <<'PY'
import json,re,sys
src,nonce,out,cid=sys.argv[1:]; comments=json.load(open(src))
pat=re.compile(r'TRADELEAK_STAGE3_CIPHERTEXT_V1\s*\nnonce='+re.escape(nonce)+r'\s*\nTRADELEAK_STAGE3_CIPHERTEXT_BEGIN\s*\n(.*?)\nTRADELEAK_STAGE3_CIPHERTEXT_END',re.S)
for x in reversed(comments):
 m=pat.search(x.get('body') or '')
 if m: open(out,'w').write(''.join(m.group(1).split())+'\n'); open(cid,'w').write(str(x['id'])); raise SystemExit(0)
raise SystemExit(1)
PY
 then found=1; break; fi; sleep 5
done
[ "$found" -eq 1 ] || { echo 'Timed out waiting for encrypted credential'; exit 2; }
base64 --decode "$C64" > "$CBIN"; openssl pkeyutl -decrypt -inkey "$PRIV" -in "$CBIN" -out "$KEYF" -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -pkeyopt rsa_mgf1_md:sha256
key="$(cat "$KEYF")"; [[ "$key" == sk-* ]] || exit 3; echo "::add-mask::$key"; export DEEPSEEK_API_KEY="$key"; export OPENAI_API_KEY="$key"; shred -u "$KEYF" 2>/dev/null || rm -f "$KEYF"
[ -s "$ROOT/cid" ] && GH_TOKEN="$GITHUB_TOKEN" gh api -X DELETE "repos/${GITHUB_REPOSITORY}/issues/comments/$(cat "$ROOT/cid")" >/dev/null 2>&1 || true
python -m pip install --quiet --upgrade pip wheel setuptools; python -m pip install --quiet 'openai>=2,<3' numpy pandas matplotlib mplfinance timeout-decorator eventlet
git clone --quiet https://github.com/MTMQuantAI/Agent-Trading-Arena.git "$ROOT/ata"; git -C "$ROOT/ata" checkout --quiet "$ATA_COMMIT"; echo "$ATA_COMMIT" > "$RESULTS/ata_commit.txt"
export ATA_ROOT="$ROOT/ata"; export TRADELEAK_STAGE3_OUT="$RESULTS"; python "$GITHUB_WORKSPACE/tradeleak_stage3/runner.py" | tee "$RESULTS/execution.log"
python - "$RESULTS" "$key" <<'PY'
from pathlib import Path
import re,sys
root=Path(sys.argv[1]); key=sys.argv[2].encode(); pat=re.compile(rb'sk-[A-Za-z0-9_-]{12,}')
for p in root.rglob('*'):
 if p.is_file():
  b=p.read_bytes(); n=b.replace(key,b'[REDACTED]') if key else b; n=pat.sub(b'[REDACTED_KEY]',n)
  if n!=b:p.write_bytes(n)
PY
python - "$RESULTS/summary.json" "$ROOT/result.txt" <<'PY'
import json,sys
s=json.load(open(sys.argv[1])); lines=['TRADELEAK_STAGE3_RESULT_V1',f"run_id={__import__('os').environ.get('GITHUB_RUN_ID')}",f"model={s['model']}",f"valid_response_rate={s['valid_response_rate']}",f"thresholds={json.dumps(s['thresholds'],separators=(',',':'))}"]
for pair,m in s['metrics'].items():
 vals={str(q):{'acc':round(v['accuracy'],4),'impact':round(v['impact_pct'],4),'cost':round(v['probe_cost'],2)} for q,v in m.items()}
 lines.append(f"{pair}={json.dumps(vals,separators=(',',':'))}")
open(sys.argv[2],'w').write('\n'.join(lines)+'\n')
PY
comment "$ROOT/result.txt"; unset DEEPSEEK_API_KEY OPENAI_API_KEY