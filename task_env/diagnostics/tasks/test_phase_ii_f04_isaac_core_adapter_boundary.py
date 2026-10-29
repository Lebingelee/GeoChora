"""Provider-free F04 boundary checks; never starts Kit or Isaac physics."""
from __future__ import annotations

from dataclasses import replace

import pytest

from task_env.runtime.sessions.api import materialize
from task_env.tasks.reference_env import SelectedReferenceEnv
from task_env.tasks.position_candidate.builder import F04PositionCandidateInputV1
from task_env.diagnostics.tasks.test_phase_ii_f03_attempt002_core_call_chain import (
    _versioned_input,
)


def test_f04_input_rejects_unverified_synthetic_delivery_before_provider_import(tmp_path):
    f03 = _versioned_input(tmp_path)
    execution = replace(
        f03.execution,
        physics_profile='isaac-gpu-physx-f04-position-v1',
    )
    f04 = F04PositionCandidateInputV1(
        'f04-position-candidate-input-v1', f03.task_source, f03.artifact,
        f03.runtime_source, execution, f03.reset_plan,
        f03.kinematics_source_xml, f03.kinematics_source_sha256,
    )
    with pytest.raises(ValueError, match='synthetic or unverified'):
        f04.validate()


def test_production_materialize_keeps_synthetic_usd_fail_closed(tmp_path):
    f03 = _versioned_input(tmp_path)
    execution = replace(
        f03.execution,
        physics_profile='isaac-gpu-physx-f04-position-v1',
    )
    with pytest.raises(ValueError, match='synthetic or unverified'):
        materialize(f03.artifact, execution, source=f03.runtime_source)


def test_environment_close_closes_session_then_process_runtime_owner_once():
    class Session:
        def __init__(self):
            self.calls = []

        def close(self):
            self.calls.append('session')

        def close_runtime_owner(self):
            self.calls.append('runtime_owner')

    env = object.__new__(SelectedReferenceEnv)
    env._closed = False
    env._stopped = False
    env.position_profile = True
    env._published_position_state = None
    env._camera_consumer = None
    env.session = Session()
    session = env.session

    env.close()
    env.close()

    assert session.calls == ['session', 'runtime_owner']
    assert env.session is None
    assert env._closed is True


def test_native_adapter_path_binding_accepts_explicit_composite_scene_paths():
    from task_env.runtime.sessions.isaac_native_io import _native_prim_path

    assert _native_prim_path('/World/task/floating_object', '/panda') == '/World/task/floating_object'
    assert _native_prim_path('panda_hand', '/panda') == '/panda/panda_hand'
    with pytest.raises(ValueError, match='not canonical'):
        _native_prim_path('/World/../escape', '/panda')


def test_native_adapter_read_views_preserves_public_local_com_and_com_twist():
    from types import SimpleNamespace

    from task_env.artifacts import FrameReference
    from task_env.runtime.sessions.free_joint_state import world_com_twist_to_body_origin_local
    from task_env.runtime.sessions.isaac_native_io import IsaacSimNativeRuntimeIOV1

    class Tensor:
        def __init__(self, value):
            self.value = value

        def numpy(self):
            import numpy as np
            return np.asarray(self.value)

    class PublicRigidPrim:
        def get_world_poses(self):
            return Tensor([[1.0, 2.0, 3.0]]), Tensor([[2 ** -0.5, 0.0, 0.0, 2 ** -0.5]])

        def get_velocities(self):
            return Tensor([[0.4, 0.7, 0.6]]), Tensor([[0.0, 0.0, 2.0]])

        def get_coms(self):
            # Isaac 6.2 Tensor RigidBodyView contract: relative to rigid-body prim.
            return Tensor([[0.1, 0.02, -0.03]]), Tensor([[1.0, 0.0, 0.0, 0.0]])

    adapter = object.__new__(IsaacSimNativeRuntimeIOV1)
    adapter._articulation = SimpleNamespace(
        get_dof_positions=lambda: Tensor([[]]),
        get_dof_velocities=lambda: Tensor([[]]),
    )
    adapter._dof_names = ()
    adapter._dof_index = {}
    adapter._source = SimpleNamespace(
        joints={}, frames={}, free_joints={"cube": "cube-root"},
    )
    adapter._frame_views = {}
    adapter._free_views = {"cube": PublicRigidPrim()}
    body_frame = FrameReference("cube", "body")
    adapter._artifact = SimpleNamespace(legacy_frame_bindings={"cube": body_frame})

    joints, velocities, frames, free = adapter._read_views()
    assert joints == velocities == frames == {}
    readback = free["cube"]
    readback.validate()
    assert readback.position_world_m == (1.0, 2.0, 3.0)
    assert readback.orientation_world_from_body_wxyz == pytest.approx((2 ** -0.5, 0.0, 0.0, 2 ** -0.5))
    assert readback.com_offset_body_m == pytest.approx((0.1, 0.02, -0.03), abs=1e-12)
    assert readback.linear_velocity_world_at_com_m_s == (0.4, 0.7, 0.6)
    assert readback.angular_velocity_world_rad_s == (0.0, 0.0, 2.0)
    linear_local, angular_local = world_com_twist_to_body_origin_local(
        position_world_m=readback.position_world_m,
        orientation_world_from_body_wxyz=readback.orientation_world_from_body_wxyz,
        com_offset_body_m=readback.com_offset_body_m,
        linear_velocity_world_at_com_m_s=readback.linear_velocity_world_at_com_m_s,
        angular_velocity_world_rad_s=readback.angular_velocity_world_rad_s,
        velocity_frame=readback.velocity_frame,
        linear_reference_point=readback.linear_reference_point,
    )
    assert linear_local == pytest.approx((0.74, -0.6, 0.6), abs=1e-12)
    assert angular_local == pytest.approx((0.0, 0.0, 2.0), abs=1e-12)


def test_isaac_app_task_thread_count_obeys_f04_resource_bound():
    from task_env.runtime.sessions.isaac_native_io import _validate_isaac_task_thread_count

    assert _validate_isaac_task_thread_count(1) == 1
    assert _validate_isaac_task_thread_count(4) == 4
    for invalid in (0, 5):
        with pytest.raises(RuntimeError, match='1-4 thread bound'):
            _validate_isaac_task_thread_count(invalid)


def test_isaac_app_owner_process_hold_defers_close_until_all_core_env_leases_finish():
    from task_env.runtime.sessions.isaac_native_io import IsaacSimAppOwnerV1

    class _AppCloseProbe:
        def __init__(self):
            self.close_count = 0

        def close(self):
            self.close_count += 1

    owner = IsaacSimAppOwnerV1()
    app = _AppCloseProbe()
    owner._app = app
    owner.retain_process_lifetime()
    owner.close()
    assert owner.open() is app
    owner.close()

    assert owner._closed is False
    assert owner._close_requested is True
    assert owner.close_attempts == 0
    assert app.close_count == 0

    owner.release_process_lifetime()
    owner.close()
    assert owner._closed is True
    assert owner.close_attempts == 1
    assert owner.close_receipt() == {
        "close_attempted": True, "close_completed": True,
        "close_failure": None, "closed": True, "close_attempts": 1,
        "framework_unload_attempted": False,
        "framework_unload_completed": False,
        "framework_unload_failure": None,
        "atexit_close_unregister_attempted": False,
        "atexit_close_unregister_completed": False,
        "atexit_close_unregister_failure": None,
    }
    assert app.close_count == 1


def test_isaac_app_owner_close_failure_is_retained_and_never_retried():
    from task_env.runtime.sessions.isaac_native_io import IsaacSimAppOwnerV1

    class _FailingApp:
        def __init__(self):
            self.close_count = 0

        def close(self):
            self.close_count += 1
            raise RuntimeError("close sentinel")

    owner = IsaacSimAppOwnerV1()
    app = _FailingApp()
    owner._app = app
    with pytest.raises(RuntimeError, match="close sentinel"):
        owner.close()
    owner.close()

    assert app.close_count == 1
    assert owner._closed is False
    assert owner.close_receipt() == {
        "close_attempted": True, "close_completed": False,
        "close_failure": {"type": "RuntimeError", "message": "close sentinel"},
        "closed": False, "close_attempts": 1,
        "framework_unload_attempted": False,
        "framework_unload_completed": False,
        "framework_unload_failure": None,
        "atexit_close_unregister_attempted": False,
        "atexit_close_unregister_completed": False,
        "atexit_close_unregister_failure": None,
    }


def test_isaac_app_owner_uses_public_close_and_retains_wrapper_until_worker_exit(monkeypatch):
    import importlib.metadata
    import sys
    from types import ModuleType, SimpleNamespace

    from task_env.runtime.sessions.isaac_native_io import IsaacSimAppOwnerV1

    import atexit

    app_calls = []
    lifecycle_events = []

    class _FakeSimulationApp:
        def __init__(self, config):
            app_calls.append(dict(config))

        def close(self):
            lifecycle_events.append("app_close")

        def _atexit_close(self):
            lifecycle_events.append("atexit_close")

        def __del__(self):
            lifecycle_events.append("app_wrapper_finalize")

    monkeypatch.setattr(atexit, "unregister", lambda _callback: pytest.fail(
        "Core App close must not manage SimulationApp's private atexit callback"
    ))

    simulation_app_module = ModuleType("isaacsim.simulation_app")
    simulation_app_module.SimulationApp = _FakeSimulationApp
    carb_module = ModuleType("carb")
    carb_module.get_framework = lambda: pytest.fail(
        "the Core App owner must leave framework/plugin unload to process exit"
    )
    carb_module.settings = SimpleNamespace(get_settings=lambda: SimpleNamespace(
        get_as_int=lambda _name: 4,
    ))
    isaacsim_module = ModuleType("isaacsim")
    isaacsim_module.__path__ = []
    monkeypatch.setitem(sys.modules, "isaacsim", isaacsim_module)
    monkeypatch.setitem(sys.modules, "isaacsim.simulation_app", simulation_app_module)
    monkeypatch.setitem(sys.modules, "carb", carb_module)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "6.2.0.0")

    owner = IsaacSimAppOwnerV1()
    app = owner.open()
    owner.close()

    assert app_calls == [{
        "headless": True, "enable_cameras": False, "limit_cpu_threads": 4,
        "fast_shutdown": False,
    }]
    assert lifecycle_events == ["app_close"]
    assert owner.app is app
    assert owner.close_receipt() == {
        "close_attempted": True, "close_completed": True,
        "close_failure": None, "closed": True, "close_attempts": 1,
        "framework_unload_attempted": False,
        "framework_unload_completed": False,
        "framework_unload_failure": None,
        "atexit_close_unregister_attempted": False,
        "atexit_close_unregister_completed": False,
        "atexit_close_unregister_failure": None,
    }


def test_isaac_app_owner_close_does_not_drop_closed_app_reference():
    from task_env.runtime.sessions.isaac_native_io import IsaacSimAppOwnerV1

    class _App:
        def __init__(self):
            self.close_count = 0

        def close(self):
            self.close_count += 1

    owner = IsaacSimAppOwnerV1()
    app = _App()
    owner._app = app
    owner.close()

    assert owner.app is app
    assert app.close_count == 1
    assert owner._closed and owner._close_completed
    assert owner.close_receipt() == {
        "close_attempted": True, "close_completed": True,
        "close_failure": None,
        "closed": True, "close_attempts": 1,
        "framework_unload_attempted": False,
        "framework_unload_completed": False,
        "framework_unload_failure": None,
        "atexit_close_unregister_attempted": False,
        "atexit_close_unregister_completed": False,
        "atexit_close_unregister_failure": None,
    }


def test_f04_attempt004_budget_has_no_app_start_cap_and_matches_frozen_window():
    import importlib.util
    import json
    import os
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    evidence_root = os.environ.get("F04_EVIDENCE_ROOT")
    if not evidence_root:
        pytest.skip("run this attempt-specific budget test under the frozen F04 evidence runner")
    runner_path = Path(evidence_root) / "run_f04_native.py"
    budget_path = (repo / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001"
                   / "sol_f04_004/execution_budget.json")
    budget = json.loads(budget_path.read_text())
    spec = importlib.util.spec_from_file_location("f04_attempt004_native_runner", runner_path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert runner.BUDGET == budget

    # App starts are uncapped, but both cumulative limits come from the package.
    order = ["official-panda", "menagerie-panda"]
    assert runner._allowed_next_families("both", False, order) == {"both"}
    assert runner._allowed_next_families("both", True, order) == {"both"}
    assert runner._allowed_next_families("official-panda", False, order) == {
        "official-panda", "both",
    }
    assert runner._allowed_next_families("official-panda", True, order) == {
        "menagerie-panda", "both",
    }
    launches = [
        {"app_start_number": index, "worker_wall_seconds": 10.0,
         "physics_steps_observed": 500}
        for index in range(1, 7)
    ]
    prior_wall, prior_steps = runner._attempt_budget(launches)
    assert (prior_wall, prior_steps) == (60.0, 3000)
    assert runner._worker_budget_violations(prior_wall, prior_steps, 900.0, 3000, 6.0) == []
    assert "per_worker_wall_seconds" in runner._worker_budget_violations(
        prior_wall, prior_steps, 900.001, 1, 0.002,
    )
    assert "per_worker_physics_steps_including_bootstrap" in runner._worker_budget_violations(
        prior_wall, prior_steps, 1.0, 3001, 6.002,
    )
    assert "per_attempt_worker_wall_seconds" in runner._worker_budget_violations(
        1700.0, 3000, 101.0, 1, 0.002,
    )
    assert "per_attempt_physics_steps_including_bootstrap" in runner._worker_budget_violations(
        80.0, 5500, 1.0, 501, 0.002,
    )
    assert "per_attempt_simulation_time_seconds" in runner._worker_budget_violations(
        0.0, 5501, 1.0, 500, 1.0,
    )


def test_isaac_native_reset_refreshes_public_kinematics_before_read_without_step():
    from types import SimpleNamespace

    import numpy as np

    from task_env.diagnostics.tasks.f04_candidate_s1_support import _native_order, build_candidate
    from task_env.runtime.sessions.isaac_native_io import IsaacSimNativeRuntimeIOV1

    candidate = build_candidate("official-panda")
    source = candidate.runtime_source
    sample = candidate.reset_plan.reset_sample
    # The production adapter's metadata order is the native binding order, not
    # a guessed canonical order. Both are pinned explicitly in this fake.
    dof_names = _native_order(source)
    semantic_by_native = {native: semantic for semantic, native in source.joint_targets.items()}
    positions = [0.0] * len(dof_names)
    events = []
    fresh = {"value": False}

    class Tensor:
        def __init__(self, value):
            self.value = np.asarray(value, dtype=np.float64)

        def numpy(self):
            return self.value

    class Articulation:
        def set_dof_positions(self, values):
            events.append("set_dof_positions")
            positions[:] = values

        def set_dof_velocities(self, values):
            events.append("set_dof_velocities")

        def set_dof_position_targets(self, values):
            events.append("set_dof_position_targets")

        def get_dof_positions(self):
            return Tensor([positions])

        def get_dof_velocities(self):
            return Tensor([[0.0] * len(positions)])

    class FreeView:
        def __init__(self):
            self.position = (0.0, 0.0, 0.0)
            self.quaternion = (1.0, 0.0, 0.0, 0.0)

        def set_world_poses(self, *, positions, orientations):
            events.append("set_free_pose")
            self.position = tuple(positions)
            self.quaternion = tuple(orientations)

        def set_velocities(self, *, linear_velocities, angular_velocities):
            events.append("set_free_velocity")

        def get_world_poses(self):
            return Tensor([self.position]), Tensor([self.quaternion])

        def get_velocities(self):
            return Tensor([[0.0, 0.0, 0.0]]), Tensor([[0.0, 0.0, 0.0]])

        def get_coms(self):
            return Tensor([[0.0, 0.0, 0.0]]), Tensor([[1.0, 0.0, 0.0, 0.0]])

    class FrameView:
        def get_world_poses(self):
            if not fresh["value"]:
                return Tensor([[9.0, 9.0, 9.0]]), Tensor([[1.0, 0.0, 0.0, 0.0]])
            # The reset kinematic refresh publishes a new Frame derived from
            # the DOF values written through the articulation public API.
            return Tensor([[0.45, 0.0, 0.5]]), Tensor([[1.0, 0.0, 0.0, 0.0]])

    class SimulationView:
        def update_articulations_kinematic(self):
            events.append("update_articulations_kinematic")
            fresh["value"] = True
            return True

    class Torch:
        class cuda:
            @staticmethod
            def synchronize(_device):
                events.append("cuda_sync")

    manager = SimpleNamespace(
        get_num_physics_steps=lambda: 17,
        get_simulation_time=lambda: 17 * 0.002,
        get_physics_simulation_view=lambda: SimulationView(),
    )
    adapter = object.__new__(IsaacSimNativeRuntimeIOV1)
    adapter._closed = False
    adapter._source = source
    adapter._artifact = candidate.artifact
    adapter._dof_names = dof_names
    adapter._dof_index = {name: index for index, name in enumerate(dof_names)}
    adapter._articulation = Articulation()
    adapter._manager = manager
    adapter._torch = Torch()
    free_view = FreeView()
    adapter._free_views = {name: free_view for name in source.free_joints}
    adapter._body_views = {name: free_view for name in source.bodies.values()}
    # Production creates body-backed frame views from RuntimeSource.bodies;
    # this official candidate has no extra Xform-only RuntimeSource.frames.
    adapter._frame_views = {name: FrameView() for name in source.bodies}

    targets = tuple(
        (index, native_name, float(sample.joint_position[semantic_by_native[native_name]]))
        for index, native_name in enumerate(dof_names)
    )
    adapter.write_reset(sample, targets)
    state = adapter.read_state()

    assert events.index("set_dof_positions") < events.index("update_articulations_kinematic")
    assert events.index("set_free_velocity") < events.index("update_articulations_kinematic")
    refresh_index = events.index("update_articulations_kinematic")
    assert any(index > refresh_index and event == "cuda_sync"
               for index, event in enumerate(events))
    assert state.frame_pose_world["panda-main/hand"].position == (0.45, 0.0, 0.5)
    assert adapter._episode_origin_step == 17
    assert adapter._episode_origin_time == pytest.approx(17 * 0.002)
    assert adapter._last_reset_refresh_receipt["physics_advanced"] is False
    assert events.count("update_articulations_kinematic") == 1


@pytest.mark.parametrize("refresh_behavior", ("missing", "raises", "steps"))
def test_isaac_native_reset_rejects_missing_failed_or_stepping_kinematic_refresh(refresh_behavior):
    from types import SimpleNamespace

    from task_env.diagnostics.tasks.f04_candidate_s1_support import _native_order, build_candidate
    from task_env.runtime.sessions.isaac_native_io import IsaacSimNativeRuntimeIOV1

    candidate = build_candidate("official-panda")
    source = candidate.runtime_source
    sample = candidate.reset_plan.reset_sample
    dof_names = _native_order(source)
    semantic_by_native = {native: semantic for semantic, native in source.joint_targets.items()}
    counter = {"steps": 7, "time": 0.014}

    class Tensor:
        def numpy(self):
            import numpy as np
            return np.zeros((1, 9))

    class Articulation:
        def set_dof_positions(self, _values): pass
        def set_dof_velocities(self, _values): pass
        def set_dof_position_targets(self, _values): pass

    class FreeView:
        def set_world_poses(self, **_kwargs): pass
        def set_velocities(self, **_kwargs): pass

    class SimulationView:
        def update_articulations_kinematic(self):
            if refresh_behavior == "raises":
                raise RuntimeError("refresh sentinel")
            if refresh_behavior == "steps":
                counter["steps"] += 1
                counter["time"] += 0.002
            return True

    class Torch:
        class cuda:
            @staticmethod
            def synchronize(_device): pass

    view = object() if refresh_behavior == "missing" else SimulationView()
    adapter = object.__new__(IsaacSimNativeRuntimeIOV1)
    adapter._closed = False
    adapter._source = source
    adapter._artifact = candidate.artifact
    adapter._dof_names = dof_names
    adapter._dof_index = {name: index for index, name in enumerate(dof_names)}
    adapter._articulation = Articulation()
    adapter._manager = SimpleNamespace(
        get_num_physics_steps=lambda: counter["steps"],
        get_simulation_time=lambda: counter["time"],
        get_physics_simulation_view=lambda: view,
    )
    adapter._torch = Torch()
    adapter._free_views = {name: FreeView() for name in source.free_joints}

    targets = tuple(
        (index, native_name, float(sample.joint_position[semantic_by_native[native_name]]))
        for index, native_name in enumerate(dof_names)
    )
    expected = {
        "missing": "lacks articulation kinematic refresh",
        "raises": "refresh sentinel",
        "steps": "advanced physics or changed time",
    }[refresh_behavior]
    with pytest.raises(RuntimeError, match=expected):
        adapter.write_reset(sample, targets)


def test_f04_menagerie_source_identity_uses_existing_asset_reference_and_frozen_gitlink():
    from types import SimpleNamespace
    from task_env.runtime.sessions.api import _validate_f04_source_family

    revision = 'b846dd12bc459d776cccb3dee0b1d02acbf7a9c7'
    definition = SimpleNamespace(
        source_reference='mujoco-menagerie://franka_emika_panda/panda.xml',
        source_revision=revision,
    )
    delivery = SimpleNamespace(
        asset_definition=definition, source_revision=revision, variant_selections={},
    )
    _validate_f04_source_family(delivery)

    changed = SimpleNamespace(
        asset_definition=definition, source_revision='b846dd12', variant_selections={},
    )
    with pytest.raises(ValueError, match='current frozen provider Gitlink'):
        _validate_f04_source_family(changed)


def test_f04_official_source_requires_exact_f01_variants():
    from types import SimpleNamespace
    from task_env.runtime.sessions.api import (
        _F04_OFFICIAL_PANDA_SOURCE_REFERENCE,
        _validate_f04_source_family,
    )

    definition = SimpleNamespace(
        source_reference=_F04_OFFICIAL_PANDA_SOURCE_REFERENCE,
        source_revision='official-s3-snapshot-2026-10-07',
    )
    variants = {
        '/panda#Gripper': 'alternatefinger',
        '/panda#Mesh': 'performance',
        '/panda#Physics': 'physx',
    }
    _validate_f04_source_family(SimpleNamespace(
        asset_definition=definition, source_revision=definition.source_revision,
        variant_selections=variants,
    ))
    with pytest.raises(ValueError, match='exact F01'):
        _validate_f04_source_family(SimpleNamespace(
            asset_definition=definition, source_revision=definition.source_revision,
            variant_selections={**variants, '/panda#Gripper': 'default'},
        ))


def test_f04_source_family_rejects_unreviewed_reference():
    from types import SimpleNamespace
    from task_env.runtime.sessions.api import _validate_f04_source_family

    definition = SimpleNamespace(source_reference='file:///tmp/panda.usd', source_revision='local')
    delivery = SimpleNamespace(asset_definition=definition, source_revision='local', variant_selections={})
    with pytest.raises(ValueError, match='two frozen Panda source families'):
        _validate_f04_source_family(delivery)


@pytest.mark.parametrize(('failure', 'expected_status', 'close_completed'), (
    ('none', 'worker-complete', True),
    ('app_open', 'worker-failed', True),
    ('family_step', 'worker-failed', True),
    ('app_close', 'worker-failed', False),
))
def test_f04_attempt004_both_worker_preserves_primary_and_finalizes_after_app_close(
        tmp_path, failure, expected_status, close_completed):
    """Exercise the combined A/B worker finalizer without importing Kit or stepping physics."""
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[3]
    evidence_root = os.environ.get('F04_EVIDENCE_ROOT')
    if not evidence_root:
        pytest.skip('run this attempt-specific lifecycle test under the frozen F04 evidence runner')
    helper = Path(evidence_root) / 'f04_combined_worker_lifecycle_s1.py'
    child_root = tmp_path / 'child'
    child_root.mkdir()
    child_env = os.environ.copy()
    child_env['PYTHONPATH'] = os.pathsep.join((str(repo), str(helper.parent)))
    child_env['PYTHONDONTWRITEBYTECODE'] = '1'
    child = subprocess.run(
        [sys.executable, str(helper), '--failure', failure, '--root', str(child_root)],
        cwd=repo, env=child_env, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, timeout=60, check=False,
    )
    assert child.returncode == 0, f'isolated worker lifecycle failed: {child.stdout}\n{child.stderr}'
    result = json.loads(child.stdout)
    receipt = result['receipt']
    assert receipt['status'] == expected_status
    assert receipt['producer_aggregate_written_after_app_close'] is close_completed
    assert receipt['app_owner']['close_attempted'] is True
    assert receipt['app_owner']['close_completed'] is close_completed
    assert result['events'][-2:] == ['close', 'aggregate']
    if failure == 'none':
        assert (result['events'].index('family:official-panda')
                < result['events'].index('family:menagerie-panda')
                < result['events'].index('close'))
        assert receipt['worker_error'] is None and receipt['cleanup_error'] is None
    elif failure == 'family_step':
        assert receipt['worker_error']['message'] == 'primary family step failure'
        assert receipt['cleanup_error'] is None and receipt['app_owner']['close_completed'] is True
    elif failure == 'app_open':
        assert receipt['worker_error']['message'] == 'primary App open failure'
        assert receipt['cleanup_error'] is None and receipt['app_owner']['close_completed'] is True
    else:
        assert receipt['worker_error'] is None
        assert receipt['cleanup_error']['message'] == 'primary App close failure'


def test_f04_attempt004_terminal_worker_parent_observes_exit_after_durable_cleanup(tmp_path):
    """Exercise the production outer worker exit in children and observe real status in parent."""
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys

    evidence_root = os.environ.get('F04_EVIDENCE_ROOT')
    s1_output = os.environ.get('F04_S1_OUTPUT')
    if not evidence_root or not s1_output:
        pytest.skip('run this attempt-specific terminal worker test under the frozen F04 evidence runner')
    harness = Path(evidence_root) / 'f04_terminal_worker_s1.py'
    result_root = Path(s1_output) / 'terminal-worker-parent-observation'
    child = subprocess.run(
        [sys.executable, '-B', str(harness), '--root', str(result_root)],
        cwd=Path(__file__).resolve().parents[3], env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180, check=False,
    )
    assert child.returncode == 0, f'terminal worker S1 failed: {child.stdout}\n{child.stderr}'
    result_path = result_root / 'terminal_worker_s1_result.json'
    result = json.loads(result_path.read_text())
    assert result['status'] == 'PASS'
    assert result['parent_survived_all_children'] is True
    assert {row['scenario'] for row in result['scenarios']} == {
        'success', 'family_failure', 'app_close_failure', 'finalize_failure', 'receipt_write_failure',
    }
    assert all(row['parent_survived'] and not row['atexit_finalizer_ran']
               for row in result['scenarios'])
