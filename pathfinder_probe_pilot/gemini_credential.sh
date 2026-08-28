#!/usr/bin/env bash
set -Eeuo pipefail
set +x
umask 077

ISSUE_NUMBER="${PATHFINDER_ISSUE_NUMBER:?required}"
NONCE="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-pathfinder-$(date +%s)-$RANDOM"
TMP="$(mktemp -d /tmp/pathfinder-gemini-key-XXXXXX)"
PRIV="$TMP/private.pem"
PUB="$TMP/public.pem"
CT_B64="$TMP/ciphertext.b64"
CT_BIN="$TMP/ciphertext.bin"
KEY_FILE="$TMP/gemini.key"
CID_FILE="$TMP/comment_id"
RUNNER="$TMP/run_dual_pilot.py"
LAUNCHER="$TMP/launch_safe.py"
OUT="$GITHUB_WORKSPACE/pathfinder_probe_pilot/output"
rm -rf "$OUT"
mkdir -p "$OUT"

cleanup(){
  set +e
  unset GEMINI_API_KEY
  for f in "$KEY_FILE" "$CT_BIN" "$CT_B64" "$PRIV" "$PUB" "$RUNNER" "$LAUNCHER"; do
    [ -f "$f" ] && (shred -u "$f" 2>/dev/null || rm -f "$f")
  done
  rm -rf "$TMP"
}
trap cleanup EXIT

post_comment(){
  GH_TOKEN="$GITHUB_TOKEN" gh issue comment "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --body-file "$1" >/dev/null
}

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "$PRIV" 2>/dev/null
openssl pkey -in "$PRIV" -pubout -out "$PUB"
{
  echo PATHFINDER_GEMINI_PUBLIC_KEY_V1
  echo "nonce=$NONCE"
  echo "run_id=${GITHUB_RUN_ID:-unknown}"
  echo PATHFINDER_GEMINI_PUBLIC_KEY_BEGIN
  cat "$PUB"
  echo PATHFINDER_GEMINI_PUBLIC_KEY_END
} > "$TMP/public_comment.txt"
post_comment "$TMP/public_comment.txt"

authoritative_ciphertext(){
  GH_TOKEN="$GITHUB_TOKEN" gh api "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}/comments?per_page=100" --paginate > "$TMP/comments.json"
  python - "$TMP/comments.json" "$NONCE" "$CT_B64" "$CID_FILE" <<'PY'
import json,re,sys
source,nonce,out,idout=sys.argv[1:]
items=json.load(open(source,encoding='utf-8'))
pat=re.compile(
    r"PATHFINDER_GEMINI_CIPHERTEXT_V1\s*\nnonce="+re.escape(nonce)+
    r"\s*\nPATHFINDER_GEMINI_CIPHERTEXT_BEGIN\s*\n(.*?)\nPATHFINDER_GEMINI_CIPHERTEXT_END",
    re.S,
)
for item in reversed(items):
    m=pat.search(item.get('body') or '')
    if m:
        open(out,'w',encoding='ascii').write(''.join(m.group(1).split())+'\n')
        open(idout,'w').write(str(item['id']))
        raise SystemExit(0)
raise SystemExit(1)
PY
}

found=0
for _ in $(seq 1 360); do
  if authoritative_ciphertext 2>/dev/null; then found=1; break; fi
  sleep 5
done
[ "$found" -eq 1 ] || { echo "Timed out waiting for encrypted Gemini credential" >&2; exit 20; }

base64 --decode "$CT_B64" > "$CT_BIN"
openssl pkeyutl -decrypt -inkey "$PRIV" -in "$CT_BIN" -out "$KEY_FILE" \
  -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256
KEY="$(tr -d '\r\n' < "$KEY_FILE")"
[ "${#KEY}" -ge 30 ] || { echo "Decrypted credential is unexpectedly short" >&2; exit 21; }
echo "::add-mask::$KEY"
export GEMINI_API_KEY="$KEY"
shred -u "$KEY_FILE" 2>/dev/null || rm -f "$KEY_FILE"

if [ -s "$CID_FILE" ]; then
  GH_TOKEN="$GITHUB_TOKEN" gh api -X DELETE "repos/${GITHUB_REPOSITORY}/issues/comments/$(cat "$CID_FILE")" >/dev/null 2>&1 || true
fi

# Reconstruct and verify the frozen v4 dual-dataset runner.
base64 --decode "$GITHUB_WORKSPACE/pathfinder_probe_pilot/run_dual_pilot.py.gz.b64" | gzip -dc > "$RUNNER"
echo '5bbfa4830da6ba60414b440dc73eb103f1c1b720faea4692b1c2628ccf5106e8  '"$RUNNER" | sha256sum --check --strict
python -m py_compile "$RUNNER"

# The v4 runner originally generated all 21 template relation specs in one
# Gemini request. That request was reproducibly disconnected server-side after
# ~4.5 minutes. Load the frozen runner as a module and replace only that call
# with one-relation-at-a-time execution. All prompts, schemas, validation,
# matching rules, target order, and downstream logic remain unchanged.
cat > "$LAUNCHER" <<'PY'
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path

runner_path=Path(sys.argv[1])
out_dir=sys.argv[2]
spec=importlib.util.spec_from_file_location('pathfinder_dual_frozen', runner_path)
mod=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
orig=mod.gemini_template_bank

def safe_template_bank(client, specs, raw_path):
    specs=list(specs)
    if len(specs)<=1:
        return orig(client, specs, raw_path)
    raw_path=Path(raw_path)
    print(f'[safe template bank] splitting {len(specs)} relation specs into singleton Gemini calls', flush=True)
    results=[]
    part_paths=[]
    for i,one in enumerate(specs,1):
        part=raw_path.with_name(f'{raw_path.stem}.part{i:02d}{raw_path.suffix or ".json"}')
        print(f'[safe template bank {i}/{len(specs)}]', flush=True)
        results.append(orig(client,[one],part))
        part_paths.append(str(part.name))
    if all(isinstance(r,list) for r in results):
        merged=[x for r in results for x in r]
    elif all(isinstance(r,dict) for r in results):
        merged={}
        for r in results:
            for k,v in r.items():
                if isinstance(v,list): merged.setdefault(k,[]).extend(v)
                elif k not in merged: merged[k]=v
                elif merged[k]!=v: merged[k]=v
    else:
        raise TypeError(f'Unexpected mixed template-bank return types: {[type(r).__name__ for r in results]}')
    raw_path.write_text(json.dumps({'split_singleton_execution':True,'parts':part_paths},indent=2),encoding='utf-8')
    return merged

mod.gemini_template_bank=safe_template_bank
sys.argv=[str(runner_path),'--rwku-pool','200','--tofu-pool','200','--targets','20','--out-dir',out_dir]
mod.main()
PY
python -m py_compile "$LAUNCHER"

set +e
python "$LAUNCHER" "$RUNNER" "$OUT" 2>&1 | tee "$OUT/execution.log"
RC=${PIPESTATUS[0]}
set -e

python - "$OUT" "$KEY" <<'PY'
from pathlib import Path
import re,sys
root=Path(sys.argv[1]); secret=sys.argv[2].encode()
patterns=[
    re.compile(rb'AQ\.[A-Za-z0-9_-]{20,}'),
    re.compile(rb'AIza[A-Za-z0-9_-]{20,}'),
]
for p in root.rglob('*'):
    if not p.is_file():
        continue
    raw=p.read_bytes()
    new=raw.replace(secret,b'[REDACTED_EXACT_GEMINI_KEY]')
    for pat in patterns:
        new=pat.sub(b'[REDACTED_GEMINI_KEY_PATTERN]',new)
    if new!=raw:
        p.write_bytes(new)
for p in root.rglob('*'):
    if p.is_file() and secret in p.read_bytes():
        raise SystemExit(f'secret remnant in {p}')
PY
unset GEMINI_API_KEY
KEY=''

{
  echo PATHFINDER_GEMINI_RESULT_V5
  echo "nonce=$NONCE"
  echo "run_id=${GITHUB_RUN_ID:-unknown}"
  echo "exit_code=$RC"
  if [ -f "$OUT/RESULTS.md" ]; then
    echo
    cat "$OUT/RESULTS.md"
  fi
} > "$TMP/result.txt"
post_comment "$TMP/result.txt" || true
exit "$RC"
