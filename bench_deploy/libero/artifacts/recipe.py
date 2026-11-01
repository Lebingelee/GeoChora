"""Compose the versioned, benchmark-specific deployment recipe."""
from __future__ import annotations

import hashlib
import json

from bench_deploy.libero import RECIPE_ID, RECIPE_SCHEMA
from bench_deploy.libero.assembly.composition import build_assembly
from bench_deploy.libero.controllers.osc import build_diagnostic_joint_pd_plan
from bench_deploy.libero.tasks.predicates import build_evaluation
from bench_deploy.libero.observations.libero import build_observation
from bench_deploy.libero.planners.libero import build_planner
from bench_deploy.libero.robots.mounted_panda import build_robot
from bench_deploy.libero.tasks.recipe import build_task


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def compose_recipe(manifest: dict, task_input: dict, binding: dict) -> dict:
    recipe = {
        "schema_version": RECIPE_SCHEMA,
        "recipe_id": RECIPE_ID,
        "source_binding": binding,
        "task": build_task(manifest),
        "robot": build_robot(task_input, manifest),
        "controller": build_diagnostic_joint_pd_plan(task_input),
        "planner": build_planner(task_input),
        "observation": build_observation(task_input),
        "assembly": build_assembly(task_input, manifest),
        "evaluation": build_evaluation(task_input, manifest),
        "recording": {
            "future_route": "same public Env: reset -> step -> observe -> existing recorder -> close -> independent reader on the same H5",
            "owner": "existing task_env recording/TransitionRecorder and versioned semantic reader",
            "episode_clock_binding": "T/T+1 observation-transition identity, action/ack/state/source identity",
            "status": "recipe_only_no_new_recording_run",
        },
        "accepted_scope": {
            "status": "ACCEPTED_BOUNDED_R07_A123_TECHNICAL",
            "tasks": ["task1", "task2", "task3"],
            "providers": ["mujoco", "geophys"],
            "backend": "cpu",
            "meaning": "frozen A-stage environment and upstream-control-flow evidence only",
            "reference_control": {
                "profile_id": "libero-spatial-bowl-to-plate-robosuite-osc-pose-qfrc-bias-v1",
                "gripper_profile_id": "robosuite-panda-gripper-delta-v1",
                "optional_improved_controller": "libero-spatial-bowl-to-plate-osc-pose-velocity-feedforward-qfrc-bias-v1",
                "optional_solution_schema": "libero-bowl-to-plate-solution-v8",
            },
            "task2_geophys_precontact_exception": {
                "decision": "accepted_for_this_frozen_a_stage_source_controller_action_sequence_only",
                "first_upstream_finger_cabinet_contact_action": 82,
                "geophys_vs_upstream_tcp_position_p95_max_mm": [33.143, 37.916],
                "geophys_vs_upstream_tcp_orientation_p95_max_mrad": [229.074, 259.412],
                "geophys_vs_mujoco_tcp_position_p95_max_mm": [33.100, 37.721],
                "geophys_vs_mujoco_tcp_orientation_p95_max_mrad": [226.906, 257.160],
                "general_provider_parity": False,
                "task_success": False,
            },
            "task_success": False,
            "qualification": False,
        },
        "limits": {
            "registered_task_route": False,
            "file_specific_asset_license_or_attribution": "unresolved",
            "high_precision_tracking": "optional_follow_up",
            "autonomous_solution_success": "optional_follow_up_not_established",
            "tasks_b_and_c": "deferred",
            "isaac_sim": "deferred",
        },
        "cost_protocol_binding": task_input["cost_protocol_binding"],
        "scope": {
            "new_native_runs": 0,
            "full_r07_exit": False,
            "accepted_slice_count_delta": 0,
            "task_success": False,
            "qualification": False,
        },
    }
    recipe["recipe_sha256"] = hashlib.sha256(_canonical(recipe)).hexdigest()
    return recipe
