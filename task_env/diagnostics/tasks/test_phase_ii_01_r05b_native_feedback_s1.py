"""Provider-free S1 checks for the bounded R05b normal feedback profile."""
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.artifacts import ExecutionSpec
from task_env.runtime.boundary import GeoPhysRuntimeBoundary
from task_env.runtime.sessions import api
from task_env.runtime.sessions.api import (
    _diagnostic_manifest,
    _r05b_native_feedback_manifest,
    provider_manifest,
)
from task_env.runtime.sessions.geophys_source import GeoPhysSourceComposer
from task_env.tasks.nut_assembly.task import (
    NutAssemblyReferenceEnv,
    R05B_NATIVE_FEEDBACK_PROFILE,
    build_native_feedback_reference,
)


def _execution(backend='cpu'):
    return ExecutionSpec('geophys', 'p1_2_scalar_cpu_v0', 'none', backend, 0, 'strict')


@pytest.mark.parametrize('backend', ['cpu', 'cuda'])
def test_public_r05b_profile_builds_and_passes_real_source_admission(backend):
    env = NutAssemblyReferenceEnv.for_native_feedback_profile(
        backend=backend, gripper_control_hz=500,
    )
    value = env.value
    source = value['source']
    receipt = source.execution_source_receipt
    try:
        assert env._native_feedback_profile == R05B_NATIVE_FEEDBACK_PROFILE
        assert env._diagnostic_profile is None
        assert value['artifact'].identity_hash == '99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe'
        assert hashlib.sha256(source.scene_source.xml.encode()).hexdigest() == (
            '909759def6bbaa4c5644a100a36625400464cd571dcab1222f807efaaf1c225d'
        )
        assert receipt.canonical_xml_sha256 == hashlib.sha256(source.scene_source.xml.encode()).hexdigest()
        assert receipt.validate_snapshot() is None
        assert source.source_closure_digest is None  # Frozen v0 ABI remains unchanged.
        assert tuple(source.open_actuators) == ('actuator8',)
        assert dict(source.joint_targets) == {
            f'panda-v1/joint{index}': f'actuator{index}' for index in range(1, 8)
        }
        manifest = _r05b_native_feedback_manifest(
            value['artifact'], _execution(backend), source, R05B_NATIVE_FEEDBACK_PROFILE,
        )
        assert manifest.backend == backend
        assert manifest.adapter_version == 'task-env-r05b-geophys-native-feedback-v1'
        assert any(claim.name == 'actuator_force_query' for claim in manifest.capabilities)
        assert provider_manifest('geophys').backend == 'cpu'
        assert not any(claim.name == 'actuator_force_query'
                       for claim in provider_manifest('geophys').capabilities)
    finally:
        env.close()


def test_current_provider_build_is_rejected_by_historical_c05c_allowlist():
    value = build_native_feedback_reference(backend='cuda', gripper_control_hz=500)
    try:
        with pytest.raises(ValueError, match='fixed GeoPhys a53a8cf'):
            _diagnostic_manifest(
                value['artifact'], _execution('cuda'), value['source'],
                'nutassembly-gripper-cadence-v1',
            )
    finally:
        value['source'].execution_source_receipt.close()


def test_r05b_admission_rejects_source_mapping_backend_and_dirty_build(monkeypatch):
    value = build_native_feedback_reference(backend='cpu', gripper_control_hz=500)
    source = value['source']
    receipt = source.execution_source_receipt
    try:
        with pytest.raises(ValueError, match='actuator mapping'):
            altered = replace(source, open_actuators=('actuator7',))
            _r05b_native_feedback_manifest(
                value['artifact'], _execution(), altered, R05B_NATIVE_FEEDBACK_PROFILE,
            )
        with pytest.raises(ValueError, match='CPU/CUDA'):
            _r05b_native_feedback_manifest(
                value['artifact'], replace(_execution(), backend='mujoco'), source,
                R05B_NATIVE_FEEDBACK_PROFILE,
            )
        with pytest.raises(ValueError, match='exact allowlist'):
            wrong_integrator = replace(
                source,
                config=replace(source.config,
                               runtime=replace(source.config.runtime, integrator='Euler')),
            )
            _r05b_native_feedback_manifest(
                value['artifact'], _execution(), wrong_integrator,
                R05B_NATIVE_FEEDBACK_PROFILE,
            )
        with pytest.raises(ValueError, match='clean committed GeoPhys build'):
            actual = api.provider_build_identity('geophys')
            monkeypatch.setattr(api, 'provider_build_identity', lambda _provider: {
                **actual, 'dirty_build_sha256': '0' * 64,
            })
            _r05b_native_feedback_manifest(
                value['artifact'], _execution(), source, R05B_NATIVE_FEEDBACK_PROFILE,
            )
    finally:
        receipt.close()


def test_execution_source_receipt_detects_snapshot_tampering():
    value = build_native_feedback_reference(backend='cpu', gripper_control_hz=500)
    receipt = value['source'].execution_source_receipt
    try:
        path = receipt.snapshot_root / 'scene.xml'
        path.chmod(0o644)
        path.write_bytes(path.read_bytes() + b' ')
        with pytest.raises(ValueError, match='snapshot bytes changed'):
            receipt.validate_snapshot()
    finally:
        receipt.close()


def test_source_composer_points_to_receipt_snapshot_and_checks_importer_dependencies(monkeypatch):
    value = build_native_feedback_reference(backend='cpu', gripper_control_hz=500)
    source = value['source']
    receipt = source.execution_source_receipt
    captured = {}

    class SceneSource:
        @staticmethod
        def mjcf_string(xml, *, base_dir, label):
            captured.update(xml=xml, base_dir=Path(base_dir), label=label)
            return SimpleNamespace(xml=xml, base_dir=Path(base_dir), label=label)

    monkeypatch.setitem(sys.modules, 'scene', SimpleNamespace(SceneSource=SceneSource))
    try:
        composer = GeoPhysSourceComposer(
            source.scene_source, execution_source_receipt=receipt,
        )
        scene_source, adapter = composer.build_scene_source(None, None)
        assert adapter == 'task_env_execution_source_receipt_v1'
        assert scene_source.base_dir == receipt.snapshot_root
        assert scene_source.xml.encode() == receipt.importer_xml
        dependencies = tuple(
            receipt.snapshot_root / path for path in receipt.closure_files
            if path.startswith('assets/')
        )
        imported = SimpleNamespace(
            dependency_paths=dependencies,
            build_rigid_scene_model=lambda *, use_imported_meshes: {
                'use_imported_meshes': use_imported_meshes,
            },
        )
        assert composer.build_scene_model(imported, None) == {'use_imported_meshes': True}
        invalid = SimpleNamespace(
            dependency_paths=(Path('/tmp/outside-r05b-source.bin'),),
            build_rigid_scene_model=lambda **_: None,
        )
        with pytest.raises(ValueError, match='dependencies differ'):
            composer.build_scene_model(invalid, None)
    finally:
        receipt.close()


def test_core_boundary_uses_public_setter_and_skips_same_effective_cap():
    calls = []

    class Physics:
        n_actuators = 8

        def set_actuator_force_limits(self, ids, lower, upper):
            calls.append((tuple(ids.tolist()), tuple(lower.tolist()), tuple(upper.tolist())))

    boundary = object.__new__(GeoPhysRuntimeBoundary)
    boundary._physics = Physics()
    boundary._actuator_force_limit_overrides = {}
    boundary.set_actuator_force_limits((7,), 10.0)
    boundary.set_actuator_force_limits(np.asarray([7], dtype=np.int64), 10.0000001)
    assert len(calls) == 1
    assert calls[0] == ((7,), (-10.0,), (10.0,))
    boundary.set_actuator_force_limits((7,), 11.0)
    assert len(calls) == 2
    boundary._apply_actuator_force_limit_overrides()  # reset/restore always reapplies persistent overrides
    assert len(calls) == 3
    with pytest.raises(TypeError, match='integer sequence'):
        boundary.set_actuator_force_limits((7.9,), 12.0)
    with pytest.raises(ValueError, match='unique'):
        boundary.set_actuator_force_limits((7, 7), 12.0)
    with pytest.raises(TypeError, match='real numeric scalar'):
        boundary.set_actuator_force_limits((7,), True)
    with pytest.raises(ValueError, match='finite and non-negative'):
        boundary.set_actuator_force_limits((7,), float('nan'))
    boundary.set_actuator_force_limits((), 12.0)
    assert len(calls) == 3
