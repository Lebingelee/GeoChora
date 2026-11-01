"""Franka Panda 的纯描述组件。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from ..utils._paths import MUJOCO_MENAGERIE_ROOT
from ..environment import AssetManifest, InitialStateSpec, ReferenceSpec
from ..artifacts import (
    ActuatorReference,
    ActuatorResourceDefinition,
    ArticulationDefinition,
    ControlGroup,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    JointDefinition,
    PoseWorld,
    RobotInstance,
    SceneDefinition,
)
from ..assembly.assets import _asset_definition_from_manifest, _source_closure_digest
from ..registry import register_agent
from .base import BaseAgent
from .gripper import ExperimentalPandaGripperController, PandaGripperController
from ..utils.rotation import matrix_to_quat_wxyz


PANDA_ASSET_ROOT = MUJOCO_MENAGERIE_ROOT / "franka_emika_panda"


@register_agent("panda-v1")
class PandaAgent(BaseAgent):
    uid = "panda-v1"

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="agent_mjcf",
            mjcf_sources=(PANDA_ASSET_ROOT / "panda.xml",),
            asset_roots=(PANDA_ASSET_ROOT,),
            asset_version="mujoco-menagerie-panda",
            source_reference="mujoco-menagerie://franka_emika_panda/panda.xml",
            source_revision="b846dd12bc459d776cccb3dee0b1d02acbf7a9c7",
        )

    def _scene_definition(
        self, *, entity_id: str | None = None, scene_id: str | None = None,
    ) -> SceneDefinition:
        """Build the Panda Scene from its declared MJCF through GeoPhys' importer."""

        manifest = self.asset_manifest()
        if len(manifest.mjcf_sources) != 1 or len(manifest.asset_roots) != 1:
            raise ValueError("Panda Scene construction requires one declared MJCF root")
        from scene import SceneSource, import_scene_source

        imported = import_scene_source(
            SceneSource.mjcf_path(
                manifest.mjcf_sources[0],
                label=f"{self.uid}:{manifest.source_revision}",
            ),
            cache=False,
        )
        root = manifest.asset_roots[0].resolve(strict=True)
        files = {}
        for raw_path in imported.dependency_paths:
            path = Path(raw_path).resolve(strict=True)
            try:
                logical_path = path.relative_to(root).as_posix()
            except ValueError as exc:
                raise ValueError(
                    f"Panda importer dependency escaped its declared asset root: {path}"
                ) from exc
            files[logical_path] = path.read_bytes()
        if not files:
            raise ValueError("Panda importer returned an empty source closure")
        return _panda_scene_from_import(
            imported,
            manifest,
            entity_id=self.uid if entity_id is None else entity_id,
            scene_id=self.uid if scene_id is None else scene_id,
            source_content_sha256=_source_closure_digest(files),
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=("link0", "hand", "left_finger", "right_finger"),
            joint_names=(
                "joint1",
                "joint2",
                "joint3",
                "joint4",
                "joint5",
                "joint6",
                "joint7",
                "finger_joint1",
                "finger_joint2",
            ),
            site_names=("nutassembly_ee_site",),
            actuator_names=(
                "actuator1",
                "actuator2",
                "actuator3",
                "actuator4",
                "actuator5",
                "actuator6",
                "actuator7",
                "actuator8",
            ),
        )

    def initial_state_spec(self) -> InitialStateSpec:
        return InitialStateSpec(
            joint_positions=(
                ("joint1", -0.17),
                ("joint2", 0.0),
                ("joint3", 0.0),
                ("joint4", -1.57079),
                ("joint5", 0.0),
                ("joint6", 1.57079),
                ("joint7", -0.7853),
                ("finger_joint1", 0.04),
                ("finger_joint2", 0.04),
            ),
            notes=("Stage 1 must resolve these names to qpos addresses.",),
        )

    def supported_controller_kinds(self) -> tuple[str, ...]:
        return (
            "absolute_joint",
            "absolute_pose",
            "delta_pose",
        )

    def create_gripper_controller(
        self,
        *,
        references,
        config,
        kind: str = "experimental_rate_limited",
        force_limit_N: float = 30.0,
        opening_step_m: float = 0.002,
        force_deadband_N: float = 1.0,
        force_adjust_step_m: float = 1.0e-4,
    ) -> PandaGripperController:
        """Create the selected Panda gripper controller after references resolve."""

        if kind == "experimental_rate_limited":
            return ExperimentalPandaGripperController(
                references=references,
                config=config,
                force_limit_N=force_limit_N,
                max_opening_step_m=opening_step_m,
                force_deadband_N=force_deadband_N,
                force_adjust_step_m=force_adjust_step_m,
            )
        if kind != "legacy":
            raise ValueError(f"unsupported Panda gripper controller kind {kind!r}")
        return PandaGripperController(
            references=references,
            config=config,
            force_limit_N=force_limit_N,
        )


__all__ = ["PANDA_ASSET_ROOT", "PandaAgent"]


def _panda_scene_from_import(
    imported,
    manifest: AssetManifest,
    *,
    entity_id: str,
    scene_id: str,
    source_content_sha256: str | None = None,
) -> SceneDefinition:
    """Map a public imported Panda source to the canonical typed Scene owner."""

    entity_id = str(entity_id)
    scene_id = str(scene_id)
    if not entity_id or not scene_id:
        raise ValueError("Panda Scene identity requires nonempty entity and scene IDs")
    asset = _asset_definition_from_manifest(manifest)
    if source_content_sha256 is not None:
        asset = replace(asset, source_content_sha256=source_content_sha256)

    bodies = {body.body_id: body for body in imported.ir.bodies}
    bodies_by_frame = {body.frame_id: body for body in imported.ir.bodies}
    frames_by_id = {frame.node_id: frame for frame in imported.ir.frames}
    frames = tuple(
        FrameDefinition(
            "frame-definition-v1", entity_id, body.name, "runtime", None, None,
        )
        for body in imported.ir.bodies
    )
    coordinate_layout = {
        "hinge": ("revolute", "radian", "radian_per_second", 1, 1),
        "slide": ("prismatic", "meter", "meter_per_second", 1, 1),
        "fixed": ("fixed", "none", "none", 0, 0),
    }
    joints = []
    source_joint_names = set()
    joint_child_frames = set()
    for imported_joint in imported.ir.joints:
        source_name = imported_joint.dynamics.get("source_name")
        if not source_name:
            raise ValueError(f"Panda joint lacks source name: {imported_joint.joint_id}")
        if imported_joint.body_a is None or imported_joint.body_a not in bodies:
            raise ValueError(f"Panda joint has no canonical parent body: {source_name}")
        if imported_joint.body_b not in bodies:
            raise ValueError(f"Panda joint has no canonical child body: {source_name}")
        parent = bodies[imported_joint.body_a]
        child = bodies[imported_joint.body_b]
        try:
            kind, position, velocity, position_size, velocity_size = coordinate_layout[
                imported_joint.type
            ]
        except KeyError as exc:
            raise ValueError(
                f"unsupported imported Panda joint type: {imported_joint.type!r}"
            ) from exc
        joints.append(
            JointDefinition(
                "joint-definition-v1",
                str(source_name),
                FrameReference(entity_id, parent.name),
                FrameReference(entity_id, child.name),
                _pose_from_transform(imported_joint.frame_a),
                _pose_from_transform(imported_joint.frame_b),
                kind,
                tuple(float(value) for value in imported_joint.axis)
                if kind in {"revolute", "prismatic"} else None,
                position,
                velocity,
                position_size,
                velocity_size,
            )
        )
        source_joint_names.add(str(source_name))
        joint_child_frames.add(child.frame_id)

    root_body = next((body for body in imported.ir.bodies if body.name == "link0"), None)
    if root_body is None:
        raise ValueError("imported Panda source is missing root body 'link0'")
    for body in imported.ir.bodies:
        if body is root_body or body.frame_id in joint_child_frames:
            continue
        source_frame = frames_by_id.get(body.frame_id)
        parent_body = None if source_frame is None else bodies_by_frame.get(source_frame.parent_id)
        if parent_body is None:
            raise ValueError(f"unmapped fixed Panda frame: {body.name}")
        joints.append(
            JointDefinition(
                "joint-definition-v1",
                f"{body.name}_fixed_mount",
                FrameReference(entity_id, parent_body.name),
                FrameReference(entity_id, body.name),
                _pose_from_transform(source_frame.local_transform),
                PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
                "fixed",
                None,
                "none",
                "none",
                0,
                0,
            )
        )

    articulation = ArticulationDefinition(
        "articulation-definition-v1",
        entity_id,
        "link0",
        tuple(body.name for body in imported.ir.bodies),
        tuple(joints),
    )
    actuator_names = tuple(sorted(
        str(actuator.parameters.get("source_name"))
        for actuator in imported.ir.actuators
        if actuator.parameters.get("source_name")
    ))
    expected_actuators = {f"actuator{index}" for index in range(1, 9)}
    if set(actuator_names) != expected_actuators:
        raise ValueError("imported Panda source must expose its eight named actuators")
    resources = tuple(
        ActuatorResourceDefinition("actuator-resource-v1", entity_id, name)
        for name in actuator_names
    )
    scene = SceneDefinition(
        "scene-definition-v3",
        scene_id,
        (asset,),
        (EntityInstance("entity-instance-v1", entity_id, asset.asset_id, asset.asset_version),),
        frames,
        (articulation,),
        (RobotInstance(
            "robot-instance-v1", entity_id, (FrameReference(entity_id, "link0"),),
        ),),
        resources,
        (
            ControlGroup(
                "control-group-v1", entity_id, "arm",
                tuple(ActuatorReference(entity_id, f"actuator{index}") for index in range(1, 8)),
            ),
            ControlGroup(
                "control-group-v1", entity_id, "gripper",
                (ActuatorReference(entity_id, "actuator8"),),
            ),
        ),
    )
    scene.validate()
    scene_joint_ids = {joint.joint_id for joint in articulation.joints}
    if not source_joint_names <= scene_joint_ids:
        raise ValueError("Panda Scene dropped an imported source joint")
    for name in actuator_names:
        reference = ActuatorReference(entity_id, name)
        if scene.resolve_actuator(reference) != ActuatorResourceDefinition(
            "actuator-resource-v1", entity_id, name,
        ):
            raise ValueError(f"Panda Scene did not retain imported actuator {name!r}")
    return scene


def _pose_from_transform(values) -> PoseWorld:
    matrix = np.asarray(values, dtype=np.float64).reshape(4, 4)
    quaternion = matrix_to_quat_wxyz(matrix[:3, :3])
    return PoseWorld(
        tuple(float(value) for value in matrix[:3, 3]),
        tuple(float(value) for value in quaternion),
    )
