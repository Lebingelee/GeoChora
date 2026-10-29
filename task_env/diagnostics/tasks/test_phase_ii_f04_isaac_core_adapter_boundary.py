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
    assert app.close_count == 1


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
