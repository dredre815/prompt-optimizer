from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(os.environ["GITHUB_WORKSPACE"])
SRC = ROOT / "worldseal_clean"
OUT = ROOT / "worldseal_output"
FLASH = "deepseek-v4-flash"
PRO = "deepseek-v4-pro"

CONFIG: dict[str, dict[str, Any]] = {
    "tradingagents": {
        "conditions": ["clean_consistent", "split_opaque", "split_explicit", "split_metadata_visible", "joint_gate"],
        "models": [(FLASH, 3), (PRO, 2)],
        "baseline_conditions": ["clean_consistent", "split_opaque"],
        "workers": 3,
        "stage": "tradingagents_joint_view",
    },
    "broker": {
        "conditions": ["clean_fresh", "stale_opaque", "stale_explicit", "causal_gate"],
        "models": [(FLASH, 8), (PRO, 5)],
        "baseline_conditions": ["clean_fresh", "stale_opaque"],
        "workers": 5,
        "stage": "broker_causal_state",
    },
    "rdagent": {
        "conditions": ["clean_aligned", "split_opaque", "split_explicit", "version_gate"],
        "models": [(FLASH, 6), (PRO, 4)],
        "baseline_conditions": ["clean_aligned", "split_opaque"],
        "workers": 4,
        "stage": "rdagent_version_split",
    },
}


def task_id(task: tuple[str, str, int, str]) -> str:
    model, condition, replicate, kind = task
    return f"{kind}__{model}__{condition}__{replicate}"


def execute(target: str, task: tuple[str, str, int, str], log_dir: Path) -> dict[str, Any]:
    model, condition, replicate, kind = task
    started = time.perf_counter()
    cmd = [sys.executable, str(SRC / "single_task.py"), target, kind, model, condition, str(replicate)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(cmd, cwd=SRC, env=env, text=True, capture_output=True, check=False)
    record = {
        "task": task_id(task),
        "target": target,
        "kind": kind,
        "model": model,
        "condition": condition,
        "replicate": replicate,
        "returncode": proc.returncode,
        "duration_seconds": time.perf_counter() - started,
        "stdout_tail": proc.stdout[-8000:],
        "stderr_tail": proc.stderr[-8000:],
    }
    (log_dir / f"{task_id(task)}.log").write_text(
        "COMMAND: " + " ".join(cmd) + "\n\nSTDOUT\n" + proc.stdout + "\n\nSTDERR\n" + proc.stderr,
        encoding="utf-8",
    )
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=tuple(CONFIG))
    args = ap.parse_args()
    cfg = CONFIG[args.target]
    log_dir = OUT / "logs" / f"parallel_{args.target}"
    log_dir.mkdir(parents=True, exist_ok=True)

    native_tasks: list[tuple[str, str, int, str]] = []
    baseline_tasks: list[tuple[str, str, int, str]] = []
    for model, repetitions in cfg["models"]:
        for condition in cfg["conditions"]:
            for replicate in range(repetitions):
                native_tasks.append((model, condition, replicate, "native"))
        for condition in cfg["baseline_conditions"]:
            for replicate in range(repetitions):
                baseline_tasks.append((model, condition, replicate, "baseline"))

    records: list[dict[str, Any]] = []
    with cf.ThreadPoolExecutor(max_workers=int(cfg["workers"])) as pool:
        futures = [pool.submit(execute, args.target, task, log_dir) for task in native_tasks]
        for idx, future in enumerate(cf.as_completed(futures), 1):
            record = future.result()
            records.append(record)
            print(f"[{args.target}:native] {idx}/{len(futures)} {record['task']} rc={record['returncode']}", flush=True)

    for idx, task in enumerate(baseline_tasks, 1):
        record = execute(args.target, task, log_dir)
        records.append(record)
        print(f"[{args.target}:baseline] {idx}/{len(baseline_tasks)} {record['task']} rc={record['returncode']}", flush=True)

    failures = [r for r in records if r["returncode"] != 0]
    manifest = {
        "target": args.target,
        "completed": not failures,
        "workers": cfg["workers"],
        "native_task_count": len(native_tasks),
        "baseline_task_count": len(baseline_tasks),
        "records": records,
    }
    path = OUT / f"PARALLEL_EXECUTION_{args.target}.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if failures:
        raise RuntimeError(f"{len(failures)} {args.target} tasks failed; see {path}")
    stage = OUT / cfg["stage"]
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "FULL_SUCCESS.marker").write_text("success\n", encoding="utf-8")


if __name__ == "__main__":
    main()
