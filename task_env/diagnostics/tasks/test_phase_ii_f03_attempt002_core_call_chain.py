"""F03 attempt002 actual Core factory/reset/step/Recorder S1 integration.

The fixture implements only the typed NativeRuntimeIOV1 port. It contains no
Core lifecycle, controller, Session, time integrator, or Recorder behavior.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from task_env.artifacts import (
    ArticulationDefinition, EntityDefinition, EntityInstance, ExecutionSpecV1,
    FrameDefinition, FrameReference, JointDefinition, PoseWorld, RendererSelectionV1,
    SceneDefinition, Timebase,
)
from task_env.assembly.source import UsdTaskSceneSourceV1
from task_env.assembly.usd_delivery import load_usd_asset_delivery, resolve_provider_representation
from task_env.controllers.canonical.contracts import ControlGroupActionV1, StructuredActionRequestV1
from task_env.environment import compile_task_artifact_v1, sample_episode_reset_plan
from task_env.runtime.sessions.free_joint_state import PublicRigidBodyReadbackV1
from task_env.runtime.sessions.leaf_control import compile_isaac_named_position_drive_receipt_v1
from task_env.runtime.sessions.native_io import (
    NativeAdvanceReceiptV1, NativePositionWriteAckV1, NativeResetWriteReceiptV1,
    NativeRuntimeIOMetadataV1, NativeRuntimeReadbackV1,
)
from task_env.runtime.sessions.source import UsdRuntimeSourceV1
from task_env.tasks.position_candidate.builder import F03PositionCandidateInputV1
from task_env.tasks.position_candidate.source import _a05_scene, _artifact_and_sample, _task_source
from task_env.tasks.reference_env import SelectedReferenceEnv


_DOFS = (
    'panda_finger_joint2', 'panda_joint4', 'panda_joint1', 'panda_joint7',
    'panda_finger_joint1', 'panda_joint2', 'panda_joint6', 'panda_joint3',
    'panda_joint5',
)


def _execution():
    return ExecutionSpecV1(
        'execution-spec-v1', 'isaacsim', 'cuda', 'physx-gpu-f03-s1', 0,
        'best_effort', RendererSelectionV1(
            'renderer-selection-v1', 'none', 'cpu', 'none', None,
        ), 'cuda:0', (),
    )


def _versioned_input(tmp_path: Path) -> F03PositionCandidateInputV1:
    from task_env.diagnostics.tasks.f02_usd_delivery_fixture import build_fixture

    delivery_path = build_fixture(tmp_path / 'f02-synthetic-delivery')
    loaded = load_usd_asset_delivery(delivery_path, allow_synthetic=True)
    representation = resolve_provider_representation(
        loaded, provider='isaacsim', provider_build_identity='isaacsim-6.2.0.0',
    )
    base = _a05_scene()
    peg_asset = loaded.delivery.asset_definition
    assets = tuple(
        peg_asset if item.asset_id == 'square-peg-v1' else item for item in base.assets
    )
    entities = tuple(
        EntityInstance(item.schema_version, item.entity_id, peg_asset.asset_id, peg_asset.asset_version)
        if item.entity_id == 'square-peg-instance' else item
        for item in base.entities
    )
    frames = (*base.frames, FrameDefinition(
        'frame-definition-v1', 'square-peg-instance', 'anchor', 'runtime', None, None,
    ))
    free_joint = JointDefinition(
        'joint-definition-v1', 'floating_root',
        FrameReference('square-peg-instance', 'anchor'),
        FrameReference('square-peg-instance', 'peg1'),
        PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
        PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
        'floating', None, 'xyz_meter_quaternion_wxyz',
        'linear_xyz_meter_per_second_angular_xyz_radian_per_second', 7, 6,
    )
    scene = replace(
        base, scene_id='f03-attempt002-panda-free-peg-v1', assets=assets,
        entities=entities, frames=tuple(frames),
        articulations=(*base.articulations, ArticulationDefinition(
            'articulation-definition-v1', 'square-peg-instance', 'anchor',
            ('anchor', 'peg1'), (free_joint,),
        )),
    )
    legacy, _unused_sample = _artifact_and_sample(scene)
    floating_name = 'square-peg-instance/floating_root'
    scalar_names = tuple(sorted(
        f'{articulation.entity_id}/{joint.joint_id}'
        for articulation in scene.articulations for joint in articulation.joints
        if joint.kind in {'revolute', 'continuous', 'prismatic'}
    ))
    scalar_name_set = set(scalar_names)
    world_entities = tuple(
        replace(
            entity,
            kind='movable' if entity.semantic_id == 'square-peg-instance' else entity.kind,
            joints=tuple(name for name in entity.joints if name in scalar_name_set),
        )
        for entity in legacy.world.entities
    )
    reset_pose = PoseWorld((0.12, -0.08, 0.23), (0.9238795325112867, 0.0, 0.0, 0.3826834323650898))
    legacy = replace(
        legacy,
        artifact_id='f03-attempt002-position-v1',
        task_id='f03-attempt002-position', artifact_version='candidate-v1',
        world=replace(legacy.world, entities=world_entities),
        initialization=replace(
            legacy.initialization,
            poses_world={'square-peg-instance/peg1': reset_pose},
            joint_position={name: value for name, value in legacy.initialization.joint_position.items()
                            if name != floating_name},
        ),
        semantics=replace(
            legacy.semantics, required_joints=scalar_names,
        ),
        timebase=Timebase(0.002, 5, 0.01),
    )
    task_source = replace(
        _task_source(scene), task_id=legacy.task_id, version=legacy.artifact_version,
    )
    artifact = compile_task_artifact_v1(task_source, scene, legacy)
    reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=31)
    task_scene_source = UsdTaskSceneSourceV1(
        'usd-task-scene-source-v1', loaded, representation,
        task_source.identity_hash, scene.identity_hash,
    )
    joints = {
        name: reference.joint_id
        for name, reference in artifact.legacy_joint_bindings.items()
    }
    bodies = {
        name: reference.frame_id
        for name, reference in artifact.legacy_frame_bindings.items()
    }
    free_joints = {'square-peg-instance/peg1': 'peg1-free-root'}
    joint_targets = {
        f'panda-main/joint{index}': f'panda_joint{index}' for index in range(1, 8)
    }
    joint_targets.update({
        'panda-main/finger_joint1': 'panda_finger_joint1',
        'panda-main/finger_joint2': 'panda_finger_joint2',
    })
    source = UsdRuntimeSourceV1(
        'usd-runtime-source-v1', artifact, scene, task_scene_source,
        joints, bodies, {}, free_joints, joint_targets,
    )
    execution = _execution()
    limits = {
        name: ((0.0, 0.04) if name.startswith('panda_finger') else (-3.2, 3.2))
        for name in _DOFS
    }
    receipt = compile_isaac_named_position_drive_receipt_v1(
        execution=execution, scene_identity_sha256=scene.identity_hash,
        source_closure_sha256=source.source_closure_digest,
        provider_build_identity='isaacsim-6.2.0.0',
        writer_id='panda-main/position-servo-v1', native_dof_names=_DOFS,
        native_position_limits=limits,
    )
    xml_path = Path('asset/external/mujoco_menagerie/franka_emika_panda/panda.xml')
    xml = xml_path.read_text()
    return F03PositionCandidateInputV1(
        'f03-position-candidate-input-v1', task_source, artifact, source,
        execution, reset_plan, xml, hashlib.sha256(xml.encode()).hexdigest(), receipt,
    )


class _SyntheticPandaNativeIO:
    """Stateful low-level fixture: named values and clocks, no simulation."""

    def __init__(self, *, artifact, execution, source, drive_receipt, input_v1, faults=None):
        from task_env.controllers.canonical.kinematics import PandaKinematics, PANDA_HAND_ORIGIN_TCP_V1

        self.artifact, self.execution, self.source = artifact, execution, source
        self.drive_receipt = drive_receipt
        self.faults = dict(faults or {})
        self.model = PandaKinematics(input_v1.kinematics_source_xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1)
        limits = {
            name: ((0.0, 0.04) if name.startswith('panda_finger') else (-3.2, 3.2))
            for name in _DOFS
        }
        self._metadata = NativeRuntimeIOMetadataV1(
            'native-runtime-io-metadata-v1', source.source_id,
            source.source_closure_digest, source.scene_definition.identity_hash,
            artifact.identity_hash, execution.identity_hash, 'isaacsim',
            'isaacsim-6.2.0.0', 'cuda', 'cuda:0', 'best_effort',
            artifact.timebase.physics_dt, artifact.timebase.control_substeps,
            _DOFS, limits,
        )
        self.joints = {}
        self.free_pose = None
        self.time_s = 0.0
        self.native_index = 0
        self.reset_count = self.read_count = self.target_write_count = 0
        self.advance_count = self.close_count = 0
        self.operations = []
        self.last_targets = None

    def metadata(self):
        self.operations.append({'op': 'metadata', 'advance_count': self.advance_count})
        return self._metadata

    def write_reset(self, sample, position_targets):
        self.reset_count += 1
        self.joints = dict(sample.joint_position)
        self.free_pose = sample.poses_world['square-peg-instance/peg1']
        self.time_s = 0.0
        self.native_index = 0
        self.last_targets = tuple(position_targets)
        names = tuple(name for _index, name, _value in position_targets)
        receipt = NativeResetWriteReceiptV1(
            'native-reset-write-receipt-v1', sample.sample_id,
            tuple(sorted(self.source.joints)), tuple(sorted(self.source.free_joints)),
            names, True, False,
        )
        if self.faults.get('partial_reset_receipt'):
            receipt = replace(receipt, partial=True)
        self.operations.append({'op': 'write_reset', 'reset_count': self.reset_count})
        return receipt

    def read_state(self):
        from task_env.artifacts import FrameReference, PoseWorld

        self.read_count += 1
        if (self.faults.get('read_state_at_advance_count') == self.advance_count
                and not self.faults.get('read_state_fault_consumed', False)):
            self.faults['read_state_fault_consumed'] = True
            self.operations.append({'op': 'read_state_error', 'advance_count': self.advance_count})
            raise RuntimeError('synthetic low-level readback sentinel')
        arm = [self.joints[f'panda-main/joint{index}'] for index in range(1, 8)]
        hand_pose = self.model.pose(arm)
        frames = {}
        for canonical_name in self.source.bodies:
            if canonical_name == 'panda-main/hand':
                frames[canonical_name] = hand_pose
            elif canonical_name == 'square-peg-instance/peg1':
                frames[canonical_name] = self.free_pose
            else:
                frames[canonical_name] = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
        native_name_by_joint = {
            f'{item.canonical_joint.entity_id}/{item.canonical_joint.joint_id}': item.native_dof_name
            for item in self.drive_receipt.drives
        }
        positions = dict(self.joints)
        velocities = {name: 0.0 for name in self.source.joints}
        free = {
            'square-peg-instance/peg1': PublicRigidBodyReadbackV1(
                'public-rigid-body-readback-v1',
                FrameReference('square-peg-instance', 'peg1'),
                self.free_pose.position, self.free_pose.quaternion_wxyz,
                (0.013, -0.004, 0.009), (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0), 'world', 'center_of_mass',
            ),
        }
        # Check the reordered native receipt remains a name-based mapping.
        if set(native_name_by_joint) != set(self.source.joint_targets):
            raise AssertionError('fixture receipt does not cover exact canonical target map')
        self.operations.append({'op': 'read_state', 'advance_count': self.advance_count})
        return NativeRuntimeReadbackV1(
            'native-runtime-readback-v1', positions, velocities, frames, free, self.time_s,
        )

    def write_position_targets(self, target_identity_sha256, targets):
        self.target_write_count += 1
        expected_names = tuple(name for _index, name, _value in targets)
        expected = {name: value for _index, name, value in targets}
        if len(expected) != 9 or set(expected) != set(_DOFS):
            raise ValueError('fixture accepts the exact nine named Panda DOF targets')
        selected = self.drive_receipt.drives
        if self.faults.get('partial_position_ack'):
            selected = selected[:1]
        for drive in selected:
            self.joints[f'{drive.canonical_joint.entity_id}/{drive.canonical_joint.joint_id}'] = expected[
                drive.native_dof_name
            ]
        self.last_targets = tuple(targets)
        self.operations.append({'op': 'write_position_targets', 'names': list(expected_names)})
        if self.faults.get('partial_position_ack'):
            self.last_partial_written_names = (selected[0].native_dof_name,)
            return NativePositionWriteAckV1(
                'native-position-write-ack-v1', target_identity_sha256,
                self.last_partial_written_names, (expected[self.last_partial_written_names[0]],),
                True, 1,
            )
        if self.faults.get('missing_position_ack'):
            # Keep completed low-level side effects visible while forcing the
            # Core Target/Ack boundary to fail closed.
            return None
        return NativePositionWriteAckV1(
            'native-position-write-ack-v1', target_identity_sha256,
            expected_names, tuple(float(value) for _index, _name, value in targets),
            False, len(targets),
        )

    def advance(self):
        self.advance_count += 1
        self.native_index += 1
        self.time_s = self.native_index * self.artifact.timebase.physics_dt
        self.operations.append({'op': 'advance', 'index': self.native_index})
        if self.faults.get('advance_error_at') == self.native_index:
            self.operations.append({'op': 'advance_error_after_side_effect', 'index': self.native_index})
            raise RuntimeError('synthetic low-level advance sentinel')
        return NativeAdvanceReceiptV1(
            'native-advance-receipt-v1', 1, self.native_index, self.time_s,
        )

    def close(self):
        self.close_count += 1
        self.operations.append({'op': 'close', 'count': self.close_count})
        if self.faults.get('close_error'):
            raise RuntimeError('synthetic low-level close sentinel')


def _action(env):
    from task_env.controllers.canonical.contracts import StructuredActionRequestV1, ControlGroupActionV1

    joints = env.typed_state.view.joints
    arm = {item.joint_id: item.position[0] for item in joints if item.entity_id == 'panda-main'}
    pose = env.controller.model.pose([arm[f'joint{index}'] for index in range(1, 8)])
    schema = env.controller.controller_binding().action_schema
    return StructuredActionRequestV1(
        'structured-action-request-v1', env.position_plan.scene_identity_hash,
        env.position_plan.identity_hash,
        (
            ControlGroupActionV1('control-group-action-v1', 'panda-main', 'arm', schema.schema_id,
                                 (*pose.position, *pose.quaternion_wxyz)),
            ControlGroupActionV1('control-group-action-v1', 'panda-main', 'gripper', schema.schema_id, (1.0,)),
        ),
    )


def test_make_env_two_reset_public_position_h5_chain(tmp_path):
    from task_env.registry import make_env
    from task_env.runtime.sessions.api import _f03_s1_native_io_context
    from task_env.recorders import load_structured_control_records_h5

    input_v1 = _versioned_input(tmp_path)
    adapters = []

    def factory(**kwargs):
        adapter = _SyntheticPandaNativeIO(**kwargs, input_v1=input_v1)
        adapters.append(adapter)
        return adapter

    env = make_env(
        'panda-position-servo-candidate-v1',
        config={'versioned_input': input_v1, 'horizon': 4},
    )
    outputs = []
    previous_episode_id = None
    previous_boundary_id = None
    try:
        for episode in range(2):
            with _f03_s1_native_io_context(input_v1, factory):
                observation, info = env.reset(seed=31)
            boundary = env.typed_state.view.boundary
            assert env.execution is input_v1.execution
            assert env.session._declared_execution_spec_v1 is input_v1.execution
            assert env.session.reset_plan_evidence['reset_sample_id'] == input_v1.reset_plan.reset_sample.sample_id
            assert env.session._reset_write_receipt.velocities_zeroed is True
            assert adapters[-1].free_pose == input_v1.reset_plan.reset_sample.poses_world[
                'square-peg-instance/peg1'
            ]
            assert env.state.control_step == 0 and env.state.simulation_time == 0.0
            assert env.controller._episode_id == boundary.episode_id
            assert env.controller._next_control_step == 0
            assert env.controller._activation_boundary_id == boundary.boundary_id
            assert env._last_position_request is None
            if previous_episode_id is not None:
                assert boundary.episode_id != previous_episode_id
                assert boundary.boundary_id != previous_boundary_id
                assert env.session._position_applied_boundary_ids == set()
            assert env.session._last_readback.free_joint_readback['square-peg-instance/peg1'].linear_velocity_world_at_com_m_s == (0.0, 0.0, 0.0)
            before_advance = adapters[-1].advance_count
            # Runner-owned typed re-snapshot and metadata reads do not advance the synthetic clock.
            env.session.snapshot_v1(
                scene=env.position_scene, joint_bindings=env.position_joint_bindings,
                frame_bindings=env.position_frame_bindings, requirements=env._position_requirements(),
            )
            env.session._native_io.metadata()
            assert adapters[-1].advance_count == before_advance == 0
            path = tmp_path / f'episode-{episode}.h5'
            env.start_recording(path)
            for _ in range(4):
                env.step(_action(env))
            assert adapters[-1].advance_count == 20
            result = env.finish_recording('horizon')
            assert result['transition_count'] == 4 and result['observation_count'] == 5
            output = Path(result['path'])
            assert output.stat().st_size <= 32 * 1024 * 1024
            loaded = load_structured_control_records_h5(output)
            assert loaded['transition_count'] == 4 and loaded['observation_count'] == 5
            profile = loaded['env_meta']['reference_profile']
            assert profile['provenance_kind'] == 'synthetic_fixture'
            assert profile['runtime_admitted'] is False and profile['source_verified'] is False
            assert profile['execution_identity_sha256'] == input_v1.execution.identity_hash
            assert profile['reset_plan_identity_sha256'] == input_v1.reset_plan.identity_hash
            for control in loaded['structured_controls']:
                applied = control.writer_controls[0]['applied_control']['payload']
                assert len(applied['native_interval_advance_receipts_v1']) == 5
                ack = applied['native_position_write_ack_v1']
                assert len(ack['native_names']) == 9
                by_name = dict(zip(ack['native_names'], ack['applied_values'], strict=True))
                assert by_name['panda_finger_joint1'] == pytest.approx(by_name['panda_finger_joint2'])
                target = control.writer_controls[0]['controller_target']['payload']
                assert by_name['panda_finger_joint1'] + by_name['panda_finger_joint2'] == pytest.approx(
                    target['gripper']['servo_opening_m'],
                )
            outputs.append(output)
            previous_episode_id = boundary.episode_id
            previous_boundary_id = boundary.boundary_id
        assert len(outputs) == 2 and sum(path.stat().st_size for path in outputs) <= 128 * 1024 * 1024
        assert adapters[0].close_count == 1  # second reset invalidated/closed episode one's view
        assert adapters[1].close_count == 0
    finally:
        env.close()
    assert adapters[1].close_count == 1


def test_production_materialize_remains_fail_closed_for_synthetic_usd(tmp_path):
    from task_env.runtime.sessions.api import materialize

    input_v1 = _versioned_input(tmp_path)
    with pytest.raises(ValueError, match='synthetic or unverified USD source'):
        materialize(input_v1.artifact, input_v1.execution, source=input_v1.runtime_source)


def _fault_env(tmp_path, faults, *, wrong_build=False, wrong_device=False):
    from task_env.registry import make_env
    from task_env.runtime.sessions.api import _f03_s1_native_io_context

    input_v1 = _versioned_input(tmp_path)
    adapters = []

    def factory(**kwargs):
        adapter = _SyntheticPandaNativeIO(**kwargs, input_v1=input_v1, faults=faults)
        if wrong_build:
            adapter._metadata = replace(adapter._metadata, provider_build_identity='wrong-build')
        if wrong_device:
            adapter._metadata = replace(adapter._metadata, device='cuda:1')
        adapters.append(adapter)
        return adapter

    env = make_env(
        'panda-position-servo-candidate-v1',
        config={'versioned_input': input_v1, 'horizon': 4},
    )
    return input_v1, env, adapters, factory, _f03_s1_native_io_context


def test_f03_reset_build_and_partial_reset_fail_closed_with_cleanup(tmp_path):
    input_v1, env, adapters, factory, scope = _fault_env(tmp_path, {}, wrong_build=True)
    with pytest.raises(ValueError, match='native I/O DOF/build metadata'):
        with scope(input_v1, factory):
            env.reset(seed=31)
    assert len(adapters) == 1
    assert adapters[0].reset_count == 0 and adapters[0].read_count == 0
    assert adapters[0].close_count == 1
    assert env.session is None and env.execution_fault.exception_type == 'ValueError'

    input_v1, env, adapters, factory, scope = _fault_env(
        tmp_path / 'partial-reset', {'partial_reset_receipt': True},
    )
    with pytest.raises(ValueError, match='reset writes must be complete'):
        with scope(input_v1, factory):
            env.reset(seed=31)
    assert adapters[0].reset_count == 1 and adapters[0].read_count == 0
    assert env.session is None
    assert adapters[0].close_count == 1

    input_v1, env, adapters, factory, scope = _fault_env(
        tmp_path / 'wrong-device', {}, wrong_device=True,
    )
    with pytest.raises(ValueError, match='metadata differs from source/artifact/execution identity'):
        with scope(input_v1, factory):
            env.reset(seed=31)
    assert adapters[0].reset_count == 0 and adapters[0].read_count == 0
    assert adapters[0].close_count == 1


def test_f03_partial_ack_and_partial_advance_preserve_primary_and_native_facts(tmp_path):
    faults = {'partial_position_ack': True}
    input_v1, env, adapters, factory, scope = _fault_env(tmp_path, faults)
    try:
        with scope(input_v1, factory):
            env.reset(seed=31)
        env.start_recording(tmp_path / 'partial-ack.h5')
        with pytest.raises(ValueError, match='Ack reports partial apply'):
            env.step(_action(env))
        adapter = adapters[0]
        assert adapter.last_partial_written_names == (_DOFS[0],)
        assert env.session._last_native_position_ack.partial is True
        assert env.execution_fault.message == 'native Position write Ack reports partial apply'
        assert env.execution_fault.transition_status == 'incomplete'
        assert env.recorder.transition_count == 0 and env.recorder.observation_count == 1
        assert adapter.advance_count == 0
    finally:
        env.close()

    # A complete low-level write without an Ack cannot be treated as an
    # acknowledged Target or published transition.
    faults = {'missing_position_ack': True}
    input_v1, env, adapters, factory, scope = _fault_env(tmp_path / 'missing-ack', faults)
    try:
        with scope(input_v1, factory):
            env.reset(seed=31)
        env.start_recording(tmp_path / 'missing-ack.h5')
        with pytest.raises(TypeError, match='must return NativePositionWriteAckV1'):
            env.step(_action(env))
        assert adapters[0].target_write_count == 1
        assert adapters[0].advance_count == 0
        assert env.session._last_native_position_ack is None
        assert env.execution_fault.exception_type == 'TypeError'
        assert env.execution_fault.transition_status == 'incomplete'
        assert env.recorder.transition_count == 0 and env.recorder.observation_count == 1
    finally:
        env.close()

    faults = {'advance_error_at': 3}
    input_v1, env, adapters, factory, scope = _fault_env(tmp_path / 'partial-step', faults)
    try:
        with scope(input_v1, factory):
            env.reset(seed=31)
        env.start_recording(tmp_path / 'partial-step.h5')
        with pytest.raises(RuntimeError, match='advance sentinel'):
            env.step(_action(env))
        adapter = adapters[0]
        assert adapter.advance_count == 3
        assert env.session._last_interval_advance_attempts == 3
        assert len(env.session._last_interval_advances) == 2
        failed_advance = adapter.operations.index({'op': 'advance_error_after_side_effect', 'index': 3})
        assert adapter.operations[failed_advance - 1:failed_advance + 1] == [
            {'op': 'advance', 'index': 3},
            {'op': 'advance_error_after_side_effect', 'index': 3},
        ]
        assert env.execution_fault.exception_type == 'RuntimeError'
        assert env.execution_fault.message == 'synthetic low-level advance sentinel'
        assert env.execution_fault.physical_progress == 'unknown'
        assert env.execution_fault.readback_error is not None
        assert env.recorder.transition_count == 0 and env.recorder.observation_count == 1
    finally:
        env.close()


def test_f03_publication_append_finalize_and_close_failures_are_visible(tmp_path):
    # A one-shot state publication read failure occurs after the complete five
    # low-level advances. Core catches it, retries readback for the fault
    # receipt, and does not publish a Recorder transition.
    faults = {'read_state_at_advance_count': 5}
    input_v1, env, adapters, factory, scope = _fault_env(tmp_path, faults)
    try:
        with scope(input_v1, factory):
            env.reset(seed=31)
        env.start_recording(tmp_path / 'publication-failure.h5')
        with pytest.raises(RuntimeError, match='readback sentinel'):
            env.step(_action(env))
        assert adapters[0].advance_count == 5
        assert env.execution_fault.phase == 'position_control_compute_apply_step'
        assert env.execution_fault.interval_completed is True
        assert env.execution_fault.message == 'synthetic low-level readback sentinel'
        assert env.recorder.transition_count == 0 and env.recorder.observation_count == 1
    finally:
        env.close()

    # Capacity failure is the real existing Recorder's pre-mutation guard.
    input_v1, env, adapters, factory, scope = _fault_env(tmp_path / 'append', {})
    try:
        with scope(input_v1, factory):
            env.reset(seed=31)
        env.start_recording(tmp_path / 'append-failure.h5')
        env.recorder.config = replace(env.recorder.config, max_buffer_bytes=env.recorder._bytes + 1)
        with pytest.raises(MemoryError, match='max_buffer_bytes'):
            env.step(_action(env))
        assert adapters[0].advance_count == 5
        assert env.execution_fault.phase == 'record_position_transition'
        assert env.execution_fault.interval_completed is True
        assert env.execution_fault.message == 'recording buffer exceeds max_buffer_bytes'
        assert env.recorder.transition_count == 0 and env.recorder.observation_count == 1
    finally:
        env.close()

    # Force the existing finalizer to fail during output creation, then make
    # low-level close fail too. close() must retain finalization as primary.
    faults = {'close_error': True}
    input_v1, env, adapters, factory, scope = _fault_env(tmp_path / 'finalize', faults)
    with scope(input_v1, factory):
        env.reset(seed=31)
    parent_file = tmp_path / 'not-a-directory'
    env.start_recording(parent_file / 'episode.h5')
    for _ in range(4):
        env.step(_action(env))
    parent_file.write_text('blocked parent', encoding='utf-8')
    with pytest.raises((FileExistsError, NotADirectoryError)) as caught:
        env.close()
    assert any(
        'RuntimeSession close after Position finalization also failed' in note
        and 'synthetic low-level close sentinel' in note
        for note in getattr(caught.value, '__notes__', ())
    )
    assert adapters[0].close_count == 1
    assert env._closed is True and env.recorder.frozen is not None
