"""Historical retired-candidate checks and compatibility fixture exports.

Current physical claims live under v2.1.1. The remaining tests describe a
removed candidate factory and an obsolete reset fake; do not reinterpret a
skip as evidence for the current Runtime contract.
"""
from dataclasses import replace
import pytest

from task_env.artifacts import FrameReference
from task_env.artifacts.contracts import CapabilityAssessmentRowV1, CapabilityAssessmentV1
from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock
from task_env.controllers.canonical.physical_commands import (
    PhysicalCommandContextV1, ContributionPolicyV1, JointEffortV1,
    PhysicalJointChannelV1, PhysicalControlBindingV1, PhysicalCommandBatchV1,
    PhysicalJointBuildReceiptV1,
)
from task_env.runtime.sessions.physical_control import (
    compile_physical_control_binding, prepare_physical_command_batch,
)
from task_env.diagnostics.tasks.physical_contract_fixtures import (
    _case, _joint_receipt, _scene_v3, _primary_closure,
)

pytestmark = pytest.mark.skip(reason='historical candidate/reset fixture; see v2.1.1 diagnostics claim map')


def test_registry_forwards_physical_execution_to_versioned_builder(monkeypatch):
    """Routing only: the builder and input are substituted, not source evidence."""
    from types import SimpleNamespace
    from task_env.registry import make_env
    from task_env.tasks.position_candidate import builder

    candidate = object.__new__(builder.F04PositionCandidateInputV1)
    monkeypatch.setattr(builder.F04PositionCandidateInputV1, 'validate', lambda self: None)
    physical = object()
    sentinel = object()
    seen = []
    def capture(value, **kwargs):
        seen.append((value, kwargs))
        return SimpleNamespace(env=sentinel)
    monkeypatch.setattr(builder, 'build_versioned_position_candidate', capture)
    result = make_env('panda-position-servo-candidate-v1', config={
        'versioned_input': candidate, 'physical_execution': physical, 'horizon': 8})
    assert result is sentinel
    assert seen[0][0] is candidate
    assert seen[0][1]['physical_execution'] is physical


def test_registry_mujoco_selection_requires_physical_profile_and_cpu(monkeypatch, tmp_path):
    """Routing only: no source construction or provider initialization."""
    from types import SimpleNamespace
    from task_env.registry import make_env
    from task_env.tasks.position_candidate import builder

    sentinel, seen = object(), []
    def capture(workspace, **kwargs):
        seen.append((workspace, kwargs))
        return SimpleNamespace(env=sentinel)
    monkeypatch.setattr(builder, 'build_position_candidate', capture)
    config = {'provider': 'mujoco', 'backend': 'cpu',
              'physical_profile': 'panda-direct-effort-v1', 'source_workspace': tmp_path}
    assert make_env('panda-position-servo-candidate-v1', config=config) is sentinel
    assert seen[0][1]['provider'] == 'mujoco'
    assert seen[0][1]['physical_profile'] == 'panda-direct-effort-v1'
    with pytest.raises(ValueError, match='admits GeoPhys CPU'):
        make_env('panda-position-servo-candidate-v1', config={**config, 'physical_profile': None})
    with pytest.raises(ValueError, match='admits GeoPhys CPU'):
        make_env('panda-position-servo-candidate-v1', config={**config, 'backend': 'cuda'})
    assert len(seen) == 1


def test_registry_physical_preflight_rejects_foreign_source_before_build(monkeypatch):
    """Actual registry/builder preflight with a substituted input, no provider."""
    from types import SimpleNamespace
    from task_env.artifacts.state import StateRequirements
    from task_env.controllers.canonical.model import ControllerModelRequirementV1, AffineJointBiasModelV1
    from task_env.controllers.canonical.physical_controller import LinearEffortProfileV1, LinearEffortControllerV1
    from task_env.registry import make_env
    from task_env.runtime.sessions.physical_control import PhysicalControlExecutionV1
    from task_env.tasks.position_candidate.builder import F04PositionCandidateInputV1

    plan, _, _, _ = _case()
    req = ControllerModelRequirementV1('controller-model-requirement-v1', 'affine-example',
        'geochora', 'v1', 'stdlib', 'source-a', 'b'*64, ('arm/drive',), ('rad',),
        'joint_bias', ('N*m',), 'joint-axis', 'evaluation_boundary', .01, 0.,
        'pure_no_physics_step', 'controller-a', 'none', 'required')
    model = AffineJointBiasModelV1('affine-joint-bias-model-v1', req, (0.,), (0.,), (0.,))
    profile = LinearEffortProfileV1('linear-effort-profile-v1', 'controller-a',
        ('action',), ('arm/drive',), ((1.,),), req)
    controller = LinearEffortControllerV1(profile, plan.binding, model)
    execution = PhysicalControlExecutionV1(plan, (controller,), plan.scene, {}, {},
        StateRequirements('state-requirements-v1', 'controller', 'controller-a', ()), 1)
    candidate = object.__new__(F04PositionCandidateInputV1)
    object.__setattr__(candidate, 'artifact', SimpleNamespace(identity_hash='a'*64))
    object.__setattr__(candidate, 'runtime_source', SimpleNamespace(
        scene_definition=plan.scene, source_id='foreign', source_closure_digest='b'*64))
    monkeypatch.setattr(F04PositionCandidateInputV1, 'validate', lambda self: None)
    with pytest.raises(ValueError, match='Scene, Artifact, or source'):
        make_env('panda-position-servo-candidate-v1', config={
            'versioned_input': candidate, 'physical_execution': execution})


def test_physical_reset_preflight_rejects_before_session_materialization(monkeypatch):
    """Exercise preparation only: no reset, provider initialization, or source parsing."""
    from types import SimpleNamespace
    from task_env.environment.reference_env import SelectedReferenceEnv
    from task_env.environment.types import StageUnavailableError
    env = object.__new__(SelectedReferenceEnv)
    env._closed = False
    env.provider, env.backend = 'isaacsim', 'cpu'
    env.binding = SimpleNamespace(physical_control_profile=lambda _env: None)
    env.session = object()
    previous = env.session
    with pytest.raises(StageUnavailableError, match='physical-control RuntimeSession adapter'):
        env._prepare_reference_reset()
    assert env.session is previous
    env.provider, env.backend, env.position_profile = 'mujoco', 'cpu', False
    env.artifact = object()
    env.value = {'source': object()}
    from task_env.runtime.sessions import mujoco_physical
    def reject_in_preflight(*args):
        raise ValueError('source capability rejected')
    monkeypatch.setattr(mujoco_physical, 'preflight_physical_mujoco', reject_in_preflight)
    with pytest.raises(ValueError, match='source capability rejected'):
        env._prepare_reference_reset()
    assert env.session is previous
