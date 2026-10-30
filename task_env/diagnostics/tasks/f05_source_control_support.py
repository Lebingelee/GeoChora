"""F05-local source setup and bottom-I/O synthetic fixture for Core S1."""
from __future__ import annotations

from dataclasses import replace
import dataclasses
import importlib.util
import hashlib
from pathlib import Path
import subprocess
import sys

REPO = Path('/home/lly/Program_Files/Geochora')
BASE = REPO / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001'
PROVIDER = BASE / 'f05_geophys_provider/GeoPhys'
for _path in (REPO, PROVIDER / 'src'):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def build_input(family='menagerie-panda'):
    if family != 'menagerie-panda':
        raise ValueError('F05 synthetic Core S1 is restricted to the public-import-ready Menagerie USD cell')
    from task_env.artifacts import ExecutionSpecV1
    from task_env.assembly.usd_delivery import resolve_provider_representation
    from task_env.diagnostics.tasks.f04_candidate_s1_support import build_candidate
    from task_env.runtime.sessions.geophys_source import compile_geophys_usd_position_drive_receipt
    from task_env.runtime.sessions.leaf_control import GeoPhysHostModelProducerIdentityV1
    from task_env.tasks.position_candidate.builder import F05PositionCandidateInputV1
    from scene import import_scene_source

    accepted = build_candidate(family)
    old_source = accepted.runtime_source
    target_build_identity = 'geophys-a53a8cfed7c9d6464274b5c96fca601271dc4ee4'
    provisional_representation = resolve_provider_representation(
        old_source.scene_source.loaded_delivery,
        provider='geophys',
        provider_build_identity=target_build_identity,
        options={'f05_attempt': '002', 'lowering': 'public-host-model-s1-v1',
                 'producer_capture': 'pending'},
    )
    provisional_source = dataclasses.replace(
        old_source,
        scene_source=dataclasses.replace(old_source.scene_source, representation=provisional_representation),
    )
    execution = replace(
        accepted.execution,
        physics_provider='geophys', physics_backend='cpu',
        physics_profile='geophys-usd-position-f05-s1-v1',
        physics_device='cpu', determinism_mode='best_effort',
    )
    imported, model, bridge_id, mapping_report = lower_public_model(provisional_source)
    module_sources = {}
    source_root = (PROVIDER / 'src').resolve()
    for module_name, module in tuple(sys.modules.items()):
        raw_origin = getattr(module, '__file__', None)
        if not raw_origin:
            continue
        path = Path(raw_origin).resolve()
        try:
            path.relative_to(source_root)
        except ValueError:
            continue
        if path.is_file():
            module_sources[module_name] = (module_name, str(path), hashlib.sha256(path.read_bytes()).hexdigest())
    rows = tuple(sorted(module_sources.values(), key=lambda row: row[0]))
    producer_identity = GeoPhysHostModelProducerIdentityV1(
        'geophys-host-model-producer-identity-v1', target_build_identity,
        str(PROVIDER.resolve()),
        subprocess.check_output(['git', '-C', str(PROVIDER), 'remote', 'get-url', 'origin'], text=True).strip(),
        subprocess.check_output(['git', '-C', str(PROVIDER), 'rev-parse', 'HEAD'], text=True).strip(),
        not bool(subprocess.check_output(
            ['git', '-C', str(PROVIDER), 'status', '--porcelain=v1', '--untracked-files=all'], text=True,
        ).strip()),
        rows,
    )
    producer_identity.validate_current_tree()
    representation = resolve_provider_representation(
        old_source.scene_source.loaded_delivery,
        provider='geophys', provider_build_identity=target_build_identity,
        options={
            'f05_attempt': '002', 'lowering': 'public-host-model-s1-v1',
            'host_model_producer_identity_sha256': producer_identity.identity_sha256,
        },
    )
    source = dataclasses.replace(
        old_source,
        scene_source=dataclasses.replace(old_source.scene_source, representation=representation),
    )
    receipt = compile_geophys_usd_position_drive_receipt(
        source, imported, model, execution,
        provider_build_identity=representation.provider_build_identity,
        provenance_kind='synthetic_fixture',
        host_model_producer_identity=producer_identity,
    )
    setup = {
        'provider_source_root': str(PROVIDER.resolve()),
        'provider_source_head': subprocess.check_output(
            ['git', '-C', str(PROVIDER), 'rev-parse', 'HEAD'], text=True,
        ).strip(),
        'requested_target_build_identity': target_build_identity,
        'host_model_producer_identity': producer_identity.to_mapping(),
        'provider_tracked_worktree_clean': not bool(subprocess.check_output(
            ['git', '-C', str(PROVIDER), 'status', '--porcelain', '--untracked-files=no'], text=True,
        ).strip()),
        'scene_import_origin': importlib.util.find_spec('scene').origin,
        'geometry_import_origin': importlib.util.find_spec('geometry').origin,
        'bridge_id': bridge_id,
        'public_import_semantic_sha256': imported.ir.semantic_hash(),
        'public_import_source_graph_sha256': imported.source_graph_hash,
        'public_model_identity_sha256': receipt.public_model_identity_sha256,
        'public_model_counts': {
            'bodies': len(imported.ir.bodies),
            'geoms': int(model.joint_data.get('n_geoms', -1)),
            'dofs': int(model.joint_data.get('n_dof', -1)),
            'actuators': int(model.joint_data.get('n_actuators', -1)),
        },
        'mapping_report': mapping_report,
        'drive_receipt_identity_sha256': receipt.identity_sha256,
        'drive_count': len(receipt.drives),
    }
    candidate = F05PositionCandidateInputV1(
        'f05-position-candidate-input-v1', accepted.task_source, accepted.artifact,
        source, execution, accepted.reset_plan, accepted.kinematics_source_xml,
        accepted.kinematics_source_sha256, producer_identity, receipt,
    )
    candidate.validate()
    return candidate, setup


def build_native_input(family='menagerie-panda'):
    """Build the single frozen F05 native candidate without initializing GeoPhys."""
    if family != 'menagerie-panda':
        raise ValueError('F05 native candidate is restricted to the frozen Menagerie USD cell')
    from dataclasses import replace
    from task_env.assembly.usd_delivery import resolve_provider_representation
    from task_env.tasks.position_candidate.builder import F05NativePositionCandidateInputV1

    s1_input, setup = build_input(family)
    producer = s1_input.host_model_producer_identity
    execution = replace(
        s1_input.execution,
        physics_profile='geophys-usd-position-f05-native-v1',
    )
    representation = resolve_provider_representation(
        s1_input.runtime_source.scene_source.loaded_delivery,
        provider='geophys',
        provider_build_identity=producer.requested_target_build_identity,
        options={
            'f05_attempt': '003',
            'lowering': 'public-host-model-native-v1',
            'host_model_producer_identity_sha256': producer.identity_sha256,
            'actual_execution_build_identity': producer.actual_provider_build_identity,
        },
    )
    source = replace(
        s1_input.runtime_source,
        scene_source=replace(s1_input.runtime_source.scene_source, representation=representation),
    )
    native = F05NativePositionCandidateInputV1(
        'f05-native-position-candidate-input-v1',
        s1_input.task_source, s1_input.artifact, source, execution,
        s1_input.reset_plan, s1_input.kinematics_source_xml,
        s1_input.kinematics_source_sha256, producer,
    )
    native.validate()
    setup.update({
        'native_profile_id': execution.physics_profile,
        'requested_target_build_identity': producer.requested_target_build_identity,
        'actual_execution_build_identity': producer.actual_provider_build_identity,
        'native_representation_identity_sha256': representation.identity_hash,
        'native_execution_identity_sha256': execution.identity_hash,
    })
    return native, setup


def lower_public_model(source):
    from task_env.runtime.sessions.geophys_source import GeoPhysSourceComposer
    from scene import import_scene_source

    composer = GeoPhysSourceComposer(source)
    try:
        public_source, bridge_id = composer.build_scene_source(None, ())
        imported = import_scene_source(public_source, cache=False)
        model = composer.build_scene_model(imported, None)
        return imported, model, bridge_id, composer.usd_mapping_report
    finally:
        composer.close()


class SyntheticGeoPhysNativeIO:
    """Bottom NativeRuntimeIO fixture; public model drives are mapped, never stepped."""

    execution_provenance_kind = 'synthetic_fixture'

    def __init__(self, *, artifact, execution, source, drive_receipt, input_v1, faults=None):
        from task_env.runtime.sessions.native_io import NativeRuntimeIOMetadataV1
        from task_env.controllers.canonical.kinematics import (
            PANDA_HAND_ORIGIN_TCP_V1, PandaKinematics,
        )

        self.artifact, self.execution, self.source = artifact, execution, source
        self.drive_receipt = drive_receipt
        self.input_v1 = input_v1
        self.faults = dict(faults or {})
        self.model = PandaKinematics(input_v1.kinematics_source_xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1)
        self.native_dof_names = tuple(
            row.native_dof_name for row in sorted(drive_receipt.drives, key=lambda item: item.native_dof_index)
        )
        limits = {row.native_dof_name: (row.lower_limit, row.upper_limit) for row in drive_receipt.drives}
        self._metadata = NativeRuntimeIOMetadataV1(
            'native-runtime-io-metadata-v1', source.source_id, source.source_closure_digest,
            source.scene_definition.identity_hash, artifact.identity_hash, execution.identity_hash,
            'geophys', drive_receipt.provider_build_identity, 'cpu', 'cpu', 'best_effort',
            artifact.timebase.physics_dt, artifact.timebase.control_substeps,
            self.native_dof_names, limits,
            input_v1.host_model_producer_identity.identity_sha256,
        )
        self._semantic_by_native = {row.native_dof_name: f'{row.canonical_joint.entity_id}/{row.canonical_joint.joint_id}'
                                    for row in drive_receipt.drives}
        self.joints = {}
        self.free_pose = None
        self.time_s = 0.0
        self.native_index = 0
        self.advance_count = self.target_write_count = self.reset_count = 0
        self.read_state_count = 0
        self.close_count = 0
        self.target_history = []
        self.control_history = []
        self.operations = []

    def metadata(self):
        self.operations.append({'op': 'metadata', 'advance_count': self.advance_count})
        if self.faults.get('metadata_error'):
            raise RuntimeError('F05 synthetic low-level metadata sentinel')
        return self._metadata

    def write_reset(self, sample, position_targets):
        from task_env.runtime.sessions.native_io import NativeResetWriteReceiptV1
        self.reset_count += 1
        self.joints = dict(sample.joint_position)
        self.free_pose = sample.poses_world['square-peg-instance/peg1']
        self.time_s = 0.0
        self.native_index = 0
        controls = self.drive_receipt.control_inputs(tuple(position_targets))
        self.control_history.append({'phase': 'reset', 'controls': [list(row) for row in controls]})
        self.target_history.append({'phase': 'reset', 'targets': [list(row) for row in position_targets]})
        names = tuple(name for _index, name, _value in position_targets)
        self.operations.append({'op': 'write_reset', 'reset_count': self.reset_count})
        return NativeResetWriteReceiptV1(
            'native-reset-write-receipt-v1', sample.sample_id,
            tuple(sorted(self.source.joints)), tuple(sorted(self.source.free_joints)),
            names, True, bool(self.faults.get('partial_reset')),
        )

    def read_state(self):
        from task_env.artifacts import FrameReference, PoseWorld
        from task_env.runtime.sessions.free_joint_state import PublicRigidBodyReadbackV1
        from task_env.runtime.sessions.native_io import NativeRuntimeReadbackV1

        self.read_state_count += 1
        self.operations.append({'op': 'read_state_attempt', 'count': self.read_state_count})
        if self.faults.get('read_state_error_at') == self.read_state_count:
            raise RuntimeError('F05 synthetic low-level state-read sentinel')
        arm = [self.joints[f'panda-main/joint{index}'] for index in range(1, 8)]
        hand_pose = self.model.pose(arm)
        frames = {}
        for canonical in (*self.source.bodies, *self.source.frames):
            if canonical == 'panda-main/hand':
                frames[canonical] = hand_pose
            elif canonical == 'square-peg-instance/peg1':
                frames[canonical] = self.free_pose
            else:
                frames[canonical] = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
        free = {
            semantic: PublicRigidBodyReadbackV1(
                'public-rigid-body-readback-v1',
                self.artifact.legacy_frame_bindings[semantic],
                self.free_pose.position, self.free_pose.quaternion_wxyz,
                (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0),
                'world', 'center_of_mass',
            ) for semantic in self.source.free_joints
        }
        self.operations.append({'op': 'read_state', 'advance_count': self.advance_count})
        return NativeRuntimeReadbackV1(
            'native-runtime-readback-v1', self.joints,
            {name: 0.0 for name in self.source.joints}, frames, free, self.time_s,
        )

    def write_position_targets(self, target_identity_sha256, targets):
        from task_env.runtime.sessions.native_io import NativePositionWriteAckV1
        self.target_write_count += 1
        targets = tuple(targets)
        controls = self.drive_receipt.control_inputs(targets)
        self.target_history.append({'phase': 'step', 'targets': [list(row) for row in targets]})
        self.control_history.append({'phase': 'step', 'controls': [list(row) for row in controls]})
        self.operations.append({'op': 'write_position_targets', 'count': self.target_write_count})
        if self.faults.get('prewrite_error'):
            raise RuntimeError('F05 synthetic low-level prewrite sentinel')
        if self.faults.get('missing_ack'):
            return None
        for _index, native, value in targets:
            self.joints[self._semantic_by_native[native]] = float(value)
        names = tuple(name for _index, name, _value in targets)
        values = tuple(float(value) for _index, _name, value in targets)
        return NativePositionWriteAckV1(
            'native-position-write-ack-v1', target_identity_sha256,
            names, values, bool(self.faults.get('partial_apply')), len(targets),
        )

    def advance(self):
        from task_env.runtime.sessions.native_io import NativeAdvanceReceiptV1
        self.advance_count += 1
        self.native_index += 1
        self.time_s = self.native_index * self.artifact.timebase.physics_dt
        self.operations.append({'op': 'advance', 'index': self.native_index})
        if self.faults.get('advance_error_at') == self.native_index:
            raise RuntimeError('F05 synthetic low-level advance sentinel')
        return NativeAdvanceReceiptV1(
            'native-advance-receipt-v1', 1, self.native_index, self.time_s,
        )

    def close(self):
        self.close_count += 1
        self.operations.append({'op': 'close', 'count': self.close_count})
        if self.faults.get('close_error'):
            raise RuntimeError('F05 synthetic low-level close sentinel')
