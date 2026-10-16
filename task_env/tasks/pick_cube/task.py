"""Selected PickCube P1.6 task definition, construction and task semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import inspect
import json
import math
from pathlib import Path
import subprocess

import numpy as np
import yaml

from ...artifacts import (
    ActionIntent, CanonicalStateView, EntityDefinition, InitializationContract,
    PoseWorld, RequiredCapabilitySet, SemanticDefinition, TaskArtifact,
    Timebase, UniformDimension, WorldDefinition,
)
from ...artifacts.execution import ResetSample
from ...assembly import TaskReferences
from ...controllers.canonical import ProductionCanonicalPandaController
from ...controllers.canonical.contracts import digest
from ...environment import RuntimeSnapshot, TaskCompositionSpec, TaskEvaluation
from ...environment.configuration import overlay_public_env_config, resolve_env_config
from ...environment.task_definition import TaskDefinitionBase
from ...registry import make_agent, make_object, make_scene, register_env
from ...robots.panda import PandaAgent
from ...runtime.sessions.source import RuntimeSource
from ..reference_env import ReferenceTaskBinding, SelectedReferenceEnv
from ...objects.pick_cube import (
    CUBE_CONTACT_MARGIN, CUBE_DIAG_INERTIA, CUBE_HALF_SIZE, CUBE_MASS,
    EE_SITE_NAME, PickCubeSceneComposer,
)


CONFIG_PATH = Path(__file__).with_name("config.yaml")
PICK_CUBE_P16_ARTIFACT_SHA256 = "fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4"
EEF = "panda-v1/ee"
FINGERS = ("panda-v1/finger_joint1", "panda-v1/finger_joint2")
TASK_CONFIGURATION_KEYS = ("recipe", "environment")


def _configuration() -> dict:
    data = yaml.safe_load(CONFIG_PATH.read_text())
    if not isinstance(data, dict) or set(data) != set(TASK_CONFIGURATION_KEYS):
        raise ValueError("PickCube config.yaml must define exactly recipe and environment")
    recipe = data["recipe"]
    if recipe.get("control_hz") != 100 or recipe.get("artifact_id") != "pick-cube-v1/p1_6_experimental_100hz":
        raise ValueError("PickCube task admits only the selected P1.6 100 Hz recipe")
    return data


def _recipe() -> dict:
    return _configuration()["recipe"]


def _environment_config():
    data = _configuration()
    recipe = data["recipe"]
    base = resolve_env_config(
        task_uid=recipe["task_uid"], scene_uid=recipe["scene_uid"],
        agent_uids=tuple(recipe["agent_uids"]), object_uids=tuple(recipe["object_uids"]),
        success_definition=recipe["success_definition"],
    )
    config = overlay_public_env_config(base, data["environment"])
    runtime = replace(config.runtime, backend="cpu", prewarm=False,
        physics_dt=float(recipe["physics_dt"]), control_substeps=int(recipe["control_substeps"]))
    return replace(config, runtime=runtime, render=replace(config.render, camera_obs=False))


def semantic_definition() -> SemanticDefinition:
    recipe = _recipe()
    scene, task = recipe["scene"], recipe["success"]
    return SemanticDefinition(
        schema_version="semantics-v0", evaluator="pick_cube_lift_v0",
        required_poses=("cube-v1", EEF), required_joints=FINGERS,
        parameters_si={
            "rest_height": float(scene["table_top_z"]) + CUBE_HALF_SIZE,
            "lift_height": float(task["lift_height_m"]),
            "reach_distance": float(task["reach_distance_m"]),
            "gripper_closed_opening": float(task["gripper_closed_opening_m"]),
        },
        success_definition=recipe["success_definition"],
    )


def _evaluate_values(cube_pos, eef_pos, gripper_opening, semantics=None) -> TaskEvaluation:
    semantics = semantic_definition() if semantics is None else semantics
    p = semantics.parameters_si
    cube_pos = np.asarray(cube_pos, dtype=np.float64)
    eef_pos = np.asarray(eef_pos, dtype=np.float64)
    cube_lift = float(cube_pos[2] - p["rest_height"])
    distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(eef_pos, cube_pos, strict=True)))
    reached = distance <= p["reach_distance"]
    grasped = bool(reached and gripper_opening <= p["gripper_closed_opening"])
    lifted = bool(cube_lift >= p["lift_height"])
    terms = {
        "reach": .10 * (1.0 - math.tanh(10.0 * distance)),
        "grasp": .25 if grasped else 0.0,
        "lift": min(.40, max(0.0, cube_lift / p["lift_height"]) * .40),
        "success": 1.0 if lifted else 0.0,
    }
    metrics = {
        "reached_cube": bool(reached), "grasped_cube": grasped,
        "lifted_cube": lifted, "task_success": lifted,
        "cube_x": float(cube_pos[0]), "cube_y": float(cube_pos[1]),
        "cube_z": float(cube_pos[2]), "cube_lift": cube_lift,
        "eef_to_cube_dist": distance, "gripper_opening": float(gripper_opening),
        "success_definition": True,
    }
    return TaskEvaluation(float(sum(terms.values())), lifted, False, metrics, terms)


def evaluate(state: CanonicalStateView, semantics: SemanticDefinition | None = None) -> TaskEvaluation:
    """Lift is the sole success gate; grasp remains a reward diagnostic."""
    if not isinstance(state, CanonicalStateView):
        raise TypeError("PickCube evaluation requires CanonicalStateView")
    expected = semantic_definition()
    semantics = expected if semantics is None else semantics
    if semantics != expected:
        raise ValueError("unsupported PickCube semantic definition")
    semantics.require_state(state)
    gripper_opening = sum(state.joint_position[name] for name in FINGERS)
    return _evaluate_values(state.pose_world["cube-v1"].position,
                            state.pose_world[EEF].position, gripper_opening, semantics)


@dataclass(frozen=True)
class PickCubeTaskDefinition(TaskDefinitionBase):
    """Core Task Definition using the same measured lift predicate as the Artifact."""

    references: TaskReferences
    success_definition: str = "cube_lifted_v1"

    def __post_init__(self):
        if self.success_definition != _recipe()["success_definition"]:
            raise ValueError("unsupported PickCube success definition")
        if "panda-v1" not in self.references.agents or "cube-v1" not in self.references.objects:
            raise KeyError("PickCube Task Definition requires panda-v1 and cube-v1 references")

    def reset(self, snapshot: RuntimeSnapshot) -> TaskEvaluation:
        return self._evaluate_snapshot(snapshot)

    def evaluate(self, previous_snapshot, action, current_snapshot) -> TaskEvaluation:
        del previous_snapshot, action
        return self._evaluate_snapshot(current_snapshot)

    def _evaluate_snapshot(self, snapshot):
        panda = self.references.agents["panda-v1"]
        cube_ref = self.references.objects["cube-v1"]
        if snapshot.site_xpos is None or snapshot.body_xpos is None:
            raise ValueError("PickCube evaluation requires site_xpos and body_xpos")
        cube_pos = snapshot.body_xpos[int(cube_ref.body_ids[0])]
        eef_pos = snapshot.site_xpos[int(panda.eef_site_id)]
        opening = float(np.sum(snapshot.qpos[panda.gripper_qpos_ids]))
        return _evaluate_values(cube_pos, eef_pos, opening)


def build_artifact() -> TaskArtifact:
    """Build the selected serialized TaskArtifact through canonical Core contracts."""
    recipe = _recipe()
    scene = recipe["scene"]
    reset = recipe["reset"]
    center = tuple(float(value) for value in np.asarray(reset["center_xy"], dtype=np.float32))
    half_extent = float(reset["half_extent_m"])
    dimensions = tuple(
        UniformDimension(f"cube-v1.position_world.{axis}",
            (value - half_extent, value + half_extent),
            (value - half_extent, value + half_extent),
            (value - half_extent, value + half_extent),
            (value - half_extent, value + half_extent))
        for axis, value in zip(("x", "y"), center, strict=True)
    )
    initial_joints = {f"panda-v1/{name}": value
        for name, value in PandaAgent().initial_state_spec().joint_positions}
    table_half = tuple(float(value) for value in scene["table_half_size"])
    artifact = TaskArtifact(
        schema_version="task-artifact-v0", artifact_id=recipe["artifact_id"],
        task_id=recipe["task_uid"], artifact_version=recipe["artifact_version"],
        world=WorldDefinition(
            schema_version="world-v0", convention="SI_right_handed_z_up_wxyz",
            entities=(
                EntityDefinition("tabletop-v1", "static", "tabletop-v1/task-local",
                    ("tabletop-v1/top",), (), "box", "support_contact",
                    {"top_z": float(scene["table_top_z"]), **{
                        f"half_size_{axis}": value for axis, value in zip("xyz", table_half, strict=True)}}),
                EntityDefinition("panda-v1", "embodiment",
                    "mujoco_menagerie/b846dd12bc459d776cccb3dee0b1d02acbf7a9c7/franka_emika_panda/panda.xml",
                    ("panda-v1/base", EEF),
                    (*tuple(f"panda-v1/joint{i}" for i in range(1, 8)), *FINGERS),
                    "referenced_articulation", "arm_hand_finger_collision", {}),
                EntityDefinition("cube-v1", "movable", "cube-v1/task-local", (), (),
                    "free_box", "table_hand_contact",
                    {"half_size": CUBE_HALF_SIZE, "mass": CUBE_MASS, **{
                        f"inertia_{axis}": value for axis, value in zip("xyz", CUBE_DIAG_INERTIA, strict=True)}}),
            ),
            action=ActionIntent("absolute_pose", "world", "quaternion_wxyz",
                "arm_joint_position_and_gripper"),
            observation_requirements=("task-env-state-v2", "privileged_state"),
            randomization_dimensions=tuple(dimension.name for dimension in dimensions),
        ),
        initialization=InitializationContract(
            schema_version="initialization-v0",
            poses_world={"cube-v1": PoseWorld(
                (center[0], center[1], float(scene["table_top_z"]) + CUBE_HALF_SIZE + CUBE_CONTACT_MARGIN),
                (1.0, 0.0, 0.0, 0.0))},
            joint_position=initial_joints, randomization=dimensions,
            inherited_state_policy="zero_named_joint_and_entity_velocities_arm_targets_at_initial_joints_gripper_open",
            reset_validity="cube_free_pose_in_declared_xy_envelope_fixed_z_identity_wxyz",
            settle_steps=0,
        ),
        semantics=semantic_definition(),
        timebase=Timebase(float(recipe["physics_dt"]), int(recipe["control_substeps"]),
                          float(recipe["control_dt"])),
        required_capabilities=RequiredCapabilitySet((
            "rigid_body", "free_body", "articulated_robot", "joint_position_actuation",
            "joint_state_query", "body_pose_query", "frame_pose_query",
        )),
    )
    if artifact.identity_hash != PICK_CUBE_P16_ARTIFACT_SHA256:
        raise ValueError("selected P1.6 TaskArtifact identity mismatch")
    return artifact


def sample_reset(artifact: TaskArtifact, task_seed: int) -> ResetSample:
    """Sample the selected PCG64-v0 reset distribution at the task boundary."""
    if not isinstance(artifact, TaskArtifact) or artifact.identity_hash != build_artifact().identity_hash:
        raise ValueError("selected P1.6 experimental_100hz TaskArtifact required")
    if type(task_seed) is not int or task_seed < 0:
        raise ValueError("task_seed must be a nonnegative integer")
    rng = np.random.Generator(np.random.PCG64(task_seed))
    initial = artifact.initialization
    position = list(initial.poses_world["cube-v1"].position)
    for index, dimension in enumerate(initial.randomization):
        position[index] = float(rng.uniform(*dimension.training_bounds))
    poses = {"cube-v1": PoseWorld(tuple(position), initial.poses_world["cube-v1"].quaternion_wxyz)}
    return ResetSample.create(
        schema_version="reset-sample-v0", task_artifact_hash=artifact.identity_hash,
        sampler_id="pick-cube-v1/uniform_xy", sampler_version="pcg64-v0",
        task_seed=task_seed, joint_position=dict(initial.joint_position), poses_world=poses,
        velocity_policy="zero_named_joint_and_entity_velocities",
        control_policy="arm_targets_at_initial_joints_gripper_open", settle_steps=initial.settle_steps,
    )


def build_runtime_source(artifact: TaskArtifact, *, backend="cpu") -> RuntimeSource:
    if artifact.identity_hash != build_artifact().identity_hash:
        raise ValueError("selected P1.6 TaskArtifact required")
    if backend not in {"cpu", "cuda"}:
        raise ValueError("PickCube reference backend must be cpu or cuda")
    recipe = _recipe()
    scene = recipe["scene"]
    cube_position = tuple(float(value) for value in scene["initial_cube_position"])
    cube_quaternion = tuple(float(value) for value in scene["initial_cube_quaternion_wxyz"])
    composer = PickCubeSceneComposer(
        table_half_size=scene["table_half_size"], table_top_z=scene["table_top_z"],
        table_center_xy=scene["table_center_xy"], cube_world_pos=cube_position,
        cube_world_quat=cube_quaternion,
    )
    config = _environment_config()
    config = replace(config, runtime=replace(config.runtime, backend=backend))
    spec = recipe
    joints = {name: name.split("/", 1)[1] for name in artifact.initialization.joint_position}
    return RuntimeSource(
        task_artifact_hash=artifact.identity_hash,
        scene_source=composer.build_source_description(),
        joints=joints, bodies={"cube-v1": "PickCube"}, frames={EEF: EE_SITE_NAME},
        free_joints={"cube-v1": "PickCube_joint"},
        joint_targets={f"panda-v1/joint{i}": f"actuator{i}" for i in range(1, 8)},
        open_actuators=("actuator8",),
        composition=TaskCompositionSpec(spec["task_uid"], spec["scene_uid"],
            tuple(spec["agent_uids"]), tuple(spec["object_uids"]),
            success_definition=spec["success_definition"]),
        config=config, scene=make_scene(spec["scene_uid"]),
        agents=tuple(make_agent(uid) for uid in spec["agent_uids"]),
        objects=tuple(make_object(uid) for uid in spec["object_uids"]),
    )


def _source_identity_files(controller, solution):
    root = Path(__file__).resolve().parents[3]
    files = {Path(__file__).resolve(), CONFIG_PATH.resolve(),
             Path(inspect.getsourcefile(PickCubeSceneComposer)).resolve(),
             Path(inspect.getsourcefile(type(controller))).resolve(),
             Path(inspect.getsourcefile(type(solution))).resolve(),
             Path(inspect.getsourcefile(ReferenceTaskBinding)).resolve(),
             Path(inspect.getsourcefile(RuntimeSource)).resolve()}
    canonical = root / "task_env" / "controllers" / "canonical"
    files.update(path.resolve() for path in canonical.glob("*.py") if path.is_file())
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


def build_reference(*, backend="cpu"):
    """Construct the single selected P1.6 route without importing a provider."""
    from ...controllers.canonical import ProductionCanonicalPandaController
    from ...controllers.canonical.contracts import digest
    from .solution import PickCubeReadinessConfig, PickCubeReadinessSolution

    recipe = _recipe()
    artifact = build_artifact()
    source = build_runtime_source(artifact, backend=backend)
    readiness = PickCubeReadinessConfig.from_source(artifact, source)
    controller = ProductionCanonicalPandaController.from_source(artifact, source)
    solution = PickCubeReadinessSolution(config=readiness)
    root = Path(__file__).resolve().parents[3]
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    source_ids = _source_identity_files(controller, solution)
    runtime_config = asdict(source.config)
    resolved = {
        "construction_id": recipe["construction_id"], "task_recipe": _configuration(),
        "artifact": artifact.to_mapping(), "artifact_sha256": artifact.identity_hash,
        "runtime_config": runtime_config, "runtime_config_sha256": hashlib.sha256(
            json.dumps(runtime_config, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "readiness": asdict(readiness), "resolved_controller_action": asdict(controller.config),
        "resolved_controller_gripper": asdict(controller.gripper_config),
        "controller_identity": controller.identity, "solution_identity": solution.identity,
        "source_xml_sha256": hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
        "source_revision": revision, "source_sha256": source_ids,
        "runtime_source_bindings": {name: dict(getattr(source, name)) for name in
            ("joints", "bodies", "frames", "free_joints", "joint_targets")},
        "runtime_open_actuators": list(source.open_actuators),
        "qualification": "NOT_REQUALIFIED",
    }
    return {
        "construction_id": recipe["construction_id"], "artifact": artifact, "source": source,
        "readiness": readiness, "controller": controller, "solution": solution,
        "source_revision": revision, "source_sha256": source_ids,
        "recipe_identity": digest(resolved), "resolved_configuration": resolved,
    }


def make_reference_binding():
    return ReferenceTaskBinding(
        build=lambda provider: build_reference(backend="cpu"),
        reset_sample=sample_reset, evaluate=evaluate,
        object_poses=(("cube-v1", "cube_v1"),),
        external_actions=True, interval_mode="grouped", recorder_mode="canonical",
        reset_expert_kwargs=lambda env: {"execution_info": env._execution_info()},
        observe_expert_kwargs=lambda env, guard_samples: {"execution_info": env._execution_info()},
    )


REFERENCE_ENV_ID = _recipe()["reference_env_id"]


@register_env()
class PickCubeReferenceEnv(SelectedReferenceEnv):
    """Public selected P1.6 route, registered beside its task definition."""

    uid = REFERENCE_ENV_ID
    binding = make_reference_binding()


__all__ = [
    "PICK_CUBE_P16_ARTIFACT_SHA256", "PickCubeReferenceEnv", "PickCubeTaskDefinition",
    "REFERENCE_ENV_ID", "build_artifact", "build_reference", "build_runtime_source", "evaluate", "make_reference_binding",
    "sample_reset", "semantic_definition",
]
