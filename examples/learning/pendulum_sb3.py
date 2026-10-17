"""Run one small SB3 PPO update through the existing Pendulum runner.

This is an executable CPU smoke, not a learning or convergence qualification.
The training loop, batch adapter, checkpoint format and return-curve writer
remain owned by ``task_env.script.rl.pendulum_ppo``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from examples._common import RunTimeout, bootstrap_imports, bounded_process


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--time-limit-s", type=int, default=180)
    parser.add_argument(
        "--address-space-limit-mb",
        type=int,
        default=8192,
        help="Linux per-process RLIMIT_AS cap; not RSS or process-tree memory",
    )
    args = parser.parse_args(argv)

    output = args.output_dir.expanduser().resolve()
    if output.exists():
        parser.error(f"output directory already exists; choose a fresh path: {output}")
    output.mkdir(parents=True)
    bootstrap_imports()

    report = {
        "status": "ERROR",
        "qualification": "NOT_ASSESSED",
        "task_uid": "pendulum-v1",
        "capability_intersection": "GeoPhys CPU, merged_scene batch, SB3 PPO one-update smoke",
        "configuration": {
            "num_env": 2,
            "updates": 1,
            "rollout_steps": 2,
            "seed": 73,
            "integrator": "implicitfast",
        },
        "output_dir": str(output),
    }
    try:
        with bounded_process(args.address_space_limit_mb, args.time_limit_s) as budget:
            from task_env.script.rl.pendulum_ppo import main as train_pendulum

            train_result = train_pendulum(
                [
                    "--num-env", "2",
                    "--backend", "cpu",
                    "--batch-physics-layout", "merged_scene",
                    "--integrator", "implicitfast",
                    "--updates", "1",
                    "--rollout-steps", "2",
                    "--seed", "73",
                    "--output-dir", str(output),
                    "--save-log", "return_curve.h5",
                    "--save-every-updates", "1",
                    "--log-every-updates", "1",
                ]
            )
            if train_result not in (None, 0):
                raise RuntimeError(f"the existing Pendulum runner returned {train_result}")
            summary_path = output / "summary.json"
            return_curve = output / "return_curve.h5"
            if not summary_path.is_file() or not return_curve.is_file():
                raise RuntimeError("the existing Pendulum runner did not finalize its expected outputs")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            batches = summary.get("batches", [])
            if len(batches) != 1:
                raise RuntimeError("expected exactly one bounded Pendulum training run")
            batch = batches[0]
            if (
                batch.get("backend") != "cpu"
                or batch.get("batch_physics_layout") != "merged_scene"
                or batch.get("num_env") != 2
                or batch.get("timesteps") != 4
                or batch.get("updates_completed") != 1
            ):
                raise RuntimeError("the existing runner summary did not match the bounded smoke configuration")
            report.update(
                status="PASS_BOUNDED_SMOKE_NOT_QUALIFICATION",
                runner_summary=str(summary_path),
                return_curve=str(return_curve),
                runner_result=batch,
                resource_budget=budget,
            )
    except RunTimeout as exc:
        report.update(status="TIMEOUT", error=str(exc))
    except SystemExit as exc:
        report.update(status="ERROR", error=f"Pendulum runner exited with code {exc.code}")
    except Exception as exc:
        report.update(status="ERROR", error=f"{type(exc).__name__}: {exc}")

    (output / "example_result.json").write_text(
        json.dumps(report, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True, default=str))
    return 0 if report["status"] == "PASS_BOUNDED_SMOKE_NOT_QUALIFICATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
