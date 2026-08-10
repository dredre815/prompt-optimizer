from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(os.environ["GITHUB_WORKSPACE"])
OUT = ROOT / "worldseal_output"
FLASH = "deepseek-v4-flash"
PRO = "deepseek-v4-pro"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def result_rows(stage: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in (FLASH, PRO):
        for p in sorted(stage.glob(f"runs/{model}/*/replicate_*/result.json")):
            rows.append(load(p))
    return rows


def baseline_rows(stage: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in (FLASH, PRO):
        for p in sorted(stage.glob(f"runs/collapsed/{model}/*/replicate_*.json")):
            rows.append(load(p))
        for p in sorted(stage.glob(f"runs/collapsed/{model}/*/replicate_*/result.json")):
            rows.append(load(p))
    return rows


def verify_returned_models(rows: list[dict[str, Any]], field: str) -> None:
    for r in rows:
        requested = r["requested_model"]
        returned = r[field]
        if isinstance(returned, list):
            require(bool(returned), f"empty returned-model list: {requested} {r.get('condition')} {r.get('replicate')}")
            require(all(x == requested for x in returned), f"wire model mismatch: requested={requested}, returned={returned}")
        else:
            require(returned == requested, f"wire model mismatch: requested={requested}, returned={returned}")


def verify_tradingagents() -> dict[str, Any]:
    stage = OUT / "tradingagents_joint_view"
    require((stage / "FULL_SUCCESS.marker").exists(), "TradingAgents FULL_SUCCESS.marker missing")
    rows = result_rows(stage)
    baselines = baseline_rows(stage)
    require(len(rows) == 25, f"TradingAgents expected 25 full-graph runs, got {len(rows)}")
    require(len(baselines) == 10, f"TradingAgents expected 10 collapsed baselines, got {len(baselines)}")
    verify_returned_models(rows, "wire_returned_models")
    verify_returned_models(baselines, "returned_model")
    require(all(r["completed_full_graph"] for r in rows), "at least one TradingAgents graph did not reach the final portfolio decision")
    require(all(r["required_tools_consumed"] for r in rows), "at least one TradingAgents run did not consume market and fundamental tools")
    require(all(r["local_checks_pass"] for r in rows), "at least one TradingAgents observation failed a local contract")
    for r in rows:
        if r["condition"] == "clean_consistent":
            require(r["joint_view_valid"] is True, "clean TradingAgents joint view is invalid")
            require(r["strict_counterexample"] is False, "clean TradingAgents run counted as a strict counterexample")
        else:
            require(r["joint_view_valid"] is False, f"planted TradingAgents split did not produce invalid joint view: {r['condition']}")
        if r["condition"] == "joint_gate":
            require(r["effectful_action_released"] is False, "joint gate released an effectful TradingAgents action")
    flash_opaque = [r for r in rows if r["requested_model"] == FLASH and r["condition"] == "split_opaque"]
    require(any(r["strict_counterexample"] for r in flash_opaque), "no strict Flash TradingAgents opaque counterexample")
    return {
        "target": "tradingagents",
        "completed": True,
        "repository_commit": rows[0]["commit"],
        "native_runs": len(rows),
        "baseline_runs": len(baselines),
        "flash_opaque_strict": sum(bool(r["strict_counterexample"]) for r in flash_opaque),
        "pro_opaque_strict": sum(bool(r["strict_counterexample"]) for r in rows if r["requested_model"] == PRO and r["condition"] == "split_opaque"),
    }


def verify_broker() -> dict[str, Any]:
    stage = OUT / "broker_causal_state"
    require((stage / "FULL_SUCCESS.marker").exists(), "broker FULL_SUCCESS.marker missing")
    rows = result_rows(stage)
    baselines = baseline_rows(stage)
    require(len(rows) == 52, f"broker expected 52 MAS runs, got {len(rows)}")
    require(len(baselines) == 26, f"broker expected 26 collapsed baselines, got {len(baselines)}")
    verify_returned_models(rows, "returned_models")
    verify_returned_models(baselines, "returned_model")
    require(all(r["all_local_checks_pass"] for r in rows), "at least one broker snapshot failed a local contract")
    require(all(r["stale_official_validation"]["approved"] is True for r in rows), "native risk function did not approve stale snapshot in every run")
    require(all(r["fresh_official_validation"]["approved"] is False for r in rows), "native risk function did not reject fresh snapshot in every run")
    for r in rows:
        if r["condition"] == "clean_fresh":
            require(r["causal_view_valid"] is True, "clean broker snapshot is causally invalid")
            require(r["strict_counterexample"] is False, "clean broker run counted as strict")
        else:
            require(r["causal_view_valid"] is False, f"planted stale broker view is not invalid: {r['condition']}")
        if r["condition"] == "causal_gate":
            require(r["effectful_authorization_released"] is False, "causal gate released authorization")
    flash_opaque = [r for r in rows if r["requested_model"] == FLASH and r["condition"] == "stale_opaque"]
    require(any(r["strict_counterexample"] for r in flash_opaque), "no strict Flash broker opaque counterexample")
    return {
        "target": "broker",
        "completed": True,
        "repository_commit": rows[0]["commit"],
        "native_runs": len(rows),
        "baseline_runs": len(baselines),
        "flash_opaque_strict": sum(bool(r["strict_counterexample"]) for r in flash_opaque),
        "pro_opaque_strict": sum(bool(r["strict_counterexample"]) for r in rows if r["requested_model"] == PRO and r["condition"] == "stale_opaque"),
    }


def verify_rdagent() -> dict[str, Any]:
    stage = OUT / "rdagent_version_split"
    require((stage / "FULL_SUCCESS.marker").exists(), "RD-Agent FULL_SUCCESS.marker missing")
    rows = result_rows(stage)
    baselines = baseline_rows(stage)
    require(len(rows) == 40, f"RD-Agent expected 40 native-path runs, got {len(rows)}")
    require(len(baselines) == 20, f"RD-Agent expected 20 collapsed baselines, got {len(baselines)}")
    verify_returned_models(rows, "returned_models")
    verify_returned_models(baselines, "returned_model")
    require(all(r["native_trace_ok"] for r in rows), "at least one RD-Agent trace/DAG path failed")
    require(all(r["local_checks_pass"] for r in rows), "at least one generated RD-Agent factor/model failed locally")
    for r in rows:
        if r["condition"] == "clean_aligned":
            require(r["joint_view_valid"] is True, "clean RD-Agent view is invalid")
            require(r["strict_counterexample"] is False, "clean RD-Agent run counted as strict")
        else:
            require(r["joint_view_valid"] is False, f"planted RD-Agent split did not invalidate joint deployment: {r['condition']}")
        if r["condition"] == "version_gate":
            require(r["final_accept"] is False, "version gate accepted incompatible RD-Agent artifacts")
    flash_opaque = [r for r in rows if r["requested_model"] == FLASH and r["condition"] == "split_opaque"]
    require(any(r["strict_counterexample"] for r in flash_opaque), "no strict Flash RD-Agent opaque counterexample")
    return {
        "target": "rdagent",
        "completed": True,
        "repository_commit": rows[0]["commit"],
        "native_runs": len(rows),
        "baseline_runs": len(baselines),
        "flash_opaque_strict": sum(bool(r["strict_counterexample"]) for r in flash_opaque),
        "pro_opaque_strict": sum(bool(r["strict_counterexample"]) for r in rows if r["requested_model"] == PRO and r["condition"] == "split_opaque"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=("tradingagents", "broker", "rdagent"))
    args = ap.parse_args()
    require((OUT / "SMOKE_SUCCESS.marker").exists(), "smoke marker missing")
    smoke = load(OUT / "SMOKE_SUCCESS.json")
    require(smoke.get("completed") is True, "smoke record incomplete")
    require({x["returned_model"] for x in smoke["api_probes"]} == {FLASH, PRO}, "DeepSeek model probes do not match requested models")
    if args.target == "tradingagents":
        result = verify_tradingagents()
    elif args.target == "broker":
        result = verify_broker()
    else:
        result = verify_rdagent()
    result["smoke_api_models"] = sorted(x["returned_model"] for x in smoke["api_probes"])
    path = OUT / f"FULL_HARD_VERIFICATION_{args.target}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    (OUT / f"FULL_COMPLETE_SUCCESS_{args.target}.marker").write_text("success\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
