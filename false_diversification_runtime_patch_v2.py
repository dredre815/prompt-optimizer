from pathlib import Path

root = Path('false_diversification')

# Swarm instrumentation: LangChain stores the returned model ID and usage in
# ChatResult.llm_output for this provider/version. Capture that location as a
# fallback; no trading logic or model behavior is changed.
p = root / 'run_swarm.py'
s = p.read_text(encoding='utf-8')
old = '''            metadata = getattr(message, "response_metadata", {}) or {}\n            returned_model = metadata.get("model_name") or metadata.get("model")\n            raw_usage = getattr(message, "usage_metadata", None) or metadata.get("token_usage")\n'''
new = '''            metadata = getattr(message, "response_metadata", {}) or {}\n            llm_output = getattr(result, "llm_output", {}) or {}\n            returned_model = (\n                metadata.get("model_name")\n                or metadata.get("model")\n                or llm_output.get("model_name")\n                or llm_output.get("model")\n            )\n            raw_usage = (\n                getattr(message, "usage_metadata", None)\n                or metadata.get("token_usage")\n                or llm_output.get("token_usage")\n            )\n'''
if s.count(old) != 1:
    raise RuntimeError(f'expected one swarm metadata block, found {s.count(old)}')
p.write_text(s.replace(old, new, 1), encoding='utf-8')

# DeepSeek V4 Flash may spend the whole completion allowance on reasoning and
# return an empty JSON body when the matched MAS average is very small. Raise
# only the per-call ceiling floor; fairness remains fail-closed because the
# verifier compares ACTUAL completion-token totals and call counts (±30%).
p = root / 'common.py'
s = p.read_text(encoding='utf-8')
old = '    per_call_cap = min(800, max(160, target_total // target_calls))\n'
new = '    per_call_cap = min(800, max(384, target_total // target_calls))\n'
if s.count(old) != 1:
    raise RuntimeError(f'expected one per_call_cap line, found {s.count(old)}')
p.write_text(s.replace(old, new, 1), encoding='utf-8')

print('Applied runtime patch v2: model-ID fallback and 384-token JSON ceiling floor')
