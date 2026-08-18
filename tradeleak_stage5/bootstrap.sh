#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ISSUE_NUMBER="${TRADELEAK_STAGE5_ISSUE_NUMBER:-43}"; ATA_COMMIT="${ATA_COMMIT:-6b49ee837ebc1fa0d5bf99d655dc3adc352a77d3}"; NONCE="${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-$(date +%s)"
ROOT="$(mktemp -d /tmp/tl5-XXXXXX)"; PRIV="$ROOT/private.pem"; PUB="$ROOT/public.pem"; C64="$ROOT/c.b64"; CBIN="$ROOT/c.bin"; KEYF="$ROOT/key"; RESULTS="$GITHUB_WORKSPACE/tradeleak_stage5_output"; mkdir -p "$RESULTS"; rm -rf "$RESULTS"/*
cleanup(){ set +e; unset DEEPSEEK_API_KEY OPENAI_API_KEY; for f in "$KEYF" "$CBIN" "$C64" "$PRIV" "$PUB"; do [ -f "$f" ] && (shred -u "$f" 2>/dev/null || rm -f "$f"); done; rm -rf "$ROOT" 2>/dev/null||true; };trap cleanup EXIT
comment(){ GH_TOKEN="$GITHUB_TOKEN" gh issue comment "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --body-file "$1" >/dev/null; }
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$PRIV" 2>/dev/null;openssl pkey -in "$PRIV" -pubout -out "$PUB";{ echo TRADELEAK_STAGE5_PUBLIC_KEY_V1;echo "nonce=$NONCE";echo "run_id=$GITHUB_RUN_ID";echo requested_model=deepseek-v4-flash;echo "ata_commit=$ATA_COMMIT";echo TRADELEAK_STAGE5_PUBLIC_KEY_BEGIN;cat "$PUB";echo TRADELEAK_STAGE5_PUBLIC_KEY_END;} > "$ROOT/pub";comment "$ROOT/pub"
found=0;for _ in $(seq 1 360);do GH_TOKEN="$GITHUB_TOKEN" gh api "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/comments?per_page=100" --paginate > "$ROOT/comments.json";if python - "$ROOT/comments.json" "$NONCE" "$C64" "$ROOT/cid" <<'PY'
import json,re,sys
src,nonce,out,cid=sys.argv[1:];xs=json.load(open(src));p=re.compile(r'TRADELEAK_STAGE5_CIPHERTEXT_V1\s*\nnonce='+re.escape(nonce)+r'\s*\nTRADELEAK_STAGE5_CIPHERTEXT_BEGIN\s*\n(.*?)\nTRADELEAK_STAGE5_CIPHERTEXT_END',re.S)
for x in reversed(xs):
 m=p.search(x.get('body') or '')
 if m:open(out,'w').write(''.join(m.group(1).split())+'\n');open(cid,'w').write(str(x['id']));raise SystemExit(0)
raise SystemExit(1)
PY
then found=1;break;fi;sleep 5;done;[ "$found" -eq 1 ]||exit 2;base64 --decode "$C64">"$CBIN";openssl pkeyutl -decrypt -inkey "$PRIV" -in "$CBIN" -out "$KEYF" -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -pkeyopt rsa_mgf1_md:sha256
key="$(cat "$KEYF")";[[ "$key" == sk-* ]]||exit 3;echo "::add-mask::$key";export DEEPSEEK_API_KEY="$key";export OPENAI_API_KEY="$key";shred -u "$KEYF" 2>/dev/null||rm -f "$KEYF";[ -s "$ROOT/cid" ]&&GH_TOKEN="$GITHUB_TOKEN" gh api -X DELETE "repos/${GITHUB_REPOSITORY}/issues/comments/$(cat "$ROOT/cid")">/dev/null 2>&1||true
python -m pip install --quiet --upgrade pip wheel setuptools;python -m pip install --quiet 'openai>=2,<3' numpy pandas matplotlib mplfinance timeout-decorator eventlet
git clone --quiet https://github.com/MTMQuantAI/Agent-Trading-Arena.git "$ROOT/ata";git -C "$ROOT/ata" checkout --quiet "$ATA_COMMIT";export ATA_ROOT="$ROOT/ata";export TRADELEAK_STAGE5_OUT="$RESULTS";python "$GITHUB_WORKSPACE/tradeleak_stage5/runner_v2.py"|tee "$RESULTS/execution.log";echo "$ATA_COMMIT">"$RESULTS/ata_commit.txt"
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
s=json.load(open(sys.argv[1]));open(sys.argv[2],'w').write('\n'.join(['TRADELEAK_STAGE5_RESULT_V2',f"run_id={os.environ.get('GITHUB_RUN_ID')}",f"model={s['model']}",f"valid_response_rate={s['valid_response_rate']}",f"active_q={s['active_q']}",f"active_one_query_accuracy={s['active_one_query_accuracy']}",f"passive_accuracy_by_observations={json.dumps(s['passive_accuracy_by_observations'],separators=(',',':'))}",f"passive_median_events_to_90pct={s['passive_median_events_to_90pct']}",f"active_story_supported={s['active_story_supported']}",f"passive_q_distribution={json.dumps(s['passive_q_distribution'],separators=(',',':'))}"])+'\n')
PY
comment "$ROOT/res";unset DEEPSEEK_API_KEY OPENAI_API_KEY
