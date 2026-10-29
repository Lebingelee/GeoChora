"""Offline public TaskEnv semantic readers for finalized R04c Generic H5 v3."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback


TASK_ENV_ROOT = Path(__file__).resolve().parents[3]
if str(TASK_ENV_ROOT) not in sys.path:
    sys.path.insert(0, str(TASK_ENV_ROOT))

FORBIDDEN_ENGINE_PREFIXES = ("mujoco", "taichi", "OpenGL", "glfw", "geophys", "GeoPhys")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _check_engine_imports(modules: list[str]) -> list[str]:
    return sorted(
        name for name in modules
        if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_ENGINE_PREFIXES)
    )


def _check_one_h5(path: Path) -> dict[str, object]:
    from task_env.recorders import (
        load_camera_observations_h5,
        load_structured_control_records_h5,
        load_structured_training_actions_h5,
    )

    controls = load_structured_control_records_h5(path)
    camera = load_camera_observations_h5(path)
    actions = load_structured_training_actions_h5(path)
    outcome = controls["outcome"]
    if (controls["schema_id"], controls["schema_version"], controls["transition_count"],
            controls["observation_count"]) != ("task-env-h5", "v3", 12, 13):
        raise ValueError("public readers require one complete Generic H5 v3 with T=12/T+1=13")
    if (camera["transition_count"], camera["observation_count"]) != (12, 13):
        raise ValueError("public camera reader did not validate 12 transitions and 13 observations")
    if len(controls["structured_controls"]) != 12 or len(actions) != 12:
        raise ValueError("public structured control/action readers did not return 12 ordered records")
    if (outcome.end_reason != "external_stop" or outcome.final_boundary != 12
            or outcome.terminated or not outcome.truncated
            or outcome.task_success is True or outcome.solution_completed is not None):
        raise ValueError("H5 outcome must preserve the valid external stop, not task/horizon success")
    boundaries = camera["boundaries"]
    binding = camera["recording_binding"]
    if len(boundaries) != 13 or binding["final_boundary"] != 12:
        raise ValueError("camera semantic reader returned incomplete boundary anchors")
    camera_ids = tuple(capture.camera_id for capture in boundaries[0].captures)
    if camera_ids != (
        "d04-fixed-square-peg-calibration-v1",
        "d04-panda-hand-mounted-camera-v1",
    ):
        raise ValueError("public camera reader returned a different D04 camera pair/order")
    return {
        "path": str(path),
        "schema_id": controls["schema_id"],
        "schema_version": controls["schema_version"],
        "transition_count": controls["transition_count"],
        "observation_count": controls["observation_count"],
        "camera_ids": list(camera_ids),
        "episode_id": outcome.episode_id,
        "end_reason": outcome.end_reason,
        "final_boundary": outcome.final_boundary,
        "terminated": outcome.terminated,
        "truncated": outcome.truncated,
        "task_success": outcome.task_success,
        "solution_completed": outcome.solution_completed,
        "recording_binding": binding,
        "reader_status": "PUBLIC_TASKENV_H5_SEMANTIC_PASS",
    }


def verify(*, worker_output: Path | None = None, h5_path: Path | None = None) -> dict[str, object]:
    started = time.monotonic()
    modules_before = sorted(sys.modules)
    if (worker_output is None) == (h5_path is None):
        raise ValueError("provide exactly one of --worker-output or --h5")
    episodes = []
    worker = None
    if worker_output is not None:
        worker = _read_json(worker_output / "r04c_worker_receipt.json")
        if worker.get("status") != "R04C_NATIVE_RECORDING_COMPLETE_PENDING_OFFLINE_READBACK":
            raise ValueError("native worker receipt is not a complete R04c recording awaiting readback")
        episodes_raw = worker.get("episode_recordings")
        if not isinstance(episodes_raw, list) or len(episodes_raw) != 2:
            raise ValueError("R04c worker receipt must identify exactly two completed episode H5 files")
        for entry in episodes_raw:
            if (not isinstance(entry, dict) or entry.get("status") != "FINALIZED"
                    or entry.get("finalizer_result", {}).get("transition_count") != 12
                    or entry.get("finalizer_result", {}).get("observation_count") != 13):
                raise ValueError("R04c worker receipt contains a non-final or incomplete episode")
            episodes.append(_check_one_h5(Path(entry["path"])))
    else:
        episodes.append(_check_one_h5(h5_path))

    modules_after = sorted(sys.modules)
    forbidden = _check_engine_imports(modules_after)
    if forbidden:
        raise RuntimeError(f"public semantic reader imported a physics/render engine: {forbidden}")
    if len(episodes) == 2:
        first, second = episodes
        b1, b2 = first["recording_binding"], second["recording_binding"]
        if first["episode_id"] == second["episode_id"]:
            raise ValueError("two H5 files share the same episode identity")
        if (b1["reset_sample_id"] != b2["reset_sample_id"]
                or b1["task_artifact_identity_hash"] != b2["task_artifact_identity_hash"]
                or b1["scene_identity_hash"] != b2["scene_identity_hash"]):
            raise ValueError("two H5 episodes do not share the frozen candidate/reset identity")
        ids = [
            episode["recording_binding"]["boundaries"][0]["state_boundary_identity"][
                "provider_materialization_id"
            ]
            for episode in (first, second)
        ]
        if ids[0] == ids[1]:
            raise ValueError("the two H5 episodes reuse one provider materialization")

    return {
        "schema_version": "r04c-public-h5-semantic-reader-v1",
        "status": "R04C_PUBLIC_H5_SEMANTIC_READBACK_PASS",
        "episodes": episodes,
        "worker_status": None if worker is None else worker.get("status"),
        "modules_before": modules_before,
        "modules_after": modules_after,
        "engine_modules_imported": forbidden,
        "engine_context_created": False,
        "elapsed_s": time.monotonic() - started,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--worker-output", type=Path)
    group.add_argument("--h5", type=Path)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = verify(worker_output=args.worker_output, h5_path=args.h5)
    except BaseException as error:
        receipt = {
            "schema_version": "r04c-public-h5-semantic-reader-v1",
            "status": "R04C_PUBLIC_H5_SEMANTIC_READBACK_FAIL",
            "error": {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()},
            "modules_after": sorted(sys.modules),
            "engine_modules_imported": _check_engine_imports(sorted(sys.modules)),
            "engine_context_created": False,
        }
        _write_json(args.receipt_out, receipt)
        print(json.dumps({"status": receipt["status"], "error": receipt["error"]["message"]}, sort_keys=True))
        return 1
    _write_json(args.receipt_out, receipt)
    print(json.dumps({"status": receipt["status"], "episodes": len(receipt["episodes"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
