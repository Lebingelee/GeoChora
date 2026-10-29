"""Compose the versioned, benchmark-specific deployment recipe."""
from __future__ import annotations

import hashlib
import json

from . import RECIPE_ID, RECIPE_SCHEMA
from .assembly import build_assembly
from .controller import build_controller
from .evaluation import build_evaluation
from .observation import build_observation
from .planner import build_planner
from .robot import build_robot
from .task import build_task


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def compose_recipe(manifest: dict, task_input: dict, binding: dict) -> dict:
    recipe = {
        "schema_version": RECIPE_SCHEMA,
        "recipe_id": RECIPE_ID,
        "source_binding": binding,
        "task": build_task(manifest),
        "robot": build_robot(task_input, manifest),
        "controller": build_controller(task_input),
        "planner": build_planner(task_input),
        "observation": build_observation(task_input),
        "assembly": build_assembly(task_input, manifest),
        "evaluation": build_evaluation(task_input, manifest),
        "recording": {
            "future_route": "same public Env: reset -> step -> observe -> existing recorder -> close -> independent reader on the same H5",
            "owner": "existing task_env recording/TransitionRecorder and versioned semantic reader",
            "episode_clock_binding": "T/T+1 observation-transition identity, action/ack/state/source identity",
            "status": "NOT_RUN; no H5 produced",
        },
        "admission": {
            "source_install_ready": True,
            "recipe_s1_ready": True,
            "core_native_admission_ready": False,
            "blocked_gates": [
                "MountedPanda seven torque motors plus two opposing finger-position actuators have no admitted Core controller/resource mapping.",
                "Selected .pruned_init ordering and realization into a Scene-v3 typed object/reset state are not validated by the Core public reset contract.",
                "On(bowl, plate) requires exact public contact and body poses; required contact remains unavailable.",
                "No native Core task construction, reset, meaningful public motion, semantic oracle, or H5 reader run was authorized in R07b.",
            ],
        },
        "cost_protocol_binding": task_input["cost_protocol_binding"],
        "scope": {
            "pilot_only": True,
            "original_five_task_r07_scope_preserved": True,
            "new_native_runs": 0,
            "r07b_full_five_task_exit": False,
            "accepted_slice_count_delta": 0,
            "qualification": False,
        },
    }
    recipe["recipe_sha256"] = hashlib.sha256(_canonical(recipe)).hexdigest()
    return recipe
