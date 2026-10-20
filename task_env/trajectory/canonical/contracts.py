"""Strict additive semantic trajectory. Historical H5 v2 remains unchanged."""
from collections.abc import Mapping
from dataclasses import dataclass
import math,re
from ...artifacts.contracts import Contract,CanonicalStateView,ExecutionSpec,Timebase
from ...artifacts.execution import ResetSample,RealizedInitialState
from ...controllers.canonical.contracts import RequestedAction,CanonicalAction,CanonicalControlTarget,AppliedCanonicalControl,digest
from ...controllers.canonical.feedback import CanonicalControlFeedback
from ...controllers.canonical.readiness import CanonicalControlReadiness
from ...controllers.canonical.kinematics import ARM,FINGERS
from .episode import BoundaryEventV1,EpisodeOutcomeV1,StructuredControlTransitionV1,validate_episode_records


def require_hash(value):
    if not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('64-hex identity required')


@dataclass(frozen=True)
class EpisodeMetadata(Contract):
    schema_version: str
    task_artifact_hash: str
    reset_sample: ResetSample
    realized_initial_state: RealizedInitialState
    execution: ExecutionSpec
    provider_provenance: Mapping[str,str]
    source_provenance: Mapping[str,str]
    timebase: Timebase
    controller_identity: str
    expert_identity: str
    readiness_identity: str
    control_contract_identity: str
    task_seed: int
    sample_role: str

    def validate(self):
        if self.schema_version!='canonical-trajectory-metadata-v0' or self.sample_role not in {'train','validation','evaluation','regression'}:raise ValueError('invalid episode metadata')
        for value in (self.task_artifact_hash,self.controller_identity,self.expert_identity,self.readiness_identity,self.control_contract_identity):require_hash(value)
        if self.task_artifact_hash!=self.reset_sample.task_artifact_hash or self.task_seed!=self.reset_sample.task_seed:raise ValueError('reset identity mismatch')
        if self.realized_initial_state.reset_sample_id!=self.reset_sample.sample_id or self.realized_initial_state.provider_name!=self.execution.physics_provider:raise ValueError('realized/provider identity mismatch')
        if not self.provider_provenance or not self.source_provenance:raise ValueError('provenance required')


@dataclass(frozen=True)
class BoundaryRecord(Contract):
    control_step: int
    simulation_time: float
    state: CanonicalStateView
    feedback: CanonicalControlFeedback
    readiness: CanonicalControlReadiness
    task_metrics: Mapping[str,float]
    is_success: bool
    task_failure: bool

    def validate(self):
        if self.control_step!=self.state.control_step or self.simulation_time!=self.state.simulation_time:raise ValueError('state boundary mismatch')
        self.feedback.require_state(self.state,self.readiness.gripper.semantic_id,FINGERS)
        self.readiness.require_boundary(self.control_step,self.simulation_time)


@dataclass(frozen=True)
class TransitionRecord(Contract):
    requested_action: RequestedAction
    canonical_action: CanonicalAction
    controller_target: CanonicalControlTarget
    applied_control: AppliedCanonicalControl
    reward: float
    terminated: bool
    truncated: bool
    expert_stage: str
    expert_diagnostics: Mapping[str,str]
    planned_action: bool
    readiness_hold: bool

    def validate(self):
        if self.canonical_action.requested!=self.requested_action:raise ValueError('requested/canonical linkage mismatch')
        if self.applied_control.target_hash!=self.controller_target.identity_hash:raise ValueError('target hash mismatch')
        if self.planned_action==self.readiness_hold:raise ValueError('exactly one planned/hold provenance required')


@dataclass(frozen=True)
class CanonicalTrajectory(Contract):
    schema_version: str
    metadata: EpisodeMetadata
    boundaries: tuple[BoundaryRecord,...]
    transitions: tuple[TransitionRecord,...]
    stop_reason: str

    def validate(self):
        if self.schema_version!='canonical-trajectory-v0':raise ValueError('unsupported trajectory schema')
        if len(self.boundaries)!=len(self.transitions)+1:raise ValueError('T+1/T invariant')
        if self.boundaries[0].state!=self.metadata.realized_initial_state.measured_state:raise ValueError('reset must be measured first boundary')
        if self.boundaries[0].control_step!=0 or self.boundaries[0].simulation_time!=0.:raise ValueError('initial timebase mismatch')
        names=set(self.boundaries[0].state.joint_position);poses=set(self.boundaries[0].state.pose_world)
        for i,transition in enumerate(self.transitions):
            a,b=self.boundaries[i:i+2];target=transition.controller_target
            if b.control_step!=a.control_step+1:raise ValueError('skipped/duplicate control boundary')
            dt=b.simulation_time-a.simulation_time
            if abs(dt-self.metadata.timebase.control_dt)>max(math.ulp(a.simulation_time),math.ulp(b.simulation_time),math.ulp(self.metadata.timebase.control_dt)):raise ValueError('timebase mismatch')
            if set(b.state.joint_position)!=names or set(b.state.pose_world)!=poses:raise ValueError('semantic state fields changed')
            if target.arm_joint_order!=ARM or target.task_artifact_hash!=self.metadata.task_artifact_hash or target.controller_identity!=self.metadata.controller_identity:raise ValueError('target identity/order mismatch')
            if transition.applied_control.provider_name!=self.metadata.execution.physics_provider:raise ValueError('applied provider mismatch')
            if i<len(self.transitions)-1 and (transition.terminated or transition.truncated):raise ValueError('transition after terminal')

    @property
    def identity_hash(self):return digest(self.to_mapping())

    @property
    def hold_count(self):return sum(t.readiness_hold for t in self.transitions)


@dataclass(frozen=True)
class CanonicalTrajectoryV1(Contract):
    """Versioned structured-control/events/outcome extension of canonical v0."""

    schema_version: str
    metadata: EpisodeMetadata
    boundaries: tuple[BoundaryRecord,...]
    transitions: tuple[TransitionRecord,...]
    structured_controls: tuple[StructuredControlTransitionV1,...]
    events: tuple[BoundaryEventV1,...]
    outcome: EpisodeOutcomeV1
    stop_reason: str

    def validate(self):
        if self.schema_version!='canonical-trajectory-v1':raise ValueError('unsupported canonical trajectory v1 schema')
        CanonicalTrajectory('canonical-trajectory-v0',self.metadata,self.boundaries,self.transitions,self.stop_reason).validate()
        if len(self.structured_controls)!=len(self.transitions):raise ValueError('structured control T alignment')
        validate_episode_records(self.events,self.outcome,len(self.transitions))
        if self.outcome.end_reason!=self.stop_reason:raise ValueError('outcome/stop reason mismatch')
        for control,transition in zip(self.structured_controls,self.transitions,strict=True):
            if len(control.writer_controls)!=1:raise ValueError('canonical Panda trajectory requires one existing controller writer')
            writer=control.writer_controls[0]
            if RequestedAction.from_mapping(writer['requested_action'])!=transition.requested_action:raise ValueError('structured/canonical requested action mismatch')
            if CanonicalAction.from_mapping(writer['canonical_action'])!=transition.canonical_action:raise ValueError('structured/canonical action mismatch')
            target=writer['controller_target']
            applied=writer['applied_control']
            if target['identity_hash']!=transition.controller_target.identity_hash or CanonicalControlTarget.from_mapping(target['payload'])!=transition.controller_target:raise ValueError('structured/canonical target mismatch')
            if applied['target_hash']!=transition.applied_control.target_hash or AppliedCanonicalControl.from_mapping(applied['payload'])!=transition.applied_control:raise ValueError('structured/canonical applied control mismatch')

    @property
    def identity_hash(self):return digest(self.to_mapping())

    @property
    def hold_count(self):return sum(t.readiness_hold for t in self.transitions)


class CanonicalRecorder:
    """Record reset first, append one transition/post-boundary, freeze once."""
    def __init__(self,metadata,initial,*,schema_version='canonical-trajectory-v0'):
        if schema_version not in {'canonical-trajectory-v0','canonical-trajectory-v1'}:raise ValueError('unsupported canonical recorder schema')
        self.schema_version=schema_version;self.metadata=metadata;self.boundaries=[initial];self.transitions=[];self.structured_controls=[];self.events=[];self._frozen=False
    def append(self,transition,boundary,*,structured_control=None):
        if self._frozen:raise RuntimeError('recorder frozen')
        if boundary.control_step!=self.boundaries[-1].control_step+1:raise ValueError('append alignment')
        if self.schema_version=='canonical-trajectory-v0' and structured_control is not None:raise ValueError('structured control requires canonical trajectory v1')
        if self.schema_version=='canonical-trajectory-v1' and structured_control is None:raise ValueError('canonical trajectory v1 requires structured control for every transition')
        if structured_control is not None and not isinstance(structured_control,StructuredControlTransitionV1):raise TypeError('structured_control must be StructuredControlTransitionV1')
        self.transitions.append(transition);self.boundaries.append(boundary);self.structured_controls.append(structured_control)
    def add_event(self,event):
        if self._frozen:raise RuntimeError('recorder frozen')
        if self.schema_version!='canonical-trajectory-v1':raise ValueError('BoundaryEvent requires canonical trajectory v1')
        if not isinstance(event,BoundaryEventV1) or event.boundary_index!=len(self.transitions):raise ValueError('event must reference a current canonical boundary')
        same=[value for value in self.events if value.boundary_index==event.boundary_index]
        if event.event_sequence!=len(same):raise ValueError('boundary event sequence')
        self.events.append(event)
    def freeze(self,stop_reason,*,outcome=None):
        if self.schema_version=='canonical-trajectory-v0':
            if outcome is not None or self.events:raise ValueError('events/outcome require canonical trajectory v1')
            value=CanonicalTrajectory('canonical-trajectory-v0',self.metadata,tuple(self.boundaries),tuple(self.transitions),stop_reason)
        else:
            if not isinstance(outcome,EpisodeOutcomeV1):raise ValueError('canonical trajectory v1 requires EpisodeOutcomeV1')
            if outcome.end_reason!=stop_reason:raise ValueError('outcome/stop reason mismatch')
            value=CanonicalTrajectoryV1('canonical-trajectory-v1',self.metadata,tuple(self.boundaries),tuple(self.transitions),tuple(self.structured_controls),tuple(self.events),outcome,stop_reason)
        self._frozen=True;return value
