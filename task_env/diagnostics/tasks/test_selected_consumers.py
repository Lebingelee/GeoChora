"""S2-A consumer boundaries; synthetic stepping never grants native acceptance."""
from dataclasses import replace
from types import SimpleNamespace
import sys
import json
import numpy as np
import pytest

from task_env import make_env
from task_env.artifacts import CanonicalStateView, PoseWorld
from task_env.artifacts.execution import RealizedInitialState
from task_env.controllers.canonical.contracts import AppliedCanonicalControl
from task_env.controllers.canonical.feedback import CanonicalControlFeedback, CanonicalGripperFeedback
from task_env.controllers.canonical.kinematics import ARM, FINGERS, PandaKinematics
from task_env.runtime.sessions.common import _SessionValues
from task_env.tasks.nut_assembly.solution import ReferenceArmSchedule, ArmRampMemory
from task_env.tasks.reference_env import SelectedReferenceEnv

IDS = ('pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1')


class FakeSession(_SessionValues):
    """Frozen physical state, real canonical controller and five native ticks."""
    def __init__(self, artifact, execution, *, source, binding):
        self._initialize_values(artifact, source, execution.physics_provider)
        self.model = PandaKinematics(source.scene_source.xml)
        self.time = 0.; self.calls = []; self.closed = False
    def reset(self, sample):
        self._validate_sample(sample)
        self.q = dict(sample.joint_position)
        self.poses = dict(sample.poses_world)
        # Authored fixed peg is not part of the free-body reset sample.
        self.poses.update({k: v for k, v in self._artifact.initialization.poses_world.items() if k not in self.poses})
        self.poses['panda-v1/ee'] = self.model.pose(np.array([self.q[k] for k in ARM]))
        if 'square-nut-v1' in self.poses:
            self.poses.setdefault('square-peg-v1', PoseWorld((.58,.045,.5),(1.,0.,0.,0.)))
        self._reset_done = True
        return RealizedInitialState('realized-initial-state-v0', sample.sample_id, self._provider, self.snapshot(), 0)
    def snapshot(self):
        return self._state(self.q, {k:0. for k in self.q}, self.poses, self.time if self._inner_interval_active else self._control_step*.01)
    def control_feedback(self, state):
        return CanonicalControlFeedback('canonical-control-feedback-v0', state.control_step, state.simulation_time,
            CanonicalGripperFeedback('panda-v1/gripper', sum(state.joint_position[k] for k in FINGERS), 0.))
    def apply_control(self, target):
        self.calls.append(target)
        return AppliedCanonicalControl('applied-canonical-control-v0', target.identity_hash, self._provider,
            dict(target.arm_servo_position), target.gripper.servo_opening_m, target.gripper.force_limit_N, False, 'synthetic')
    def step(self):
        self.time += .01;self._control_step += 1
        return self.snapshot()
    def _step_physics_once(self): self.time += .002
    def close(self): self._closed = self.closed = True


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr('task_env.tasks.reference_env.materialize_control', FakeSession)
    monkeypatch.setattr('task_env.runtime.sessions.provenance.provider_build_identity', lambda provider: {'synthetic_provider':provider})


@pytest.mark.parametrize('uid', IDS)
@pytest.mark.parametrize('provider', ['geophys', 'mujoco'])
def test_actual_factory_reset_expert_recording_and_teardown(uid, provider, fake, tmp_path):
    from task_env.trajectory.canonical.execution import load
    env = make_env(uid, config={'provider':provider, 'horizon':3})
    obs, info = env.reset(seed=19)
    assert env.observation_space.contains(obs)
    assert env.state.control_step == 0
    path = tmp_path/'fresh.h5'
    env.start_recording(path)
    for _ in range(3): env.step_expert()
    assert env._stopped
    assert env.state.control_step == 3
    assert len(env.session.calls) == (3 if env.binding.interval_mode == 'grouped' else 15)
    with pytest.raises(RuntimeError): env.step_expert()
    result = env.finish_recording('bounded_truncation')
    assert result.get('byte_exact', result.get('logical_mapping_exact'))
    if env.binding.recorder_mode == 'canonical':
        from task_env.trajectory.canonical.h5 import load as load_outer
        outer = load_outer(path).to_mapping()
        value = {**outer, 'recipe': {'d0_reconstructible':False}}
    else:
        value = load(path)
    assert len(value['transitions']) == 3 and len(value['boundaries']) == 4
    assert not value['recipe']['d0_reconstructible']
    assert value['metadata']['task_artifact_hash'] == env.artifact.identity_hash
    if env.binding.recorder_mode == 'execution':
        assert env.info['readiness_warnings'] == []
        assert not env.info['outcome_complete']
        assert env.info['original_expert_lifecycle_status']
        assert env.value['execution_policy']['policy_id'] == 'nutassembly-outcome-oriented-completion-v1'
    old = env.session
    env.reset(seed=19)
    assert old.closed
    assert env.state.control_step == 0
    env.close()
    with pytest.raises(RuntimeError): env.reset(seed=19)


@pytest.mark.parametrize('old', ['pick-cube-v1', 'nut-assembly-square-v1'])
def test_no_silent_uid_or_public_class_alias(old):
    with pytest.raises(ValueError, match='legacy'): make_env(old)
    from task_env.registry import ENV_REGISTRY
    assert old not in ENV_REGISTRY.uids()
    import task_env
    assert not hasattr(task_env, 'PickCubeEnv') and not hasattr(task_env, 'NutAssemblyEnv')


@pytest.mark.parametrize('config', [{'runtime':{'control_substeps':20}}, {'backend':'cuda'},
    {'provider':'genesis'}, {'horizon':0}, {'horizon':True}, {'force_limit_N':30.}])
def test_incompatible_config_rejected_before_materialization(config):
    with pytest.raises(ValueError): make_env(IDS[1], config=config)


@pytest.mark.parametrize('uid', IDS)
def test_external_expert_modes_and_invalid_actions(uid, fake):
    env = make_env(uid);env.reset(seed=19)
    with pytest.raises((ValueError, RuntimeError)): env.step(np.full(8, np.nan))
    assert env.state.control_step == 0
    if env.binding.external_actions:
        with pytest.raises(RuntimeError): env.step_expert()
    else:
        assert env._episode_mode is None  # no unguarded Nut action entered execution
        env.step_expert()
    env.reset(seed=19);env.step_expert()
    with pytest.raises(RuntimeError): env.step(np.zeros(8))
    env.close()


def test_arm_schedule_matches_historical_interpolation_and_ack_memory():
    from task_env.tasks.nut_assembly.task import build_reference
    from task_env.controllers.canonical.contracts import CanonicalControlTarget, GripperControlTarget
    value = build_reference()
    solution = SimpleNamespace(_lift_released=True)
    memory = ArmRampMemory({k:.1 for k in ARM})
    schedule = ReferenceArmSchedule(solution, memory)
    target = CanonicalControlTarget('canonical-control-v0', value['artifact'].identity_hash,
        value['controller_identity'], ARM, {k:.4 for k in ARM}, {k:.4 for k in ARM},
        GripperControlTarget('panda-v1/gripper', .08, 10., .08))
    schedule.begin(target)
    for i in range(5):
        effective = schedule.target(target, i, 5)
        assert effective.arm_servo_position == {k:.1+(i+1)/5*(.4-.1) for k in ARM}
        schedule.applied(SimpleNamespace(arm_servo_position=effective.arm_servo_position))
    assert memory.last_applied_arm == dict(target.arm_servo_position)
    with pytest.raises(ValueError): ReferenceArmSchedule(solution, ArmRampMemory()).begin(target)


def test_active_imports_do_not_load_diagnostics_or_native(tmp_path):
    import subprocess, os
    code = "from task_env import make_env; make_env('nut-assembly-outcome-reference-v1').close(); import sys; assert not any(k.startswith(('task_env.diagnostics','mujoco','taichi')) for k in sys.modules)"
    result = subprocess.run([sys.executable, '-c', code], env={**os.environ,'PYTHONPATH':str(__import__('pathlib').Path.cwd())}, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_task_bindings_declare_selected_control_and_recording_requirements():
    pickcube = make_env(IDS[0])
    nutassembly = make_env(IDS[1])
    assert (pickcube.binding.interval_mode, pickcube.binding.recorder_mode,
            pickcube.binding.external_actions) == ('grouped', 'canonical', True)
    assert (nutassembly.binding.interval_mode, nutassembly.binding.recorder_mode,
            nutassembly.binding.external_actions, nutassembly.binding.record_native_substeps,
            nutassembly.binding.capture_guard_samples) == ('native', 'execution', False, True, True)
    assert nutassembly.value['construction_id'] == 'nut-assembly-outcome-reference-v1'
    pickcube.close()
    nutassembly.close()


def test_reporter_and_expert_factory_use_selected_owner(fake):
    from task_env.reporter.real_taskenv_tcp_fixture import _config
    from task_env.reporter.real_taskenv_v2_tcp_fixture import _config as config2
    for uid in IDS:
        env = make_env(uid, config={'provider': 'geophys', 'backend': 'cpu', 'horizon': 5})
        assert env.uid == uid
        assert env.artifact.identity_hash == env.metadata['task_artifact_hash']
        assert env.solution.identity
        env.close()
    assert _config() == config2() == {'provider':'geophys', 'backend':'cpu', 'horizon':8}


@pytest.mark.parametrize('uid', IDS)
def test_current_source_reexecution_uses_selected_factory(uid, fake, tmp_path):
    from task_env.trajectory.reference_replay import reexecute_selected
    env=make_env(uid, config={'provider':'mujoco','horizon':3})
    env.reset(seed=19);env.start_recording(tmp_path/'source.h5')
    while not env._stopped:env.step_expert()
    env.finish_recording('bounded_truncation');env.close()
    report=reexecute_selected(tmp_path/'source.h5',output=tmp_path/'reexecution.h5')
    assert report['status']=='PASS' and report['transitions']==3
    assert report['D0']=='NOT_ASSESSED'


def test_nut_reset_provenance_is_not_silently_relabelled(fake):
    env=make_env(IDS[1])
    with pytest.raises(ValueError, match='seed19'):env.reset(seed=31)
    env.close()


def test_metadata_ownership_is_per_environment():
    a=make_env(IDS[0]);b=make_env(IDS[0])
    a.metadata['action_schema']['dimension']=999
    assert b.metadata['action_schema']['dimension']==8
    a.close();b.close()


def test_c05b_public_solution_lifecycle_and_control_ack_match_internal(fake, tmp_path):
    from task_env.planners.completion import ExpertExecutionInfo
    from task_env.tasks.pick_cube import build_readiness_solution

    internal = make_env(IDS[0], config={'provider':'geophys','horizon':3})
    external = make_env(IDS[0], config={'provider':'geophys','horizon':3})
    try:
        _, internal_reset = internal.reset(seed=19)
        solution = build_readiness_solution()
        _, external_reset = external.reset_for_solution(solution, seed=19)
        first_episode_id = external_reset['expert_execution_boundary_v1']['episode_id']
        _, external_reset = external.reset_for_solution(solution, seed=19)
        assert external_reset['expert_execution_boundary_v1']['episode_id'] != first_episode_id

        for info in (internal_reset, external_reset):
            execution = ExpertExecutionInfo.from_mapping(info['expert_execution_info_v1'])
            execution.validate()
            assert execution.control_step == 0 and execution.simulation_time == 0.
            assert info['control_readiness_v1'] == execution.control_readiness.to_mapping()
            assert info['expert_execution_boundary_v1']['control_step'] == 0
            assert info['expert_execution_boundary_v1']['episode_id']
            assert 'control_application_v1' not in info
        assert external.solution is None  # external instance owns all mutable stage state
        assert external.expert_execution_info().control_readiness.to_mapping() == external_reset['control_readiness_v1']
        internal.start_recording(tmp_path/'internal.h5')
        external.start_recording(tmp_path/'external.h5')

        append_order = []
        append = external.recorder.append

        def observe_before_append(*args, **kwargs):
            append_order.append((solution._awaiting_observation, solution.total_control_actions_emitted))
            return append(*args, **kwargs)

        external.recorder.append = observe_before_append
        internal_result = internal.step_expert()
        external_result = external.step_with_solution(solution)
        assert append_order == [(False, 1)]
        np.testing.assert_array_equal(internal_result[0]['state']['ee_pose'], external_result[0]['state']['ee_pose'])
        assert internal_result[1:4] == external_result[1:4]
        external_calls = len(external.session.calls)
        with pytest.raises(RuntimeError, match='cannot.*mix'):
            external.step(np.zeros(8))
        with pytest.raises(RuntimeError, match='cannot.*mix'):
            external.step_expert()
        assert external.state.control_step == 1 and len(external.session.calls) == external_calls

        for env, result in ((internal, internal_result), (external, external_result)):
            info = result[4]
            application = info['control_application_v1']
            assert application['schema_version'] == 'selected-control-application-v1'
            assert application['request_boundary']['control_step'] == 0
            assert application['evaluation_boundary']['control_step'] == 1
            assert application['request_boundary']['episode_id'] == info['expert_execution_boundary_v1']['episode_id']
            assert application['target_identity_hash'] == application['applied_target_hash']
            assert application['target_identity_hash'] == application['applied']['target_hash']
            assert application['task_artifact_hash'] == env.artifact.identity_hash
            assert application['controller_identity'] == env.controller.identity
            assert info['expert_execution_boundary_v1']['control_step'] == 1
            assert not info['is_success']
            assert not info['selected_policy_execution_complete']
            assert len(env.recorder.transitions) == 1
            assert len(env.recorder.boundaries) == 2
        left = internal.recorder.transitions[0]
        right = external.recorder.transitions[0]
        assert left.requested_action == right.requested_action
        assert left.controller_target == right.controller_target
        assert left.applied_control == right.applied_control
        assert internal.finish_recording('c05b-s1')['logical_mapping_exact']
        assert external.finish_recording('c05b-s1')['logical_mapping_exact']
    finally:
        internal.close()
        external.close()


@pytest.mark.parametrize('damage', ['missing', 'stale', 'wrong_boundary'])
def test_c05b_invalid_public_readiness_rejects_before_solution_or_control(damage, fake):
    from task_env.tasks.pick_cube import build_readiness_solution

    env = make_env(IDS[0], config={'provider':'geophys','horizon':3})
    solution = build_readiness_solution()
    try:
        env.reset_for_solution(solution, seed=19)
        if damage == 'missing':
            env.info.pop('expert_execution_info_v1')
        elif damage == 'stale':
            env.info['expert_execution_info_v1']['simulation_time'] = .01
        else:
            env.info['expert_execution_boundary_v1']['source_id'] = 'wrong-source'
        compute_calls = []
        compute = env.controller.compute

        def count_compute(*args, **kwargs):
            compute_calls.append(True)
            return compute(*args, **kwargs)

        env.controller.compute = count_compute
        with pytest.raises((ValueError, TypeError)):
            env.step_with_solution(solution)
        assert env.execution_fault.phase == 'public_execution_readiness'
        assert env.state.control_step == 0 and env.state.simulation_time == 0.
        assert not env.session.calls and not compute_calls
        assert solution.total_control_actions_emitted == 0
        with pytest.raises(RuntimeError, match='faulted'):
            env.step_with_solution(solution)
        assert not env.session.calls and not compute_calls
    finally:
        env.close()


def test_c05b_foreign_solution_identity_rejects_before_reset(fake):
    from task_env.tasks.pick_cube import build_readiness_solution

    env = make_env(IDS[0], config={'provider':'geophys','horizon':3})
    foreign = build_readiness_solution()
    foreign.identity = 'f' * 64
    try:
        with pytest.raises(ValueError, match='identity'):
            env.reset_for_solution(foreign, seed=19)
        assert env.session is None
        assert env.execution_fault is None
    finally:
        env.close()


def test_c05b_observer_failure_latches_before_recorder_append(fake, tmp_path):
    from task_env.tasks.pick_cube import build_readiness_solution

    env = make_env(IDS[0], config={'provider':'geophys','horizon':3})
    solution = build_readiness_solution()
    try:
        env.reset_for_solution(solution, seed=19)
        env.start_recording(tmp_path/'observer-fault.h5')
        append_calls = []
        env.recorder.append = lambda *args, **kwargs: append_calls.append(True)

        def fail_observe(*args, **kwargs):
            raise RuntimeError('injected external observe failure')

        solution.observe = fail_observe
        with pytest.raises(RuntimeError, match='external observe failure'):
            env.step_with_solution(solution)
        assert env.execution_fault.phase == 'solution_observation'
        assert env.execution_fault.physical_progress == 'advanced'
        assert env.execution_fault.transition_status == 'incomplete'
        assert env.state.control_step == 1 and len(env.session.calls) == 1
        assert not env.recorder.transitions and len(env.recorder.boundaries) == 1
        assert not append_calls
        with pytest.raises(RuntimeError, match='faulted'):
            env.step_with_solution(solution)
        assert env.state.control_step == 1 and len(env.session.calls) == 1
    finally:
        env.close()


def test_c05b_recorder_append_failure_latches_after_observe_without_valid_transition(fake, tmp_path):
    from task_env.tasks.pick_cube import build_readiness_solution

    env = make_env(IDS[0], config={'provider':'geophys','horizon':3})
    solution = build_readiness_solution()
    try:
        env.reset_for_solution(solution, seed=19)
        env.start_recording(tmp_path/'append-fault.h5')
        append_observations = []

        def fail_append(*args, **kwargs):
            append_observations.append((solution._awaiting_observation, solution.total_control_actions_emitted))
            raise RuntimeError('injected canonical Recorder append failure')

        env.recorder.append = fail_append
        with pytest.raises(RuntimeError, match='Recorder append failure'):
            env.step_with_solution(solution)
        assert append_observations == [(False, 1)]
        assert env.execution_fault.phase == 'record_interval'
        assert env.execution_fault.physical_progress == 'advanced'
        assert env.execution_fault.transition_status == 'rejected'
        assert env.state.control_step == 1 and len(env.session.calls) == 1
        assert not env.recorder.transitions and len(env.recorder.boundaries) == 1
        with pytest.raises(RuntimeError, match='faulted'):
            env.step_with_solution(solution)
        assert env.state.control_step == 1 and len(env.session.calls) == 1
    finally:
        env.close()


def test_failed_reset_closes_old_runtime_and_requires_new_reset(fake):
    env=make_env(IDS[1]);env.reset(seed=19);old=env.session
    with pytest.raises(ValueError):env.reset(seed=31)
    assert old.closed and env.session is None and env._stopped
    assert env.execution_fault.phase == 'reset_seed'
    assert env.execution_fault.physical_progress == 'not_advanced'
    with pytest.raises(RuntimeError):env.step_expert()
    env.reset(seed=19);env.step_expert();env.close()


def test_native_partial_interval_fault_is_recorded_without_a_transition(fake, tmp_path):
    env=make_env(IDS[1], config={'provider':'mujoco','horizon':4})
    env.reset(seed=19)
    env.start_recording(tmp_path/'partial-interval.h5')
    completed_substeps=[]

    def fail_during_second_native_step():
        if not completed_substeps:
            env.session.time += .002
            completed_substeps.append(1)
            return
        raise RuntimeError('injected native-step failure after one completed step')

    env.session._step_physics_once=fail_during_second_native_step
    with pytest.raises(RuntimeError, match='native-step failure'):
        env.step_expert()

    receipt=env.execution_fault
    assert receipt.phase == 'physics_step'
    # The FakeSession exposes only its last completed control boundary here.
    # One observer/Recorder receipt conflicts with that unchanged public clock,
    # so physical progress must stay unknown instead of being inferred from a
    # callback count.
    assert receipt.physical_progress == 'unknown'
    assert receipt.observer_confirmed_substeps == 1
    assert receipt.recorder_confirmed_substeps == 1
    assert receipt.native_substeps_expected == env.artifact.timebase.control_substeps
    assert receipt.transition_status == 'incomplete'
    assert receipt.interval_attempted and not receipt.interval_completed
    assert env.recorder.pending is not None
    assert env.recorder.pending['native_step_count'] == 1
    assert env.recorder.value['transitions'] == []
    assert len(env.recorder.value['boundaries']) == 1
    with pytest.raises(RuntimeError, match='faulted; reset'):
        env.step_expert()
    with pytest.raises(ValueError, match='incomplete effective interval'):
        env.finish_recording('failed')
    with pytest.raises(RuntimeError, match='finalize current recording before reset'):
        env.reset(seed=19)
    env.close()


def _expose_fake_physics_clock(env, *, should_fail=None):
    from dataclasses import replace

    original_snapshot = env.session.snapshot

    def public_snapshot():
        if should_fail is not None and should_fail():
            raise RuntimeError('injected public clock readback failure')
        state = original_snapshot()
        return replace(state, simulation_time=float(env.session.time))

    env.session.snapshot = public_snapshot


def _assert_faulted_recording_has_no_transition(env, *, transition_status='incomplete'):
    assert env.execution_fault.transition_status == transition_status
    assert env.recorder.value['transitions'] == []
    assert env.recorder.pending is not None
    with pytest.raises(ValueError, match='incomplete effective interval'):
        env.finish_recording('failed')
    with pytest.raises(RuntimeError, match='faulted; reset'):
        env.step_expert()


def test_native_last_substep_advances_then_raises_uses_public_clock(fake, tmp_path):
    env=make_env(IDS[1], config={'provider':'mujoco','horizon':4})
    env.reset(seed=19)
    env.start_recording(tmp_path/'last-step-raised.h5')
    _expose_fake_physics_clock(env)
    expected=env.artifact.timebase.control_substeps
    calls=0
    original_step=env.session._step_physics_once

    def advance_then_raise_on_last():
        nonlocal calls
        calls += 1
        if calls == expected:
            env.session.time += env.artifact.timebase.physics_dt
            raise RuntimeError('injected failure after last physical advancement')
        original_step()

    env.session._step_physics_once=advance_then_raise_on_last
    with pytest.raises(RuntimeError, match='last physical advancement'):
        env.step_expert()

    receipt=env.execution_fault
    assert receipt.physical_progress == 'advanced'
    assert receipt.observer_confirmed_substeps == expected - 1
    assert receipt.recorder_confirmed_substeps == expected - 1
    assert receipt.simulation_time_after_s - receipt.simulation_time_before_s == pytest.approx(
        env.artifact.timebase.control_dt
    )
    _assert_faulted_recording_has_no_transition(env)
    env.close()


def test_native_mid_interval_advance_then_raise_reports_partial_clock(fake, tmp_path):
    env=make_env(IDS[1], config={'provider':'mujoco','horizon':4})
    env.reset(seed=19)
    env.start_recording(tmp_path/'mid-step-raised.h5')
    _expose_fake_physics_clock(env)
    calls=0
    original_step=env.session._step_physics_once

    def advance_then_raise_mid_interval():
        nonlocal calls
        calls += 1
        if calls == 2:
            env.session.time += env.artifact.timebase.physics_dt
            raise RuntimeError('injected mid-interval physical advancement failure')
        original_step()

    env.session._step_physics_once=advance_then_raise_mid_interval
    with pytest.raises(RuntimeError, match='mid-interval physical advancement'):
        env.step_expert()

    receipt=env.execution_fault
    assert receipt.physical_progress == 'partially_advanced'
    assert receipt.observer_confirmed_substeps == 1
    assert receipt.recorder_confirmed_substeps == 1
    assert receipt.simulation_time_after_s - receipt.simulation_time_before_s == pytest.approx(
        2 * env.artifact.timebase.physics_dt
    )
    _assert_faulted_recording_has_no_transition(env)
    env.close()


def test_unreadable_fault_boundary_keeps_counts_but_progress_unknown(fake, tmp_path):
    env=make_env(IDS[1], config={'provider':'mujoco','horizon':4})
    env.reset(seed=19)
    env.start_recording(tmp_path/'unreadable-boundary.h5')
    faulted=False
    _expose_fake_physics_clock(env, should_fail=lambda: faulted)
    original_step=env.session._step_physics_once
    calls=0

    def fail_second_step_before_advancing():
        nonlocal calls, faulted
        calls += 1
        if calls == 2:
            faulted=True
            raise RuntimeError('injected mid-interval provider failure')
        original_step()

    env.session._step_physics_once=fail_second_step_before_advancing
    with pytest.raises(RuntimeError, match='mid-interval provider failure'):
        env.step_expert()

    receipt=env.execution_fault
    assert receipt.physical_progress == 'unknown'
    assert receipt.observer_confirmed_substeps == 1
    assert receipt.recorder_confirmed_substeps == 1
    assert receipt.readback_error.startswith('RuntimeError: injected public clock')
    _assert_faulted_recording_has_no_transition(env)
    env.close()


def test_full_physics_with_missing_final_recorder_receipt_is_not_a_transition(fake, tmp_path):
    env=make_env(IDS[1], config={'provider':'mujoco','horizon':4})
    env.reset(seed=19)
    env.start_recording(tmp_path/'missing-final-recorder-receipt.h5')
    _expose_fake_physics_clock(env)
    expected=env.artifact.timebase.control_substeps
    original_record=env.recorder.applied_substep

    def fail_final_recorder_receipt(index, *args):
        if index == expected - 1:
            raise RuntimeError('injected final Recorder receipt failure')
        return original_record(index, *args)

    env.recorder.applied_substep=fail_final_recorder_receipt
    with pytest.raises(RuntimeError, match='final Recorder receipt failure'):
        env.step_expert()

    receipt=env.execution_fault
    assert receipt.physical_progress == 'advanced'
    assert receipt.observer_confirmed_substeps == expected
    assert receipt.recorder_confirmed_substeps == expected - 1
    assert receipt.transition_status == 'incomplete'
    assert receipt.interval_completed is False
    _assert_faulted_recording_has_no_transition(env)
    env.close()


def test_full_physics_with_silent_recorder_omission_cannot_append_transition(fake, tmp_path):
    env=make_env(IDS[1], config={'provider':'mujoco','horizon':4})
    env.reset(seed=19)
    env.start_recording(tmp_path/'silent-recorder-omission.h5')
    _expose_fake_physics_clock(env)
    expected=env.artifact.timebase.control_substeps
    original_record=env.recorder.applied_substep

    def omit_final_recorder_receipt(index, *args):
        if index == expected - 1:
            return None
        return original_record(index, *args)

    env.recorder.applied_substep=omit_final_recorder_receipt
    with pytest.raises(ValueError, match='incomplete native Recorder application receipts'):
        env.step_expert()

    receipt=env.execution_fault
    assert receipt.phase == 'record_interval'
    assert receipt.physical_progress == 'advanced'
    assert receipt.observer_confirmed_substeps == expected
    assert receipt.recorder_confirmed_substeps == expected - 1
    assert receipt.interval_completed is True
    assert receipt.transition_status == 'rejected'
    assert env.recorder.pending['native_step_count'] == expected - 1
    _assert_faulted_recording_has_no_transition(env, transition_status='rejected')
    env.close()


def test_conflicting_recorder_counter_is_unknown_and_cannot_append_transition(fake, tmp_path):
    env=make_env(IDS[1], config={'provider':'mujoco','horizon':4})
    env.reset(seed=19)
    env.start_recording(tmp_path/'conflicting-recorder-counter.h5')
    _expose_fake_physics_clock(env)
    expected=env.artifact.timebase.control_substeps
    original_record=env.recorder.applied_substep

    def conflict_final_counter(index, *args):
        result=original_record(index, *args)
        if index == expected - 1:
            env.recorder.pending['native_step_count'] += 1
        return result

    env.recorder.applied_substep=conflict_final_counter
    with pytest.raises(ValueError, match='incomplete native Recorder application receipts'):
        env.step_expert()

    receipt=env.execution_fault
    assert receipt.physical_progress == 'advanced'
    assert receipt.observer_confirmed_substeps == expected
    assert receipt.recorder_confirmed_substeps is None
    assert receipt.transition_status == 'rejected'
    assert env.recorder.pending['native_step_count'] == expected + 1
    assert len(env.recorder.pending['substeps']) == expected
    _assert_faulted_recording_has_no_transition(env, transition_status='rejected')
    env.close()


def test_full_physics_with_invalid_post_boundary_keeps_transition_uncommitted(fake, tmp_path):
    env=make_env(IDS[1], config={'provider':'mujoco','horizon':4})
    env.reset(seed=19)
    env.start_recording(tmp_path/'invalid-post-boundary.h5')
    _expose_fake_physics_clock(env)
    expected=env.artifact.timebase.control_substeps

    class InvalidBoundary:
        def to_mapping(self):
            raise RuntimeError('injected post-boundary serialization failure')

    env._boundary=lambda: InvalidBoundary()
    with pytest.raises(RuntimeError, match='post-boundary serialization failure'):
        env.step_expert()

    receipt=env.execution_fault
    assert receipt.physical_progress == 'advanced'
    assert receipt.observer_confirmed_substeps == expected
    assert receipt.recorder_confirmed_substeps == expected
    assert receipt.transition_status == 'rejected'
    assert env.recorder.value['transitions'] == []
    assert len(env.recorder.value['boundaries']) == 1
    assert env.recorder.pending['native_step_count'] == expected
    _assert_faulted_recording_has_no_transition(env, transition_status='rejected')
    env.close()


def test_expert_proposal_exception_faults_before_physics_and_blocks_step(fake):
    env=make_env(IDS[0]);env.reset(seed=19)

    def fail_proposal():
        raise RuntimeError('injected expert proposal failure')

    env.solution.act=fail_proposal
    with pytest.raises(RuntimeError, match='expert proposal failure'):
        env.step_expert()
    assert env.execution_fault.phase == 'expert_proposal'
    assert env.execution_fault.physical_progress == 'not_advanced'
    applied_calls=len(env.session.calls)
    with pytest.raises(RuntimeError, match='faulted; reset'):
        env.step_expert()
    assert len(env.session.calls) == applied_calls
    env.close()


def test_task_success_does_not_stop_expert_before_solution_completion(fake):
    from task_env.environment.types import TaskEvaluation

    class Expert:
        done=False
        failed=False
        failure_reason=None
        def __init__(self, action):
            self.action=action
            self.observed=0
        def act(self):
            return SimpleNamespace(stage='post_success', diagnostics={}, action=self.action)
        def observe(self, *_args, **_kwargs):
            self.observed += 1
            self.done = self.observed == 2

    env=make_env(IDS[0]);env.reset(seed=19)
    ee=env.state.pose_world['panda-v1/ee']
    expert=Expert(np.asarray((*ee.position,*ee.quaternion_wxyz,0.0),dtype=float))
    env.solution=expert
    original_observation=env.observation
    def successful_observation(state):
        obs, info, _ = original_observation(state)
        info['is_success']=True
        return obs, info, TaskEvaluation(reward=1.0,success=True,failure=False)
    env.observation=successful_observation

    first=env.step_expert()
    assert first[2] is False
    assert first[4]['is_success'] is True
    assert not env._stopped
    second=env.step_expert()
    assert second[2] is False
    assert second[4]['is_success'] is True
    assert expert.done and expert.observed == 2 and env._stopped
    assert env.state.control_step == 2
    env.close()


def test_nutassembly_public_example_does_not_admit_external_gripper_actions():
    env=make_env(IDS[1])
    try:
        assert env.binding.external_actions is False
        with pytest.raises(RuntimeError, match='requires step_expert'):
            env.step(np.zeros(8))
    finally:
        env.close()


def test_example_completion_reports_task_outcome_and_expert_status_separately():
    from examples._common import episode_result

    class Solution:
        done = True
        failed = False
        failure_reason = None
        def outcome_report(self):
            return {'planned_trajectory_completed': True, 'outcome_complete': True,
                    'unapproved_override_used': False, 'expert_complete': False,
                    'readiness_warnings': ['stable_height_mismatch']}

    env=SimpleNamespace(solution=Solution(),info={'is_success':True,
        'task_metrics':{'task_success':True},'original_expert_lifecycle_status':{
            'policy':'original-guarded-v2-v5-strict-gates', 'expert_complete':False,
            'expert_failed':True, 'failure_reason':'stable_height_mismatch'}})
    report=episode_result(env,info=env.info,transitions=11)
    assert report['status']=='PASS' and report['task_success'] is True
    assert report['expert_complete'] is False and report['outcome_complete'] is True
    assert report['original_expert_lifecycle_status']['expert_complete'] is False


def test_planning_cli_keeps_outcome_success_separate_from_strict_expert_lifecycle():
    from task_env.script.trajectory.planning._common import _completion_fields

    class OutcomeSolution:
        done = True
        failed = False

        def __init__(self, complete=True):
            self.complete = complete

        def outcome_report(self):
            return {'planned_trajectory_completed': self.complete, 'outcome_complete': self.complete,
                    'unapproved_override_used': False, 'expert_complete': False,
                    'readiness_warnings': ['stable_height_mismatch']}

    fields = _completion_fields(OutcomeSolution(), {
        'is_success': True,
        'task_metrics': {'task_success': True},
        'original_expert_lifecycle_status': {
            'policy': 'original-guarded-v2-v5-strict-gates', 'expert_complete': False,
            'expert_failed': True, 'failure_reason': 'stable_height_mismatch',
        },
    }, terminated=False, truncated=False)
    assert fields['success'] is True
    assert fields['task_success'] is True
    assert fields['expert_complete'] is False
    assert fields['outcome_complete'] is True
    assert fields['original_expert_lifecycle_status']['expert_complete'] is False
    assert fields['readiness_warnings'] == ['stable_height_mismatch']

    incomplete = _completion_fields(OutcomeSolution(complete=False), {
        'is_success': True, 'task_metrics': {'task_success': True},
    }, terminated=False, truncated=False)
    assert incomplete['success'] is False
    assert _completion_fields(OutcomeSolution(), {
        'is_success': True, 'task_metrics': {'task_success': True},
    }, terminated=True, truncated=False)['success'] is False


def test_recording_example_finalizes_failed_task_h5_and_returns_nonzero(fake, tmp_path, monkeypatch, capsys):
    from contextlib import nullcontext
    import task_env
    from examples.recording import record_expert
    monkeypatch.setattr(record_expert, 'bounded_process', lambda *args: nullcontext({'bounded_test': True}))
    monkeypatch.setattr(task_env, 'make_env', lambda uid, config=None: make_env(uid, config=config))
    output=tmp_path/'failed-current-route.h5'
    code=record_expert.main(['--env-id', IDS[0], '--provider', 'mujoco', '--horizon', '3',
        '--output', str(output), '--time-limit-s', '10', '--memory-limit-mb', '1024'])
    result=json.loads(capsys.readouterr().out)
    assert code==1 and result['status']=='FAIL'
    assert output.exists() and result['roundtrip']=='PASS'
    assert result['recording']['transitions']==3 and result['recording']['boundaries']==4
    assert result['recording']['t_plus_one_valid'] is True


def test_retired_phase_i_and_grouped_trajectory_commands_fail_explicitly(capsys):
    from task_env.script import stage11, stage11_socket
    from task_env.script.trajectory.commands import main as trajectory_main
    assert stage11.main([])==2
    assert stage11_socket.main([])==2
    assert trajectory_main(['--historical-grouped'])==2
    message=capsys.readouterr().err
    assert 'p2_0_s4_5_a_source_recovery.json' in message and 'No task UID' in message


def test_removed_task_plan_and_private_recorder_exports_are_not_active():
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module('task_env.script.trajectory._task_plans')
    import task_env.script.recorder as recorder
    import task_env.script.trajectory as trajectory
    assert recorder.__all__==['main']
    assert not hasattr(trajectory, '_build_plan')
    assert not hasattr(recorder, '_pick_cube_config')
