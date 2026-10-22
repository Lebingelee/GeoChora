"""P99 public UID admission/import contracts and real failure boundaries (CPU)."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import subprocess
import sys
from unittest.mock import patch

import pytest

from task_env import make_env
from task_env.controllers.canonical.contracts import ControlGroupActionV1, StructuredActionRequestV1


UID = 'panda-position-servo-candidate-v1'


def test_registration_is_provider_free_and_does_not_import_diagnostics():
    code = '''
import sys
from importlib.abc import MetaPathFinder
class BlockNative(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'scene', 'taichi', 'taichi_forge', 'mujoco'}:
            raise AssertionError('native import during registration: ' + fullname)
        if fullname.startswith('task_env.diagnostics') or '.test_' in fullname:
            raise AssertionError('diagnostic/test dependency: ' + fullname)
sys.meta_path.insert(0, BlockNative())
import task_env.tasks
import task_env.tasks.position_candidate.builder
from task_env.registry import ENV_REGISTRY
assert ENV_REGISTRY.get('panda-position-servo-candidate-v1').uid == 'panda-position-servo-candidate-v1'
assert ENV_REGISTRY.get('pick-cube-p16-reference-v1').uid == 'pick-cube-p16-reference-v1'
assert ENV_REGISTRY.get('nut-assembly-outcome-reference-v1').uid == 'nut-assembly-outcome-reference-v1'
'''
    subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True)


@pytest.mark.parametrize('config', [
    {'provider': 'mujoco'}, {'provider': 'sapien'}, {'backend': 'cuda'},
    {'horizon': True}, {'horizon': 0}, {'horizon': 6001},
    {'runtime': {'backend': 'cpu'}}, {'profile': 'production-r1'},
    {'source_workspace': ''}, {'source_workspace': 12},
])
def test_invalid_public_config_refused_before_source_construction(config):
    with patch('task_env.tasks.position_candidate.builder.build_position_candidate') as build:
        with pytest.raises(ValueError):
            make_env(UID, config=config)
        build.assert_not_called()


def test_render_extra_kwargs_and_existing_source_bytes_refused(tmp_path):
    (tmp_path / 'protected').write_bytes(b'preserve source')
    with patch('task_env.tasks.position_candidate.builder.build_position_candidate') as build:
        for kwargs in ({'render_mode': 'rgb_array'}, {'seed': 31},
                       {'config': {'source_workspace': str(tmp_path)}}):
            with pytest.raises(ValueError):
                make_env(UID, **kwargs)
        build.assert_not_called()
    assert (tmp_path / 'protected').read_bytes() == b'preserve source'


def test_wrong_source_identity_fails_before_provider_materialization(tmp_path, monkeypatch):
    from task_env.tasks.position_candidate import source
    import json
    mapping = json.loads((source.FIXTURE_ROOT / 'a05_scene_definition_v3.json').read_text())
    mapping['scene_id'] += '-wrong'
    (tmp_path / 'a05_scene_definition_v3.json').write_text(json.dumps(mapping))
    monkeypatch.setattr(source, 'FIXTURE_ROOT', tmp_path)
    with patch('task_env.runtime.sessions.api.materialize') as materialize:
        with pytest.raises(ValueError, match='Scene identity mismatch'):
            make_env(UID, config={'source_workspace': str(tmp_path / 'build')})
        materialize.assert_not_called()


def test_public_request_identity_and_record_append_failure_are_fail_closed(tmp_path):
    from task_env.recorders import TransitionRecorder
    env = make_env(UID, config={'source_workspace': str(tmp_path / 'source'), 'horizon': 4})
    try:
        observation, _ = env.reset()
        assert env.observation_space.contains(observation)
        before_read = env.typed_state.view.boundary
        observed, info, _ = env.observation(env.state)
        for name, value in observation['state'].items():
            assert np.array_equal(value, observed['state'][name])
        assert info['state_boundary_id'] == before_read.boundary_id
        assert env.typed_state.view.boundary == before_read
        plan = env.position_plan
        schema = plan.controller_bindings[0].action_schema.schema_id
        hand = tuple(float(x) for x in observation['state']['hand_pose'])
        request = StructuredActionRequestV1(
            'structured-action-request-v1', plan.scene_identity_hash, plan.identity_hash,
            (ControlGroupActionV1('control-group-action-v1', 'panda-main', 'arm', schema, hand),
             ControlGroupActionV1('control-group-action-v1', 'panda-main', 'gripper', schema, (1.0,))),
        )
        env.start_recording(tmp_path / 'fault.h5')
        before = env.typed_state.view.boundary
        with patch.object(type(env.session), 'step', side_effect=AssertionError('must not step')):
            for field in ('scene_identity_hash', 'binding_identity_hash'):
                with pytest.raises(ValueError):
                    env.step(replace(request, **{field: 'f' * 64}))
        assert env.typed_state.view.boundary == before
        assert (env.recorder.transition_count, env.recorder.observation_count) == (0, 1)
        with patch.object(TransitionRecorder, 'append_transition', side_effect=OSError('injected recording failure')):
            with pytest.raises(OSError, match='injected recording failure'):
                env.step(request)
        assert env.execution_fault is not None
        assert env.execution_fault.transition_status == 'rejected'
        assert (env.recorder.transition_count, env.recorder.observation_count) == (0, 1)
        assert env.state.control_step == 1
        with pytest.raises(RuntimeError, match='faulted'):
            env.step(request)
    finally:
        env.close()


def test_task_owned_source_bytes_match_retained_historical_inputs():
    from task_env.tasks.position_candidate.source import FIXTURE_ROOT
    historical = Path(__file__).with_name('fixtures') / 'phase_ii_d01a'
    for path in FIXTURE_ROOT.iterdir():
        assert path.read_bytes() == (historical / path.name).read_bytes()
