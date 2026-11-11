"""Admitted legacy native-feedback source and Controller ownership.

This binding is installed after the existing scalar/native-feedback admission.
It does not turn a legacy Artifact into a SceneDefinition or grant admission.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json


@dataclass(frozen=True)
class LegacyNativeFeedbackBindingV1:
    source_id: str
    source_closure_sha256: str
    artifact_sha256: str
    controller_identity: str
    writer_id: str
    joint_targets: tuple
    gripper_semantic_id: str
    open_actuators: tuple
    materialization_id: str
    _source: object = field(repr=False, compare=False)
    _receipt: object = field(repr=False, compare=False)
    _controller: object = field(repr=False, compare=False)

    @property
    def identity_hash(self):
        values = {name: getattr(self, name) for name in (
            'source_id', 'source_closure_sha256', 'artifact_sha256',
            'controller_identity', 'writer_id', 'joint_targets',
            'gripper_semantic_id', 'open_actuators', 'materialization_id')}
        values['schema_version'] = 'legacy-native-feedback-binding-v1'
        return hashlib.sha256(json.dumps(values, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()

    @property
    def resources(self):
        return tuple(sorted((*dict(self.joint_targets), self.gripper_semantic_id)))

    def validate_live(self, session):
        source = getattr(session, '_source', None)
        controller = self._controller
        if (source is not self._source
                or getattr(source, 'execution_source_receipt', None) is not self._receipt
                or self._receipt.source_closure_digest != self.source_closure_sha256
                or source.source_id != self.source_id
                or tuple(sorted(source.joint_targets.items())) != self.joint_targets
                or tuple(source.open_actuators) != self.open_actuators
                or getattr(session._artifact, 'identity_hash', None) != self.artifact_sha256
                or session.provider_materialization_id != self.materialization_id
                or controller.identity != self.controller_identity
                or controller.control_submission_writer_id != self.writer_id
                or controller.gripper_semantic_id != self.gripper_semantic_id):
            raise ValueError('legacy native feedback binding no longer matches its admitted owners')


def install_admitted_binding(session, *, source, artifact, controller):
    """Freeze facts of the already-admitted materialization, without new admission."""
    from .source import ExecutionSourceReceiptV1
    receipt = source.execution_source_receipt
    if (type(receipt) is not ExecutionSourceReceiptV1 or session._source is not source
            or source.source_closure_digest not in (None, receipt.source_closure_digest)
            or receipt.source_id != source.source_id
            or source.task_artifact_hash != artifact.identity_hash
            or not source.joint_targets or not source.open_actuators):
        raise ValueError('legacy native feedback binding requires its admitted source receipt')
    writer = controller.control_submission_writer_id
    gripper = controller.gripper_semantic_id
    if (type(writer) is not str or not writer or type(gripper) is not str or not gripper
            or gripper in source.joint_targets
            or len(set(source.joint_targets.values()) | set(source.open_actuators))
            != len(source.joint_targets) + len(source.open_actuators)):
        raise ValueError('legacy native feedback resources are ambiguous')
    binding = LegacyNativeFeedbackBindingV1(source.source_id, receipt.source_closure_digest,
        artifact.identity_hash, controller.identity, writer,
        tuple(sorted(source.joint_targets.items())), gripper,
        tuple(source.open_actuators), session.provider_materialization_id,
        source, receipt, controller)
    binding.validate_live(session)
    session._legacy_native_feedback_binding = binding


def source_closure_identity(session):
    binding = getattr(session, '_legacy_native_feedback_binding', None)
    if binding is not None:
        if type(binding) is not LegacyNativeFeedbackBindingV1:
            raise TypeError('unsupported legacy native feedback binding')
        binding.validate_live(session)
        return binding.source_closure_sha256
    return session._source.source_closure_digest


@contextmanager
def native_feedback_interval(session, target, state, *, controller):
    binding = getattr(session, '_legacy_native_feedback_binding', None)
    if type(binding) is not LegacyNativeFeedbackBindingV1:
        raise ValueError('legacy native feedback lacks its admitted binding')
    binding.validate_live(session)
    if (controller is not binding._controller or target.controller_identity != binding.controller_identity
            or target.task_artifact_hash != binding.artifact_sha256
            or set(target.arm_servo_position) != set(dict(binding.joint_targets))
            or target.gripper.semantic_id != binding.gripper_semantic_id):
        raise ValueError('legacy native feedback target differs from its admitted Controller resources')
    current = session.snapshot()
    if current.to_mapping() != state.to_mapping():
        raise ValueError('legacy native feedback target uses a stale state')
    boundary = (session.provider_materialization_id, session.episode_id,
                session.state_revision, current.control_step)
    consumed = getattr(session, '_legacy_native_feedback_consumed', None)
    if consumed is None:
        consumed = session._legacy_native_feedback_consumed = set()
    if boundary in consumed or getattr(session, '_legacy_native_feedback_inflight', None) is not None:
        raise ValueError('legacy native feedback boundary is already consumed or active')
    consumed.add(boundary)
    session._legacy_native_feedback_inflight = (boundary, target.identity_hash, target.controller_identity)
    try:
        yield
    finally:
        session._legacy_native_feedback_inflight = None
