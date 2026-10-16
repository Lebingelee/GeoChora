"""S1 independent pre-change values and defect-sensitive, provider-free oracles."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from task_env.artifacts import CanonicalStateView, PoseWorld, TaskArtifact
from task_env.tasks.pick_cube.task import (
    build_artifact as pc_build_artifact, build_reference as pc_build_reference,
    evaluate as pc_evaluate, sample_reset as pc_sample_reset,
)
from task_env.tasks.nut_assembly.task import (
    build_artifact as na_build_artifact, build_reference as na_build_reference,
    evaluate as na_evaluate, sample_reset as na_reset,
)

ROOT = Path(__file__).resolve().parents[3]
BASELINE = json.loads(Path(__file__).with_name('reference_construction_baseline.json').read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def assert_source(value, expected, *, check_solution_identity=True):
    assert value['artifact'].identity_hash == expected['artifact_hash']
    assert digest(asdict(value['source'].config)) == expected['source_config_sha256']
    xml = value['source'].scene_source.xml.replace(str(ROOT), '${REPO_ROOT}')
    assert hashlib.sha256(xml.encode()).hexdigest() == expected['normalized_xml_sha256']
    if check_solution_identity:
        solution_identity = value.get('solution_identity', value['solution'].identity)
        assert solution_identity == expected['solution_identity']


def test_pickcube_minimal_task_preserves_p16_identity_config_readiness_and_reset():
    value = pc_build_reference()
    old = BASELINE['pickcube']
    assert isinstance(value['artifact'], TaskArtifact)
    assert_source(value, old, check_solution_identity=False)
    assert value['artifact'].artifact_id == 'pick-cube-v1/p1_6_experimental_100hz'
    assert value['artifact'].artifact_version == 'ver_p1_6_experimental_100hz'
    assert value['controller'].identity == old['controller_identity']
    assert digest(asdict(value['readiness'])) == old['readiness_sha256']
    assert value['solution'].version == 'pick-cube-p16-readiness-expert-v2'
    solution_hash = hashlib.sha256((ROOT / 'task_env/tasks/pick_cube/solution.py').read_bytes()).hexdigest()
    assert value['solution'].identity == digest({
        'version': value['solution'].version, 'config': value['readiness'].identity,
        'implementation_sha256': solution_hash,
    })
    source_hashes = value['resolved_configuration']['source_sha256']
    assert source_hashes['task_env/tasks/pick_cube/task.py'] == hashlib.sha256(
        (ROOT / 'task_env/tasks/pick_cube/task.py').read_bytes()).hexdigest()
    assert source_hashes['task_env/tasks/pick_cube/solution.py'] == solution_hash
    assert source_hashes['task_env/tasks/pick_cube/config.yaml'] == hashlib.sha256(
        (ROOT / 'task_env/tasks/pick_cube/config.yaml').read_bytes()).hexdigest()
    assert source_hashes['task_env/objects/pick_cube.py'] == hashlib.sha256(
        (ROOT / 'task_env/objects/pick_cube.py').read_bytes()).hexdigest()
    assert value['source_revision']
    assert value['resolved_configuration']['task_recipe']['recipe']['control_hz'] == 100
    for seed, expected in old['resets'].items():
        assert json.loads(json.dumps(pc_sample_reset(value['artifact'], int(seed)).to_mapping())) == expected
    assert pc_build_artifact() == value['artifact']


def test_nutassembly_selected_route_preserves_artifact_assets_and_resolved_parameters():
    for provider in ('geophys', 'mujoco'):
        value = na_build_reference(provider=provider)
        old = BASELINE['nutassembly'][f'{provider}_100']
        assert isinstance(value['artifact'], TaskArtifact)
        assert value['artifact'].artifact_id == 'nut-assembly-square-v1/p1_8_e/nominal-v1'
        assert value['artifact'].identity_hash == old['artifact_hash']
        assert digest(asdict(value['source'].config)) == old['source_config_sha256']
        xml = value['source'].scene_source.xml.replace(str(ROOT), '${REPO_ROOT}')
        assert hashlib.sha256(xml.encode()).hexdigest() == old['normalized_xml_sha256']
        assert value['source'].scene_source.xml == na_build_reference(provider=provider)['source'].scene_source.xml
        assert value['source'].config.robot.gripper.force_limit_N == 10.0
        assert value['solution'].STAGES == (
            'approach_nut', 'descend_to_handle', 'close_gripper', 'verify_lift',
            'raise_for_transport', 'move_above_square_peg', 'align_nut_yaw',
            'descend_to_peg_top', 'lower_nut_to_table', 'open_gripper', 'release_retreat')
        assert value['solution'].config.capture_translation_slip_m == .008
        assert value['solution'].config.capture_rotation_slip_rad == .15
        assert value['solution'].config.action_budget_s == 60.0
        assert value['execution_policy']['policy_id'] == 'nutassembly-outcome-oriented-completion-v1'
        assert value['execution_policy']['diagnostic_continuation'] is False
        assert value['solution_identity'] != old['solution_identity']
        assert value['recipe_identity'] == digest(value['resolved_configuration'])
        assert value['source_revision']
        reset = na_reset(value['artifact'], 19)
        assert reset.task_artifact_hash == value['artifact'].identity_hash
        assert reset.task_seed == 19 and reset.settle_steps == 0
        assert value['controller'].inner.version == 'native-gripper-500hz-v1'
    assert na_build_artifact().identity_hash == BASELINE['nutassembly']['geophys_100']['artifact_hash']


def test_nutassembly_has_one_flattened_active_solution_and_four_task_files():
    from importlib.util import find_spec
    from task_env.tasks.nut_assembly.solution import NutAssemblyOutcomeSolutionV1
    task_dir = ROOT / 'task_env/tasks/nut_assembly'
    assert sorted(path.name for path in task_dir.iterdir() if path.is_file()) == [
        '__init__.py', 'config.yaml', 'solution.py', 'task.py']
    assert NutAssemblyOutcomeSolutionV1.__mro__ == (NutAssemblyOutcomeSolutionV1, object)
    for module in (
        'task_env.tasks.nut_assembly.canonical_artifact',
        'task_env.tasks.nut_assembly.canonical_reset',
        'task_env.tasks.nut_assembly.canonical_semantics',
        'task_env.tasks.nut_assembly.canonical_solution',
        'task_env.tasks.nut_assembly.canonical_solution_v2',
        'task_env.tasks.nut_assembly.canonical_source',
        'task_env.tasks.nut_assembly.clearance_candidate_v3',
        'task_env.tasks.nut_assembly.clearance_candidate_v5',
        'task_env.tasks.nut_assembly.guarded_authorization_candidate',
        'task_env.tasks.nut_assembly.guarded_authorization_candidate_v2',
        'task_env.tasks.nut_assembly.outcome_solution',
        'task_env.tasks.nut_assembly.reference',
        'task_env.tasks.nut_assembly.reference_config',
        'task_env.tasks.nut_assembly.reference_env',
        'task_env.tasks.nut_assembly.reference_execution',
        'task_env.tasks.nut_assembly.stable_grasp_candidate',
    ):
        assert find_spec(module) is None
    with pytest.raises(ImportError, match="package-level historical build_reference API is retired"):
        from task_env.tasks.nut_assembly import build_reference  # noqa: F401


@pytest.mark.parametrize('yaw', [-1.2, -0.2, 0.0, 0.2, 1.4])
def test_nutassembly_yaw_helper_preserves_the_selected_square_symmetry_formula(yaw):
    from task_env.tasks.nut_assembly.solution import NutAssemblyOutcomeSolutionV1
    quaternion = [__import__('math').cos(yaw / 2), 0.0, 0.0, __import__('math').sin(yaw / 2)]
    period = 0.5 * __import__('math').pi
    expected = -((yaw + 0.5 * period) % period - 0.5 * period)
    assert NutAssemblyOutcomeSolutionV1._square_yaw_correction(quaternion) == pytest.approx(expected, abs=1e-12)

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
        result = pc_evaluate(current, pc_build_artifact().semantics)
        assert result.success is success
        assert result.metrics['grasped_cube'] is False
        assert result.reward_terms['grasp'] == 0.
        assert result.reward_terms['success'] == float(success)
        # Pose subtraction introduces binary64 rounding; success stays exact.
        assert result.reward_terms['lift'] == pytest.approx(min(.4, lift / .1 * .4), abs=1e-12, rel=0)


def test_pickcube_scalar_metrics_preserve_accepted_mujoco_boundary_values():
    current = state({
        'cube-v1': PoseWorld((0.6351343459705087, -0.08646434752767339, 0.48762747518153127),
                             (1., 0., 0., 0.)),
        'panda-v1/ee': PoseWorld((0.5914863404002174, -0.08949059580312209, 0.5771712604381248),
                                 (-0.01493029538157625, 0.7644666296611904,
                                  0.6443596055257806, -0.012982957326429108)),
    }, 0.07999873306277117)
    result = pc_evaluate(current, pc_build_artifact().semantics)
    assert result.metrics['eef_to_cube_dist'] == 0.09966140700877033
    assert result.reward == 0.026493052593642232


def test_nutassembly_success_requires_measured_release_and_retreat():
    poses = {'square-nut-v1': PoseWorld((.58, .045, .473), (1., 0., 0., 0.)),
             'square-peg-v1': PoseWorld((.58, .045, .5), (1., 0., 0., 0.)),
             'panda-v1/ee': PoseWorld((.58, .045, .65), (1., 0., 0., 0.))}
    assert not na_evaluate(state(poses, .02)).success
    assert na_evaluate(state(poses, .08)).success
    poses['panda-v1/ee'] = poses['square-nut-v1']
    assert not na_evaluate(state(poses, .08)).success


@pytest.mark.parametrize('options', [{'provider':'sapien'}, {'rate_hz':50},
                                     {'execution_policy':'diagnostic'}])
def test_unadmitted_nutassembly_selectors_fail_closed(options):
    with pytest.raises((ValueError, TypeError)):
        na_build_reference(**options)


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
from task_env.tasks.pick_cube.task import build_reference as pc
from task_env.tasks.nut_assembly.task import build_reference as na
assert pc()['artifact'].identity_hash.startswith('fd5bc968')
assert na(provider='geophys')['source'].config.robot.gripper.force_limit_N==10.
assert na(provider='mujoco')['source'].config.robot.gripper.force_limit_N==10.
assert not any(n.startswith('task_env.diagnostics') for n in sys.modules)
assert 'task_env.tasks.pick_cube.task' in sys.modules
assert 'task_env.tasks.pick_cube.candidate' not in sys.modules
assert 'task_env.tasks.nut_assembly.task' in sys.modules
assert 'task_env.tasks.nut_assembly.solution' in sys.modules
assert not any(name.startswith('task_env.tasks.nut_assembly.') and name.rsplit('.',1)[-1] in {
 'canonical_artifact','canonical_reset','canonical_semantics','canonical_solution','canonical_solution_v2',
 'canonical_source','clearance_candidate_v3','clearance_candidate_v5','guarded_authorization_candidate',
 'guarded_authorization_candidate_v2','outcome_solution','reference','reference_config','reference_env',
 'reference_execution','stable_grasp_candidate'} for name in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
                 OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1'),
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_pickcube_historical_modules_and_gym_entrypoint_are_explicitly_retired():
    from importlib.util import find_spec
    from task_env.diagnostics.historical_tasks import make_historical_env
    task_dir = ROOT / 'task_env/tasks/pick_cube'
    assert sorted(path.name for path in task_dir.iterdir() if path.is_file()) == [
        '__init__.py', 'config.yaml', 'solution.py', 'task.py',
    ]
    for module in (
        'task_env.tasks.pick_cube.artifact',
        'task_env.tasks.pick_cube.assets',
        'task_env.tasks.pick_cube.candidate',
        'task_env.tasks.pick_cube.canonical_semantics',
        'task_env.tasks.pick_cube.definition',
        'task_env.tasks.pick_cube.reference',
        'task_env.tasks.pick_cube.reference_config',
        'task_env.tasks.pick_cube.reference_env',
        'task_env.tasks.pick_cube.readiness_solution',
        'task_env.tasks.pick_cube.reset',
        'task_env.tasks.pick_cube.reset_policy',
        'task_env.tasks.pick_cube.runtime_source',
        'task_env.tasks.pick_cube.timebase',
    ):
        assert find_spec(module) is None
    with pytest.raises(RuntimeError, match='restore the immutable v1.0.0 source'):
        make_historical_env('pick-cube-v1')
