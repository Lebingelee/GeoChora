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
        level = args[3] if len(args) > 3 else options.get('level', 0)
        if level == 0 and (name == 'mujoco' or name.startswith('mujoco.')):
            raise AssertionError('provider-free R03c S1 imported MuJoCo')
        return original(name, *args, **options)

    monkeypatch.setattr(builtins, '__import__', guarded)
    return build_attached_leaf_candidate(environment_type=SelectedReferenceEnv, **kwargs)


def _fixed_receipt(candidate, materialization_id='synthetic-materialization-r03c'):
    plan = candidate.attachment_plan
    order_variant = plan.parent_asset_version == 'menagerie-b846dd12-r06b-order-v1'
    bindings = {ref.joint_id: (entry.binding, limits)
                for entry in candidate.plan.leaves
                for ref, limits in zip(entry.binding.joint_order, entry.binding.joint_position_limits, strict=True)}
    body_items = list(plan.native_body_names.items())
    joint_items = list(plan.native_joint_names.items())
    actuator_items = list(plan.native_actuator_names.items())
    if order_variant:
        joint_items[-2:] = reversed(joint_items[-2:])
        actuator_items[:7] = reversed(actuator_items[:7])
    body_names = ['world', *(native for _, native in body_items)]
    body_ids = {name: index for index, name in enumerate(body_names)}
    parent_names = {'link0': 'world', **{f'link{i}': f'link{i-1}' for i in range(1, 8)},
                    'attachment': 'link7', 'probe_hand_hand': 'attachment',
                    'probe_hand_left_finger': 'probe_hand_hand',
                    'probe_hand_right_finger': 'probe_hand_hand'}
    joints = {}
    for index, (canonical, native) in enumerate(joint_items):
        entity, local = canonical.split('/')
        binding, limits = bindings[local]
        joint = next(joint for articulation in candidate.scene.articulations
                     if articulation.entity_id == entity
                     for joint in articulation.joints if joint.joint_id == local)
        joints[canonical] = {
            'native_name': native, 'joint_id': index, 'qpos_address': index,
            'dof_address': index, 'type': 3 if binding.profile_kind == 'arm_position' else 2,
            'axis': list(joint.axis), 'limited': True, 'range': list(limits),
            'body_id': body_ids[plan.native_body_names[f'{entity}/{joint.child_frame.frame_id}']],
        }
    actuators = {}
    for index, (canonical, native) in enumerate(actuator_items):
        hand = canonical.startswith('panda-hand/')
        target = 'probe_hand_split' if hand else native.replace('actuator', 'joint')
        actuators[canonical] = {
            'native_name': native, 'actuator_id': index, 'ctrl_slot': index,
            'transmission_type': 3 if hand else 0, 'target_native_name': target,
            'ctrl_limited': True, 'ctrl_range': [0.0, 255.0] if hand else list(bindings[target][1]),
            'force_limited': False, 'force_range': [0.0, 0.0],
        }
    bodies = {canonical: {
        'native_name': native, 'body_id': index + 1,
        'parent_body_id': body_ids[parent_names[native]], 'parent_native_name': parent_names[native],
    } for index, (canonical, native) in enumerate(body_items)}
    tendons = {canonical: {'native_name': native, 'tendon_id': 0, 'wraps': [
        {'wrap_type': 1, 'joint_native_name': 'probe_hand_finger_joint1', 'coefficient': 0.5},
        {'wrap_type': 1, 'joint_native_name': 'probe_hand_finger_joint2', 'coefficient': 0.5},
    ]}
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
        'dimensions': {'nq': 9, 'nv': 9, 'nu': 8, 'njnt': 9, 'nbody': 13,
                       'nsite': 1, 'nmesh': 67, 'ngeom': 81, 'neq': 1,
                       'ntendon': 1, 'nexclude': 3},
        'native_body_order': body_names,
        'native_joint_order': [native for _, native in joint_items],
        'native_actuator_order': [native for _, native in actuator_items],
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
            canonical = f'{ref.entity_id}/{ref.joint_id}'
            native_row = attachment['native_joint_mappings'][canonical]
            joint_rows.append(LeafNativeJointMappingV1(
                'leaf-native-joint-mapping-v1', ref, native, native_row['joint_id'],
                native_row['qpos_address'], native_row['dof_address'],
                entry.binding.joint_position_unit,
            ))
            joint_id += 1
        for pair in entry.binding.joint_actuator_bindings:
            canonical = f'{pair.actuator.entity_id}/{pair.actuator.actuator_id}'
            native_row = attachment['native_actuator_mappings'][canonical]
            slot = native_row['ctrl_slot']
            actuator_rows.append(LeafNativeActuatorMappingV1(
                'leaf-native-actuator-mapping-v1', pair.actuator, native_row['native_name'],
                native_row['actuator_id'], slot, tuple(native_row['ctrl_range']),
                'radian', 'joint', native_joint_by_ref[pair.joint],
            ))
        if entry.binding.profile_kind == 'hand_position':
            ref = entry.binding.actuator_order[0]
            canonical = f'{ref.entity_id}/{ref.actuator_id}'
            native_row = attachment['native_actuator_mappings'][canonical]
            slot = native_row['ctrl_slot']
            actuator_rows.append(LeafNativeActuatorMappingV1(
                'leaf-native-actuator-mapping-v1', ref, native_row['native_name'],
                native_row['actuator_id'], slot, tuple(native_row['ctrl_range']),
                'native_ctrl', 'tendon', 'probe_hand_split',
            ))
        frame_rows.append(LeafNativeFrameMappingV1(
            'leaf-native-frame-mapping-v1', entry.binding.tcp_frame,
            ('link7' if entry.binding.entity_id == 'panda-arm' else 'probe_hand_hand'),
            attachment['native_body_mappings'][f'{entry.binding.entity_id}/{entry.binding.tcp_frame.frame_id}']['body_id'],
        ))
    receipt = LeafMaterializationReceiptV1(
        'leaf-materialization-receipt-v1', 'synthetic_fixture', plan.scene_identity_sha256,
        plan.source_closure_sha256, plan.identity_sha256, plan.provider_name,
        plan.provider_version, plan.provider_build_sha256, plan.backend,
        'synthetic-materialization-r03c', 'leaf-' + plan.identity_sha256[:20],
        9, 9, 8, 9, 13, 1, 1, tuple(joint_rows), tuple(actuator_rows),
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


def _session_with_synthetic_native_io(candidate):
    """Keep all Core owners real; replace only the native model/data operations.

    This models names, slots and dimensions, never physical motion. In
    particular the source tendon key differs from the leaf logical identity.
    """
    from task_env.runtime.sessions.mujoco import _MuJoCoSession
    session = object.__new__(_MuJoCoSession)
    session._initialize_values(candidate.artifact, candidate.source, 'mujoco')
    receipt = _fixed_receipt(candidate, session.provider_materialization_id)
    attachment = receipt
    joint_rows = sorted(receipt['native_joint_mappings'].values(), key=lambda row: row['joint_id'])
    actuator_rows = sorted(receipt['native_actuator_mappings'].values(), key=lambda row: row['actuator_id'])
    names = {
        'joint': [row['native_name'] for row in joint_rows],
        'actuator': [row['native_name'] for row in actuator_rows],
        'body': receipt['native_body_order'], 'tendon': ['probe_hand_split'],
    }
    joint_ids = {row['native_name']: row['joint_id'] for row in joint_rows}
    actuator_trnid = []
    actuator_trntype = []
    for row in actuator_rows:
        if row['transmission_type'] == 3:
            actuator_trnid.append([0, -1])
            actuator_trntype.append(3)
        else:
            actuator_trnid.append([joint_ids[row['target_native_name']], -1])
            actuator_trntype.append(0)
    model = SimpleNamespace(
        nq=9, nv=9, nu=8, njnt=9, nbody=13, neq=1, ntendon=1,
        jnt_type=np.asarray([row['type'] for row in joint_rows]),
        jnt_limited=np.ones(9, dtype=bool),
        jnt_range=np.asarray([row['range'] for row in joint_rows]),
        jnt_qposadr=np.arange(9), jnt_dofadr=np.arange(9),
        actuator_ctrlrange=np.asarray([row['ctrl_range'] for row in actuator_rows]),
        actuator_ctrllimited=np.ones(8, dtype=bool),
        actuator_trnid=np.asarray(actuator_trnid),
        actuator_trntype=np.asarray(actuator_trntype),
        tendon_num=np.asarray([2]), tendon_adr=np.asarray([0]),
        wrap_type=np.asarray([1, 1]),
        wrap_objid=np.asarray([joint_ids['probe_hand_finger_joint1'],
                               joint_ids['probe_hand_finger_joint2']]),
        wrap_prm=np.asarray([0.5, 0.5]),
        eq_type=np.asarray([2]),
        eq_obj1id=np.asarray([joint_ids['probe_hand_finger_joint1']]),
        eq_obj2id=np.asarray([joint_ids['probe_hand_finger_joint2']]),
        opt=SimpleNamespace(timestep=0.002),
    )
    data = SimpleNamespace(qpos=np.zeros(9), qvel=np.zeros(9), act=np.zeros(0),
        ctrl=np.zeros(8), time=0.0, xpos=np.zeros((13,3)),
        xquat=np.tile((1.,0.,0.,0.), (13,1)),
        site_xpos=np.zeros((1,3)), site_xmat=np.eye(3).reshape(1,9), warning=[])

    def name2id(_model, kind, name):
        return names[kind].index(name) if name in names[kind] else -1

    def reset(_model, values):
        values.qpos[:]=0; values.qvel[:]=0; values.ctrl[:]=0; values.time=0.0

    def step(_model, values):
        # Deterministic mock IO follows named Actuator slots and emits enough
        # distinguishable state to exercise the unchanged strict H5 reader.
        # It is deliberately not a dynamics simulation or native evidence.
        for actuator in actuator_rows:
            if actuator['transmission_type'] == 0:
                joint_id = joint_ids[actuator['target_native_name']]
                values.qpos[joint_id] = values.ctrl[actuator['ctrl_slot']]
        hand_actuator = attachment['native_actuator_mappings']['panda-hand/actuator8']
        opening = min(0.08, max(0.0, float(values.ctrl[hand_actuator['ctrl_slot']]) / 255.0 * 0.08))
        values.qpos[joint_ids['probe_hand_finger_joint1']] = opening / 2.0
        values.qpos[joint_ids['probe_hand_finger_joint2']] = opening / 2.0
        values.time += 0.002
        interval = min(64, int(round(values.time / 0.01)))
        if interval <= 16:
            joint1 = 0.1 * interval / 16.0
        elif interval <= 32:
            joint1 = 0.1
        elif interval <= 48:
            joint1 = 0.1 * (48 - interval) / 16.0
        else:
            joint1 = ARM_HOME[0]
        values.qpos[joint_ids['joint1']] = joint1
        for index, value in enumerate(ARM_HOME[1:], start=2):
            values.qpos[joint_ids[f'joint{index}']] = value
        update_forward(_model, values)

    transform = candidate.attachment_plan.parent_site_from_child_root
    hand_body_id = attachment['native_body_mappings']['panda-hand/hand']['body_id']
    site_id = 0
    joint1_id = joint_ids['joint1']

    def update_forward(_model, values):
        theta = float(values.qpos[joint1_id])
        cosine, sine = np.cos(theta), np.sin(theta)
        rotation = np.asarray(((cosine, -sine, 0.0), (sine, cosine, 0.0), (0.0, 0.0, 1.0)))
        values.site_xmat[site_id] = rotation.reshape(9)
        translation = np.asarray(transform.position, dtype=float)
        values.xpos[hand_body_id] = values.site_xpos[site_id] + rotation @ translation
        parent_quaternion = (float(np.cos(theta / 2.0)), 0.0, 0.0, float(np.sin(theta / 2.0)))
        child_quaternion = transform.quaternion_wxyz
        w1, x1, y1, z1 = parent_quaternion
        w2, x2, y2, z2 = child_quaternion
        values.xquat[hand_body_id] = (
            w1*w2 - x1*x2 - y1*y2 - z1*z2,
            w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2,
            w1*z2 + x1*y2 - y1*x2 + z1*w2,
        )

    def quaternion(output, matrix):
        matrix = np.asarray(matrix).reshape(3, 3)
        cosine = np.sqrt(max(0.0, 1.0 + np.trace(matrix))) / 2.0
        output[:] = (cosine, 0.0, 0.0,
                     np.copysign(np.sqrt(max(0.0, 1.0 - cosine*cosine)), matrix[1, 0]))

    session._model, session._data = model, data
    session._mj = SimpleNamespace(
        mjtJoint=SimpleNamespace(mjJNT_FREE=0, mjJNT_HINGE=3, mjJNT_SLIDE=2),
        mjtObj=SimpleNamespace(mjOBJ_JOINT='joint', mjOBJ_ACTUATOR='actuator', mjOBJ_BODY='body', mjOBJ_TENDON='tendon'),
        mjtTrn=SimpleNamespace(mjTRN_JOINT=0, mjTRN_TENDON=3),
        mjtEq=SimpleNamespace(mjEQ_JOINT=2),
        mj_name2id=name2id, mj_id2name=lambda _m, kind, index: names[kind][index],
        mj_resetData=reset, mj_forward=update_forward, mj_step=step, mju_mat2Quat=quaternion,
    )
    session._fixed_attachment_receipt=receipt
    session._fixed_attachment_close_receipt=None
    session._joint_addresses={key:(row['qpos_address'],row['dof_address']) for key,row in receipt['native_joint_mappings'].items()}
    session._bodies={key:row['body_id'] for key,row in receipt['native_body_mappings'].items()}
    session._frames={key:0 for key in candidate.source.frames}
    session._free_addresses={}
    session._target_actuators={key:names['actuator'].index(native) for key,native in candidate.source.joint_targets.items()}
    session._open_actuators=(7,)
    session._native_steps=0; session._fixed_forward_calls=0
    session._leaf_plan=None; session._leaf_materialization_receipt=None
    session._leaf_fault=None; session._leaf_consumed_boundaries=set()
    session._leaf_interval_active=False; session._leaf_interval_writers=set()
    session._leaf_active_plan_identity=None
    return session


def test_public_env_reset_and_step_reach_real_attached_admission_and_publication(monkeypatch):
    from task_env.runtime.sessions import api
    candidate=_candidate(monkeypatch)
    session=_session_with_synthetic_native_io(candidate)
    monkeypatch.setattr(api, '_materialize_admitted', lambda *_:session)
    try:
        obs, info=candidate.env.reset(seed=31)
        receipt=session.leaf_materialization_receipt
        assert receipt.tendons[0].tendon_identity == 'hand.xml/tendon/split'
        assert receipt.tendons[0].native_name == 'probe_hand_split'
        assert candidate.attachment_plan.native_tendon_names == {'panda-hand/split':'probe_hand_split'}
        assert obs['state']['entities']['panda-arm']['joint_position'].shape==(7,)
        assert obs['state']['entities']['panda-hand']['joint_position'].shape==(2,)
        assert session._data.ctrl[7] == 242.25
        candidate.env.step(action_for_interval(candidate,1,arm_active=True,hand_active=True))
        assert session._native_steps==5 and session._fixed_forward_calls==2
        assert candidate.env.typed_state.view.boundary.control_step==1
        assert len(session._leaf_consumed_boundaries)==1
        assert candidate.env.state.simulation_time==0.01
    finally:
        candidate.env.close()
    assert session._closed and session._model is None and session._data is None


def test_native_snapshot_bindings_use_scene_joint_definitions(monkeypatch):
    from task_env.artifacts.contracts import JointDefinition
    from task_env.diagnostics.tasks.r03c_attached_leaf_probe import _candidate_bindings
    import sys

    candidate=_candidate(monkeypatch)
    joint_bindings, frame_bindings=_candidate_bindings(candidate)
    expected={
        f'{articulation.entity_id}/{joint.joint_id}': joint
        for articulation in candidate.scene.articulations
        for joint in articulation.joints
    }
    selected={
        f'{ref.entity_id}/{ref.joint_id}'
        for entry in candidate.plan.leaves
        for ref in entry.binding.joint_order
    }
    assert set(joint_bindings)==selected
    assert all(type(value) is JointDefinition for value in joint_bindings.values())
    assert joint_bindings=={name:expected[name] for name in sorted(selected)}
    assert set(frame_bindings)==set(candidate.source.bodies)|set(candidate.source.frames)
    assert not any(name.split('.',1)[0] in {'mujoco','taichi'} for name in sys.modules)


@pytest.mark.parametrize('episode,arm_active,hand_active,arm_gain', [
    ('E1', True, False, 2.5), ('E2', False, True, 2.5),
    ('E3', True, True, 2.5), ('E4', True, True, 3.0),
])
def test_runner_mount_snapshot_reaches_real_core_after_reset_and_step(
        monkeypatch, episode, arm_active, hand_active, arm_gain):
    from task_env.runtime.sessions import api
    from task_env.diagnostics.tasks.r03c_attached_leaf_probe import (
        _candidate_bindings, _mount_requirements, _check_reset, _check_outer,
    )

    candidate = _candidate(monkeypatch, episode_id=episode, arm_gain=arm_gain,
                           arm_active=arm_active, hand_active=hand_active)
    session = _session_with_synthetic_native_io(candidate)
    # Explicit synthetic native readback geometry, not a dynamics result.
    child = session._bodies['panda-hand/hand']
    session._data.xquat[child] = candidate.attachment_plan.parent_site_from_child_root.quaternion_wxyz
    session._data.warning = []
    monkeypatch.setattr(api, '_materialize_admitted', lambda *_: session)
    try:
        candidate.env.reset(seed=31)
        joints, frames = _candidate_bindings(candidate)
        requirements = _mount_requirements(candidate)

        def snapshot():
            return session.snapshot_v1(scene=candidate.scene, joint_bindings=joints,
                                       frame_bindings=frames, requirements=requirements)

        initial = snapshot()
        reset = _check_reset(candidate, candidate.env, initial, ())
        assert reset['joint_position_max_abs_error_rad_or_m'] == 0
        assert len(initial.view.joints) == 9
        # Same path and API that failed in attempt002, not just a type assertion.
        wrong_joints = {f'{ref.entity_id}/{ref.joint_id}': ref
                        for entry in candidate.plan.leaves for ref in entry.binding.joint_order}
        with pytest.raises(TypeError, match='must be a JointDefinition'):
            session.snapshot_v1(scene=candidate.scene, joint_bindings=wrong_joints,
                                frame_bindings=frames, requirements=requirements)
        candidate.env.step(action_for_interval(candidate, 1, arm_active=arm_active,
                                               hand_active=hand_active))
        after = snapshot()
        _check_outer(candidate, candidate.env, after, 1, ())
        assert after.view.boundary.control_step == 1
        assert after.view.sample_clock.simulation_time_s == 0.01
        assert session._native_steps == 5  # Synthetic IO calls, no native import.
    finally:
        candidate.env.close()
    assert session._closed and session._model is None and session._data is None


def test_real_attached_admission_rejects_logical_tendon_key_in_source_namespace(monkeypatch):
    candidate=_candidate(monkeypatch)
    session=_session_with_synthetic_native_io(candidate)
    receipt=session._fixed_attachment_receipt
    receipt['native_tendon_mappings']['hand.xml/tendon/split']=receipt['native_tendon_mappings'].pop('panda-hand/split')
    with pytest.raises(ValueError,match='actuator/tendon mapping'):
        session.admit_leaf_control_plan(candidate.plan)
    assert session._native_steps==0
    session.close()


def test_fresh_freeze_and_real_runner_preflight_validate_reserved_ledger_without_provider(monkeypatch, tmp_path):
    import subprocess
    from task_env.diagnostics.tasks import r03c_freeze
    from task_env.diagnostics.tasks.r03c_attached_leaf_probe import run_native

    original_import=builtins.__import__
    def block(name,*args,**kwargs):
        level=args[3] if len(args)>3 else kwargs.get('level',0)
        if level==0 and name.split('.')[0] in {'mujoco','taichi'}:
            raise AssertionError('static execution preflight reached native import')
        return original_import(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',block)
    root=r03c_freeze.ROOT
    # Keep this provider-free fixture self-contained in a fresh checkout; the
    # historical attempt's ignored workspace snapshot is not a repository input.
    snapshot={'protected_sha256':{
        relative: hashlib.sha256((root/relative).read_bytes()).hexdigest()
        for relative in r03c_freeze.SOURCES
    }}
    prompt=tmp_path/'prompt.md'; prompt.write_text('Synthetic S1 gate fixture; not native execution authorization.\n')
    snapshot.update(core_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
                    branch=subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip(),
                    prompt=str(prompt),native_window={'max_starts':1,'consumed':False})
    snapshot_path=tmp_path/'snapshot.json'; snapshot_path.write_text(json.dumps(snapshot))
    output=tmp_path/'fresh-package'
    r03c_freeze.main(['--fresh-window','--output-dir',str(output),'--snapshot',str(snapshot_path),'--prompt',str(prompt)])
    result=run_native(output,snapshot_path,preflight_only=True)
    assert result['status']=='PROVIDER_FREE_NATIVE_PREFLIGHT_READY'
    assert result['provider_imports']==result['native_starts']==result['mj_step_calls']==0
    assert not (output/'native').exists()
    with pytest.raises(FileNotFoundError):
        run_native(output,snapshot_path)  # Actual import remains behind mandatory reservation.
    native=output/'native'; native.mkdir()
    record={'attempt':1,'event':'START_RECORDED_BEFORE_NATIVE_PROCESS_LAUNCH',
            'budget_before_start':{'native_starts':0},'budget_after_reserving_start':{'native_starts':1},
            'executed_contract_sha256':hashlib.sha256((output/'freeze/executed_contract.json').read_bytes()).hexdigest()}
    (native/'native_invocation.json').write_text(json.dumps(record))
    ledger=native/'native_process_ledger.jsonl'; ledger.write_text(json.dumps(record)+'\n')
    assert run_native(output,snapshot_path,preflight_only=True)['expected_episodes']==4
    assert not (native/'native_progress.json').exists()
    ledger.write_text(ledger.read_text()+json.dumps(record)+'\n')
    with pytest.raises(ValueError,match='one bound prelaunch'):
        run_native(output,snapshot_path,preflight_only=True)
    assert 'mujoco' not in __import__('sys').modules and 'taichi' not in __import__('sys').modules


@pytest.fixture
def runner_closeout(monkeypatch, tmp_path):
    """Synthetic completed-episode facts; exercises real receipt IO, no physics claim."""
    from task_env.diagnostics.tasks import r03c_attached_leaf_probe as probe
    import time

    original_import = builtins.__import__

    def block(name, *args, **kwargs):
        level = args[3] if len(args) > 3 else kwargs.get('level', 0)
        if level == 0 and name.split('.')[0] in {'mujoco', 'taichi'}:
            raise AssertionError('runner closeout imported a native provider')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', block)
    native = tmp_path / 'native'
    native.mkdir()
    freeze = tmp_path / 'freeze'
    freeze.mkdir()
    (native / 'executed_contract.json').write_text('{}\n')
    (freeze / 'execution_freeze.json').write_text('{}\n')
    return probe, {
        'output_dir': tmp_path, 'native_dir': native,
        'snapshot': {'core_head': 'synthetic-closeout'},
        'contract': {'required_native_totals': {'materialization_attempts': 4, 'resets': 4}},
        'counters': {'materialization_attempts': 4, 'resets': 4, 'outer_intervals': 256,
                     'mj_step_calls': 1280, 'simulated_seconds': 2.56,
                     'mj_forward_calls': 260, 'max_rss_bytes': 1024},
        'identity': {'synthetic': True},
        'results': [{'episode_id': f'E{i}', 'transition_count': 64, 'observation_count': 65}
                    for i in range(1, 5)],
        'gain_comparison': {}, 'inventory': {'synthetic': True},
        'native_started_at': time.monotonic(),
    }


def test_runner_closeout_publishes_receipt_and_cli_summary(runner_closeout, monkeypatch, capsys):
    probe, facts = runner_closeout
    # CLI invokes the actual closeout used by run_native, including all file writes.
    monkeypatch.setattr(probe, 'run_native', lambda *args, **kwargs: probe._finish_native_run(**facts))
    probe.main(['--output-dir', str(facts['output_dir'])])
    summary = json.loads(capsys.readouterr().out)
    result = json.loads((facts['native_dir'] / 'native_result.json').read_text())
    progress = json.loads((facts['native_dir'] / 'native_progress.json').read_text())
    assert summary['status'] == result['status'] == 'NATIVE_S2_COMPLETE_AWAITING_HOST_OFFLINE_S3'
    assert summary['episodes'] == 4
    assert result['counters'] == facts['counters']
    assert result['resource_limits']['native_log_bytes'] > 0
    assert result['resource_limits']['output_bytes'] >= result['resource_limits']['native_log_bytes']
    assert result['executed_contract_sha256'] == probe._sha(facts['native_dir'] / 'executed_contract.json')
    assert result['execution_freeze_sha256'] == probe._sha(facts['output_dir'] / 'freeze/execution_freeze.json')
    assert progress['active']['phase'] == 'complete'
    assert not (facts['native_dir'] / 'native_result.pending.json').exists()


@pytest.mark.parametrize('change,error,match', [
    ({'materialization_attempts': 5}, RuntimeError, 'budget exceeded'),
    ({'resets': 5}, RuntimeError, 'budget exceeded'),
    ({'outer_intervals': 255}, ValueError, 'cumulative native counters'),
    ({'mj_step_calls': 1279}, ValueError, 'cumulative native counters'),
    ({'mj_forward_calls': 301}, ValueError, 'cumulative native counters'),
    ({'simulated_seconds': 2.55}, ValueError, 'cumulative native counters'),
])
def test_runner_closeout_rejects_invalid_counts(runner_closeout, change, error, match):
    probe, facts = runner_closeout
    facts['counters'].update(change)
    with pytest.raises(error, match=match):
        probe._finish_native_run(**facts)
    assert not (facts['native_dir'] / 'native_result.json').exists()


def test_runner_closeout_rejects_missing_episode(runner_closeout):
    probe, facts = runner_closeout
    facts['results'].pop()
    with pytest.raises(ValueError, match='H5 files are missing'):
        probe._finish_native_run(**facts)
    assert not (facts['native_dir'] / 'native_result.json').exists()


@pytest.mark.parametrize('location,size', [('native', 129 * 1024**2), ('output', 257 * 1024**2)])
def test_runner_closeout_budget_failure_never_publishes_success(runner_closeout, location, size):
    probe, facts = runner_closeout
    # Sparse file: exercises real stat accounting without writing hundreds of MiB.
    directory = facts['native_dir'] if location == 'native' else facts['output_dir']
    with (directory / 'synthetic-sparse-output').open('wb') as stream:
        stream.truncate(size)
    with pytest.raises(MemoryError, match='byte budget exceeded'):
        probe._finish_native_run(**facts)
    assert not (facts['native_dir'] / 'native_result.json').exists()


@pytest.mark.parametrize('failure', ['nonfinite', 'progress_write', 'receipt_write'])
def test_runner_closeout_failure_never_publishes_success(runner_closeout, monkeypatch, failure):
    probe, facts = runner_closeout
    if failure == 'nonfinite':
        facts['identity']['invalid'] = float('nan')
        error = ValueError
    else:
        error = OSError

        def fail(*args, **kwargs):
            raise OSError('synthetic closeout write failure')

        monkeypatch.setattr(probe, '_write_progress' if failure == 'progress_write' else '_write_json', fail)
    with pytest.raises(error):
        probe._finish_native_run(**facts)
    assert not (facts['native_dir'] / 'native_result.json').exists()


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


def _write_attached_recording(monkeypatch, tmp_path):
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
    return candidate, env


def test_attached_generic_h5_closes_and_independently_reads_back_without_native(monkeypatch, tmp_path):
    candidate, env = _write_attached_recording(monkeypatch, tmp_path)
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


@pytest.mark.parametrize('case', ('ack_target', 'ctrl_slot_permutation', 'near_failed_hand_close', 'zero_rotation'))
def test_attached_reader_rejects_coherent_corruption_and_failed_motion(monkeypatch, tmp_path, case):
    import h5py
    from task_env.recorders.h5 import _read_text
    from task_env.runtime.sessions.leaf_control import LeafPreparedCommandV1

    _, env = _write_attached_recording(monkeypatch, tmp_path)
    destination=tmp_path/f'coherent-{case}.h5'
    shutil.copy2(env.recording_path, destination)
    with h5py.File(destination, 'r+') as root:
        rows=json.loads(_read_text(root, 'meta/structured_controls_v1_json'))
        row=rows[0]['writer_controls'][0]
        if case=='ack_target':
            row['canonical_action']['application_ack']['target_identity_hash']='0'*64
            row['applied_control']['payload']['ack']['target_identity_hash']='0'*64
        elif case=='ctrl_slot_permutation':
            payload=row['canonical_action']['prepared_command']
            slots=payload['slot_values']
            slots[0]['ctrl_slot'],slots[1]['ctrl_slot']=slots[1]['ctrl_slot'],slots[0]['ctrl_slot']
            row['canonical_action']['command_identity_sha256']=LeafPreparedCommandV1.from_mapping(payload).command_identity_sha256
            row['applied_control']['payload']['applied_slots']=[item['ctrl_slot'] for item in slots]
        elif case=='near_failed_hand_close':
            root['obs/state/entities/panda-hand/joint_position'][16:33]=[[0.01000025]*2]*17
        else:
            root['obs/state/entities/panda-hand/hand_pose'][0,3:7]=[0.0]*4
        if case in ('ack_target', 'ctrl_slot_permutation'):
            del root['meta/structured_controls_v1_json']
            root.create_dataset('meta/structured_controls_v1_json',data=json.dumps(rows),
                                dtype=h5py.string_dtype(encoding='utf-8'))
    with pytest.raises(ValueError):
        load_leaf_control_records_h5(destination)
