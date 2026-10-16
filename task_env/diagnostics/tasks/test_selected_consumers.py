"""S2-A consumer boundaries; synthetic stepping never grants native acceptance."""
from dataclasses import replace
from types import SimpleNamespace
import sys
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
    from task_env.script.trajectory._task_plans import _build_plan
    for uid in IDS:
        cfg, solution = _build_plan(uid, 'cpu', 5)
        env = make_env(uid, config=cfg)
        assert type(env.solution) is type(solution)
        env.close()
    assert _config() == config2() == {'provider':'geophys', 'backend':'cpu', 'horizon':8}
    with pytest.raises(ValueError): _build_plan(IDS[1], 'cpu', 5, force_limit_N=30.)


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


def test_failed_reset_closes_old_runtime_and_requires_new_reset(fake):
    env=make_env(IDS[1]);env.reset(seed=19);old=env.session
    with pytest.raises(ValueError):env.reset(seed=31)
    assert old.closed and env.session is None and env._stopped
    with pytest.raises(RuntimeError):env.step_expert()
    env.reset(seed=19);env.step_expert();env.close()
