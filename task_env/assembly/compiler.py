"""Stage 1 task-specific scene composition adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
import xml.etree.ElementTree as ET

import numpy as np

from ..environment import EpisodePhysicsState, TaskCompositionSpec
from ..environment.task_source import TaskArtifactDeclarationV1
from ..utils._paths import callable_source_path
from .references import TaskReferences, resolve_task_references
from .logical_source import LogicalAssemblySourceProjectionV1, project_logical_assembly_source


@dataclass(frozen=True)
class CompiledTaskScene:
    imported_scene: object
    loader_result: object
    scene_model: object
    references: TaskReferences
    initial_state: EpisodePhysicsState
    composition_adapter: str


@dataclass(frozen=True)
class CompiledReferenceTaskV1:
    """Provider-free Artifact/source facts produced from one task declaration."""

    artifact: object
    source: object
    controller: object | None = None
    source_owners: tuple = ()

    def identity_fields(self, *, include_runtime_config_sha256: bool = True) -> dict[str, object]:
        return reference_task_identity_fields(
            self.artifact, self.source, self.controller,
            include_runtime_config_sha256=include_runtime_config_sha256,
        )


def reference_task_identity_fields(artifact, source, controller, *,
                                   include_runtime_config_sha256: bool = True) -> dict[str, object]:
    """Return the shared resolved identity facts for a compiled task route."""
    runtime_config = asdict(source.config)
    xml = source.scene_source.xml
    if not isinstance(xml, (str, bytes)):
        raise TypeError("reference source identity requires immutable XML bytes or text")
    xml_bytes = xml.encode("utf-8") if isinstance(xml, str) else xml
    result = {
        "artifact_sha256": artifact.identity_hash,
        "runtime_config": runtime_config,
        "source_xml_sha256": hashlib.sha256(xml_bytes).hexdigest(),
        "controller_identity": None if controller is None else controller.identity,
        "runtime_source_bindings": {
            name: dict(getattr(source, name))
            for name in ("joints", "bodies", "frames", "free_joints", "joint_targets")
        },
        "runtime_open_actuators": list(source.open_actuators),
    }
    if include_runtime_config_sha256:
        result["runtime_config_sha256"] = hashlib.sha256(json.dumps(
            runtime_config, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
    return result


def reference_construction_value(compiled, *, task_id, construction_schema, owners=(), binding=None, metadata=None):
    """Prepare a selected construction receipt from a compiled task and its owners.

    Source bytes are sampled for this construction, rather than cached by path.
    The caller may supply additional task-specific owners. When a selected
    binding is supplied, collect its declared callable owners as well; shared
    construction and lifecycle owners remain visible in provenance.
    """
    from ..controllers.canonical.contracts import digest
    from ..environment.lifecycle import EpisodeExecutionState
    from ..environment.reference_binding import ReferenceTaskBinding

    if compiled.controller is None:
        raise ValueError("selected reference construction requires a controller")
    root = Path(__file__).resolve().parents[2]
    binding_owners = ()
    if binding is not None:
        if type(binding) is not ReferenceTaskBinding:
            raise TypeError('construction binding must be an exact ReferenceTaskBinding')
        binding_owners = (type(binding), *(
            value for descriptor in fields(binding)
            if callable(value := getattr(binding, descriptor.name))
        ))
        if binding.scalar_control_binding is not None:
            binding_owners += (type(binding.scalar_control_binding),)
    all_owners = (*owners, *binding_owners, *compiled.source_owners, type(compiled), ReferenceTaskDeclarationV1,
                  TaskArtifactDeclarationV1, compile_reference_source,
                  reference_task_identity_fields, reference_construction_value,
                  callable_source_path, type(compiled.controller), EpisodeExecutionState)
    paths = set()
    for owner in all_owners:
        try:
            paths.add(callable_source_path(owner))
        except (TypeError, ValueError) as error:
            raise ValueError(f"construction owner has no source file: {owner!r}") from error
    source_hashes = {
        (path.relative_to(root).as_posix() if path.is_relative_to(root)
         else f'external:{path.name}'): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }
    if len(source_hashes) != len(paths):
        raise ValueError("construction owner source paths have ambiguous provenance names")
    metadata = {} if metadata is None else dict(metadata)
    identities = reference_task_identity_fields(compiled.artifact, compiled.source, compiled.controller)
    reserved = {'schema_version', 'task_id', 'source_sha256', 'solution', 'qualification'} | identities.keys()
    if metadata.keys() & reserved:
        raise ValueError('construction metadata conflicts with reserved fields')
    resolved = {
        **metadata, 'schema_version': construction_schema, 'task_id': task_id,
        **identities,
        'source_sha256': source_hashes,
        'solution': 'not_declared', 'qualification': 'NOT_REQUALIFIED',
    }
    return {
        'construction_id': construction_schema, 'artifact': compiled.artifact,
        'source': compiled.source, 'controller': compiled.controller, 'solution': None,
        'solution_identity': digest({'schema': 'no-task-solution-v1', 'task_id': task_id}),
        'recipe_identity': digest(resolved), 'resolved_configuration': resolved,
        'source_sha256': source_hashes,
    }


@dataclass(frozen=True)
class ReferenceTaskDeclarationV1:
    """Task data plus Core source bindings for a selected reference construction.

    The task owns scene bytes and semantic names; this declaration makes Core
    the single owner of Artifact validation and RuntimeSource binding.
    """

    artifact: TaskArtifactDeclarationV1
    composition: TaskCompositionSpec
    bodies: Mapping[str, str]
    frames: Mapping[str, str]
    free_joints: Mapping[str, str]
    joint_targets: Mapping[str, str]
    open_actuators: tuple[str, ...]
    joints: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if type(self.artifact) is not TaskArtifactDeclarationV1:
            raise TypeError("artifact must be a TaskArtifactDeclarationV1")
        if type(self.composition) is not TaskCompositionSpec:
            raise TypeError("composition must be a TaskCompositionSpec")
        if self.composition.task_uid != self.artifact.task_id:
            raise ValueError("task composition identity differs from Artifact declaration")
        for name in ("bodies", "frames", "free_joints", "joint_targets"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise TypeError(f"{name} must be a mapping")
            if any(not isinstance(key, str) or not key or not isinstance(item, str) or not item
                   for key, item in value.items()):
                raise ValueError(f"{name} must map nonempty names to nonempty names")
            object.__setattr__(self, name, MappingProxyType(dict(value)))
        if self.joints is not None:
            if not isinstance(self.joints, Mapping):
                raise TypeError("joints must be a mapping when supplied")
            object.__setattr__(self, "joints", MappingProxyType(dict(self.joints)))
        actuators = tuple(self.open_actuators)
        if any(not isinstance(value, str) or not value for value in actuators):
            raise ValueError("open_actuators must contain nonempty names")
        object.__setattr__(self, "open_actuators", actuators)

    def compile_source(self, artifact, *, scene_source, config, own_snapshot=False, **source_options):
        """Bind one declared Artifact to its source without native materialization."""
        expected = self.artifact.compile()
        if type(artifact) is not type(expected) or artifact.identity_hash != expected.identity_hash:
            raise ValueError("source Artifact does not match the task declaration")
        source = compile_reference_source(
            artifact=artifact,
            scene_source=scene_source,
            composition=self.composition,
            config=config,
            bodies=self.bodies,
            frames=self.frames,
            free_joints=self.free_joints,
            joint_targets=self.joint_targets,
            open_actuators=self.open_actuators,
            **({"joints": self.joints} if self.joints is not None else {}),
            **source_options,
        )
        if own_snapshot:
            from ..runtime.sessions.source import snapshot_legacy_mjcf_source
            source = snapshot_legacy_mjcf_source(source)
        return source

    def compile(self, *, scene_source, config, controller_factory: Callable | None = None,
                own_snapshot=False, **source_options) -> CompiledReferenceTaskV1:
        """Compile Artifact, source bindings and an optional pure controller."""
        artifact = self.artifact.compile()
        source = self.compile_source(
            artifact, scene_source=scene_source, config=config, own_snapshot=own_snapshot, **source_options,
        )
        from contextlib import nullcontext
        from ..runtime.sessions.source import close_execution_source_on_failure
        cleanup = close_execution_source_on_failure(source) if own_snapshot else nullcontext()
        with cleanup:
            controller = None
            if controller_factory is not None:
                if not callable(controller_factory):
                    raise TypeError("controller_factory must be callable")
                controller = controller_factory(artifact, source)
        return CompiledReferenceTaskV1(artifact, source, controller)


def _source_for_task(composition: TaskCompositionSpec, agents, scene, scene_composer=None):
    """Resolve source through the explicitly supplied composer or Scene owner."""
    for owner in (scene_composer, scene):
        build = getattr(owner, "build_scene_source", None)
        if callable(build):
            return build(composition, agents)
    raise NotImplementedError(
        f"no scene source composer for {composition.task_uid} / {composition.scene_uid}"
    )


def _build_scene_model(imported_scene, composition: TaskCompositionSpec, scene_composer=None):
    build_scene_model = getattr(scene_composer, "build_scene_model", None)
    if build_scene_model is not None:
        return build_scene_model(imported_scene, composition)
    return imported_scene.build_rigid_scene_model()


def _semantic_geom_names(source) -> tuple[str, ...]:
    """Return all authored MJCF geom names, including render-only geoms."""
    if getattr(source, "xml", None) is None:
        return ()
    root = ET.fromstring(source.xml)
    return tuple(
        name
        for geom in root.iter("geom")
        if (name := geom.get("name"))
    )


def _validate_external_assets(components) -> None:
    """Fail clearly when a repository/deployment asset prerequisite is absent."""

    missing: list[str] = []
    for component in components:
        manifest = component.asset_manifest()
        for path in manifest.mjcf_sources:
            if not path.is_file():
                missing.append(f"{manifest.owner_uid}: MJCF {path}")
        for path in manifest.asset_roots:
            if not path.is_dir():
                missing.append(f"{manifest.owner_uid}: asset root {path}")
    if missing:
        details = "; ".join(missing)
        raise FileNotFoundError(
            "TaskEnv external asset prerequisite missing; install or mount the "
            f"repository assets before building this environment: {details}"
        )


def _initial_state(scene_model, agents, references: TaskReferences) -> EpisodePhysicsState:
    joint_data = scene_model.joint_data
    n_qpos = int(joint_data.get("n_qpos", 0))
    n_dof = int(joint_data.get("n_dof", 0))
    n_act = int(joint_data.get("n_actuators", 0))
    qpos = np.asarray(
        joint_data.get("initial_qpos", np.zeros(max(n_qpos, 1))),
        dtype=np.float32,
    )[:n_qpos].copy()
    qvel = np.asarray(
        joint_data.get("initial_qvel", np.zeros(max(n_dof, 1))),
        dtype=np.float32,
    )[:n_dof].copy()
    ctrl = np.asarray(
        joint_data.get("initial_ctrl", np.zeros(max(n_act, 1))),
        dtype=np.float32,
    )[:n_act].copy()
    act = np.asarray(
        joint_data.get("initial_act", np.zeros(max(n_act, 1))),
        dtype=np.float32,
    )[:n_act].copy()

    for agent in agents:
        named_positions = dict(agent.initial_state_spec().joint_positions)
        for joint_name, value in named_positions.items():
            joint_id = references.names.joints[joint_name]
            qpos_adr = int(scene_model.joint_data["jnt_qposadr"][joint_id])
            qpos[qpos_adr] = np.float32(value)
        initial_control = getattr(agent, "component_initial_control", None)
        if initial_control is not None:
            targets, upper_limits = initial_control()
            agent_ref = references.agents[agent.uid]
            declaration = agent.reference_spec()
            target_actuators = tuple(name for name, _ in targets)
            if (len(set((*target_actuators, *upper_limits))) != len(target_actuators) + len(upper_limits)
                    or not set((*target_actuators, *upper_limits)) <= set(declaration.actuator_names)
                    or not {name for _, name in targets} <= set(declaration.joint_names)):
                raise ValueError("initial control must use distinct actuators and joints owned by the Robot")
            for actuator_name, joint_name in targets:
                actuator_id = references.names.actuators[actuator_name]
                joint_id = references.names.joints[joint_name]
                qpos_adr = int(joint_data["jnt_qposadr"][joint_id])
                ctrl[actuator_id] = qpos[qpos_adr]
            for actuator_name in upper_limits:
                actuator_id = references.names.actuators[actuator_name]
                ctrl[actuator_id] = agent_ref.ctrl_range[actuator_id, 1]

    return EpisodePhysicsState(
        qpos=qpos,
        qvel=qvel,
        qacc=np.zeros(n_dof, dtype=np.float32),
        ctrl=ctrl,
        act=act,
    )


_UNSET_COMPONENT = object()


def compile_reference_source(*, artifact, scene_source, composition, config,
                             bodies, frames, free_joints, joint_targets,
                             open_actuators, joints=None, scene=_UNSET_COMPONENT,
                             agents=_UNSET_COMPONENT, objects=_UNSET_COMPONENT, **source_options):
    """Bind semantic names and declared components to a provider-free source.

    Registered components are resolved from a TaskCompositionSpec by default.
    A benchmark with already compiled components can supply those values and a
    source-specific composition receipt explicitly.
    """
    from ..registry import make_agent, make_object, make_scene
    from ..runtime.sessions.source import RuntimeSource

    if joints is None:
        joints = {name: name.split("/", 1)[1] for name in artifact.initialization.joint_position}
    supplied = tuple(value is not _UNSET_COMPONENT for value in (scene, agents, objects))
    if not all(supplied):
        if scene is _UNSET_COMPONENT:
            scene = make_scene(composition.scene_uid)
        elif getattr(scene, 'uid', None) != composition.scene_uid:
            raise ValueError('supplied Scene differs from the task composition')
        if agents is _UNSET_COMPONENT:
            agents = tuple(make_agent(uid) for uid in composition.agent_uids)
        else:
            agents = tuple(agents)
            if tuple(getattr(agent, 'uid', None) for agent in agents) != composition.agent_uids:
                raise ValueError('supplied Robots differ from the task composition')
        if objects is _UNSET_COMPONENT:
            objects = tuple(make_object(uid) for uid in composition.object_uids)
        else:
            objects = tuple(objects)
            if tuple(getattr(item, 'uid', None) for item in objects) != composition.object_uids:
                raise ValueError('supplied objects differ from the task composition')
    return RuntimeSource(
        task_artifact_hash=artifact.identity_hash, scene_source=scene_source,
        joints=joints, bodies=bodies, frames=frames, free_joints=free_joints,
        joint_targets=joint_targets, open_actuators=tuple(open_actuators),
        composition=composition, config=config, scene=scene,
        agents=tuple(agents), objects=tuple(objects), **source_options,
    )


def compile_task_scene(
    *,
    composition: TaskCompositionSpec,
    scene,
    agents,
    objects,
    scene_composer=None,
) -> CompiledTaskScene:
    from scene import import_scene_source
    from ..environment.protocols import AgentComponent, RobotComponent

    # Robots represented by the source already own their scene identities.
    # Only components declaring the legacy asset/reference contract need the
    # corresponding import-time name and initial-state resolution.
    if any(not isinstance(agent, RobotComponent) for agent in agents):
        raise TypeError('scene agents must be Robot components')
    reference_agents = tuple(agent for agent in agents if isinstance(agent, AgentComponent))
    _validate_external_assets((*reference_agents, *objects))
    source, adapter_name = _source_for_task(composition, agents, scene, scene_composer)
    imported_scene = import_scene_source(source)
    scene_model = _build_scene_model(imported_scene, composition, scene_composer)
    # G4 场景导入不再暴露旧 loader_result；其 articulation 视图保留了
    # TaskEnv 编译期名称解析所需的 links/actuators 契约。
    loader_result = imported_scene.articulation
    references = resolve_task_references(
        loader_result=loader_result,
        scene_model=scene_model,
        semantic_geom_names=_semantic_geom_names(source),
        scene=scene,
        agents=reference_agents,
        objects=objects,
    )
    initial_state = _initial_state(scene_model, reference_agents, references)
    return CompiledTaskScene(
        imported_scene=imported_scene,
        loader_result=loader_result,
        scene_model=scene_model,
        references=references,
        initial_state=initial_state,
        composition_adapter=adapter_name,
    )


__all__ = [
    "CompiledReferenceTaskV1",
    "CompiledTaskScene",
    "ReferenceTaskDeclarationV1",
    "compile_task_scene",
    "reference_task_identity_fields",
    "reference_construction_value",
]
