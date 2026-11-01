"""Provider-free S1 checks for the bounded R05b normal feedback profile."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import h5py
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
from task_env.runtime.sessions.common import _SessionValues
from task_env.diagnostics.tasks import r05b_native_feedback_independent_reader as raw_reader
from task_env.diagnostics.tasks import r05b_native_feedback_s2_worker as worker
from task_env.diagnostics.tasks import r05b_native_feedback_supervisor as supervisor
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
        assert value['resolved_configuration']['native_feedback_profile'] == R05B_NATIVE_FEEDBACK_PROFILE
        assert value['resolved_configuration']['gripper_control_hz'] == 500
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
        with pytest.raises(ValueError, match='fixed GeoPhys a53a8cf repair baseline'):
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
        wrong_joints = dict(source.joints)
        wrong_joints['panda-v1/joint1'] = 'joint2'
        with pytest.raises(ValueError, match='semantic and actuator mappings'):
            _r05b_native_feedback_manifest(
                value['artifact'], _execution(), replace(source, joints=wrong_joints),
                R05B_NATIVE_FEEDBACK_PROFILE,
            )
        wrong_bodies = dict(source.bodies)
        wrong_bodies['square-peg-v1'] = 'peg2'
        with pytest.raises(ValueError, match='semantic and actuator mappings'):
            _r05b_native_feedback_manifest(
                value['artifact'], _execution(), replace(source, bodies=wrong_bodies),
                R05B_NATIVE_FEEDBACK_PROFILE,
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


def test_r05b_admission_rejects_rehashed_asset_and_importer_receipts():
    from task_env.runtime.sessions.source import ExecutionSourceReceiptV1

    value = build_native_feedback_reference(backend='cpu', gripper_control_hz=500)
    source = value['source']
    original = source.execution_source_receipt
    try:
        changed = dict(original.closure_files)
        changed['assets/link0.stl'] += b' rehashed-but-untrusted'
        forged_asset = ExecutionSourceReceiptV1.create(
            source_id=original.source_id,
            canonical_xml=changed['canonical-source.xml'],
            importer_xml=original.importer_xml,
            closure_files={name: data for name, data in changed.items() if name != 'scene.xml'},
        )
        try:
            with pytest.raises(ValueError, match='trusted full source closure'):
                _r05b_native_feedback_manifest(
                    value['artifact'], _execution(),
                    replace(source, execution_source_receipt=forged_asset),
                    R05B_NATIVE_FEEDBACK_PROFILE,
                )
        finally:
            forged_asset.close()

        forged_importer = ExecutionSourceReceiptV1.create(
            source_id=original.source_id,
            canonical_xml=original.closure_files['canonical-source.xml'],
            importer_xml=original.importer_xml + b' ',
            closure_files={name: data for name, data in original.closure_files.items()
                           if name != 'scene.xml'},
        )
        try:
            with pytest.raises(ValueError, match='trusted full source closure|canonical-to-importer'):
                _r05b_native_feedback_manifest(
                    value['artifact'], _execution(),
                    replace(source, execution_source_receipt=forged_importer),
                    R05B_NATIVE_FEEDBACK_PROFILE,
                )
        finally:
            forged_importer.close()

        changed_canonical = original.closure_files['canonical-source.xml'] + b' '
        changed_importer = original.importer_xml + b' '
        forged_canonical = ExecutionSourceReceiptV1.create(
            source_id=original.source_id,
            canonical_xml=changed_canonical,
            importer_xml=changed_importer,
            closure_files={
                **{name: data for name, data in original.closure_files.items()
                   if name not in {'scene.xml', 'canonical-source.xml'}},
                'canonical-source.xml': changed_canonical,
            },
        )
        try:
            altered_scene_source = replace(
                source.scene_source, xml=changed_canonical.decode('utf-8'),
                base_dir=forged_canonical.snapshot_root,
            )
            altered_source = replace(
                source, scene_source=altered_scene_source,
                execution_source_receipt=forged_canonical,
            )
            with pytest.raises(ValueError, match='trusted full source closure'):
                _r05b_native_feedback_manifest(
                    value['artifact'], _execution(), altered_source,
                    R05B_NATIVE_FEEDBACK_PROFILE,
                )
        finally:
            forged_canonical.close()
    finally:
        original.close()


def test_normal_profile_rejects_wrong_live_controller_or_law_before_materialization():
    from task_env.runtime.sessions.control import ControlBinding, materialize_control

    value = build_native_feedback_reference(backend='cpu', gripper_control_hz=500)
    source = value['source']
    receipt = source.execution_source_receipt
    controller = value['controller']
    actual_controller = controller.hold.controller
    try:
        original_identity = controller.hold.controller.identity
        controller.hold.controller.identity = '0' * 64
        try:
            with pytest.raises(ValueError, match='exact admitted R3 Controller'):
                materialize_control(
                    value['artifact'], _execution(), source=source,
                    binding=ControlBinding('panda-v1/gripper', .08),
                    native_feedback_profile=R05B_NATIVE_FEEDBACK_PROFILE,
                    selected_controller=controller, selected_solution=value['solution'],
                    native_feedback_gripper_control_hz=500,
                )
        finally:
            controller.hold.controller.identity = original_identity
        original_config = actual_controller.config
        actual_controller.config = replace(original_config, ik_position_gain=original_config.ik_position_gain + 0.1)
        try:
            with pytest.raises(ValueError, match='exact admitted R3 Controller'):
                materialize_control(
                    value['artifact'], _execution(), source=source,
                    binding=ControlBinding('panda-v1/gripper', .08),
                    native_feedback_profile=R05B_NATIVE_FEEDBACK_PROFILE,
                    selected_controller=controller, selected_solution=value['solution'],
                    native_feedback_gripper_control_hz=500,
                )
        finally:
            actual_controller.config = original_config
        original_solution_config = value['solution'].config
        value['solution'].config = replace(
            original_solution_config,
            translation_speed_m_s=original_solution_config.translation_speed_m_s + 0.01,
        )
        try:
            with pytest.raises(ValueError, match='exact admitted R3 Controller'):
                materialize_control(
                    value['artifact'], _execution(), source=source,
                    binding=ControlBinding('panda-v1/gripper', .08),
                    native_feedback_profile=R05B_NATIVE_FEEDBACK_PROFILE,
                    selected_controller=controller, selected_solution=value['solution'],
                    native_feedback_gripper_control_hz=500,
                )
        finally:
            value['solution'].config = original_solution_config
        with pytest.raises(ValueError, match='exact admitted R3 Controller'):
            materialize_control(
                value['artifact'], _execution(), source=source,
                binding=ControlBinding('panda-v1/gripper', .08),
                native_feedback_profile=R05B_NATIVE_FEEDBACK_PROFILE,
                selected_controller=controller, selected_solution=value['solution'],
                native_feedback_gripper_control_hz=100,
            )
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


def test_core_boundary_rejects_original_width_ids_before_any_provider_write():
    calls = []

    class Physics:
        n_actuators = 8

        def set_actuator_force_limits(self, ids, lower, upper):
            calls.append((ids.copy(), lower.copy(), upper.copy()))

    boundary = object.__new__(GeoPhysRuntimeBoundary)
    boundary._physics = Physics()
    boundary._actuator_force_limit_overrides = {}
    invalid = (
        ([2**32], ValueError),
        (np.asarray([2**64 - 1], dtype=np.uint64), ValueError),
        ([2**63], ValueError),
        ([-1], ValueError),
        ([1, True], TypeError),
        ([1.0], TypeError),
        ([[1]], TypeError),
        (np.asarray([1.0]), TypeError),
        (np.asarray([1, 1], dtype=np.int64), ValueError),
    )
    for ids, error in invalid:
        with pytest.raises(error):
            boundary.set_actuator_force_limits(ids, 10.0)
        assert boundary._actuator_force_limit_overrides == {}
        assert calls == []
    boundary.set_actuator_force_limits((), 10.0)
    assert boundary._actuator_force_limit_overrides == {}
    assert calls == []


class _ProviderFreeR05bSession(_SessionValues):
    """Use Core's shared interval loop with synthetic bottom-level physics IO."""

    def __init__(self, artifact, source, provider):
        self._initialize_values(artifact, source, provider)
        from task_env.controllers.canonical.kinematics import PandaKinematics
        self._kinematics = PandaKinematics(source.scene_source.xml)
        self._simulation_time = 0.0
        self._sample = None
        self._joint_position = {}
        self._joint_velocity = {}
        self._measurement = None
        self.close_count = 0

    def _measurement_at_current_time(self, *, phase, native_index):
        from task_env.environment import ActuatorForceMeasurementV1
        dt = float(self._artifact.timebase.physics_dt)
        self._measurement = ActuatorForceMeasurementV1(
            schema_version='task-env-actuator-force-sample-v1',
            source_generation=1,
            sample_sequence=native_index + 1,
            state_revision=self._state_revision,
            configuration_revision=0,
            native_step_index=native_index,
            phase=phase,
            valid=True,
            force_unit='N',
            episode_id=str(self._episode_id),
            reset_sample_id=str(self._reset_sample_id),
            evaluation_control_step=native_index // self._artifact.timebase.control_substeps,
            evaluation_simulation_time_s=self._simulation_time,
            actuator_id=self._source.open_actuators[0],
            actuator_ctrl=0.0,
            signed_force_N=-1.0,
            native_sample_time_s=(0.0 if native_index == 0 else (native_index - 1) * dt),
        )

    def reset(self, sample):
        self._begin_reset()
        self._validate_sample(sample)
        self._sample = sample
        self._joint_position = {name: float(value) for name, value in sample.joint_position.items()}
        self._joint_velocity = {name: 0.0 for name in sample.joint_position}
        self._simulation_time = 0.0
        realized = self._realized(sample)
        self._measurement_at_current_time(phase='reset_forward', native_index=0)
        return realized

    def _poses(self):
        from task_env.artifacts import PoseWorld
        from task_env.utils.rotation import matrix_to_quat_wxyz
        poses = dict(self._sample.poses_world)
        identity = PoseWorld((0.4, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
        for semantic in self._source.bodies:
            poses.setdefault(semantic, identity)
        if 'panda-v1/ee' in self._source.frames:
            q = np.asarray([self._joint_position[f'panda-v1/joint{i}'] for i in range(1, 8)])
            matrix, _jacobian = self._kinematics.fk_jacobian(q)
            poses['panda-v1/ee'] = PoseWorld(
                tuple(float(value) for value in matrix[:3, 3]),
                tuple(float(value) for value in matrix_to_quat_wxyz(matrix[:3, :3])),
            )
        for semantic in self._source.frames:
            poses.setdefault(semantic, identity)
        return poses

    def snapshot(self):
        self._require_reset()
        return self._state(
            dict(self._joint_position), dict(self._joint_velocity), self._poses(),
            self._simulation_time,
        )

    def control_feedback(self, state, *, actuator_force=None):
        from task_env.runtime.sessions.control import feedback_value
        self._require_reset()
        if not self._measurement.valid:
            raise ValueError('synthetic provider force sample is invalid')
        return feedback_value(self, state, self._measurement.signed_force_N)

    def native_control_feedback_sample(self, state, feedback):
        from task_env.controllers.canonical.feedback import NativeControlFeedbackSampleV1
        return NativeControlFeedbackSampleV1(
            'native-control-feedback-sample-v1', self._provider,
            self._provider_materialization_id, self._source.scene_source.source_id,
            self._source.source_closure_digest, str(self._episode_id),
            str(self._reset_sample_id), feedback, self._measurement,
        )

    def apply_control(self, target):
        from task_env.controllers.canonical.contracts import AppliedCanonicalControl
        return AppliedCanonicalControl(
            'applied-canonical-control-v0', target.identity_hash, self._provider,
            dict(target.arm_servo_position), target.gripper.servo_opening_m,
            target.gripper.force_limit_N, False,
            'provider-free synthetic acknowledgement for R05b S1',
        )

    def _step_physics_once(self):
        self._require_reset()
        self._simulation_time += float(self._artifact.timebase.physics_dt)
        self._state_revision += 1
        native_index = int(round(self._simulation_time / self._artifact.timebase.physics_dt))
        self._measurement_at_current_time(
            phase='native_step_pre_integration', native_index=native_index,
        )

    def step_control_interval(self, *args, **kwargs):
        from task_env.runtime.sessions.common import _SessionValues
        return _SessionValues.step_control_interval(self, *args, **kwargs)

    def step(self):
        self._require_reset()
        for _ in range(self._artifact.timebase.control_substeps):
            self._step_physics_once()
        self._control_step += 1
        return self.snapshot()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.close_count += 1
        receipt = getattr(self._source, 'execution_source_receipt', None)
        if receipt is not None:
            receipt.close()


def _install_provider_free_materialize(monkeypatch):
    def materialize(artifact, execution, source):
        return _ProviderFreeR05bSession(artifact, source, execution.physics_provider)
    monkeypatch.setattr(api, '_materialize_admitted', materialize)


def test_ordinary_public_pickcube_and_nutassembly_reset_step_routes_survive(monkeypatch):
    _install_provider_free_materialize(monkeypatch)
    from task_env.tasks.pick_cube.task import PickCubeReferenceEnv

    pick = PickCubeReferenceEnv(provider='geophys', backend='cpu')
    try:
        pick.reset(seed=19)
        ee = pick.state.pose_world['panda-v1/ee']
        action = (*ee.position, *ee.quaternion_wxyz, 1.0)
        pick.step(action)
        assert pick.state.control_step == 1
    finally:
        pick.close()

    ordinary = NutAssemblyReferenceEnv(provider='geophys', backend='cpu')
    try:
        solution = ordinary.solution
        ordinary.reset_for_solution(solution, seed=19)
        _obs, _reward, terminated, truncated, _info = ordinary.step_with_solution(solution)
        assert not terminated and not truncated
        assert ordinary.state.control_step == 1
    finally:
        ordinary.close()


@pytest.mark.parametrize(('law_hz', 'expected_updates', 'expected_holds'), [
    (100, 1, 4), (500, 5, 0),
])
def test_normal_public_profile_laws_drive_real_five_sample_interval(
    monkeypatch, law_hz, expected_updates, expected_holds,
):
    _install_provider_free_materialize(monkeypatch)
    env = NutAssemblyReferenceEnv.for_native_feedback_profile(
        backend='cpu', gripper_control_hz=law_hz,
    )
    solution = env.solution
    try:
        env.reset_for_solution(solution, seed=19)
        assert env.controller.gripper_rate_hz == law_hz
        _obs, _reward, terminated, truncated, _info = env.step_with_solution(solution)
        assert not terminated and not truncated
        assert env.controller.inner.update_count == expected_updates
        assert env.controller.inner.held_count == expected_holds
        assert env.info['native_interval_receipt_v1']['completed_substeps'] == 5
        assert len(env.info['native_interval_receipt_v1']['samples']) == 5
        assert env.state.control_step == 1
        assert abs(env.state.simulation_time - 0.01) < 1e-12
    finally:
        env.close()


def _run_raw_reader(h5_path, expected_path, output_path):
    return subprocess.run(
        [sys.executable, '-I', '-B', str(Path(raw_reader.__file__).resolve()),
         '--h5', str(h5_path), '--expected', str(expected_path), '--output', str(output_path)],
        cwd=output_path.parent, text=True, capture_output=True, timeout=60,
    )


def test_real_r05b_worker_recorder_finalizer_and_independent_reader_provider_free(
    monkeypatch, tmp_path,
):
    output_root = Path(os.environ.get('R05B_S1_OUTPUT_ROOT', str(tmp_path)))
    output_root.mkdir(parents=True, exist_ok=True)
    _install_provider_free_materialize(monkeypatch)
    output = output_root / f'worker_synthetic_success_{uuid4().hex[:8]}'
    result = worker.run('cpu', output)
    assert result['status'] == 'passed' and result['close_success'] is True
    assert result['completed_outer_intervals'] == 2
    assert result['completed_native_steps'] == 10
    assert result['reader']['native_sample_count'] == 10
    (output / 's1_synthetic_provenance.json').write_text(json.dumps({
        'schema_version': 'r05b-provider-free-worker-s1-v1',
        'status': 'SYNTHETIC_IO_ONLY_NOT_PHYSICAL_S2',
        'actual_core_path': 'SelectedReferenceEnv -> normal R05b admission -> shared native interval -> Controller/Guard -> ExecutionRecorder -> production H5 reader -> close',
        'substitution': 'only _materialize_admitted bottom-level RuntimeSession/native physics IO replaced by _ProviderFreeR05bSession',
        'h5_path': result['h5_path'],
    }, indent=2, sort_keys=True) + '\n')
    expected = {
        name: result[name] for name in (
            'backend', 'artifact_identity', 'source_id', 'source_xml_sha256',
            'controller_identity', 'solution_identity', 'episode_id',
            'reset_sample_id', 'provider_materialization_id',
        )
    }
    expected_path = output / 'independent_reader_expected.json'
    expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + '\n')
    independent_output = output / 'independent_reader.json'
    positive = _run_raw_reader(result['h5_path'], expected_path, independent_output)
    assert positive.returncode == 0, positive.stdout + positive.stderr
    raw = json.loads(independent_output.read_text())
    assert raw['imports_task_env'] is False
    assert raw['source_closure_digest'] == 'bf08619661608cf4caa7ecacda2ab9f4cd02489fd411935a26678bdde8b07f6c'

    wrong_expected = {**expected, 'source_id': 'wrong-run-source'}
    wrong_expected_path = output / 'independent_reader_wrong_source_expected.json'
    wrong_expected_path.write_text(json.dumps(wrong_expected, sort_keys=True) + '\n')
    wrong_source = _run_raw_reader(
        result['h5_path'], wrong_expected_path, output / 'reader_wrong_source.json',
    )
    assert wrong_source.returncode != 0
    wrong_episode_path = output / 'independent_reader_wrong_episode_expected.json'
    wrong_episode_path.write_text(json.dumps(
        {**expected, 'episode_id': 'episode-wrong-run'}, sort_keys=True,
    ) + '\n')
    wrong_episode = _run_raw_reader(
        result['h5_path'], wrong_episode_path, output / 'reader_wrong_episode.json',
    )
    assert wrong_episode.returncode != 0

    truncated = output / 'truncated.h5'
    truncated.write_bytes(Path(result['h5_path']).read_bytes()[:256])
    truncated_result = _run_raw_reader(
        truncated, expected_path, output / 'reader_truncated.json',
    )
    assert truncated_result.returncode != 0

    tampered = output / 'tampered_receipt.h5'
    with h5py.File(result['h5_path'], 'r') as source_h5:
        logical = json.loads(source_h5['logical_json_utf8'][:].tobytes())
        control_step = source_h5['control_step'][:]
        native_step_index = source_h5['native_step_index'][:]
    provenance = logical['metadata']['source_provenance']
    receipt = json.loads(provenance['runtime_execution_source_receipt_json'])
    receipt['files'][0]['sha256'] = '0' * 64
    receipt['source_closure_digest'] = raw_reader._closure_digest(receipt['files'])
    provenance['runtime_execution_source_receipt_json'] = json.dumps(
        receipt, sort_keys=True, separators=(',', ':'), allow_nan=False,
    )
    logical_bytes = json.dumps(
        logical, sort_keys=True, separators=(',', ':'), allow_nan=False,
    ).encode('utf-8')
    with h5py.File(tampered, 'w') as target_h5:
        target_h5.create_dataset('logical_json_utf8', data=np.frombuffer(logical_bytes, dtype=np.uint8))
        target_h5.create_dataset('control_step', data=control_step)
        target_h5.create_dataset('native_step_index', data=native_step_index)
        target_h5.attrs['logical_hash'] = raw_reader._canonical_digest(logical)
    tampered_result = _run_raw_reader(
        tampered, expected_path, output / 'reader_tampered_receipt.json',
    )
    assert tampered_result.returncode != 0
    assert 'trusted full source closure' in tampered_result.stderr

    def mutate_and_reject(name, mutate, *, allow_nan=False):
        target = output / f'tampered_{name}.h5'
        with h5py.File(result['h5_path'], 'r') as source_h5:
            value = json.loads(source_h5['logical_json_utf8'][:].tobytes())
            control_projection = source_h5['control_step'][:]
            native_projection = source_h5['native_step_index'][:]
            previous_hash = source_h5.attrs['logical_hash']
        first = value['transitions'][0]['interval']['substeps'][0][
            'native_feedback_sample_v1']['provider_feedback_sample']['actuator_force_measurement']
        second = value['transitions'][0]['interval']['substeps'][1][
            'native_feedback_sample_v1']['provider_feedback_sample']['actuator_force_measurement']
        third = value['transitions'][0]['interval']['substeps'][2][
            'native_feedback_sample_v1']['provider_feedback_sample']['actuator_force_measurement']
        mutate(first, second, third)
        logical_payload = json.dumps(
            value, sort_keys=True, separators=(',', ':'), allow_nan=allow_nan,
        ).encode('utf-8')
        logical_hash = previous_hash if allow_nan else raw_reader._canonical_digest(value)
        with h5py.File(target, 'w') as target_h5:
            target_h5.create_dataset('logical_json_utf8', data=np.frombuffer(logical_payload, dtype=np.uint8))
            target_h5.create_dataset('control_step', data=control_projection)
            target_h5.create_dataset('native_step_index', data=native_projection)
            target_h5.attrs['logical_hash'] = logical_hash
        receipt_path = output / f'reader_tampered_{name}.json'
        process = _run_raw_reader(target, expected_path, receipt_path)
        assert process.returncode != 0, f'{name} tampering unexpectedly passed'
        (output / f'reader_tampered_{name}_failure.json').write_text(json.dumps({
            'returncode': process.returncode,
            'stderr': process.stderr[-2000:],
        }, indent=2, sort_keys=True) + '\n')

    mutate_and_reject('phase', lambda first, _second, _third: first.update(phase='state_restore_forward'))
    mutate_and_reject('generation', lambda _first, second, _third: second.update(source_generation=2))
    mutate_and_reject('revision', lambda first, second, _third: second.update(state_revision=first['state_revision']))
    mutate_and_reject('sequence', lambda first, second, _third: second.update(sample_sequence=first['sample_sequence']))
    mutate_and_reject(
        'clock', lambda _first, _second, third: third.update(evaluation_simulation_time_s=0.005),
    )
    mutate_and_reject('nan_force', lambda first, _second, _third: first.update(signed_force_N=float('nan')),
                      allow_nan=True)

    original_step = _ProviderFreeR05bSession._step_physics_once
    def worker_failure(self):
        raise RuntimeError('synthetic worker exception for S1 finalizer')
    monkeypatch.setattr(_ProviderFreeR05bSession, '_step_physics_once', worker_failure)
    failed = worker.run('cpu', output_root / f'worker_synthetic_exception_{uuid4().hex[:8]}')
    assert failed['status'] == 'failed_or_blocked' and failed['close_success'] is True
    monkeypatch.setattr(_ProviderFreeR05bSession, '_step_physics_once', original_step)

    original_close = _ProviderFreeR05bSession.close
    def close_failure(self):
        original_close(self)
        raise RuntimeError('synthetic close failure for S1 finalizer')
    monkeypatch.setattr(_ProviderFreeR05bSession, 'close', close_failure)
    close_failed = worker.run('cpu', output_root / f'worker_synthetic_close_{uuid4().hex[:8]}')
    assert close_failed['status'] == 'failed_or_blocked' and close_failed['close_success'] is False


def test_native_supervisor_rejects_uninitialized_resource_receipt():
    worker_result = {'status': 'passed', 'close_success': True}
    assert supervisor._worker_resources_pass(
        backend='cpu', child_return=0, resource_limit_reason=None,
        worker_result=worker_result, rss_sample_count=1, rss_max_sample_bytes=4096,
        minimum_mem_available_sample_bytes=8 * 1024**3,
        minimum_gpu_free_sample_bytes=None,
    )
    assert not supervisor._worker_resources_pass(
        backend='cpu', child_return=0, resource_limit_reason=None,
        worker_result=worker_result, rss_sample_count=0, rss_max_sample_bytes=0,
        minimum_mem_available_sample_bytes=None, minimum_gpu_free_sample_bytes=None,
    )
    assert not supervisor._worker_resources_pass(
        backend='cpu', child_return=0, resource_limit_reason=None,
        worker_result={'status': 'passed', 'close_success': False},
        rss_sample_count=1, rss_max_sample_bytes=4096,
        minimum_mem_available_sample_bytes=8 * 1024**3,
        minimum_gpu_free_sample_bytes=None,
    )
