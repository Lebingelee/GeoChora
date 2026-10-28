"""Provider-free R03c static, admission and typed dispatch regression gates."""
from __future__ import annotations

from dataclasses import replace
import builtins
import hashlib
import json
import shutil
from types import SimpleNamespace

import numpy as np

import pytest

from task_env.artifacts import PoseWorld
from task_env.artifacts import ExecutionSpec
from task_env.artifacts.state import (
    StateBoundaryIdentity, StateSampleClock, CanonicalStatePublicationV1,
    StateViewLifetime, TypedFrameStateValue, TypedJointStateValue, CanonicalStateViewV1,
)
from task_env.controllers.canonical.leaf_profiles import (
    LeafApplicationAckV1, PANDA_HAND_TENDON_IDENTITY,
)
from task_env.controllers.canonical.leaf_plan import compile_effective_leaf_plan
from task_env.runtime.sessions.control import ControlBinding, materialize_control
from task_env.runtime.sessions import control as control_module
from task_env.runtime.sessions.leaf_control import (
    LeafActionRequestV1, LeafApplyResultV1, LeafControlIntervalRequestV1,
    LeafMaterializationReceiptV1, LeafNativeActuatorMappingV1,
    LeafNativeFrameMappingV1, LeafNativeJointMappingV1, LeafNativeTendonMappingV1,
    LeafRuntimeClockV1, dispatch_leaf_control_interval,
)
from task_env.recorders import RecorderConfig, TransitionRecorder
from task_env.recorders.h5 import load_leaf_control_records_h5
from task_env.trajectory.metadata import dump_metadata, load_metadata
from task_env.tasks.position_candidate.attached_leaf_candidate import (
    ARM_HOME, ARM_WRITER_ID, HAND_WRITER_ID, action_for_interval,
    build_attached_leaf_candidate,
)
from task_env.tasks.reference_env import SelectedReferenceEnv


def _candidate(monkeypatch, **kwargs):
    original = builtins.__import__

    def guarded(name, *args, **options):
        if name == 'mujoco' or name.startswith('mujoco.'):
            raise AssertionError('provider-free R03c S1 imported MuJoCo')
        return original(name, *args, **options)

    monkeypatch.setattr(builtins, '__import__', guarded)
    return build_attached_leaf_candidate(environment_type=SelectedReferenceEnv, **kwargs)


def _fixed_receipt(candidate, materialization_id='synthetic-materialization-r03c'):
    plan = candidate.attachment_plan
    joints = {}
    for index, (canonical, native) in enumerate(plan.native_joint_names.items()):
        joints[canonical] = {
            'native_name': native, 'joint_id': index, 'qpos_address': index,
            'dof_address': index, 'type': 3, 'axis': [0.0, 0.0, 1.0],
            'limited': True, 'range': [0.0, 0.04], 'body_id': index + 1,
        }
    actuators = {}
    for index, (canonical, native) in enumerate(plan.native_actuator_names.items()):
        actuators[canonical] = {
            'native_name': native, 'actuator_id': index, 'ctrl_slot': index,
            'transmission_type': 0, 'target_native_name': 'joint1',
            'ctrl_limited': True, 'ctrl_range': [-10.0, 10.0],
            'force_limited': False, 'force_range': [0.0, 0.0],
        }
    bodies = {canonical: {
        'native_name': native, 'body_id': index + 1,
        'parent_body_id': 0, 'parent_native_name': 'world',
    } for index, (canonical, native) in enumerate(plan.native_body_names.items())}
    tendons = {canonical: {'native_name': native, 'tendon_id': 0, 'wraps': []}
               for canonical, native in plan.native_tendon_names.items()}
    payload = {
        'schema_version': 'fixed-attachment-model-receipt-v1',
        'provider': 'mujoco', 'backend': 'cpu', 'provider_build': {}, 'runtime_identity': {},
        'provider_materialization_id': materialization_id,
        'task_artifact_sha256': candidate.artifact.identity_hash,
        'scene_identity_sha256': candidate.scene.identity_hash,
        'assembly_identity_sha256': plan.logical_content_sha256,
        'attachment_plan_sha256': plan.identity_hash,
        'source_closure_sha256': candidate.source.source_closure_digest,
        'fixed_root': {
            'parent_entity_id': plan.parent_entity_id,
            'parent_root': f'{plan.parent_root.entity_id}/{plan.parent_root.frame_id}',
            'child_entity_id': plan.child_entity_id,
            'child_root': f'{plan.child_root.entity_id}/{plan.child_root.frame_id}',
            'parent_mount': f'{plan.parent_mount.entity_id}/{plan.parent_mount.frame_id}',
            'child_mount': f'{plan.child_mount.entity_id}/{plan.child_mount.frame_id}',
            'parent_site_from_child_root': plan.parent_site_from_child_root.to_mapping(),
            'root_policy': plan.root_policy,
        },
        'dimensions': {'nq': 9, 'nv': 9, 'nu': 8, 'njnt': 9, 'nbody': 20,
                       'nsite': 2, 'nmesh': 0, 'ngeom': 1, 'neq': 1,
                       'ntendon': 1, 'nexclude': 3},
        'native_body_order': list(plan.native_body_names.values()),
        'native_joint_order': list(plan.native_joint_names.values()),
        'native_actuator_order': list(plan.native_actuator_names.values()),
        'native_body_mappings': bodies, 'native_site_mappings': {},
        'native_joint_mappings': joints, 'native_actuator_mappings': actuators,
        'native_tendon_mappings': tendons,
        'native_body_inverse': {value['native_name']: key for key, value in bodies.items()},
        'native_site_inverse': {},
        'native_joint_inverse': {value['native_name']: key for key, value in joints.items()},
        'native_actuator_inverse': {value['native_name']: key for key, value in actuators.items()},
        'source_collision_policy': plan.collision_policy,
        'compiled_exclusions': [], 'compiled_geoms': [], 'lowering': {},
    }
    payload['receipt_identity_sha256'] = __import__('hashlib').sha256(
        __import__('json').dumps(payload, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()
    return payload


def _synthetic_io(candidate):
    plan, scene = candidate.plan, candidate.scene
    attachment = _fixed_receipt(candidate)
    joint_rows, actuator_rows, frame_rows = [], [], []
    joint_id = 0
    native_joint_by_ref = {}
    for entry in plan.leaves:
        for ref, limits in zip(entry.binding.joint_order, entry.binding.joint_position_limits, strict=True):
            native = ref.joint_id if ref.entity_id == 'panda-arm' else 'probe_hand_' + ref.joint_id
            native_joint_by_ref[ref] = native
            joint_rows.append(LeafNativeJointMappingV1(
                'leaf-native-joint-mapping-v1', ref, native, joint_id, joint_id, joint_id,
                entry.binding.joint_position_unit,
            ))
            joint_id += 1
        for pair in entry.binding.joint_actuator_bindings:
            slot = len(actuator_rows)
            actuator_rows.append(LeafNativeActuatorMappingV1(
                'leaf-native-actuator-mapping-v1', pair.actuator, pair.actuator.actuator_id,
                slot, slot, (-10.0, 10.0), 'radian', 'joint', native_joint_by_ref[pair.joint],
            ))
        if entry.binding.profile_kind == 'hand_position':
            ref = entry.binding.actuator_order[0]
            slot = len(actuator_rows)
            actuator_rows.append(LeafNativeActuatorMappingV1(
                'leaf-native-actuator-mapping-v1', ref, 'probe_hand_actuator8',
                slot, slot, (0.0, 255.0), 'native_ctrl', 'tendon', 'probe_hand_split',
            ))
        frame_rows.append(LeafNativeFrameMappingV1(
            'leaf-native-frame-mapping-v1', entry.binding.tcp_frame,
            ('link7' if entry.binding.entity_id == 'panda-arm' else 'probe_hand_hand'),
            10 if entry.binding.entity_id == 'panda-arm' else 11,
        ))
    receipt = LeafMaterializationReceiptV1(
        'leaf-materialization-receipt-v1', 'synthetic_fixture', plan.scene_identity_sha256,
        plan.source_closure_sha256, plan.identity_sha256, plan.provider_name,
        plan.provider_version, plan.provider_build_sha256, plan.backend,
        'synthetic-materialization-r03c', 'leaf-' + plan.identity_sha256[:20],
        9, 9, 8, 9, 20, 1, 1, tuple(joint_rows), tuple(actuator_rows),
        tuple(frame_rows), (LeafNativeTendonMappingV1(
            'leaf-native-tendon-mapping-v1', 'hand.xml/tendon/split', 'probe_hand_split',
        ),), ('hand.xml/equality/finger_joint1=finger_joint2',),
        attachment['receipt_identity_sha256'],
    )
    boundary = StateBoundaryIdentity(
        'state-boundary-identity-v1', 'synthetic-episode', candidate.reset_plan.reset_sample.sample_id,
        scene.identity_hash, 'synthetic-scene-instance', receipt.materialization_id, 0, 3,
    )
    clock = StateSampleClock('state-sample-clock-v1', 'evaluation_boundary', 0, 0.0)
    joints, frames = [], []
    for entry in plan.leaves:
        for index, ref in enumerate(entry.binding.joint_order):
            value = ARM_HOME[index] if entry.binding.profile_kind == 'arm_position' else 0.038
            joints.append(TypedJointStateValue(
                'typed-joint-state-v1', ref.entity_id, ref.joint_id,
                'revolute' if entry.binding.profile_kind == 'arm_position' else 'prismatic',
                entry.binding.joint_position_unit, (float(value),),
                'radian_per_second' if entry.binding.profile_kind == 'arm_position' else 'meter_per_second',
                (0.0,),
            ))
        frames.append(TypedFrameStateValue(
            'typed-frame-state-v1', entry.binding.tcp_frame,
            PoseWorld((0.4, 0.0, 0.5), (1.0, 0.0, 0.0, 0.0)),
        ))
    view = CanonicalStateViewV1(
        'canonical-state-v1', 'SI_right_handed_z_up_wxyz', boundary, clock,
        tuple(joints), tuple(frames), (),
    )
    publication = CanonicalStatePublicationV1(
        'canonical-state-publication-v1', view,
        StateViewLifetime('state-view-lifetime-v1', receipt.materialization_id,
                          boundary, 3, 'owned_snapshot', 'retained'),
    )
    return receipt, publication, attachment


class _SyntheticRuntime:
    def __init__(self, candidate, receipt, publication, attachment=None):
        self.candidate, self.receipt, self.publication = candidate, receipt, publication
        self.fixed_attachment_receipt = attachment or _fixed_receipt(candidate)
        self.leaf_materialization_receipt = receipt
        self.leaf_configuration_revision = receipt.configuration_revision
        self.clock = LeafRuntimeClockV1(
            'leaf-runtime-clock-v1', publication.view.boundary,
            publication.view.sample_clock, receipt.configuration_revision,
        )
        self.applied = []
        self.step_calls = 0
        self.consumed = set()
        self.active_leaf_plan_identity = None

    @property
    def leaf_control_fault(self):
        return None

    def validate_leaf_materialization(self, receipt, plan):
        assert receipt == self.receipt
        receipt.validate_against_plan(plan)

    def validate_leaf_writer_available(self, writer_id, actuator_refs, receipt):
        assert writer_id in {ARM_WRITER_ID, HAND_WRITER_ID}
        assert actuator_refs and receipt == self.receipt

    def read_leaf_runtime_clock(self):
        return self.clock

    def begin_leaf_control_interval(self, plan_identity, boundary_id):
        assert plan_identity == self.candidate.plan.identity_sha256
        assert boundary_id not in self.consumed
        self.consumed.add(boundary_id)
        self.active_leaf_plan_identity = plan_identity

    def apply_leaf_actuator_patch(self, patch):
        self.applied.append(patch)
        self.clock = replace(self.clock, boundary=replace(
            self.clock.boundary, state_revision=self.clock.boundary.state_revision + 1,
        ))
        target, entry = patch.target, next(
            item for item in self.candidate.plan.leaves if item.binding.writer_id == patch.writer_id
        )
        ack = LeafApplicationAckV1(
            'leaf-application-ack-v1', entry.binding.profile_kind,
            entry.binding.profile_id, entry.binding.action_schema_id,
            target.identity_hash, target.writer_id, target.binding_identity_hash,
            target.source_closure_sha256, target.scene_identity_hash,
            target.joint_order, target.actuator_order, target.source_boundary,
            target.sample_clock, self.clock.boundary, self.clock.sample_clock,
        )
        return LeafApplyResultV1(
            'leaf-apply-result-v1', patch.writer_id, patch.command_identity_sha256,
            patch.materialization_identity_sha256,
            tuple(item.ctrl_slot for item in patch.slot_values), ack,
        )

    def step_leaf_control_interval(self, *, substeps):
        assert substeps == 5
        self.step_calls += 1
        before = self.clock
        next_step = before.boundary.control_step + 1
        boundary = replace(before.boundary, control_step=next_step,
                           state_revision=before.boundary.state_revision + 1)
        clock = replace(before.sample_clock, sample_index=next_step,
                        simulation_time_s=before.sample_clock.simulation_time_s + 0.01)
        self.clock = LeafRuntimeClockV1(
            'leaf-runtime-clock-v1', boundary, clock, before.configuration_revision,
        )

    def publish_leaf_state(self, scene, requirements):
        return replace(self.publication, view=replace(
            self.publication.view, boundary=self.clock.boundary,
            sample_clock=self.clock.sample_clock,
        ), lifetime=replace(self.publication.lifetime, boundary=self.clock.boundary,
                            generation=self.clock.boundary.state_revision))

    def latch_leaf_control_fault(self, progress, error):
        raise AssertionError(f'unexpected S1 runtime fault: {error!r}')


@pytest.mark.parametrize(('episode', 'gain', 'arm_active', 'hand_active'), [
    ('E1', 2.5, True, False), ('E2', 2.5, False, True),
    ('E3', 2.5, True, True), ('E4', 3.0, True, True),
])
def test_attached_candidate_and_two_entity_request_are_provider_free(
        monkeypatch, episode, gain, arm_active, hand_active):
    candidate = _candidate(
        monkeypatch, episode_id=episode, arm_gain=gain,
        arm_active=arm_active, hand_active=hand_active,
    )
    assert candidate.scene.identity_hash == '7981f0bb31875b35eb0973b08c1f65ac09210b55b7e9e0ea45761e4f8a4cfe9a'
    assert candidate.assembly.logical_content_sha256 == '232e62b18ea48ab04cc4ec2761a11666c8e1955a599b4f04ff585887d2fe1b4a'
    assert candidate.plan.fixed_attachment_plan_identity_sha256 == candidate.attachment_plan.identity_hash
    assert candidate.attachment_plan.native_tendon_names == {'panda-hand/split': 'probe_hand_split'}
    assert candidate.env.fixed_attachment_leaf_position_profile is True
    assert {entry.binding.entity_id for entry in candidate.plan.leaves} == {'panda-arm', 'panda-hand'}
    hand = next(entry for entry in candidate.plan.leaves if entry.binding.profile_kind == 'hand_position')
    assert hand.binding.tendon_identity == PANDA_HAND_TENDON_IDENTITY == 'hand.xml/tendon/split'
    assert hand.section.values()['gripper_position_stiffness_N_per_m'] == 50.0
    arm = next(entry for entry in candidate.plan.leaves if entry.binding.profile_kind == 'arm_position')
    assert arm.section.values()['joint_position_correction_gain'] == gain
    action = action_for_interval(candidate, 1, arm_active=arm_active, hand_active=hand_active)
    request = action.structured_request(candidate.scene, candidate.plan)
    assert {(item.entity_id, item.group_id) for item in request.groups} == {
        ('panda-arm', 'arm-position'), ('panda-hand', 'hand-position'),
    }
    assert action.arm.position_rad[0] == (0.00625 if arm_active else 0.0)
    assert action.hand.opening_m == (0.0715 if hand_active else 0.076)


def test_retry_counter_reconstruction_uses_append_only_ledger_prefix(tmp_path):
    from task_env.diagnostics.tasks.r03c_attached_leaf_probe import _retry_counters

    prior = tmp_path / 'native'
    retry = tmp_path / 'native_attempt_002'
    prior.mkdir(); retry.mkdir()
    failure = {
        'status': 'NATIVE_FAILURE', 'exception_type': 'ValueError',
        'message': 'Attachment receipt omits the canonical Hand actuator/tendon mapping',
        'active': {'phase': 'public_env_reset'},
        'traceback': 'ReferenceEnv materialize_control task_env/runtime/sessions/control.py admit_leaf_control_plan',
        'counters': {
            'native_starts': 1, 'materialization_attempts': 0, 'resets': 1,
            'mj_forward_calls': 0, 'mj_step_calls': 0,
        },
    }
    progress = {'counters': {'native_starts': 1, 'mj_forward_calls': 0, 'mj_step_calls': 0}}
    first = {'attempt': 1, 'event': 'START_RECORDED_BEFORE_NATIVE_PROCESS_LAUNCH'}
    second = {
        'attempt': 2, 'event': 'START_RECORDED_BEFORE_NATIVE_PROCESS_LAUNCH',
        'budget_before_start': {'native_starts': 1},
        'budget_after_reserving_start': {'native_starts': 2},
    }
    (prior / 'native_failure.json').write_text(json.dumps(failure))
    (prior / 'native_progress.json').write_text(json.dumps(progress))
    (retry / 'native_invocation.json').write_text(json.dumps(second))
    ledger_prefix = (json.dumps(first, sort_keys=True, separators=(',', ':')) + '\n').encode()
    with (prior / 'native_process_ledger.jsonl').open('wb') as stream:
        stream.write(ledger_prefix)
        stream.write((json.dumps(second, sort_keys=True, separators=(',', ':')) + '\n').encode())

    counters = _retry_counters(prior, tmp_path)
    assert counters['native_starts'] == 2
    assert counters['materialization_attempts'] == 1 and counters['resets'] == 1
    assert counters['mj_forward_calls'] == 0 and counters['mj_step_calls'] == 0
    assert counters['reconstructed_prior_attempt']['native_process_ledger_sha256'] == hashlib.sha256(
        ledger_prefix
    ).hexdigest()


def test_attached_plan_dispatches_both_real_typed_leaf_owners_through_one_interval(monkeypatch):
    candidate = _candidate(monkeypatch)
    receipt, publication, _attachment = _synthetic_io(candidate)
    runtime = _SyntheticRuntime(candidate, receipt, publication)
    action = action_for_interval(candidate, 1, arm_active=True, hand_active=True)
    request = action.structured_request(candidate.scene, candidate.plan)
    interval = LeafControlIntervalRequestV1(
        'leaf-control-interval-request-v1', candidate.plan.identity_sha256,
        receipt, publication, receipt.configuration_revision,
        (LeafActionRequestV1('leaf-action-request-v1', ARM_WRITER_ID, action.arm),
         LeafActionRequestV1('leaf-action-request-v1', HAND_WRITER_ID, action.hand)),
    )
    result = dispatch_leaf_control_interval(
        candidate.plan, interval, scene=candidate.scene, runtime=runtime,
    )
    assert result.interval_completed is True
    assert runtime.step_calls == 1 and len(runtime.applied) == 2
    slots = [value.ctrl_slot for patch in runtime.applied for value in patch.slot_values]
    assert sorted(slots) == list(range(8))
    assert len({value.actuator.entity_id for patch in runtime.applied
                for value in patch.slot_values}) == 2
    assert result.next_publication.view.boundary.control_step == 1


def test_attached_public_materialization_reaches_existing_runtime_owner_without_native(monkeypatch):
    candidate = _candidate(monkeypatch)
    admitted = []

    class StubSession:
        def __init__(self):
            self.closed = False

        def admit_leaf_control_plan(self, plan):
            admitted.append(plan)

        def close(self):
            self.closed = True

    stub = StubSession()
    calls = []
    monkeypatch.setattr(control_module, 'materialize',
                        lambda *args, **kwargs: calls.append((args, kwargs)) or stub)
    execution = ExecutionSpec('mujoco', 'p1_2_scalar_cpu_v0', 'none', 'cpu', 31, 'strict')
    result = materialize_control(
        candidate.artifact, execution, source=candidate.source,
        binding=ControlBinding('panda-hand/hand-position', 0.08),
        leaf_plan=candidate.plan,
    )
    assert result is stub and admitted == [candidate.plan] and len(calls) == 1
    assert calls[0][1]['_materialization_authority'] is None

    wrong_plan = compile_effective_leaf_plan(
        candidate.scene, candidate.assembly, (), candidate.bindings, candidate.preset,
        candidate.overrides, source_closure_sha256=candidate.source.source_closure_digest,
        fixed_attachment_plan_identity_sha256='0' * 64,
    )
    with pytest.raises(ValueError, match='Attachment plan'):
        materialize_control(
            candidate.artifact, execution, source=candidate.source,
            binding=ControlBinding('panda-hand/hand-position', 0.08), leaf_plan=wrong_plan,
        )
    assert len(calls) == 1


def _observation(candidate, index, boundary_id):
    arm_values = np.asarray(ARM_HOME, dtype=np.float32).copy()
    if candidate.arm_active:
        if index <= 16:
            arm_values[0] = np.float32(0.1 * index / 16)
        elif index <= 32:
            arm_values[0] = np.float32(0.1)
        elif index <= 48:
            arm_values[0] = np.float32(0.1 * (48 - index) / 16)
    if candidate.hand_active and index <= 16:
        opening = 0.076 - 0.072 * index / 16
    elif candidate.hand_active and index <= 32:
        opening = 0.004
    elif candidate.hand_active and index <= 48:
        opening = 0.004 + 0.072 * (index - 32) / 16
    else:
        opening = 0.076
    finger = np.asarray((opening / 2, opening / 2), dtype=np.float32)
    angle = float(arm_values[0]) * 0.6
    quaternion = np.asarray((np.cos(angle / 2), 0.0, 0.0, np.sin(angle / 2)), dtype=np.float32)
    hand_pose = np.asarray((0.4, 0.0, 0.5, *quaternion), dtype=np.float32)
    return {
        'state': {
            'ee_pose': hand_pose.copy(),
            'joint_position': np.concatenate((arm_values, finger)).astype(np.float32),
            'hand_pose': hand_pose,
                'boundary_identity_sha256': np.frombuffer(
                    bytes.fromhex(boundary_id.removeprefix('state-boundary-')),
                    dtype=np.uint8,
                ).copy(),
            'entities': {
                'panda-arm': {'joint_position': arm_values, 'hand_pose': hand_pose.copy()},
                'panda-hand': {'joint_position': finger, 'hand_pose': hand_pose.copy()},
            },
        },
        'privileged_state': {},
    }


def test_attached_generic_h5_closes_and_independently_reads_back_without_native(monkeypatch, tmp_path):
    candidate = _candidate(monkeypatch, episode_id='E3')
    receipt, publication, attachment = _synthetic_io(candidate)
    runtime = _SyntheticRuntime(candidate, receipt, publication, attachment)
    env = candidate.env
    env.session = runtime
    env.position_scene = candidate.scene
    env.horizon = 64
    env.recording_path = tmp_path / 'r03c-s1-synthetic.h5'
    env.recorder = TransitionRecorder(RecorderConfig(schema_version='v3', max_transitions=64))
    env._position_reset_info = {'seed': 31, 'reset_sample_id': candidate.reset_plan.reset_sample.sample_id}
    env.obs = _observation(candidate, 0, publication.view.boundary.boundary_id)
    env.info = {'control_step': 0, 'simulation_time_s': 0.0, 'task_metrics': {}}
    env.evaluation = SimpleNamespace(reward=0.0, success=False, failure=False, metrics={})
    env.recorder.begin_episode(env.obs, dict(env._position_reset_info), env._position_record_metadata())
    for index in range(1, 65):
        action = action_for_interval(candidate, index, arm_active=True, hand_active=True)
        structured = action.structured_request(candidate.scene, candidate.plan)
        request = LeafControlIntervalRequestV1(
            'leaf-control-interval-request-v1', candidate.plan.identity_sha256,
            receipt, runtime.publication, receipt.configuration_revision,
            (LeafActionRequestV1('leaf-action-request-v1', ARM_WRITER_ID, action.arm),
             LeafActionRequestV1('leaf-action-request-v1', HAND_WRITER_ID, action.hand)),
        )
        result = dispatch_leaf_control_interval(candidate.plan, request,
                                                scene=candidate.scene, runtime=runtime)
        runtime.publication = result.next_publication
        env.obs = _observation(candidate, index, runtime.clock.boundary.boundary_id)
        env.info = {'control_step': index, 'simulation_time_s': index * 0.01,
                    'task_metrics': {}, 'state_boundary_id': runtime.clock.boundary.boundary_id}
        env.evaluation = SimpleNamespace(reward=0.0, success=False, failure=False, metrics={})
        env._record_leaf_position_transition(
            action, structured, result, terminated=False, truncated=index == 64,
        )
    env.state = SimpleNamespace(control_step=64, simulation_time=0.64)
    env.typed_state = runtime.publication
    env._published_position_state = env.state
    env._published_position_typed_state = env.typed_state
    env._published_position_obs = env.obs
    env._published_position_info = env.info
    env._published_position_evaluation = env.evaluation
    env._position_episode_end = env._make_position_episode_end(
        'horizon_reached', terminated=False, truncated=True, bootstrap_allowed=True,
    )
    result = env.finish_recording('horizon')
    assert result['schema_version'] == 'v3'
    assert result['transition_count'] == 64 and result['observation_count'] == 65
    cases = {
        'target_identity': lambda rows: rows[0]['writer_controls'][0]['controller_target'].__setitem__('identity_hash', '0' * 64),
        'ack_writer': lambda rows: rows[0]['writer_controls'][0]['canonical_action']['application_ack'].__setitem__('writer_id', 'tampered-writer'),
        'prepared_command': lambda rows: rows[0]['writer_controls'][0]['canonical_action']['prepared_command']['slot_values'][0].__setitem__('value', 999.0),
        'source_digest': lambda rows: rows[0]['writer_controls'][0]['canonical_action'].__setitem__('source_closure_sha256', '0' * 64),
        'configuration_identity': lambda rows: rows[0]['writer_controls'][0]['canonical_action'].__setitem__('configuration_identity_sha256', '0' * 64),
        'missing_writer': lambda rows: rows[0]['writer_controls'].pop(),
        'duplicate_slot': lambda rows: rows[0]['writer_controls'][1]['applied_control']['payload'].__setitem__(
            'applied_slots', [rows[0]['writer_controls'][0]['canonical_action']['prepared_command']['slot_values'][0]['ctrl_slot']]
        ),
    }

    def alter_controls(destination, mutation):
        import h5py
        from task_env.recorders.h5 import _read_text

        with h5py.File(destination, 'r+') as root:
            rows = json.loads(_read_text(root, 'meta/structured_controls_v1_json'))
            mutation(rows)
            del root['meta/structured_controls_v1_json']
            root.create_dataset('meta/structured_controls_v1_json',
                                data=json.dumps(rows, sort_keys=True),
                                dtype=h5py.string_dtype(encoding='utf-8'))

    for label, mutation in cases.items():
        destination = tmp_path / f'tamper-{label}.h5'
        shutil.copy2(env.recording_path, destination)
        alter_controls(destination, mutation)
        with pytest.raises(Exception):
            load_leaf_control_records_h5(destination)

    import h5py
    destination = tmp_path / 'tamper-boundary.h5'
    shutil.copy2(env.recording_path, destination)
    with h5py.File(destination, 'r+') as root:
        values = root['obs/state/boundary_identity_sha256']
        values[1, 0] = (int(values[1, 0]) + 1) % 256
    with pytest.raises(ValueError):
        load_leaf_control_records_h5(destination)

    destination = tmp_path / 'tamper-t-plus-one.h5'
    shutil.copy2(env.recording_path, destination)
    with h5py.File(destination, 'r+') as root:
        root.attrs['observation_count'] = 64
    with pytest.raises(ValueError):
        load_leaf_control_records_h5(destination)

    metadata_cases = {
        'attachment_hash': lambda profile: profile.__setitem__('attachment_plan_identity_sha256', '0' * 64),
        'entity_binding': lambda profile: profile['writers'][0].__setitem__('entity_id', 'panda-secondary'),
        'native_tcp': lambda profile: profile['attachment_receipt']['native_body_mappings'][
            'panda-hand/hand'
        ].__setitem__('native_name', 'hand'),
    }
    for label, mutation in metadata_cases.items():
        destination = tmp_path / f'tamper-{label}.h5'
        shutil.copy2(env.recording_path, destination)
        with h5py.File(destination, 'r+') as root:
            from task_env.recorders.h5 import _read_text
            raw = load_metadata(_read_text(root, 'meta/env_meta'))
            mutation(raw['reference_profile'])
            del root['meta/env_meta']
            root.create_dataset('meta/env_meta', data=dump_metadata(raw),
                                dtype=h5py.string_dtype(encoding='utf-8'))
        with pytest.raises(ValueError):
            load_leaf_control_records_h5(destination)

    import hashlib
    offline_dir = tmp_path / 'offline-readback'
    native_dir = offline_dir / 'native'
    native_dir.mkdir(parents=True)
    offline_h5 = native_dir / 'E3.h5'
    shutil.copy2(env.recording_path, offline_h5)
    contract_episode = {
        'episode_id': 'E3',
        'task_artifact_identity_sha256': candidate.artifact.identity_hash,
        'scene_identity_sha256': candidate.scene.identity_hash,
        'assembly_identity_sha256': candidate.assembly.logical_content_sha256,
        'attachment_plan_identity_sha256': candidate.attachment_plan.identity_hash,
        'source_closure_sha256': candidate.source.source_closure_digest,
        'reset_plan_identity_sha256': candidate.reset_plan.identity_hash,
        'effective_leaf_plan_identity_sha256': candidate.plan.identity_sha256,
        'arm_active': True, 'hand_active': True,
    }
    (native_dir / 'executed_contract.json').write_text(json.dumps({
        'input_head': '703e8a1b184b18e7efbc0b5532b96fb3a462b4d2',
        'episodes': [contract_episode],
    }))
    (native_dir / 'native_result.json').write_text(json.dumps({
        'status': 'NATIVE_S2_COMPLETE_AWAITING_HOST_OFFLINE_S3',
        'episodes': [{'episode_id': 'E3', 'sha256': hashlib.sha256(offline_h5.read_bytes()).hexdigest()}],
    }))
    from task_env.diagnostics.tasks.r03c_offline_readback import run as offline_readback
    offline = offline_readback(offline_dir)
    assert offline['status'] == 'OFFLINE_READBACK_INCOMPLETE_OR_FAILED'
    assert offline['aggregate'] == {
        'episode_count': 1, 'transition_count': 64, 'observation_count': 65,
        'tamper_rejections': 12,
    }
    assert 'mujoco' not in __import__('sys').modules and 'taichi' not in __import__('sys').modules
