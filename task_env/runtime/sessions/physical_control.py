"""Preflight and combine physical commands at the existing session boundary.

The module is provider-free. A native adapter must independently admit its
public API and source mapping before implementing the session write method.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType

from ...artifacts import FixedAttachmentPlanV1, FrameReference, SceneDefinition, resolve_logical_assembly
from ...artifacts.contracts import CapabilityAssessmentV1
from ...artifacts.logical_assembly import LogicalAssemblySubcomponentReferenceV1
from ...artifacts.state import CanonicalStateViewV1, CanonicalStateViewV2
from ...controllers.canonical.physical_commands import (
    PhysicalControlBindingV1, PhysicalCommandBatchV1, PhysicalControlReceiptV1,
    PhysicalBodyBuildReceiptV1, PhysicalJointBuildReceiptV1, PhysicalBufferPolicyV1,
    PhysicalJointChannelV1,
)


@dataclass(frozen=True)
class ControlledSubjectV1:
    """A subject's named channels in one already-declared source/Scene.

    Source ownership describes the declaration, not a second importer. Root
    attachment is a requirement: provider admission still has to prove it.
    """
    subject_id: str
    entity_id: str
    source_id: str
    source_closure_sha256: str
    source_ownership: str
    root_mode: str
    root_frame: FrameReference
    parent_subject_id: str | None
    channel_paths: tuple[tuple[str, ...], ...]
    controller_writers: tuple[str, ...]
    schema_version: str = 'controlled-subject-v1'
    attachment_plan: FixedAttachmentPlanV1 | None = None
    supported_controller_profiles: tuple[str, ...] = ()

    def __post_init__(self):
        from ...artifacts.contracts import FrameReference, _SHA256, _name
        if self.schema_version != 'controlled-subject-v1':
            raise ValueError('unsupported controlled subject version')
        for value in (self.subject_id, self.entity_id, self.source_id):
            _name(value)
        if self.source_ownership not in {'owns_source', 'references_existing'}:
            raise ValueError('subject source ownership is not declared')
        if type(self.source_closure_sha256) is not str or not _SHA256.fullmatch(self.source_closure_sha256):
            raise ValueError('subject requires an exact source closure digest')
        if self.root_mode not in {'fixed', 'free', 'constrained'}:
            raise ValueError('subject root mode is not declared')
        if type(self.root_frame) is not FrameReference or self.root_frame.entity_id != self.entity_id:
            raise ValueError('subject root requires an entity-qualified Frame')
        if self.parent_subject_id is not None:
            _name(self.parent_subject_id)
            if self.parent_subject_id == self.subject_id:
                raise ValueError('subject cannot parent itself')
            if self.root_mode != 'constrained':
                raise ValueError('a subject with a parent requires a constrained root')
        elif self.root_mode == 'constrained':
            raise ValueError('a constrained subject requires a parent')
        if self.attachment_plan is not None and type(self.attachment_plan) is not FixedAttachmentPlanV1:
            raise TypeError('subject attachment must be a typed FixedAttachmentPlanV1')
        if self.root_mode != 'constrained' and self.attachment_plan is not None:
            raise ValueError('only constrained subjects may declare an attachment')
        if (type(self.channel_paths) is not tuple or not self.channel_paths
                or any(type(path) is not tuple or not path for path in self.channel_paths)
                or len(set(self.channel_paths)) != len(self.channel_paths)):
            raise ValueError('subject requires unique named channel paths')
        for path in self.channel_paths:
            for part in path:
                _name(part)
        if (type(self.controller_writers) is not tuple or not self.controller_writers
                or len(set(self.controller_writers)) != len(self.controller_writers)):
            raise ValueError('subject requires unique Controller writers')
        for writer in self.controller_writers:
            _name(writer)
        if (type(self.supported_controller_profiles) is not tuple
                or len(set(self.supported_controller_profiles)) != len(self.supported_controller_profiles)):
            raise ValueError('subject supported Controller profiles must be a unique ordered tuple')
        for profile_id in self.supported_controller_profiles:
            _name(profile_id)

    @property
    def identity_hash(self):
        from ...controllers.canonical.contracts import digest
        payload = {'schema_version': self.schema_version, 'subject_id': self.subject_id,
            'entity_id': self.entity_id, 'source_id': self.source_id,
            'source_closure_sha256': self.source_closure_sha256,
            'source_ownership': self.source_ownership, 'root_mode': self.root_mode,
            'root_frame': self.root_frame.to_mapping(), 'parent_subject_id': self.parent_subject_id,
            'channel_paths': self.channel_paths, 'controller_writers': self.controller_writers,
            'attachment_plan_sha256': (None if self.attachment_plan is None
                                       else self.attachment_plan.identity_hash)}
        if self.supported_controller_profiles:
            payload['supported_controller_profiles'] = self.supported_controller_profiles
        return digest(payload)



@dataclass(frozen=True)
class SubjectJointDeclarationV1:
    """Source-adapter transmission facts for one subject-declared logical joint."""
    component_path: tuple[str, ...]
    joint_id: str
    owner_ids: tuple[str, ...]
    native_actuator: str
    transmission_id: str
    transmission_coefficient: float
    native_range: tuple[float, float]
    native_drive: str


def uniform_native_drive_mode(binding):
    """Admit the drive mode declared by all channels of a physical binding."""
    modes = {channel.native_drive for channel in binding.channels}
    if not modes:
        return 'position'
    if len(modes) != 1 or not modes <= {'position', 'disabled'}:
        raise ValueError('physical adapter requires one supported native drive mode')
    return next(iter(modes))


def compile_existing_subject_assembly(*, scene, artifact_sha256, source_id,
                                      source_closure_sha256, subject, declarations,
                                      assembly_id, nested_component_id=None):
    """Compile one existing Robot's declared joints, including optional nested parts."""
    from ...artifacts.logical_assembly import (LogicalAssemblyV1, LogicalAssemblyScenePinV1,
        LogicalAssemblyNestedMemberV1)
    from ...artifacts.logical_assembly_resolution import existing_entity_joint_members

    pin = LogicalAssemblyScenePinV1('logical-assembly-scene-pin-v1', scene.scene_id,
                                    scene.schema_version, scene.identity_hash)
    if nested_component_id is None:
        joint_paths = tuple((item.component_path, item.joint_id) for item in declarations)
    else:
        if any(len(item.component_path) < 2 or item.component_path[0] != 'robot' for item in declarations):
            raise ValueError('nested Robot component paths must start with robot')
        joint_paths = tuple((item.component_path[1:], item.joint_id) for item in declarations)
    owner, *refs = existing_entity_joint_members(scene, subject.entity_id, joint_paths)
    if nested_component_id is None:
        members, children = (owner, *refs), {}
    else:
        child = LogicalAssemblyV1('logical-assembly-v1', nested_component_id, 'v1', pin, tuple(refs))
        members = (owner, LogicalAssemblyNestedMemberV1('nested_assembly', ('robot',),
            child.assembly_id, child.revision, child.logical_content_sha256))
        children = {(child.assembly_id, child.revision): child}
    assembly = LogicalAssemblyV1('logical-assembly-v1', assembly_id, 'v1', pin, members)
    return compile_declared_subject_binding(scene, artifact_sha256, source_id,
        source_closure_sha256, assembly, children, (subject,), declarations)


def build_declared_effort_execution(*, scene, artifact, source, subject, declarations,
                                    assembly_id, controller_factory, state_joint_names,
                                    joint_bindings, frame_bindings, nested_component_id=None):
    """Compile one declared subject and bind its Controller to the Runtime execution."""
    from ...artifacts.state import StateFieldRequirement, StateRequirements

    if len(subject.controller_writers) != 1:
        raise ValueError('single-subject effort construction requires one declared writer')
    writer = subject.controller_writers[0]
    compiled = compile_existing_subject_assembly(scene=scene, artifact_sha256=artifact.identity_hash,
        source_id=source.source_id, source_closure_sha256=source.source_closure_digest,
        subject=subject, declarations=declarations, assembly_id=assembly_id,
        nested_component_id=nested_component_id)
    controller = controller_factory(compiled.binding, writer)
    requirements = StateRequirements('state-requirements-v1', 'controller', writer, tuple(
        StateFieldRequirement('state-field-requirement-v1', field, 'joint', subject.entity_id,
            name, 'required', 'evaluation_boundary', 'joint-definition', 'joint_state_query')
        for name in state_joint_names for field in ('joint_position', 'joint_velocity')))
    execution = PhysicalControlExecutionV1(compiled, (controller,), scene,
        joint_bindings, frame_bindings, requirements, 1, (subject,))
    execution.validate_source(scene=scene, artifact_sha256=artifact.identity_hash,
        source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
    return execution


def build_existing_subject_effort(robot, *, scene, artifact, source, profile_id,
                                  subject, declarations):
    """Compile the source-checked Robot declaration into an effort execution."""
    names = tuple(robot.state_joint_names)
    definitions = {joint.joint_id: joint for articulation in scene.articulations or ()
                   if articulation.entity_id == subject.entity_id for joint in articulation.joints}
    joint_bindings = {f'{subject.entity_id}/{name}': definitions[name] for name in names}
    frame_bindings = {name: FrameReference(*name.split('/', 1)) for name in source.bodies}

    def make_controller(binding, writer):
        units = tuple(channel.unit for channel in binding.channels)
        from ...controllers.canonical.physical_controller import select_subject_effort_controller
        return select_subject_effort_controller(subject, binding, profile_id=profile_id,
            writer_id=writer, units=units, cadence_s=artifact.timebase.control_dt)

    from dataclasses import replace
    execution = build_declared_effort_execution(scene=scene, artifact=artifact, source=source,
        subject=subject, declarations=declarations, assembly_id=robot.assembly_id,
        controller_factory=make_controller, state_joint_names=names,
        joint_bindings=joint_bindings, frame_bindings=frame_bindings)
    return replace(execution, selection_profile_id=profile_id)


def compile_declared_subject_binding(scene, artifact_sha256, source_id, source_closure_sha256,
                                     root, children, subjects, joint_declarations, bodies=()):
    """Build the existing physical binding from subjects, resolved joints and source facts.

    Source adapters must independently validate their transmission declarations
    against source bytes and native builds; this function does not import them.
    """
    if (type(subjects) is not tuple or not subjects
            or any(type(subject) is not ControlledSubjectV1 for subject in subjects)):
        raise TypeError('binding construction requires controlled subject declarations')
    if (type(joint_declarations) is not tuple
            or any(type(item) is not SubjectJointDeclarationV1 for item in joint_declarations)):
        raise TypeError('binding construction requires typed subject joint declarations')
    declared_paths = tuple(path for subject in subjects for path in subject.channel_paths)
    if (len(set(declared_paths)) != len(declared_paths)
            or tuple(item.component_path for item in joint_declarations) != declared_paths):
        raise ValueError('joint declarations must cover subject paths in declared order')
    resolved = resolve_logical_assembly(root, scene, children)
    leaves = {leaf.full_path: leaf.member for leaf in resolved.leaves}
    definitions = {(art.entity_id, joint.joint_id): joint
                   for art in scene.articulations or () for joint in art.joints}
    channels = []
    position = 0
    for subject in subjects:
        if (subject.source_id != source_id or subject.source_closure_sha256 != source_closure_sha256):
            raise ValueError('subject declaration refers to a foreign source')
        for path in subject.channel_paths:
            item = joint_declarations[position]
            position += 1
            leaf = leaves.get(path)
            if (type(leaf) is not LogicalAssemblySubcomponentReferenceV1
                    or leaf.target_kind != 'joint'
                    or (leaf.target.entity_id, leaf.target.joint_id) != (subject.entity_id, item.joint_id)):
                raise ValueError('subject joint declaration does not resolve to its named joint')
            joint = definitions.get((subject.entity_id, item.joint_id))
            if joint is None or joint.kind not in {'revolute', 'prismatic'} or joint.axis is None:
                raise ValueError('subject joint is not a supported Scene joint')
            if not item.owner_ids or not set(item.owner_ids) <= set(subject.controller_writers):
                raise ValueError('joint writers differ from subject declaration')
            coefficient = item.transmission_coefficient
            if (not math.isfinite(coefficient) or coefficient == 0
                    or len(item.native_range) != 2
                    or not all(math.isfinite(value) for value in item.native_range)
                    or item.native_range[0] > item.native_range[1]):
                raise ValueError('invalid declared source transmission')
            effort_range = tuple(sorted(coefficient * value for value in item.native_range))
            channel = PhysicalJointChannelV1('physical-joint-channel-v1', path, item.owner_ids,
                subject.entity_id, item.joint_id, 'dof0', joint.kind,
                _rotate(joint.pose_parent_from_joint.quaternion_wxyz, joint.axis),
                joint.parent_frame, 1, 'N*m' if joint.kind == 'revolute' else 'N',
                effort_range, item.native_actuator, item.transmission_id, coefficient,
                item.native_range, item.native_drive)
            channel.validate()
            channels.append(channel)
    binding = PhysicalControlBindingV1('physical-control-binding-v1', scene.identity_hash,
        artifact_sha256, source_id, source_closure_sha256, root.logical_content_sha256,
        tuple(channels), bodies)
    compiled = compile_physical_control_binding(scene, root, children, binding)
    from types import SimpleNamespace
    declared_writers = {writer for subject in subjects for writer in subject.controller_writers}
    validate_controlled_subjects(compiled, subjects,
        tuple(SimpleNamespace(writer_id=writer) for writer in sorted(declared_writers)))
    return compiled


def validate_controlled_subjects(compiled, subjects, controllers):
    """Match subjects and Controller writers to the real resolved channels."""
    if type(subjects) is not tuple or not subjects or any(type(s) is not ControlledSubjectV1 for s in subjects):
        raise TypeError('physical execution requires typed controlled subjects')
    resolved = _validate_physical_binding(compiled.scene, compiled.root, compiled.children, compiled.binding)
    by_id = {s.subject_id: s for s in subjects}
    if len(by_id) != len(subjects) or len({s.entity_id for s in subjects}) != len(subjects):
        raise ValueError('duplicate subject or entity ownership')
    entities = {e.entity_id for e in compiled.scene.entities}
    frames = {(f.entity_id, f.frame_id) for f in compiled.scene.frames or ()}
    source_owners = [s.source_id for s in subjects if s.source_ownership == 'owns_source']
    if len(source_owners) != len(set(source_owners)):
        raise ValueError('a source cannot have multiple subject owners')
    channels = {c.component_path: c for c in compiled.binding.channels}
    leaves = {leaf.full_path: leaf.member for leaf in resolved.leaves}
    used = set()
    writers = {getattr(c, 'writer_id', None) for c in controllers}
    for subject in subjects:
        if (subject.entity_id not in entities or subject.source_id != compiled.binding.source_id
                or subject.source_closure_sha256 != compiled.binding.source_closure_sha256):
            raise ValueError('subject entity or source is missing or foreign')
        if (subject.root_frame.entity_id, subject.root_frame.frame_id) not in frames:
            raise ValueError('subject root Frame is missing')
        roots = {a.root_frame_id for a in compiled.scene.articulations or ()
                 if a.entity_id == subject.entity_id}
        if subject.root_frame.frame_id not in roots:
            raise ValueError('subject root Frame is not an articulation root')
        if subject.source_ownership == 'owns_source':
            from ...artifacts.logical_assembly import LogicalAssemblyEntityMemberV1
            if not any(type(member) is LogicalAssemblyEntityMemberV1
                       and member.entity_id == subject.entity_id for member in leaves.values()):
                raise ValueError('source-owning subject needs an Assembly entity owner')
        chain, cursor = set(), subject
        while cursor.parent_subject_id is not None:
            if cursor.subject_id in chain:
                raise ValueError('controlled subject parent cycle')
            chain.add(cursor.subject_id)
            cursor = by_id.get(cursor.parent_subject_id)
            if cursor is None:
                raise ValueError('controlled subject parent is missing')
        if subject.root_mode == 'constrained':
            parent = by_id[subject.parent_subject_id]
            attachment = subject.attachment_plan
            if type(attachment) is not FixedAttachmentPlanV1:
                raise ValueError('constrained subject requires a source-bound attachment plan')
            if (attachment.parent_entity_id != parent.entity_id
                    or attachment.child_entity_id != subject.entity_id
                    or attachment.parent_root != parent.root_frame
                    or attachment.child_root != subject.root_frame
                    or attachment.scene_pin.scene_identity_sha256 != compiled.scene.identity_hash
                    or attachment.source_closure_sha256 != compiled.binding.source_closure_sha256):
                raise ValueError('subject attachment differs from its parent, Scene or source')
        if not set(subject.controller_writers) <= writers:
            raise ValueError('subject Controller writer is missing')
        for path in subject.channel_paths:
            channel = channels.get(path)
            member = leaves.get(path)
            if path in used or channel is None or channel.entity_id != subject.entity_id:
                raise ValueError('subject channel is missing, duplicated or foreign')
            if type(member) is not LogicalAssemblySubcomponentReferenceV1 or member.target_kind != 'joint':
                raise ValueError('subject channel does not resolve to a joint')
            if not set(channel.owner_ids) <= set(subject.controller_writers):
                raise ValueError('subject channel Controller writers differ')
            used.add(path)
        if tuple(channel.component_path for channel in compiled.binding.channels
                 if channel.component_path in subject.channel_paths) != subject.channel_paths:
            raise ValueError('subject channel order differs from physical binding')
    if used != set(channels):
        raise ValueError('every physical joint channel needs exactly one subject')


@dataclass(frozen=True)
class CompiledPhysicalBindingV1:
    """Declarations and inputs to be revalidated before every admission."""
    binding: PhysicalControlBindingV1
    scene: SceneDefinition
    root: object
    children: object


@dataclass(frozen=True)
class PhysicalControlExecutionV1:
    """Selected task's immutable control wiring, consumed by its existing Env."""
    compiled: CompiledPhysicalBindingV1
    controllers: tuple[object, ...]
    scene: SceneDefinition
    joint_bindings: object
    frame_bindings: object
    requirements: object
    generation: int
    subjects: tuple[ControlledSubjectV1, ...] = ()
    selection_profile_id: str | None = None

    def selected_runtime_builder(self, selected):
        from .selected_materialization import PhysicalRuntimeBuilder
        # A declared Position owner must create its admitted control session;
        # this execution then binds its physical port and initializes itself.
        return PhysicalRuntimeBuilder(self, bool(selected.position_capabilities),
                                      selected.selection_matches)

    def __post_init__(self):
        from collections.abc import Mapping
        from ...artifacts.state import StateRequirements
        _validate_compiled_binding(self.compiled)
        if type(self.scene) is not SceneDefinition or self.scene.identity_hash != self.compiled.binding.scene_sha256:
            raise ValueError('physical execution Scene differs from compiled binding')
        if (type(self.controllers) is not tuple or not self.controllers
                or any(not callable(getattr(controller, 'compute', None))
                       or getattr(controller, 'binding', None) != self.compiled.binding
                       or not isinstance(getattr(controller, 'identity', None), str)
                       or not isinstance(getattr(controller, 'writer_id', None), str)
                       or not controller.writer_id
                       for controller in self.controllers)):
            raise ValueError('physical execution Controllers differ from binding')
        if self.selection_profile_id is not None:
            if (type(self.selection_profile_id) is not str or not self.selection_profile_id
                    or any(getattr(controller, 'profile_id', None) != self.selection_profile_id
                           for controller in self.controllers)
                    or any(self.selection_profile_id not in subject.supported_controller_profiles
                           for subject in self.subjects)):
                raise ValueError('physical selection differs from its Controllers or subjects')
        if len({controller.identity for controller in self.controllers}) != len(self.controllers):
            raise ValueError('physical execution Controller identities must be unique')
        if len({controller.writer_id for controller in self.controllers}) != len(self.controllers):
            raise ValueError('physical execution Controller writers must be unique')
        if not isinstance(self.joint_bindings, Mapping) or not isinstance(self.frame_bindings, Mapping):
            raise TypeError('physical execution state bindings must be mappings')
        if type(self.requirements) is not StateRequirements:
            raise TypeError('physical execution requires typed state requirements')
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError('physical execution generation must be nonnegative')
        object.__setattr__(self, 'joint_bindings', MappingProxyType(dict(self.joint_bindings)))
        object.__setattr__(self, 'frame_bindings', MappingProxyType(dict(self.frame_bindings)))
        if self.subjects:
            validate_controlled_subjects(self.compiled, self.subjects, self.controllers)

    def controller_batch(self, action, view, context):
        """Compute one interval through the declared subject and existing Controller owners."""
        from collections.abc import Mapping
        if self.subjects:
            validate_controlled_subjects(self.compiled, self.subjects, self.controllers)
        if len(self.controllers) == 1 and (
                not isinstance(action, Mapping)
                or self._controller_action_space(self.controllers[0]).contains(action)
                or set(action) != {self.controllers[0].identity}):
            actions = {self.controllers[0].identity: action}
        elif isinstance(action, Mapping):
            actions = dict(action)
        else:
            raise TypeError('multiple physical Controllers require identity-keyed actions')
        if set(actions) != {controller.identity for controller in self.controllers}:
            raise ValueError('physical action must cover every bound Controller exactly once')
        parts = tuple(controller.compute(actions[controller.identity], view, context)
                      for controller in self.controllers)
        if any(type(part) is not PhysicalCommandBatchV1 or part.context != context for part in parts):
            raise ValueError('physical Controller returned a foreign or untyped batch')
        for controller, part in zip(self.controllers, parts, strict=True):
            if any(item.contribution.owner_id != controller.writer_id
                   for item in (*part.joint_efforts, *part.body_wrenches, *part.extensions)):
                raise ValueError('physical Controller contribution owner differs from binding')
            if self.subjects:
                paths = {path for s in self.subjects if controller.writer_id in s.controller_writers
                         for path in s.channel_paths}
                allowed = {c.target_key for c in self.compiled.binding.channels if c.component_path in paths}
                if any(item.target_key not in allowed for item in part.joint_efforts):
                    raise ValueError('Controller output is outside its subject channels')
        return PhysicalCommandBatchV1('physical-command-batch-v1', context,
            tuple(item for part in parts for item in part.joint_efforts),
            tuple(item for part in parts for item in part.body_wrenches),
            tuple(item for part in parts for item in part.extensions))

    def controller_versions(self):
        """Capture actual Controller identities and optional individual generations."""
        rows = []
        for controller in self.controllers:
            generation = getattr(controller, 'generation', None)
            if generation is not None and (type(generation) is not int or generation < 0):
                raise ValueError('physical Controller generation must be nonnegative')
            rows.append((controller.writer_id, controller.identity, generation))
        return tuple(rows)

    @property
    def requires_source_dynamics(self):
        return any(callable(getattr(controller, 'bind_model', None)) for controller in self.controllers)

    def initialize_controllers(self, session, publication):
        """Initialize the Controllers owned by this execution from one realized view."""
        from ...artifacts.state import CanonicalStatePublicationV2
        if type(publication) is not CanonicalStatePublicationV2:
            raise TypeError('physical Controller initialization requires typed V2 state')
        publication.view.validate_against_scene(self.scene)
        publication.view.validate_requirements(self.requirements)
        source_model = getattr(session, 'physical_source_dynamics_model', None)
        if self.requires_source_dynamics and not callable(source_model):
            from ...environment.types import StageUnavailableError
            raise StageUnavailableError('selected session has no source dynamics model')
        for controller in self.controllers:
            bind_model = getattr(controller, 'bind_model', None)
            if callable(bind_model):
                bind_model(source_model())
            initialize = getattr(controller, 'reset_from_realized_state', None)
            if callable(initialize):
                initialize(publication.view)

    def action_schema(self):
        """Describe the action inputs of the Controllers actually compiled here."""
        from gymnasium.spaces import Box, Dict
        def describe(controller):
            space = self._controller_action_space(controller)
            if isinstance(space, Box):
                return {'identity': controller.identity, 'shape': list(space.shape)}
            if isinstance(space, Dict) and all(isinstance(value, Box) for value in space.spaces.values()):
                return {'identity': controller.identity, 'components': {
                    key: {'shape': list(value.shape), 'dtype': str(value.dtype)}
                    for key, value in space.spaces.items()}}
            raise TypeError('physical Controller action schema requires a Box or named Box components')
        return {'schema_version': 'physical-control-actions-v1',
                'controllers': [describe(controller) for controller in self.controllers]}

    def action_space(self):
        """Compose declared Controller input spaces, retaining legacy shape-only callers."""
        from gymnasium.spaces import Dict

        spaces = {controller.identity: PhysicalControlExecutionV1._controller_action_space(controller)
                  for controller in self.controllers}
        return next(iter(spaces.values())) if len(spaces) == 1 else Dict(spaces)

    @staticmethod
    def _controller_action_space(controller):
        import numpy as np
        from gymnasium.spaces import Box, Space

        declared = getattr(controller, 'action_space', None)
        if declared is not None:
            if not isinstance(declared, Space):
                raise TypeError('physical Controller action_space must be a Gymnasium Space')
            shape = getattr(controller, 'action_shape', None)
            if shape is not None and declared.shape is not None and tuple(shape) != declared.shape:
                raise ValueError('physical Controller action shape differs from its action_space')
            return declared
        shape = getattr(controller, 'action_shape', None)
        if (type(shape) is not tuple or not shape
                or any(type(n) is not int or n < 1 for n in shape)):
            raise ValueError('physical Controller requires an action_space or legacy positive action shape')
        # Existing shape-only physical controllers retain their established v1 contract.
        return Box(-np.inf, np.inf, shape=shape, dtype=np.float32)

    def preflight(self, *, provider, backend, artifact, source):
        """Delegate source-bound admission to the selected physical adapter."""
        from importlib import import_module
        from ...environment.types import StageUnavailableError

        adapters = {
            ('mujoco', 'cpu'): ('.mujoco_physical', 'preflight_physical_mujoco'),
            ('geophys', 'cpu'): ('.geophys_physical', 'preflight_physical_geophys'),
            ('isaacsim', 'cuda'): ('.isaac_physical', 'preflight_physical_isaac'),
        }
        try:
            module, method = adapters[provider, backend]
        except KeyError as error:
            raise StageUnavailableError('physical-control RuntimeSession adapter is not implemented') from error
        return getattr(import_module(module, __package__), method)(self, artifact, source)

    def validate_source(self, *, scene, artifact_sha256, source_id, source_closure_sha256, source=None):
        """Recheck an execution selection against the actual task source."""
        _validate_compiled_binding(self.compiled)
        binding = self.compiled.binding
        if (type(scene) is not SceneDefinition or scene.identity_hash != self.scene.identity_hash
                or binding.artifact_sha256 != artifact_sha256
                or binding.source_id != source_id
                or binding.source_closure_sha256 != source_closure_sha256):
            raise ValueError('physical execution differs from selected Scene, Artifact, or source')
        if source is not None:
            joint_names = set(source.joints) | set(source.free_joints)
            frame_names = set(source.bodies) | set(source.frames)
            if (set(source.joints) & set(source.free_joints)
                    or set(source.bodies) & set(source.frames)
                    or set(self.joint_bindings) != joint_names
                    or set(self.frame_bindings) != frame_names):
                raise ValueError('physical state bindings must exactly cover selected source names')
            for subject in self.subjects:
                free = any(name.startswith(subject.entity_id + '/') for name in source.free_joints)
                if (subject.root_mode == 'free') != free:
                    raise ValueError('subject root mode differs from source free-joint binding')
                if subject.root_mode == 'constrained':
                    attachment = getattr(source, 'fixed_attachment_plan', None)
                    assembly = getattr(source, 'fixed_attachment_assembly', None)
                    if (type(attachment) is not FixedAttachmentPlanV1
                            or attachment.identity_hash != subject.attachment_plan.identity_hash
                            or assembly is None):
                        raise ValueError('subject attachment is not bound to the runtime source')
                    from ...assembly.panda_source_profiles import validate_panda_fixed_attachment_scene
                    validate_panda_fixed_attachment_scene(attachment, assembly, scene)
        self.action_space()


def _validate_physical_binding(scene, root, children, binding):
    if type(scene) is not SceneDefinition or type(binding) is not PhysicalControlBindingV1:
        raise TypeError('physical binding requires a canonical Scene and typed binding')
    resolved = resolve_logical_assembly(root, scene, children)
    if (scene.identity_hash != binding.scene_sha256
            or resolved.root_logical_content_sha256 != binding.logical_assembly_sha256):
        raise ValueError('physical binding Scene or logical Assembly identity mismatch')
    leaves = {leaf.full_path: leaf.member for leaf in resolved.leaves}
    joints = {(a.entity_id, j.joint_id): j for a in scene.articulations or () for j in a.joints}
    for channel in binding.channels:
        member = leaves.get(channel.component_path)
        if (type(member) is not LogicalAssemblySubcomponentReferenceV1
                or member.target_kind != 'joint'
                or (member.target.entity_id, member.target.joint_id)
                != (channel.entity_id, channel.joint_id)):
            raise ValueError('component path does not resolve to its declared joint')
        joint = joints.get((channel.entity_id, channel.joint_id))
        if joint is None or joint.kind != channel.kind or joint.axis is None:
            raise ValueError('physical channel joint kind or source does not match Scene')
        if channel.axis_frame != joint.parent_frame:
            raise ValueError('physical channel axis must use the declared parent frame')
        parent_axis = _rotate(joint.pose_parent_from_joint.quaternion_wxyz, joint.axis)
        if any(abs(a-b) > 1e-9 for a, b in zip(parent_axis, channel.axis, strict=True)):
            raise ValueError('physical channel axis differs from Scene')
    frames = {(frame.entity_id, frame.frame_id) for frame in scene.frames or ()}
    for body in binding.bodies:
        if (body.body_frame.entity_id, body.body_frame.frame_id) not in frames:
            raise ValueError('physical body binding references unknown Scene frame')
    return resolved


def compile_physical_control_binding(scene, root, children, binding):
    _validate_physical_binding(scene, root, children, binding)
    from collections.abc import Mapping
    if not isinstance(children, Mapping):
        raise TypeError('physical binding child catalog must be a mapping')
    return CompiledPhysicalBindingV1(binding, scene, root, MappingProxyType(dict(children)))


def _validate_compiled_binding(compiled):
    if type(compiled) is not CompiledPhysicalBindingV1:
        raise ValueError('physical binding must be compiled against Scene and Assembly')
    _validate_physical_binding(compiled.scene, compiled.root, compiled.children, compiled.binding)


@dataclass(frozen=True)
class ResolvedJointEffortV1:
    entity_id: str
    joint_id: str
    dof_id: str
    unit: str
    value: float
    contribution_ids: tuple[str, ...]
    clipped_before_sum: bool
    clipped_after_sum: bool


@dataclass(frozen=True)
class ResolvedBodyWrenchV1:
    entity_id: str
    body_id: str
    force_world_N: tuple[float, float, float]
    torque_at_body_origin_world_Nm: tuple[float, float, float]
    body_origin_world_m: tuple[float, float, float]
    contribution_ids: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedPhysicalBatchV1:
    """Admission output, before adapter mapping and native write."""
    input_batch: PhysicalCommandBatchV1
    binding_sha256: str
    joints: tuple[ResolvedJointEffortV1, ...]
    body_wrenches: tuple
    extensions: tuple
    accepted_receipt: PhysicalControlReceiptV1
    mapping_provenance: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedPhysicalSequenceV1:
    """Previously admitted batches and their aligned, nonoverlapping ranges."""
    action: object
    slices: tuple[tuple[int, int, ResolvedPhysicalBatchV1], ...]

    @property
    def action_sha256(self):
        return self.action.identity_hash

    @property
    def identity_hash(self):
        from ...controllers.canonical.contracts import digest
        return digest({'schema_version': 'resolved-physical-sequence-v1',
            'action_sha256': self.action_sha256,
            'slices': tuple({'start': start, 'end': end, 'batch_sha256': resolved.input_batch.identity_hash}
                            for start, end, resolved in self.slices)})


@dataclass(frozen=True)
class PhysicalSequenceAcknowledgementV1:
    """Native staging acknowledgement; it is not a force measurement."""
    sequence_sha256: str
    batch_sha256s: tuple[str, ...]
    producer_id: str

    @property
    def identity_hash(self):
        from ...controllers.canonical.contracts import digest
        return digest({'schema_version': 'physical-sequence-ack-v1',
            'sequence_sha256': self.sequence_sha256, 'batch_sha256s': self.batch_sha256s,
            'producer_id': self.producer_id})


def _clamp(value, bounds):
    return min(max(value, bounds[0]), bounds[1])


def _add(a, b):
    return tuple(x+y for x, y in zip(a, b, strict=True))


def _sub(a, b):
    return tuple(x-y for x, y in zip(a, b, strict=True))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _rotate(quat, vector):
    w, x, y, z = quat
    u = (x, y, z)
    uv = _cross(u, vector)
    uuv = _cross(u, uv)
    return tuple(v + 2*(w*a+b) for v, a, b in zip(vector, uv, uuv, strict=True))


def resolve_body_wrench_at_poses(item, body_frame, poses):
    """Resolve the declared total moment about its reference at current poses.

    The application point does not add a second moment to a torque already
    declared about another reference. It remains explicit for the equivalent
    point-wrench transformation and for validating the requested frame.
    """
    origin = poses[body_frame].position
    expression, point_frame = poses[item.expressed_in], poses[item.point_frame]
    reference_frame = poses[item.moment_reference_frame]
    force = _rotate(expression.quaternion_wxyz, item.force_N)
    torque_reference = _rotate(expression.quaternion_wxyz, item.torque_Nm)
    point = _add(point_frame.position, _rotate(point_frame.quaternion_wxyz, item.point))
    reference = _add(reference_frame.position,
                     _rotate(reference_frame.quaternion_wxyz, item.moment_reference))
    torque_point = _add(torque_reference, _cross(_sub(reference, point), force))
    torque_origin = _add(torque_point, _cross(_sub(point, origin), force))
    return origin, force, torque_origin


def prepare_physical_command_batch(compiled, batch, *, expected_context,
                                   assessment, registered_extensions=(),
                                   topology_sha256=None, state=None, body_build_receipt=None,
                                   joint_build_receipt=None, buffer_policy=None):
    """Admit the entire batch before any controller/session/provider write.

    Wrenches are transformed into world coordinates about the bound body
    origin using an exact-boundary immutable state publication.
    """
    _validate_compiled_binding(compiled)
    if type(batch) is not PhysicalCommandBatchV1:
        raise TypeError('physical command requires a typed batch')
    batch.validate()
    binding = compiled.binding
    context = batch.context
    if context != expected_context:
        raise ValueError('stale or foreign physical command context')
    if (context.boundary.scene_identity_hash != binding.scene_sha256
            or context.artifact_sha256 != binding.artifact_sha256
            or context.source_id != binding.source_id
            or context.source_closure_sha256 != binding.source_closure_sha256):
        raise ValueError('physical command differs from source-bound plan')
    if type(assessment) is not CapabilityAssessmentV1 or assessment.request_identity != binding.identity_hash:
        raise ValueError('physical command requires a binding-specific capability assessment')
    # Synthetic mappings can exercise pure admission, but cannot substantiate a
    # native-build/runtime capability declaration. Preserve that distinction in
    # the result instead of silently promoting a fixture into build evidence.
    receipts = tuple(x for x in (joint_build_receipt, body_build_receipt) if x is not None)
    if assessment.phase in {'native_build', 'runtime'} and any(
            getattr(x, 'provenance', None) != 'native_build' for x in receipts):
        raise ValueError('synthetic mapping cannot support native build or runtime assessment')
    capability_names = set()
    if batch.joint_efforts:
        capability_names.update(('joint_effort', 'transmission', 'native_drive_state'))
        if (type(joint_build_receipt) is not PhysicalJointBuildReceiptV1
                or joint_build_receipt.binding_sha256 != binding.identity_hash
                or joint_build_receipt.source_closure_sha256 != binding.source_closure_sha256
                or joint_build_receipt.provider_materialization_id != context.boundary.provider_materialization_id
                or set(joint_build_receipt.channels) != set(binding.channels)):
            raise ValueError('joint effort requires an exact session build mapping receipt')
    if batch.body_wrenches:
        capability_names.update(('body_force', 'body_torque', 'body_frame', 'body_offset_point'))
    if any(x.contribution.composition == 'sum' for x in (*batch.joint_efforts, *batch.body_wrenches)):
        capability_names.add('sum')
    if any(x.contribution.persistence == 'hold_reapply' for x in (*batch.joint_efforts, *batch.body_wrenches)):
        capability_names.add('hold_reapply')
        if (type(buffer_policy) is not PhysicalBufferPolicyV1
                or buffer_policy.binding_sha256 != binding.identity_hash
                or buffer_policy.provider_materialization_id != context.boundary.provider_materialization_id):
            raise ValueError('held load requires a source-bound clear/add or replace policy')
    capability_names.update(f'load_extension:{x.namespace}/{x.extension_schema}' for x in batch.extensions)
    rows = {r.capability_id: r for r in assessment.rows
            if r.requiredness == 'required' and r.object_ref == f'binding:{binding.identity_hash}'}
    if not capability_names <= rows.keys():
        raise ValueError('physical command capability assessment is incomplete')
    for name in capability_names:
        row = rows[name]
        if (row.provider_api != 'supported' or row.core_adapter != 'implemented'
                or row.dependency != 'available' or row.requirement_status != 'satisfied'
                or row.caller_restriction != 'none'):
            raise ValueError(f'physical command capability not admitted: {name}')
    for extension in batch.extensions:
        if extension.topology_sha256 != topology_sha256:
            raise ValueError('typed load extension topology is stale')
        if (extension.namespace, extension.extension_schema) not in registered_extensions:
            if extension.requiredness == 'required':
                raise ValueError('unknown required typed load extension')
            raise ValueError('optional extension is unavailable; it cannot be silently submitted')
    channels = {x.target_key: x for x in binding.channels}
    grouped = {}
    for item in batch.joint_efforts:
        channel = channels.get(item.target_key)
        if channel is None:
            raise ValueError('joint effort target is not source-bound')
        if (item.contribution.owner_id not in channel.owner_ids or
            (item.joint_kind, item.axis, item.axis_frame,
             item.sign, item.unit, item.limit)
                != (channel.kind, channel.axis, channel.axis_frame,
                    channel.sign, channel.unit, channel.effort_range)):
            raise ValueError('joint effort differs from its source-bound channel')
        if item.controller_law == 'explicit_full_pd' and channel.native_drive not in {'disabled', 'passive'}:
            raise ValueError('explicit PD overlaps an uncoordinated native drive')
        grouped.setdefault(item.target_key, []).append(item)
    results = []
    for key, items in sorted(grouped.items()):
        if len(items) > 1 and any(x.contribution.composition != 'sum' for x in items):
            raise ValueError('overlapping joint effort requires declared sum')
        orders = {x.contribution.limit_order for x in items}
        if len(orders) != 1:
            raise ValueError('summed joint contributions require the same limit order')
        order = next(iter(orders))
        bounds = channels[key].effort_range
        values = [x.value for x in items]
        if order == 'reject_outside' and any(not bounds[0] <= x <= bounds[1] for x in values):
            raise ValueError('joint effort exceeds pre-combination limit')
        pre = [_clamp(x, bounds) for x in values] if order == 'clip_before_sum' else values
        total = sum(pre)
        if order != 'clip_after_sum' and not bounds[0] <= total <= bounds[1]:
            raise ValueError('combined effort exceeds limit')
        final = _clamp(total, bounds) if order == 'clip_after_sum' else total
        results.append(ResolvedJointEffortV1(*key, channels[key].unit, final,
            tuple(x.contribution.contribution_id for x in items), pre != values, final != total))
    # A transmission is a scalar source-bound map, not an arbitrary independent
    # force vector. Every declared channel of a touched transmission is needed.
    result_map = {(x.entity_id, x.joint_id, x.dof_id): x for x in results}
    transmissions = {}
    for channel in binding.channels:
        transmissions.setdefault((channel.entity_id, channel.transmission_id), []).append(channel)
    for group in transmissions.values():
        touched = [x for x in group if x.target_key in result_map]
        if not touched:
            continue
        if len(touched) != len(group):
            raise ValueError('coupled transmission requires all named channels')
        # The source coefficient maps native actuator effort to its native
        # axis; sign maps that axis to the declared canonical direction.
        native = [x.sign * result_map[x.target_key].value / x.transmission_coefficient for x in group]
        if any(not math.isclose(x, native[0], rel_tol=0, abs_tol=1e-12) for x in native[1:]):
            raise ValueError('joint effort vector is not representable by source transmission')
        if not group[0].native_range[0] <= native[0] <= group[0].native_range[1]:
            raise ValueError('source transmission native range exceeded')
    body_results = []
    if batch.body_wrenches:
        if (type(body_build_receipt) is not PhysicalBodyBuildReceiptV1
                or body_build_receipt.binding_sha256 != binding.identity_hash
                or body_build_receipt.source_closure_sha256 != binding.source_closure_sha256
                or body_build_receipt.provider_materialization_id != context.boundary.provider_materialization_id):
            raise ValueError('body wrench requires an exact session build mapping receipt')
        if set(body_build_receipt.bodies) != set(binding.bodies):
            raise ValueError('body build mapping differs from declared source binding')
        if type(state) not in (CanonicalStateViewV1, CanonicalStateViewV2):
            raise TypeError('body wrench requires a typed canonical state snapshot')
        if state.boundary != context.boundary or state.sample_clock != context.clock:
            raise ValueError('body wrench frame state is stale or foreign')
        poses = {entry.frame: entry.pose_world for entry in state.frames}
        bindings = {(x.entity_id, x.body_id): x for x in binding.bodies}
        groups = {}
        for item in batch.body_wrenches:
            key = (item.entity_id, item.body_id)
            if key not in bindings:
                raise ValueError('body wrench target is not source-bound')
            if item.contribution.owner_id not in bindings[key].owner_ids:
                raise ValueError('body wrench owner is not bound to the target')
            groups.setdefault(key, []).append(item)
        for key, items in sorted(groups.items()):
            if len(items) > 1 and any(x.contribution.composition != 'sum' for x in items):
                raise ValueError('overlapping body wrenches require declared sum')
            body = bindings[key]
            try:
                origin = poses[body.body_frame].position
                force_total, torque_total = (0., 0., 0.), (0., 0., 0.)
                for item in items:
                    _origin, force, torque_origin = resolve_body_wrench_at_poses(item, body.body_frame, poses)
                    force_total, torque_total = _add(force_total, force), _add(torque_total, torque_origin)
            except KeyError as exc:
                raise ValueError(f'required body wrench frame is unavailable: {exc.args[0]}') from exc
            body_results.append(ResolvedBodyWrenchV1(*key, force_total, torque_total, origin,
                tuple(x.contribution.contribution_id for x in items)))
    ids = tuple(x.contribution.contribution_id for x in (*batch.joint_efforts, *batch.body_wrenches, *batch.extensions))
    receipt = PhysicalControlReceiptV1('physical-control-receipt-v1', context, batch.identity_hash,
                                       'accepted', ids, 'core-admission', 'per-channel')
    return ResolvedPhysicalBatchV1(batch, binding.identity_hash, tuple(results),
                                   tuple(body_results), batch.extensions, receipt,
                                   tuple(x.provenance for x in receipts))
