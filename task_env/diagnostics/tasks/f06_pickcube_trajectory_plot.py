"""Plot F06 PickCube seed-31 planned and measured TCP from recorded H5 data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import h5py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def _finite_array(value, label: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if not np.isfinite(array).all():
        raise ValueError(f"{label} contains non-finite values")
    return array


def _failure_label(run: dict) -> str:
    episode = run.get("episode") or {}
    outcome = run.get("task_outcome") or {}
    return str(
        episode.get("failure_reason")
        or outcome.get("failure_reason")
        or run.get("failure_reason")
        or ("task success" if run.get("task_success") else "task/expert result not reported")
    )


def _read_geophys(h5_path: Path, run_path: Path) -> dict:
    run = json.loads(run_path.read_text())
    with h5py.File(h5_path, "r") as root:
        if root.attrs.get("schema") != "task-env-canonical-trajectory-v0":
            raise ValueError("GeoPhys H5 is not the expected canonical trajectory schema")
        logical = json.loads(root["logical_json"].asstr()[()])
    transitions = logical["transitions"]
    boundaries = logical["boundaries"]
    if len(boundaries) != len(transitions) + 1:
        raise ValueError("GeoPhys trajectory does not have T+1 state boundaries")
    planned = _finite_array([
        transition["canonical_action"]["resolved_world_pose"]["position"]
        for transition in transitions
    ], "GeoPhys planned TCP")
    measured = _finite_array([
        boundary["state"]["pose_world"]["panda-v1/ee"]["position"]
        for boundary in boundaries[1:]
    ], "GeoPhys measured public EE pose")
    opening = _finite_array([
        boundary["feedback"]["gripper"]["opening_m"]
        for boundary in boundaries[1:]
    ], "GeoPhys measured gripper opening")
    times = _finite_array([boundary["simulation_time"] for boundary in boundaries[1:]],
                          "GeoPhys simulation time")
    return {
        "planned": planned, "measured": measured, "opening": opening, "times": times,
        "transitions": len(transitions), "failure": _failure_label(run),
        "source_revision": run.get("source_revision", "unknown"),
        "recipe_identity": run.get("recipe_identity", "unknown"),
        "h5_sha256": hashlib.sha256(h5_path.read_bytes()).hexdigest(),
    }


def _read_isaac(h5_path: Path, run_path: Path) -> dict:
    run = json.loads(run_path.read_text())
    with h5py.File(h5_path, "r") as root:
        if (root.attrs.get("schema_id"), root.attrs.get("schema_version")) != ("task-env-h5", "v3"):
            raise ValueError("Isaac H5 is not the expected task-env-h5/v3 schema")
        transitions = int(root.attrs["transition_count"])
        observations = int(root.attrs["observation_count"])
        if observations != transitions + 1:
            raise ValueError("Isaac H5 does not have T+1 observations")
        planned = _finite_array(np.column_stack([
            np.asarray(root[f"action/{axis}"]).reshape(-1) for axis in ("x", "y", "z")
        ]), "Isaac planned TCP")
        measured = _finite_array(np.asarray(root["obs/state/ee_pose"])[1:, :3],
                                 "Isaac measured public EE pose")
        opening = _finite_array(np.asarray(root["info/task_metrics/gripper_opening"]).reshape(-1),
                                "Isaac measured gripper opening")
    if planned.shape != measured.shape or len(opening) != transitions:
        raise ValueError("Isaac TCP/opening arrays do not align with recorded transitions")
    times = (np.arange(transitions, dtype=np.float64) + 1.0) * float(run.get("physics_dt_s", 0.002)) * int(run.get("control_substeps", 5))
    return {
        "planned": planned, "measured": measured, "opening": opening, "times": times,
        "transitions": transitions, "failure": _failure_label(run),
        "source_revision": run.get("source_revision", "unknown"),
        "recipe_identity": run.get("recipe_identity", "unknown"),
        "h5_sha256": hashlib.sha256(h5_path.read_bytes()).hexdigest(),
    }


def make_plot(*, geophys_h5: Path, geophys_run: Path, isaac_h5: Path,
              isaac_run: Path, output: Path) -> dict:
    routes = {
        "GeoPhys CPU": _read_geophys(geophys_h5, geophys_run),
        "Isaac Sim 6.2 / CUDA PhysX": _read_isaac(isaac_h5, isaac_run),
    }
    colors = ("tab:blue", "tab:orange", "tab:green")
    fig, axes = plt.subplots(2, 3, figsize=(18, 8), sharex="col")
    fig.suptitle(
        "F06 PickCube seed 31 — planned world TCP vs post-step public EE pose\n"
        "R3 continuous profile · 10 ms/control tick · gripper opening in metres",
        fontsize=14,
    )
    for column, (provider, data) in enumerate(routes.items()):
        position_ax = axes[0, column]
        opening_ax = axes[1, column]
        for axis_index, axis_name in enumerate(("x", "y", "z")):
            color = colors[axis_index]
            position_ax.plot(data["times"], data["planned"][:, axis_index],
                             color=color, linestyle="--", linewidth=1.1,
                             label=f"{axis_name} target")
            position_ax.plot(data["times"], data["measured"][:, axis_index],
                             color=color, linewidth=1.1, label=f"{axis_name} measured")
        position_ax.set_title(f"{provider} · T={data['transitions']}\n"
                              f"recipe {data['recipe_identity'][:12]} · source {data['source_revision'][:8]}")
        position_ax.set_ylabel("TCP position (m)")
        position_ax.grid(True, alpha=0.25)
        position_ax.legend(fontsize=7, ncol=2, loc="best")
        position_ax.text(0.02, 0.02, f"reported: {data['failure']}",
                         transform=position_ax.transAxes, fontsize=8,
                         va="bottom", bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none"})
        opening_ax.plot(data["times"], data["opening"], color="tab:purple", linewidth=1.1)
        opening_ax.set_xlabel("Episode time (s)")
        opening_ax.set_ylabel("Measured opening (m)")
        opening_ax.grid(True, alpha=0.25)

    mujoco_ax, opening_ax = axes[0, 2], axes[1, 2]
    mujoco_ax.clear()
    mujoco_ax.set_title("MuJoCo CPU · R3 continuous\nseed31 gate failed; seeds32/33 not run")
    mujoco_ax.text(
        0.5, 0.5,
        "QACC DOF13 execution fault at 0.448 s\n"
        "No F06 R3 H5 was produced.\n"
        "R1 diagnostic H5 excluded by maintainer decision.",
        ha="center", va="center", wrap=True, transform=mujoco_ax.transAxes,
    )
    mujoco_ax.set_xticks([]); mujoco_ax.set_yticks([])
    mujoco_ax.set_xlabel("No F06 R3 trajectory")
    opening_ax.clear()
    opening_ax.set_title("Gripper opening")
    opening_ax.text(0.5, 0.5, "No F06 R3 H5", ha="center", va="center",
                    transform=opening_ax.transAxes)
    opening_ax.set_xticks([]); opening_ax.set_yticks([])
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return {
        "output": str(output),
        "routes": {provider: {k: v[k] for k in ("transitions", "failure", "source_revision", "recipe_identity", "h5_sha256")}
                   for provider, v in routes.items()},
        "mujoco": {"status": "FAILED_R3_QACC_GATE", "seed31_failure_s": 0.448,
                   "r1_h5_used": False},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geophys-h5", type=Path, required=True)
    parser.add_argument("--geophys-run", type=Path, required=True)
    parser.add_argument("--isaac-h5", type=Path, required=True)
    parser.add_argument("--isaac-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = make_plot(geophys_h5=args.geophys_h5, geophys_run=args.geophys_run,
                        isaac_h5=args.isaac_h5, isaac_run=args.isaac_run,
                        output=args.output)
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
