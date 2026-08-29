from pathlib import Path

p = Path(__file__).with_name("runner.py")
s = p.read_text(encoding="utf-8")

replacements = [
    (
        'REQUEST_TIMEOUT_SEC = 60\n',
        'REQUEST_TIMEOUT_SEC = 60\nMAX_COMPLETION_TOKENS = 4096\n',
    ),
    (
        '    "provider_errors": 0,\n    "mechanical_json_wraps": 0,\n',
        '    "provider_errors": 0,\n    "provider_success_empty": 0,\n    "provider_success_nonempty": 0,\n    "finish_reasons": {},\n    "mechanical_json_wraps": 0,\n',
    ),
    (
        '                max_tokens=1024,\n            )\n            last = response.choices[0].message.content or ""\n            if last.strip():\n                return _mechanical_format_canonicalization(last)\n',
        '                max_tokens=MAX_COMPLETION_TOKENS,\n            )\n            choice = response.choices[0]\n            finish_reason = str(getattr(choice, "finish_reason", None))\n            API_STATS["finish_reasons"][finish_reason] = API_STATS["finish_reasons"].get(finish_reason, 0) + 1\n            last = choice.message.content or ""\n            if last.strip():\n                API_STATS["provider_success_nonempty"] += 1\n                return _mechanical_format_canonicalization(last)\n            API_STATS["provider_success_empty"] += 1\n',
    ),
    (
        '            "request_timeout_sec": REQUEST_TIMEOUT_SEC,\n            "mechanical_json_shell_only": True,\n',
        '            "request_timeout_sec": REQUEST_TIMEOUT_SEC,\n            "max_completion_tokens": MAX_COMPLETION_TOKENS,\n            "mechanical_json_shell_only": True,\n',
    ),
]

for old, new in replacements:
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"V2 patch expected exactly one match, got {count}: {old[:80]!r}")
    s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("Applied frozen Stage-7a V2 execution-only patch: max_tokens=4096 + empty-content telemetry")
