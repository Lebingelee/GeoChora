"""Offline regression checks for maintenance boundaries."""
from types import SimpleNamespace

import pytest


def test_position_materialization_preparation_binds_exact_source_and_rejects_invalid(monkeypatch):
    from task_env.runtime.sessions import source as source_owner
    from task_env.runtime.sessions.control import (
        ControlBinding, ControlBindingPlanV1, prepare_position_control_materialization,
    )

    scene = object()
    source = SimpleNamespace(scene_definition=scene)
    artifact = object()
    plan = ControlBindingPlanV1('control-binding-plan-v1', 'b' * 64, (), ())
    binding = ControlBinding('panda-v1/gripper', 0.08)
    value = {'source': source}
    observed = []
    def joints(actual_scene, actual_artifact, actual_source):
        assert (actual_scene, actual_artifact, actual_source) == (scene, artifact, source)
        observed.append('joints')
        return {'j': 'native-j'}
    def frames(actual_artifact, actual_source):
        assert (actual_artifact, actual_source) == (artifact, source)
        observed.append('frames')
        return {'f': 'native-f'}
    monkeypatch.setattr(source_owner, 'position_joint_bindings_from_artifact', joints)
    monkeypatch.setattr(source_owner, 'position_frame_bindings_from_artifact', frames)
    def select(actual_value):
        assert actual_value is value
        observed.append('selector')
        return binding
    kwargs = dict(source=source, artifact=artifact, profiles=(), leaf_position=False,
                  plan=plan, select_binding=select, value=value)
    result = prepare_position_control_materialization(**kwargs)
    assert result == (plan, {'j': 'native-j'}, {'f': 'native-f'}, binding)
    assert observed == ['joints', 'frames', 'selector']
    observed.clear()
    with pytest.raises(ValueError, match='leaf route'):
        prepare_position_control_materialization(**{**kwargs, 'leaf_position': True})
    assert observed == []
    with pytest.raises(TypeError, match='exact ControlBinding'):
        prepare_position_control_materialization(**{**kwargs, 'select_binding': lambda _: object()})


def test_reset_execution_binding_preserves_exact_route_and_requested_seed():
    from dataclasses import replace
    from task_env.artifacts import ExecutionSpecV1, RendererSelectionV1
    from task_env.environment.reference_binding import resolve_reset_execution

    declared = ExecutionSpecV1(
        schema_version='execution-spec-v1', physics_provider='mujoco',
        physics_backend='cpu', physics_profile='example-profile', provider_seed=19,
        determinism_mode='strict',
        render_default=RendererSelectionV1('renderer-selection-v1', 'none', 'none', 'none'),
        physics_device='cpu',
    )
    runtime_input = SimpleNamespace(reset_plan=SimpleNamespace(
        reset_sample=SimpleNamespace(task_seed=31)))
    binding = SimpleNamespace(reset_runtime_input=lambda value: value['runtime_input'])
    current = replace(declared, provider_seed=31)
    value = {'execution_spec_v1': current, 'runtime_input': runtime_input}
    assert resolve_reset_execution(binding, value, declared, seed=31,
                                   provider='mujoco', backend='cpu') is current
    for changed in (replace(current, physics_profile='other'),
                    replace(current, provider_seed=32)):
        with pytest.raises(ValueError, match='exact route or requested seed'):
            resolve_reset_execution(binding, {**value, 'execution_spec_v1': changed},
                                    declared, seed=31, provider='mujoco', backend='cpu')
    runtime_input.reset_plan.reset_sample.task_seed = 32
    with pytest.raises(ValueError, match='exact route or requested seed'):
        resolve_reset_execution(binding, value, declared, seed=31,
                                provider='mujoco', backend='cpu')
    with pytest.raises(ValueError, match='dropped its declared'):
        resolve_reset_execution(binding, {}, declared, seed=31,
                                provider='mujoco', backend='cpu')


@pytest.mark.parametrize('session_fails', [False, True])
def test_mixed_close_receipt_failure_does_not_skip_remaining_cleanup(session_fails):
    from task_env.environment.reference_env import SelectedReferenceEnv

    calls = []
    class Session:
        def close(self):
            calls.append('session')
            if session_fails:
                raise RuntimeError('session failure')

        @property
        def close_receipt(self):
            calls.append('receipt')
            raise LookupError('receipt failure')

        def close_runtime_owner(self):
            calls.append('owner')

    env = SimpleNamespace(
        mixed_control_profile=True, session=Session(), _mixed_episode_end=object(),
        _execution_fault=None, recorder=None, _mixed_close_receipt=None,
        value={'source': SimpleNamespace(execution_source_receipt=SimpleNamespace(
            close=lambda: calls.append('source')))},
        binding=SimpleNamespace(close_task_resources=lambda: calls.append('task')),
    )
    with pytest.raises(RuntimeError if session_fails else LookupError) as raised:
        SelectedReferenceEnv._close_reference_resources(env)
    assert calls == ['session', 'receipt', 'owner', 'source', 'task']
    assert env.session is None
    if session_fails:
        assert any('receipt failure' in note for note in raised.value.__notes__)


@pytest.mark.parametrize('route', ['selected', 'mixed', 'position'])
def test_reference_close_preserves_resource_order_and_primary_fault(route):
    from task_env.environment.reference_env import SelectedReferenceEnv

    events = []
    class Session:
        close_receipt = {'session_closed': True}

        def close(self):
            events.append('session')
            raise RuntimeError('session failure')

        def close_runtime_owner(self):
            events.append('owner')
            raise ValueError('owner failure')

    def camera_close():
        events.append('camera')
        raise LookupError('camera failure')

    def close_source():
        events.append('source')

    def close_task():
        events.append('task')
        return {'closed': True}

    env = SimpleNamespace(
        mixed_control_profile=route == 'mixed', position_profile=route == 'position',
        session=Session(), _mixed_episode_end=object(), _execution_fault=None,
        recorder=None, value={'source': SimpleNamespace(
            execution_source_receipt=SimpleNamespace(close=close_source))},
        binding=SimpleNamespace(close_task_resources=close_task),
        _mixed_close_receipt=None, _published_position_state=None,
        _close_camera_consumer=camera_close,
    )
    expected_error = LookupError if route == 'position' else RuntimeError
    with pytest.raises(expected_error) as raised:
        SelectedReferenceEnv._close_reference_resources(env)
    assert env.session is None
    assert events == (['camera', 'session', 'owner'] if route == 'position'
                      else ['session', 'owner', 'source', 'task'])
    notes = getattr(raised.value, '__notes__', [])
    assert any('owner failure' in note for note in notes)
    if route == 'position':
        assert any('session failure' in note for note in notes)
    if route == 'mixed':
        assert env._mixed_close_receipt == {
            'session_closed': True, 'task_resource_close_receipt': {'closed': True},
        }


@pytest.mark.parametrize(('joint_data', 'sampler', 'capture'), [
    ({'n_dof': 0}, None, False),
    ({'n_dof': 1}, None, True),
    ({}, None, True),
    ({'n_dof': 0}, object(), True),
])
def test_bootstrap_skips_static_capture_only_for_known_empty_scene(monkeypatch, joint_data, sampler, capture):
    import sys
    from types import ModuleType
    from task_env.runtime import bootstrap

    def module(name, **attributes):
        result = ModuleType(name)
        result.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, result)
        return result

    module('geophys', __path__=[])
    module('geophys.demo_runtime', assemble_mjcf_articulated_runtime=lambda *a, **k:
           SimpleNamespace(solver=object(), simulator=object(), render_source=None, render_options=None))
    module('geophys.test_runtime', init_test_backend=lambda backend: None)
    module('solvers', __path__=[])
    module('solvers.rigid', RigidGroundConfig=lambda **kwargs: object())
    compiled = SimpleNamespace(imported_scene=object(), scene_model=SimpleNamespace(joint_data=joint_data),
                               initial_state=object())
    monkeypatch.setattr(bootstrap, 'compile_task_scene', lambda **kwargs: compiled)
    observed = {}
    monkeypatch.setattr(bootstrap, 'GeoPhysRuntimeBoundary', lambda **kwargs:
                        observed.update(kwargs) or object())
    runtime = SimpleNamespace(backend='cpu', physics_dt=0.01, gravity=(0, 0, -9.81),
                              integrator='default', broadphase='default',
                              rigid_solver_backend=None, body_contact_solver_iterations=None,
                              prewarm=False)
    config = SimpleNamespace(runtime=runtime, render=SimpleNamespace(camera_obs=False))
    bootstrap.bootstrap_task_runtime(config=config, composition=object(), scene=object(),
                                     agents=(), objects=(), reset_sampler=sampler)
    assert observed['capture_static_world_children'] is capture


def test_historical_pickcube_rejection_is_available_without_diagnostics_dependency():
    from task_env.environment._historical import make_replay_env
    from task_env.diagnostics.historical_tasks import make_historical_env

    for constructor in (make_replay_env, make_historical_env):
        with pytest.raises(RuntimeError, match='retired.*immutable v1.0.0'):
            constructor('pick-cube-v1')


def test_recording_owner_uses_start_snapshot_without_rereading_source(monkeypatch):
    from pathlib import Path
    from task_env.tasks.reference_env import SelectedReferenceEnv

    calls = []
    def unexpected_read(path):
        calls.append(path)
        raise AssertionError('recording boundary reread source')
    monkeypatch.setattr(Path, 'read_bytes', unexpected_read)
    env = SimpleNamespace(
        _episode_mode='external', info={'is_success': False},
        state=SimpleNamespace(control_step=0, simulation_time=0.0),
        artifact=SimpleNamespace(identity_hash='a' * 64),
        controller=SimpleNamespace(identity='b' * 64), provider='mujoco',
        _active_solution_identity=lambda: 'c' * 64,
        _recording_adapter_source_sha256='d' * 64,
    )
    for step in range(3):
        env.state.control_step = step
        receipt = SelectedReferenceEnv._owners(env)
        assert receipt['owners']['coordinator']['source_sha256'] == 'd' * 64
        assert receipt['control_step'] == step
    assert calls == []


def test_execution_boundary_reuses_xml_digest_but_invalidates_on_replacement(monkeypatch):
    import hashlib
    from task_env.tasks.reference_env import SelectedReferenceEnv

    original_sha256 = hashlib.sha256
    xml_inputs = []
    def counting_sha256(data=b''):
        if data in (b'<scene/>', b'<scene changed="yes"/>'):
            xml_inputs.append(data)
        return original_sha256(data)
    monkeypatch.setattr(hashlib, 'sha256', counting_sha256)
    class BoundaryEnv(SimpleNamespace):
        _source_xml_sha256 = SelectedReferenceEnv._source_xml_sha256
        _execution_boundary = SelectedReferenceEnv._execution_boundary

    scene = SimpleNamespace(source_id='scene', xml='<scene/>')
    env = BoundaryEnv(
        value={'source': SimpleNamespace(scene_source=scene, source_closure_digest=None)},
        _selected_episode_id='episode', artifact=SimpleNamespace(identity_hash='a' * 64),
        session=SimpleNamespace(provider_materialization_id='materialization'),
        controller=SimpleNamespace(identity='b' * 64),
        _active_solution_identity=lambda: 'c' * 64,
        sample=SimpleNamespace(sample_id='reset'),
    )
    info = SimpleNamespace(control_step=0, simulation_time=0.0)
    first = env._execution_boundary(info)
    info.control_step = 1
    info.simulation_time = 0.01
    second = env._execution_boundary(info)
    assert first['identity_hash'] != second['identity_hash']
    assert first['source_xml_sha256'] == second['source_xml_sha256']
    scene.xml = '<scene changed="yes"/>'
    third = env._execution_boundary(info)
    assert third['source_xml_sha256'] != second['source_xml_sha256']
    assert third['identity_hash'] != second['identity_hash']
    assert xml_inputs == [b'<scene/>', b'<scene changed="yes"/>']


def test_selected_compatibility_exports_reference_the_canonical_objects():
    from task_env.environment.reference_binding import ReferenceTaskBinding
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.tasks.reference_env import (
        ReferenceTaskBinding as old_binding,
        SelectedReferenceEnv as old_env,
    )

    assert old_env is SelectedReferenceEnv
    assert old_binding is ReferenceTaskBinding


def test_example_bootstrap_accepts_explicit_geophys_source_and_rejects_missing(monkeypatch, tmp_path):
    import sys
    from examples._common import bootstrap_imports

    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setenv('GEOCHORA_GEOPHYS_SRC', str(tmp_path / 'missing'))
    with pytest.raises(ValueError, match='GeoPhys src directory'):
        bootstrap_imports()
    source = tmp_path / 'src'
    (source / 'scene').mkdir(parents=True)
    (source / 'scene' / '__init__.py').write_text('')
    monkeypatch.setenv('GEOCHORA_GEOPHYS_SRC', str(source))
    monkeypatch.setitem(sys.modules, 'scene', SimpleNamespace(__file__=str(tmp_path / 'old' / 'scene.py')))
    with pytest.raises(RuntimeError, match='already imported outside'):
        bootstrap_imports()
    monkeypatch.delitem(sys.modules, 'scene')
    bootstrap_imports()
    assert str(source) in sys.path


def test_start_routes_explicit_paths_and_rejects_unsupported_without_spawning(monkeypatch, tmp_path):
    import sys
    from examples import start

    source = tmp_path / 'geophys' / 'src'
    (source / 'scene').mkdir(parents=True)
    (source / 'scene' / '__init__.py').write_text('')
    captured = []
    monkeypatch.setattr(start.subprocess, 'run', lambda command, **kwargs: (
        captured.append((command, kwargs)) or SimpleNamespace(returncode=0)
    ))
    base = ['--python', sys.executable, '--geophys-src', str(source),
            '--uid', 'pendulum-v1', '--provider', 'geophys', '--backend', 'cpu',
            '--renderer', 'none', '--seed', '73']
    assert start.main(base) == 0
    command, options = captured[0]
    assert command[0] == str(__import__('pathlib').Path(sys.executable).resolve())
    assert command[1].endswith('examples/tasks/scalar_step.py')
    assert command[-2:] == ['--seed', '73']
    assert options['env']['GEOCHORA_GEOPHYS_SRC'] == str(source)
    assert options['env']['GEOCHORA_CORE_PYTHON'] == command[0]
    assert options['env']['PYTHONPATH'].split(__import__('os').pathsep) == [str(start.ROOT), str(source)]
    with pytest.raises(SystemExit):
        start.main(base[:-4] + ['--backend', 'cuda', '--renderer', 'none'])
    assert len(captured) == 1


def test_start_passes_external_isaac_interpreter_and_manifest(monkeypatch, tmp_path):
    import sys
    from examples import start

    source = tmp_path / 'src'
    (source / 'scene').mkdir(parents=True)
    (source / 'scene' / '__init__.py').write_text('')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{}')
    captured = []
    monkeypatch.setattr(start.subprocess, 'run', lambda command, **kwargs: (
        captured.append((command, kwargs)) or SimpleNamespace(returncode=0)
    ))
    assert start.main(['--python', sys.executable, '--geophys-src', str(source),
                       '--uid', 'pick-cube-p16-reference-v1', '--provider', 'isaacsim',
                       '--backend', 'cuda', '--renderer', 'none', '--isaac-python', sys.executable,
                       '--source-delivery-manifest', str(manifest), '--seed', '31']) == 0
    command, options = captured[0]
    assert command[command.index('--isaac-python') + 1] == str(__import__('pathlib').Path(sys.executable).resolve())
    assert command[command.index('--source-delivery-manifest') + 1] == str(manifest)
    assert options['env']['GEOCHORA_GEOPHYS_SRC'] == str(source)


def test_leaf_action_compatibility_exports_use_controller_owned_types():
    from task_env.controllers.canonical.leaf_actions import (
        AttachedLeafActionSetV1, LeafPositionActionSetV1,
    )
    from task_env.tasks.position_candidate.attached_leaf_candidate import AttachedLeafActionSetV1 as old_attached
    from task_env.tasks.position_candidate.leaf_candidate import LeafPositionActionSetV1 as old_leaf

    assert old_attached is AttachedLeafActionSetV1
    assert old_leaf is LeafPositionActionSetV1


def test_static_boundary_skips_unavailable_articulated_pose_reader_and_rejects_override():
    import numpy as np
    from task_env.environment import EpisodePhysicsState, StageUnavailableError
    from task_env.runtime.boundary import GeoPhysRuntimeBoundary

    class StaticPhysics:
        n_actuators = 0
        restores = 0
        def read_static_world_child_body_poses(self):
            raise AssertionError('static route must not ask for articulated pose fields')
        def snapshot(self):
            return {'marker': np.array([1.0])}
        def restore(self, _state):
            self.restores += 1
        def synchronize_kinematic_state(self, **_kwargs):
            pass

    physics = StaticPhysics()
    empty = np.zeros(0, dtype=np.float32)
    state = EpisodePhysicsState(empty, empty, empty, empty, empty)
    boundary = GeoPhysRuntimeBoundary(
        physics=physics, scheduler=SimpleNamespace(), physics_dt=0.002,
        ctrl_range=np.empty((0, 2)), initial_state=state,
        capture_static_world_children=False,
    )
    restores = physics.restores
    with pytest.raises(StageUnavailableError, match='static world-child reset overrides'):
        boundary.apply_reset_state(state, static_world_child_poses={0: (np.zeros(3), np.ones(4))})
    assert physics.restores == restores


def test_articulated_boundary_still_restores_static_world_children():
    import numpy as np
    from task_env.environment import EpisodePhysicsState
    from task_env.runtime.boundary import GeoPhysRuntimeBoundary

    class ArticulatedPhysics:
        n_actuators = 0
        def __init__(self):
            self.writes = []
        def read_static_world_child_body_poses(self):
            return np.array([3], dtype=np.int32), np.array([[1., 2., 3.]]), np.array([[1., 0., 0., 0.]])
        def write_static_world_child_body_poses(self, ids, positions, orientations):
            self.writes.append((np.array(ids), np.array(positions), np.array(orientations)))
        def snapshot(self):
            return {'marker': np.array([1.0])}
        def restore(self, _state):
            pass
        def synchronize_kinematic_state(self, **_kwargs):
            pass

    physics = ArticulatedPhysics()
    empty = np.zeros(0, dtype=np.float32)
    state = EpisodePhysicsState(empty, empty, empty, empty, empty)
    boundary = GeoPhysRuntimeBoundary(physics=physics, scheduler=SimpleNamespace(),
                                     physics_dt=0.002, ctrl_range=np.empty((0, 2)),
                                     initial_state=state)
    assert len(physics.writes) == 1
    boundary.apply_reset_state(state)
    assert len(physics.writes) == 2
    assert physics.writes[-1][0].tolist() == [3]
    assert physics.writes[-1][1].tolist() == [[1., 2., 3.]]


def test_scalar_example_checks_spaces_and_closes(monkeypatch, capsys):
    import json
    import numpy as np
    import task_env
    from examples.tasks import scalar_step

    class Space:
        def contains(self, value):
            return value['state'].shape == (3,) and value['state'].dtype == np.float32
    class Env:
        observation_space = Space()
        closed = False
        def reset(self, *, seed):
            assert seed == 73
            return {'state': np.zeros(3, dtype=np.float32)}, {}
        def step(self, action):
            assert action['torque'].shape == (1,)
            return {'state': np.ones(3, dtype=np.float32)}, 0.5, False, False, {'is_success': False}
        def close(self):
            self.closed = True
    env = Env()
    monkeypatch.setattr(scalar_step, 'bootstrap_imports', lambda: None)
    monkeypatch.setattr(task_env, 'make_env', lambda *args, **kwargs: env)
    assert scalar_step.main(['--uid', 'pendulum-v1', '--seed', '73']) == 0
    result = json.loads(capsys.readouterr().out)
    assert env.closed and result['close_returned']
    assert result['action']['torque'] == {'shape': [1], 'dtype': 'float32'}
    assert result['step_observation']['state'] == {'shape': [3], 'dtype': 'float32'}


def test_artifact_digest_reuses_immutable_snapshot_and_recomputes_replacements(monkeypatch):
    import hashlib
    import json
    from dataclasses import FrozenInstanceError, replace
    from task_env.artifacts import TaskArtifact
    from task_env.tasks.pick_cube.task import build_artifact

    original = build_artifact()
    artifact = replace(original)
    canonical = json.dumps(artifact.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False)
    expected = hashlib.sha256(canonical.encode()).hexdigest()
    real_to_mapping = TaskArtifact.to_mapping
    calls = []
    def counted(value):
        calls.append(value)
        return real_to_mapping(value)
    monkeypatch.setattr(TaskArtifact, 'to_mapping', counted)
    assert artifact.identity_hash == expected
    assert artifact.identity_hash == expected
    assert len(calls) == 1
    with pytest.raises((FrozenInstanceError, AttributeError)):
        artifact.artifact_id = 'changed'
    with pytest.raises(TypeError):
        artifact.semantics.parameters_si['new'] = 1.0
    changed = replace(artifact, artifact_version='v999')
    assert changed.identity_hash != expected
    assert len(calls) == 2


def test_artifact_digest_does_not_cache_unknown_mutable_contract_subclasses():
    from dataclasses import replace
    from task_env.artifacts import SemanticDefinition
    from task_env.tasks.pick_cube.task import build_artifact

    class MutableSemantic(SemanticDefinition):
        def to_mapping(self):
            result = super().to_mapping()
            result['success_definition'] = self.extra[0]
            return result
    base = build_artifact()
    data = base.semantics.to_mapping()
    semantic = MutableSemantic.from_mapping(data)
    object.__setattr__(semantic, 'extra', ['first'])
    artifact = replace(base, semantics=semantic)
    first = artifact.identity_hash
    semantic.extra[0] = 'second'
    assert artifact.identity_hash != first


def test_selected_source_identity_includes_action_and_artifact_contract_bytes():
    import hashlib
    from pathlib import Path
    from task_env.artifacts import TaskArtifact
    from task_env.tasks.pick_cube import specialization as pick
    from task_env.tasks.nut_assembly import specialization as nut

    root = Path(pick.__file__).resolve().parents[3]
    pick_files = pick._source_identity_files(pick.build_artifact(), TaskArtifact)
    nut_files = nut._source_identity_files()
    for relative in ('task_env/artifacts/contracts.py', 'task_env/planners/contracts.py',
                     'task_env/environment/lifecycle.py'):
        expected = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        assert pick_files[relative] == expected
        assert nut_files[relative] == expected
    relative = 'task_env/planners/completion.py'
    expected = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    assert nut_files[relative] == expected
    assert pick_files[relative] == expected


def test_artifact_digest_detects_low_level_frozen_field_tampering():
    from dataclasses import replace
    from task_env.tasks.pick_cube.task import build_artifact

    original = build_artifact()
    artifact = replace(original, semantics=replace(original.semantics))
    first = artifact.identity_hash
    object.__setattr__(artifact.semantics, 'success_definition', 'tampered-success')
    assert artifact.identity_hash != first
    object.__setattr__(artifact.semantics, 'success_definition', original.semantics.success_definition)
    assert artifact.identity_hash == first


def test_artifact_digest_never_reuses_a_replaced_mutable_nested_mapping():
    from dataclasses import replace
    from task_env.tasks.pick_cube.task import build_artifact

    original = build_artifact()
    artifact = replace(original, semantics=replace(original.semantics))
    original_hash = artifact.identity_hash
    mutable = dict(artifact.semantics.parameters_si)
    object.__setattr__(artifact.semantics, 'parameters_si', mutable)
    assert artifact.identity_hash == original_hash
    key = next(iter(mutable))
    mutable[key] = float(mutable[key]) + 1.0
    assert artifact.identity_hash != original_hash
    assert '_immutable_identity_hash' not in artifact.__dict__


def test_artifact_digest_distinguishes_signed_zero_after_frozen_field_tampering():
    from dataclasses import replace
    from types import MappingProxyType
    from task_env.tasks.pick_cube.task import build_artifact

    original = build_artifact()
    artifact = replace(original, semantics=replace(original.semantics))
    values = dict(artifact.semantics.parameters_si)
    key = next(iter(values))
    values[key] = -0.0
    object.__setattr__(artifact.semantics, 'parameters_si', MappingProxyType(dict(values)))
    negative = artifact.identity_hash
    values[key] = 0.0
    object.__setattr__(artifact.semantics, 'parameters_si', MappingProxyType(dict(values)))
    assert artifact.identity_hash != negative


def test_usd_task_reset_identity_closure_rejects_each_wrong_source():
    from types import SimpleNamespace as Namespace
    import pytest
    from task_env.runtime.sessions.source import validate_usd_task_reset_identities

    task = Namespace(identity_hash='task')
    artifact = Namespace(identity_hash='artifact', scene_identity_hash='scene')
    source = Namespace(
        task_artifact=Namespace(identity_hash='artifact'),
        scene_definition=Namespace(identity_hash='scene'),
        scene_source=Namespace(task_source_identity_sha256='task', scene_identity_sha256='scene'),
    )
    plan = Namespace(role_binding=Namespace(task_source_identity_hash='task', scene_identity_hash='scene'),
                     reset_sample=Namespace(task_artifact_hash='artifact'))

    def check():
        validate_usd_task_reset_identities(task, artifact, source, plan, error_message='identity mismatch')

    check()
    for owner, name in (
        (source.task_artifact, 'identity_hash'),
        (artifact, 'scene_identity_hash'),
        (source.scene_source, 'task_source_identity_sha256'),
        (source.scene_source, 'scene_identity_sha256'),
        (plan.role_binding, 'task_source_identity_hash'),
        (plan.role_binding, 'scene_identity_hash'),
        (plan.reset_sample, 'task_artifact_hash'),
    ):
        value = getattr(owner, name)
        setattr(owner, name, 'wrong')
        with pytest.raises(ValueError, match='identity mismatch'):
            check()
        setattr(owner, name, value)
    check()


def test_usd_task_reset_identity_closure_accepts_real_f04_input_and_rejects_wrong_plan():
    from dataclasses import replace
    from task_env.diagnostics.tasks.f04_candidate_s1_support import build_candidate
    from task_env.runtime.sessions.source import validate_usd_task_reset_identities

    candidate = build_candidate('menagerie-panda')
    validate_usd_task_reset_identities(
        candidate.task_source, candidate.artifact, candidate.runtime_source, candidate.reset_plan,
        error_message='identity mismatch',
    )
    wrong_plan = replace(candidate.reset_plan, role_binding=replace(
        candidate.reset_plan.role_binding, scene_identity_hash='0' * 64,
    ))
    with pytest.raises(ValueError, match='identity mismatch'):
        validate_usd_task_reset_identities(
            candidate.task_source, candidate.artifact, candidate.runtime_source, wrong_plan,
            error_message='identity mismatch',
        )
