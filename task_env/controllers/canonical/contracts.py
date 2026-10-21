"""Four immutable semantic control layers, independent of native storage."""
from collections.abc import Mapping
from dataclasses import dataclass
import math
import hashlib,json
from ...artifacts.contracts import Contract,PoseWorld,_name
from ...artifacts.state import StateBoundaryIdentity,StateSampleClock


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


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
