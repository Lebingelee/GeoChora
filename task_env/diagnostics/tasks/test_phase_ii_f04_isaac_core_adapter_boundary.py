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


def test_isaac_app_task_thread_count_obeys_f04_resource_bound():
    from task_env.runtime.sessions.isaac_native_io import _validate_isaac_task_thread_count

    assert _validate_isaac_task_thread_count(1) == 1
    assert _validate_isaac_task_thread_count(4) == 4
    for invalid in (0, 5):
        with pytest.raises(RuntimeError, match='1-4 thread bound'):
            _validate_isaac_task_thread_count(invalid)


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
