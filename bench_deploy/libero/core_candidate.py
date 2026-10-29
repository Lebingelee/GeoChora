"""Internal, provider-free R07c LIBERO Core Env candidate.

This module does not register a public make_env UID and does not admit a
physics provider. It connects the frozen static MJCF candidate through the
existing BaseTaskEnv compiler/lifecycle/recording owners for S1 only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
from typing import Any

import numpy as np

from task_env.environment import (
    AssetManifest,
    ContactSummary,
    InitialStateSpec,
    ReferenceSpec,
    TaskEvaluation,
    TaskEvaluationContextV1,
    TaskPredicateEvaluationV1,
    TaskPredicateResultV1,
)
from task_env.environment.configuration import resolve_env_config
from task_env.environment.env import BaseTaskEnv
from task_env.environment.protocols import AgentComponent, SceneBuilderComponent
from task_env.environment.task_definition import TaskDefinitionBase, as_task_state_view
from task_env.registry import AGENT_REGISTRY, SCENE_REGISTRY
from task_env.assembly.source import TaskSceneSource
from task_env.runtime.sessions.geophys_source import native_scene_source

from .evaluation import (
    PILOT_TASK_UID,
    OnBowlPlateEvidenceV1,
    evaluate_on_bowl_plate_v1,
)
from .task import PILOT_SOURCE_ID, LiberoPilotControlHookV1


SCENE_UID = "libero-pilot-source-scene-candidate-v1"
AGENT_UID = "libero-mounted-panda-v1"
_MANIFEST_SHA256 = PILOT_SOURCE_ID.removeprefix("libero-pilot-candidate:")


class LiberoPilotSceneComponent(SceneBuilderComponent):
    uid = SCENE_UID

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(owner_uid=self.uid, asset_kind="verified_source_composition")

    def reference_spec(self) -> ReferenceSpec:
        names = (
            "main_table", "akita_black_bowl_1", "akita_black_bowl_2", "cookies_1",
            "glazed_rim_porcelain_ramekin_1", "plate_1", "flat_stove_1",
            "wooden_cabinet_1", "panda_base", "robot__link0", "robot__link1",
            "robot__link2", "robot__link3", "robot__link4", "robot__link5",
            "robot__link6", "robot__link7", "robot__right_hand", "right_gripper",
            "eef", "gripper__leftfinger", "gripper__rightfinger",
        )
        return ReferenceSpec(body_names=names)


class LiberoMountedPandaAgent(AgentComponent):
    uid = AGENT_UID

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="verified_source_composition_agent",
            asset_version="libero-mounted-panda-pilot-source-v1",
            source_reference="libero/robosuite-mounted-panda",
            source_revision="8f1084e3132a39270c3a13ebe37270a43ece2a01:fbee5844ff5632f5b5698e204ec5357ca50be0df",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=(
                "panda_base", "robot__link0", "robot__link1", "robot__link2",
                "robot__link3", "robot__link4", "robot__link5", "robot__link6",
                "robot__link7", "robot__right_hand", "right_gripper", "eef",
                "gripper__leftfinger", "gripper__rightfinger",
            ),
            joint_names=tuple(f"joint{i}" for i in range(1, 8))
            + ("finger_joint1", "finger_joint2"),
            site_names=("grip_site",),
            actuator_names=tuple(f"torq_j{i}" for i in range(1, 8))
            + ("gripper_finger_joint1", "gripper_finger_joint2"),
        )

    def initial_state_spec(self) -> InitialStateSpec:
        # This is the pinned MountedPanda robot arm init_qpos, not the task's
        # .pruned_init row. The task initialization row remains unmapped.
        return InitialStateSpec(
            joint_positions=(
                ("joint1", 0.0), ("joint2", -0.161037389), ("joint3", 0.0),
                ("joint4", -2.44459747), ("joint5", 0.0), ("joint6", 2.22675220),
                ("joint7", float(np.pi / 4.0)),
            ),
            notes=("Pinned MountedPanda.init_qpos only; not LIBERO .pruned_init.",),
        )

    def supported_controller_kinds(self) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True)
class LiberoPilotSceneComposer:
    xml: str
    composed_mjcf_sha256: str
    install_root: Path
    source_manifest_sha256: str = _MANIFEST_SHA256

    def __post_init__(self) -> None:
        encoded = self.xml.encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != self.composed_mjcf_sha256:
            raise ValueError("composer XML does not match its frozen composition hash")
        if self.source_manifest_sha256 != _MANIFEST_SHA256:
            raise ValueError("composer source manifest differs from fixed pilot")

    def build_scene_source(self, composition, agents):
        del composition, agents
        source = TaskSceneSource(
            xml=self.xml,
            base_dir=self.install_root,
            source_id=f"libero-pilot-static-mjcf:{self.composed_mjcf_sha256}",
            diagnostics=(
                "static composed MJCF only; runtime placement and native IDs are unverified",
            ),
        )
        return native_scene_source(source), "libero_verified_static_mjcf_v2"

    def build_scene_model(self, imported_scene, composition):
        del composition
        return imported_scene.build_rigid_scene_model()


@dataclass(frozen=True)
class LiberoPilotTaskDefinitionV1(LiberoPilotControlHookV1):
    bowl_body_id: int
    plate_body_id: int

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("bowl_body_id", "plate_body_id"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
                raise ValueError(f"{name} must be a resolved non-negative body ID")
        if self.bowl_body_id == self.plate_body_id:
            raise ValueError("bowl and plate body IDs must be distinct")

    def _evaluation(self, context: TaskEvaluationContextV1) -> TaskPredicateResultV1:
        state = as_task_state_view(context.state)
        contact = state.contact_summary
        if contact is None:
            result = TaskPredicateResultV1.unavailable("contact_summary_not_requested")
        elif contact.status == "unavailable":
            result = TaskPredicateResultV1.unavailable(contact.reason or "contact_summary_unavailable")
        elif state.body_xpos is None:
            result = TaskPredicateResultV1.unavailable("body_pose_unavailable")
        else:
            poses = np.asarray(state.body_xpos)
            if poses.ndim != 2 or poses.shape[1] != 3:
                result = TaskPredicateResultV1.unavailable("body_pose_shape_unavailable")
            elif max(self.bowl_body_id, self.plate_body_id) >= len(poses):
                result = TaskPredicateResultV1.unavailable("resolved_body_id_out_of_snapshot_range")
            else:
                pair_key = "akita_black_bowl_1/plate_1"
                # A public available summary represents the queried entity
                # pairs; an absent key therefore means zero observed contacts.
                contact_count = contact.pair_counts.get(pair_key, 0)
                evidence = OnBowlPlateEvidenceV1(
                    task_uid=PILOT_TASK_UID,
                    source_manifest_sha256=_MANIFEST_SHA256,
                    frame_id="world",
                    bowl_center_m=tuple(float(x) for x in poses[self.bowl_body_id]),
                    plate_center_m=tuple(float(x) for x in poses[self.plate_body_id]),
                    geom_group_contact=bool(contact_count),
                )
                result = evaluate_on_bowl_plate_v1(
                    evidence,
                    expected_source_manifest_sha256=_MANIFEST_SHA256,
                )
        return result

    def evaluate_predicates(self, context: TaskEvaluationContextV1):
        if not isinstance(context, TaskEvaluationContextV1):
            raise TypeError("LIBERO candidate predicate evaluation requires TaskEvaluationContextV1")
        return TaskPredicateEvaluationV1.available({"on_bowl_plate": self._evaluation(context)})

    uses_unified_state_view = True

    def reset(self, *, state, reset_mask=None):
        del reset_mask
        view = as_task_state_view(state)
        result = self.evaluate_predicates(TaskEvaluationContextV1(state=view, elapsed_steps=0))
        predicate = result.predicates["on_bowl_plate"]
        success = bool(predicate.value) if predicate.status == "available" else False
        return TaskEvaluation(
            reward=1.0 if success else 0.0,
            success=success,
            metrics={"on_bowl_plate_available": predicate.status == "available"},
        )

    def evaluate(self, *, state, action, elapsed_steps, previous_state=None):
        del action, previous_state
        result = self.evaluate_predicates(
            TaskEvaluationContextV1(state=state, elapsed_steps=int(elapsed_steps))
        )
        predicate = result.predicates["on_bowl_plate"]
        success = bool(predicate.value) if predicate.status == "available" else False
        return TaskEvaluation(
            reward=1.0 if success else 0.0,
            success=success,
            metrics={"on_bowl_plate_available": predicate.status == "available"},
        )


class LiberoPilotCandidateEnv(BaseTaskEnv):
    uid = "libero-pilot-env-internal-candidate-v1"
    task_uid = PILOT_TASK_UID
    scene_uid = SCENE_UID
    agent_uids = (AGENT_UID,)
    object_uids = ()
    success_definition = "LIBERO On(bowl,plate) candidate; static source tree only"
    supports_structured_control_recording = True

    def __init__(self, *, composer: LiberoPilotSceneComposer, build_runtime: bool = True):
        self._libero_composer = composer
        super().__init__(config=self.default_config(), build_runtime=build_runtime)

    @classmethod
    def default_config(cls):
        return resolve_env_config(
            task_uid=cls.task_uid,
            scene_uid=cls.scene_uid,
            agent_uids=cls.agent_uids,
            object_uids=(),
            success_definition=cls.success_definition,
            runtime={"backend": "cpu", "physics_dt": 0.002, "control_substeps": 25, "prewarm": False},
            episode={"horizon": 1, "ignore_done": False},
        )

    def create_scene_composer(self):
        return self._libero_composer

    def reference_profile(self):
        return {
            "schema_version": "libero-pilot-source-control-profile-v1",
            "source_id": PILOT_SOURCE_ID,
            "composed_mjcf_sha256": self._libero_composer.composed_mjcf_sha256,
            "provider_admission": "NOT_ADMITTED",
        }

    def create_task_definition(self, compiled_scene):
        names = compiled_scene.references.names.bodies
        try:
            bowl_id = names["akita_black_bowl_1"]
            plate_id = names["plate_1"]
        except KeyError as exc:
            raise ValueError(f"composed candidate semantic body is unresolved: {exc.args[0]}") from exc
        return LiberoPilotTaskDefinitionV1(
            source_id=PILOT_SOURCE_ID,
            source_xml_sha256=self._libero_composer.composed_mjcf_sha256,
            agent_uid=AGENT_UID,
            servo_config=_candidate_servo_config(),
            bowl_body_id=bowl_id,
            plate_body_id=plate_id,
        )

    def _format_step_result(self, lifecycle, result):
        """Add the existing typed v3 recording value for this one candidate writer."""
        observation, reward, terminated, truncated, info = super()._format_step_result(
            lifecycle, result,
        )
        if self._action_adapter is None:
            raise RuntimeError("LIBERO candidate structured recording requires its mixed adapter")
        from task_env.controllers.canonical.contracts import (
            ControlGroupActionV1,
            StructuredActionRequestV1,
        )
        from task_env.trajectory.canonical.episode import StructuredControlTransitionV1

        mapping = self._action_adapter.mapping
        action_spec = self._action_adapter.action_contract
        components = tuple(action_spec.components)
        values = tuple(float(value) for value in np.asarray(result.command.requested_action))
        if len(components) != 8 or len(values) != len(components):
            raise ValueError("candidate structured action must retain seven joints and opening_m")
        request = StructuredActionRequestV1(
            "structured-action-request-v1",
            self._libero_composer.composed_mjcf_sha256,
            mapping.identity_hash,
            (ControlGroupActionV1(
                "control-group-action-v1",
                "libero-panda",
                "mixed-actuation",
                action_spec.schema_id,
                values,
            ),),
        )
        request.validate()
        target_payload = {
            "schema_version": "libero-mixed-control-target-v1",
            "source_id": mapping.source_id,
            "composed_mjcf_sha256": mapping.source_xml_sha256,
            "mapping_identity_sha256": mapping.identity_hash,
            "action_values": values,
            "requested_ctrl": tuple(float(value) for value in result.applied.requested_ctrl),
        }
        target_hash = hashlib.sha256(json.dumps(
            target_payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        applied_payload = {
            "schema_version": "libero-mixed-applied-control-v1",
            "requested_ctrl": tuple(float(value) for value in result.applied.requested_ctrl),
            "applied_ctrl": tuple(float(value) for value in result.applied.applied_ctrl),
            "clipped": bool(result.applied.clipped),
            "native_status": "synthetic_s1_leaf_io",
        }
        group_projection = ({
            "entity_id": "libero-panda",
            "group_id": "mixed-actuation",
            "action_components": components,
        },)
        transition = StructuredControlTransitionV1(
            "structured-control-transition-v1",
            request,
            ({
                "writer_id": "libero-mounted-panda-mixed-writer-v1",
                "action_schema_id": action_spec.schema_id,
                "components": components,
                "groups": group_projection,
                "requested_action": {
                    "schema_version": action_spec.schema_id,
                    "values": values,
                    "unit": "radian_arm_and_meter_opening",
                    "provenance": "candidate_provider_free_s1",
                },
                "canonical_action": {
                    "schema_version": "libero-mixed-canonical-action-v1",
                    "interpreted_values": values,
                    "mapping_identity_sha256": mapping.identity_hash,
                    "gain_status": self._action_adapter.config.gain_status,
                },
                "controller_target": {
                    "schema_version": target_payload["schema_version"],
                    "payload": target_payload,
                    "identity_hash": target_hash,
                },
                "applied_control": {
                    "schema_version": applied_payload["schema_version"],
                    "payload": applied_payload,
                    "target_hash": target_hash,
                },
            },),
        )
        transition.validate()
        info = dict(info)
        info["structured_control_transition"] = transition
        return observation, reward, terminated, truncated, info


def _candidate_servo_config():
    from task_env.controllers.mounted_panda_mixed import MountedPandaServoConfigV1

    return MountedPandaServoConfigV1(
        kp_Nm_per_rad=(1.0,) * 7,
        kd_Nm_s_per_rad=(0.1,) * 7,
        gain_status="synthetic_s1_fixture",
    )


def build_libero_pilot_env(*, xml: str, composed_mjcf_sha256: str, install_root: Path, build_runtime: bool = True):
    """Construct the internal candidate using existing TaskEnv owners."""
    # Load existing component modules before adding the two task-local candidate
    # descriptions; this does not register an environment UID with make_env.
    import task_env.robots  # noqa: F401
    import task_env.tasks.worlds  # noqa: F401
    if not issubclass(LiberoMountedPandaAgent, AgentComponent):
        raise TypeError("candidate agent must implement the Core AgentComponent owner")
    if not issubclass(LiberoPilotSceneComponent, SceneBuilderComponent):
        raise TypeError("candidate scene must implement the Core SceneBuilderComponent owner")
    if AGENT_UID not in AGENT_REGISTRY.uids():
        AGENT_REGISTRY.register(AGENT_UID, LiberoMountedPandaAgent)
    if SCENE_UID not in SCENE_REGISTRY.uids():
        SCENE_REGISTRY.register(SCENE_UID, LiberoPilotSceneComponent)
    composer = LiberoPilotSceneComposer(
        xml=xml,
        composed_mjcf_sha256=composed_mjcf_sha256,
        install_root=Path(install_root),
    )
    return LiberoPilotCandidateEnv(composer=composer, build_runtime=build_runtime)


__all__ = [
    "LiberoPilotCandidateEnv",
    "LiberoPilotSceneComposer",
    "LiberoPilotTaskDefinitionV1",
    "build_libero_pilot_env",
]
