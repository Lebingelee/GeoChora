"""Focused contract tests for the versioned built-in PickCube Harness mode."""
from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from builtin_example_schema import BuiltinPickCubeExampleV1, ExampleWorkingTreeScopeV1


def _spec(**changes):
    value = {
        'schema_version': 'harness-builtin-pickcube-example-v1',
        'example_id': 'pickcube-harness-example-v1',
        'task_uid': 'pick-cube-p16-reference-v1',
        'provider': 'mujoco', 'backend': 'cpu', 'device': 'cpu',
        'controller_profile': 'r3_continuous_v1', 'seeds': [31, 32, 33],
        'horizon_control_ticks': 1000, 'physics_dt_s': 0.002, 'control_substeps': 5,
        'source_delivery_manifest': None,
    }
    value.update(changes)
    return BuiltinPickCubeExampleV1.from_dict(value)


def _artifact():
    from task_env.tasks.pick_cube.task import build_artifact

    return build_artifact()


def test_builtin_example_schema_pins_uid_profile_seed_set_and_timebase():
    spec = _spec()
    assert spec.identity_sha256
    assert spec.seeds == (31, 32, 33)
    for changes in (
        {'task_uid': 'other/task-v1'},
        {'provider': 'mujoco', 'backend': 'cuda', 'device': 'cuda:0'},
        {'controller_profile': 'r1'},
        {'seeds': [31, 32]},
        {'horizon_control_ticks': 1001},
        {'control_substeps': 4},
    ):
        with pytest.raises(ValueError):
            _spec(**changes)
    with pytest.raises(ValueError, match='source delivery manifest'):
        _spec(provider='isaacsim', backend='cuda', device='cuda:0')
    isaac = _spec(
        provider='isaacsim', backend='cuda', device='cuda:0',
        source_delivery_manifest='/frozen/pickcube/delivery_manifest.json',
    )
    assert isaac.provider == 'isaacsim'


def test_repository_harness_spec_is_complete_for_versioned_builtin_schema():
    path = Path(__file__).resolve().parents[3] / 'examples/tasks/pick_cube_harness.json'
    spec = BuiltinPickCubeExampleV1.load(path)
    assert spec.provider == 'mujoco'
    assert spec.source_delivery_manifest is None


def test_working_tree_scope_requires_exact_sorted_byte_pins():
    scope = ExampleWorkingTreeScopeV1.from_dict({
        'schema_version': 'harness-example-working-tree-scope-v1',
        'expected_untracked': [
            {'path': 'docs/maintenance/a.md', 'sha256': 'a' * 64},
        ],
    })
    assert scope.to_dict()['expected_untracked'][0]['path'] == 'docs/maintenance/a.md'
    with pytest.raises(ValueError):
        ExampleWorkingTreeScopeV1.from_dict({
            'schema_version': 'harness-example-working-tree-scope-v1',
            'expected_untracked': [
                {'path': 'b', 'sha256': 'b' * 64}, {'path': 'a', 'sha256': 'a' * 64},
            ],
        })


def test_compiler_uses_builtin_catalog_but_preserves_candidate_spec():
    import harness_compiler
    from harness_spec_schema import CandidateSpec

    spec = _spec()
    scope = ExampleWorkingTreeScopeV1('harness-example-working-tree-scope-v1', ())
    artifact = type('Artifact', (), {
        'identity_hash': 'f' * 64, 'task_id': 'pick-cube-v1',
        'timebase': type('Timebase', (), {'physics_dt': 0.002, 'control_substeps': 5})(),
    })()
    source = type('Source', (), {
        'scene_source': type('SceneSource', (), {'source_id': 'test-source', 'xml': '<mujoco/>'})(),
    })()
    controller = type('Controller', (), {'identity': 'controller-v1'})()
    solution = type('Solution', (), {'identity': 'solution-v1'})()
    value = {
        'artifact': artifact, 'construction_id': 'pickcube-core-v2',
        'recipe_identity': 'e' * 64, 'source_revision': 'commit',
        'source_sha256': {'task_env/tasks/pick_cube/task.py': '1' * 64},
        'source': source, 'controller': controller, 'solution_identity': solution.identity,
    }
    catalog = {
        'schema_version': 'harness-catalog-v0', 'core_repo': '/tmp/core',
        'core_commit': 'commit', 'core_dirty': False,
        'builtin_examples': {'pickcube-harness-example-v1': {'task_uid': spec.task_uid}},
        'env_uids': [spec.task_uid], 'providers': {'mujoco': {'available': True}},
    }
    with patch.object(harness_compiler, '_example_working_tree_context', return_value={
        'schema_version': scope.schema_version, 'tracked_clean': True,
        'repo_dirty': False, 'expected_untracked': [],
    }), patch('catalog_query.core_context', return_value={'core_repo': '/tmp/core', 'core_commit': 'commit', 'core_dirty': False}), \
         patch.object(subprocess, 'check_output', return_value=''), \
         patch('task_env.tasks.pick_cube.task.build_reference', return_value=value):
        compiled = harness_compiler.compile_builtin_pickcube_example(spec, catalog, working_tree_scope=scope)

    assert compiled.artifact_hash == 'f' * 64
    assert compiled.runtime_source_id == 'test-source'
    with pytest.raises((ValueError, TypeError)):
        CandidateSpec.from_dict(spec.to_dict())


def test_compiler_admits_only_the_catalogued_exact_isaac_route():
    import harness_compiler

    spec = _spec(provider='isaacsim', backend='cuda', device='cuda:0',
                 source_delivery_manifest='/frozen/pickcube/delivery_manifest.json')
    scope = ExampleWorkingTreeScopeV1('harness-example-working-tree-scope-v1', ())
    catalog = {
        'schema_version': 'harness-catalog-v0', 'core_repo': '/tmp/core',
        'core_commit': 'commit', 'core_dirty': False,
        'builtin_examples': {'pickcube-harness-example-v1': {
            'task_uid': spec.task_uid,
            'provider_routes': {'isaacsim': {
                'backend': 'cuda', 'device': 'cuda:0', 'runtime_tested': False,
            }},
        }},
        'env_uids': [spec.task_uid], 'providers': {},
    }
    with patch.object(harness_compiler, '_example_working_tree_context', return_value={
        'schema_version': scope.schema_version, 'tracked_clean': True,
        'repo_dirty': False, 'expected_untracked': [],
    }), patch('catalog_query.core_context', return_value={'core_repo': '/tmp/core', 'core_commit': 'commit', 'core_dirty': False}), \
         patch.object(subprocess, 'check_output', return_value=''), \
         patch('task_env.tasks.pick_cube.task.build_isaac_reference', return_value={
             'artifact': _artifact(), 'construction_id': 'f06', 'recipe_identity': 'a' * 64,
             'controller': SimpleNamespace(identity='b' * 64),
             'solution_identity': 'c' * 64, 'source_revision': 'commit',
             'source_sha256': {'task_env/tasks/pick_cube/isaac.py': 'd' * 64},
             'source': SimpleNamespace(
                 scene_source=SimpleNamespace(source_id='f06-source'),
                 source_closure_digest='e' * 64,
             ),
         }):
        compiled = harness_compiler.compile_builtin_pickcube_example(
            spec, catalog, working_tree_scope=scope,
        )
        assert compiled.runtime_source_id == 'f06-source'
        assert compiled.runtime_source_sha256 == 'e' * 64


def test_validation_supervises_the_compiled_isaac_route_after_static_compile(tmp_path):
    import builtin_example_validation

    spec = _spec(
        provider='isaacsim', backend='cuda', device='cuda:0',
        source_delivery_manifest='/frozen/pickcube/delivery_manifest.json',
    )
    spec_path = tmp_path / 'spec.json'
    spec_path.write_text(json.dumps(spec.to_dict()))
    scope = ExampleWorkingTreeScopeV1('harness-example-working-tree-scope-v1', ())
    scope_path = tmp_path / 'scope.json'
    scope_path.write_text(json.dumps(scope.to_dict()))
    catalog_path = tmp_path / 'catalog.json'
    catalog_path.write_text('{}')
    manifest_path = tmp_path / 'delivery_manifest.json'
    manifest_path.write_text('{}')
    compiled = SimpleNamespace(
        artifact_hash='a' * 64, construction_id='f06', recipe_identity='b' * 64,
        controller_identity='c' * 64, solution_identity='d' * 64,
        source_revision='commit', runtime_source_id='source',
        runtime_source_sha256='e' * 64,
        working_tree_scope={'expected_untracked': []}, repo_dirty=False,
    )
    row = {'seed': 31, 'provider': 'isaacsim', 'status': 'RUNTIME_VALID',
           'runtime_valid': True, 'task_outcome': 'TASK_OR_EXPERT_FAILURE_REPORTED'}
    with patch('harness_compiler.compile_builtin_pickcube_example', return_value=compiled), \
         patch.object(builtin_example_validation, '_run_one', return_value=row):
        result = builtin_example_validation.validate_provider(
            spec_path, catalog_path, scope_path, tmp_path / 'result', only_seed=31,
            provider_override='isaacsim', source_delivery_manifest=manifest_path,
        )
    assert result['provider'] == 'isaacsim'
    assert result['disposition'] == 'PREFLIGHT'
    assert result['runtime_valid_count'] == 1


def test_worker_accepts_supervisor_created_output_dir_but_rejects_other_data(tmp_path):
    from builtin_example_worker import _prepare_output_directory

    output = tmp_path / 'seed_31'
    output.mkdir()
    (output / 'worker.stdout.log').touch()
    (output / 'worker.stderr.log').touch()
    (output / 'run_plan.json').write_text('{}')
    (output / 'run_preflight.json').write_text('{}')
    assert _prepare_output_directory(output) == output.resolve()
    (output / 'episode.h5').touch()
    with pytest.raises(FileExistsError, match='already contains data'):
        _prepare_output_directory(output)


def test_isaac_worker_uses_controlled_process_exit_after_receipt():
    from builtin_example_worker import _terminate_isaac_worker

    with patch('builtin_example_worker.os._exit', side_effect=RuntimeError('exit boundary')) as exit_call:
        with pytest.raises(RuntimeError, match='exit boundary'):
            _terminate_isaac_worker(7)
    exit_call.assert_called_once_with(7)


def test_worker_counts_core_planned_actions_from_loaded_canonical_trajectory():
    from builtin_example_worker import _planned_action_count

    trajectory = SimpleNamespace(transitions=(
        SimpleNamespace(planned_action=True),
        SimpleNamespace(planned_action=False),
        SimpleNamespace(planned_action=True),
    ))

    assert _planned_action_count(trajectory) == 2
    assert _planned_action_count(SimpleNamespace(transitions=())) == 0


def test_isaac_bootstrap_receipt_uses_observed_finite_run_plan_bound():
    from builtin_example_worker import _validate_f06_bootstrap_receipt
    from builtin_example_validation import ISAAC_BOOTSTRAP_PHYSICS_STEPS_UPPER_BOUND

    row = {
        'seed': 31, 'source_revision': 'a' * 40,
        'horizon_control_ticks': 1000, 'control_substeps': 5,
        'physics_dt_s': 0.002,
    }
    plan = {
        'schema_version': 'harness-builtin-pickcube-example-run-plan-v1',
        'provider': 'isaacsim', 'seed': 31, 'core_commit': 'a' * 40,
        'horizon_control_ticks': 1000, 'control_substeps': 5,
        'physics_dt_s': 0.002, 'bootstrap_physics_steps_upper_bound': 18,
        'physics_steps_upper_bound': 5018,
    }
    receipt = {
        'schema_version': 'isaac-public-physics-bootstrap-v1',
        'step_index_before': 0, 'step_index_after': 18,
        'physics_steps': 18, 'physics_dt_s': 0.002,
        'physics_time_s': 0.036,
    }

    assert _validate_f06_bootstrap_receipt(receipt, plan, row=row) == 18
    assert ISAAC_BOOTSTRAP_PHYSICS_STEPS_UPPER_BOUND == 18
    overrun = dict(receipt, step_index_after=19, physics_steps=19, physics_time_s=0.038)
    with pytest.raises(ValueError, match='exceed or differ from the run plan'):
        _validate_f06_bootstrap_receipt(overrun, plan, row=row)
    malformed_bound = dict(plan, physics_steps_upper_bound=5010)
    with pytest.raises(ValueError, match='run-plan native-step bounds are malformed'):
        _validate_f06_bootstrap_receipt(receipt, malformed_bound, row=row)


def test_worker_reports_preplan_solution_failure_without_calling_it_h5_failure():
    from builtin_example_worker import _validate_f06_planning_action_count

    assert _validate_f06_planning_action_count(0, solution_failed=True) == 0
    assert _validate_f06_planning_action_count(1, solution_failed=False) == 1
    with pytest.raises(ValueError, match='no non-hold Core-planned action'):
        _validate_f06_planning_action_count(0, solution_failed=False)


def test_provider_matrix_requires_any_core_planned_action_before_passing_route():
    from builtin_example_validation import _planned_action_route_evidence

    rows = [
        {'seed': 31, 'planning_action_count': 0},
        {'seed': 32, 'planning_action_count': 48},
        {'seed': 33, 'planning_action_count': 0},
    ]
    assert _planned_action_route_evidence(rows) == (48, [32])
    assert _planned_action_route_evidence([
        {'seed': 31, 'planning_action_count': 0},
        {'seed': 32, 'planning_action_count': 0},
        {'seed': 33, 'planning_action_count': 0},
    ]) == (0, [])


def test_worker_action_trace_records_failed_proposal_boundary(tmp_path):
    from builtin_example_worker import _install_action_trace

    pose = SimpleNamespace(position=(0.1, 0.2, 0.3), quaternion_wxyz=(1.0, 0.0, 0.0, 0.0))
    state = SimpleNamespace(control_step=7, simulation_time=0.07,
                            pose_world={'panda-v1/ee': pose, 'cube-v1': pose})
    env = SimpleNamespace(provider='mujoco', sample=SimpleNamespace(task_seed=31), state=state,
                          info={'task_metrics': {'task_success': False}}, execution_fault=None)

    def fail_step(action, *, proposal=None, observer_solution=None):
        raise RuntimeError('diagnostic interval failure')

    env._step = fail_step
    capture, _write_trace = _install_action_trace(env, tmp_path / 'step_trace.json')
    proposal = SimpleNamespace(stage='approach')
    with pytest.raises(RuntimeError, match='diagnostic interval failure'):
        env._step([0.2, 0.3, 0.4, 1.0, 0.0, 0.0, 0.0, 0.04], proposal=proposal)
    trace = json.loads((tmp_path / 'step_trace.json').read_text())
    assert capture['attempted'] == 1 and capture['completed'] == 0
    assert trace['rows'][0]['control_step_before'] == 7
    assert trace['rows'][0]['planned_tcp_pose'] == [0.2, 0.3, 0.4, 1.0, 0.0, 0.0, 0.0]
    assert trace['rows'][0]['error']['message'] == 'diagnostic interval failure'


def test_pickcube_r3_profile_is_task_versioned_and_records_rate_bound():
    from task_env.tasks.pick_cube.task import build_reference

    built = build_reference(controller_profile='r3_continuous_v1')
    task_profile = built['resolved_configuration']['task_controller_profile']
    controller_profile = built['controller'].rate_profile_mapping()
    assert task_profile == {
        'schema_version': 'pick-cube-r3-continuous-profile-v1',
        'joint_velocity_limit_rad_s': 4.0,
    }
    assert controller_profile['joint_velocity_limit_rad_s'] == 4.0
    assert built['resolved_configuration']['controller_profile'] == 'r3_continuous_v1'


def test_isaac_core_site_overlay_excludes_conflicting_openusd_package(tmp_path):
    from builtin_example_validation import _populate_isaac_core_site_overlay

    core_site = tmp_path / 'core-site'
    core_site.mkdir()
    (core_site / 'h5py').mkdir()
    (core_site / 'pxr').mkdir()
    (core_site / 'usd_core-26.11.dist-info').mkdir()
    (core_site / 'numpy.py').write_text('sentinel = True\n')
    overlay = tmp_path / 'isaac-overlay'

    manifest = _populate_isaac_core_site_overlay(core_site, overlay)

    assert manifest['schema_version'] == 'isaac-core-site-overlay-v1'
    assert manifest['excluded_entries'] == ['pxr', 'usd_core-26.11.dist-info']
    assert manifest['included_entry_count'] == 2
    assert (overlay / 'h5py').is_symlink()
    assert (overlay / 'numpy.py').is_symlink()
    assert not (overlay / 'pxr').exists()


@pytest.mark.parametrize('module_name', (
    'harness_compiler', 'builtin_example_validation', 'builtin_example_worker',
))
def test_harness_cli_help_supports_direct_and_package_invocation(module_name):
    core = Path(__file__).resolve().parents[3]
    env = dict(__import__('os').environ)
    env['PYTHONPATH'] = f'{core / "GeoPhys/src"}:{core}'
    direct = subprocess.run(
        [sys.executable, str(AGENT_DIR / f'{module_name}.py'), '--help'],
        cwd=core, env=env, text=True, capture_output=True, timeout=20,
    )
    assert direct.returncode == 0, direct.stderr
    assert 'usage:' in direct.stdout.lower()

    packaged = subprocess.run(
        [sys.executable, '-m', f'task_env.script.agent.{module_name}', '--help'],
        cwd=core, env=env, text=True, capture_output=True, timeout=20,
    )
    assert packaged.returncode == 0, packaged.stderr
    assert 'usage:' in packaged.stdout.lower()


def test_isaac_usd_generator_help_does_not_import_core_or_start_simulator():
    core = Path(__file__).resolve().parents[3]
    isaac_python = core / 'workspace/environments/isaacsim-6.2.0/bin/python'
    if not isaac_python.is_file():
        pytest.skip('frozen Isaac Python is not installed in this checkout')
    generator = core / 'task_env/diagnostics/tasks/pickcube_isaac_usd_delivery.py'
    result = subprocess.run(
        [str(isaac_python), str(generator), '--help'],
        cwd=core, text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert '--core-python' in result.stdout
    assert '--source-package' in result.stdout


def test_isaac_worker_opens_shared_app_before_source_compile_and_closes_on_compile_failure(tmp_path):
    import json
    import builtin_example_worker
    import task_env.runtime.sessions.isaac_native_io as isaac_native_io

    events = []

    class AppOwner:
        def __init__(self):
            self.opened = False
            self.closed = False

        def open(self):
            events.append('app_open')
            self.opened = True

        def launch_profile_receipt(self):
            return {
                'profile_id': 'f06-headless-no-render-v1',
                'simulation_app_config': {'headless': True},
            }

        def close(self):
            events.append('app_close')
            self.closed = True

        def close_receipt(self):
            return {'close_attempted': True, 'close_completed': self.closed}

    owner = AppOwner()
    spec = _spec(
        provider='isaacsim', backend='cuda', device='cuda:0',
        source_delivery_manifest='/frozen/pickcube/delivery_manifest.json',
    )
    scope = ExampleWorkingTreeScopeV1('harness-example-working-tree-scope-v1', ())
    catalog = {'core_repo': str(tmp_path)}
    output = tmp_path / 'isaac-run'
    output.mkdir()
    (output / 'run_plan.json').write_text(json.dumps({
        'schema_version': 'harness-builtin-pickcube-example-run-plan-v2',
        'isaac_app_launch_profile_id': 'f06-headless-no-render-v1',
    }))

    def compile_example(*_args, **_kwargs):
        events.append('source_compile')
        assert owner.opened
        raise RuntimeError('offline compile probe')

    with patch.object(builtin_example_worker, 'core_context', return_value={
        'core_repo': str(tmp_path), 'core_commit': 'commit', 'core_dirty': False,
        }), patch.object(isaac_native_io, '_process_app_owner', return_value=owner), \
         patch.object(builtin_example_worker, 'compile_builtin_pickcube_example', side_effect=compile_example):
        row = builtin_example_worker.run_one(
            spec, catalog, scope, seed=31, output=output,
        )

    assert events == ['app_open', 'source_compile', 'app_close']
    assert row['isaac_app_precompile_start_attempted'] is True
    assert row['isaac_app_precompile_start_completed'] is True
    assert row['isaac_app_launch_profile']['profile_id'] == 'f06-headless-no-render-v1'
    assert row['isaac_app_owner_close_receipt']['close_completed'] is True
    assert row['errors'][0]['phase'] == 'compile'
    assert row['runtime_valid'] is False
    assert not (tmp_path / 'isaac-run' / 'episode.h5').exists()
