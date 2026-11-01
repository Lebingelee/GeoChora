"""Four immutable semantic control layers, independent of native storage."""
from collections.abc import Mapping
from dataclasses import dataclass
import math
import hashlib,json
from ...artifacts.contracts import Contract,PoseWorld,_name
from ...artifacts.state import StateBoundaryIdentity,StateSampleClock


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


CANONICAL_PANDA_ARM_ORDER_V1 = tuple(f'panda-v1/joint{i}' for i in range(1, 8))


@dataclass(frozen=True)
class RequestedAction(Contract):
    mode: str
    reference: str | None
    rotation_representation: str
    values: tuple[float,...]

    def validate(self):
        allowed={'absolute_joint':{None},'absolute_pose':{'world','base'},'delta_pose':{'world','base','ee'}}
        if self.mode not in allowed or self.reference not in allowed[self.mode]:raise ValueError('invalid action mode/reference')
        if self.rotation_representation not in ({'none'} if self.mode=='absolute_joint' else {'quaternion_wxyz','rotvec'}):raise ValueError('invalid rotation')
        size=8 if self.mode=='absolute_joint' or self.rotation_representation=='quaternion_wxyz' else 7
        if len(self.values)!=size:raise ValueError('invalid action shape')
        if any(not math.isfinite(value) for value in self.values):raise ValueError('action values must be finite')


@dataclass(frozen=True)
class CanonicalAction(Contract):
    schema_version: str
    requested: RequestedAction
    interpreted_values: tuple[float,...]
    clipped: bool
    resolved_world_pose: PoseWorld | None

    def validate(self):
        if self.schema_version!='canonical-action-v0' or len(self.interpreted_values)!=len(self.requested.values):raise ValueError('invalid canonical action')
        if any(not math.isfinite(value) for value in self.interpreted_values):raise ValueError('canonical action values must be finite')
        if not -1<=self.interpreted_values[-1]<=1:raise ValueError('invalid gripper scalar')
        if (self.requested.mode=='absolute_joint') != (self.resolved_world_pose is None):raise ValueError('pose interpretation mismatch')


@dataclass(frozen=True)
class CanonicalArmReferenceV1(Contract):
    """One provider-neutral R3 arm target without a gripper feedback contract."""

    schema_version: str
    controller_identity: str
    canonical_action: CanonicalAction
    arm_joint_order: tuple[str, ...]
    arm_position: Mapping[str, float]

    def validate(self):
        if self.schema_version != 'canonical-arm-reference-v1':
            raise ValueError('unsupported canonical arm-reference schema')
        if (len(self.controller_identity) != 64
                or any(character not in '0123456789abcdef' for character in self.controller_identity)):
            raise ValueError('canonical arm reference requires a controller identity hash')
        self.canonical_action.validate()
        if (len(self.arm_joint_order) != 7
                or len(set(self.arm_joint_order)) != 7
                or set(self.arm_joint_order) != set(self.arm_position)):
            raise ValueError('canonical arm reference requires seven ordered Panda joints')
        for name in self.arm_joint_order:
            _name(name)
        if any(not math.isfinite(float(value)) for value in self.arm_position.values()):
            raise ValueError('canonical arm reference positions must be finite')
@dataclass(frozen=True)
class CanonicalArmTargetV1(Contract):
    """Versioned world-pose resolution from the shared Panda arm owner."""

    schema_version: str
    source_xml_sha256: str
    controller_identity: str
    canonical_action: CanonicalAction
    arm_joint_order: tuple[str, ...]
    joint_position_rad: tuple[float, ...]
    servo_position_rad: tuple[float, ...]

    def validate(self):
        import re
        if self.schema_version != 'canonical-arm-target-v1':
            raise ValueError('unsupported canonical arm target schema')
        if re.fullmatch(r'[0-9a-f]{64}', self.source_xml_sha256) is None:
            raise ValueError('canonical arm target requires a source XML SHA-256')
        if type(self.controller_identity) is not str or not self.controller_identity:
            raise ValueError('canonical arm target requires a Controller identity')
        if not isinstance(self.canonical_action, CanonicalAction):
            raise TypeError('canonical arm target requires the existing CanonicalAction')
        self.canonical_action.validate()
        requested = self.canonical_action.requested
        if (requested.mode != 'absolute_pose' or requested.reference != 'world'
                or requested.rotation_representation != 'quaternion_wxyz'):
            raise ValueError('canonical arm target requires an absolute world pose in quaternion_wxyz')
        if (type(self.arm_joint_order) is not tuple
                or self.arm_joint_order != CANONICAL_PANDA_ARM_ORDER_V1
                or len(self.joint_position_rad) != 7 or len(self.servo_position_rad) != 7):
            raise ValueError('canonical arm target requires the canonical named Panda joint order and seven values')
        for name in self.arm_joint_order:
            _name(name)
        if any(not math.isfinite(float(value)) for value in (*self.joint_position_rad, *self.servo_position_rad)):
            raise ValueError('canonical arm target values must be finite')


@dataclass(frozen=True)
class CanonicalArmResolutionDiagnosticsV1(Contract):
    """Measured residual and bounded-work receipt for iterative IK resolution."""

    schema_version: str
    method_id: str
    iteration_count: int
    max_iterations: int
    position_residual_m: float
    orientation_residual_rad: float
    position_tolerance_m: float
    orientation_tolerance_rad: float
    converged: bool
    initial_position_gap_m: float
    initial_orientation_gap_rad: float
    model_position_tolerance_m: float
    model_orientation_tolerance_rad: float

    def validate(self):
        if (self.schema_version != 'canonical-arm-resolution-diagnostics-v1'
                or self.method_id != 'shared_canonical_dls_iterative_v1'):
            raise ValueError('unsupported canonical arm resolution diagnostics')
        if (type(self.iteration_count) is not int or self.iteration_count < 1
                or type(self.max_iterations) is not int
                or self.max_iterations < self.iteration_count):
            raise ValueError('canonical arm resolution iteration count must fit its positive bound')
        numbers = (self.position_residual_m, self.orientation_residual_rad,
                   self.position_tolerance_m, self.orientation_tolerance_rad,
                   self.initial_position_gap_m, self.initial_orientation_gap_rad,
                   self.model_position_tolerance_m, self.model_orientation_tolerance_rad)
        if (any(isinstance(value, bool) or not math.isfinite(float(value)) for value in numbers)
                or self.position_residual_m < 0.0 or self.orientation_residual_rad < 0.0
                or self.initial_position_gap_m < 0.0 or self.initial_orientation_gap_rad < 0.0
                or self.position_tolerance_m <= 0.0 or self.orientation_tolerance_rad <= 0.0
                or self.model_position_tolerance_m <= 0.0
                or self.model_orientation_tolerance_rad <= 0.0
                or type(self.converged) is not bool):
            raise ValueError('canonical arm resolution diagnostics contain invalid values')
        if self.converged and (self.position_residual_m > self.position_tolerance_m
                               or self.orientation_residual_rad > self.orientation_tolerance_rad):
            raise ValueError('converged canonical arm resolution exceeds its declared tolerance')
        if (self.initial_position_gap_m > self.model_position_tolerance_m
                or self.initial_orientation_gap_rad > self.model_orientation_tolerance_rad):
            raise ValueError('initial public pose differs from the pinned model beyond its declared gate')


@dataclass(frozen=True)
class CanonicalArmResolutionV1(Contract):
    """Advanced result combining the existing arm target with FK residual evidence."""

    schema_version: str
    target: CanonicalArmTargetV1
    diagnostics: CanonicalArmResolutionDiagnosticsV1

    def validate(self):
        if self.schema_version != 'canonical-arm-resolution-v1':
            raise ValueError('unsupported canonical arm resolution schema')
        if not isinstance(self.target, CanonicalArmTargetV1):
            raise TypeError('canonical arm resolution requires the existing typed arm target')
        if not isinstance(self.diagnostics, CanonicalArmResolutionDiagnosticsV1):
            raise TypeError('canonical arm resolution requires typed convergence diagnostics')
        self.target.validate()
        self.diagnostics.validate()


@dataclass(frozen=True)
class GripperControlTarget(Contract):
    semantic_id: str
    opening_m: float
    force_limit_N: float
    servo_opening_m: float

    def validate(self):
        _name(self.semantic_id)
        if not all(math.isfinite(value) for value in (self.opening_m,self.force_limit_N,self.servo_opening_m)):raise ValueError('gripper target values must be finite')
        if not 0<=self.opening_m<=.08 or not 0<=self.servo_opening_m<=.08 or self.force_limit_N<=0:raise ValueError('invalid physical gripper target')


@dataclass(frozen=True)
class CanonicalControlTarget(Contract):
    schema_version: str
    task_artifact_hash: str
    controller_identity: str
    arm_joint_order: tuple[str,...]
    arm_position: Mapping[str,float]
    arm_servo_position: Mapping[str,float]
    gripper: GripperControlTarget

    def validate(self):
        if self.schema_version!='canonical-control-v0' or len(self.task_artifact_hash)!=64:raise ValueError('invalid control schema/link')
        if len(self.arm_joint_order)!=7 or len(set(self.arm_joint_order))!=7 or set(self.arm_joint_order)!=set(self.arm_position) or set(self.arm_position)!=set(self.arm_servo_position):raise ValueError('seven semantic arm joints required')
        for name in self.arm_joint_order:_name(name)
        if any(not math.isfinite(value) for mapping in (self.arm_position,self.arm_servo_position) for value in mapping.values()):raise ValueError('control target positions must be finite')

    @property
    def identity_hash(self):return digest(self.to_mapping())


@dataclass(frozen=True)
class PositionControlTargetV1(Contract):
    """Canonical position target bound to one writer, plan, and source boundary."""

    schema_version: str
    writer_id: str
    controller_identity: str
    binding_identity_hash: str
    source_closure_digest: str
    source_boundary: StateBoundaryIdentity
    sample_clock: StateSampleClock
    target: CanonicalControlTarget

    def validate(self):
        import re
        if self.schema_version != 'position-control-target-v1':
            raise ValueError('unsupported position control target schema')
        _name(self.writer_id)
        for value in (self.controller_identity,self.binding_identity_hash,self.source_closure_digest):
            if not re.fullmatch(r'[0-9a-f]{64}',value):
                raise ValueError('position control target requires SHA-256 identities')
        if not isinstance(self.source_boundary,StateBoundaryIdentity) or not isinstance(self.sample_clock,StateSampleClock):
            raise TypeError('position target requires typed source boundary and sample clock')
        if not isinstance(self.target,CanonicalControlTarget):
            raise TypeError('position target requires the existing canonical control target')
        self.source_boundary.validate()
        self.sample_clock.validate()
        self.target.validate()
        if (self.target.controller_identity != self.controller_identity
                or self.target.task_artifact_hash == ''):
            raise ValueError('position target Controller/Artifact identity mismatch')
        if self.source_boundary.scene_identity_hash == '' or (
            self.sample_clock.clock_domain != 'evaluation_boundary'
            or self.sample_clock.sample_index != self.source_boundary.control_step
        ):
            raise ValueError('position target source boundary and evaluation clock disagree')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class AppliedCanonicalControl(Contract):
    schema_version: str
    target_hash: str
    provider_name: str
    arm_servo_position: Mapping[str,float]
    gripper_servo_opening_m: float
    gripper_force_limit_N: float
    clipped: bool
    mapping: str

    def validate(self):
        if self.schema_version!='applied-canonical-control-v0' or len(self.target_hash)!=64:raise ValueError('invalid applied schema')
        for name in self.arm_servo_position:_name(name)
        if any(not math.isfinite(value) for value in (*self.arm_servo_position.values(),self.gripper_servo_opening_m,self.gripper_force_limit_N)):raise ValueError('applied control values must be finite')
        if self.gripper_force_limit_N<=0 or not 0<=self.gripper_servo_opening_m<=.08:raise ValueError('invalid applied gripper')


@dataclass(frozen=True)
class MixedActuatorTargetV1(Contract):
    """Named mixed actuator values bound to one Selected Runtime boundary."""

    schema_version: str
    task_artifact_hash: str
    source_id: str
    source_closure_digest: str
    controller_identity: str
    provider_materialization_id: str
    episode_id: str
    reset_sample_id: str
    control_step: int
    state_revision: int
    simulation_time_s: float
    joint_torque_Nm: Mapping[str, float]
    finger_position_m: Mapping[str, float]

    def validate(self):
        import re
        if self.schema_version != 'mixed-actuator-target-v1':
            raise ValueError('unsupported mixed actuator target schema')
        for name in ('task_artifact_hash', 'source_closure_digest'):
            if type(getattr(self, name)) is not str or re.fullmatch(r'[0-9a-f]{64}', getattr(self, name)) is None:
                raise ValueError(f'{name} must be a lowercase SHA-256')
        for name in ('source_id', 'controller_identity', 'provider_materialization_id',
                     'episode_id', 'reset_sample_id'):
            if type(getattr(self, name)) is not str or not getattr(self, name).strip():
                raise ValueError(f'{name} must be nonempty')
        if (type(self.control_step) is not int or self.control_step < 0
                or type(self.state_revision) is not int or self.state_revision < 0
                or not math.isfinite(float(self.simulation_time_s)) or self.simulation_time_s < 0):
            raise ValueError('mixed actuator target boundary is invalid')
        torques = dict(self.joint_torque_Nm)
        positions = dict(self.finger_position_m)
        if not torques or not positions or set(torques) & set(positions):
            raise ValueError('mixed actuator target requires disjoint named torque and position channels')
        if any(type(name) is not str or not name.strip() for name in (*torques, *positions)):
            raise ValueError('mixed actuator target names must be nonempty')
        if any(not math.isfinite(float(value)) for value in (*torques.values(), *positions.values())):
            raise ValueError('mixed actuator target values must be finite')
        object.__setattr__(self, 'simulation_time_s', float(self.simulation_time_s))

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class AppliedMixedActuatorV1(Contract):
    """Named source actuator acknowledgement; native slots remain private."""

    schema_version: str
    target_hash: str
    provider_name: str
    joint_torque_Nm: Mapping[str, float]
    finger_position_m: Mapping[str, float]
    clipped: bool
    mapping: str

    def validate(self):
        if self.schema_version != 'applied-mixed-actuator-v1':
            raise ValueError('unsupported mixed actuator acknowledgement schema')
        if not isinstance(self.target_hash, str) or len(self.target_hash) != 64:
            raise ValueError('mixed actuator acknowledgement requires its target hash')
        if not isinstance(self.provider_name, str) or not self.provider_name.strip():
            raise ValueError('mixed actuator acknowledgement requires provider identity')
        if type(self.clipped) is not bool or not isinstance(self.mapping, str) or not self.mapping.strip():
            raise ValueError('mixed actuator acknowledgement mapping is invalid')
        for mapping in (self.joint_torque_Nm, self.finger_position_m):
            if any(not isinstance(name, str) or not name.strip() or not math.isfinite(float(value))
                   for name, value in mapping.items()):
                raise ValueError('mixed actuator acknowledgement values must be finite and named')


@dataclass(frozen=True)
class MixedActuatorChannelV1(Contract):
    """One source-bound scalar channel in a bounded mixed-control plan."""

    semantic_id: str
    actuator_name: str
    joint_name: str
    drive_mode: str
    unit: str
    control_range: tuple[float, float]
    hold_policy: str = 'zero_order_hold_per_control_interval_v1'

    def validate(self):
        for name in (self.semantic_id, self.actuator_name, self.joint_name):
            if type(name) is not str or not name.strip():
                raise ValueError('mixed-control channel names must be nonempty strings')
        if (self.drive_mode, self.unit) not in {
            ('joint_torque', 'N*m'), ('joint_position', 'rad'),
            ('joint_position', 'm'),
        }:
            raise ValueError('mixed-control channel drive mode and unit are unsupported')
        if self.hold_policy != 'zero_order_hold_per_control_interval_v1':
            raise ValueError('mixed-control channel hold policy is unsupported')
        if (not isinstance(self.control_range, (tuple, list)) or len(self.control_range) != 2
                or any(not math.isfinite(float(value)) for value in self.control_range)
                or float(self.control_range[0]) > float(self.control_range[1])):
            raise ValueError('mixed-control channel requires a finite ordered control range')
        object.__setattr__(self, 'control_range', tuple(float(value) for value in self.control_range))


@dataclass(frozen=True)
class MixedActuatorPlanV1(Contract):
    """Typed source-bound admission for named mixed actuator control.

    It carries declarations only. Provider adapters still resolve names and
    verify transmission, native drive metadata, units, and limits after compile.
    """

    schema_version: str
    task_artifact_hash: str
    source_id: str
    source_closure_digest: str
    controller_identity: str
    channels: tuple[MixedActuatorChannelV1, ...]

    def validate(self):
        import re
        for name in ('task_artifact_hash', 'source_closure_digest', 'controller_identity'):
            if type(getattr(self, name)) is not str or re.fullmatch(r'[0-9a-f]{64}', getattr(self, name)) is None:
                raise ValueError(f'mixed-control {name} must be a lowercase SHA-256')
        if self.schema_version != 'mixed-actuator-plan-v1':
            raise ValueError('unsupported mixed actuator plan schema')
        if type(self.source_id) is not str or not self.source_id.strip():
            raise ValueError('mixed actuator plan requires a source identity')
        channels = tuple(self.channels)
        if not channels or any(type(channel) is not MixedActuatorChannelV1 for channel in channels):
            raise TypeError('mixed actuator plan requires typed channel declarations')
        for channel in channels:
            channel.validate()
        names = [channel.semantic_id for channel in channels]
        actuators = [channel.actuator_name for channel in channels]
        if len(names) != len(set(names)) or len(actuators) != len(set(actuators)):
            raise ValueError('mixed actuator plan channel and actuator writers must be unique')
        object.__setattr__(self, 'channels', tuple(sorted(channels, key=lambda item: item.semantic_id)))

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class MixedActuatorCommandV1(Contract):
    """Generic named actuator values bound to one selected runtime boundary."""

    schema_version: str
    plan_identity_hash: str
    task_artifact_hash: str
    source_id: str
    source_closure_digest: str
    controller_identity: str
    provider_materialization_id: str
    episode_id: str
    reset_sample_id: str
    control_step: int
    state_revision: int
    simulation_time_s: float
    channel_values: Mapping[str, float]
    channel_units: Mapping[str, str]

    def validate(self):
        import re
        if self.schema_version != 'mixed-actuator-command-v1':
            raise ValueError('unsupported mixed actuator command schema')
        for name in ('plan_identity_hash', 'task_artifact_hash', 'source_closure_digest', 'controller_identity'):
            if type(getattr(self, name)) is not str or re.fullmatch(r'[0-9a-f]{64}', getattr(self, name)) is None:
                raise ValueError(f'mixed actuator command {name} must be a lowercase SHA-256')
        for name in ('source_id', 'provider_materialization_id', 'episode_id', 'reset_sample_id'):
            if type(getattr(self, name)) is not str or not getattr(self, name).strip():
                raise ValueError(f'mixed actuator command {name} must be nonempty')
        if (type(self.control_step) is not int or self.control_step < 0
                or type(self.state_revision) is not int or self.state_revision < 0
                or not math.isfinite(float(self.simulation_time_s)) or self.simulation_time_s < 0):
            raise ValueError('mixed actuator command boundary is invalid')
        values, units = dict(self.channel_values), dict(self.channel_units)
        if not values or set(values) != set(units):
            raise ValueError('mixed actuator command values and units must cover the same channels')
        if any(type(name) is not str or not name.strip() for name in values):
            raise ValueError('mixed actuator command channel names must be nonempty')
        if any(not math.isfinite(float(value)) for value in values.values()):
            raise ValueError('mixed actuator command values must be finite')
        if any(unit not in {'N*m', 'rad', 'm'} for unit in units.values()):
            raise ValueError('mixed actuator command units are unsupported')
        object.__setattr__(self, 'simulation_time_s', float(self.simulation_time_s))

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


@dataclass(frozen=True)
class AppliedMixedActuatorCommandV1(Contract):
    """Provider acknowledgement for a completely preflighted mixed command."""

    schema_version: str
    target_hash: str
    provider_name: str
    channel_values: Mapping[str, float]
    channel_units: Mapping[str, str]
    clipped: bool
    mapping: str

    def validate(self):
        import re
        if (self.schema_version != 'applied-mixed-actuator-command-v1'
                or type(self.target_hash) is not str or re.fullmatch(r'[0-9a-f]{64}', self.target_hash) is None):
            raise ValueError('invalid applied mixed actuator command identity')
        if type(self.provider_name) is not str or not self.provider_name.strip():
            raise ValueError('applied mixed actuator command requires provider identity')
        values, units = dict(self.channel_values), dict(self.channel_units)
        if not values or set(values) != set(units):
            raise ValueError('applied mixed actuator values and units must cover the same channels')
        if any(not math.isfinite(float(value)) for value in values.values()):
            raise ValueError('applied mixed actuator values must be finite')
        if type(self.clipped) is not bool or type(self.mapping) is not str or not self.mapping.strip():
            raise ValueError('applied mixed actuator receipt metadata is invalid')


@dataclass(frozen=True)
class ControlGroupActionV1(Contract):
    """One entity/group slice of a complete, statically bound action request."""

    schema_version: str
    entity_id: str
    group_id: str
    action_schema_id: str
    values: tuple[float,...]

    def validate(self):
        if self.schema_version!='control-group-action-v1':raise ValueError('unsupported ControlGroup action schema')
        for name in (self.entity_id,self.group_id,self.action_schema_id):_name(name)
        if not self.values or any(not math.isfinite(value) for value in self.values):raise ValueError('ControlGroup action must be a nonempty finite vector')


@dataclass(frozen=True)
class StructuredActionRequestV1(Contract):
    """Complete action input; it is data only and cannot mutate a controller/runtime."""

    schema_version: str
    scene_identity_hash: str
    binding_identity_hash: str
    groups: tuple[ControlGroupActionV1,...]

    def validate(self):
        if self.schema_version!='structured-action-request-v1':raise ValueError('unsupported structured action request schema')
        for value in (self.scene_identity_hash,self.binding_identity_hash):
            if len(value)!=64 or any(char not in '0123456789abcdef' for char in value):raise ValueError('structured action requires Scene and binding SHA-256 identities')
        if not self.groups:raise ValueError('structured action requires all bound ControlGroups')
        keys=tuple((group.entity_id,group.group_id) for group in self.groups)
        if len(keys)!=len(set(keys)):raise ValueError('duplicate entity-qualified ControlGroup action')
        object.__setattr__(self,'groups',tuple(sorted(self.groups,key=lambda group:(group.entity_id,group.group_id))))
