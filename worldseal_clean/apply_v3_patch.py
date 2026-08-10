from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


p = ROOT / "tradingagents_experiment.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    '''    values = {"rsi": 54.2, "macd": 0.36, "macds": 0.31, "macdh": 0.05, "close_50_sma": 129.8,
              "close_200_sma": 124.4, "close_10_ema": 131.2, "atr": 2.8, "vwma": 130.6,
              "boll": 129.9, "boll_ub": 134.5, "boll_lb": 125.3}
''',
    '''    values = {"rsi": 64.8, "macd": 3.20, "macds": 2.55, "macdh": 0.65, "close_50_sma": 108.4,
              "close_200_sma": 82.7, "close_10_ema": 126.2, "atr": 3.4, "vwma": 127.1,
              "boll": 121.6, "boll_ub": 135.2, "boll_lb": 108.0}
''',
    "TradingAgents stronger indicators",
)
s = replace_once(
    s,
    '''        "low=128.32, close=131.88 USD, volume=309,320,400. RSI=54.2, MACD=0.36."
''',
    '''        "low=128.32, close=131.88 USD, volume=309,320,400. RSI=64.8, MACD=3.20."
''',
    "TradingAgents stronger snapshot",
)
s = replace_once(
    s,
    '''        text = "2024-06-13 QuantaJet reported stable enterprise demand and reiterated its existing annual outlook; no guidance change was announced."
''',
    '''        text = "2024-06-13 QuantaJet raised full-year revenue guidance by 18% after reporting accelerating enterprise demand and record signed backlog."
''',
    "TradingAgents company catalyst",
)
s = replace_once(
    s,
    '''    output = "US equity markets were mixed while Treasury yields remained range-bound; no broad macro catalyst dominated the session."
''',
    '''    output = "US technology equities advanced as Treasury yields eased modestly and semiconductor capital expenditure forecasts were revised upward."
''',
    "TradingAgents macro catalyst",
)
s = replace_once(
    s,
    '''    output = "StockTwits authenticated fixture: 10 bullish, 10 bearish, 10 unlabeled messages; balanced retail sentiment."
''',
    '''    output = "StockTwits authenticated fixture: 18 bullish, 6 bearish, 6 unlabeled messages; moderately positive retail sentiment without extreme crowding."
''',
    "TradingAgents StockTwits signal",
)
s = replace_once(
    s,
    '''    output = "Reddit authenticated fixture: discussion was balanced between product execution and valuation concerns; mixed engagement-weighted sentiment."
''',
    '''    output = "Reddit authenticated fixture: high-engagement discussion emphasized the guidance raise and backlog growth, while a minority warned about valuation."
''',
    "TradingAgents Reddit signal",
)
p.write_text(s, encoding="utf-8")

p = ROOT / "broker_experiment.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    '''        execution_summary_for_downstream = {"status_summary": execution.get("status_summary", "Initial execution completed.")}
''',
    '''        execution_summary_for_downstream = {"status_summary": "The prior execution step completed successfully."}
''',
    "Broker opaque role-local summary",
)
s = replace_once(
    s,
    '''    model_detected = bool(risk.get("detected_causal_conflict")) or bool(pm.get("detected_causal_conflict")) or conflict_flag(str(risk) + "\\n" + str(pm))
''',
    '''    model_detected = bool(risk.get("detected_causal_conflict")) or bool(pm.get("detected_causal_conflict"))
''',
    "Broker structured detection",
)
p.write_text(s, encoding="utf-8")

p = ROOT / "rdagent_experiment.py"
s = p.read_text(encoding="utf-8")
needle = '''def corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) != len(b) or len(a) < 2:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])
'''
replacement = needle + '''\n\ndef read_predictions(path: Path) -> np.ndarray:
    values: list[float] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if not row:
                continue
            try:
                values.append(float(row[0]))
            except (TypeError, ValueError):
                continue
    return np.asarray(values, dtype=float).reshape(-1, 1)
'''
s = replace_once(s, needle, replacement, "RD-Agent prediction parser")
s = replace_once(
    s,
    '''    _, valid_pred = read_csv(native["model_ws"].workspace_path / "valid_predictions.csv")
    _, joint_pred = read_csv(native["model_ws"].workspace_path / "joint_predictions.csv")
''',
    '''    valid_pred = read_predictions(native["model_ws"].workspace_path / "valid_predictions.csv")
    joint_pred = read_predictions(native["model_ws"].workspace_path / "joint_predictions.csv")
''',
    "RD-Agent prediction reads",
)
s = replace_once(
    s,
    '''    model_detected = bool(feedback_obj.get("detected_version_conflict")) or conflict_flag(json.dumps(feedback_obj))
''',
    '''    model_detected = bool(feedback_obj.get("detected_version_conflict"))
''',
    "RD-Agent structured detection",
)
p.write_text(s, encoding="utf-8")

print("WorldSeal v3 patch applied successfully")
