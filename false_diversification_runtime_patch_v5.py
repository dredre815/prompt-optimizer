from pathlib import Path

ROOT = Path(__file__).resolve().parent / "false_diversification"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)

# Make structured auxiliary calls reliable under DeepSeek V4. Official MAS
# calls remain in the provider's default thinking mode. Only the external
# component classifier uses non-thinking mode; matched baselines keep thinking
# enabled but receive enough output budget to emit their final JSON after CoT.
p = ROOT / "common.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    '''        retries: int = 7,\n    ) -> tuple[dict[str, Any], APICallRecord, str]:\n''',
    '''        retries: int = 7,\n        thinking_disabled: bool = False,\n    ) -> tuple[dict[str, Any], APICallRecord, str]:\n''',
    "client thinking toggle signature",
)
s = replace_once(
    s,
    '''                    response_format={"type": "json_object"},\n                )\n''',
    '''                    response_format={"type": "json_object"},\n                    extra_body={"thinking": {"type": "disabled"}} if thinking_disabled else None,\n                )\n''',
    "client thinking toggle request",
)
s = replace_once(
    s,
    '''    per_call_max = 800\n''',
    '''    # DeepSeek V4 thinking tokens share max_tokens with final content.\n    # 800 frequently exhausts the budget before any JSON content is emitted.\n    per_call_max = max(4096, min(12288, target_completion * 4))\n''',
    "baseline output budget",
)
p.write_text(s, encoding="utf-8")

p = ROOT / "run_tradingagents.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    '''    trimmed = {k: v[:6500] for k, v in components.items()}\n''',
    '''    # The classifier needs stance and source citations, not full reports.\n    # Smaller inputs remove an avoidable JSON-mode failure surface.\n    trimmed = {k: v[:2500] for k, v in components.items()}\n''',
    "judge input bound",
)
s = replace_once(
    s,
    '''    obj, _, _ = client.call(stage=f"ta_judge:{scenario['id']}:{condition}", role="component_judge", system=system, user=user, max_tokens=1800)\n''',
    '''    obj, _, _ = client.call(\n        stage=f"ta_judge:{scenario['id']}:{condition}",\n        role="component_judge",\n        system=system,\n        user=user,\n        max_tokens=4096,\n        thinking_disabled=True,\n    )\n''',
    "judge reliable JSON call",
)
p.write_text(s, encoding="utf-8")

print("Applied runtime patch v5: non-thinking evaluator and reliable baseline JSON budgets")
