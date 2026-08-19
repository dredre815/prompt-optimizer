#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ISSUE_NUMBER="${TRADELEAK_STAGE6C_ISSUE_NUMBER:-60}"; ATA_COMMIT="${ATA_COMMIT:-6b49ee837ebc1fa0d5bf99d655dc3adc352a77d3}"; NONCE="${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-$(date +%s)"
ROOT="$(mktemp -d /tmp/tl6c-XXXXXX)"; PRIV="$ROOT/private.pem"; PUB="$ROOT/public.pem"; CHEX="$ROOT/c.hex"; CBIN="$ROOT/c.bin"; KEYF="$ROOT/key"; RESULTS="$GITHUB_WORKSPACE/tradeleak_stage6c_output"; mkdir -p "$RESULTS"; rm -rf "$RESULTS"/*
cleanup(){ set +e; unset DEEPSEEK_API_KEY OPENAI_API_KEY; for f in "$KEYF" "$CBIN" "$CHEX" "$PRIV" "$PUB"; do [ -f "$f" ] && (shred -u "$f" 2>/dev/null || rm -f "$f"); done; rm -rf "$ROOT" 2>/dev/null||true; };trap cleanup EXIT
comment(){ GH_TOKEN="$GITHUB_TOKEN" gh issue comment "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --body-file "$1" >/dev/null; }
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$PRIV" 2>/dev/null;openssl pkey -in "$PRIV" -pubout -out "$PUB";{ echo TRADELEAK_STAGE6C_PUBLIC_KEY_V2;echo "nonce=$NONCE";echo "run_id=$GITHUB_RUN_ID";echo requested_model=deepseek-v4-flash;echo "ata_commit=$ATA_COMMIT";echo TRADELEAK_STAGE6C_PUBLIC_KEY_BEGIN;cat "$PUB";echo TRADELEAK_STAGE6C_PUBLIC_KEY_END;} > "$ROOT/pub";comment "$ROOT/pub"
found=0;for _ in $(seq 1 360);do GH_TOKEN="$GITHUB_TOKEN" gh api "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/comments?per_page=100" --paginate > "$ROOT/comments.json";if python - "$ROOT/comments.json" "$NONCE" "$CHEX" "$ROOT/cids" <<'PY'
import json,re,sys
src,nonce,out,cids=sys.argv[1:];xs=json.load(open(src));parts=[];ids=[]
for i in range(8):
 p=re.compile(r'^TRADELEAK_STAGE6C_CHUNK_V2\s*\nnonce='+re.escape(nonce)+r'\s*\nindex='+str(i)+r'\s*\ndata=([0-9a-fA-F]{128})\s*$',re.M)
 hit=None
 for x in reversed(xs):
  m=p.search(x.get('body') or '')
  if m:hit=(m.group(1),x['id']);break
 if hit is None:raise SystemExit(1)
 parts.append(hit[0]);ids.append(str(hit[1]))
h=''.join(parts)
if len(h)!=1024:raise SystemExit(1)
open(out,'w').write(h+'\n');open(cids,'w').write('\n'.join(ids)+'\n')
PY
then found=1;break;fi;sleep 5;done;[ "$found" -eq 1 ]||exit 2;[ "$(tr -d '\n\r ' < "$CHEX" | wc -c)" -eq 1024 ]||exit 4;xxd -r -p "$CHEX">"$CBIN";[ "$(wc -c < "$CBIN")" -eq 512 ]||exit 5;openssl pkeyutl -decrypt -inkey "$PRIV" -in "$CBIN" -out "$KEYF" -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -pkeyopt rsa_mgf1_md:sha256
key="$(cat "$KEYF")";[[ "$key" == sk-* ]]||exit 3;echo "::add-mask::$key";export DEEPSEEK_API_KEY="$key";export OPENAI_API_KEY="$key";shred -u "$KEYF" 2>/dev/null||rm -f "$KEYF";while read -r cid;do [ -n "$cid" ]&&GH_TOKEN="$GITHUB_TOKEN" gh api -X DELETE "repos/${GITHUB_REPOSITORY}/issues/comments/$cid">/dev/null 2>&1||true;done<"$ROOT/cids"
python -m pip install --quiet --upgrade pip wheel setuptools;python -m pip install --quiet 'openai>=2,<3' numpy pandas matplotlib mplfinance timeout-decorator eventlet
git clone --quiet https://github.com/MTMQuantAI/Agent-Trading-Arena.git "$ROOT/ata";git -C "$ROOT/ata" checkout --quiet "$ATA_COMMIT";export ATA_ROOT="$ROOT/ata";export TRADELEAK_STAGE6C_OUT="$RESULTS";python "$GITHUB_WORKSPACE/tradeleak_stage6c/runner.py"|tee "$RESULTS/execution.log";echo "$ATA_COMMIT">"$RESULTS/ata_commit.txt"
python - "$RESULTS" "$key" <<'PY'
from pathlib import Path
import re,sys
r=Path(sys.argv[1]);k=sys.argv[2].encode();p=re.compile(rb'sk-[A-Za-z0-9_-]{12,}')
for f in r.rglob('*'):
 if f.is_file():
  b=f.read_bytes();n=b.replace(k,b'[REDACTED]') if k else b;n=p.sub(b'[REDACTED_KEY]',n)
  if n!=b:f.write_bytes(n)
PY
python - "$RESULTS/summary.json" "$ROOT/res" <<'PY'
import json,sys,os
s=json.load(open(sys.argv[1]));open(sys.argv[2],'w').write('\n'.join(['TRADELEAK_STAGE6C_RESULT_V1',f"run_id={os.environ.get('GITHUB_RUN_ID')}",f"model={s['model']}",f"valid_response_rate={s['valid_response_rate']}",f"passed_pairs={json.dumps(s['passed_pairs'],separators=(',',':'))}",f"mean_activation_gain={json.dumps(s['mean_activation_gain'],separators=(',',':'))}",f"success_pairs={json.dumps(s['success_pairs'],separators=(',',':'))}",f"activation_supported={s['activation_supported']}"])+'\n')
PY
comment "$ROOT/res";unset DEEPSEEK_API_KEY OPENAI_API_KEY
