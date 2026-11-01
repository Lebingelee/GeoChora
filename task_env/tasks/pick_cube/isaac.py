"""PickCube's versioned Isaac Sim scene and TaskArtifact projection.

This module owns only the task-to-USD structural projection.  Provider startup,
materialization, reset writes, and physics state continue to use the existing
Core RuntimeSession owners.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from ...artifacts import ExecutionSpecV1, RendererSelectionV1
from ...runtime.sessions.source import UsdRuntimeSourceV1
from ...assembly.source import UsdTaskSceneSourceV1
from ...assembly.usd_delivery import load_usd_asset_delivery, resolve_provider_representation
from ...environment import sample_episode_reset_plan
from ...artifacts.execution import EpisodeResetPlanV1
from ...environment.task_source import TaskSourceV1
from ...artifacts import TaskArtifactV1

from ...artifacts import AssetDefinition, FrameDefinition, FrameReference, SceneDefinition
from ...environment import adapt_legacy_recipe_task_source, compile_task_artifact_v1


SCHEMA_VERSION = "pick-cube-isaac-scene-v1"
SCENE_RECIPE_ID = "pick-cube-isaac-desktop-scene-v1"
ISAAC_PROFILE_V1 = "isaac-gpu-physx-pickcube-f06-v1"
ISAAC_REPRESENTATION_V1 = "isaacsim-6.2.0.0-pickcube-desktop-v1"
ISAAC_DELIVERY_MANIFEST_SHA256_V1 = (
    "6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2"
)


def build_pickcube_isaac_scene(task_config: dict) -> SceneDefinition:
    """Compose the existing Panda structure with the actual PickCube desktop.

    The existing canonical Scene builder owns the detailed Panda frames,
    joint order, floating-body graph, and TCP transform. The F06 projection
    changes the Panda/cube/support identities and binds the task-owned desktop; its
    USD recipe is generated separately and does not reuse F05 physical values.
    """
    from ..position_candidate.source import _f05_dg01_scene

    base = _f05_dg01_scene().to_mapping()
    raw = deepcopy(base)

    def remap(value):
        if isinstance(value, dict):
            return {key: remap(item) for key, item in value.items()}
        if isinstance(value, list):
            return [remap(item) for item in value]
        if isinstance(value, str):
            return (value.replace("panda-main", "panda-v1")
                    .replace("free-cube", "cube-v1")
                    .replace("f05-dg01-free-cube-v1", "pick-cube-cube-v1")
                    .replace("f05-dg01-support-v1", "pick-cube-tabletop-v1")
                    .replace("support", "tabletop-v1"))
        return value

    raw = remap(raw)
    raw["scene_id"] = str(task_config["recipe"]["scene_uid"])
    raw["assets"] = [AssetDefinition(
        "asset-definition-v1",
        "f05-dg03-menagerie-panda-source-preserving-isaac-usd",
        "f05-dg03-isaac-usd-v4",
        "mujoco-menagerie://franka_emika_panda/panda.xml",
        "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7",
        "a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a",
        "bsd-3-clause",
    ).to_mapping()] + [
        AssetDefinition(
            "asset-definition-v1", "pick-cube-cube-v1", "pick-cube-recipe-v1",
            "geochora-task-scene://pick-cube-v1/cube", SCENE_RECIPE_ID,
            hashlib.sha256(_canonical_task_recipe(task_config)).hexdigest(),
        ).to_mapping(),
        AssetDefinition(
            "asset-definition-v1", "pick-cube-tabletop-v1", "pick-cube-recipe-v1",
            "geochora-task-scene://pick-cube-v1/tabletop", SCENE_RECIPE_ID,
            hashlib.sha256(_canonical_task_recipe(task_config)).hexdigest(),
        ).to_mapping(),
    ]
    for entity in raw["entities"]:
        if entity["entity_id"] == "panda-v1":
            entity.update(
                asset_id="f05-dg03-menagerie-panda-source-preserving-isaac-usd",
                asset_version="f05-dg03-isaac-usd-v4",
            )
        elif entity["entity_id"] == "cube-v1":
            entity.update(asset_id="pick-cube-cube-v1", asset_version="pick-cube-recipe-v1")
        elif entity["entity_id"] == "tabletop-v1":
            entity.update(
                asset_id="pick-cube-tabletop-v1",
                asset_version="pick-cube-recipe-v1",
            )
    raw["entities"] = [
        entity for entity in raw["entities"]
        if entity["entity_id"] in {"panda-v1", "cube-v1", "tabletop-v1"}
    ]
    for frame in raw["frames"]:
        if frame["entity_id"] == "tabletop-v1":
            frame["frame_id"] = "top"
        elif frame["entity_id"] == "cube-v1" and frame["frame_id"] == "free_cube":
            frame["frame_id"] = "cube"
    raw["frames"].append(FrameDefinition(
        "frame-definition-v1", "panda-v1", "ee", "runtime", None, None,
    ).to_mapping())
    for articulation in raw["articulations"]:
        if articulation["entity_id"] == "cube-v1":
            articulation["root_frame_id"] = "world"
            articulation["link_frame_ids"] = [
                "cube" if value == "free_cube" else value
                for value in articulation["link_frame_ids"]
            ]
            for joint in articulation["joints"]:
                for field in ("parent_frame", "child_frame"):
                    if joint[field]["entity_id"] == "cube-v1" and joint[field]["frame_id"] == "free_cube":
                        joint[field]["frame_id"] = "cube"
    return SceneDefinition.from_mapping(raw)


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
                or self.delivery_manifest_sha256 != ISAAC_DELIVERY_MANIFEST_SHA256_V1
                or delivery.delivery.representation_id != ISAAC_REPRESENTATION_V1
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
) -> PickCubeIsaacRuntimeInputV1:
    """Build the current PickCube Task and public USD source through Core owners."""
    from .task import _configuration, build_artifact

    if type(task_seed) is not int or task_seed < 0:
        raise ValueError("F06 PickCube task_seed must be a nonnegative integer")
    if type(horizon) is not int or not 1 <= horizon <= 1000:
        raise ValueError("F06 PickCube horizon must be an integer in [1, 1000]")
    path = Path(delivery_manifest).resolve(strict=True)
    loaded = load_usd_asset_delivery(path)
    manifest_sha = loaded.manifest_bytes_sha256
    if (manifest_sha != ISAAC_DELIVERY_MANIFEST_SHA256_V1
            or not loaded.locally_validated or loaded.source_verified
            or loaded.delivery.representation_id != ISAAC_REPRESENTATION_V1):
        raise ValueError("F06 builder requires the exact generated PickCube desktop delivery v1")

    task_config = _configuration()
    legacy_artifact = build_artifact()
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
    "ISAAC_DELIVERY_MANIFEST_SHA256_V1", "PickCubeIsaacRuntimeInputV1",
    "build_pickcube_isaac_scene", "compile_pickcube_isaac_task_artifact",
    "build_pickcube_isaac_runtime_input_v1",
]
