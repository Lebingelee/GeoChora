"""Build a DG02 source-bound Core candidate inside the CPU supervisor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def run(plan_path: Path, sidecar_path: Path, worker_receipt_path: Path) -> dict:
    plan_path = plan_path.resolve(strict=True)
    sidecar_path = sidecar_path.resolve(strict=True)
    raw = plan_path.read_bytes()
    plan_sha256 = hashlib.sha256(raw).hexdigest()
    if plan_sha256 != sidecar_path.read_text(encoding="ascii").split()[0]:
        raise ValueError("supervised candidate plan SHA-256 mismatch")
    plan = json.loads(raw)
    for row in plan["code"]["tracked_inputs"]:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"supervised candidate code hash differs: {path}")
    for repo_key, head_key, branch_key in (
        ("core_worktree", "core_input_head", "core_branch"),
        ("provider_worktree", "provider_input_head", "provider_branch"),
    ):
        repo = Path(plan["input_identity"][repo_key]).resolve(strict=True)
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "-C", str(repo), "branch", "--show-current"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if (head, branch) != (
            plan["input_identity"][head_key], plan["input_identity"][branch_key],
        ):
            raise ValueError(f"supervised candidate {repo_key} identity changed")

    from task_env.diagnostics.tasks.f05_dg02_core_source_receipt import build_candidate_receipt

    receipt, candidate = build_candidate_receipt(plan, include_candidate=True)
    if (receipt["checks"]["solver_initialized"]
            or receipt["checks"]["solver_constructed"]
            or receipt["checks"]["physics_steps"] != 0):
        raise RuntimeError("static Core candidate unexpectedly initialized or stepped a solver")
    receipt_path = Path(plan["output"]["candidate_receipt"]).resolve()
    receipt.update({
        "plan_path": str(plan_path),
        "plan_sha256": plan_sha256,
        "supervision": "f05_dg02_n1_supervisor_cpu_fail_closed",
    })
    _atomic_json(receipt_path, receipt)
    worker_receipt = {
        "schema_version": "f05-dg02-supervised-candidate-worker-receipt-v1",
        "run_id": plan["run_id"],
        "plan_path": str(plan_path),
        "plan_sha256": plan_sha256,
        "candidate_receipt_path": str(receipt_path),
        "candidate_receipt_sha256": _sha(receipt_path),
        "candidate_controller_identity_sha256": candidate.env.controller.identity,
        "candidate_controller_method": {
            "arm_tracking_method": candidate.env.controller.arm_tracking_method,
            "arm_tracking_profile": candidate.env.controller.arm_tracking_profile,
            "arm_reference_identity": candidate.env.controller._arm_reference.identity,
            "nullspace_reference_gain": candidate.env.controller.nullspace_reference_gain,
            "pose_target_method": candidate.env.controller.pose_target_method,
            "arm_target_limit_source": candidate.env.controller.arm_target_limit_source,
        },
        "public_model_counts": receipt["public_model_counts"],
        "native_starts": 1,
        "physics_steps_attempted": 0,
        "physics_steps_completed": 0,
        "solver_initialized": False,
        "solver_constructed": False,
        "status": "PASS_SUPERVISED_STATIC_CORE_CANDIDATE",
    }
    worker_receipt_path = worker_receipt_path.resolve()
    _atomic_json(worker_receipt_path, worker_receipt)
    return worker_receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--counter", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.plan, args.plan_sha256, args.receipt)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
