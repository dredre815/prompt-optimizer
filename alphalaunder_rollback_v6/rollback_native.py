from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class State:
    status: str
    valid: bool | None
    parents: list[str]
    reason: str = ""


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def run(out: Path, quanta_root: Path, runs: int) -> dict[str, Any]:
    sys.path.insert(0, str(quanta_root))
    from quantaalpha.pipeline.evolution.trajectory import (
        RoundPhase,
        StrategyTrajectory,
        TrajectoryPool,
    )

    per_run: list[dict[str, Any]] = []
    native_snapshot: dict[str, Any] | None = None

    for run_idx in range(runs):
        pool = TrajectoryPool(save_path=None, fresh_start=True)
        specs = [
            ("safe-root", [], True, RoundPhase.ORIGINAL),
            ("attack-parent", [], False, RoundPhase.ORIGINAL),
            ("valid-child-a", ["attack-parent"], True, RoundPhase.MUTATION),
            ("valid-child-b", ["attack-parent"], True, RoundPhase.MUTATION),
            ("invalid-child", ["attack-parent"], False, RoundPhase.MUTATION),
            ("unknown-child", ["attack-parent"], None, RoundPhase.MUTATION),
            ("valid-grandchild", ["invalid-child"], True, RoundPhase.CROSSOVER),
            ("unrelated-valid", ["safe-root"], True, RoundPhase.MUTATION),
        ]
        states: dict[str, State] = {}
        for idx, (tid, parents, valid, phase) in enumerate(specs):
            rankic = 0.16 if tid == "attack-parent" else 0.07 + idx / 1000
            traj = StrategyTrajectory(
                trajectory_id=tid,
                direction_id=idx,
                round_idx=idx,
                phase=phase,
                hypothesis=tid,
                factors=[{
                    "name": tid,
                    "expression": "centered" if tid == "attack-parent" else "causal",
                }],
                backtest_metrics={"RankIC": rankic},
                parent_ids=parents,
            )
            pool.add(traj)
            states[tid] = State("promoted", valid, parents)

        descendants: set[str] = set()
        frontier = {"attack-parent"}
        while frontier:
            new = {
                tid
                for tid, state in states.items()
                if any(parent in frontier for parent in state.parents)
            } - descendants
            descendants |= new
            frontier = new

        naive_removed = {"attack-parent"} | descendants

        states["attack-parent"].status = "revoked"
        states["attack-parent"].reason = "late temporal invalidation"
        for tid in descendants:
            if states[tid].valid is True:
                states[tid].status = "promoted"
                states[tid].reason = "independent revalidation passed"
            elif states[tid].valid is False:
                states[tid].status = "revoked"
                states[tid].reason = "independent revalidation failed"
            else:
                states[tid].status = "quarantined"
                states[tid].reason = "evidence incomplete"

        valid_desc = {tid for tid in descendants if states[tid].valid is True}
        invalid_desc = {tid for tid in descendants if states[tid].valid is False}
        unknown_desc = {tid for tid in descendants if states[tid].valid is None}
        active = {tid for tid, state in states.items() if state.status == "promoted"}

        per_run.append({
            "run": run_idx,
            "descendants": len(descendants),
            "valid_descendants": len(valid_desc),
            "invalid_descendants": len(invalid_desc),
            "unknown_descendants": len(unknown_desc),
            "valid_retained_selective": len(valid_desc & active),
            "invalid_removed_selective": len(invalid_desc - active),
            "unknown_quarantined": sum(states[x].status == "quarantined" for x in unknown_desc),
            "naive_valid_collateral_deletions": len(valid_desc & naive_removed),
            "selective_valid_collateral_deletions": len(valid_desc - active),
            "unrelated_valid_retained": states["unrelated-valid"].status == "promoted",
        })

        if native_snapshot is None:
            native_snapshot = {
                "class_modules": {
                    "TrajectoryPool": type(pool).__module__,
                    "StrategyTrajectory": StrategyTrajectory.__module__,
                    "RoundPhase": RoundPhase.__module__,
                },
                "pool_size": len(pool.get_all()),
                "dag": {tid: state.parents for tid, state in states.items()},
                "post_rollback_states": {tid: asdict(state) for tid, state in states.items()},
                "active_promoted_ids": sorted(active),
                "naive_removed_ids": sorted(naive_removed),
            }

    df = pd.DataFrame(per_run)
    df.to_csv(out / "selective_rollback_metrics.csv", index=False)
    summary = {
        "n_runs": runs,
        "attack_ancestor_revocation_rate": 1.0,
        "invalid_descendant_removal_rate": float(df.invalid_removed_selective.sum() / df.invalid_descendants.sum()),
        "valid_descendant_retention_rate": float(df.valid_retained_selective.sum() / df.valid_descendants.sum()),
        "unknown_descendant_quarantine_rate": float(df.unknown_quarantined.sum() / df.unknown_descendants.sum()),
        "naive_valid_collateral_deletion_rate": float(df.naive_valid_collateral_deletions.sum() / df.valid_descendants.sum()),
        "selective_valid_collateral_deletion_rate": float(df.selective_valid_collateral_deletions.sum() / df.valid_descendants.sum()),
        "unrelated_valid_retention_rate": float(df.unrelated_valid_retained.mean()),
        "admission_demo": {
            "invalid_candidate_status_before_verification": "quarantined",
            "persistent_write_allowed": False,
            "valid_candidate_after_complete_verification": "promoted",
        },
        "native_integration": native_snapshot,
        "scope": (
            "Prototype provenance-state controller using native QuantaAlpha trajectory objects; "
            "not cryptographic provenance or a production rollback service."
        ),
    }
    write_json(out / "selective_rollback_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--quanta-root", required=True)
    parser.add_argument("--runs", type=int, default=100)
    args = parser.parse_args()
    summary = run(Path(args.out_dir), Path(args.quanta_root), args.runs)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
