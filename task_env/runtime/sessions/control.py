"""Opt-in semantic control admission; legacy no-control materialize unchanged."""
from dataclasses import asdict, dataclass, field
from collections.abc import Mapping
import hashlib
import json
import math
from typing import Protocol
from .api import RuntimeSession, PROFILE
from ...controllers.canonical.feedback import CanonicalControlFeedback
from ...controllers.canonical.contracts import (
    AppliedCanonicalControl,
    CanonicalControlTarget,
    RequestedAction,
    StructuredActionRequestV1,
    MixedActuatorCommandV1,
)
from ...artifacts import (
    ActuatorReference,
    CapabilityClaim,
    CapabilityAdmissionError,
    ProviderCapabilityManifest,
    RequiredCapabilitySet,
    SceneDefinition,
    StateRequirements,
    admit_capabilities,
)
from ...artifacts.contracts import SUPPORTED_STATUSES
from ...environment.types import ActionModeSpec
from .api import materialize,provider_manifest
from .provenance import provider_build_identity
from ...controllers.canonical.contracts import digest

class ControlledRuntimeSession(RuntimeSession, Protocol):
    def control_feedback(
        self, state, *, actuator_force=None,
    ) -> CanonicalControlFeedback: ...
    def apply_control(self, target: CanonicalControlTarget) -> AppliedCanonicalControl: ...


CONTROL_REQUIRED=RequiredCapabilitySet(('articulated_robot','joint_position_actuation','joint_state_query','body_pose_query','frame_pose_query'))


def declared_source_capabilities(source):
    """Project only requirements present in the selected source bindings."""
    required = set()
    if getattr(source, 'joints', {}):
        required.update(('articulated_robot', 'joint_state_query'))
    if getattr(source, 'free_joints', {}):
        required.add('free_body')
    if (getattr(source, 'joint_targets', {}) or getattr(source, 'open_actuators', ())
            or getattr(source, 'position_actuators', {})):
        required.add('joint_position_actuation')
    if getattr(source, 'torque_actuators', {}):
        required.add('joint_torque_actuation')
    if getattr(source, 'bodies', {}):
        required.add('body_pose_query')
    if getattr(source, 'frames', {}):
        required.add('frame_pose_query')
    return RequiredCapabilitySet(tuple(sorted(required)))



@dataclass(frozen=True)
class SelectedPositionCapabilityV1:
    """Controller-provided typed Position construction and reset capability."""
    owner: object

    @property
    def writer_id(self):
        return self.owner.writer_id

    @property
    def entity_id(self):
        return self.owner.entity_id

    def controller_binding(self):
        return self.owner.controller_binding()

    def validate_plan(self, plan):
        return self.owner._validate_plan(plan)

    def initialize(self, publication, plan):
        return self.owner.reset(publication, plan)

    def selected_runtime_builder(self, selected):
        from .selected_materialization import PositionRuntimeBuilder
        matches = tuple(getattr(selected, 'selection_matches', ()))
        return PositionRuntimeBuilder(selected.position_capabilities,
                                      matches,
                                      selection_match_required=hasattr(selected, 'selection_matches'))


def _selected_position_capability(controller):
    factory = getattr(controller, 'selected_position_capability', None)
    capability = factory() if callable(factory) else None
    if type(capability) is not SelectedPositionCapabilityV1 or capability.owner is not controller:
        return None
    return capability


@dataclass(frozen=True)
class SelectedControllerBinding:
    """Admitted controller and profile facts for selected environment assembly."""
    controller: object
    position_profiles: tuple
    mixed: bool
    position: bool
    requires_reset_plan: bool = False
    position_capabilities: tuple = ()
    selection_matches: tuple = ()
    physical_execution: object | None = None


@dataclass(frozen=True)
class ControllerSelectionMatchV1:
    """Production evidence binding one selected Controller set to its subject."""

    schema_version: str
    selection_profile_id: str
    control_kind: str
    subject_ids: tuple[str, ...]
    entity_ids: tuple[str, ...]
    controller_identities: tuple[str, ...]
    writer_ids: tuple[str, ...]
    artifact_identity_sha256: str
    source_id: str
    source_closure_sha256: str
    scene_identity_sha256: str
    channel_keys: tuple[str, ...]
    channel_units: tuple[str, ...]
    resource_keys: tuple[tuple[str, str, str], ...]
    action_contract_sha256: str
    state_requirements_sha256: str
    model_requirement_sha256: str | None
    cadence_s: float

    def __post_init__(self):
        if self.schema_version != 'controller-selection-match-v1':
            raise ValueError('unsupported Controller selection match schema')
        if self.control_kind not in {'joint_effort', 'position'}:
            raise ValueError('unsupported matched Controller command kind')
        names = (self.selection_profile_id, self.source_id)
        if any(type(value) is not str or not value.strip() for value in names):
            raise ValueError('Controller selection match requires named identities')
        hashes = (self.artifact_identity_sha256, self.source_closure_sha256, self.scene_identity_sha256,
                  self.action_contract_sha256, self.state_requirements_sha256)
        if any(type(value) is not str or len(value) != 64
               or any(char not in '0123456789abcdef' for char in value) for value in hashes):
            raise ValueError('Controller selection match requires exact SHA-256 identities')
        if self.model_requirement_sha256 is not None and (
                len(self.model_requirement_sha256) != 64
                or any(char not in '0123456789abcdef' for char in self.model_requirement_sha256)):
            raise ValueError('Controller model requirement must be SHA-256')
        if (not self.subject_ids or len(set(self.subject_ids)) != len(self.subject_ids)
                or not self.entity_ids or len(set(self.entity_ids)) != len(self.entity_ids)
                or not self.controller_identities or len(set(self.controller_identities)) != len(self.controller_identities)
                or not self.writer_ids or len(set(self.writer_ids)) != len(self.writer_ids)):
            raise ValueError('Controller selection match requires unique subject/controller ownership')
        if (len(self.channel_keys) != len(self.channel_units) or not self.channel_keys
                or len(set(self.channel_keys)) != len(self.channel_keys)):
            raise ValueError('Controller selection match channels and units must align')
        if (len(self.resource_keys) != len(set(self.resource_keys))
                or any(row[2] not in self.writer_ids for row in self.resource_keys)):
            raise ValueError('Controller selection match resources must have unique declared writers')
        if not math.isfinite(self.cadence_s) or self.cadence_s <= 0:
            raise ValueError('Controller selection match cadence must be positive and finite')

    @property
    def identity_hash(self):
        return digest(asdict(self))


def is_admitted_position_profile_set(profiles):
    capabilities = tuple(_selected_position_capability(profile) for profile in profiles)
    return (bool(capabilities) and len(capabilities) <= 2 and all(capabilities)
            and len({item.writer_id for item in capabilities}) == len(capabilities)
            and len({item.entity_id for item in capabilities}) == len(capabilities))


def _selected_profile_label(value, fallback):
    resolved = value.get('resolved_configuration')
    if isinstance(resolved, Mapping):
        for key in ('controller_profile', 'selected_controller_profile_id'):
            candidate = resolved.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
    candidate = value.get('selected_controller_profile_id')
    return candidate if isinstance(candidate, str) and candidate else fallback


def _match_physical_execution(value):
    from .physical_control import PhysicalControlExecutionV1

    execution = value.get('physical_execution')
    profile_id = value.get('selected_controller_profile_id')
    if execution is None or profile_id is None:
        return None
    if type(execution) is not PhysicalControlExecutionV1:
        raise TypeError('selected physical Controller requires a typed execution')
    artifact, source = value.get('artifact'), value.get('source')
    if artifact is None or source is None:
        raise ValueError('selected physical Controller match requires its Artifact and source')
    execution.validate_source(scene=execution.scene, artifact_sha256=artifact.identity_hash,
        source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
    if len(execution.controllers) != len(execution.subjects):
        raise ValueError('selected physical Controller match requires one writer per declared subject')

    required_fields = {
        (item.field_name, item.entity_id, item.subject_id)
        for item in execution.requirements.requirements
        if item.requiredness == 'required' and item.sample_domain == 'evaluation_boundary'
    }
    action_rows, model_hashes, channel_keys, channel_units, resources = [], [], [], [], []
    writers, identities, subjects, entities = [], [], [], []
    for subject in execution.subjects:
        if profile_id not in subject.supported_controller_profiles:
            raise ValueError('selected Controller profile is not declared by the controlled subject')
        controllers = tuple(item for item in execution.controllers
                            if item.writer_id in subject.controller_writers)
        if len(controllers) != 1:
            raise ValueError('each selected subject requires exactly one matching Controller writer')
        controller = controllers[0]
        if getattr(controller, 'profile_id', None) != profile_id:
            raise ValueError('selected Controller implementation differs from the requested profile')
        if controller.binding is not execution.compiled.binding:
            raise ValueError('selected Controller binding is not the execution binding')
        controller_channels = tuple(getattr(controller, '_channels', ()))
        if not controller_channels:
            raise ValueError('selected Controller does not expose its declared output channels')
        if tuple(item.component_path for item in controller_channels) != subject.channel_paths:
            raise ValueError('selected Controller channel order differs from subject declaration')
        if any(item.entity_id != subject.entity_id or controller.writer_id not in item.owner_ids
               for item in controller_channels):
            raise ValueError('selected Controller channels or writer differ from subject binding')
        action_profile = getattr(controller, 'profile', None)
        model_requirement = getattr(action_profile, 'model_requirement', None)
        if model_requirement is not None:
            if (model_requirement.source_id, model_requirement.source_closure_sha256) != (
                    execution.compiled.binding.source_id,
                    execution.compiled.binding.source_closure_sha256):
                raise ValueError('selected Controller model is bound to a foreign source')
            if model_requirement.cadence_s != artifact.timebase.control_dt:
                raise ValueError('selected Controller model cadence differs from task timebase')
            expected_units = tuple('rad' if item.kind == 'revolute' else 'm'
                                   for item in controller_channels)
            if (model_requirement.joint_names != tuple(
                    f'{item.entity_id}/{item.joint_id}' for item in controller_channels)
                    or model_requirement.joint_units != expected_units
                    or model_requirement.output_units != tuple(item.unit for item in controller_channels)):
                raise ValueError('selected Controller model channel names or units differ from binding')
            for item in controller_channels:
                for field_name in ('joint_position', 'joint_velocity'):
                    if (field_name, item.entity_id, item.joint_id) not in required_fields:
                        raise ValueError(f'selected Controller model lacks required state field {field_name}')
            model_hashes.append(model_requirement.identity_hash)
        else:
            model_hashes.append(None)
        if action_profile is not None:
            action_rows.append({
                'action_names': action_profile.action_names,
                'action_to_effort': action_profile.action_to_effort,
                'action_key': getattr(action_profile, 'action_key', None),
                'action_low': getattr(action_profile, 'action_low', ()),
                'action_high': getattr(action_profile, 'action_high', ()),
            })
        else:
            action_rows.append({
                'action_key': getattr(controller, '_action_key', None),
                'ranges': tuple(item.effort_range for item in controller_channels),
            })
        for channel in controller_channels:
            key = f'{channel.entity_id}/{channel.joint_id}'
            channel_keys.append(key)
            channel_units.append(channel.unit)
            resources.append((channel.entity_id, channel.joint_id, controller.writer_id))
        writers.append(controller.writer_id)
        identities.append(controller.identity)
        subjects.append(subject.subject_id)
        entities.append(subject.entity_id)
    if len(resources) != len(set((entity, resource) for entity, resource, _ in resources)):
        raise ValueError('selected Controllers claim overlapping physical resources')
    match = ControllerSelectionMatchV1(
        'controller-selection-match-v1', profile_id, 'joint_effort',
        tuple(subjects), tuple(entities), tuple(identities), tuple(writers),
        artifact.identity_hash,
        execution.compiled.binding.source_id,
        execution.compiled.binding.source_closure_sha256,
        execution.scene.identity_hash, tuple(channel_keys), tuple(channel_units),
        tuple(resources), digest(tuple(action_rows)),
        digest(execution.requirements.to_mapping()),
        None if all(item is None for item in model_hashes) else digest(tuple(model_hashes)),
        artifact.timebase.control_dt)
    return match


def _match_position_profiles(value, profiles):
    capabilities = tuple(_selected_position_capability(item) for item in profiles)
    if not capabilities or not all(capabilities):
        return ()
    if not value.get('source') or not value.get('artifact'):
        return ()
    source, artifact = value['source'], value['artifact']
    configured_profile = _selected_profile_label(value, capabilities[0].owner.profile_id)
    source_id, source_closure = source.source_id, source.source_closure_digest
    scene = source.scene_definition
    groups_by_key = {
        (group.entity_id, group.group_id): group
        for group in (scene.control_groups or ())
    }
    controller_identities, writers, subjects, entities = [], [], [], []
    channel_keys, channel_units, resources, action_rows, state_hashes, model_hashes = [], [], [], [], [], []
    for capability in capabilities:
        owner = capability.owner
        binding = capability.controller_binding()
        if (owner.source.source_id, owner.source.source_closure_digest,
                owner.scene.identity_hash, owner.artifact.identity_hash) != (
                source_id, source_closure, scene.identity_hash, artifact.identity_hash):
            raise ValueError('selected Position Controller differs from source, Scene, or Artifact')
        if binding.writer_id != capability.writer_id or binding.controller_identity not in (None, owner.identity):
            raise ValueError('selected Position Controller identity differs from its typed binding')
        target_bindings = getattr(owner, '_target_bindings', {})
        if not target_bindings:
            raise ValueError('selected Position Controller has no declared joint resource mapping')
        owner_keys = tuple(sorted(target_bindings))
        joints = {(art.entity_id, joint.joint_id): joint
                  for art in scene.articulations or () for joint in art.joints}
        for key in owner_keys:
            entity_id, joint_id = key.split('/', 1)
            joint = joints.get((entity_id, joint_id))
            if joint is None:
                raise ValueError('selected Position Controller resource is absent from its Scene')
            channel_keys.append(key)
            channel_units.append('rad' if joint.kind == 'revolute' else 'm')
        # Match physical resources in the same key space as the compiled plan.
        # Position target_bindings are native Joint/DOF names on some providers
        # (notably the admitted F06 USD route), while ControlBindingPlanV1 owns
        # authored Scene actuator resources.  Keep those two mappings separate:
        # the profile/source identity binds native targets, and these Scene
        # ControlGroups bind the Controller's actuator write set.
        for projection in binding.groups:
            group = groups_by_key.get(projection.key)
            if group is None or projection.entity_id != owner.entity_id:
                raise ValueError('selected Position Controller references a foreign Scene ControlGroup')
            for resource in group.actuator_refs:
                if resource.entity_id != owner.entity_id:
                    raise ValueError('selected Position Controller actuator is outside its subject Entity')
                resources.append((resource.entity_id, resource.actuator_id, binding.writer_id))
        controller_identities.append(owner.identity)
        writers.append(binding.writer_id)
        subjects.append(owner.profile_id)
        entities.append(owner.entity_id)
        action_rows.append(asdict(binding.action_schema))
        state_hashes.append(digest(binding.feedback_requirements.to_mapping()))
        model = getattr(owner, 'model', None)
        model_hashes.append(getattr(model, 'identity', None)
                            or getattr(model, 'identity_hash', None)
                            or getattr(model, 'source_sha256', None))
    if len(resources) != len(set((entity, resource) for entity, resource, _ in resources)):
        raise ValueError('selected Position Controllers claim overlapping actuator resources')
    return (ControllerSelectionMatchV1(
        'controller-selection-match-v1', configured_profile, 'position',
        tuple(subjects), tuple(entities), tuple(controller_identities), tuple(writers),
        artifact.identity_hash, source_id, source_closure, scene.identity_hash,
        tuple(channel_keys), tuple(channel_units),
        tuple(resources), _schema_hash(tuple(action_rows)), digest(tuple(state_hashes)),
        None if all(item is None for item in model_hashes) else digest(tuple(model_hashes)),
        artifact.timebase.control_dt),)


def bind_selected_controller(value, *, binding, provider, backend):
    """Admit a declared controller against its source and execution route."""
    if value.get('leaf_plan') is not None:
        raise ValueError('diagnostic leaf Position execution has been retired')

    raw = value['controller']
    if value.get('selected_controller_kind') == 'mixed_actuator_v1':
        plan = getattr(value.get('source'), 'mixed_actuator_plan', None)
        if (binding is None or binding.build_mixed_control_profile is None or plan is None
                or not callable(getattr(raw, 'compute_target', None))
                or not callable(getattr(raw, 'identity_mapping', None))
                or type(getattr(raw, 'identity', None)) is not str
                or getattr(plan, 'controller_identity', None) != raw.identity):
            raise TypeError('mixed-control route requires a controller bound to its typed source plan')
        return SelectedControllerBinding(raw, (), True, False)

    profiles = tuple(raw) if isinstance(raw, (tuple, list)) else (raw,)
    capabilities = tuple(_selected_position_capability(item) for item in profiles)
    if capabilities and all(capabilities):
        if len(profiles) > 2 or len({item.writer_id for item in profiles}) != len(profiles):
            raise ValueError('selected Position route admits one writer or the bounded two-Entity profile set')
        if len({item.entity_id for item in profiles}) != len(profiles):
            raise ValueError('selected Position writers must bind distinct Entities')
        profiles = tuple(sorted(profiles, key=lambda item: item.entity_id))
        capabilities = tuple(_selected_position_capability(item) for item in profiles)
        matches = _match_position_profiles(value, profiles)
        return SelectedControllerBinding(profiles[0], profiles, False, True, True,
                                         capabilities, matches)
    if isinstance(raw, (tuple, list)):
        raise TypeError('legacy selected routes do not accept a Controller profile collection')
    physical_match = _match_physical_execution(value)
    physical_execution = value.get('physical_execution') if physical_match is not None else None
    return SelectedControllerBinding(raw, (), False, False,
                                     value.get('physical_execution') is not None,
                                     (), (() if physical_match is None else (physical_match,)),
                                     physical_execution)


def mixed_substep_controller(hook, env, prepared):
    """Validate each task-produced native-rate command and retain its receipt."""
    controller_receipts = []

    def make_substep_command(state, substep_index, substep_count, state_revision):
        control = hook(env, prepared, state, substep_index, substep_count, state_revision)
        if not isinstance(control, Mapping) or set(control) != {'target', 'controller_receipt'}:
            raise TypeError('mixed substep Controller hook returned unknown or missing fields')
        target = control['target']
        if type(target) is not MixedActuatorCommandV1:
            raise TypeError('mixed substep Controller hook must return MixedActuatorCommandV1')
        target.validate()
        receipt = control['controller_receipt']
        if not isinstance(receipt, Mapping):
            raise TypeError('mixed substep Controller receipt must be a mapping')
        controller_receipts.append(dict(receipt))
        return target

    return make_substep_command, controller_receipts


def mixed_stepwise_receipt(receipt, controller_receipts, *, substeps, target):
    """Bind each controller receipt to the native interval and its first target."""
    if (not isinstance(receipt, Mapping)
            or not isinstance(receipt.get('substeps'), list)
            or len(receipt['substeps']) != substeps
            or len(controller_receipts) != substeps):
        raise ValueError('RuntimeSession stepwise receipt differs from the admitted substep count')
    rows = [{**dict(row), 'controller_receipt': controller_receipt}
            for row, controller_receipt in zip(receipt['substeps'], controller_receipts, strict=True)]
    result = {**dict(receipt), 'substeps': rows}
    first_row = rows[0]
    applied = first_row.get('applied')
    if (not isinstance(applied, Mapping)
            or first_row.get('target_identity_sha256') != target.identity_hash
            or first_row.get('target') != target.to_mapping()):
        raise ValueError('stepwise RuntimeSession first command differs from prepared outer target')
    return result, applied


def validate_mixed_control_preparation(prepared, *, stepwise, source, artifact, session, sample, before):
    """Validate task-prepared mixed controls against the live RuntimeSession boundary."""
    fields = {'action_values', 'universal_action', 'request', 'target', 'writer_control'}
    if stepwise:
        fields.add('substep_context')
    if not isinstance(prepared, Mapping) or set(prepared) != fields:
        raise TypeError('mixed-control preparation must return the exact typed preparation fields')
    action_values = tuple(float(value) for value in prepared['action_values'])
    universal_action = tuple(float(value) for value in prepared['universal_action'])
    if (not action_values or len(action_values) != len(universal_action)
            or any(not math.isfinite(value) for value in (*action_values, *universal_action))):
        raise ValueError('mixed-control task preparation returned invalid action values')
    request, target, writer_control = prepared['request'], prepared['target'], prepared['writer_control']
    if type(request) is not StructuredActionRequestV1 or type(target) is not MixedActuatorCommandV1:
        raise TypeError('mixed-control preparation must return a StructuredActionRequest and MixedActuatorCommand')
    request.validate()
    target.validate()
    if not isinstance(writer_control, Mapping) or set(writer_control) != {
        'writer_id', 'action_schema_id', 'components', 'groups', 'requested_action', 'canonical_action',
    }:
        raise TypeError('mixed-control task writer metadata has unknown or missing fields')
    if (target.plan_identity_hash != source.mixed_actuator_plan.identity_hash
            or target.task_artifact_hash != artifact.identity_hash
            or target.source_id != source.scene_source.source_id
            or target.source_closure_digest != source.source_closure_digest
            or target.provider_materialization_id != session.provider_materialization_id
            or target.episode_id != session.episode_id
            or target.reset_sample_id != sample.sample_id
            or target.control_step != session.snapshot().control_step
            or target.state_revision != session.state_revision
            or target.simulation_time_s != before.simulation_time):
        raise ValueError('mixed-control target differs from the live source boundary')
    return action_values, universal_action, request, target, writer_control


def _binding_identity(value):
    """Hash static schemas with explicit tokens for ActionModeSpec's infinite bounds."""
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            raise ValueError('binding identity cannot contain NaN')
        return 'Infinity' if value > 0 else '-Infinity'
    if isinstance(value, dict):
        return {key: _binding_identity(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_binding_identity(item) for item in value]
    return value


def _schema_hash(value):
    payload = json.dumps(_binding_identity(value), sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ControlGroupActionProjectionV1:
    """The action components a ControllerBinding assigns to one A03 group."""

    schema_version: str
    entity_id: str
    group_id: str
    action_components: tuple[str, ...]

    def __post_init__(self):
        from ...artifacts.contracts import _name
        if self.schema_version != 'control-group-action-projection-v1':
            raise ValueError('unsupported ControlGroup action projection schema')
        _name(self.entity_id)
        _name(self.group_id)
        components = tuple(str(value) for value in self.action_components)
        if not components or any(not value.strip() for value in components):
            raise ValueError('ControlGroup action projection requires named components')
        if len(components) != len(set(components)):
            raise ValueError('ControlGroup action projection has duplicate components')
        object.__setattr__(self, 'action_components', components)

    @property
    def key(self):
        return self.entity_id, self.group_id


@dataclass(frozen=True)
class ControllerBindingV1:
    """One existing Controller writer and its complete group/action/feedback contract."""

    schema_version: str
    writer_id: str
    action_schema: ActionModeSpec
    feedback_schema_id: str
    feedback_schema_version: str
    feedback_requirements: StateRequirements
    groups: tuple[ControlGroupActionProjectionV1, ...]
    controller_identity: str | None = None
    controller_kinematics_identity: str | None = None

    def __post_init__(self):
        from ...artifacts.contracts import _name
        if self.schema_version != 'controller-binding-v1':
            raise ValueError('unsupported ControllerBinding schema')
        _name(self.writer_id)
        if not isinstance(self.action_schema, ActionModeSpec):
            raise TypeError('ControllerBinding requires an existing ActionModeSpec')
        if not self.feedback_schema_id.strip() or not self.feedback_schema_version.strip():
            raise ValueError('ControllerBinding requires an explicit feedback schema identity')
        if not isinstance(self.feedback_requirements, StateRequirements):
            raise TypeError('ControllerBinding requires existing typed StateRequirements')
        for name in ('controller_identity', 'controller_kinematics_identity'):
            value = getattr(self, name)
            if value is not None and (
                len(value) != 64 or any(char not in '0123456789abcdef' for char in value)
            ):
                raise ValueError(f'ControllerBinding {name} must be a SHA-256')
        if (self.feedback_requirements.consumer_kind, self.feedback_requirements.consumer_id) != (
            'controller', self.writer_id,
        ):
            raise ValueError('feedback requirements must belong to the bound Controller writer')
        groups = tuple(self.groups)
        if not groups or any(not isinstance(group, ControlGroupActionProjectionV1) for group in groups):
            raise ValueError('ControllerBinding requires explicit ControlGroup projections')
        object.__setattr__(self, 'groups', tuple(sorted(groups, key=lambda group: group.key)))


@dataclass(frozen=True)
class ControlBindingPlanV1:
    """Immutable, source-bound binding snapshot; it owns no Controller or Runtime state."""

    schema_version: str
    scene_identity_hash: str
    controller_bindings: tuple[ControllerBindingV1, ...]
    resource_writers: tuple[tuple[str, str, str], ...]
    artifact_identity_hash: str | None = None
    source_closure_digest: str | None = None
    assembly_identity_hash: str | None = None
    cross_entity_frame_grants: tuple[tuple[str, str, str], ...] = ()
    feedback_attachment_identity_hash: str | None = None
    _compiled: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self):
        if self.schema_version != 'control-binding-plan-v1':
            raise ValueError('unsupported ControlBindingPlan schema')
        if len(self.scene_identity_hash) != 64:
            raise ValueError('ControlBindingPlan requires a Scene identity')
        for name in ('artifact_identity_hash', 'source_closure_digest', 'assembly_identity_hash',
                     'feedback_attachment_identity_hash'):
            value = getattr(self, name)
            if value is not None and (
                len(value) != 64 or any(char not in '0123456789abcdef' for char in value)
            ):
                raise ValueError(f'ControlBindingPlan {name} must be a SHA-256')
        object.__setattr__(self, 'controller_bindings', tuple(sorted(
            self.controller_bindings, key=lambda binding: binding.writer_id,
        )))
        object.__setattr__(self, 'resource_writers', tuple(sorted(self.resource_writers)))
        grants = tuple(sorted(self.cross_entity_frame_grants))
        if (any(type(row) is not tuple or len(row) != 3 or any(type(x) is not str or not x for x in row)
                for row in grants) or len(grants) != len(set(grants))
                or bool(grants) != (self.feedback_attachment_identity_hash is not None)):
            raise ValueError('cross-entity feedback grants require one exact attachment identity')
        object.__setattr__(self, 'cross_entity_frame_grants', grants)
        writer_ids = {binding.writer_id for binding in self.controller_bindings}
        if len(writer_ids) != len(self.controller_bindings):
            raise ValueError('ControlBindingPlan contains duplicate Controller writers')
        resource_keys = tuple((entity_id, actuator_id) for entity_id, actuator_id, _writer in self.resource_writers)
        if len(resource_keys) != len(set(resource_keys)):
            raise ValueError('ControlBindingPlan contains overlapping actuator writers')
        if any(writer_id not in writer_ids for _entity_id, _actuator_id, writer_id in self.resource_writers):
            raise ValueError('ControlBindingPlan resource writer is not bound')

    def position_state_requirements(self):
        """Return the typed state declared by the compiled Position writers."""
        if not self._compiled or not 1 <= len(self.controller_bindings) <= 2:
            raise ValueError('Position state requires one or two compiled Controller bindings')
        requirements = tuple(binding.feedback_requirements for binding in self.controller_bindings)
        if len(requirements) == 1:
            return requirements[0]
        return StateRequirements('state-requirements-v1', 'controller', 'c02b-dual-position-dispatch-v1',
            tuple(item for requirement in requirements for item in requirement.requirements))

    def initial_materialization_receipt(self, _session):
        return None

    @property
    def identity_hash(self):
        payload = {
            'schema_version': self.schema_version,
            'scene_identity_hash': self.scene_identity_hash,
            'controller_bindings': [
                {
                    'schema_version': binding.schema_version,
                    'writer_id': binding.writer_id,
                    'action_schema': asdict(binding.action_schema),
                    'feedback_schema_id': binding.feedback_schema_id,
                    'feedback_schema_version': binding.feedback_schema_version,
                    'feedback_requirements': binding.feedback_requirements.to_mapping(),
                    **({'controller_identity': binding.controller_identity}
                       if binding.controller_identity is not None else {}),
                    **({'controller_kinematics_identity': binding.controller_kinematics_identity}
                       if binding.controller_kinematics_identity is not None else {}),
                    'groups': [
                        {
                            'schema_version': group.schema_version,
                            'entity_id': group.entity_id,
                            'group_id': group.group_id,
                            'action_components': group.action_components,
                        }
                        for group in binding.groups
                    ],
                }
                for binding in self.controller_bindings
            ],
            'resource_writers': self.resource_writers,
        }
        # Keep historical v1 plan hashes byte-for-byte stable when these
        # source-instance bindings are absent. New bounded R1 plans include
        # them so a writer name cannot stand in for a constructed Controller.
        if self.assembly_identity_hash is not None:
            payload['assembly_identity_hash'] = self.assembly_identity_hash
        if self.artifact_identity_hash is not None:
            payload['artifact_identity_hash'] = self.artifact_identity_hash
        if self.source_closure_digest is not None:
            payload['source_closure_digest'] = self.source_closure_digest
        if self.cross_entity_frame_grants:
            payload['cross_entity_frame_grants'] = self.cross_entity_frame_grants
            payload['feedback_attachment_identity_hash'] = self.feedback_attachment_identity_hash
        return _schema_hash(payload)


def compile_control_binding_plan(
    scene: SceneDefinition,
    controller_bindings: tuple[ControllerBindingV1, ...],
    *,
    artifact_identity_hash: str | None = None,
    source_closure_digest: str | None = None,
    logical_assembly=None,
    assembly_children=(),
    cross_entity_frame_grants=(),
    feedback_attachment=None,
    feedback_attachment_scene=None,
) -> ControlBindingPlanV1:
    """Resolve each A03 ControlGroup to exactly one existing writer and schema."""
    if not isinstance(scene, SceneDefinition) or scene.schema_version != 'scene-definition-v3':
        raise ValueError('Controller bindings require a canonical scene-definition-v3')
    if not isinstance(controller_bindings, tuple):
        raise TypeError('Controller bindings must be an immutable tuple')
    assembly_identity = None
    assembly_entities = set()
    if logical_assembly is not None:
        from ...artifacts.logical_assembly import LogicalAssemblyEntityMemberV1
        from ...artifacts.logical_assembly_resolution import resolve_logical_assembly
        resolved = resolve_logical_assembly(logical_assembly, scene, assembly_children)
        assembly_identity = resolved.root_logical_content_sha256
        assembly_entities = {leaf.member.entity_id for leaf in resolved.leaves
                             if type(leaf.member) is LogicalAssemblyEntityMemberV1}
        if not assembly_entities:
            raise ValueError('Controller Assembly must own at least one Scene entity')
    elif assembly_children:
        raise ValueError('Assembly children require a root logical Assembly')
    if type(cross_entity_frame_grants) is not tuple:
        raise TypeError('cross-entity frame grants require an immutable tuple')
    if cross_entity_frame_grants:
        from ...artifacts.fixed_attachment import FixedAttachmentPlanV1
        if (type(feedback_attachment) is not FixedAttachmentPlanV1
                or type(feedback_attachment_scene) is not SceneDefinition
                or assembly_identity is None):
            raise ValueError('cross-entity frame feedback requires its exact source Attachment and Assembly')
        feedback_attachment.validate()
        if (feedback_attachment.scene_pin.scene_identity_sha256 != feedback_attachment_scene.identity_hash
                or not {feedback_attachment.parent_entity_id, feedback_attachment.child_entity_id} <= assembly_entities):
            raise ValueError('cross-entity frame feedback Attachment is foreign')
    elif feedback_attachment is not None or feedback_attachment_scene is not None:
        raise ValueError('feedback Attachment requires explicit cross-entity frame grants')
    groups_by_key = {
        (group.entity_id, group.group_id): group
        for group in (scene.control_groups or ())
    }
    if not groups_by_key:
        raise ValueError('Controller binding requires at least one declared ControlGroup')
    if len({binding.writer_id for binding in controller_bindings}) != len(controller_bindings):
        raise ValueError('one Controller writer must be represented by one complete binding')

    bound_groups = {}
    resource_writers = {}
    controller_entities = {}
    for binding in controller_bindings:
        if not isinstance(binding, ControllerBindingV1):
            raise TypeError('Controller binding plan contains an unsupported binding value')
        if binding.action_schema.schema_version != 'task-env-action-v2':
            raise ValueError('Controller binding requires the current ActionModeSpec contract')
        entity_ids = {group.entity_id for group in binding.groups}
        if len(entity_ids) != 1 and (assembly_identity is None or not entity_ids <= assembly_entities):
            raise ValueError('multi-entity Controller requires ownership by its resolved logical Assembly')
        controller_entities[binding.writer_id] = tuple(sorted(entity_ids))
        action_components = []
        for projection in binding.groups:
            key = projection.key
            group = groups_by_key.get(key)
            if group is None:
                raise ValueError(f'Controller binding references unknown ControlGroup: {key}')
            if key in bound_groups:
                raise ValueError(f'ControlGroup has overlapping Controller writers: {key}')
            bound_groups[key] = binding.writer_id
            unknown_components = set(projection.action_components) - set(binding.action_schema.components)
            if unknown_components:
                raise ValueError(f'ControlGroup action schema references unknown components: {sorted(unknown_components)}')
            action_components.extend(projection.action_components)
            for resource in group.actuator_refs:
                scene.resolve_actuator(resource)
                resource_key = (resource.entity_id, resource.actuator_id)
                if resource_key in resource_writers:
                    raise ValueError(f'actuator resource has overlapping Controller writers: {resource_key}')
                resource_writers[resource_key] = binding.writer_id
        if len(action_components) != len(set(action_components)):
            raise ValueError(f'Controller action components have overlapping group writers: {binding.writer_id}')
        if set(action_components) != set(binding.action_schema.components):
            raise ValueError(f'ControlGroups must partition the complete action schema: {binding.writer_id}')
        grants = tuple(row for row in cross_entity_frame_grants if row[0] == binding.writer_id)
        if grants and (entity_ids != {feedback_attachment.parent_entity_id}
                       or any(entity != feedback_attachment.child_entity_id for _, entity, _ in grants)):
            raise ValueError('cross-entity frame grant is outside the declared parent/child Attachment')
        declared_grants = {(binding.writer_id, item.entity_id, item.subject_id)
            for item in binding.feedback_requirements.requirements
            if item.subject_kind == 'frame' and item.entity_id not in entity_ids}
        if grants and set(grants) != declared_grants:
            raise ValueError('cross-entity frame grants must exactly match declared feedback')
        _validate_feedback_requirements(scene, binding, entity_ids, frame_grants=grants)

    if {row[0] for row in cross_entity_frame_grants} - {binding.writer_id for binding in controller_bindings}:
        raise ValueError('cross-entity frame grant names an unknown writer')

    missing_groups = set(groups_by_key) - set(bound_groups)
    extra_groups = set(bound_groups) - set(groups_by_key)
    if missing_groups or extra_groups:
        raise ValueError(
            f'ControlGroup binding coverage mismatch: missing={sorted(missing_groups)}, extra={sorted(extra_groups)}'
        )
    declared_resources = {
        (resource.entity_id, resource.actuator_id)
        for resource in (scene.actuator_resources or ())
    }
    if set(resource_writers) != declared_resources:
        raise ValueError('every declared actuator resource requires exactly one bound Controller writer')
    plan = ControlBindingPlanV1(
        'control-binding-plan-v1', scene.identity_hash, controller_bindings,
        tuple((entity_id, actuator_id, writer_id)
              for (entity_id, actuator_id), writer_id in resource_writers.items()),
        artifact_identity_hash, source_closure_digest, assembly_identity,
        cross_entity_frame_grants,
        None if feedback_attachment is None else feedback_attachment.identity_hash,
    )
    object.__setattr__(plan, '_compiled', True)
    return plan


def project_controller_feedback(plan):
    """Return the feedback actually declared by a Scene-compiled writer plan."""
    if type(plan) is not ControlBindingPlanV1 or not plan._compiled:
        raise ValueError('feedback projection requires a compiled ControllerBindingPlanV1')
    return tuple((binding.writer_id, requirement)
                 for binding in plan.controller_bindings
                 for requirement in binding.feedback_requirements.requirements)


def project_leaf_feedback(scene, root, children, plan):
    """Project a compiled leaf plan through the existing logical resolver."""
    from ...artifacts.logical_assembly_resolution import resolve_logical_assembly
    from ...controllers.canonical.leaf_plan import EffectiveLeafPlanV1
    if type(plan) is not EffectiveLeafPlanV1 or not plan._compiled:
        raise ValueError('leaf feedback projection requires a compiled EffectiveLeafPlanV1')
    resolved = resolve_logical_assembly(root, scene, children)
    if (resolved.root_logical_content_sha256 != plan.root_logical_content_sha256
            or resolved.scene_identity_sha256 != plan.scene_identity_sha256):
        raise ValueError('leaf plan does not match the resolved logical Assembly and Scene')
    paths = {leaf.full_path for leaf in resolved.leaves}
    if any(entry.binding.member_path not in paths for entry in plan.leaves):
        raise ValueError('leaf plan refers to an unresolved logical Assembly member')
    return tuple((entry.binding.writer_id, requirement)
                 for entry in plan.leaves
                 for requirement in entry.binding.required_state.state_requirements.requirements)


def _validate_feedback_requirements(scene, binding, entity_ids, *, frame_grants=()):
    joints = {
        (articulation.entity_id, joint.joint_id)
        for articulation in (scene.articulations or ())
        for joint in articulation.joints
        if joint.kind != 'fixed'
    }
    frames = {(frame.entity_id, frame.frame_id) for frame in (scene.frames or ())}
    actuators = {
        (actuator.entity_id, actuator.actuator_id)
        for actuator in (scene.actuator_resources or ())
    }
    entities = {entity.entity_id for entity in scene.entities}
    for requirement in binding.feedback_requirements.requirements:
        key = (requirement.entity_id, requirement.subject_id)
        if requirement.entity_id not in entity_ids and not (
                requirement.subject_kind == 'frame'
                and (binding.writer_id, requirement.entity_id, requirement.subject_id) in frame_grants):
            raise ValueError('Controller feedback requirement crosses its bound Entity')
        missing = ((requirement.subject_kind == 'joint' and key not in joints)
                   or (requirement.subject_kind == 'frame' and key not in frames)
                   or (requirement.subject_kind == 'actuator' and key not in actuators)
                   or (requirement.subject_kind == 'entity' and
                       (requirement.entity_id not in entities or requirement.subject_id not in entities)))
        if missing and requirement.requiredness == 'required':
            label = {'joint': 'Joint', 'frame': 'Frame', 'actuator': 'actuator resource', 'entity': 'Entity'}[requirement.subject_kind]
            raise ValueError(f'Controller feedback references unknown {label}: {key}')



def single_position_action_request(action, *, scene, plan, profile):
    """Project one eight-component pose/gripper action onto its bound groups."""
    import numpy as np
    from ...controllers.canonical.contracts import ControlGroupActionV1, StructuredActionRequestV1

    vector = np.asarray(action, dtype=float)
    if vector.shape != (8,) or not np.isfinite(vector).all():
        raise ValueError('Position expert requires a finite eight-dimensional planned action')
    schema_id = profile.controller_binding().action_schema.schema_id
    request = StructuredActionRequestV1(
        'structured-action-request-v1', scene.identity_hash, plan.identity_hash,
        (ControlGroupActionV1('control-group-action-v1', profile.entity_id, 'arm', schema_id,
                              tuple(float(value) for value in vector[:7])),
         ControlGroupActionV1('control-group-action-v1', profile.entity_id, 'gripper', schema_id,
                              (float(vector[7]),))),
    )
    request.validate()
    return request


def prepare_structured_action(
    plan: ControlBindingPlanV1,
    request: StructuredActionRequestV1,
) -> tuple[tuple[str, RequestedAction], ...]:
    """Validate the entire request before yielding any Controller input or side effect."""
    if not isinstance(plan, ControlBindingPlanV1) or not isinstance(request, StructuredActionRequestV1):
        raise TypeError('structured action preparation requires a binding plan and typed request')
    if not plan._compiled:
        raise ValueError('structured action requires a Scene-validated ControlBindingPlan')
    if request.scene_identity_hash != plan.scene_identity_hash:
        raise ValueError('structured action Scene identity mismatch')
    if request.binding_identity_hash != plan.identity_hash:
        raise ValueError('structured action binding identity mismatch')
    projections = {
        projection.key: (binding, projection)
        for binding in plan.controller_bindings
        for projection in binding.groups
    }
    actions = {(group.entity_id, group.group_id): group for group in request.groups}
    if set(actions) != set(projections):
        raise ValueError(
            f'complete action must provide every bound ControlGroup exactly once: '
            f'missing={sorted(set(projections)-set(actions))}, extra={sorted(set(actions)-set(projections))}'
        )

    prepared = []
    for binding in plan.controller_bindings:
        values_by_component = {}
        for projection in binding.groups:
            action = actions[projection.key]
            if action.action_schema_id != binding.action_schema.schema_id:
                raise ValueError(f'action schema identity mismatch for ControlGroup: {projection.key}')
            if len(action.values) != len(projection.action_components):
                raise ValueError(f'action dimension mismatch for ControlGroup: {projection.key}')
            if any(not math.isfinite(value) for value in action.values):
                raise ValueError(f'nonfinite action value for ControlGroup: {projection.key}')
            values_by_component.update(zip(projection.action_components, action.values, strict=True))
        schema = binding.action_schema
        values = tuple(values_by_component[name] for name in schema.components)
        _validate_rotation(schema, values)
        requested = RequestedAction(
            schema.controller_kind,
            schema.reference,
            schema.rotation_representation or 'none',
            values,
        )
        prepared.append((binding.writer_id, requested))
    return tuple(prepared)


def _validate_rotation(schema, values):
    if schema.rotation_representation != 'quaternion_wxyz':
        return
    names = {
        'absolute_pose': ('qw', 'qx', 'qy', 'qz'),
        'delta_pose': ('dqw', 'dqx', 'dqy', 'dqz'),
    }.get(schema.controller_kind)
    if names is None:
        raise ValueError('quaternion action schema has no supported rotation component mapping')
    rotation = [values[schema.components.index(name)] for name in names]
    if not math.isfinite(math.sqrt(sum(value * value for value in rotation))) or math.sqrt(sum(value * value for value in rotation)) < 1.0e-8:
        raise ValueError('structured action quaternion must have positive finite norm')


@dataclass(frozen=True)
class ControlBinding:
    gripper_semantic_id: str
    opening_range_m: float

    def __post_init__(self):
        from ...artifacts.contracts import _name
        _name(self.gripper_semantic_id)
        if self.opening_range_m!=.08:raise ValueError('only audited 0.08m tendon gripper mapping implemented')

    def selected_runtime_builder(self, _selected):
        from .selected_materialization import ScalarRuntimeBuilder
        return ScalarRuntimeBuilder(self)


def prepare_position_control_materialization(
    *, source, artifact, profiles, leaf_position, plan, select_binding, value,
    capabilities=None,
):
    """Prepare the task's Position bindings before a provider is materialized."""
    from .source import position_frame_bindings_from_artifact, position_joint_bindings_from_artifact

    scene = source.scene_definition
    if leaf_position:
        if plan is not None:
            raise ValueError('leaf route cannot carry a legacy ControllerBindingPlan')
    else:
        if capabilities is not None and (len(capabilities) != len(profiles)
                or any(type(capability) is not SelectedPositionCapabilityV1
                       or capability.owner is not profile
                       for capability, profile in zip(capabilities, profiles, strict=True))):
            raise ValueError('Position construction capabilities differ from their selected Controllers')
        owners = profiles if capabilities is None else capabilities
        if plan is None:
            plan = compile_control_binding_plan(
                scene, tuple(owner.controller_binding() for owner in owners),
            )
        if not isinstance(plan, ControlBindingPlanV1):
            raise TypeError('PositionServoV1 selected route requires ControlBindingPlanV1')
        for owner in owners:
            if capabilities is None:
                owner._validate_plan(plan)
            else:
                owner.validate_plan(plan)
    joint_bindings = position_joint_bindings_from_artifact(scene, artifact, source)
    frame_bindings = position_frame_bindings_from_artifact(artifact, source)
    if not callable(select_binding):
        raise TypeError('Position control requires its declared ControlBinding selector')
    binding = select_binding(value)
    if type(binding) is not ControlBinding:
        raise TypeError('Position control selector must return an exact ControlBinding')
    return plan, joint_bindings, frame_bindings, binding


_C02B_R1_GEO_PHYS_REVISION = '67da1165149486d3ae3e779c13ce31af49e17d50'
_C02B_R1_ARTIFACT_IDENTITY = '97e0f33d06bc58831a946e3a0cdf277f3f52efe5b2bcf801192a965631c90efd'
_C02B_R1_SCENE_IDENTITY = '047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e'
_C02B_R1_SOURCE_CLOSURE = 'aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47'
_C02B_R1_CONTROLLER_IDENTITY = 'aa97e909925b397968ad1c45716ce6e3f22902d5e676d2a18a1f27b86a814c76'
_C02B_R1_KINEMATICS_IDENTITY = '6ce5254cd92efaffbf52d72881d96a1ea6a35da0b27aefd0c4ac89f181ca5d14'
_C02B_R1_PLAN_IDENTITY = 'b4838ab8c954f462066cdb07356e5a90ad3f9c521c9f9b53ce9c933ac2828c80'
_C02B_R1_SOURCE_XML_SHA256 = '2521356a6c925e8756e8d5309d68532aabce497654a7bd410cabac8533312aa3'
_C02B_R1_TCP_IDENTITY = 'b27be18d500ddaa548f7a588d61a3756ae7663679ca66b3272aa268183461ff8'
_C02B_R1_TASK_ID = 'phase-ii-c02b-r1-typed-force'
_C02B_R1_MUJOCO_PACKAGE_VERSION = '3.8.1'
_C02B_R1_MUJOCO_RUNTIME_VERSION = '3.8.1'
_C02B_R1_MUJOCO_PYTHON_ORIGIN_SHA256 = 'f8e5b528617004b6215e16cb0c945faf1f8c7b5d798e5b92e3aabce19c838497'
_C02B_R1_MUJOCO_BINDING_SHA256 = '9067239d3126392729430d12d077ab4b298c61d2ea1209c9333823be410359e3'
_C02B_R1_MUJOCO_CORE_SHA256 = '8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592'


def _mujoco_r1_build_identity():
    """Return the installed Python package and native MuJoCo build identity."""
    from importlib.util import find_spec
    from pathlib import Path
    import hashlib
    import mujoco

    build = dict(provider_build_identity('mujoco'))
    runtime_version = str(mujoco.mj_versionString())
    package_root = Path(mujoco.__file__).resolve().parent
    binding_spec = find_spec('mujoco._functions')
    binding_path = None if binding_spec is None or binding_spec.origin is None else Path(binding_spec.origin).resolve()
    core_candidates = tuple(
        path.resolve() for path in package_root.glob('libmujoco.*')
        if path.is_file() and runtime_version in path.name
    )
    if binding_path is not None and binding_path.is_file():
        build['native_binding_origin'] = str(binding_path)
        build['native_binding_sha256'] = hashlib.sha256(binding_path.read_bytes()).hexdigest()
    if len(core_candidates) == 1:
        core_path = core_candidates[0]
        build['native_core_origin'] = str(core_path)
        build['native_core_sha256'] = hashlib.sha256(core_path.read_bytes()).hexdigest()
    else:
        build['native_core_origin'] = None
        build['native_core_sha256'] = None
    return build, runtime_version


def _c02b_r1_force_capability_manifest(artifact, execution, source, plan, controller, binding):
    """Build exact admission evidence for one audited Provider/source/Controller tuple."""
    from ...controllers.canonical.production import ProductionCanonicalPandaController
    from ...artifacts import TaskArtifactV1
    import hashlib

    if type(controller) is not ProductionCanonicalPandaController:
        raise CapabilityAdmissionError('actuator_force_query requires the actual bounded R1 Controller instance')
    if execution.backend != 'cpu':
        raise CapabilityAdmissionError('typed R1 actuator force is limited to audited CPU Providers')
    if (execution.render_provider != 'none' or execution.physics_profile != PROFILE
            or execution.determinism_mode != 'strict'):
        raise CapabilityAdmissionError('typed R1 actuator force execution profile is unsupported')
    provider = execution.physics_provider
    if provider == 'geophys':
        build = provider_build_identity('geophys')
        runtime_version = None
        if (build.get('repository_revision') != _C02B_R1_GEO_PHYS_REVISION
                or build.get('dirty_build_sha256') is not None):
            raise CapabilityAdmissionError(
                'typed R1 actuator force requires clean GeoPhys repair commit '
                f'{_C02B_R1_GEO_PHYS_REVISION}'
            )
        provider_evidence = f'geophys=git:{_C02B_R1_GEO_PHYS_REVISION}'
    elif provider == 'mujoco':
        build, runtime_version = _mujoco_r1_build_identity()
        if (build.get('package_version') != _C02B_R1_MUJOCO_PACKAGE_VERSION
                or runtime_version != _C02B_R1_MUJOCO_RUNTIME_VERSION
                or build.get('origin_sha256') != _C02B_R1_MUJOCO_PYTHON_ORIGIN_SHA256
                or build.get('native_binding_sha256') != _C02B_R1_MUJOCO_BINDING_SHA256
                or build.get('native_core_sha256') != _C02B_R1_MUJOCO_CORE_SHA256):
            raise CapabilityAdmissionError(
                'typed R1 actuator force requires the audited MuJoCo Python/native build '
                f'{_C02B_R1_MUJOCO_PACKAGE_VERSION}'
            )
        provider_evidence = (
            f'mujoco=package:{build["package_version"]}/runtime:{runtime_version}/'
            f'python_origin_sha256:{build["origin_sha256"]}/'
            f'native_binding_sha256:{build["native_binding_sha256"]}/'
            f'native_core_sha256:{build["native_core_sha256"]}'
        )
    else:
        raise CapabilityAdmissionError(
            'typed R1 actuator force is limited to the audited GeoPhys and MuJoCo CPU intersections'
        )
    scene = getattr(source, 'scene_definition', None)
    if not isinstance(scene, SceneDefinition) or scene.identity_hash != _C02B_R1_SCENE_IDENTITY:
        raise CapabilityAdmissionError('typed R1 actuator force Scene identity is outside the audited candidate')
    if not isinstance(artifact, TaskArtifactV1) or (
        artifact.task_id != _C02B_R1_TASK_ID
        or artifact.artifact_version != 'candidate-v1'
        or artifact.identity_hash != _C02B_R1_ARTIFACT_IDENTITY
    ):
        raise CapabilityAdmissionError('typed R1 actuator force requires the exact versioned candidate Artifact')
    if (source.task_artifact_hash != artifact.identity_hash
            or artifact.scene_identity_hash != scene.identity_hash
            or source.scene_source.source_id != f'{scene.schema_version}:{scene.identity_hash}'
            or source.source_closure_digest != _C02B_R1_SOURCE_CLOSURE
            or hashlib.sha256(source.scene_source.xml.encode('utf-8')).hexdigest()
                != _C02B_R1_SOURCE_XML_SHA256):
        raise CapabilityAdmissionError('typed R1 actuator force source/materialization identity mismatch')
    if (artifact.timebase.physics_dt != 0.002 or artifact.timebase.control_substeps != 5
            or artifact.timebase.control_dt != 0.01
            or source.config.runtime.backend != 'cpu'
            or source.config.runtime.physics_dt != 0.002
            or source.config.runtime.control_substeps != 5):
        raise CapabilityAdmissionError('typed R1 actuator force requires the audited 100 Hz / 5x2 ms candidate')
    expected_targets = {
        f'panda-main/joint{index}': f'actuator{index}' for index in range(1, 8)
    }
    if (dict(source.joint_targets) != expected_targets
            or tuple(source.open_actuators) != ('actuator8',)
            or controller.gripper_semantic_id != 'panda-main/gripper'
            or binding.gripper_semantic_id != 'panda-main/gripper'
            or binding.opening_range_m != 0.08):
        raise CapabilityAdmissionError('typed R1 actuator/joint/gripper binding is outside the audited mapping')
    kinematics_identity = controller.source_kinematics_identity
    if (controller.identity != _C02B_R1_CONTROLLER_IDENTITY
            or controller.source_artifact_hash != artifact.identity_hash
            or controller.source_xml_sha256 != _C02B_R1_SOURCE_XML_SHA256
            or controller.tcp_profile_identity != _C02B_R1_TCP_IDENTITY
            or kinematics_identity != _C02B_R1_KINEMATICS_IDENTITY):
        raise CapabilityAdmissionError('actual R1 Controller or hand-origin TCP differs from the bound candidate')
    if (plan.identity_hash != _C02B_R1_PLAN_IDENTITY
            or plan.scene_identity_hash != scene.identity_hash
            or plan.artifact_identity_hash != artifact.identity_hash
            or plan.source_closure_digest != source.source_closure_digest
            or len(plan.controller_bindings) != 1):
        raise CapabilityAdmissionError('ControlBindingPlan is not the exact R1 candidate plan')
    controller_binding = plan.controller_bindings[0]
    if (controller_binding.writer_id != 'panda-main/production-r1'
            or controller_binding.controller_identity != controller.identity
            or controller_binding.controller_kinematics_identity != kinematics_identity
            or {group.key for group in controller_binding.groups} != {
                ('panda-main', 'arm'), ('panda-main', 'gripper'),
            }):
        raise CapabilityAdmissionError('ControlBindingPlan does not identify the actual R1 Controller instance')
    force_requirements = tuple(
        item for item in controller_binding.feedback_requirements.requirements
        if item.field_name == 'actuator_force' and item.requiredness == 'required'
    )
    if len(force_requirements) != 1 or (
        force_requirements[0].entity_id, force_requirements[0].subject_id,
        force_requirements[0].unit, force_requirements[0].sample_domain,
    ) != ('panda-main', 'actuator8', 'N', 'evaluation_boundary'):
        raise CapabilityAdmissionError('R1 Controller must require raw N force for panda-main/actuator8')
    generic = provider_manifest(provider)
    evidence = (
        'C02b-R1-typed-force-v1/'
        f'artifact={artifact.identity_hash}/scene={scene.identity_hash}/'
        f'source={source.source_closure_digest}/controller={controller.identity}/plan={plan.identity_hash}/'
        f'{provider_evidence}'
    )
    claim = CapabilityClaim('actuator_force_query', 'tested', evidence)
    return ProviderCapabilityManifest(
        'provider-capability-v0', provider, build['manifest_version'],
        'task-env-c02b-r1-typed-force-v1', 'cpu', PROFILE, 'none', 'strict',
        tuple(generic.capabilities) + (claim,), generic.known_unsupported, evidence,
    )


def materialize_control(
    artifact,
    execution,
    *,
    source,
    binding,
    manifest=None,
    controller_binding_plan: ControlBindingPlanV1 | None = None,
    controller_profile=None,
    leaf_plan=None,
    diagnostic_profile=None,
    session_admission_input=None,
    native_feedback_profile=None,
    selected_controller=None,
    native_feedback_gripper_control_hz=None,
    observer_render_request=None,
    task_render_requested=False,
):
    from ...artifacts import ExecutionSpecV1
    from ...artifacts.execution import legacy_execution_projection

    declared_execution = execution
    from .api import (
        _current_f05_dg04_s1_native_io_context,
        _session_admission_input_route,
    )
    f05_dg04_s1_scope = _current_f05_dg04_s1_native_io_context()
    f04_native = False
    admission_route = _session_admission_input_route(session_admission_input)
    f05_native_input = session_admission_input if admission_route == 'f05_native' else None
    f05_dg02_geophys_input = session_admission_input if admission_route == 'f05_dg02' else None
    f05_dg04_isaac_native_input = session_admission_input if admission_route == 'f05_dg04' else None
    f06_pickcube_isaac_input = session_admission_input if admission_route == 'f06_pickcube' else None
    f05_native = admission_route == 'f05_native'
    f05_dg02_native = admission_route == 'f05_dg02'
    f05_dg04_native = admission_route == 'f05_dg04'
    f06_pickcube_isaac = admission_route == 'f06_pickcube'
    if native_feedback_profile is not None and admission_route is not None:
        raise ValueError('R05b native feedback admission cannot combine with an exact F task input')
    if f05_native:
        from .api import F05_GEOPHYS_NATIVE_POSITION_PROFILE, _validate_f05_geophys_native_position_input
        from ...artifacts import ExecutionSpec, ProviderCapabilityManifest, CapabilityClaim

        _validate_f05_geophys_native_position_input(
            f05_native_input, artifact, declared_execution, source,
        )
        if (manifest is not None or diagnostic_profile is not None or leaf_plan is not None
                or type(declared_execution) is not ExecutionSpecV1):
            raise ValueError('F05 native exact-cell admission cannot combine with caller manifests or diagnostics')
        if declared_execution.physics_profile != F05_GEOPHYS_NATIVE_POSITION_PROFILE:
            raise ValueError('F05 native input requires its exact GeoPhys execution profile')
        execution = ExecutionSpec(
            'geophys', F05_GEOPHYS_NATIVE_POSITION_PROFILE, 'none', 'cpu',
            declared_execution.provider_seed, 'best_effort',
        )
        f05_capabilities = sorted(set(CONTROL_REQUIRED.names) | set(artifact.required_capabilities.names))
        actual_manifest = ProviderCapabilityManifest(
            'provider-capability-v0', 'geophys',
            f05_native_input.host_model_producer_identity.actual_provider_build_identity,
            'f05-menagerie-geophys-cpu-position-native-v1', 'cpu',
            F05_GEOPHYS_NATIVE_POSITION_PROFILE, 'none', 'best_effort',
            tuple(CapabilityClaim(capability, 'tested', 'f05-exact-menagerie-cpu-cell')
                  for capability in f05_capabilities),
            ('rgb_camera', 'depth_camera', 'contact_detection', 'contact_impulse'),
            'bounded F05 Menagerie GeoPhys CPU cell; no provider-wide qualification',
        )
    elif f05_dg02_native:
        from .api import F05_DG02_GEOPHYS_USD_PROFILE, _validate_f05_dg02_geophys_usd_input
        from ...artifacts import ExecutionSpec, ProviderCapabilityManifest, CapabilityClaim

        _validate_f05_dg02_geophys_usd_input(
            f05_dg02_geophys_input, artifact, declared_execution, source,
        )
        if (manifest is not None or diagnostic_profile is not None or leaf_plan is not None
                or type(declared_execution) is not ExecutionSpecV1):
            raise ValueError('DG02 exact-cell admission cannot combine with caller manifests or diagnostics')
        if declared_execution.physics_profile != F05_DG02_GEOPHYS_USD_PROFILE:
            raise ValueError('DG02 input requires its exact GeoPhys/USD execution profile')
        execution = ExecutionSpec(
            'geophys', F05_DG02_GEOPHYS_USD_PROFILE, 'none', 'cpu',
            declared_execution.provider_seed, 'best_effort',
        )
        dg02_capabilities = sorted(set(CONTROL_REQUIRED.names) | set(artifact.required_capabilities.names))
        actual_manifest = ProviderCapabilityManifest(
            'provider-capability-v0', 'geophys',
            f05_dg02_geophys_input.host_model_producer_identity.actual_provider_build_identity,
            'f05-dg02-source-preserving-usd-core-native-v1', 'cpu',
            F05_DG02_GEOPHYS_USD_PROFILE, 'none', 'best_effort',
            tuple(CapabilityClaim(capability, 'tested', 'f05-dg02-exact-source-bound-core-cell')
                  for capability in dg02_capabilities),
            ('rgb_camera', 'depth_camera', 'contact_detection', 'contact_impulse'),
            'bounded DG02 source-preserving USD/Core CPU cell; no provider-wide qualification',
        )
    elif f05_dg04_native:
        from .api import (
            F05_DG04_ISAAC_NATIVE_PROFILE, _f05_dg04_isaac_capability_manifest,
            _validate_f05_dg04_isaac_native_input,
        )
        from ...artifacts import ExecutionSpec

        _validate_f05_dg04_isaac_native_input(
            f05_dg04_isaac_native_input, artifact, declared_execution, source,
        )
        if (type(declared_execution) is not ExecutionSpecV1
                or manifest is not None or diagnostic_profile is not None or leaf_plan is not None
                or declared_execution.physics_profile != F05_DG04_ISAAC_NATIVE_PROFILE):
            raise ValueError('DG04 exact-cell admission requires its exact input without alternate authorities')
        execution = ExecutionSpec(
            'isaacsim', F05_DG04_ISAAC_NATIVE_PROFILE, 'none', 'cuda',
            declared_execution.provider_seed, 'best_effort',
        )
        actual_manifest = _f05_dg04_isaac_capability_manifest(
            artifact, synthetic_s1=f05_dg04_s1_scope is not None,
        )
    elif f06_pickcube_isaac:
        from .api import (
            F06_PICKCUBE_ISAAC_PROFILE, _f06_pickcube_isaac_capability_manifest,
            _validate_f06_pickcube_isaac_input,
        )
        from ...artifacts import ExecutionSpec

        _validate_f06_pickcube_isaac_input(
            f06_pickcube_isaac_input, artifact, declared_execution, source,
        )
        if (type(declared_execution) is not ExecutionSpecV1
                or manifest is not None or diagnostic_profile is not None or leaf_plan is not None
                or declared_execution.physics_profile != F06_PICKCUBE_ISAAC_PROFILE):
            raise ValueError('F06 exact-cell admission requires its exact input without alternate authorities')
        execution = ExecutionSpec(
            'isaacsim', F06_PICKCUBE_ISAAC_PROFILE, 'none', 'cuda',
            declared_execution.provider_seed, 'best_effort',
        )
        actual_manifest = _f06_pickcube_isaac_capability_manifest(artifact)
    elif (type(declared_execution) is ExecutionSpecV1
          and getattr(declared_execution, 'physics_provider', None) == 'isaacsim'):
        from .api import F04_ISAAC_POSITION_PROFILE, _validate_f04_isaac_position_source
        from ...artifacts import ExecutionSpec, ProviderCapabilityManifest, CapabilityClaim

        _validate_f04_isaac_position_source(artifact, declared_execution, source)
        if manifest is not None or diagnostic_profile is not None or leaf_plan is not None:
            raise ValueError('F04 Isaac control admission cannot combine with other admission authorities')
        execution = ExecutionSpec(
            declared_execution.physics_provider, declared_execution.physics_profile,
            'none', declared_execution.physics_backend,
            declared_execution.provider_seed, declared_execution.determinism_mode,
        )
        # The F04 local Panda cell also owns the delivered free cube.  The
        # source-bound admission below is authoritative for that requirement;
        # include it in the exact-cell manifest instead of making the manifest
        # weaker than the RuntimeSource it is about to admit.
        f04_capabilities = sorted(
            set(CONTROL_REQUIRED.names)
            | set(artifact.required_capabilities.names)
            | set(declared_source_capabilities(source).names)
        )
        actual_manifest = ProviderCapabilityManifest(
            'provider-capability-v0', 'isaacsim', '6.2.0.0',
            'f04-isaac-panda-native-runtime-io-v1', 'cuda',
            F04_ISAAC_POSITION_PROFILE, 'none', 'best_effort',
            tuple(CapabilityClaim(capability, 'implemented', 'f04-exact-panda-profile')
                  for capability in f04_capabilities),
            ('rgb_camera', 'depth_camera', 'contact_detection', 'contact_impulse'),
            'bounded F04 Panda Position adapter; no provider-wide qualification',
        )
        f04_native = True
    else:
        execution = legacy_execution_projection(execution)
    if leaf_plan is not None:
        from ...controllers.canonical.leaf_plan import EffectiveLeafPlanV1
        from .provenance import provider_build_identity
        if (type(leaf_plan) is not EffectiveLeafPlanV1 or leaf_plan._compiled is not True
                or controller_binding_plan is not None or controller_profile is not None
                or diagnostic_profile is not None):
            raise TypeError('R02c leaf materialization requires one compiled plan without legacy Controllers')
        if (execution.physics_provider, execution.backend, execution.render_provider) != ('mujoco', 'cpu', 'none'):
            raise ValueError('R02c leaf materialization is limited to MuJoCo CPU with no renderer')
        scene = getattr(source, 'scene_definition', None)
        if (scene is None or scene.identity_hash != leaf_plan.scene_identity_sha256
                or source.source_closure_digest != leaf_plan.source_closure_sha256
                or source.task_artifact_hash != artifact.identity_hash):
            raise ValueError('R02c leaf plan does not match the exact Artifact/Scene/source closure')
        build_info = provider_build_identity('mujoco')
        build_sha = __import__('hashlib').sha256(
            __import__('json').dumps(build_info, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()
        ).hexdigest()
        if (leaf_plan.provider_name, leaf_plan.provider_version, leaf_plan.provider_build_sha256,
                leaf_plan.backend, leaf_plan.physics_dt_s, leaf_plan.control_substeps) != (
                'mujoco', str(build_info['package_version']), build_sha, 'cpu',
                artifact.timebase.physics_dt, artifact.timebase.control_substeps):
            raise ValueError('R02c leaf plan Provider/build/backend/timebase identity mismatch')
        attachment_plan = getattr(source, 'fixed_attachment_plan', None)
        if leaf_plan.fixed_attachment_plan_identity_sha256 is not None:
            if (attachment_plan is None
                    or attachment_plan.identity_hash != leaf_plan.fixed_attachment_plan_identity_sha256):
                raise ValueError('attached leaf plan differs from the exact RuntimeSource Attachment plan')
            expected_targets = {
                f'{entry.binding.entity_id}/{ref.joint_id}': attachment_plan.native_actuator_names[
                    f'{entry.binding.entity_id}/{actuator.actuator_id}'
                ]
                for entry in leaf_plan.leaves if entry.binding.profile_kind == 'arm_position'
                for ref, actuator in zip(entry.binding.joint_order,
                                         tuple(pair.actuator for pair in entry.binding.joint_actuator_bindings),
                                         strict=True)
            }
            expected_open = tuple(
                attachment_plan.native_actuator_names[f'{entry.binding.entity_id}/{ref.actuator_id}']
                for entry in leaf_plan.leaves if entry.binding.profile_kind == 'hand_position'
                for ref in entry.binding.actuator_order
            )
        else:
            expected_targets = {f'{entry.binding.entity_id}/{ref.joint_id}': f'actuator{index}'
                                for entry in leaf_plan.leaves if entry.binding.profile_kind == 'arm_position'
                                for index, ref in enumerate(entry.binding.joint_order, 1)}
            expected_open = tuple(
                ref.actuator_id for entry in leaf_plan.leaves
                if entry.binding.profile_kind == 'hand_position' for ref in entry.binding.actuator_order
            )
        if dict(source.joint_targets) != expected_targets or tuple(source.open_actuators) != expected_open:
            raise ValueError('R02c RuntimeSource actuator names differ from ordered leaf bindings')
        if len(leaf_plan.leaves) != 2 or {entry.binding.profile_kind for entry in leaf_plan.leaves} != {
            'arm_position', 'hand_position',
        }:
            raise ValueError('R02c requires exactly one Arm and one Position Hand leaf')
    if diagnostic_profile is not None and native_feedback_profile is not None:
        raise ValueError('diagnostic and normal native-feedback admissions are mutually exclusive')
    if native_feedback_profile is not None:
        from ...controllers.canonical.production_r3 import ProductionCanonicalPandaControllerR3
        from ...controllers.canonical.execution import ReferenceExecutionController, StableArmTargetHold
        from ...controllers.canonical.gripper_execution import EqualRateGripperServo, NativeRateGripperServo
        from ...controllers.canonical.contracts import digest
        from .r05c_v211_candidate import PROFILE_ID as candidate_profile, CONTROLLER_IDENTITY as candidate_identity
        historical_controller_identity = {
            # Pin the post-refactor source-bound identities. The independent
            # field, source, provider and resource checks remain mandatory.
            100: '94c148b14915a0637bfaf572c101ba2980b93b43c88b0a3a9ccd39785a1d679d',
            500: '7cdf5c3c91ab3ec78dc3fa740fce1cbca7c229a0bf36b1d13c5da3a9c75cc4ec',
        }
        if native_feedback_profile == candidate_profile:
            if execution.physics_provider != 'geophys' or execution.backend != 'cpu':
                raise ValueError('v2.1.1 R05c diagnostic candidate requires GeoPhys CPU')
            expected_controller_identity = {100: candidate_identity}
        elif native_feedback_profile == 'nutassembly-native-feedback-v1':
            expected_controller_identity = historical_controller_identity
        else:
            raise ValueError('unknown normal native-feedback admission profile')
        expected_inner_type = {
            100: EqualRateGripperServo,
            500: NativeRateGripperServo,
        }
        actual_controller = getattr(getattr(selected_controller, 'hold', None), 'controller', None)
        if (type(native_feedback_gripper_control_hz) is not int
                or native_feedback_gripper_control_hz not in expected_controller_identity
                or type(selected_controller) is not ReferenceExecutionController
                or type(selected_controller.hold) is not StableArmTargetHold
                or type(actual_controller) is not ProductionCanonicalPandaControllerR3
                or selected_controller.gripper_rate_hz != native_feedback_gripper_control_hz
                or selected_controller.identity != expected_controller_identity[native_feedback_gripper_control_hz]
                or type(selected_controller.inner) is not expected_inner_type[native_feedback_gripper_control_hz]
                or selected_controller.inner.rate_hz != native_feedback_gripper_control_hz
                or selected_controller.inner.outer_dt_s != 0.01
                or selected_controller.inner.controller is not actual_controller
                or digest(asdict(actual_controller.config)) !=
                    '46e7a5aa81005a48f04f4183ff6a790a0b17716418de6b277404a234b5aa905b'
                or digest(asdict(actual_controller.gripper_config)) !=
                    '322155ae1e86c0410cbf3a096f92b1d2f243719f19f5310431c2ab83b1ad907d'
                or digest(actual_controller.physical_profile) !=
                    '0d3e4c367487eb156db3271eecdf051fda7b17e8568f5a7fdfb51ee33e576f7c'
                or (actual_controller.feedforward_gain, actual_controller.position_feedback_s,
                    actual_controller.rotation_feedback_s, actual_controller.joint_velocity_limit_rad_s,
                    actual_controller.reference_lead_limit_rad, actual_controller.inner_physics_dt_s,
                    actual_controller.dls_damping, actual_controller.rotation_row_weight) !=
                    (1.0, 4.0, 4.0, 2.0, 0.15, 0.002, 0.02, 0.22)
                or actual_controller.gripper_config.force_limit_N != 10.0):
            raise ValueError(
                'R05b normal profile requires the exact admitted R3 Controller, 10 N cap, '
                'and selected 100/500 Hz law'
            )
        if source.config.runtime.backend != execution.backend:
            raise ValueError('R05b selected Controller/source backend mismatch')
    if native_feedback_profile is not None:
        from .api import _r05b_native_feedback_manifest
        if manifest is not None:
            raise CapabilityAdmissionError('R05b native feedback admission does not accept a custom manifest')
        actual_manifest = _r05b_native_feedback_manifest(
            artifact, execution, source, native_feedback_profile,
        )
    elif diagnostic_profile is not None:
        from .api import _diagnostic_manifest
        if manifest is not None:
            raise CapabilityAdmissionError('diagnostic control admission does not accept a custom manifest')
        actual_manifest = _diagnostic_manifest(artifact, execution, source, diagnostic_profile)
    elif not (f04_native or f05_native or f05_dg02_native
              or f05_dg04_native or f06_pickcube_isaac):
        actual_manifest = provider_manifest(execution.physics_provider)
    source_requirements = declared_source_capabilities(source)
    if manifest is not None:
        admit_capabilities(source_requirements, manifest, execution)
    admit_capabilities(source_requirements, actual_manifest, execution)
    # DG02 materialize() admits the Core-generated, source-bound manifest
    # alongside its exact candidate input. Keep it on the same public path
    # after the controller-level capability check.
    admission_manifest = actual_manifest if (
        f05_dg02_native or f05_dg04_native or f06_pickcube_isaac
    ) else manifest
    profiles = ()
    r1_controller = None
    r1_manifest = None

    if controller_profile is not None:
        from ...controllers.canonical.position_profile import PandaPositionServoProfileV1
        from ...controllers.canonical.production import ProductionCanonicalPandaController

        if isinstance(controller_profile, PandaPositionServoProfileV1) or isinstance(
            controller_profile, (tuple, list),
        ):
            profiles = (
                (controller_profile,)
                if isinstance(controller_profile, PandaPositionServoProfileV1)
                else tuple(controller_profile)
            )
            if (not profiles or len(profiles) > 2
                    or any(not isinstance(profile, PandaPositionServoProfileV1) for profile in profiles)):
                raise TypeError('unsupported explicit Controller profile set')
            for profile in profiles:
                generation = getattr(profile, 'generation', None)
                if generation is not None and (type(generation) is not int or generation < 0):
                    raise ValueError('materialized Position Controller generation must be nonnegative')
            if (not f04_native and not f05_native
                    and not f05_dg04_native and not f06_pickcube_isaac
                    and (execution.physics_provider not in {'geophys', 'mujoco'}
                                or execution.backend != 'cpu')):
                raise ValueError('PositionServoV1 materialization is limited to GeoPhys/MuJoCo CPU')
            if controller_binding_plan is None:
                raise ValueError('PositionServoV1 requires a compiled ControlBindingPlanV1')
            if len({profile.writer_id for profile in profiles}) != len(profiles):
                raise ValueError('PositionServoV1 profile set contains duplicate writers')
            if len({profile.entity_id for profile in profiles}) != len(profiles):
                raise ValueError('PositionServoV1 profile set must bind distinct Entities')
            if len(profiles) == 2 and {profile.entity_id for profile in profiles} != {
                'panda-main', 'panda-secondary',
            }:
                raise ValueError('bounded dual Position admission requires panda-main and panda-secondary')
            if {item.writer_id for item in controller_binding_plan.controller_bindings} != {
                profile.writer_id for profile in profiles
            }:
                raise ValueError('PositionServoV1 profile writers must exactly cover the plan')
            expected_targets = {}
            expected_open = []
            for profile in profiles:
                profile._validate_plan(controller_binding_plan)
                if artifact.identity_hash != profile.artifact.identity_hash:
                    raise ValueError('PositionServoV1 materialization Artifact differs from a Controller instance')
                profile._validate_source(source)
                expected_targets.update(profile._target_bindings)
                expected_open.append(profile.open_actuator)
            if f04_native:
                if (len(profiles) != 1 or profiles[0].open_actuator is not None
                        or profiles[0].native_drive_receipt is not None
                        or set(source.joint_targets) != set(source.joints)
                        or len(set(source.joint_targets.values())) != 9):
                    raise ValueError('F04 Position requires one deferred native receipt and exact nine-name source bindings')
            elif f05_native:
                if (len(profiles) != 1 or profiles[0].open_actuator is not None
                        or profiles[0].native_drive_receipt is not None
                        or dict(source.joint_targets) != dict(source.joints)
                        or len(set(source.joint_targets.values())) != 9):
                    raise ValueError('F05 Position requires one deferred model-bound receipt and exact nine-name source bindings')
            elif f05_dg02_native:
                receipt = f05_dg02_geophys_input.native_drive_receipt
                expected_named_targets = {
                    f'{row.canonical_joint.entity_id}/{row.canonical_joint.joint_id}': row.native_dof_name
                    for row in receipt.drives
                }
                if (len(profiles) != 1 or profiles[0].open_actuator is not None
                        or profiles[0].native_drive_receipt is not receipt
                        or dict(source.joint_targets) != expected_named_targets):
                    raise ValueError('DG02 Position requires its exact nine-DOF/eight-actuator source receipt')
            elif f05_dg04_native:
                expected_joint_map = {
                    **{f'panda-main/joint{index}': f'joint{index}' for index in range(1, 8)},
                    'panda-main/finger_joint1': 'finger_joint1',
                    'panda-main/finger_joint2': 'finger_joint2',
                }
                if (len(profiles) != 1 or profiles[0].open_actuator is not None
                        or profiles[0].native_drive_receipt is not None
                        or dict(source.joints) != expected_joint_map
                        or dict(source.joint_targets) != expected_joint_map):
                    raise ValueError('DG04 Position requires its exact nine-joint source map and deferred native receipt')
            elif f06_pickcube_isaac:
                expected_joint_map = {
                    **{f'panda-v1/joint{index}': f'joint{index}' for index in range(1, 8)},
                    'panda-v1/finger_joint1': 'finger_joint1',
                    'panda-v1/finger_joint2': 'finger_joint2',
                }
                if (len(profiles) != 1 or profiles[0].open_actuator is not None
                        or profiles[0].native_drive_receipt is not None
                        or dict(source.joints) != expected_joint_map
                        or dict(source.joint_targets) != expected_joint_map):
                    raise ValueError('F06 Position requires its exact nine-joint source map and deferred native receipt')
            elif dict(source.joint_targets) != expected_targets or set(source.open_actuators) != set(expected_open):
                raise ValueError('PositionServoV1 source actuator mapping differs from its bound plan')
            if binding.gripper_semantic_id != profiles[0].gripper_semantic_id:
                raise ValueError('PositionServoV1 gripper semantic binding mismatch')
        elif type(controller_profile) is ProductionCanonicalPandaController:
            if controller_binding_plan is None or len(controller_binding_plan.controller_bindings) != 1:
                raise ValueError('bounded plan-bound R1 requires one compiled ControllerBinding')
            r1_controller = controller_profile
            r1_manifest = _c02b_r1_force_capability_manifest(
                artifact, execution, source, controller_binding_plan, r1_controller, binding,
            )
            if manifest is not None and manifest.identity_hash != r1_manifest.identity_hash:
                raise CapabilityAdmissionError(
                    'supplied manifest does not carry the exact R1 Provider/source provenance'
                )
            admission_manifest = r1_manifest
        else:
            raise TypeError('unsupported explicit Controller profile instance')
    elif leaf_plan is None and (len(source.joint_targets) != 7 or len(source.open_actuators) != 1):
        raise ValueError('unsupported control source bindings')

    if controller_binding_plan is not None:
        if not isinstance(controller_binding_plan, ControlBindingPlanV1) or not controller_binding_plan._compiled:
            raise ValueError('control materialization requires a Scene-validated ControllerBinding plan')
        scene = getattr(source, 'scene_definition', None)
        if not isinstance(scene, SceneDefinition) or scene.identity_hash != controller_binding_plan.scene_identity_hash:
            raise ValueError('ControllerBinding Scene identity does not match RuntimeSource')
        required_feedback = {
            requirement.required_capability
            for controller_binding in controller_binding_plan.controller_bindings
            for requirement in controller_binding.feedback_requirements.requirements
            if requirement.requiredness == 'required'
        }
        effective_manifest = admission_manifest or actual_manifest
        supported = {
            claim.name for claim in effective_manifest.capabilities
            if claim.status in SUPPORTED_STATUSES
        }
        if manifest is not None and r1_manifest is None:
            supported &= {
                claim.name for claim in manifest.capabilities
                if claim.status in SUPPORTED_STATUSES
            }
        missing = required_feedback - supported
        if missing:
            raise CapabilityAdmissionError(
                f'missing supported Controller feedback capabilities for '
                f'{execution.physics_provider}: {sorted(missing)}'
            )

    materialization_authority = None
    if len(profiles) == 2:
        from .api import _DUAL_POSITION_MATERIALIZATION_AUTHORITY
        materialization_authority = _DUAL_POSITION_MATERIALIZATION_AUTHORITY
    session = materialize(
        artifact, declared_execution, source=source,
        manifest=None if f04_native else admission_manifest,
        _materialization_authority=materialization_authority,
        _diagnostic_profile=diagnostic_profile,
        _session_admission_input=session_admission_input,
        _native_feedback_profile=native_feedback_profile,
        _observer_render_request=observer_render_request,
        _task_render_requested=task_render_requested,
    )
    if f04_native:
        try:
            receipt = getattr(session, '_drive_receipt', None)
            from .leaf_control import IsaacNamedPositionDriveReceiptV1
            io_provenance = getattr(
                getattr(session, '_native_io', None),
                'execution_provenance_kind', 'native_runtime',
            )
            expected_receipt_provenance = (
                'synthetic_fixture' if io_provenance == 'synthetic_fixture' else 'native_runtime'
            )
            if (type(receipt) is not IsaacNamedPositionDriveReceiptV1
                    or receipt.provenance_kind != expected_receipt_provenance
                    or dict(source.joint_targets) != {
                        f'{item.canonical_joint.entity_id}/{item.canonical_joint.joint_id}': item.native_dof_name
                        for item in receipt.drives
                    }):
                raise ValueError('F04 native receipt differs from the exact verified RuntimeSource target map')
        except BaseException as admission_error:
            try:
                session.close()
            except BaseException as cleanup_error:
                admission_error.add_note(
                    f'F04 RuntimeSession cleanup after receipt admission failure also failed: '
                    f'{type(cleanup_error).__name__}: {cleanup_error}'
                )
            try:
                session.close_runtime_owner()
            except BaseException as cleanup_error:
                admission_error.add_note(
                    f'F04 App owner cleanup after receipt admission failure also failed: '
                    f'{type(cleanup_error).__name__}: {cleanup_error}'
                )
            raise
    elif f05_native:
        try:
            from .leaf_control import (
                GeoPhysUsdPositionDriveReceiptV1,
                GeoPhysUsdSourceActuationReceiptV2,
            )
            receipt = getattr(session, '_drive_receipt', None)
            metadata = getattr(session, '_native_io_metadata', None)
            producer = f05_native_input.host_model_producer_identity
            supported_receipts = (GeoPhysUsdPositionDriveReceiptV1, GeoPhysUsdSourceActuationReceiptV2)
            expected_targets = {
                f'{item.canonical_joint.entity_id}/{item.canonical_joint.joint_id}': item.native_dof_name
                for item in receipt.drives
            } if type(receipt) in supported_receipts else {}
            if (type(receipt) not in supported_receipts
                    or receipt.provenance_kind != 'native_runtime'
                    or receipt.provider_build_identity != producer.actual_provider_build_identity
                    or receipt.host_model_producer_identity_sha256 != producer.identity_sha256
                    or metadata.host_model_producer_identity_sha256 != producer.identity_sha256
                    or metadata.provider_build_identity != producer.actual_provider_build_identity
                    or metadata.physics_provider != 'geophys'
                    or dict(source.joint_targets) != expected_targets):
                raise ValueError('F05 native receipt/metadata does not bind the actual GeoPhys producer and exact DOF targets')
        except BaseException as admission_error:
            try:
                session.close()
            except BaseException as cleanup_error:
                admission_error.add_note(
                    f'F05 native RuntimeSession cleanup after receipt admission failure also failed: '
                    f'{type(cleanup_error).__name__}: {cleanup_error}'
                )
            raise
    elif f05_dg02_native:
        try:
            from .leaf_control import GeoPhysUsdSourceActuationReceiptV2
            receipt = getattr(session, '_drive_receipt', None)
            metadata = getattr(session, '_native_io_metadata', None)
            producer = f05_dg02_geophys_input.host_model_producer_identity
            expected_targets = {
                f'{item.canonical_joint.entity_id}/{item.canonical_joint.joint_id}': item.native_dof_name
                for item in receipt.drives
            } if type(receipt) is GeoPhysUsdSourceActuationReceiptV2 else {}
            if (type(receipt) is not GeoPhysUsdSourceActuationReceiptV2
                    or receipt.provenance_kind != 'native_runtime'
                    or receipt.identity_sha256 != f05_dg02_geophys_input.native_drive_receipt.identity_sha256
                    or receipt.provider_build_identity != producer.actual_provider_build_identity
                    or receipt.host_model_producer_identity_sha256 != producer.identity_sha256
                    or metadata.host_model_producer_identity_sha256 != producer.identity_sha256
                    or metadata.provider_build_identity != producer.actual_provider_build_identity
                    or metadata.physics_provider != 'geophys'
                    or dict(source.joint_targets) != expected_targets):
                raise ValueError('DG02 native receipt/metadata does not bind the exact public model producer/DOF map')
        except BaseException as admission_error:
            try:
                session.close()
            except BaseException as cleanup_error:
                admission_error.add_note(
                    f'DG02 RuntimeSession cleanup after receipt admission failure also failed: '
                    f'{type(cleanup_error).__name__}: {cleanup_error}'
                )
            raise
    if (selected_controller is not None
            and getattr(source, 'position_subject_binding', None) is None):
        try:
            from .legacy_native_feedback_binding import install_admitted_binding
            install_admitted_binding(session, source=source, artifact=artifact,
                                     controller=selected_controller)
        except BaseException as admission_error:
            try:
                session.close()
            except BaseException as cleanup_error:
                admission_error.add_note(
                    f'legacy native feedback cleanup after binding failure also failed: {cleanup_error!r}'
                )
            raise
    session._control_binding = binding
    if controller_binding_plan is not None:
        force_required = any(
            item.field_name == 'actuator_force' and item.requiredness == 'required'
            for controller_binding in controller_binding_plan.controller_bindings
            for item in controller_binding.feedback_requirements.requirements
        )
        session._force_feedback_required = force_required
        session._control_binding_plan = controller_binding_plan
    elif leaf_plan is not None:
        session._force_feedback_required = False
        session._control_binding_plan = None
        try:
            session.admit_leaf_control_plan(leaf_plan)
        except BaseException as admission_error:
            try:
                session.close()
            except BaseException as cleanup_error:
                admission_error.add_note(
                    f"RuntimeSession cleanup after leaf admission failure also failed: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
            raise
    else:
        session._force_feedback_required = True
        session._control_binding_plan = None
    if r1_controller is not None:
        session._r1_force_admitted = True
        session._r1_controller_identity = r1_controller.identity
        session._r1_binding_identity_hash = controller_binding_plan.identity_hash
        session._r1_source_closure_digest = source.source_closure_digest
        session._r1_admitted_manifest = r1_manifest
        session._r1_applied_boundary_ids = set()
        session._r1_target_in_flight = None
    if profiles:
        session._position_profiles_by_writer = {profile.writer_id: profile for profile in profiles}
        session._position_profile_identities = {profile.writer_id: profile.identity for profile in profiles}
        session._position_profile_generations = {
            profile.writer_id: getattr(profile, 'generation', None) for profile in profiles
        }
        session._position_profile_identity = profiles[0].identity
        session._position_profile_id = profiles[0].profile_id
        session._position_writer_id = profiles[0].writer_id
        session._position_binding_identity_hash = controller_binding_plan.identity_hash
        session._position_source_closure_digest = source.source_closure_digest
        session._position_applied_boundary_ids = set()
        if len(profiles) == 2:
            session._position_control_bindings_by_semantic = {
                profile.gripper_semantic_id: ControlBinding(profile.gripper_semantic_id, .08)
                for profile in profiles
            }
            native_open_actuator_ids = dict(zip(
                source.open_actuators, session._open_actuators, strict=True,
            ))
            session._open_actuators_by_semantic = {
                profile.gripper_semantic_id: native_open_actuator_ids[profile.open_actuator]
                for profile in profiles
            }
    return session


@__import__('contextlib').contextmanager
def position_subject_interval(session, target, state, *, controller=None):
    """Authorize one Controller-produced target for the current live boundary."""
    session._require_reset()
    binding = getattr(session._source, 'position_subject_binding', None)
    if binding is None:
        raise ValueError('position subject interval requires its declared binding')
    split_bundle = None
    if len(binding.plan.controller_bindings) != 1:
        from ...controllers.canonical.split_panda_position import (
            PandaArmPositionControllerV1, PandaHandPositionControllerV1,
            SplitPandaPositionControllerV1, SplitPositionBundleV1,
        )
        if type(controller) is not SplitPandaPositionControllerV1:
            raise TypeError('multiple position subjects require their actual split Controller owners')
        split_bundle = controller.last_split_bundle
        if (type(split_bundle) is not SplitPositionBundleV1
                or type(controller.arm) is not PandaArmPositionControllerV1
                or type(controller.hand) is not PandaHandPositionControllerV1
                or controller.arm.identity != split_bundle.arm_identity
                or controller.hand.identity != split_bundle.hand_identity):
            raise ValueError('split Position outputs do not belong to the live Controller owners')
        split_bundle.validate_target(target, binding.plan)
    current = session.snapshot()
    if current.to_mapping() != state.to_mapping():
        raise ValueError('position subject target was computed from a stale state')
    boundary = (session.provider_materialization_id, session.episode_id,
                session.state_revision, current.control_step)
    consumed = getattr(session, '_subject_position_consumed', None)
    if consumed is None:
        consumed = session._subject_position_consumed = set()
    if boundary in consumed or getattr(session, '_subject_position_inflight', None) is not None:
        raise ValueError('position subject boundary is already consumed or active')
    consumed.add(boundary)
    session._subject_position_inflight = (boundary, target.identity_hash, target.controller_identity)
    session._subject_position_split_bundle = split_bundle
    try:
        yield
    finally:
        session._subject_position_inflight = None
        session._subject_position_split_bundle = None


def validate_target(session,target):
    if not isinstance(target, CanonicalControlTarget):raise TypeError("CanonicalControlTarget required")
    session._require_reset()
    if not hasattr(session,'_control_binding'):raise ValueError('control session admission required')
    subject_binding = getattr(getattr(session, '_source', None), 'position_subject_binding', None)
    if subject_binding is not None:
        inflight = getattr(session, '_subject_position_inflight', None)
        if (not isinstance(inflight, tuple) or len(inflight) != 3
                or inflight[0][0] != session.provider_materialization_id
                or inflight[0][1] != session.episode_id
                or inflight[0][3] != session.snapshot().control_step
                or inflight[2] != target.controller_identity
                or (not getattr(session, '_inner_interval_active', False)
                    and inflight[1] != target.identity_hash)):
            raise ValueError('position target is not authorized for the current subject boundary')
        from ...assembly.source_composition import PositionSubjectControlBindingV1
        if type(subject_binding) is not PositionSubjectControlBindingV1:
            raise TypeError('position target requires its exact subject binding')
        binding_plan = subject_binding.plan
        if (not binding_plan._compiled or binding_plan.artifact_identity_hash != target.task_artifact_hash
                or binding_plan.source_closure_digest != session._source.source_closure_digest):
            raise ValueError('position target lacks its source-bound Controller binding')
        bindings = binding_plan.controller_bindings
        if len(bindings) == 1:
            if bindings[0].controller_identity != target.controller_identity:
                raise ValueError('position target Controller identity differs from subject binding')
        else:
            from ...controllers.canonical.split_panda_position import SplitPositionBundleV1
            bundle = getattr(session, '_subject_position_split_bundle', None)
            if type(bundle) is not SplitPositionBundleV1:
                raise ValueError('position target lacks its admitted component outputs')
            bundle.validate_target(target, binding_plan)
        if {writer for _, _, writer in binding_plan.resource_writers} != {item.writer_id for item in bindings}:
            raise ValueError('position target writers differ from the declared Controller binding')
        native_resources = {native for _, _, native in subject_binding.resource_native_names}
        requested_resources = set(session._source.joint_targets.values()) | set(session._source.open_actuators)
        if native_resources != requested_resources:
            raise ValueError('position target native writers differ from subject binding')
        composition = getattr(session._source, 'composition_runtime_input', None)
        if composition is not None and (
                binding_plan.identity_hash != composition.plan.control_binding_identity_sha256
                or subject_binding.subject_identity_sha256 != composition.plan.subject_binding_identity_sha256):
            raise ValueError('position subject binding differs from source composition')
    if hasattr(session, '_position_profile_identities'):
        if getattr(session, '_position_target_in_flight', None) != target.identity_hash:
            raise ValueError('PositionServoV1 target must pass source-bound boundary validation')
        profile = next((item for item in session._position_profiles_by_writer.values()
                        if item.identity == target.controller_identity), None)
        if (profile is None or set(target.arm_joint_order) != set(profile._target_bindings)
                or target.gripper.semantic_id != profile.gripper_semantic_id):
            raise ValueError('PositionServoV1 target Entity/writer binding mismatch')
    elif hasattr(session, '_position_profile_identity'):
        if (getattr(session, '_position_target_in_flight', None) != target.identity_hash
                or target.controller_identity != session._position_profile_identity):
            raise ValueError('PositionServoV1 target must pass source-bound boundary validation')
    elif hasattr(session, '_r1_controller_identity'):
        expected = getattr(session, '_r1_target_in_flight', None)
        if (not isinstance(expected, tuple) or len(expected) != 4
                or expected[0] != target.identity_hash
                or expected[2] != target.controller_identity
                or expected[2] != session._r1_controller_identity
                or expected[3] != session._r1_binding_identity_hash):
            raise ValueError('R1 target must pass source-, Controller- and boundary-bound validation')
    if (target.task_artifact_hash != session._artifact.identity_hash
            or len(target.arm_joint_order) != 7
            or not set(target.arm_joint_order).issubset(session._target_actuators)):
        raise ValueError('canonical control binding mismatch')
    if hasattr(session, '_position_control_bindings_by_semantic'):
        if target.gripper.semantic_id not in session._position_control_bindings_by_semantic:
            raise ValueError('canonical control binding mismatch')
    elif target.gripper.semantic_id != session._control_binding.gripper_semantic_id:
        raise ValueError('canonical control binding mismatch')


def feedback_value(session, state, native_force):
    """Private adapter lowering for audited positive-open Panda tendon binding."""
    from ...controllers.canonical.feedback import CanonicalGripperFeedback
    from ...controllers.canonical.kinematics import FINGERS
    session._require_reset()
    if not hasattr(session, '_control_binding'):
        raise ValueError('control session admission required')
    if state.to_mapping() != session.snapshot().to_mapping():
        raise ValueError('feedback requires the current measured canonical boundary')
    import math
    if not math.isfinite(float(native_force)):
        raise ValueError('nonfinite native actuator force')
    # The legacy route uses panda-v1 names. The bounded source-bound route
    # explicitly adapts its one Entity-qualified Panda finger pair here.
    positions = state.joint_position
    if all(name in positions for name in FINGERS):
        finger_names = FINGERS
    elif getattr(session, '_r1_force_admitted', False):
        matches = {}
        for suffix in ('finger_joint1', 'finger_joint2'):
            found = [name for name in positions if name.endswith('/' + suffix)]
            if len(found) != 1:
                raise ValueError('R1 feedback requires one Entity-qualified finger Joint pair')
            matches[suffix] = found[0]
        if matches['finger_joint1'].rsplit('/', 1)[0] != matches['finger_joint2'].rsplit('/', 1)[0]:
            raise ValueError('R1 feedback finger Joints belong to different Entities')
        finger_names = (matches['finger_joint1'], matches['finger_joint2'])
    else:
        raise ValueError('canonical gripper feedback lacks its declared finger Joint state')
    # Both supported sources bind positive native actuator output to opening.
    return CanonicalControlFeedback('canonical-control-feedback-v0', state.control_step,
        state.simulation_time, CanonicalGripperFeedback(session._control_binding.gripper_semantic_id,
        max(0., float(sum(positions[n] for n in finger_names))), max(0., -float(native_force))))


def _validate_position_source_boundary(
    session, controller_profile, plan, publication, *, scene,
    joint_bindings, frame_bindings,
):
    from ...controllers.canonical.position_profile import PandaPositionServoProfileV1
    from ...controllers.canonical.contracts import PositionControlTargetV1

    if not isinstance(controller_profile, PandaPositionServoProfileV1):
        raise TypeError('PositionServoV1 dispatch requires its actual Controller instance')
    controller_profile._validate_source(controller_profile.source)
    plan_identity = controller_profile._validate_plan(plan)
    admitted_profiles = getattr(session, '_position_profiles_by_writer', None)
    admitted_profile = (
        admitted_profiles.get(controller_profile.writer_id)
        if isinstance(admitted_profiles, dict) else None
    )
    if admitted_profiles is not None:
        session_profile_valid = admitted_profile is not None and (
            admitted_profile.identity == controller_profile.identity
            and admitted_profile.source.source_closure_digest == controller_profile.source.source_closure_digest
        )
        generations = getattr(session, '_position_profile_generations', None)
        if generations is not None:
            session_profile_valid = session_profile_valid and (
                controller_profile.writer_id in generations
                and generations[controller_profile.writer_id] == getattr(controller_profile, 'generation', None)
                and getattr(admitted_profile, 'generation', None) == generations[controller_profile.writer_id]
            )
    else:
        session_profile_valid = (
            getattr(session, '_position_profile_identity', None) == controller_profile.identity
            and getattr(session, '_position_profile_id', None) == controller_profile.profile_id
            and getattr(session, '_position_writer_id', None) == controller_profile.writer_id
        )
    if (not session_profile_valid
            or getattr(session, '_position_binding_identity_hash', None) != plan_identity
            or getattr(session, '_position_source_closure_digest', None) != controller_profile.source.source_closure_digest):
        raise ValueError('RuntimeSession/Controller/plan identity mismatch')
    if publication.view.boundary.scene_identity_hash != plan.scene_identity_hash:
        raise ValueError('position state publication/plan Scene identity mismatch')
    fresh = session.snapshot_v1(
        scene=scene, joint_bindings=joint_bindings, frame_bindings=frame_bindings,
        requirements=controller_profile.requirements,
    )
    if (fresh.view.boundary.boundary_id != publication.view.boundary.boundary_id
            or fresh.view.sample_clock != publication.view.sample_clock):
        raise ValueError('position state publication is stale for the RuntimeSession boundary')
    return plan_identity


def _prepare_position_profile_replacement(
    session, current_profile, candidate_profile, plan, publication, *, scene,
    joint_bindings, frame_bindings,
):
    """Validate one single-Entity Position instance replacement without mutation."""
    from ...controllers.canonical.position_profile import PandaPositionServoProfileV1

    if (type(current_profile) is not PandaPositionServoProfileV1
            or type(candidate_profile) is not PandaPositionServoProfileV1):
        raise TypeError('PositionServoV1 replacement requires exact existing Profile instances')
    for profile in (current_profile, candidate_profile):
        if (profile.identity != profile._constructed_identity
                or profile.config != profile._constructed_config
                or profile._algorithm.identity != profile._constructed_algorithm_identity
                or profile._algorithm.config != profile._constructed_config):
            raise ValueError('PositionServoV1 identity/configuration changed after construction')
    admitted = getattr(session, '_position_profiles_by_writer', None)
    if (not isinstance(admitted, dict) or len(admitted) != 1
            or admitted.get(current_profile.writer_id) is not current_profile):
        raise ValueError('PositionServoV1 replacement requires the admitted single active writer')
    if len(plan.controller_bindings) != 1:
        raise ValueError('PositionServoV1 replacement is single-writer only')

    current_profile._validate_source(session._source)
    candidate_profile._validate_source(candidate_profile.source)
    plan_identity = current_profile._validate_plan(plan)
    if candidate_profile._validate_plan(plan) != plan_identity:
        raise ValueError('replacement Controller plan identity changed')
    if (current_profile._plan_identity_hash != plan_identity
            or current_profile._episode_id != publication.view.boundary.episode_id
            or current_profile._reset_sample_id != publication.view.boundary.reset_sample_id
            or current_profile._next_control_step != publication.view.boundary.control_step):
        raise ValueError('active PositionServoV1 memory is not at the published boundary')

    compatible_fields = (
        'profile_id', 'writer_id', 'entity_id', 'joint_ids', 'finger_joint_ids',
        'hand_frame_id', 'native_prefix', 'actuator_prefix', '_source_joint_ids',
        '_target_bindings', 'open_actuator', 'gripper_semantic_id', 'requirements',
        '_source_bindings',
    )
    for field_name in compatible_fields:
        if getattr(current_profile, field_name) != getattr(candidate_profile, field_name):
            raise ValueError(f'PositionServoV1 replacement changes owned binding field {field_name}')
    if (current_profile.artifact.identity_hash != candidate_profile.artifact.identity_hash
            or current_profile.scene.identity_hash != candidate_profile.scene.identity_hash
            or current_profile.source.source_closure_digest != candidate_profile.source.source_closure_digest
            or current_profile.model.source_sha256 != candidate_profile.model.source_sha256
            or current_profile.artifact.timebase != candidate_profile.artifact.timebase
            or current_profile.tcp_profile.to_mapping() != candidate_profile.tcp_profile.to_mapping()
            or current_profile.controller_binding() != candidate_profile.controller_binding()):
        raise ValueError('PositionServoV1 replacement changes schema, source, frame, unit, timebase or ownership')
    if candidate_profile.identity == current_profile.identity or candidate_profile.config == current_profile.config:
        raise ValueError('PositionServoV1 replacement must select a distinct parameterized instance')

    _validate_position_source_boundary(
        session, current_profile, plan, publication, scene=scene,
        joint_bindings=joint_bindings, frame_bindings=frame_bindings,
    )
    generation = getattr(candidate_profile, 'generation', None)
    if generation is not None and (type(generation) is not int or generation < 0):
        raise ValueError('replacement Position Controller generation must be nonnegative')
    activation = candidate_profile._prepare_switch_activation(publication, plan)
    replacement_profiles = dict(admitted)
    replacement_profiles[candidate_profile.writer_id] = candidate_profile
    replacement_identities = dict(getattr(session, '_position_profile_identities', {}))
    replacement_identities[candidate_profile.writer_id] = candidate_profile.identity
    replacement_generations = dict(getattr(session, '_position_profile_generations', {}))
    replacement_generations[candidate_profile.writer_id] = getattr(candidate_profile, 'generation', None)
    return {
        'current_profile': current_profile,
        'candidate_profile': candidate_profile,
        'activation': activation,
        'profiles_by_writer': replacement_profiles,
        'profile_identities': replacement_identities,
        'profile_generations': replacement_generations,
        'profile_identity': candidate_profile.identity,
        'profile_id': candidate_profile.profile_id,
        'writer_id': candidate_profile.writer_id,
    }


def _commit_position_profile_replacement(session, prepared):
    """Commit the prepared active-writer projection at a selected safe boundary."""
    current = prepared['current_profile']
    candidate = prepared['candidate_profile']
    if session._position_profiles_by_writer.get(current.writer_id) is not current:
        raise ValueError('active PositionServoV1 writer changed before replacement commit')
    # All candidate/profile/source/schema checks happened during preparation.
    # Seed the fresh candidate's cursor only after this last session-owner guard;
    # plain field assignment below then makes it the admitted writer.
    candidate._activate_switch_memory(prepared['activation'])
    (
        session._position_profiles_by_writer,
        session._position_profile_identities,
        session._position_profile_generations,
        session._position_profile_identity,
        session._position_profile_id,
        session._position_writer_id,
    ) = (
        prepared['profiles_by_writer'],
        prepared['profile_identities'],
        prepared['profile_generations'],
        prepared['profile_identity'],
        prepared['profile_id'],
        prepared['writer_id'],
    )


def _position_control_part(
    session, target, *, controller_profile, plan, publication, scene,
    joint_bindings, frame_bindings,
):
    """Preflight one writer and return its exact resources and provider lowerer."""
    from ...controllers.canonical.contracts import PositionControlTargetV1

    if type(target) is not PositionControlTargetV1:
        raise TypeError('PositionControlTargetV1 required')
    target.validate()
    plan_identity = _validate_position_source_boundary(
        session, controller_profile, plan, publication, scene=scene,
        joint_bindings=joint_bindings, frame_bindings=frame_bindings,
    )
    boundary = publication.view.boundary
    if (target.writer_id != controller_profile.writer_id
            or target.controller_identity != controller_profile.identity
            or target.binding_identity_hash != plan_identity
            or target.source_closure_digest != controller_profile.source.source_closure_digest
            or target.source_boundary.boundary_id != boundary.boundary_id
            or target.sample_clock != publication.view.sample_clock
            or target.target.controller_identity != controller_profile.identity
            or target.target.task_artifact_hash != controller_profile.artifact.identity_hash):
        raise ValueError('position target writer/Profile/plan/source boundary mismatch')
    if target.target.gripper.semantic_id != controller_profile.gripper_semantic_id:
        raise ValueError('position target gripper semantic binding mismatch')
    def lower_position_target():
        session._position_target_in_flight = target.target.identity_hash
        session._position_target_source_boundary_in_flight = target.source_boundary
        try:
            acknowledgement = session.apply_control(target.target)
        finally:
            session._position_target_in_flight = None
            session._position_target_source_boundary_in_flight = None
        if acknowledgement.target_hash != target.target.identity_hash:
            raise ValueError('Provider acknowledgement does not match the applied canonical target')
        return acknowledgement

    resource_ids = tuple(sorted(f'{entity}/{actuator}'
                                for entity, actuator, writer in plan.resource_writers
                                if writer == target.writer_id))
    if not resource_ids:
        raise ValueError('position writer owns no declared ControlBinding resources')
    return boundary, resource_ids, lower_position_target


def apply_position_control_target(
    session,
    target,
    *,
    controller_profile,
    plan,
    publication,
    scene,
    joint_bindings,
    frame_bindings,
):
    """Validate and submit one source-bound position target through the common owner."""
    boundary, resource_ids, lower = _position_control_part(
        session, target, controller_profile=controller_profile, plan=plan,
        publication=publication, scene=scene, joint_bindings=joint_bindings,
        frame_bindings=frame_bindings,
    )
    from .control_submission import submit_control_command
    acknowledgement = submit_control_command(
        session, target, command_kind='position-target', command_sha256=target.identity_hash,
        source_id=controller_profile.source.source_id,
        source_closure_sha256=target.source_closure_digest,
        artifact_sha256=target.target.task_artifact_hash,
        boundary=boundary, sample_clock=target.sample_clock,
        controller_generation=int(getattr(controller_profile, 'generation', 0)),
        controller_identities=(target.controller_identity,), writer_ids=(target.writer_id,),
        resource_ids=resource_ids,
        resource_owners=((target.writer_id, resource_ids),),
        units=('arm-position:rad', 'gripper-position:m'),
        lowering=f'{type(session).__module__}.{type(session).__qualname__}.apply_control(position)',
        lower=lower)
    return acknowledgement


def apply_position_control_batch(
    session, parts, *, plan, publication, scene, joint_bindings, frame_bindings,
):
    """Commit all preflighted writer targets as one interval transaction."""
    parts = tuple(parts)
    if len(parts) < 2:
        raise ValueError('position batch requires at least two writer parts')
    prepared = []
    for profile, target in parts:
        boundary, resources, lower = _position_control_part(
            session, target, controller_profile=profile, plan=plan,
            publication=publication, scene=scene, joint_bindings=joint_bindings,
            frame_bindings=frame_bindings,
        )
        prepared.append((profile, target, boundary, resources, lower))
    prepared.sort(key=lambda row: row[1].writer_id)
    targets = tuple(row[1] for row in prepared)
    writer_ids = tuple(target.writer_id for target in targets)
    resource_owners = tuple((target.writer_id, row[3])
                            for row, target in zip(prepared, targets))
    resources = tuple(sorted(resource for _writer, owned in resource_owners for resource in owned))
    if len(resources) != len(set(resources)):
        raise ValueError('position writers claim a conflicting provider resource')
    boundary = prepared[0][2]
    if any(row[2] != boundary for row in prepared[1:]):
        raise ValueError('position writer targets do not share one state boundary')

    from .control_submission import (
        PositionControlBatchAcknowledgementV1, PositionControlBatchV1,
        submit_control_command,
    )
    batch = PositionControlBatchV1(targets)
    progress = {'attempted_writer_ids': [], 'completed_writer_ids': []}

    def lower_batch():
        acknowledgements = []
        for profile, target, _target_boundary, _resources, lower in prepared:
            progress['attempted_writer_ids'].append(target.writer_id)
            acknowledgement = lower()
            progress['completed_writer_ids'].append(target.writer_id)
            acknowledgements.append(acknowledgement)
        aggregate = hashlib.sha256(json.dumps(
            tuple((target.writer_id, ack.target_hash)
                  for target, ack in zip(targets, acknowledgements)),
            separators=(',', ':')).encode()).hexdigest()
        return PositionControlBatchAcknowledgementV1(tuple(acknowledgements), aggregate)

    identities = tuple(sorted({target.controller_identity for target in targets}))
    anchor_writer = getattr(session, '_position_writer_id', prepared[0][1].writer_id)
    anchor = next((row[0] for row in prepared if row[1].writer_id == anchor_writer), None)
    if anchor is None:
        raise ValueError('position batch lacks the legacy lifecycle anchor writer')
    acknowledgement = submit_control_command(
        session, batch, command_kind='position-target', command_sha256=batch.identity_hash,
        source_id=prepared[0][0].source.source_id,
        source_closure_sha256=targets[0].source_closure_digest,
        artifact_sha256=targets[0].target.task_artifact_hash,
        boundary=boundary, sample_clock=targets[0].sample_clock,
        controller_generation=int(getattr(anchor, 'generation', 0)),
        controller_identities=identities, writer_ids=writer_ids,
        resource_ids=resources, resource_owners=resource_owners,
        units=('arm-position:rad', 'gripper-position:m'),
        lowering=f'{type(session).__module__}.{type(session).__qualname__}.apply_control(position-batch)',
        lower=lower_batch, submission_progress=progress,
    )
    return acknowledgement.acknowledgements


def execute_position_control_interval(
    session,
    controller_profile,
    plan,
    request,
    publication,
    *,
    scene,
    joint_bindings,
    frame_bindings,
    requirements=None,
):
    """Preflight both groups, compute/apply once, then advance one outer interval."""
    from ...controllers.canonical.position_sequence import PositionActionSequenceV1
    if type(request) is PositionActionSequenceV1:
        return _execute_position_action_sequence(
            session, controller_profile, plan, request, publication, scene=scene,
            joint_bindings=joint_bindings, frame_bindings=frame_bindings,
            requirements=requirements)
    prepared = prepare_structured_action(plan, request)
    from .transport import RemoteSession
    if isinstance(session, RemoteSession):
        if isinstance(controller_profile, (tuple, list)):
            raise ValueError('isolated Position route currently requires one writer')
        if len(prepared) != 1 or prepared[0][0] != controller_profile.writer_id:
            raise ValueError('PositionServoV1 requires exactly one matching structured-action writer')
        controller_profile._validate_source(controller_profile.source)
        plan_identity = controller_profile._validate_plan(plan)
        if session.position_preflight(publication) != plan_identity:
            raise ValueError('worker Position plan identity mismatch')
        canonical, target = controller_profile.compute(publication, prepared[0][1], plan)
        applied = session.position_apply(target, publication)
        state = session.step()
        next_publication = session.snapshot_v1(
            scene=scene, joint_bindings=joint_bindings, frame_bindings=frame_bindings,
            requirements=requirements or controller_profile.requirements,
        )
        return canonical, target, applied, state, next_publication
    if isinstance(controller_profile, (tuple, list)):
        profiles = tuple(controller_profile)
        if len(profiles) != 2 or any(not hasattr(item, 'controller_binding') for item in profiles):
            raise ValueError('bounded dual-Entity Position dispatch requires exactly two profile instances')
        by_writer = {profile.writer_id: profile for profile in profiles}
        if len(by_writer) != 2 or tuple(writer for writer, _action in prepared) != tuple(sorted(by_writer)):
            raise ValueError('complete structured request does not match the admitted Position writers')
        if {binding.writer_id for binding in plan.controller_bindings} != set(by_writer):
            raise ValueError('Position profile set does not exactly match the ControlBindingPlan')
        sources = {(profile.source.source_id, profile.source.source_closure_digest,
                    profile.artifact.identity_hash) for profile in profiles}
        if len(sources) != 1:
            raise ValueError('Position writers must share source and Artifact')
        actions = dict(prepared)
        # Verify every writer/profile/source/state boundary before any Controller compute.
        for writer_id in sorted(by_writer):
            _validate_position_source_boundary(
                session, by_writer[writer_id], plan, publication, scene=scene,
                joint_bindings=joint_bindings, frame_bindings=frame_bindings,
            )
        computed = []
        for writer_id in sorted(by_writer):
            profile = by_writer[writer_id]
            canonical, target = profile.compute(publication, actions[writer_id], plan)
            computed.append((profile, canonical, target))
        acknowledgements = apply_position_control_batch(
            session, tuple((profile, target) for profile, _canonical, target in computed),
            plan=plan, publication=publication, scene=scene,
            joint_bindings=joint_bindings, frame_bindings=frame_bindings,
        )
        applied = tuple((canonical, target, acknowledgement)
                        for (_profile, canonical, target), acknowledgement
                        in zip(computed, acknowledgements))
        state = session.step()
        next_publication = session.snapshot_v1(
            scene=scene, joint_bindings=joint_bindings, frame_bindings=frame_bindings,
            requirements=requirements or profiles[0].requirements,
        )
        return applied, state, next_publication
    if len(prepared) != 1 or prepared[0][0] != controller_profile.writer_id:
        raise ValueError('PositionServoV1 requires exactly one matching structured-action writer')
    _validate_position_source_boundary(
        session, controller_profile, plan, publication, scene=scene,
        joint_bindings=joint_bindings, frame_bindings=frame_bindings,
    )
    canonical, target = controller_profile.compute(publication, prepared[0][1], plan)
    applied = apply_position_control_target(
        session, target, controller_profile=controller_profile, plan=plan,
        publication=publication, scene=scene, joint_bindings=joint_bindings,
        frame_bindings=frame_bindings,
    )
    state = session.step()
    next_publication = session.snapshot_v1(
        scene=scene, joint_bindings=joint_bindings, frame_bindings=frame_bindings,
        requirements=requirements or controller_profile.requirements,
    )
    return canonical, target, applied, state, next_publication



def _execute_position_action_sequence(session, profile, plan, action, publication, *,
                                      scene, joint_bindings, frame_bindings, requirements):
    """Commit and execute one bounded, source-bound MuJoCo Position sequence."""
    from .mujoco import _MuJoCoSession
    from .control_submission import PositionControlSequenceV1, submit_control_command
    from ...controllers.canonical.position_profile import PandaPositionServoProfileV1
    if (type(session) is not _MuJoCoSession or type(profile) is not PandaPositionServoProfileV1
            or getattr(session, '_mixed_actuator_plan', None) is not None
            or hasattr(session, '_gravity_model')):
        raise ValueError('Position sequence requires the admitted scalar MuJoCo Position port')
    physical = getattr(session, '_physical_port', None)
    if physical is not None:
        from .mujoco_control_resources import position_native_dofs
        position_dofs = position_native_dofs(session, profile, plan)
        if position_dofs.intersection(physical.dofs.values()):
            raise ValueError('Position and physical bindings overlap native DOFs')
        raise ValueError('disjoint Position and physical plans require a common mixed submission')
    count = session._artifact.timebase.control_substeps
    action.validate(substeps=count)
    _validate_position_source_boundary(session, profile, plan, publication, scene=scene,
        joint_bindings=joint_bindings, frame_bindings=frame_bindings)
    if getattr(session, '_prepared_position_sequence', None) is not None:
        raise RuntimeError('Position sequence is already prepared')
    previews = profile.preview_absolute_joint_targets(publication,
        tuple(item.request for item in action.slices), plan)
    prepared = []
    for item, (canonical, target) in zip(action.slices, previews, strict=True):
        boundary, resources, lower = _position_control_part(session, target,
            controller_profile=profile, plan=plan, publication=publication, scene=scene,
            joint_bindings=joint_bindings, frame_bindings=frame_bindings)
        # Provider validation is read-only; the in-flight marker is scoped to
        # this preflight and is not an acknowledgement or physical write.
        session._position_target_in_flight = target.target.identity_hash
        session._position_target_source_boundary_in_flight = target.source_boundary
        try:
            validate_target(session, target.target)
        finally:
            session._position_target_in_flight = None
            session._position_target_source_boundary_in_flight = None
        prepared.append((item, canonical, target, boundary, resources, lower))
    if any(row[3] != prepared[0][3] or row[4] != prepared[0][4] for row in prepared):
        raise ValueError('Position sequence slices differ in boundary or resources')
    sequence = PositionControlSequenceV1(action,
        tuple((row[0].start_substep, row[0].end_substep, row[2]) for row in prepared))
    sequence.validate()
    session._prepared_position_sequence = sequence
    try:
        ack = submit_control_command(session, sequence, command_kind='position-target',
            command_sha256=sequence.identity_hash, source_id=profile.source.source_id,
            source_closure_sha256=profile.source.source_closure_digest,
            artifact_sha256=profile.artifact.identity_hash, boundary=publication.view.boundary,
            sample_clock=publication.view.sample_clock,
            controller_generation=int(getattr(profile, 'generation', 0)),
            controller_identities=(profile.identity,), writer_ids=(profile.writer_id,),
            resource_ids=prepared[0][4], resource_owners=((profile.writer_id, prepared[0][4]),),
            units=('arm-position:rad', 'gripper-position:m'),
            lowering=f'{type(session).__module__}.{type(session).__qualname__}.stage_position_sequence',
            lower=lambda: session.stage_position_sequence(sequence, tuple(row[5] for row in prepared)))
        # Preview is pure. Consume the Controller cursor only after the common
        # submission owner has acknowledged staging; any later failure is
        # fault-latched by the selected Position lifecycle and requires reset.
        if session.state_boundary_identity() != publication.view.boundary:
            raise ValueError('Position sequence Controller boundary changed during staging')
        profile.commit_absolute_joint_preview(publication, plan, sequence,
                                               session._last_scene_control_submission)
        state = session.step()
        applied = getattr(session, '_last_position_sequence_applied', None)
        if type(applied) is not tuple or len(applied) != len(prepared):
            raise ValueError('Position sequence did not acknowledge every native target')
        next_publication = session.snapshot_v1(scene=scene, joint_bindings=joint_bindings,
            frame_bindings=frame_bindings, requirements=requirements or profile.requirements)
        # Preserve the established single-target transition shape using the
        # last real native acknowledgement; the scene receipt carries slices.
        last = prepared[-1]
        return last[1], last[2], applied[-1], state, next_publication
    finally:
        if getattr(session, '_prepared_position_sequence', None) is sequence:
            session._prepared_position_sequence = None


def _r1_controller_state_from_publication(publication, scene):
    from ...artifacts import CanonicalStateView

    view = publication.view
    view.validate_against_scene(scene)
    entity_id = 'panda-main'
    joint_values = {
        value.joint_id: value for value in view.joints if value.entity_id == entity_id
    }
    arm_joint_ids = tuple(f'joint{index}' for index in range(1, 8))
    finger_joint_ids = ('finger_joint1', 'finger_joint2')
    expected_ids = set(arm_joint_ids + finger_joint_ids)
    if set(joint_values) != expected_ids:
        raise ValueError('R1 typed Controller input requires exactly its seven arm and two finger Joints')
    positions = {}
    velocities = {}
    for joint_id, value in joint_values.items():
        if len(value.position) != 1 or len(value.velocity) != 1:
            raise ValueError(f'R1 scalar Joint has an unsupported typed layout: {joint_id}')
        positions[f'panda-v1/{joint_id}'] = float(value.position[0])
        velocities[f'panda-v1/{joint_id}'] = float(value.velocity[0])
    hand_frames = [
        value for value in view.frames
        if value.frame.entity_id == entity_id and value.frame.frame_id == 'hand'
    ]
    if len(hand_frames) != 1:
        raise ValueError('R1 typed Controller input requires one panda-main/hand Frame')
    return CanonicalStateView(
        'canonical-state-v0', view.convention, view.boundary.control_step,
        view.sample_clock.simulation_time_s, positions, velocities,
        {'panda-v1/ee': hand_frames[0].pose_world},
    )


def execute_plan_bound_r1_control_interval(
    session,
    controller,
    plan,
    request,
    publication,
    *,
    scene,
    joint_bindings,
    frame_bindings,
):
    """Run one exact single-Entity R1 interval through existing Core owners.

    This bounded route consumes the actual typed raw force publication, lets
    the existing Provider session perform the canonical feedback projection,
    computes one real R1 target, applies it through the admitted session, and
    returns the next typed state publication.
    """
    from ...artifacts import CanonicalStatePublicationV2
    from ...controllers.canonical.production import ProductionCanonicalPandaController
    from ...controllers.canonical.contracts import CanonicalControlTarget
    from dataclasses import replace

    if type(controller) is not ProductionCanonicalPandaController:
        raise TypeError('bounded R1 dispatch requires its actual ProductionCanonicalPandaController')
    if not isinstance(publication, CanonicalStatePublicationV2):
        raise TypeError('bounded R1 dispatch requires CanonicalStatePublicationV2')
    if (getattr(session, '_r1_controller_identity', None) != controller.identity
            or getattr(session, '_r1_binding_identity_hash', None) != plan.identity_hash
            or getattr(session, '_r1_source_closure_digest', None) != getattr(session._source, 'source_closure_digest', None)):
        raise ValueError('RuntimeSession/Controller/plan/source identity mismatch')
    if len(plan.controller_bindings) != 1:
        raise ValueError('R1 plan must contain exactly one Controller binding')
    binding = plan.controller_bindings[0]
    if (binding.controller_identity != controller.identity
            or binding.writer_id != 'panda-main/production-r1'):
        raise ValueError('R1 Controller instance does not match the one-writer plan')
    prepared = prepare_structured_action(plan, request)
    if len(prepared) != 1 or prepared[0][0] != binding.writer_id:
        raise ValueError('R1 structured action must cover its exact bound writer')
    publication.validate()
    publication.view.validate_requirements(binding.feedback_requirements)
    if publication.view.boundary.scene_identity_hash != plan.scene_identity_hash:
        raise ValueError('R1 typed state publication and ControlBindingPlan Scene differ')
    if publication.view.boundary.provider_materialization_id != session._provider_materialization_id:
        raise ValueError('R1 typed state publication belongs to another Provider materialization')
    state = _r1_controller_state_from_publication(publication, scene)
    if state.control_step != publication.view.boundary.control_step:
        raise ValueError('R1 Controller input step differs from typed state boundary')
    native_state = session.snapshot()
    if (native_state.control_step != state.control_step
            or native_state.simulation_time != state.simulation_time):
        raise ValueError('R1 typed Joint/Frame input is stale for the RuntimeSession')

    fresh = session.snapshot_v2(
        scene=scene, joint_bindings=joint_bindings, frame_bindings=frame_bindings,
        requirements=binding.feedback_requirements,
    )
    if (fresh.view.identity_hash != publication.view.identity_hash
            or fresh.view.boundary.boundary_id != publication.view.boundary.boundary_id):
        raise ValueError('R1 typed state publication is stale for the live RuntimeSession boundary')
    forces = [
        value for value in publication.view.actuator_forces
        if value.entity_id == 'panda-main' and value.actuator_id == 'actuator8'
    ]
    if len(forces) != 1 or not forces[0].valid:
        raise ValueError('R1 required raw actuator force is absent or invalid')
    force_value = forces[0]
    if force_value.unit != 'N':
        raise ValueError('bounded Panda tendon force must remain signed in N')
    if (force_value.source_closure_digest != session._r1_source_closure_digest
            or force_value.provider_materialization_id != session._provider_materialization_id):
        raise ValueError('R1 typed force sample source/materialization identity mismatch')
    feedback = session.control_feedback(native_state, actuator_force=force_value)

    boundary_id = publication.view.boundary.boundary_id
    consumed = session._r1_applied_boundary_ids
    if boundary_id in consumed:
        raise ValueError('R1 target for this state boundary was already applied')
    if getattr(session, '_r1_controller_episode_id', None) != publication.view.boundary.episode_id:
        controller.reset(state, feedback)
        session._r1_controller_episode_id = publication.view.boundary.episode_id
    elif controller.expected_control_step != state.control_step:
        raise ValueError('R1 Controller memory is not at the published evaluation boundary')

    canonical, legacy_target = controller.compute(state, feedback, prepared[0][1])
    source_joint_order = tuple(
        f'panda-main/{name.rsplit("/", 1)[-1]}' for name in legacy_target.arm_joint_order
    )
    if len(source_joint_order) != 7 or len(set(source_joint_order)) != 7:
        raise ValueError('R1 target does not contain the seven exact Panda arm Joints')
    if legacy_target.gripper.semantic_id != 'panda-main/gripper':
        raise ValueError('R1 target gripper semantic identity does not match its bound Entity')
    target = replace(
        legacy_target,
        arm_joint_order=source_joint_order,
        arm_position={
            source: legacy_target.arm_position[legacy]
            for source, legacy in zip(source_joint_order, legacy_target.arm_joint_order, strict=True)
        },
        arm_servo_position={
            source: legacy_target.arm_servo_position[legacy]
            for source, legacy in zip(source_joint_order, legacy_target.arm_joint_order, strict=True)
        },
    )
    if not isinstance(target, CanonicalControlTarget):
        raise TypeError('R1 source adapter must preserve the existing canonical target contract')
    target.validate()
    consumed.add(boundary_id)
    session._r1_target_in_flight = (
        target.identity_hash, boundary_id, controller.identity, plan.identity_hash,
    )
    try:
        acknowledgement = session.apply_control(target)
    finally:
        session._r1_target_in_flight = None
    if acknowledgement.target_hash != target.identity_hash:
        raise ValueError('R1 Provider acknowledgement does not match its applied canonical target')
    stepped_state = session.step()
    next_publication = session.snapshot_v2(
        scene=scene, joint_bindings=joint_bindings, frame_bindings=frame_bindings,
        requirements=binding.feedback_requirements,
    )
    expected_step = state.control_step + 1
    expected_time = state.simulation_time + 0.01
    if (stepped_state.control_step != expected_step
            or abs(stepped_state.simulation_time - expected_time) > 1.0e-12
            or next_publication.view.boundary.control_step != expected_step
            or abs(next_publication.view.sample_clock.simulation_time_s - expected_time) > 1.0e-12):
        raise ValueError('R1 interval did not complete exactly one 100 Hz control boundary')
    next_publication.view.validate_requirements(binding.feedback_requirements)
    return canonical, target, acknowledgement, stepped_state, next_publication, feedback


def validate_position_control_subjects(*, scene, root, children, subjects, plan, attachment_scene=None):
    """Bind position Controller resources to declared subjects and logical paths.

    This validates static ownership only. Provider build and per-interval
    target validation remain separate obligations.
    """
    from ...artifacts.logical_assembly import LogicalAssemblySubcomponentReferenceV1
    from ...artifacts.logical_assembly_resolution import resolve_logical_assembly
    from ...runtime.sessions.physical_control import ControlledSubjectV1
    if (type(subjects) is not tuple or not subjects
            or any(type(subject) is not ControlledSubjectV1 for subject in subjects)):
        raise TypeError('position binding requires typed controlled subjects')
    if type(plan) is not ControlBindingPlanV1 or not plan._compiled:
        raise TypeError('position subjects require a compiled Controller binding plan')
    resolved = resolve_logical_assembly(root, scene, children)
    if (resolved.scene_identity_sha256 != plan.scene_identity_hash
            or resolved.root_logical_content_sha256 != plan.assembly_identity_hash):
        raise ValueError('position subject Assembly differs from Controller binding')
    by_id = {subject.subject_id: subject for subject in subjects}
    if len(by_id) != len(subjects) or len({s.entity_id for s in subjects}) != len(subjects):
        raise ValueError('position subjects must have unique identities and entities')
    leaves = {leaf.full_path: leaf.member for leaf in resolved.leaves}
    from ...artifacts.logical_assembly import LogicalAssemblyEntityMemberV1
    owners = {member.entity_id for member in leaves.values()
              if type(member) is LogicalAssemblyEntityMemberV1}
    owning_sources = [subject.source_id for subject in subjects if subject.source_ownership == 'owns_source']
    if len(owning_sources) != len(set(owning_sources)):
        raise ValueError('position subjects cannot duplicate source ownership')
    used = set()
    for subject in subjects:
        if subject.entity_id not in owners:
            raise ValueError('position subject lacks an Assembly entity owner')
        chain, cursor = set(), subject
        while cursor.parent_subject_id is not None:
            if cursor.subject_id in chain:
                raise ValueError('position subject parent cycle')
            chain.add(cursor.subject_id)
            cursor = by_id.get(cursor.parent_subject_id)
            if cursor is None:
                raise ValueError('position subject parent is missing')
        roots = {item.root_frame_id for item in scene.articulations or ()
                 if item.entity_id == subject.entity_id}
        if subject.root_frame.frame_id not in roots:
            raise ValueError('position subject root differs from Scene articulation')
        expected_writers = {writer for entity, _, writer in plan.resource_writers
                            if entity == subject.entity_id}
        if expected_writers != set(subject.controller_writers):
            raise ValueError('position subject writers differ from Controller binding')
        expected_joints = {joint.joint_id for art in scene.articulations or ()
                           if art.entity_id == subject.entity_id for joint in art.joints
                           if joint.kind != 'fixed'}
        names = set()
        for path in subject.channel_paths:
            member = leaves.get(path)
            if (path in used or type(member) is not LogicalAssemblySubcomponentReferenceV1
                    or member.target_kind != 'joint' or member.target.entity_id != subject.entity_id):
                raise ValueError('position subject channel path does not resolve to its own joint')
            used.add(path); names.add(member.target.joint_id)
        if len(names) != len(subject.channel_paths) or names != expected_joints:
            raise ValueError('position subject channels do not cover its joints exactly')
        if subject.root_mode == 'constrained':
            parent = by_id.get(subject.parent_subject_id)
            attachment = subject.attachment_plan
            if parent is None or attachment is None or attachment_scene is None:
                raise ValueError('constrained position subject requires declared source attachment')
            if (attachment.parent_entity_id != parent.entity_id
                    or attachment.child_entity_id != subject.entity_id
                    or attachment.parent_root != parent.root_frame
                    or attachment.child_root != subject.root_frame
                    or attachment.scene_pin.scene_identity_sha256 != attachment_scene.identity_hash
                    or attachment.source_closure_sha256 != subject.source_closure_sha256):
                raise ValueError('position subject attachment differs from source ownership')
        elif subject.parent_subject_id is not None:
            raise ValueError('unconstrained subject cannot have a parent')
    if {entity for entity, _, _ in plan.resource_writers} != {s.entity_id for s in subjects}:
        raise ValueError('every position resource must have exactly one subject owner')
    if plan.cross_entity_frame_grants:
        attachments = {subject.attachment_plan.identity_hash for subject in subjects
                       if subject.attachment_plan is not None}
        if plan.feedback_attachment_identity_hash not in attachments:
            raise ValueError('position feedback grants differ from the actual subject Attachment')
    return position_subject_identity(plan, subjects)


def position_subject_identity(plan, subjects):
    """Identity of the already validated subjects retained with a binding."""
    subject_facts = []
    for subject in subjects:
        subject_facts.append({'subject_id': subject.subject_id, 'entity_id': subject.entity_id,
            'source_id': subject.source_id, 'source_closure': subject.source_closure_sha256,
            'ownership': subject.source_ownership, 'root_mode': subject.root_mode,
            'root': subject.root_frame.to_mapping(), 'parent': subject.parent_subject_id,
            'channels': subject.channel_paths, 'writers': subject.controller_writers,
            'attachment': None if subject.attachment_plan is None else subject.attachment_plan.identity_hash})
    return _schema_hash({'schema_version': 'position-subject-binding-v1',
                         'scene': plan.scene_identity_hash, 'assembly': plan.assembly_identity_hash,
                         'controller': plan.identity_hash, 'subjects': subject_facts})
