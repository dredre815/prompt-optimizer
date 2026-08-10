#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$GITHUB_WORKSPACE"
OUT="$ROOT/worldseal_output"
mkdir -p "$OUT" "$ROOT/repos"
python -m pip install --upgrade pip wheel setuptools
python -m pip install 'openai>=1.75,<2' 'httpx>=0.28,<1' 'numpy>=1.26,<3' 'pandas>=2.2,<3' 'scipy>=1.13,<2' 'scikit-learn>=1.5,<2' 'pydantic>=2.10,<3' 'pydantic-settings>=2.7,<3' python-dotenv requests filelock loguru fire fuzzywuzzy python-Levenshtein pyarrow rich tqdm typer matplotlib tables langchain langchain-community tiktoken litellm
clone_pin() {
  local slug="$1" dir="$2" sha="$3"
  rm -rf "$dir"
  git clone --filter=blob:none --no-checkout "https://github.com/$slug.git" "$dir"
  git -C "$dir" fetch --depth=1 origin "$sha"
  git -C "$dir" checkout --detach "$sha"
}
clone_pin TauricResearch/TradingAgents "$ROOT/repos/TradingAgents" a33fd4c0f134485a43553a2c23a63cb14adbd88f
clone_pin zhound420/swarm-trader "$ROOT/repos/swarm-trader" 3470b8291c438dc36b22ed37b7e56ba2bbf249b5
clone_pin microsoft/RD-Agent "$ROOT/repos/RD-Agent" 6762f84f9bc0f5c6486c50a00e128a57ac6c3683
python -m pip install -e "$ROOT/repos/TradingAgents"
python -m pip install -e "$ROOT/repos/RD-Agent" --no-deps
python "$ROOT/worldseal_clean/smoke.py"
