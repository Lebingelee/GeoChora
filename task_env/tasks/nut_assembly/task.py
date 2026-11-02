"""NutAssembly reset, feedback observations, and task evaluation semantics."""
from __future__ import annotations

import hashlib
import math
import numpy as np

from ...artifacts import CanonicalStateView, SemanticDefinition, TaskArtifact
from ...artifacts.execution import ResetSample
from ...objects.nut_assembly import NUT_HALF_HEIGHT, NUT_HANDLE_LOCAL_X
from ...utils.rotation import quat_wxyz_to_matrix
from .solution import NutAssemblyNativeFeedbackSampleV1, NutAssemblyNativeIntervalReceiptV1

EEF = "panda-v1/ee"
NUT = "square-nut-v1"
PEG = "square-peg-v1"
FINGERS = ("panda-v1/finger_joint1", "panda-v1/finger_joint2")
SUCCESS = "nut_on_square_peg_canonical_state_v0"

def semantic_definition(*, lift_height_m=None) -> SemanticDefinition:
    recipe = _recipe()
    p = recipe["semantic_parameters"]
    scene = recipe["scene"]
    return SemanticDefinition("semantics-v0", "nut_assembly_state_v0",
        (NUT, PEG, EEF), FINGERS,
        {**{key: float(value) for key, value in p.items()},
         "lift_height": float(p["lift_height"] if lift_height_m is None else lift_height_m),
         "table_top_z": float(scene["table_top_z"]),
         "nut_half_height": float(NUT_HALF_HEIGHT),
         "nut_contact_margin": float(recipe["asset"]["nut_contact_margin_m"]),
         "nut_handle_local_x": float(NUT_HANDLE_LOCAL_X),
         "peg_half_height": float(scene["peg_half_height"])}, SUCCESS)


def evaluate(state: CanonicalStateView, semantics: SemanticDefinition | None = None, *, lift_height_m=None):
    from ...environment import TaskEvaluation
    expected = semantic_definition(lift_height_m=lift_height_m)
    semantics = expected if semantics is None else semantics
    if not isinstance(state, CanonicalStateView) or semantics != expected:
        raise ValueError("unsupported canonical NutAssembly state/semantics")
    semantics.require_state(state)
    p = semantics.parameters_si
    nut, peg = state.pose_world[NUT], state.pose_world[PEG]
    position = np.asarray(nut.position)
    ee = np.asarray(state.pose_world[EEF].position)
    rotation = quat_wxyz_to_matrix(nut.quaternion_wxyz)
    handle = position + rotation @ np.array([p["nut_handle_local_x"], 0.0, 0.0])
    yaw = float(np.arctan2(rotation[1, 0], rotation[0, 0]))
    period = 0.5 * np.pi
    yaw_error = abs((yaw + 0.5 * period) % period - 0.5 * period)
    xy_error = float(np.linalg.norm(position[:2] - np.asarray(peg.position[:2])))
    z_error = float(position[2] - (p["table_top_z"] + p["nut_half_height"] + p["nut_contact_margin"]))
    ee_distance = float(np.linalg.norm(ee - position))
    handle_distance = float(np.linalg.norm(ee - handle))
    opening = float(sum(state.joint_position[name] for name in FINGERS))
    reached = handle_distance <= p["grasp_distance"]
    grasped = bool(reached and opening <= p["gripper_closed_opening"])
    lifted = bool(position[2] >= p["table_top_z"] + p["nut_half_height"] + p["lift_height"])
    hover = bool(lifted and xy_error <= p["hover_xy_tolerance"])
    aligned = bool(xy_error <= p["insert_xy_tolerance"] and yaw_error <= p["insert_yaw_tolerance"])
    passed = bool(position[2] <= peg.position[2] + p["peg_half_height"] - p["nut_contact_margin"])
    returned = bool(position[2] <= p["table_top_z"] + 3 * p["nut_half_height"])
    inserted = bool(aligned and passed and returned)
    gripper_released = bool(opening >= p["gripper_release_opening"])
    released = bool(inserted and gripper_released and ee_distance >= p["release_distance"])
    success = bool(inserted and released)
    metrics = {
        "reached_nut": bool(reached), "grasped_nut": bool(grasped),
        "lifted_nut": bool(lifted), "hovered_over_peg": bool(hover),
        "aligned_with_peg": bool(aligned), "peg_passed_through_nut_center": bool(passed),
        "nut_returned_to_table": bool(returned), "inserted_on_peg": bool(inserted),
        "gripper_released": bool(gripper_released), "released_nut": bool(released),
        "task_success": bool(success), "nut_x": float(position[0]),
        "nut_y": float(position[1]), "nut_z": float(position[2]), "nut_yaw": yaw,
        "table_seated_nut_max_z": p["table_top_z"] + 3 * p["nut_half_height"],
        "peg_xy_error": xy_error, "peg_z_error": z_error, "yaw_error": yaw_error,
        "eef_to_nut_dist": ee_distance, "eef_to_handle_dist": handle_distance,
        "gripper_opening": opening, "success_definition": True,
    }
    terms = {"reach": 0.10 * (1.0 - math.tanh(10.0 * handle_distance)),
             "grasp": 0.25 if grasped else 0.0, "lift": 0.25 if lifted else 0.0,
             "hover": 0.15 if hover else 0.0, "insert": 0.15 if inserted else 0.0,
             "release": 0.10 if released else 0.0, "success": 1.0 if success else 0.0}
    return TaskEvaluation(reward=float(sum(terms.values())), success=success,
        failure=False, metrics=metrics, reward_terms=terms)


def sample_reset(artifact: TaskArtifact, task_seed: int = 19, *, lift_height_m=None) -> ResetSample:
    expected = build_artifact(lift_height_m=lift_height_m)
    if not isinstance(artifact, TaskArtifact) or artifact.to_mapping() != expected.to_mapping():
        raise ValueError("selected NA-S0 TaskArtifact required")
    if type(task_seed) is not int or task_seed != 19:
        raise ValueError("selected NA-S0 uses fixed provenance seed19")
    initialization = artifact.initialization
    return ResetSample.create(schema_version="reset-sample-v0",
        task_artifact_hash=artifact.identity_hash, sampler_id=_recipe()["reset"]["sampler_id"],
        sampler_version=_recipe()["reset"]["sampler_version"], task_seed=task_seed,
        joint_position=dict(initialization.joint_position), poses_world=dict(initialization.poses_world),
        velocity_policy=_recipe()["reset"]["inherited_state_policy"],
        control_policy=_recipe()["reset"]["control_policy"],
        settle_steps=int(_recipe()["reset"]["settle_steps"]))


def _reset_seed(seed):
    if seed not in (19, None):
        raise ValueError("selected NutAssembly NA-S0 has fixed provenance seed19")
    return 19 if seed is None else seed


def _native_feedback_sample(env, stage, index, state, feedback, target, applied, diagnostics,
                            provider_feedback_sample, request_boundary):
    metrics = None
    if stage == "close_gripper":
        _, observation_info, _ = env.observation(state)
        metrics = observation_info["task_metrics"]
    ee = state.pose_world["panda-v1/ee"]
    sample = NutAssemblyNativeFeedbackSampleV1(
        "nutassembly-native-feedback-sample-v1",
        env.provider,
        provider_feedback_sample.provider_materialization_id,
        env.artifact.identity_hash,
        env.value["source"].scene_source.source_id,
        hashlib.sha256(env.value["source"].scene_source.xml.encode()).hexdigest(),
        request_boundary["controller_identity"],
        request_boundary["solution_identity"],
        request_boundary["episode_id"],
        request_boundary["reset_sample_id"],
        request_boundary["identity_hash"],
        float(state.simulation_time),
        int(state.control_step),
        int(index),
        int(provider_feedback_sample.actuator_force_measurement.sample_sequence),
        float(provider_feedback_sample.actuator_force_measurement.native_sample_time_s),
        float(env.artifact.timebase.physics_dt),
        str(provider_feedback_sample.actuator_force_measurement.phase),
        "valid" if provider_feedback_sample.actuator_force_measurement.valid else "invalid",
        tuple((*ee.position, *ee.quaternion_wxyz)),
        feedback,
        dict(diagnostics),
        provider_feedback_sample,
        target.identity_hash,
        applied.to_mapping(),
        None if metrics is None else bool(metrics.get("grasped_nut", False)),
    )
    return sample


def _native_interval_receipt(env, request_boundary, evaluation_boundary, native_samples, substeps):
    expected = env.artifact.timebase.control_substeps
    if expected != 5 or len(native_samples) != expected or len(substeps) != expected:
        raise ValueError("NutAssembly native interval requires five completed 2 ms applications")
    if tuple(index for index, _, _ in substeps) != tuple(range(expected)):
        raise ValueError("NutAssembly native interval substeps are missing or out of order")
    return NutAssemblyNativeIntervalReceiptV1(
        "nutassembly-native-interval-receipt-v1",
        env.provider,
        request_boundary["provider_materialization_id"],
        env.artifact.identity_hash,
        env.value["source"].scene_source.source_id,
        hashlib.sha256(env.value["source"].scene_source.xml.encode()).hexdigest(),
        request_boundary["controller_identity"],
        request_boundary["solution_identity"],
        request_boundary["episode_id"],
        request_boundary["reset_sample_id"],
        request_boundary,
        evaluation_boundary,
        float(env.artifact.timebase.physics_dt),
        expected,
        len(native_samples),
        tuple(native_samples),
    )


def _observe_kwargs(env, native_samples, receipt):
    if not isinstance(receipt, NutAssemblyNativeIntervalReceiptV1):
        raise ValueError("NutAssembly Solution observation requires a completed native interval receipt")
    return {"readiness": env.controller.readiness(env.state, env.feedback),
        "native_samples": tuple(native_samples),
        "native_interval_receipt": receipt}


# Existing imports remain a thin bridge while repository callers migrate.
from .specialization import (
    NutAssemblyReferenceEnv, REFERENCE_ENV_ID, R05B_NATIVE_FEEDBACK_PROFILE,
    _configuration, _recipe, build_artifact, build_reference, build_runtime_source,
    build_outcome_solution, build_gripper_cadence_diagnostic_reference,
    build_gripper_cadence_diagnostic_solution, build_native_feedback_reference,
    build_native_feedback_solution,
)

__all__ = ["NutAssemblyReferenceEnv", "REFERENCE_ENV_ID", "build_artifact",
           "build_reference", "build_outcome_solution", "build_runtime_source", "evaluate",
           "sample_reset", "semantic_definition", "build_gripper_cadence_diagnostic_reference",
           "build_gripper_cadence_diagnostic_solution", "build_native_feedback_reference",
           "build_native_feedback_solution", "R05B_NATIVE_FEEDBACK_PROFILE"]
