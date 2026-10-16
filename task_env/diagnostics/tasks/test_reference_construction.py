"""S1 independent pre-change values and defect-sensitive, provider-free oracles."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from task_env.artifacts import CanonicalStateView, PoseWorld
from task_env.tasks.pick_cube import reference as pc
from task_env.tasks.nut_assembly import reference as na
from task_env.tasks.pick_cube.canonical_semantics import evaluate as pc_evaluate
from task_env.tasks.nut_assembly.canonical_semantics import evaluate as na_evaluate
from task_env.tasks.nut_assembly.canonical_reset import sample_reset as na_reset

ROOT = Path(__file__).resolve().parents[3]
BASELINE = json.loads(Path(__file__).with_name('reference_construction_baseline.json').read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def assert_source(value, expected):
    assert value['artifact'].identity_hash == expected['artifact_hash']
    assert digest(asdict(value['source'].config)) == expected['source_config_sha256']
    xml = value['source'].scene_source.xml.replace(str(ROOT), '${REPO_ROOT}')
    assert hashlib.sha256(xml.encode()).hexdigest() == expected['normalized_xml_sha256']
    solution_identity = value.get('solution_identity', value['solution'].identity)
    assert solution_identity == expected['solution_identity']


def test_pickcube_exact_p16_identity_config_readiness_reset_and_legacy_caller():
    value = pc.build_reference()
    old = BASELINE['pickcube']
    assert_source(value, old)
    assert value['artifact'].artifact_id == 'pick-cube-v1/p1_6_experimental_100hz'
    assert value['artifact'].artifact_version == 'ver_p1_6_experimental_100hz'
    assert value['controller'].identity == old['controller_identity']
    assert digest(asdict(value['readiness'])) == old['readiness_sha256']
    for seed, expected in old['resets'].items():
        assert json.loads(json.dumps(pc.sample_reset(value['artifact'], int(seed)).to_mapping())) == expected
    from task_env.tasks.pick_cube.timebase import build_timebase_candidate
    assert build_timebase_candidate('TB-100').identity_hash != value['artifact'].identity_hash
    with pytest.raises(ValueError):
        pc.sample_reset(build_timebase_candidate('TB-100'), 31)
    from task_env.diagnostics.phase1.policy_search.timebase100 import context
    _, artifact, source, config, controller, expert = context('cpu')
    assert artifact == value['artifact'] and source.config == value['source'].config
    assert config == value['readiness'] and controller.identity == value['controller'].identity
    assert expert.identity == value['solution'].identity


@pytest.mark.parametrize('rate', [50, 100, 500])
@pytest.mark.parametrize('provider', ['geophys', 'mujoco'])
def test_nutassembly_exact_historical_physics_solution_and_new_source_identity(rate, provider):
    value = na.build_reference(rate_hz=rate, provider=provider)
    old = BASELINE['nutassembly'][f'{provider}_{rate}']
    assert_source(value, old)
    assert digest(value['controller'].physical_profile) == old['physical_profile_sha256']
    assert digest(asdict(value['solution_config'])) == old['solution_config_sha256']
    assert value['controller_identity'] != old['controller_identity']
    assert value['source'].config.robot.gripper.force_limit_N == 10.
    assert value['dynamic_profile_sha256'] == '5bbac0ad315c07a1ced354ccee845acf92ae50ab1a125255d6af486c83d4c266'
    reset = na_reset(value['artifact'], 19)
    assert reset.task_artifact_hash == value['artifact'].identity_hash
    assert reset.settle_steps == 0
    assert value['recipe_identity'] == digest(value['resolved_configuration'])
    assert value['controller'].inner.version == 'native-gripper-500hz-v1'
    assert not value['diagnostic_shadow_mode']


def test_execution_policies_keep_the_same_strict_expert_and_no_outcome_policy_default():
    strict = na.build_reference()
    diagnostic = na.build_reference(execution_policy=na.DIAGNOSTIC_OBSERVATION)
    assert strict['solution_identity'] == diagnostic['solution_identity']
    assert strict['controller_identity'] == diagnostic['controller_identity']
    assert strict['solution'].completion_policy.value == 'on_expert_terminal_stage'
    assert diagnostic['solution'].completion_policy.value == 'on_expert_terminal_stage'
    assert strict['solution']._stable_height_ready(.5, .6) is False
    assert diagnostic['solution']._stable_height_ready(.5, .6) is False
    assert diagnostic['diagnostic_shadow_mode'] and not strict['diagnostic_shadow_mode']
    assert diagnostic['execution_policy']['grants_full_expert_pass'] is False
    assert diagnostic['recipe_identity'] != strict['recipe_identity']
    assert not diagnostic['execution_policy']['outcome_oriented_proposal_enabled']
    lifecycle = strict['solution'].lifecycle
    lifecycle.observe_task_outcome(task_success=True, control_step=1, simulation_time_s=.01)
    assert lifecycle.task_success_seen and not lifecycle.expert_complete
    lifecycle.fail('stable_height_mismatch', control_step=2, simulation_time_s=.02)
    assert lifecycle.expert_failed and not lifecycle.expert_complete


def state(poses, opening):
    joints = {'panda-v1/finger_joint1': opening / 2,
              'panda-v1/finger_joint2': opening / 2}
    return CanonicalStateView('canonical-state-v0', 'SI_right_handed_z_up_wxyz',
                             0, 0., joints, {name: 0. for name in joints}, poses)


def test_pickcube_lift_only_success_and_reward_independent_oracle():
    rest = .462 + .025
    for lift, success in [(.09999, False), (.10001, True)]:
        current = state({'cube-v1': PoseWorld((.5, 0., rest + lift), (1., 0., 0., 0.)),
                         'panda-v1/ee': PoseWorld((.5, 0., 1.5), (1., 0., 0., 0.))}, .08)
        result = pc_evaluate(current, pc.build_artifact().semantics)
        assert result.success is success
        assert result.metrics['grasped_cube'] is False
        assert result.reward_terms['grasp'] == 0.
        assert result.reward_terms['success'] == float(success)
        # Pose subtraction introduces binary64 rounding; success stays exact.
        assert result.reward_terms['lift'] == pytest.approx(min(.4, lift / .1 * .4), abs=1e-12, rel=0)


def test_nutassembly_success_requires_measured_release_and_retreat():
    poses = {'square-nut-v1': PoseWorld((.58, .045, .473), (1., 0., 0., 0.)),
             'square-peg-v1': PoseWorld((.58, .045, .5), (1., 0., 0., 0.)),
             'panda-v1/ee': PoseWorld((.58, .045, .65), (1., 0., 0., 0.))}
    assert not na_evaluate(state(poses, .02)).success
    assert na_evaluate(state(poses, .08)).success
    poses['panda-v1/ee'] = poses['square-nut-v1']
    assert not na_evaluate(state(poses, .08)).success


@pytest.mark.parametrize('options', [{'rate_hz':20}, {'rate_hz':True}, {'provider':'sapien'},
                                     {'execution_policy':'on_task_success'}])
def test_unadmitted_nutassembly_route_fails_closed(options):
    with pytest.raises(ValueError):
        na.build_reference(**options)


def test_fresh_construction_has_no_diagnostic_native_or_workspace_dependency(tmp_path):
    code = r'''
import resource,sys,importlib.abc
resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if name.startswith('task_env.diagnostics') or name.split('.')[0] in {'mujoco','taichi','geophys','solvers','scene','visualization','torch','triton'}:
   raise AssertionError('forbidden import '+name)
sys.meta_path.insert(0,Guard())
from pathlib import Path
original=Path.open
reads=[]
def checked(self,*args,**kwargs):
 if '/workspace/' in str(self.resolve()):raise AssertionError('workspace access '+str(self))
 reads.append(str(self))
 return original(self,*args,**kwargs)
Path.open=checked
from task_env.tasks.pick_cube.reference import build_reference as pc
from task_env.tasks.nut_assembly.reference import build_reference as na
assert pc()['artifact'].identity_hash.startswith('fd5bc968')
assert na(provider='geophys')['source'].config.robot.gripper.force_limit_N==10.
assert na(provider='mujoco')['source'].config.robot.gripper.force_limit_N==10.
assert not any(n.startswith('task_env.diagnostics') for n in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
                 OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'),
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_task_owned_runner_selection_preserves_legacy_context_and_guard_admission():
    # Import the retained runner only in this explicit compatibility test.
    # It imports MuJoCo's observer module but does not create a native runtime.
    from task_env.diagnostics.phase1.integration.lifecycle_full import (
        context, _validate_cross_provider_contract, _CROSS_PROVIDER_CONTRACT_PATH,
    )
    contract = json.loads(_CROSS_PROVIDER_CONTRACT_PATH.read_text())
    candidate = 'guarded-primary-readiness-alternative-8n-v2-v5-clearance'
    for provider in ('geophys', 'mujoco'):
        legacy = context(50, candidate, provider=provider)
        assert_source(legacy, BASELINE['nutassembly'][f'{provider}_50'])
        for diagnostic in (False, True):
            selected = context(50, candidate, provider=provider,
                               construction_route='task-owned',
                               diagnostic_observation=diagnostic)
            _validate_cross_provider_contract(selected, contract)
            assert selected['construction_id'] == na.CONSTRUCTION_ID
            assert selected['diagnostic_shadow_mode'] is diagnostic
            assert selected['solution_identity'] == legacy['solution_identity']
    with pytest.raises(ValueError, match='selected guarded'):
        context(50, construction_route='task-owned')
