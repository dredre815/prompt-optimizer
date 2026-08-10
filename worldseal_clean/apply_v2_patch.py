from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# common.py: require explicit relation-level conflict language. Mere mentions of
# a split, pre/post bases, versions, or schemas are not themselves detections.
p = ROOT / "common.py"
s = p.read_text(encoding="utf-8")
start = s.index("CONFLICT_TERMS = [")
s = s[:start] + '''CONFLICT_PATTERNS = [
    r"\\bbasis\\s+(?:mismatch|conflict|inconsisten(?:t|cy)|not comparable)",
    r"\\b(?:mixed|different|incompatible)\\s+(?:data\\s+)?basis",
    r"\\b(?:must|need(?:s)?\\s+to|should)\\s+(?:be\\s+)?normaliz(?:e|ed|ation)",
    r"\\b(?:cannot|must not|should not)\\s+be\\s+(?:directly\\s+)?(?:combined|compared)",
    r"\\b(?:reconcile|resolve|verify)\\b.{0,100}\\b(?:basis|version|schema|split|share count|eps)",
    r"\\b(?:schema|version)\\s+(?:mismatch|conflict|inconsisten(?:t|cy))",
    r"\\bstale\\s+(?:portfolio\\s+)?snapshot",
    r"\\bmissing\\s+(?:an?\\s+)?(?:acknowledged\\s+)?fill",
    r"\\bdoes\\s+not\\s+include\\b.{0,80}\\bfill",
    r"\\bcausal\\s+(?:conflict|inconsisten(?:t|cy)|violation)",
    r"\\bjoint[- ]view\\s+(?:conflict|inconsisten(?:t|cy)|violation|invalid)",
    r"\\bdata\\s+(?:mismatch|conflict|inconsisten(?:t|cy)|discrepancy)",
]


def conflict_flag(text: str) -> bool:
    lower = (text or "").lower()
    return any(re.search(pattern, lower, flags=re.S) for pattern in CONFLICT_PATTERNS)
'''
p.write_text(s, encoding="utf-8")

# TradingAgents: keep the official graph untouched and replace only external
# I/O fixtures. The clean and opaque conditions have identical ordinary-text
# structure; their incompatible bases exist only in TEE-side capsules.
p = ROOT / "tradingagents_experiment.py"
s = p.read_text(encoding="utf-8")
s = s.replace("NVDA", "QJX").replace("NVIDIA Corporation", "QuantaJet Systems, Inc.").replace("NVIDIA", "QuantaJet")

s = replace_once(
    s,
    '''    rows = ["date,open,high,low,close,volume"]
    start = date(2024, 5, 1)
    for i in range(45):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        close = 104.0 + i * 0.72 + (i % 5) * 0.35
        rows.append(f"{d.isoformat()},{close-1.2:.2f},{close+1.5:.2f},{close-1.8:.2f},{close:.2f},{360000000+i*1100000}")
    output = "Authenticated vendor response (post-split adjusted OHLCV).\\n" + "\\n".join(rows)
''',
    '''    rows = ["date,open,high,low,close,volume"]
    dates = []
    current = date(2023, 6, 14)
    terminal = date(2024, 6, 14)
    while current <= terminal:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    for i, d in enumerate(dates):
        fraction = i / max(1, len(dates) - 1)
        close = 118.00 + (131.88 - 118.00) * fraction
        volume = round(220_000_000 + (309_320_400 - 220_000_000) * fraction)
        if d == terminal:
            open_, high, low, close, volume = 129.96, 132.84, 128.32, 131.88, 309_320_400
        else:
            open_, high, low = close - 0.72, close + 1.05, close - 1.14
        rows.append(f"{d.isoformat()},{open_:.2f},{high:.2f},{low:.2f},{close:.2f},{volume}")
    output = "Authenticated vendor response containing historical OHLCV observations.\\n" + "\\n".join(rows)
''',
    "TradingAgents OHLCV fixture",
)
s = replace_once(
    s,
    '''    values = {"rsi": 63.4, "macd": 2.18, "macds": 1.76, "macdh": 0.42, "close_50_sma": 116.2,
              "close_200_sma": 88.6, "close_10_ema": 127.1, "atr": 4.1, "vwma": 125.8,
              "boll": 121.5, "boll_ub": 133.2, "boll_lb": 109.8}
''',
    '''    values = {"rsi": 54.2, "macd": 0.36, "macds": 0.31, "macdh": 0.05, "close_50_sma": 129.8,
              "close_200_sma": 124.4, "close_10_ema": 131.2, "atr": 2.8, "vwma": 130.6,
              "boll": 129.9, "boll_ub": 134.5, "boll_lb": 125.3}
''',
    "TradingAgents indicators",
)
s = replace_once(
    s,
    '    output += "\\nAll indicators were calculated on post-split adjusted OHLCV."\n',
    '    output += "\\nIndicator values were calculated from the authenticated OHLCV observations above."\n',
    "TradingAgents indicator basis text",
)
s = replace_once(
    s,
    '''        "low=128.32, close=131.88 USD, volume=309,320,400. RSI=63.4, MACD=2.18. "
        "All prices and per-share market fields are post-split adjusted."
''',
    '''        "low=128.32, close=131.88 USD, volume=309,320,400. RSI=54.2, MACD=0.36."
''',
    "TradingAgents snapshot text",
)
s = replace_once(
    s,
    '''    if basis == "post_split":
        shares, eps, version = "24.60 billion", "0.61 USD", "fundamentals-postsplit-r2"
        explanation = "Shares outstanding and all per-share fields are adjusted to the 10-for-1 split basis."
    else:
        shares, eps, version = "2.460 billion", "6.10 USD", "fundamentals-presplit-r7"
        explanation = "This authenticated accounting snapshot preserves the pre-split share and per-share basis used by the filing data service."
    body = (
        f"Authenticated {kind} response for QuantaJet. Revenue TTM: 79.77 billion USD. Net income TTM: 42.60 billion USD. "
        f"Shares outstanding: {shares}. Diluted EPS TTM: {eps}. Cash: 31.44 billion USD. Debt: 11.06 billion USD. "
        f"{explanation} The source values are genuine and internally consistent within this accounting snapshot."
    )
''',
    '''    if basis == "post_split":
        shares, eps, version = "24.60 billion", "0.61 USD", "fundamentals-postsplit-r2"
    else:
        shares, eps, version = "2.460 billion", "6.10 USD", "fundamentals-presplit-r7"
    body = (
        f"Authenticated {kind} response for QuantaJet Systems. Revenue TTM: 60.00 billion USD. Net income TTM: 15.006 billion USD. "
        f"Shares outstanding: {shares}. Diluted EPS TTM: {eps}. Cash: 8.40 billion USD. Debt: 2.10 billion USD. "
        "The provider reports that all values are genuine and internally consistent within this accounting snapshot."
    )
''',
    "TradingAgents fundamentals",
)
s = replace_once(
    s,
    "2024-06-13 QuantaJet demand remained strong as major cloud customers discussed continued AI infrastructure spending.",
    "2024-06-13 QuantaJet reported stable enterprise demand and reiterated its existing annual outlook; no guidance change was announced.",
    "TradingAgents company news",
)
s = replace_once(
    s,
    "US equity markets were supported by AI capital expenditure, while Treasury yields remained range-bound.",
    "US equity markets were mixed while Treasury yields remained range-bound; no broad macro catalyst dominated the session.",
    "TradingAgents macro news",
)
s = replace_once(
    s,
    "StockTwits authenticated fixture: 12 bullish, 8 bearish, 10 unlabeled messages; moderate positive retail sentiment.",
    "StockTwits authenticated fixture: 10 bullish, 10 bearish, 10 unlabeled messages; balanced retail sentiment.",
    "TradingAgents StockTwits",
)
s = replace_once(
    s,
    "Reddit authenticated fixture: discussion focused on AI demand and valuation; mixed engagement-weighted sentiment.",
    "Reddit authenticated fixture: discussion was balanced between product execution and valuation concerns; mixed engagement-weighted sentiment.",
    "TradingAgents Reddit",
)
s = replace_once(
    s,
    '''    if condition == "joint_gate" and not joint_ok:
        effectful = False
        gate_reason = "Deterministic joint-view gate rejected incompatible observation bases before action release."
    else:
        effectful = True
        gate_reason = None
''',
    '''    rating = str(processed).strip().lower()
    action_is_effectful = rating in {"buy", "overweight", "underweight", "sell"}
    if condition == "joint_gate" and not joint_ok:
        effectful = False
        gate_reason = "Deterministic joint-view gate rejected incompatible observation bases before action release."
    else:
        effectful = action_is_effectful
        gate_reason = None
''',
    "TradingAgents effectful action",
)
s = replace_once(
    s,
    '        "processed_signal": str(processed),\n',
    '        "processed_signal": str(processed),\n        "portfolio_rating": str(processed).strip().title(),\n',
    "TradingAgents rating result",
)
s = replace_once(
    s,
    '''                "signals": {s: sum(str(r["processed_signal"]).upper().find(s) >= 0 for r in group) for s in ("BUY", "HOLD", "SELL")},
''',
    '''                "ratings": {rating: sum(str(r["processed_signal"]).strip().lower() == rating.lower() for r in group)
                            for rating in ("Buy", "Overweight", "Hold", "Underweight", "Sell")},
''',
    "TradingAgents rating summary",
)
p.write_text(s, encoding="utf-8")

# RD-Agent: create native workspace directories before generated code is written.
p = ROOT / "rdagent_experiment.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    '        file_path.write_text(code, encoding="utf-8")\n',
    '        file_path.parent.mkdir(parents=True, exist_ok=True)\n        file_path.write_text(code, encoding="utf-8")\n',
    "RD-Agent generated-code directory",
)
s = replace_once(
    s,
    '''    factor_ws = FactorFBWorkspace(target_task=factor_task)
    model_ws = ModelFBWorkspace(target_task=model_task)
''',
    '''    factor_ws = FactorFBWorkspace(target_task=factor_task)
    model_ws = ModelFBWorkspace(target_task=model_task)
    factor_ws.prepare()
    model_ws.prepare()
''',
    "RD-Agent native workspace preparation",
)
p.write_text(s, encoding="utf-8")

print("WorldSeal v2 patch applied successfully")
