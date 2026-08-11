from pathlib import Path

root = Path('false_diversification')
p = root / 'run_swarm.py'
s = p.read_text(encoding='utf-8')
old = '''            metadata = getattr(message, "response_metadata", {}) or {}\n            returned_model = metadata.get("model_name") or metadata.get("model")\n            raw_usage = getattr(message, "usage_metadata", None) or metadata.get("token_usage")\n'''
new = '''            metadata = getattr(message, "response_metadata", {}) or {}\n            llm_output = getattr(result, "llm_output", {}) or {}\n            returned_model = (\n                metadata.get("model_name")\n                or metadata.get("model")\n                or llm_output.get("model_name")\n                or llm_output.get("model")\n            )\n            raw_usage = (\n                getattr(message, "usage_metadata", None)\n                or metadata.get("token_usage")\n                or llm_output.get("token_usage")\n            )\n'''
if s.count(old) != 1:
    raise RuntimeError(f'expected one swarm metadata block, found {s.count(old)}')
p.write_text(s.replace(old, new, 1), encoding='utf-8')
print('Applied runtime patch v1: capture ChatResult.llm_output model identity')
