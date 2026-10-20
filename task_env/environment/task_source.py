"""Strict, provider-free Task Source declarations for Phase II authoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Literal

from ..artifacts import (
    FrameReference,
    JointReference,
    SceneDefinition,
    TaskArtifact,
    TaskArtifactV1,
)
from ..artifacts.execution import EpisodeResetPlanV1, ResetSample, RoleBindingV1
from .configuration import load_yaml_mapping


_SOURCE_VERSION = "task-source-v1"
_ROLE_TYPES = {"robot", "rigid_body"}
_CARDINALITIES = {"exactly_one"}
_HOOK_PHASES = {
    "authoring_hook": "source_compile",
    "initialization_hook": "reset_sample",
    "semantic_hook": "evaluation_boundary",
}
_ROLE_SELECTION_POLICY_ID = "sorted-candidate-pcg64"
_ROLE_SELECTION_POLICY_VERSION = "v1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SAMPLER_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _mapping(value, name: str, *, required: set[str]) -> Mapping:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    if any(type(key) is not str for key in value):
        raise TypeError(f"{name} keys must be strings")
    unknown = set(value) - required
    missing = required - set(value)
    if unknown:
        raise ValueError(f"unknown {name} fields: {sorted(unknown)}")
    if missing:
        raise ValueError(f"missing {name} fields: {sorted(missing)}")
    return value


def _identifier(value, name: str) -> str:
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a non-empty identifier")
    return value


def _choice(value, choices: set[str], name: str) -> str:
    if type(value) is not str or value not in choices:
        raise ValueError(f"unsupported {name}: {value!r}")
    return value


def _reference(value, name: str) -> str:
    if type(value) is not str or not value.strip() or any(char.isspace() for char in value):
        raise ValueError(f"{name} must be a non-empty reference without whitespace")
    return value


def _unique_identifiers(value, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be a sequence of identifiers")
    result = tuple(_identifier(item, name) for item in value)
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{name} must contain unique identifiers")
    return result


def _identifier_sequence(value, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be a sequence of identifiers")
    if not value:
        return ()
    result = tuple(_identifier(item, name) for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must contain unique identifiers")
    return result


@dataclass(frozen=True)
class TaskRoleDeclarationV1:
    """Strict v1 role declaration; reset-time selection is owned by B02."""

    role_id: str
    entity_type: str
    selection_kind: Literal["ids"]
    selection_values: tuple[str, ...]
    cardinality: str

    def __post_init__(self):
        _identifier(self.role_id, "role id")
        _choice(self.entity_type, _ROLE_TYPES, "Task Source role entity_type")
        _choice(self.selection_kind, {"ids"}, "Task Source selector")
        values = _unique_identifiers(self.selection_values, "role selection")
        object.__setattr__(self, "selection_values", tuple(sorted(values)))
        _choice(self.cardinality, _CARDINALITIES, "Task Source cardinality")

    @classmethod
    def from_mapping(cls, role_id: str, value: Mapping) -> "TaskRoleDeclarationV1":
        raw = _mapping(value, f"role {role_id!r}", required={"entity_type", "selection", "cardinality"})
        selector_value = raw["selection"]
        if not isinstance(selector_value, Mapping):
            raise TypeError(f"role {role_id!r} selection must be a mapping")
        selector = _mapping(
            selector_value,
            f"role {role_id!r} selection",
            required=set(selector_value),
        )
        if set(selector) != {"ids"}:
            raise ValueError("B01 role selection must declare explicit entity ids only")
        selection_kind = next(iter(selector))
        return cls(
            role_id,
            raw["entity_type"],
            selection_kind,
            _unique_identifiers(selector[selection_kind], "role selection"),
            raw["cardinality"],
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "entity_type": self.entity_type,
            "selection": {self.selection_kind: list(self.selection_values)},
            "cardinality": self.cardinality,
        }


@dataclass(frozen=True)
class TaskHookDeclarationV1:
    """Auditable hook metadata only; this contract never imports or runs code."""

    kind: Literal["authoring_hook", "initialization_hook", "semantic_hook"]
    hook_id: str
    version: str
    code_hash: str
    inputs: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    determinism: Literal["deterministic", "seeded"]
    evaluation_phase: str
    pure_or_stateful: Literal["pure", "stateful"]

    def __post_init__(self):
        _choice(self.kind, set(_HOOK_PHASES), "Task Source hook kind")
        _identifier(self.hook_id, "hook id")
        _identifier(self.version, "hook version")
        if type(self.code_hash) is not str or not _SHA256.fullmatch(self.code_hash):
            raise ValueError("hook code_hash must be a lowercase SHA-256 hex digest")
        object.__setattr__(self, "inputs", _identifier_sequence(self.inputs, "hook inputs"))
        object.__setattr__(
            self,
            "required_capabilities",
            _identifier_sequence(self.required_capabilities, "hook required_capabilities"),
        )
        _choice(self.determinism, {"deterministic", "seeded"}, "hook determinism")
        if self.determinism == "seeded" and "task_seed" not in self.inputs:
            raise ValueError("seeded hooks must declare task_seed as an input")
        expected_phase = _HOOK_PHASES[self.kind]
        if self.evaluation_phase != expected_phase:
            raise ValueError(
                f"{self.kind} must declare evaluation_phase {expected_phase!r}"
            )
        _choice(self.pure_or_stateful, {"pure", "stateful"}, "hook pure_or_stateful")
        if self.kind != "semantic_hook" and self.pure_or_stateful != "pure":
            raise ValueError("authoring and initialization hooks must be pure")

    @classmethod
    def from_mapping(cls, value: Mapping) -> "TaskHookDeclarationV1":
        fields = {
            "kind", "hook_id", "version", "code_hash", "inputs",
            "required_capabilities", "determinism", "evaluation_phase", "pure_or_stateful",
        }
        raw = _mapping(value, "Task Source hook", required=fields)
        return cls(
            raw["kind"], raw["hook_id"], raw["version"], raw["code_hash"],
            _identifier_sequence(raw["inputs"], "hook inputs"),
            _identifier_sequence(raw["required_capabilities"], "hook required_capabilities"),
            raw["determinism"],
            raw["evaluation_phase"], raw["pure_or_stateful"],
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "hook_id": self.hook_id,
            "version": self.version,
            "code_hash": self.code_hash,
            "inputs": list(self.inputs),
            "required_capabilities": list(self.required_capabilities),
            "determinism": self.determinism,
            "evaluation_phase": self.evaluation_phase,
            "pure_or_stateful": self.pure_or_stateful,
        }


@dataclass(frozen=True)
class TaskInitializationV1:
    """Sampler identity/domain; bounds remain owned by the existing Artifact."""

    sampler_id: str
    sampler_version: str
    sampling_domain: Literal["training", "feasibility", "evaluation"]
    velocity_policy: str
    control_policy: str

    def __post_init__(self):
        if type(self.sampler_id) is not str or not _SAMPLER_ID.fullmatch(self.sampler_id):
            raise ValueError("sampler id must be a stable ResetSample-compatible token")
        _identifier(self.sampler_version, "sampler version")
        _choice(self.sampling_domain, {"training", "feasibility", "evaluation"}, "sampling domain")
        _choice(
            self.velocity_policy,
            {"zero_named_joint_and_entity_velocities"},
            "ResetSample velocity policy",
        )
        _choice(
            self.control_policy,
            {"arm_targets_at_initial_joints_gripper_open"},
            "ResetSample control policy",
        )

    @classmethod
    def from_mapping(cls, value: Mapping) -> "TaskInitializationV1":
        raw = _mapping(
            value,
            "Task Source initialization",
            required={"sampler_id", "sampler_version", "sampling_domain", "velocity_policy", "control_policy"},
        )
        return cls(
            raw["sampler_id"], raw["sampler_version"], raw["sampling_domain"],
            raw["velocity_policy"], raw["control_policy"],
        )

    def to_mapping(self) -> dict[str, str]:
        return {
            "sampler_id": self.sampler_id,
            "sampler_version": self.sampler_version,
            "sampling_domain": self.sampling_domain,
            "velocity_policy": self.velocity_policy,
            "control_policy": self.control_policy,
        }


@dataclass(frozen=True)
class TaskSourceV1:
    """Small declarative input envelope, not a compiled TaskArtifact."""

    task_id: str
    version: str
    scene_ref: str
    roles: tuple[TaskRoleDeclarationV1, ...]
    initialization: TaskInitializationV1 | None
    hooks: tuple[TaskHookDeclarationV1, ...] = ()
    schema_version: str = _SOURCE_VERSION

    def __post_init__(self):
        _choice(self.schema_version, {_SOURCE_VERSION}, "Task Source schema")
        _identifier(self.task_id, "task id")
        _identifier(self.version, "task source version")
        _reference(self.scene_ref, "scene ref")
        if self.initialization is not None and not isinstance(self.initialization, TaskInitializationV1):
            raise TypeError("Task Source initialization must be TaskInitializationV1 or None")
        if any(not isinstance(role, TaskRoleDeclarationV1) for role in self.roles):
            raise TypeError("Task Source roles must be TaskRoleDeclarationV1 values")
        role_ids = tuple(role.role_id for role in self.roles)
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("Task Source role ids must be unique")
        if any(not isinstance(hook, TaskHookDeclarationV1) for hook in self.hooks):
            raise TypeError("Task Source hooks must be TaskHookDeclarationV1 values")
        hook_kinds = tuple(hook.kind for hook in self.hooks)
        if len(hook_kinds) != len(set(hook_kinds)):
            raise ValueError("Task Source allows at most one hook per declared phase")
        object.__setattr__(self, "roles", tuple(sorted(self.roles, key=lambda role: role.role_id)))
        object.__setattr__(self, "hooks", tuple(sorted(self.hooks, key=lambda hook: hook.kind)))

    @classmethod
    def from_mapping(cls, value: Mapping) -> "TaskSourceV1":
        if not isinstance(value, Mapping):
            raise TypeError("Task Source must be a mapping")
        if any(type(key) is not str for key in value):
            raise TypeError("Task Source keys must be strings")
        required = {"schema_version", "identity", "scene", "roles", "hooks"}
        allowed = required | {"initialization"}
        unknown = set(value) - allowed
        missing = required - set(value)
        if unknown:
            raise ValueError(f"unknown Task Source fields: {sorted(unknown)}")
        if missing:
            raise ValueError(f"missing Task Source fields: {sorted(missing)}")
        raw = value
        _choice(raw["schema_version"], {_SOURCE_VERSION}, "Task Source schema")
        identity = _mapping(raw["identity"], "Task Source identity", required={"task_id", "version"})
        scene = _mapping(raw["scene"], "Task Source scene", required={"ref"})
        roles = raw["roles"]
        if not isinstance(roles, Mapping):
            raise TypeError("Task Source roles must be a mapping")
        parsed_roles = tuple(
            TaskRoleDeclarationV1.from_mapping(role_id, role_value)
            for role_id, role_value in roles.items()
        )
        raw_hooks = raw["hooks"]
        if not isinstance(raw_hooks, Sequence) or isinstance(raw_hooks, (str, bytes)):
            raise TypeError("Task Source hooks must be a sequence")
        hooks = tuple(TaskHookDeclarationV1.from_mapping(item) for item in raw_hooks)
        initialization_value = raw.get("initialization")
        initialization = None if initialization_value is None else TaskInitializationV1.from_mapping(initialization_value)
        return cls(identity["task_id"], identity["version"], scene["ref"], parsed_roles, initialization, hooks)

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "identity": {"task_id": self.task_id, "version": self.version},
            "scene": {"ref": self.scene_ref},
            "roles": {role.role_id: role.to_mapping() for role in self.roles},
            "initialization": None if self.initialization is None else self.initialization.to_mapping(),
            "hooks": [hook.to_mapping() for hook in self.hooks],
        }

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_task_source(source: str | Path | Mapping) -> TaskSourceV1:
    """Load and validate one Task Source file or already-parsed mapping."""

    values = load_yaml_mapping(source) if isinstance(source, (str, Path)) else source
    return TaskSourceV1.from_mapping(values)


def _domain_seed(*parts: str | int) -> int:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:16], "little")


def resolve_role_binding(
    source: TaskSourceV1,
    scene: SceneDefinition,
    *,
    task_seed: int,
    artifact: TaskArtifact | TaskArtifactV1,
) -> RoleBindingV1:
    """Resolve explicit ID candidate lists using independent per-role RNG domains."""

    _validate_role_candidates(source, scene, artifact)
    if type(task_seed) is not int or task_seed < 0:
        raise ValueError("task_seed must be a nonnegative integer")

    try:
        import numpy as np
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on installation
        raise RuntimeError("Task Source role selection requires NumPy") from exc

    bindings = {}
    for role in source.roles:
        candidates = tuple(sorted(role.selection_values))
        seed = _domain_seed(
            _ROLE_SELECTION_POLICY_ID,
            _ROLE_SELECTION_POLICY_VERSION,
            task_seed,
            scene.identity_hash,
            role.role_id,
            *candidates,
        )
        index = int(np.random.Generator(np.random.PCG64(seed)).integers(len(candidates)))
        bindings[role.role_id] = candidates[index]
    return RoleBindingV1(
        "role-binding-v1",
        source.identity_hash,
        scene.identity_hash,
        task_seed,
        _ROLE_SELECTION_POLICY_ID,
        _ROLE_SELECTION_POLICY_VERSION,
        bindings,
    )


def _validate_role_candidates(
    source: TaskSourceV1,
    scene: SceneDefinition,
    artifact: TaskArtifact | TaskArtifactV1 | None = None,
) -> None:
    """Validate Source selectors without sampling or committing a binding."""

    if not isinstance(source, TaskSourceV1) or not isinstance(scene, SceneDefinition):
        raise TypeError("Role validation requires TaskSourceV1 and SceneDefinition")
    source.__post_init__()
    scene.validate()
    if artifact is not None and not isinstance(artifact, (TaskArtifact, TaskArtifactV1)):
        raise TypeError("role validation artifact must be TaskArtifact v0 or v1")
    if source.scene_ref != scene.scene_id:
        raise ValueError("Task Source Scene reference does not match the canonical Scene")

    scene_entities = {entity.entity_id for entity in scene.entities}
    robot_entities = {robot.entity_id for robot in scene.robots or ()}
    artifact_by_id = None
    if isinstance(artifact, TaskArtifact):
        artifact.validate()
        if artifact.task_id != source.task_id or artifact.artifact_version != source.version:
            raise ValueError("Task Source identity does not match TaskArtifact identity")
        artifact_entities = {entity.semantic_id for entity in artifact.world.entities}
        artifact_by_id = {entity.semantic_id: entity for entity in artifact.world.entities}
        missing_scene_entities = artifact_entities - scene_entities
        if missing_scene_entities:
            raise ValueError(
                "TaskArtifact Entities are absent from canonical Scene: "
                f"{sorted(missing_scene_entities)}"
            )
        if scene.schema_version not in {"scene-definition-v2", "scene-definition-v3"}:
            raise ValueError("TaskArtifact role resolution requires a structured A Scene")
        for entity in scene.entities:
            artifact_entity = artifact_by_id.get(entity.entity_id)
            if artifact_entity is None:
                continue
            scene_frames = {
                f"{entity.entity_id}/{frame.frame_id}"
                for frame in scene.frames or () if frame.entity_id == entity.entity_id
            }
            scene_joints = {
                f"{entity.entity_id}/{joint.joint_id}"
                for articulation in scene.articulations or ()
                if articulation.entity_id == entity.entity_id
                for joint in articulation.joints
            }
            if (
                not set(artifact_entity.frames) <= scene_frames
                or not set(artifact_entity.joints) <= scene_joints
                or ((entity.entity_id in robot_entities) != (artifact_entity.kind == "embodiment"))
            ):
                raise ValueError(
                    f"Scene/TaskArtifact topology mismatch for {entity.entity_id!r}"
                )
    elif isinstance(artifact, TaskArtifactV1):
        artifact.validate_scene(scene)
        if artifact.task_id != source.task_id or artifact.artifact_version != source.version:
            raise ValueError("Task Source identity does not match TaskArtifact v1 identity")
        if artifact.task_source_identity_hash != source.identity_hash:
            raise ValueError("Task Source identity differs from TaskArtifact v1 snapshot")
        artifact_entities = scene_entities
    else:
        artifact_entities = scene_entities

    claimed_candidates: dict[str, str] = {}
    for role in source.roles:
        candidates = set(role.selection_values)
        missing_scene = candidates - scene_entities
        missing_artifact = candidates - artifact_entities
        if missing_scene or missing_artifact:
            raise ValueError(
                f"role {role.role_id!r} has unresolved candidates: "
                f"scene={sorted(missing_scene)}, artifact={sorted(missing_artifact)}"
            )
        if role.entity_type == "robot" and not candidates <= robot_entities:
            raise ValueError(f"role {role.role_id!r} candidates are not A03 RobotInstances")
        if role.entity_type == "rigid_body" and candidates & robot_entities:
            raise ValueError(f"role {role.role_id!r} cannot bind a RobotInstance as a rigid_body")
        if artifact_by_id is not None:
            for entity_id in candidates:
                kind = artifact_by_id[entity_id].kind
                if role.entity_type == "robot" and kind != "embodiment":
                    raise ValueError(
                        f"role {role.role_id!r} candidate is not an embodiment TaskArtifact Entity"
                    )
                if role.entity_type == "rigid_body" and kind not in {"static", "movable"}:
                    raise ValueError(
                        f"role {role.role_id!r} candidate is not a rigid-body TaskArtifact Entity"
                    )
        for entity_id in candidates:
            previous = claimed_candidates.get(entity_id)
            if previous is not None:
                raise ValueError(
                    f"Task Source roles {previous!r} and {role.role_id!r} have overlapping candidates"
                )
            claimed_candidates[entity_id] = role.role_id


def _set_dimension_value(name: str, value: float, poses: dict, joints: dict, role_binding: RoleBindingV1):
    if name in joints:
        joints[name] = value
        return
    for axis in ("x", "y", "z"):
        suffix = f".position_world.{axis}"
        if name.endswith(suffix):
            reference = name[:-len(suffix)]
            entity_id = role_binding.bindings.get(reference, reference)
            if entity_id not in poses:
                raise ValueError(f"randomization dimension {name!r} has no initialized PoseWorld")
            pose = poses[entity_id]
            coordinates = list(pose.position)
            coordinates[{"x": 0, "y": 1, "z": 2}[axis]] = value
            poses[entity_id] = type(pose)(tuple(coordinates), pose.quaternion_wxyz)
            return
    for role_id, entity_id in role_binding.bindings.items():
        prefix = f"{role_id}.joint_position."
        if name.startswith(prefix):
            joint_id = name[len(prefix):]
            semantic_joint = f"{entity_id}/{joint_id}"
            if semantic_joint not in joints:
                raise ValueError(f"randomization dimension {name!r} has no initialized Joint")
            joints[semantic_joint] = value
            return
    raise ValueError(f"unsupported v0 InitializationContract dimension: {name!r}")


def _sample_dimensions(source: TaskSourceV1, scene: SceneDefinition, artifact: TaskArtifact, task_seed: int):
    initializer = source.initialization
    if initializer is None:
        raise ValueError("Task Source requires an initialization sampler declaration")
    dimensions = artifact.initialization.randomization
    if initializer.sampler_version == "frozen-authored-v0":
        if dimensions:
            raise ValueError("frozen-authored-v0 cannot sample declared randomization dimensions")
        return []
    if initializer.sampler_version == "pcg64-v0":
        import numpy as np

        generator = np.random.Generator(np.random.PCG64(task_seed))
        sampled = []
        for dimension in dimensions:
            lower, upper = getattr(dimension, f"{initializer.sampling_domain}_bounds")
            sampled.append((dimension, float(generator.uniform(lower, upper))))
        return sampled
    if initializer.sampler_version == "pcg64-domain-v1":
        import numpy as np

        sampled = []
        for dimension in dimensions:
            lower, upper = getattr(dimension, f"{initializer.sampling_domain}_bounds")
            seed = _domain_seed(
                initializer.sampler_id,
                initializer.sampler_version,
                initializer.sampling_domain,
                task_seed,
                scene.identity_hash,
                dimension.name,
            )
            generator = np.random.Generator(np.random.PCG64(seed))
            sampled.append((dimension, float(generator.uniform(lower, upper))))
        return sampled
    raise ValueError(f"unsupported Task Source sampler version: {initializer.sampler_version!r}")


def sample_episode_reset_plan(
    source: TaskSourceV1,
    scene: SceneDefinition,
    artifact: TaskArtifact | TaskArtifactV1,
    *,
    task_seed: int,
) -> EpisodeResetPlanV1:
    """Build RoleBinding plus the existing provider-facing v0 sample from declarations."""

    if not isinstance(source, TaskSourceV1) or not isinstance(scene, SceneDefinition):
        raise TypeError("reset planning requires TaskSourceV1 and SceneDefinition")
    if not isinstance(artifact, (TaskArtifact, TaskArtifactV1)):
        raise TypeError("reset plan requires TaskArtifact v0 or v1")
    if source.initialization is None:
        raise ValueError("Task Source requires an initialization sampler declaration")
    artifact.validate()
    role_binding = resolve_role_binding(source, scene, task_seed=task_seed, artifact=artifact)
    if artifact.initialization.settle_steps != 0:
        raise ValueError("current RuntimeSession reset route does not admit nonzero settle_steps")
    poses = dict(artifact.initialization.poses_world)
    joints = dict(artifact.initialization.joint_position)
    for dimension, value in _sample_dimensions(source, scene, artifact, task_seed):
        if not dimension.hard_bounds[0] <= value <= dimension.hard_bounds[1]:
            raise ValueError(f"sampled value violates hard bounds for {dimension.name!r}")
        _set_dimension_value(dimension.name, value, poses, joints, role_binding)

    initializer = source.initialization
    sample = ResetSample.create(
        schema_version="reset-sample-v0",
        task_artifact_hash=artifact.identity_hash,
        sampler_id=initializer.sampler_id,
        sampler_version=initializer.sampler_version,
        task_seed=task_seed,
        joint_position=joints,
        poses_world=poses,
        velocity_policy=initializer.velocity_policy,
        control_policy=initializer.control_policy,
        settle_steps=artifact.initialization.settle_steps,
    )
    return EpisodeResetPlanV1(
        "episode-reset-plan-v1", role_binding, sample, initializer.sampling_domain,
    )


def compile_task_artifact_v1(
    source: TaskSourceV1,
    scene: SceneDefinition,
    legacy_artifact: TaskArtifact,
    *,
    frame_bindings: Mapping[str, FrameReference] | None = None,
    joint_bindings: Mapping[str, JointReference] | None = None,
) -> TaskArtifactV1:
    """Compile the declared Source against one canonical Scene and v0 semantics.

    The v0 Artifact supplies task-facing action, initialization, semantic,
    timebase, observation, and capability contracts during this bounded bridge.
    Its duplicate ``WorldDefinition`` is not copied: every legacy entity/frame/
    joint reference must resolve into the supplied canonical Scene, which is
    referenced by its exact schema and identity. No runtime/provider is read.
    """
    if not isinstance(source, TaskSourceV1):
        raise TypeError("TaskArtifact v1 compilation requires TaskSourceV1")
    if not isinstance(scene, SceneDefinition):
        raise TypeError("TaskArtifact v1 compilation requires SceneDefinition")
    if not isinstance(legacy_artifact, TaskArtifact):
        raise TypeError("TaskArtifact v1 compilation requires the existing v0 semantic bridge")

    # Re-decode through each current owner so a caller cannot bypass strict
    # validation by mutating an object obtained through an untrusted path.
    source = TaskSourceV1.from_mapping(source.to_mapping())
    scene = SceneDefinition.from_mapping(scene.to_mapping())
    legacy_artifact = TaskArtifact.from_mapping(legacy_artifact.to_mapping())
    if source.task_id != legacy_artifact.task_id or source.version != legacy_artifact.artifact_version:
        raise ValueError("Task Source identity does not match the v0 semantic bridge")
    if source.scene_ref != scene.scene_id:
        raise ValueError("Task Source Scene reference does not match the canonical Scene")
    if scene.schema_version not in {"scene-definition-v2", "scene-definition-v3"}:
        raise ValueError("TaskArtifact v1 compilation requires a structured canonical Scene")

    scene_entities = {entity.entity_id for entity in scene.entities}
    scene_frames = {(frame.entity_id, frame.frame_id) for frame in scene.frames or ()}
    scene_joints = {
        (articulation.entity_id, joint.joint_id)
        for articulation in scene.articulations or ()
        for joint in articulation.joints
    }
    robot_entities = {robot.entity_id for robot in scene.robots or ()}

    def local_name(entity_id: str, name: str, kind: str) -> str:
        prefix = f"{entity_id}/"
        if name.startswith(prefix):
            return name[len(prefix):]
        if "/" in name:
            raise ValueError(f"legacy {kind} reference {name!r} belongs to another Entity")
        return name

    if frame_bindings is not None and not isinstance(frame_bindings, Mapping):
        raise TypeError("frame_bindings must be an explicit legacy-name mapping")
    if joint_bindings is not None and not isinstance(joint_bindings, Mapping):
        raise TypeError("joint_bindings must be an explicit legacy-name mapping")
    frame_bindings = {} if frame_bindings is None else dict(frame_bindings)
    joint_bindings = {} if joint_bindings is None else dict(joint_bindings)
    if any(not isinstance(value, FrameReference) for value in frame_bindings.values()):
        raise TypeError("frame_bindings values must be FrameReference")
    if any(not isinstance(value, JointReference) for value in joint_bindings.values()):
        raise TypeError("joint_bindings values must be JointReference")
    legacy_frames = {
        frame for entity in legacy_artifact.world.entities for frame in entity.frames
    }
    legacy_joints = {
        joint for entity in legacy_artifact.world.entities for joint in entity.joints
    }
    if set(frame_bindings) - legacy_frames or set(joint_bindings) - legacy_joints:
        raise ValueError("Scene binding contains an unknown legacy Frame or Joint")

    canonical_frames: dict[str, FrameReference] = {}
    canonical_joints: dict[str, JointReference] = {}
    legacy_entities = {entity.semantic_id: entity for entity in legacy_artifact.world.entities}
    for entity in legacy_artifact.world.entities:
        if entity.semantic_id not in scene_entities:
            raise ValueError(f"legacy Artifact Entity is absent from canonical Scene: {entity.semantic_id!r}")
        for frame in entity.frames:
            reference = frame_bindings.get(frame)
            if reference is None:
                reference = FrameReference(
                    entity.semantic_id, local_name(entity.semantic_id, frame, "Frame"),
                )
            if reference.entity_id != entity.semantic_id or (
                reference.entity_id, reference.frame_id
            ) not in scene_frames:
                raise ValueError(f"legacy Artifact Frame has no valid canonical Scene binding: {frame!r}")
            canonical_frames[frame] = reference
        for joint in entity.joints:
            reference = joint_bindings.get(joint)
            if reference is None:
                reference = JointReference(
                    entity.semantic_id, local_name(entity.semantic_id, joint, "Joint"),
                )
            if reference.entity_id != entity.semantic_id or (
                reference.entity_id, reference.joint_id
            ) not in scene_joints:
                raise ValueError(f"legacy Artifact Joint has no valid canonical Scene binding: {joint!r}")
            canonical_joints[joint] = reference
        if (entity.kind == "embodiment") != (entity.semantic_id in robot_entities):
            raise ValueError(f"legacy Artifact Robot role differs from canonical Scene: {entity.semantic_id!r}")

    # Reuse B02's selector/type/cardinality/overlap validation without asking
    # its v0 compatibility path to infer a renamed Frame or Joint. Bind roles
    # against A Scene and the source v0 Artifact explicitly, but do not sample.
    _validate_role_candidates(source, scene)
    for role in source.roles:
        for entity_id in role.selection_values:
            entity = legacy_entities.get(entity_id)
            if entity is None:
                raise ValueError(f"role {role.role_id!r} candidate is absent from the v0 semantic bridge")
            if role.entity_type == "robot" and entity.kind != "embodiment":
                raise ValueError(
                    f"role {role.role_id!r} candidate is not an embodiment TaskArtifact Entity"
                )
            if role.entity_type == "rigid_body" and entity.kind not in {"static", "movable"}:
                raise ValueError(
                    f"role {role.role_id!r} candidate is not a rigid-body TaskArtifact Entity"
                )

    source_mapping = source.to_mapping()
    source_retained_fields = tuple(
        f"/world/entities/{index}/{field}"
        for index, entity in enumerate(legacy_artifact.world.entities)
        for field in ("kind", "asset_reference", "geometry", "collision_intent", "parameters_si")
    )
    return TaskArtifactV1(
        schema_version="task-artifact-v1",
        artifact_id=legacy_artifact.artifact_id,
        task_id=source.task_id,
        artifact_version=source.version,
        source_artifact_schema_version=legacy_artifact.schema_version,
        source_artifact_identity_hash=legacy_artifact.identity_hash,
        source_retained_v0_fields=source_retained_fields,
        scene_schema_version=scene.schema_version,
        scene_id=scene.scene_id,
        scene_identity_hash=scene.identity_hash,
        legacy_frame_bindings=canonical_frames,
        legacy_joint_bindings=canonical_joints,
        task_source_schema_version=source.schema_version,
        task_source=source_mapping,
        task_source_identity_hash=source.identity_hash,
        action=legacy_artifact.world.action,
        world_convention=legacy_artifact.world.convention,
        observation_requirements=legacy_artifact.world.observation_requirements,
        initialization=legacy_artifact.initialization,
        semantics=legacy_artifact.semantics,
        timebase=legacy_artifact.timebase,
        required_capabilities=legacy_artifact.required_capabilities,
    )


def adapt_legacy_recipe_task_source(values: Mapping) -> TaskSourceV1:
    """Project the existing ``recipe``/``environment`` shape into B01's small envelope.

    The task-owned legacy config remains authoritative for execution. This adapter
    extracts identity, Scene reference, and exact entity roles only; it does not
    rewrite or hash TaskArtifact v0, and leaves ``environment`` to the existing
    ResolvedEnvConfig loader.
    """

    raw = _mapping(values, "legacy task config", required={"recipe", "environment"})
    recipe = raw["recipe"]
    if not isinstance(recipe, Mapping):
        raise TypeError("legacy recipe must be a mapping")
    if not isinstance(raw["environment"], Mapping):
        raise TypeError("legacy environment execution config must be a mapping")
    required_recipe = {"task_uid", "artifact_version", "scene_uid", "agent_uids", "object_uids"}
    missing = required_recipe - set(recipe)
    if missing:
        raise ValueError(f"legacy recipe is missing Task Source identity fields: {sorted(missing)}")
    agent_uids = _unique_identifiers(recipe["agent_uids"], "legacy agent_uids")
    object_uids = _unique_identifiers(recipe["object_uids"], "legacy object_uids")
    roles = {}
    for uid in agent_uids:
        roles[f"agent_{uid}"] = {
            "entity_type": "robot", "selection": {"ids": [uid]}, "cardinality": "exactly_one",
        }
    for uid in object_uids:
        roles[f"object_{uid}"] = {
            "entity_type": "rigid_body", "selection": {"ids": [uid]}, "cardinality": "exactly_one",
        }
    reset = recipe.get("reset")
    initialization = None
    if isinstance(reset, Mapping) and {"sampler_id", "sampler_version"} <= set(reset):
        initialization = {
            "sampler_id": reset["sampler_id"],
            "sampler_version": reset["sampler_version"],
            "sampling_domain": "training",
            "velocity_policy": "zero_named_joint_and_entity_velocities",
            "control_policy": "arm_targets_at_initial_joints_gripper_open",
        }
    return TaskSourceV1.from_mapping({
        "schema_version": _SOURCE_VERSION,
        "identity": {"task_id": recipe["task_uid"], "version": recipe["artifact_version"]},
        "scene": {"ref": recipe["scene_uid"]},
        "roles": roles,
        "initialization": initialization,
        "hooks": [],
    })


__all__ = [
    "TaskHookDeclarationV1",
    "TaskInitializationV1",
    "TaskRoleDeclarationV1",
    "TaskSourceV1",
    "adapt_legacy_recipe_task_source",
    "compile_task_artifact_v1",
    "load_task_source",
    "resolve_role_binding",
    "sample_episode_reset_plan",
]
