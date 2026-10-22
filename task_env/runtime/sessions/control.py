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
    controller_profile=None,
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
    if controller_profile is not None:
        from ...controllers.canonical.position_profile import (
            PandaPositionServoProfileV1,
        )
        profiles = tuple(controller_profile) if isinstance(controller_profile, (tuple, list)) else (controller_profile,)
        if (not profiles or len(profiles) > 2
                or any(not isinstance(profile, PandaPositionServoProfileV1) for profile in profiles)):
            raise TypeError('unsupported explicit Controller profile set')
        if execution.physics_provider not in {'geophys', 'mujoco'} or execution.backend != 'cpu':
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
        if dict(source.joint_targets) != expected_targets or set(source.open_actuators) != set(expected_open):
            raise ValueError('PositionServoV1 source actuator mapping differs from its bound plan')
        if binding.gripper_semantic_id != profiles[0].gripper_semantic_id:
            raise ValueError('PositionServoV1 gripper semantic binding mismatch')
    else:
        profiles = ()
        if len(source.joint_targets)!=7 or len(source.open_actuators)!=1:
            raise ValueError('unsupported control source bindings')
    materialization_authority = None
    if len(profiles) == 2:
        from .api import _DUAL_POSITION_MATERIALIZATION_AUTHORITY

        materialization_authority = _DUAL_POSITION_MATERIALIZATION_AUTHORITY
    session=materialize(
        artifact, execution, source=source, manifest=manifest,
        _materialization_authority=materialization_authority,
    )
    session._control_binding=binding
    if controller_binding_plan is not None:
        force_required = any(
            item.field_name == 'actuator_force' and item.requiredness == 'required'
            for controller_binding in controller_binding_plan.controller_bindings
            for item in controller_binding.feedback_requirements.requirements
        )
        # No-plan compatibility keeps the historical measured-force cache.
        session._force_feedback_required = force_required
        session._control_binding_plan = controller_binding_plan
    else:
        session._force_feedback_required = True
        session._control_binding_plan = None
    if profiles:
        session._position_profiles_by_writer = {profile.writer_id: profile for profile in profiles}
        session._position_profile_identities = {profile.writer_id: profile.identity for profile in profiles}
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


def validate_target(session,target):
    if not isinstance(target, CanonicalControlTarget):raise TypeError("CanonicalControlTarget required")
    session._require_reset()
    if not hasattr(session,'_control_binding'):raise ValueError('control session admission required')
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
    # Both supported sources bind positive native actuator force to opening.
    return CanonicalControlFeedback('canonical-control-feedback-v0', state.control_step,
        state.simulation_time, CanonicalGripperFeedback(session._control_binding.gripper_semantic_id,
        max(0., float(sum(state.joint_position[n] for n in FINGERS))), max(0., -float(native_force))))


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
    activation = candidate_profile._prepare_switch_activation(publication, plan)
    replacement_profiles = dict(admitted)
    replacement_profiles[candidate_profile.writer_id] = candidate_profile
    replacement_identities = dict(getattr(session, '_position_profile_identities', {}))
    replacement_identities[candidate_profile.writer_id] = candidate_profile.identity
    return {
        'current_profile': current_profile,
        'candidate_profile': candidate_profile,
        'activation': activation,
        'profiles_by_writer': replacement_profiles,
        'profile_identities': replacement_identities,
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
        session._position_profile_identity,
        session._position_profile_id,
        session._position_writer_id,
    ) = (
        prepared['profiles_by_writer'],
        prepared['profile_identities'],
        prepared['profile_identity'],
        prepared['profile_id'],
        prepared['writer_id'],
    )


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
    """Validate a source-bound position target, then lower it once via the existing session."""
    from ...controllers.canonical.contracts import PositionControlTargetV1

    if not isinstance(target, PositionControlTargetV1):
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
    consumed = session._position_applied_boundary_ids
    consumed_key = (controller_profile.writer_id, boundary.boundary_id)
    if consumed_key in consumed:
        raise ValueError('position target for this state boundary was already applied')
    # Close the same-boundary replay window before crossing into the Provider.
    consumed.add(consumed_key)
    session._position_target_in_flight = target.target.identity_hash
    try:
        acknowledgement = session.apply_control(target.target)
    finally:
        session._position_target_in_flight = None
    if acknowledgement.target_hash != target.target.identity_hash:
        raise ValueError('Provider acknowledgement does not match the applied canonical target')
    return acknowledgement


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
    prepared = prepare_structured_action(plan, request)
    if isinstance(controller_profile, (tuple, list)):
        profiles = tuple(controller_profile)
        if len(profiles) != 2 or any(not hasattr(item, 'controller_binding') for item in profiles):
            raise ValueError('bounded dual-Entity Position dispatch requires exactly two profile instances')
        by_writer = {profile.writer_id: profile for profile in profiles}
        if len(by_writer) != 2 or tuple(writer for writer, _action in prepared) != tuple(sorted(by_writer)):
            raise ValueError('complete structured request does not match the admitted Position writers')
        if {binding.writer_id for binding in plan.controller_bindings} != set(by_writer):
            raise ValueError('Position profile set does not exactly match the ControlBindingPlan')
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
        applied = []
        for profile, canonical, target in computed:
            acknowledgement = apply_position_control_target(
                session, target, controller_profile=profile, plan=plan,
                publication=publication, scene=scene, joint_bindings=joint_bindings,
                frame_bindings=frame_bindings,
            )
            applied.append((canonical, target, acknowledgement))
        state = session.step()
        next_publication = session.snapshot_v1(
            scene=scene, joint_bindings=joint_bindings, frame_bindings=frame_bindings,
            requirements=requirements or profiles[0].requirements,
        )
        return tuple(applied), state, next_publication
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
