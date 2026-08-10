from __future__ import annotations

import argparse
import json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=("tradingagents", "broker", "rdagent"))
    ap.add_argument("kind", choices=("native", "baseline"))
    ap.add_argument("model")
    ap.add_argument("condition")
    ap.add_argument("replicate", type=int)
    args = ap.parse_args()

    if args.target == "tradingagents":
        import tradingagents_experiment as module
        fn = module.run_one if args.kind == "native" else module.run_collapsed_baseline
    elif args.target == "broker":
        import broker_experiment as module
        fn = module.run_one if args.kind == "native" else module.collapsed_baseline
    else:
        import rdagent_experiment as module
        fn = module.run_one if args.kind == "native" else module.collapsed_baseline
    result = fn(args.model, args.condition, args.replicate)
    print(json.dumps({
        "target": args.target,
        "kind": args.kind,
        "model": args.model,
        "condition": args.condition,
        "replicate": args.replicate,
        "strict_counterexample": result.get("strict_counterexample"),
    }, indent=2))


if __name__ == "__main__":
    main()
