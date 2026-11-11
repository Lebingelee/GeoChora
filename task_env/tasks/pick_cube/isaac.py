"""PickCube's versioned Isaac Sim scene and TaskArtifact projection.

This module owns only the task-to-USD structural projection.  Provider startup,
materialization, reset writes, and physics state continue to use the existing
Core RuntimeSession owners.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from ...artifacts import ExecutionSpecV1, RendererSelectionV1
from ...runtime.sessions.source import UsdRuntimeSourceV1
from ...assembly.source import UsdTaskSceneSourceV1
from ...assembly.usd_delivery import load_usd_asset_delivery, resolve_provider_representation
from ...environment import sample_episode_reset_plan
from ...artifacts.execution import EpisodeResetPlanV1
from ...environment.task_source import TaskSourceV1
from ...artifacts import TaskArtifactV1

from ...artifacts import (
    ArticulationDefinition,
    AssetDefinition,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    JointDefinition,
    PoseWorld,
    SceneDefinition,
)
from ...environment import adapt_legacy_recipe_task_source, compile_task_artifact_v1


SCHEMA_VERSION = "pick-cube-isaac-scene-v1"
SCENE_RECIPE_ID = "pick-cube-isaac-desktop-scene-v1"
ISAAC_PROFILE_V1 = "isaac-gpu-physx-pickcube-f06-v1"
ISAAC_REPRESENTATION_V1 = "isaacsim-6.2.0.0-pickcube-desktop-v1"
ISAAC_DELIVERY_MANIFEST_SHA256_V1 = (
    "6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2"
)
# Separately versioned asset-object scene: the F06 composition with the task
# object's geometry/material replaced by a generated asset (asset-creation skill,
# TRELLIS.2).  Derived by task_env/diagnostics/tasks/pickcube_isaac_asset_object_delivery.py.
ISAAC_REPRESENTATION_ASSET_OBJECT_V1 = "isaacsim-6.2.0.0-pickcube-asset-object-v1"
ISAAC_DELIVERY_MANIFEST_SHA256_ASSET_OBJECT_V1 = (
    "40b0dd2226d49e22d8d4ad03de5440ea454bbb7d4b4e2eabea3abbe732565d3e"
)
# Exact admitted delivery manifest bytes -> required representation id.
ISAAC_ADMITTED_DELIVERIES_V1 = MappingProxyType({
    ISAAC_DELIVERY_MANIFEST_SHA256_V1: ISAAC_REPRESENTATION_V1,
    ISAAC_DELIVERY_MANIFEST_SHA256_ASSET_OBJECT_V1: ISAAC_REPRESENTATION_ASSET_OBJECT_V1,
})


def isaac_delivery_admitted(manifest_sha256: str, representation_id: str) -> bool:
    """Return whether these exact manifest bytes are a Core-admitted PickCube Isaac delivery."""
    return ISAAC_ADMITTED_DELIVERIES_V1.get(manifest_sha256) == representation_id


def build_pickcube_isaac_scene(task_config: dict) -> SceneDefinition:
    """Compose the Panda source with task-owned PickCube entities and recipe."""
    from ...robots.panda import PandaAgent

    scene_id = str(task_config["recipe"]["scene_uid"])
    panda_scene = PandaAgent()._scene_definition(entity_id="panda-v1", scene_id=scene_id)
    source_asset = panda_scene.assets[0]
    if not source_asset.source_content_sha256:
        raise ValueError("Panda importer must provide the consumed source closure digest")

    panda_asset = AssetDefinition(
        schema_version="asset-definition-v1",
        asset_id="f05-dg03-menagerie-panda-source-preserving-isaac-usd",
        asset_version="f05-dg03-isaac-usd-v4",
        source_reference=source_asset.source_reference,
        source_revision=source_asset.source_revision,
        source_content_sha256=source_asset.source_content_sha256,
        license_id="bsd-3-clause",
    )
    panda_entity = replace(
        panda_scene.entities[0],
        asset_id=panda_asset.asset_id,
        asset_version=panda_asset.asset_version,
    )
    recipe_digest = hashlib.sha256(_canonical_task_recipe(task_config)).hexdigest()
    cube_asset = AssetDefinition(
        "asset-definition-v1", "pick-cube-cube-v1", "pick-cube-recipe-v1",
        "geochora-task-scene://pick-cube-v1/cube", SCENE_RECIPE_ID, recipe_digest,
    )
    tabletop_asset = AssetDefinition(
        "asset-definition-v1", "pick-cube-tabletop-v1", "pick-cube-recipe-v1",
        "geochora-task-scene://pick-cube-v1/tabletop", SCENE_RECIPE_ID, recipe_digest,
    )
    cube = EntityInstance(
        "entity-instance-v1", "cube-v1", cube_asset.asset_id, cube_asset.asset_version,
    )
    tabletop = EntityInstance(
        "entity-instance-v1", "tabletop-v1", tabletop_asset.asset_id,
        tabletop_asset.asset_version,
    )
    identity_pose = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    cube_articulation = ArticulationDefinition(
        "articulation-definition-v1",
        "cube-v1",
        "world",
        ("world", "cube"),
        (JointDefinition(
            "joint-definition-v1",
            "cube_freejoint",
            FrameReference("cube-v1", "world"),
            FrameReference("cube-v1", "cube"),
            identity_pose,
            identity_pose,
            "floating",
            None,
            "xyz_meter_quaternion_wxyz",
            "linear_xyz_meter_per_second_angular_xyz_radian_per_second",
            7,
            6,
        ),),
    )
    return SceneDefinition(
        schema_version="scene-definition-v3",
        scene_id=scene_id,
        assets=(panda_asset, cube_asset, tabletop_asset),
        entities=(panda_entity, cube, tabletop),
        frames=(
            *panda_scene.frames,
            FrameDefinition("frame-definition-v1", "panda-v1", "ee", "runtime", None, None),
            FrameDefinition("frame-definition-v1", "cube-v1", "world", "runtime", None, None),
            FrameDefinition("frame-definition-v1", "cube-v1", "cube", "runtime", None, None),
            FrameDefinition("frame-definition-v1", "tabletop-v1", "top", "runtime", None, None),
        ),
        articulations=(*panda_scene.articulations, cube_articulation),
        robots=panda_scene.robots,
        actuator_resources=panda_scene.actuator_resources,
        control_groups=panda_scene.control_groups,
    )


def _canonical_task_recipe(task_config: dict) -> bytes:
    return json.dumps(
        {"schema_version": SCHEMA_VERSION, "recipe": task_config["recipe"]},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def compile_pickcube_isaac_task_artifact(task_config: dict, legacy_artifact):
    """Compile the existing PickCube v0 semantics against its USD Scene."""
    scene = build_pickcube_isaac_scene(task_config)
    task_source = adapt_legacy_recipe_task_source(task_config)
    artifact = compile_task_artifact_v1(
        task_source, scene, legacy_artifact,
        frame_bindings={
            "panda-v1/base": FrameReference("panda-v1", "link0"),
            "panda-v1/ee": FrameReference("panda-v1", "ee"),
        },
    )
    # The v0 Artifact's reset/success pose is the cube Entity identity, while
    # RuntimeSourceV1 needs that pose bound to the cube's measured body Frame.
    # Keep this task-specific alias explicit in the v1 projection.
    bindings = dict(artifact.legacy_frame_bindings)
    bindings["cube-v1"] = FrameReference("cube-v1", "cube")
    from dataclasses import replace

    artifact = replace(artifact, legacy_frame_bindings=bindings)
    artifact.validate_scene(scene)
    return task_source, scene, artifact


@dataclass(frozen=True)
class PickCubeIsaacRuntimeInputV1:
    """Exact local USD source/Task/Execution input for the F06 Isaac route."""

    schema_version: str
    task_source: TaskSourceV1
    artifact: TaskArtifactV1
    runtime_source: UsdRuntimeSourceV1
    execution: ExecutionSpecV1
    reset_plan: EpisodeResetPlanV1
    controller_profile: str
    horizon: int
    delivery_manifest_sha256: str

    def validate(self) -> None:
        if self.schema_version != "pick-cube-isaac-runtime-input-v1":
            raise ValueError("unsupported PickCube Isaac RuntimeInput schema")
        if (type(self.task_source) is not TaskSourceV1
                or type(self.artifact) is not TaskArtifactV1
                or type(self.runtime_source) is not UsdRuntimeSourceV1
                or type(self.execution) is not ExecutionSpecV1
                or type(self.reset_plan) is not EpisodeResetPlanV1):
            raise TypeError("F06 requires exact PickCube TaskSource/Artifact/USD/Execution/reset contracts")
        self.artifact.validate()
        self.runtime_source.validate()
        self.execution.validate()
        self.reset_plan.validate()
        if self.runtime_source.task_artifact is not self.artifact:
            raise ValueError("F06 RuntimeSource must reference the exact PickCube TaskArtifact")
        if (self.runtime_source.scene_source.task_source_identity_sha256
                != self.task_source.identity_hash
                or self.runtime_source.scene_source.scene_identity_sha256
                != self.runtime_source.scene_definition.identity_hash):
            raise ValueError("F06 USD RuntimeSource must bind the exact TaskSource and Scene")
        delivery = self.runtime_source.scene_source.loaded_delivery
        if (delivery.manifest_bytes_sha256 != self.delivery_manifest_sha256
                or not isaac_delivery_admitted(
                    self.delivery_manifest_sha256, delivery.delivery.representation_id)
                or not delivery.locally_validated or delivery.source_verified):
            raise ValueError("F06 requires its exact locally validated, non-upstream Isaac desktop USD")
        expected_joints = {
            **{f"panda-v1/joint{index}": f"joint{index}" for index in range(1, 8)},
            "panda-v1/finger_joint1": "finger_joint1",
            "panda-v1/finger_joint2": "finger_joint2",
        }
        if (dict(self.runtime_source.joints) != expected_joints
                or dict(self.runtime_source.joint_targets) != expected_joints
                or dict(self.runtime_source.bodies) != {
                    "panda-v1/base": "/F06Scene/panda/Geometry/link0",
                    "cube-v1": "/F06Scene/cube_v1",
                }
                or dict(self.runtime_source.frames) != {
                    "panda-v1/ee": (
                        "/F06Scene/panda/Geometry/link0/link1/link2/link3/link4/"
                        "link5/link6/link7/hand/ee"
                    ),
                    "tabletop-v1/top": "/F06Scene/tabletop_v1/top",
                }
                or dict(self.runtime_source.free_joints) != {
                    "cube-v1": "/F06Scene/cube_v1",
                }):
            raise ValueError("F06 RuntimeSource differs from its exact Panda/PickCube USD binding map")
        if (self.controller_profile != "r3_continuous_v1"
                or type(self.horizon) is not int or not 1 <= self.horizon <= 1000):
            raise ValueError("F06 PickCube Isaac requires frozen R3 and at most 1000 control ticks")
        if (self.execution.physics_provider, self.execution.physics_backend,
                self.execution.physics_profile, self.execution.physics_device,
                self.execution.provider_seed, self.execution.determinism_mode) != (
                "isaacsim", "cuda", ISAAC_PROFILE_V1, "cuda:0",
                self.reset_plan.reset_sample.task_seed, "best_effort"):
            raise ValueError("F06 ExecutionSpec differs from its frozen Isaac provider/seed profile")


def _source_bindings(scene: SceneDefinition, artifact: TaskArtifactV1):
    entry = "/F06Scene"
    body_paths = {
        "panda-v1/base": f"{entry}/panda/Geometry/link0",
        "cube-v1": f"{entry}/cube_v1",
    }
    frame_paths = {
        "panda-v1/ee": (
            f"{entry}/panda/Geometry/link0/link1/link2/link3/link4/"
            "link5/link6/link7/hand/ee"
        ),
        "tabletop-v1/top": f"{entry}/tabletop_v1/top",
    }
    scalar_joints = {}
    for articulation in scene.articulations:
        for joint in articulation.joints:
            if joint.kind in {"revolute", "continuous", "prismatic"}:
                semantic = f"{articulation.entity_id}/{joint.joint_id}"
                scalar_joints[semantic] = joint.joint_id
    required = set(artifact.legacy_joint_bindings)
    if set(scalar_joints) != required:
        raise ValueError("F06 USD binding map must cover every PickCube scalar Joint exactly")
    if set(body_paths) | set(frame_paths) != set(artifact.legacy_frame_bindings):
        raise ValueError("F06 USD body/frame map must cover every PickCube TaskArtifact runtime Frame")
    if set(artifact.initialization.poses_world) != {"cube-v1"}:
        raise ValueError("F06 PickCube reset must bind exactly the task-owned floating cube")
    return scalar_joints, body_paths, frame_paths, {"cube-v1": f"{entry}/cube_v1"}


def build_pickcube_isaac_runtime_input_v1(
    delivery_manifest: str | Path, *, task_seed: int = 31, horizon: int = 1000,
    task_config=None,
) -> PickCubeIsaacRuntimeInputV1:
    """Build the current PickCube Task and public USD source through Core owners."""
    from .specialization import _configuration, build_artifact

    if type(task_seed) is not int or task_seed < 0:
        raise ValueError("F06 PickCube task_seed must be a nonnegative integer")
    if type(horizon) is not int or not 1 <= horizon <= 1000:
        raise ValueError("F06 PickCube horizon must be an integer in [1, 1000]")
    path = Path(delivery_manifest).resolve(strict=True)
    loaded = load_usd_asset_delivery(path)
    manifest_sha = loaded.manifest_bytes_sha256
    if (not isaac_delivery_admitted(manifest_sha, loaded.delivery.representation_id)
            or not loaded.locally_validated or loaded.source_verified):
        raise ValueError("F06 builder requires an exact Core-admitted PickCube Isaac delivery")

    task_config = _configuration() if task_config is None else task_config
    legacy_artifact = build_artifact(task_config=task_config)
    task_source, scene, artifact = compile_pickcube_isaac_task_artifact(
        task_config, legacy_artifact,
    )
    options = {
        "f06_goal": "PickCube-Harness-three-backend-example",
        "lowering": "pickcube-desktop-physx-native-mimic-v1",
        "delivery_manifest_sha256": manifest_sha,
        "task_scene_recipe_sha256": hashlib.sha256(
            _canonical_task_recipe(task_config)
        ).hexdigest(),
    }
    representation = resolve_provider_representation(
        loaded, provider="isaacsim", provider_build_identity="isaacsim-6.2.0.0",
        options=options,
    )
    task_scene_source = UsdTaskSceneSourceV1(
        "usd-task-scene-source-v1", loaded, representation,
        task_source.identity_hash, scene.identity_hash,
    )
    joints, bodies, frames, free_joints = _source_bindings(scene, artifact)
    source = UsdRuntimeSourceV1(
        "usd-runtime-source-v1", artifact, scene, task_scene_source,
        joints, bodies, frames, free_joints, joints,
    )
    reset_plan = sample_episode_reset_plan(
        task_source, scene, artifact, task_seed=task_seed,
    )
    execution = ExecutionSpecV1(
        "execution-spec-v1", "isaacsim", "cuda", ISAAC_PROFILE_V1,
        task_seed, "best_effort", RendererSelectionV1(
            "renderer-selection-v1", "none", "cpu", "none", None,
        ), "cuda:0", (),
    )
    result = PickCubeIsaacRuntimeInputV1(
        "pick-cube-isaac-runtime-input-v1", task_source, artifact, source,
        execution, reset_plan, "r3_continuous_v1", horizon, manifest_sha,
    )
    result.validate()
    return result


__all__ = [
    "SCHEMA_VERSION", "SCENE_RECIPE_ID", "ISAAC_PROFILE_V1",
    "ISAAC_DELIVERY_MANIFEST_SHA256_V1", "ISAAC_REPRESENTATION_ASSET_OBJECT_V1",
    "ISAAC_DELIVERY_MANIFEST_SHA256_ASSET_OBJECT_V1", "ISAAC_ADMITTED_DELIVERIES_V1",
    "isaac_delivery_admitted", "PickCubeIsaacRuntimeInputV1",
    "build_pickcube_isaac_scene", "compile_pickcube_isaac_task_artifact",
    "build_pickcube_isaac_runtime_input_v1",
]
