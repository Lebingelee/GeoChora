"""Opt-in semantic control admission; legacy no-control materialize unchanged."""
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from typing import Protocol
from .api import RuntimeSession
from ...controllers.canonical.feedback import CanonicalControlFeedback
from ...controllers.canonical.contracts import (
    AppliedCanonicalControl,
    CanonicalControlTarget,
    RequestedAction,
    StructuredActionRequestV1,
)
from ...artifacts import (
    ActuatorReference,
    CapabilityAdmissionError,
    RequiredCapabilitySet,
    SceneDefinition,
    StateRequirements,
    admit_capabilities,
)
from ...artifacts.contracts import SUPPORTED_STATUSES
from ...environment.types import ActionModeSpec
from .api import materialize,provider_manifest

class ControlledRuntimeSession(RuntimeSession, Protocol):
    def control_feedback(self, state) -> CanonicalControlFeedback: ...
    def apply_control(self, target: CanonicalControlTarget) -> AppliedCanonicalControl: ...


CONTROL_REQUIRED=RequiredCapabilitySet(('articulated_robot','joint_position_actuation','joint_state_query','body_pose_query','frame_pose_query'))


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
    _compiled: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self):
        if self.schema_version != 'control-binding-plan-v1':
            raise ValueError('unsupported ControlBindingPlan schema')
        if len(self.scene_identity_hash) != 64:
            raise ValueError('ControlBindingPlan requires a Scene identity')
        object.__setattr__(self, 'controller_bindings', tuple(sorted(
            self.controller_bindings, key=lambda binding: binding.writer_id,
        )))
        object.__setattr__(self, 'resource_writers', tuple(sorted(self.resource_writers)))
        writer_ids = {binding.writer_id for binding in self.controller_bindings}
        if len(writer_ids) != len(self.controller_bindings):
            raise ValueError('ControlBindingPlan contains duplicate Controller writers')
        resource_keys = tuple((entity_id, actuator_id) for entity_id, actuator_id, _writer in self.resource_writers)
        if len(resource_keys) != len(set(resource_keys)):
            raise ValueError('ControlBindingPlan contains overlapping actuator writers')
        if any(writer_id not in writer_ids for _entity_id, _actuator_id, writer_id in self.resource_writers):
            raise ValueError('ControlBindingPlan resource writer is not bound')

    @property
    def identity_hash(self):
        return _schema_hash({
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
        })


def compile_control_binding_plan(
    scene: SceneDefinition,
    controller_bindings: tuple[ControllerBindingV1, ...],
) -> ControlBindingPlanV1:
    """Resolve each A03 ControlGroup to exactly one existing writer and schema."""
    if not isinstance(scene, SceneDefinition) or scene.schema_version != 'scene-definition-v3':
        raise ValueError('Controller bindings require a canonical scene-definition-v3')
    if not isinstance(controller_bindings, tuple):
        raise TypeError('Controller bindings must be an immutable tuple')
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
        if len(entity_ids) != 1:
            raise ValueError('one Controller writer cannot span multiple Robot entities in this slice')
        controller_entities[binding.writer_id] = next(iter(entity_ids))
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
        _validate_feedback_requirements(scene, binding, entity_ids)

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
    )
    object.__setattr__(plan, '_compiled', True)
    return plan


def _validate_feedback_requirements(scene, binding, entity_ids):
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
        if requirement.entity_id not in entity_ids:
            raise ValueError('Controller feedback requirement crosses its bound Entity')
        if requirement.subject_kind == 'joint' and key not in joints:
            raise ValueError(f'Controller feedback references unknown Joint: {key}')
        if requirement.subject_kind == 'frame' and key not in frames:
            raise ValueError(f'Controller feedback references unknown Frame: {key}')
        if requirement.subject_kind == 'actuator' and key not in actuators:
            raise ValueError(f'Controller feedback references unknown actuator resource: {key}')
        if requirement.subject_kind == 'entity' and (
            requirement.entity_id not in entities or requirement.subject_id not in entities
        ):
            raise ValueError(f'Controller feedback references unknown Entity: {key}')


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


def materialize_control(
    artifact,
    execution,
    *,
    source,
    binding,
    manifest=None,
    controller_binding_plan: ControlBindingPlanV1 | None = None,
):
    actual_manifest=provider_manifest(execution.physics_provider)
    if manifest is not None:admit_capabilities(CONTROL_REQUIRED,manifest,execution)
    admit_capabilities(CONTROL_REQUIRED,actual_manifest,execution)
    if controller_binding_plan is not None:
        if not isinstance(controller_binding_plan, ControlBindingPlanV1) or not controller_binding_plan._compiled:
            raise ValueError('control materialization requires a Scene-validated ControllerBinding plan')
        scene=getattr(source,'scene_definition',None)
        if not isinstance(scene,SceneDefinition) or scene.identity_hash!=controller_binding_plan.scene_identity_hash:
            raise ValueError('ControllerBinding Scene identity does not match RuntimeSource')
        required_feedback={
            requirement.required_capability
            for controller_binding in controller_binding_plan.controller_bindings
            for requirement in controller_binding.feedback_requirements.requirements
            if requirement.requiredness=='required'
        }
        supported={claim.name for claim in actual_manifest.capabilities if claim.status in SUPPORTED_STATUSES}
        if manifest is not None:
            supported &= {claim.name for claim in manifest.capabilities if claim.status in SUPPORTED_STATUSES}
        missing=required_feedback-supported
        if missing:
            raise CapabilityAdmissionError(
                f'missing supported Controller feedback capabilities for '
                f'{execution.physics_provider}: {sorted(missing)}'
            )
    if len(source.joint_targets)!=7 or len(source.open_actuators)!=1:raise ValueError('unsupported control source bindings')
    session=materialize(artifact,execution,source=source,manifest=manifest)
    session._control_binding=binding
    return session


def validate_target(session,target):
    if not isinstance(target, CanonicalControlTarget):raise TypeError("CanonicalControlTarget required")
    session._require_reset()
    if not hasattr(session,'_control_binding'):raise ValueError('control session admission required')
    if (target.task_artifact_hash!=session._artifact.identity_hash or set(target.arm_joint_order)!=set(session._target_actuators)
        or target.gripper.semantic_id!=session._control_binding.gripper_semantic_id):raise ValueError('canonical control binding mismatch')


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
    # Both supported sources bind positive native actuator force to opening.
    return CanonicalControlFeedback('canonical-control-feedback-v0', state.control_step,
        state.simulation_time, CanonicalGripperFeedback(session._control_binding.gripper_semantic_id,
        max(0., float(sum(state.joint_position[n] for n in FINGERS))), max(0., -float(native_force))))
