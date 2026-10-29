"""F04 candidate construction and public action helpers for provider-free S1."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[3]
BASE = REPO / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001"
EVIDENCE = BASE / "f04_003/evidence"
if str(EVIDENCE) not in sys.path:
    sys.path.insert(0, str(EVIDENCE))
from build_f04_candidates import build as _build_candidate  # noqa: E402


def build_candidate(family):
    return _build_candidate(family)


def _native_order(source):
    values = tuple(source.joint_targets.values())
    if len(values) != 9 or len(set(values)) != 9:
        raise ValueError("S1 metadata order requires exactly nine source-bound native DOFs")
    order = (7, 3, 8, 0, 6, 2, 5, 1, 4)
    return tuple(values[index] for index in order)


def _limits(source):
    canonical = {
        "panda-main/joint1": (-2.8973000049591064, 2.8973000049591064),
        "panda-main/joint2": (-1.7627999782562256, 1.7627999782562256),
        "panda-main/joint3": (-2.8973000049591064, 2.8973000049591064),
        "panda-main/joint4": (-3.0717999935150146, -0.0697999969124794),
        "panda-main/joint5": (-2.8973000049591064, 2.8973000049591064),
        "panda-main/joint6": (-0.017500000074505806, 3.752500057220459),
        "panda-main/joint7": (-2.8973000049591064, 2.8973000049591064),
        "panda-main/finger_joint1": (0.0, 0.03999999910593033),
        "panda-main/finger_joint2": (0.0, 0.03999999910593033),
    }
    return {native: canonical[semantic] for semantic, native in source.joint_targets.items()}


def _home():
    return {
        "panda-main/joint1": 0.012,
        "panda-main/joint2": -0.568,
        "panda-main/joint3": 0.0,
        "panda-main/joint4": -2.811,
        "panda-main/joint5": 0.0,
        "panda-main/joint6": 3.037,
        "panda-main/joint7": 0.741,
        "panda-main/finger_joint1": 0.03999999910593033,
        "panda-main/finger_joint2": 0.03999999910593033,
    }


def _action_for(env, interval):
    from task_env.controllers.canonical.contracts import (
        ControlGroupActionV1, StructuredActionRequestV1,
    )

    current = {item.joint_id: float(item.position[0])
               for item in env.typed_state.view.joints if item.entity_id == "panda-main"}
    goal = [current[f"joint{i}"] for i in range(1, 8)]
    direction = 1.0 if interval in (0, 3) else -1.0
    goal[0] += direction * 0.045
    goal[1] -= direction * 0.025
    goal[3] += direction * 0.02
    pose = env.controller.model.pose(goal)
    schema = env.controller.controller_binding().action_schema
    return StructuredActionRequestV1(
        "structured-action-request-v1", env.position_plan.scene_identity_hash,
        env.position_plan.identity_hash,
        (
            ControlGroupActionV1(
                "control-group-action-v1", "panda-main", "arm", schema.schema_id,
                (*pose.position, *pose.quaternion_wxyz),
            ),
            ControlGroupActionV1(
                "control-group-action-v1", "panda-main", "gripper", schema.schema_id,
                (1.0 if interval in (0, 3) else 0.25,),
            ),
        ),
    )
