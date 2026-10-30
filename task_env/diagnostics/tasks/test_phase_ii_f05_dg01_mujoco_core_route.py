"""DG01 source-bound MJCF construction and admission contracts."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from task_env.runtime.sessions.source import project_scene_definition_v3_to_mjcf
from task_env.tasks.position_candidate.source import _f05_dg01_scene


def _projection_fixture(*, freejoint_count=1):
    scene = _f05_dg01_scene()
    joints = ''.join(f'<joint name="{name}"/>' for name in (
        'joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6', 'joint7',
        'finger_joint1', 'finger_joint2',
    ))
    freejoints = '<freejoint name="cube_freejoint"/>' * freejoint_count
    source = f'<mujoco><worldbody><body name="panda">{joints}{freejoints}</body></worldbody></mujoco>'
    return scene, source


def test_canonical_mjcf_projection_retains_exact_floating_joint():
    scene, source = _projection_fixture()
    projected = project_scene_definition_v3_to_mjcf(source, scene)
    assert '<freejoint name="cube_freejoint"' in projected
    assert projected.count('name="cube_freejoint"') == 1


@pytest.mark.parametrize('count', [0, 2])
def test_canonical_mjcf_projection_rejects_missing_or_ambiguous_floating_joint(count):
    scene, source = _projection_fixture(freejoint_count=count)
    with pytest.raises(ValueError, match='canonical floating Joint.*exactly one'):
        project_scene_definition_v3_to_mjcf(source, scene)


def test_dg01_candidate_build_and_profile_admission_are_provider_free(tmp_path):
    repo_root = Path(__file__).resolve().parents[3]
    provider_src = repo_root.parent / 'GeoPhys' / 'src'
    assert provider_src.is_dir()
    script = r'''
import importlib.abc
import json
import sys

import task_env.runtime.sessions.api as session_api
import task_env.runtime.sessions.control as session_control
mujoco_manifest = session_api.provider_manifest('mujoco')
assert 'mujoco' not in sys.modules
original_provider_manifest = session_api.provider_manifest
session_api.provider_manifest = lambda provider: (
    mujoco_manifest if provider == 'mujoco' else original_provider_manifest(provider)
)

blocked = ('mujoco', 'taichi', 'isaacsim', 'omni', 'newton', 'solvers')
class BlockNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
            raise AssertionError('native/solver import during provider-free candidate build: ' + fullname)
        return None
sys.meta_path.insert(0, BlockNative())
from task_env.tasks.position_candidate.builder import build_f05_dg01_mujoco_candidate
from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
from task_env.runtime.sessions.api import materialize
from task_env.runtime.sessions.control import ControlBinding, materialize_control
from task_env.artifacts import ExecutionSpec
candidate = build_f05_dg01_mujoco_candidate(sys.argv[1], horizon=300)
profile = PandaPositionServoProfileV1.from_source(candidate.artifact, candidate.source)
try:
    materialize(candidate.artifact, candidate.execution, source=candidate.source)
except ValueError as error:
    assert 'requires its exact versioned candidate input' in str(error)
else:
    raise AssertionError('bare DG01 profile was admitted without its source-bound input')
observed_execution_types = []
observed_manifest_profiles = []
original_admit = session_api.admit_capabilities
def observe_admission(required, manifest, execution=None):
    assert type(execution) is ExecutionSpec
    observed_execution_types.append(type(execution).__name__)
    observed_manifest_profiles.append(manifest.physics_profile)
    return original_admit(required, manifest, execution)
session_api.admit_capabilities = observe_admission
session_control.admit_capabilities = observe_admission
class NativeBoundaryReceipt:
    pass
def stop_at_native_boundary(artifact, execution, source, *, f05_dg01_input=None):
    assert artifact is candidate.artifact
    assert source is candidate.source
    assert f05_dg01_input is candidate.candidate_input
    assert type(execution) is ExecutionSpec
    return NativeBoundaryReceipt()
session_api._materialize_admitted = stop_at_native_boundary
session = materialize(
    candidate.artifact, candidate.execution, source=candidate.source,
    _f05_dg01_mujoco_input=candidate.candidate_input,
)
assert observed_execution_types == ['ExecutionSpec']
assert observed_manifest_profiles == ['mujoco-mjcf-f05-dg01-core-v1']
assert session._declared_execution_spec_v1_identity_sha256 == candidate.execution.identity_hash
controlled = materialize_control(
    candidate.artifact,
    candidate.execution,
    source=candidate.source,
    binding=ControlBinding('panda-main/gripper', .08),
    controller_binding_plan=candidate.controller_binding_plan,
    controller_profile=profile,
    f05_dg01_mujoco_input=candidate.candidate_input,
)
assert type(controlled) is NativeBoundaryReceipt
assert controlled._control_binding == ControlBinding('panda-main/gripper', .08)
assert controlled._control_binding_plan is candidate.controller_binding_plan
assert controlled._declared_execution_spec_v1_identity_sha256 == candidate.execution.identity_hash
assert observed_execution_types == ['ExecutionSpec', 'ExecutionSpec', 'ExecutionSpec']
assert observed_manifest_profiles == [
    'mujoco-mjcf-f05-dg01-core-v1',
    'mujoco-mjcf-f05-dg01-core-v1',
    'mujoco-mjcf-f05-dg01-core-v1',
]
assert candidate.panda_file_count == 68
assert candidate.panda_closure_digest == 'a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a'
assert len(candidate.candidate_input.runtime_source.joints) == 9
assert len(candidate.candidate_input.runtime_source.free_joints) == 1
assert candidate.candidate_input.artifact.initialization.poses_world['free-cube/free_cube'].position == (1.0, 0.5, 0.9)
assert not any(name == root or name.startswith(root + '.') for name in sys.modules for root in blocked)
print(json.dumps({
    'candidate_input_schema': candidate.candidate_input.schema_version,
    'artifact_identity_sha256': candidate.artifact.identity_hash,
    'scene_identity_sha256': candidate.source.scene_definition.identity_hash,
    'source_id': candidate.source.source_id,
    'source_closure_sha256': candidate.source_closure_digest,
    'derived_scene_sha256': candidate.derived_source_sha256,
    'panda_closure_sha256': candidate.panda_closure_digest,
    'panda_file_count': candidate.panda_file_count,
    'execution_identity_sha256': candidate.execution.identity_hash,
    'exact_core_admission_execution_type': observed_execution_types,
    'exact_core_admission_profile': observed_manifest_profiles,
    'materialize_control_admitted_exact_candidate': True,
    'materialization_stopped_at_native_boundary': True,
    'native_imports': [],
}, sort_keys=True))
candidate.env.close()
'''
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join((str(repo_root), str(provider_src)))
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path / 'candidate-source')],
        cwd=repo_root, env=env, check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout.splitlines()[-1])
    assert evidence['panda_file_count'] == 68
    assert evidence['native_imports'] == []
    assert evidence['exact_core_admission_execution_type'] == [
        'ExecutionSpec', 'ExecutionSpec', 'ExecutionSpec',
    ]
    assert evidence['exact_core_admission_profile'] == [
        'mujoco-mjcf-f05-dg01-core-v1',
        'mujoco-mjcf-f05-dg01-core-v1',
        'mujoco-mjcf-f05-dg01-core-v1',
    ]
    assert evidence['materialize_control_admitted_exact_candidate'] is True
    assert evidence['materialization_stopped_at_native_boundary'] is True
    assert len(evidence['derived_scene_sha256']) == 64


def test_position_control_boundary_is_carried_only_during_session_apply(monkeypatch):
    from types import SimpleNamespace

    import task_env.runtime.sessions.control as session_control
    from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock
    from task_env.controllers.canonical.contracts import (
        CanonicalControlTarget,
        GripperControlTarget,
        PositionControlTargetV1,
    )

    boundary = StateBoundaryIdentity(
        'state-boundary-identity-v1', 'episode-1', 'reset-' + 'a' * 64,
        'b' * 64, 'scene-instance-1', 'provider-materialization-1', 0, 0,
    )
    clock = StateSampleClock('state-sample-clock-v1', 'evaluation_boundary', 0, 0.0)
    joints = tuple(f'panda-main/joint{index}' for index in range(1, 8))
    canonical = CanonicalControlTarget(
        'canonical-control-v0', 'c' * 64, 'd' * 64, joints,
        {name: 0.0 for name in joints}, {name: 0.0 for name in joints},
        GripperControlTarget('panda-main/gripper', .04, 5.0, .04),
    )
    target = PositionControlTargetV1(
        'position-control-target-v1', 'writer-v1', 'd' * 64, 'e' * 64,
        'f' * 64, boundary, clock, canonical,
    )
    profile = SimpleNamespace(
        writer_id='writer-v1', identity='d' * 64,
        source=SimpleNamespace(source_closure_digest='f' * 64),
        gripper_semantic_id='panda-main/gripper',
        artifact=SimpleNamespace(identity_hash='c' * 64),
    )
    publication = SimpleNamespace(view=SimpleNamespace(boundary=boundary, sample_clock=clock))
    monkeypatch.setattr(
        session_control,
        '_validate_position_source_boundary',
        lambda *_args, **_kwargs: 'e' * 64,
    )

    class Session:
        def __init__(self):
            self._position_applied_boundary_ids = set()
            self._position_target_in_flight = None
            self._position_target_source_boundary_in_flight = None
            self.seen_boundary = None

        def apply_control(self, applied_target):
            self.seen_boundary = self._position_target_source_boundary_in_flight
            return SimpleNamespace(target_hash=applied_target.identity_hash)

    session = Session()
    acknowledgement = session_control.apply_position_control_target(
        session, target, controller_profile=profile, plan=object(),
        publication=publication, scene=None, joint_bindings=None, frame_bindings=None,
    )

    assert session.seen_boundary is boundary
    assert acknowledgement.target_hash == canonical.identity_hash
    assert session._position_target_in_flight is None
    assert session._position_target_source_boundary_in_flight is None
