#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ISSUE_NUMBER="${TRADELEAK_STAGE7_ISSUE_NUMBER:-55}"; ATA_COMMIT="${ATA_COMMIT:-6b49ee837ebc1fa0d5bf99d655dc3adc352a77d3}"; NONCE="${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-$(date +%s)"
ROOT="$(mktemp -d /tmp/tl7-XXXXXX)"; PRIV="$ROOT/private.pem"; PUB="$ROOT/public.pem"; CHEX="$ROOT/c.hex"; CBIN="$ROOT/c.bin"; KEYF="$ROOT/key"; RESULTS="$GITHUB_WORKSPACE/tradeleak_stage7_output"; mkdir -p "$RESULTS"; rm -rf "$RESULTS"/*
cleanup(){ set +e; unset DEEPSEEK_API_KEY OPENAI_API_KEY; for f in "$KEYF" "$CBIN" "$CHEX" "$PRIV" "$PUB"; do [ -f "$f" ] && (shred -u "$f" 2>/dev/null || rm -f "$f"); done; rm -rf "$ROOT" 2>/dev/null||true; };trap cleanup EXIT
comment(){ GH_TOKEN="$GITHUB_TOKEN" gh issue comment "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --body-file "$1" >/dev/null; }
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$PRIV" 2>/dev/null;openssl pkey -in "$PRIV" -pubout -out "$PUB";{ echo TRADELEAK_STAGE7_PUBLIC_KEY_V2;echo "nonce=$NONCE";echo "run_id=$GITHUB_RUN_ID";echo requested_model=deepseek-v4-flash;echo "ata_commit=$ATA_COMMIT";echo TRADELEAK_STAGE7_PUBLIC_KEY_BEGIN;cat "$PUB";echo TRADELEAK_STAGE7_PUBLIC_KEY_END;} > "$ROOT/pub";comment "$ROOT/pub"
found=0;for _ in $(seq 1 360);do GH_TOKEN="$GITHUB_TOKEN" gh api "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/comments?per_page=100" --paginate > "$ROOT/comments.json";if python - "$ROOT/comments.json" "$NONCE" "$CHEX" "$ROOT/cid" <<'PY'
import json,re,sys
src,nonce,out,cid=sys.argv[1:];xs=json.load(open(src));head=re.compile(r'TRADELEAK_STAGE7_CIPHERTEXT_CHUNKS_V2\s*\nnonce='+re.escape(nonce)+r'\s*\n')
for x in reversed(xs):
 b=x.get('body') or ''
 if not head.search(b):continue
 parts=[];ok=True
 for i in range(8):
  m=re.search(r'^chunk%d=([0-9a-fA-F]{128})$'%i,b,re.M)
  if not m:ok=False;break
  parts.append(m.group(1))
 if not ok:continue
 h=''.join(parts)
 if len(h)!=1024:continue
 open(out,'w').write(h+'\n');open(cid,'w').write(str(x['id']));raise SystemExit(0)
raise SystemExit(1)
PY
then found=1;break;fi;sleep 5;done;[ "$found" -eq 1 ]||exit 2;[ "$(tr -d '\n\r ' < "$CHEX" | wc -c)" -eq 1024 ]||exit 4;xxd -r -p "$CHEX">"$CBIN";[ "$(wc -c < "$CBIN")" -eq 512 ]||exit 5;openssl pkeyutl -decrypt -inkey "$PRIV" -in "$CBIN" -out "$KEYF" -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -pkeyopt rsa_mgf1_md:sha256
key="$(cat "$KEYF")";[[ "$key" == sk-* ]]||exit 3;echo "::add-mask::$key";export DEEPSEEK_API_KEY="$key";export OPENAI_API_KEY="$key";shred -u "$KEYF" 2>/dev/null||rm -f "$KEYF";[ -s "$ROOT/cid" ]&&GH_TOKEN="$GITHUB_TOKEN" gh api -X DELETE "repos/${GITHUB_REPOSITORY}/issues/comments/$(cat "$ROOT/cid")">/dev/null 2>&1||true
python -m pip install --quiet --upgrade pip wheel setuptools;python -m pip install --quiet -r <(curl -fsSL https://raw.githubusercontent.com/MTMQuantAI/Agent-Trading-Arena/${ATA_COMMIT}/decoupledmarket/requirements.txt)
git clone --quiet https://github.com/MTMQuantAI/Agent-Trading-Arena.git "$ROOT/ata";git -C "$ROOT/ata" checkout --quiet "$ATA_COMMIT";export ATA_ROOT="$ROOT/ata";export TRADELEAK_STAGE7_OUT="$RESULTS";python "$GITHUB_WORKSPACE/tradeleak_stage7/runner.py"|tee "$RESULTS/execution.log";echo "$ATA_COMMIT">"$RESULTS/ata_commit.txt"
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
s=json.load(open(sys.argv[1]));open(sys.argv[2],'w').write('\n'.join(['TRADELEAK_STAGE7_RESULT_V1',f"run_id={os.environ.get('GITHUB_RUN_ID')}",f"verdict={s['verdict']}",f"model={s['model']}",f"valid_response_rate={s['valid_response_rate']}",f"memory_on_recovery_auc={s['memory_on_recovery']['auc']}",f"memory_off_recovery_auc={s['memory_off_recovery']['auc']}",f"recovery_auc_delta={s['recovery_auc_delta']}",f"memory_on_overall_auc={s['memory_on_overall']['auc']}",f"memory_off_overall_auc={s['memory_off_overall']['auc']}"])+'\n')
PY
comment "$ROOT/res";unset DEEPSEEK_API_KEY OPENAI_API_KEY
