from pathlib import Path

root = Path('false_diversification')

# Instrumentation-only compatibility fix: with this LangChain/provider version,
# the actual DeepSeek model ID and usage may be stored in ChatResult.llm_output.
p = root / 'run_swarm.py'
s = p.read_text(encoding='utf-8')
old = '''            metadata = getattr(message, "response_metadata", {}) or {}\n            returned_model = metadata.get("model_name") or metadata.get("model")\n            raw_usage = getattr(message, "usage_metadata", None) or metadata.get("token_usage")\n'''
new = '''            metadata = getattr(message, "response_metadata", {}) or {}\n            llm_output = getattr(result, "llm_output", {}) or {}\n            returned_model = (\n                metadata.get("model_name")\n                or metadata.get("model")\n                or llm_output.get("model_name")\n                or llm_output.get("model")\n            )\n            raw_usage = (\n                getattr(message, "usage_metadata", None)\n                or metadata.get("token_usage")\n                or llm_output.get("token_usage")\n            )\n'''
if s.count(old) != 1:
    raise RuntimeError(f'expected one swarm metadata block, found {s.count(old)}')
p.write_text(s.replace(old, new, 1), encoding='utf-8')

# DeepSeek V4 Flash can spend 384 completion tokens entirely on hidden
# reasoning and return an empty JSON body. Use the experiment's pre-registered
# absolute ceiling (800) for structured baseline calls. This does not relax
# budget matching: the verifier compares ACTUAL successful calls and ACTUAL
# completion-token totals with the official MAS within +/-30%.
p = root / 'common.py'
s = p.read_text(encoding='utf-8')
old = '    per_call_max = min(800, max(180, int(target_completion * 1.35)))\n'
new = '    per_call_max = 800\n'
if s.count(old) != 1:
    raise RuntimeError(f'expected one per_call_max line, found {s.count(old)}')
p.write_text(s.replace(old, new, 1), encoding='utf-8')

print('Applied runtime patch v4: model-ID fallback and fixed 800-token JSON ceiling')
