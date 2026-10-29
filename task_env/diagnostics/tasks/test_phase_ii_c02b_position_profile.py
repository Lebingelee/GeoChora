"""S1 contracts for the force-free C02b Panda position profile."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import hashlib
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from task_env.artifacts import (
    CanonicalStatePublicationV1,
    CanonicalStateViewV1,
    FrameReference,
    PoseWorld,
    StateBoundaryIdentity,
    StateSampleClock,
    StateViewLifetime,
    Timebase,
    TypedFrameStateValue,
    TypedJointStateValue,
)
from task_env.controllers.canonical.contracts import (
    AppliedCanonicalControl,
    ControlGroupActionV1,
    StructuredActionRequestV1,
)
from task_env.controllers.canonical.kinematics import PANDA_HAND_ORIGIN_TCP_V1, PandaKinematics
from task_env.controllers.canonical.position_profile import (
    PandaPositionServoProfileV1,
)
from task_env.diagnostics.tasks.test_phase_ii_d01a_scene_materialization import (
    _a05_scene,
    _artifact_and_sample,
    _source_input,
)
from task_env.diagnostics.tasks.test_phase_ii_d01b_vnext_materialization import _task_source
from task_env.environment import TaskSourceV1, compile_task_artifact_v1, sample_episode_reset_plan
from task_env.runtime.sessions.source import project_scene_definition_v3_to_mjcf
from task_env.runtime.sessions.control import (
    apply_position_control_target,
    compile_control_binding_plan,
    execute_position_control_interval,
)


def _candidate(scene, tmp_path):
    legacy, _ = _artifact_and_sample(scene)
    legacy = replace(
        legacy,
        artifact_id='phase-ii-c02b-position-servo-v1',
        task_id='phase-ii-c02b-position-servo',
        artifact_version='candidate-v1',
        timebase=Timebase(0.002, 5, 0.01),
    )
    declared_source = replace(
        _task_source(scene), task_id=legacy.task_id, version=legacy.artifact_version,
    )
    artifact = compile_task_artifact_v1(declared_source, scene, legacy)
    reset_plan = sample_episode_reset_plan(
        declared_source, scene, artifact, task_seed=31,
    )
    source, imported, closure_digest, panda_digest, file_count = _source_input(
        pytest.importorskip('scene'), tmp_path, scene, legacy,
    )
    assert imported is not None and len(panda_digest) == 64 and len(closure_digest) == 64
    config = replace(
        source.config,
        runtime=replace(source.config.runtime, control_substeps=5),
    )
    source = replace(
        source,
        task_artifact_hash=artifact.identity_hash,
        joint_targets={f'panda-main/joint{i}': f'actuator{i}' for i in range(1, 8)},
        open_actuators=('actuator8',),
        config=config,
        source_closure_digest=closure_digest,
    )
    return declared_source, artifact, reset_plan, source, file_count


def _typed_publication(scene, reset_plan, *, step=0, state_revision=None):
    sample = reset_plan.reset_sample
    revision = step if state_revision is None else state_revision
    boundary = StateBoundaryIdentity(
        'state-boundary-identity-v1', 'episode-c02b-s1', sample.sample_id,
        scene.identity_hash, 'scene-instance-c02b-s1', 'mujoco-materialization-c02b-s1',
        step, revision,
    )
    clock = StateSampleClock(
        'state-sample-clock-v1', 'evaluation_boundary', step, step * 0.01,
    )
    joints = []
    for articulation in scene.articulations or ():
        for definition in articulation.joints:
            if definition.kind == 'fixed':
                continue
            semantic = f'{articulation.entity_id}/{definition.joint_id}'
            coordinate = float(sample.joint_position[semantic])
            joints.append(TypedJointStateValue(
                'typed-joint-state-v1', articulation.entity_id, definition.joint_id,
                definition.kind, definition.position_representation, (coordinate,),
                definition.velocity_representation, (0.0,),
            ))
    frames = tuple(TypedFrameStateValue(
        'typed-frame-state-v1', FrameReference(frame.entity_id, frame.frame_id),
        PoseWorld((0.35, 0.0, 0.45), (1.0, 0.0, 0.0, 0.0)),
    ) for frame in scene.frames or () if frame.frame_kind == 'runtime')
    view = CanonicalStateViewV1(
        'canonical-state-v1', 'SI_right_handed_z_up_wxyz', boundary, clock,
        tuple(joints), frames, (),
    )
    lifetime = StateViewLifetime(
        'state-view-lifetime-v1', boundary.provider_materialization_id,
        boundary, revision, 'owned_snapshot', 'retained',
    )
    return CanonicalStatePublicationV1(
        'canonical-state-publication-v1', view, lifetime,
    )


def _bindings(scene, source):
    joints = {
        f'{articulation.entity_id}/{joint.joint_id}': joint
        for articulation in scene.articulations or ()
        for joint in articulation.joints
        if joint.kind != 'fixed'
    }
    frames = {
        f'{item.entity_id}/{item.frame_id}': FrameReference(item.entity_id, item.frame_id)
        for item in scene.frames or () if item.frame_kind == 'runtime'
    }
    assert set(joints) == set(source.joints)
    return joints, frames


def _request(plan, *, arm=(0.35, 0.0, 0.45, 1.0, 0.0, 0.0, 0.0), gripper=(1.0,)):
    schema = plan.controller_bindings[0].action_schema
    return StructuredActionRequestV1(
        'structured-action-request-v1', plan.scene_identity_hash, plan.identity_hash,
        (
            ControlGroupActionV1('control-group-action-v1', 'panda-main', 'arm', schema.schema_id, tuple(arm)),
            ControlGroupActionV1('control-group-action-v1', 'panda-main', 'gripper', schema.schema_id, tuple(gripper)),
        ),
    )


class _PositionSessionProbe:
    def __init__(self, publication, *, profile, plan, scene, reset_plan):
        self.publication = publication
        self.scene = scene
        self.reset_plan = reset_plan
        self._position_profile_identity = profile.identity
        self._position_profile_id = profile.profile_id
        self._position_writer_id = profile.writer_id
        self._position_binding_identity_hash = plan.identity_hash
        self._position_source_closure_digest = profile.source.source_closure_digest
        self._position_applied_boundary_ids = set()
        self._force_feedback_required = False
        self.apply_calls = []
        self.snapshot_v1_calls = 0
        self.step_calls = 0
        self.native_steps = 0

    def snapshot_v1(self, **_kwargs):
        self.snapshot_v1_calls += 1
        return self.publication

    def apply_control(self, target):
        self.apply_calls.append(target)
        return AppliedCanonicalControl(
            'applied-canonical-control-v0', target.identity_hash, 'mujoco',
            dict(target.arm_servo_position), target.gripper.servo_opening_m,
            target.gripper.force_limit_N, False, 's1-session-probe',
        )

    def step(self):
        self.step_calls += 1
        self.native_steps += 5
        old = self.publication
        self.publication = _typed_publication(
            self.scene, self.reset_plan, step=old.view.boundary.control_step + 1,
            state_revision=old.view.boundary.state_revision + 1,
        )
        return SimpleNamespace(control_step=self.publication.view.boundary.control_step)


def test_position_profile_binds_hand_origin_tcp_a05_mapping_and_100hz_candidate(tmp_path):
    scene = _a05_scene()
    _declared_source, artifact, reset_plan, source, _file_count = _candidate(scene, tmp_path)
    profile = PandaPositionServoProfileV1.from_source(artifact, source)
    plan = compile_control_binding_plan(scene, (profile.controller_binding(),))

    root = ET.fromstring(source.scene_source.xml)
    hand = root.find(".//body[@name='hand']")
    assert hand is not None
    assert hand.find("site[@name='nutassembly_ee_site']") is None
    materialized_xml = project_scene_definition_v3_to_mjcf(
        source.scene_source.xml, scene,
    )
    actual = PandaKinematics(materialized_xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1)
    assert actual.tcp_profile == PANDA_HAND_ORIGIN_TCP_V1
    assert actual.fk_jacobian(np.zeros(7))[0].shape == (4, 4)
    assert profile.model.source_sha256 == actual.source_sha256

    assert artifact.timebase.physics_dt == 0.002
    assert artifact.timebase.control_substeps == 5
    assert artifact.timebase.control_dt == 0.01
    assert reset_plan.reset_sample.task_artifact_hash == artifact.identity_hash
    assert plan.resource_writers == tuple(
        ('panda-main', f'actuator{i}', profile.writer_id) for i in range(1, 9)
    )
    assert source.joint_targets == {
        f'panda-main/joint{i}': f'actuator{i}' for i in range(1, 8)
    }
    assert source.open_actuators == ('actuator8',)
    requirements = profile.requirements.requirements
    assert len(requirements) == 10
    assert {item.required_capability for item in requirements} == {
        'joint_state_query', 'frame_pose_query',
    }
    assert not any(item.field_name == 'actuator_force' for item in requirements)


def test_typed_hand_and_joint_state_adapt_to_canonical_controller_inputs(tmp_path):
    scene = _a05_scene()
    _declared_source, artifact, reset_plan, source, _ = _candidate(scene, tmp_path)
    profile = PandaPositionServoProfileV1.from_source(artifact, source)
    plan = compile_control_binding_plan(scene, (profile.controller_binding(),))
    publication = _typed_publication(scene, reset_plan)
    profile.reset(publication, plan)
    requested = profile.controller_binding().action_schema
    action = _request(plan)
    from task_env.runtime.sessions.control import prepare_structured_action
    _, request = prepare_structured_action(plan, action)[0]
    _canonical, target = profile.compute(publication, request, plan)
    assert target.target.gripper.semantic_id == 'panda-main/gripper'
    assert target.target.controller_identity == profile.identity
    assert target.source_boundary.boundary_id == publication.view.boundary.boundary_id
    assert target.sample_clock == publication.view.sample_clock
    assert target.binding_identity_hash == plan.identity_hash
    assert target.target.gripper.force_limit_N == profile.config.gripper_default_force_N
    assert requested.schema_id == plan.controller_bindings[0].action_schema.schema_id


def test_structured_position_preflight_then_single_writer_apply_and_five_step_interval(tmp_path):
    scene = _a05_scene()
    _declared_source, artifact, reset_plan, source, _ = _candidate(scene, tmp_path)
    profile = PandaPositionServoProfileV1.from_source(artifact, source)
    plan = compile_control_binding_plan(scene, (profile.controller_binding(),))
    publication = _typed_publication(scene, reset_plan)
    profile.reset(publication, plan)
    joints, frames = _bindings(scene, source)
    session = _PositionSessionProbe(
        publication, profile=profile, plan=plan, scene=scene, reset_plan=reset_plan,
    )

    _canonical, target, applied, state, next_publication = execute_position_control_interval(
        session, profile, plan, _request(plan), publication,
        scene=scene, joint_bindings=joints, frame_bindings=frames,
    )
    assert len(session.apply_calls) == 1
    assert applied.target_hash == target.target.identity_hash
    assert session.step_calls == 1 and session.native_steps == 5
    assert state.control_step == 1
    assert next_publication.view.boundary.control_step == 1
    assert session._force_feedback_required is False


@pytest.mark.parametrize("provider", ("geophys", "mujoco"))
def test_position_candidate_admission_binds_profile_and_disables_force_cache(
    provider, monkeypatch, tmp_path,
):
    from task_env.artifacts import ExecutionSpec
    from task_env.runtime.sessions import control as control_sessions
    from task_env.runtime.sessions.control import ControlBinding, materialize_control

    scene = _a05_scene()
    _declared_source, artifact, _reset_plan, source, _ = _candidate(scene, tmp_path)
    profile = PandaPositionServoProfileV1.from_source(artifact, source)
    plan = compile_control_binding_plan(scene, (profile.controller_binding(),))
    session = SimpleNamespace()
    calls = []

    def materialize_probe(*args, **kwargs):
        calls.append((args, kwargs))
        return session

    monkeypatch.setattr(control_sessions, 'materialize', materialize_probe)
    admitted = materialize_control(
        artifact,
        ExecutionSpec(provider, 'p1_2_scalar_cpu_v0', 'none', 'cpu', 0, 'strict'),
        source=source,
        binding=ControlBinding('panda-main/gripper', 0.08),
        controller_binding_plan=plan,
        controller_profile=profile,
    )
    assert admitted is session
    assert len(calls) == 1
    assert admitted._position_profile_identity == profile.identity
    assert admitted._position_binding_identity_hash == plan.identity_hash
    assert admitted._force_feedback_required is False

    bad_joint_binding = replace(
        source,
        joints={**source.joints, 'panda-main/joint7': 'joint6'},
    )
    with pytest.raises(ValueError, match='RuntimeSource identity or bindings changed'):
        materialize_control(
            artifact,
            ExecutionSpec(provider, 'p1_2_scalar_cpu_v0', 'none', 'cpu', 0, 'strict'),
            source=bad_joint_binding,
            binding=ControlBinding('panda-main/gripper', 0.08),
            controller_binding_plan=plan,
            controller_profile=profile,
        )
    assert len(calls) == 1

    bad_source = replace(
        source,
        joint_targets={**source.joint_targets, 'panda-main/joint7': 'actuator8'},
    )
    with pytest.raises(ValueError, match='RuntimeSource identity or bindings changed'):
        materialize_control(
            artifact,
            ExecutionSpec(provider, 'p1_2_scalar_cpu_v0', 'none', 'cpu', 0, 'strict'),
            source=bad_source,
            binding=ControlBinding('panda-main/gripper', 0.08),
            controller_binding_plan=plan,
            controller_profile=profile,
        )
    assert len(calls) == 1


def test_invalid_groups_wrong_identity_and_duplicate_or_stale_targets_reject_before_extra_write(tmp_path):
    scene = _a05_scene()
    _declared_source, artifact, reset_plan, source, _ = _candidate(scene, tmp_path)
    profile = PandaPositionServoProfileV1.from_source(artifact, source)
    plan = compile_control_binding_plan(scene, (profile.controller_binding(),))
    publication = _typed_publication(scene, reset_plan)
    profile.reset(publication, plan)
    joints, frames = _bindings(scene, source)
    session = _PositionSessionProbe(
        publication, profile=profile, plan=plan, scene=scene, reset_plan=reset_plan,
    )

    malformed = replace(_request(plan), groups=(_request(plan).groups[0],))
    with pytest.raises(ValueError, match='every bound ControlGroup'):
        execute_position_control_interval(
            session, profile, plan, malformed, publication, scene=scene,
            joint_bindings=joints, frame_bindings=frames,
        )
    assert session.apply_calls == [] and session.step_calls == 0
    assert profile._next_control_step == 0

    wrong_plan_identity = replace(_request(plan), binding_identity_hash='0' * 64)
    with pytest.raises(ValueError, match='binding identity'):
        execute_position_control_interval(
            session, profile, plan, wrong_plan_identity, publication, scene=scene,
            joint_bindings=joints, frame_bindings=frames,
        )
    assert session.apply_calls == [] and session.step_calls == 0
    assert profile._next_control_step == 0

    from task_env.runtime.sessions.control import prepare_structured_action
    _, requested = prepare_structured_action(plan, _request(plan))[0]
    _canonical, target = profile.compute(publication, requested, plan)
    from task_env.runtime.sessions.control import validate_target
    session._require_reset = lambda: None
    session._control_binding = object()
    session._artifact = artifact
    session._target_actuators = {name: index for index, name in enumerate(target.target.arm_joint_order)}
    with pytest.raises(ValueError, match='source-bound boundary validation'):
        validate_target(session, target.target)
    wrong_writer = replace(target, writer_id='panda-main/other-writer')
    with pytest.raises(ValueError, match='writer/Profile/plan/source boundary'):
        apply_position_control_target(
            session, wrong_writer, controller_profile=profile, plan=plan,
            publication=publication, scene=scene, joint_bindings=joints,
            frame_bindings=frames,
        )
    assert session.apply_calls == []

    apply_position_control_target(
        session, target, controller_profile=profile, plan=plan,
        publication=publication, scene=scene, joint_bindings=joints,
        frame_bindings=frames,
    )
    with pytest.raises(ValueError, match='already applied'):
        apply_position_control_target(
            session, target, controller_profile=profile, plan=plan,
            publication=publication, scene=scene, joint_bindings=joints,
            frame_bindings=frames,
        )
    assert len(session.apply_calls) == 1

    session.publication = _typed_publication(scene, reset_plan, step=1, state_revision=1)
    with pytest.raises(ValueError, match='stale for the RuntimeSession'):
        apply_position_control_target(
            session, target, controller_profile=profile, plan=plan,
            publication=publication, scene=scene, joint_bindings=joints,
            frame_bindings=frames,
        )
    assert len(session.apply_calls) == 1


def test_mujoco_position_policy_skips_force_copy_and_geo_feedback_query(monkeypatch):
    from task_env.runtime.sessions.mujoco import _MuJoCoSession
    from task_env.runtime.sessions.geophys import _GeoPhysSession

    class ForceCopySentinel:
        def __init__(self):
            self.copy_calls = 0

        def copy(self):
            self.copy_calls += 1
            raise AssertionError('position profile read/copy actuator_force')

    sentinel = ForceCopySentinel()
    mujoco = object.__new__(_MuJoCoSession)
    mujoco._force_feedback_required = False
    mujoco._closed = False
    mujoco._reset_done = False
    mujoco._reset_plan_gate_required = False
    mujoco._reset_plan_gate_open = False
    mujoco._control_step = 0
    mujoco._state_revision = 0
    mujoco._artifact = SimpleNamespace(timebase=SimpleNamespace(control_substeps=5, physics_dt=0.002))
    mujoco._model = object()
    mujoco._data = SimpleNamespace(
        qpos=np.zeros(0), qvel=np.zeros(0), act=np.zeros(0), ctrl=np.zeros(1),
        actuator_force=sentinel,
    )
    mj_steps = []
    mj_forward_calls = []
    mujoco._mj = SimpleNamespace(
        mj_resetData=lambda *_args: None,
        mj_forward=lambda *_args: mj_forward_calls.append(True),
        mj_step=lambda *_args: mj_steps.append(True),
    )
    mujoco._target_actuators = {}
    mujoco._open_actuators = ()
    mujoco._source = SimpleNamespace(open_actuators=('actuator8',), fixed_attachment_plan=None)
    mujoco._episode_id = 'episode-position-sentinel'
    mujoco._reset_sample_id = 'reset-position-sentinel'
    mujoco._native_steps = 0
    mujoco._force_sample_sequence = 0
    mujoco._force_configuration_revision = 0
    mujoco._control_binding = object()
    mujoco._begin_reset = lambda: None
    mujoco._validate_sample = lambda _sample: None
    mujoco._realized = lambda _sample: (setattr(mujoco, '_reset_done', True) or 'reset')
    mujoco.snapshot = lambda: 'state'

    sample = SimpleNamespace(joint_position={}, poses_world={})
    assert mujoco.reset(sample) == 'reset'
    assert mujoco.step() == 'state'
    assert len(mj_steps) == 5
    assert len(mj_forward_calls) == 2
    assert sentinel.copy_calls == 0
    with pytest.raises(ValueError, match='not admitted'):
        mujoco.control_feedback('state')
    assert sentinel.copy_calls == 0

    # Legacy no-plan force-aware sessions still retain the cache by default.
    mujoco._force_feedback_required = True
    mujoco._open_actuators = (0,)
    mujoco._data.actuator_force = np.array([2.0])
    mujoco._cache_completed_actuator_force()
    assert mujoco._completed_actuator_force.tolist() == [2.0]

    geo = object.__new__(_GeoPhysSession)
    geo._closed = False
    geo._reset_done = True
    geo._reset_plan_gate_required = False
    geo._reset_plan_gate_open = False
    geo._force_feedback_required = False
    geo._control_binding = object()
    geo._boundary = SimpleNamespace(read_snapshot=lambda *_args, **_kwargs: pytest.fail('force query issued'))
    with pytest.raises(ValueError, match='not admitted'):
        geo.control_feedback('state')


def test_selected_reference_position_interval_uses_existing_fault_latch(monkeypatch, tmp_path):
    from types import MethodType
    from task_env.tasks.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions import control as control_sessions

    scene = _a05_scene()
    _declared_source, artifact, _reset_plan, _source, _ = _candidate(scene, tmp_path)
    before = SimpleNamespace(control_step=0, simulation_time=0.0)
    selected = SimpleNamespace(
        _execution_fault=None,
        _stopped=False,
        horizon=10,
        position_profile=True,
        session=SimpleNamespace(snapshot=lambda: before),
        controller=object(),
        position_plan=object(),
        typed_state=object(),
        position_scene=scene,
        position_joint_bindings={},
        position_frame_bindings={},
        state=before,
        artifact=artifact,
        recorder=None,
    )
    selected._latch_fault = MethodType(SelectedReferenceEnv._latch_fault, selected)
    selected._recording_counts = SelectedReferenceEnv._recording_counts
    selected._fault_transition_status = MethodType(
        SelectedReferenceEnv._fault_transition_status.__func__, selected,
    )

    def fail_after_dispatch_start(*_args, **_kwargs):
        raise RuntimeError('injected position interval failure')

    monkeypatch.setattr(control_sessions, 'execute_position_control_interval', fail_after_dispatch_start)
    with pytest.raises(RuntimeError, match='injected position interval failure'):
        SelectedReferenceEnv._step_position_profile(selected, object())
    assert selected._execution_fault is not None
    assert selected._execution_fault.phase == 'position_control_compute_apply_step'
    assert selected._stopped is True


def test_selected_position_profile_rejects_legacy_action_before_mode_mutation():
    from task_env.tasks.reference_env import SelectedReferenceEnv

    selected = SimpleNamespace(
        _closed=False,
        _execution_fault=None,
        binding=SimpleNamespace(external_actions=True),
        _episode_mode=None,
        position_profile=True,
        position_plan=object(),
        _stopped=False,
        session=object(),
        state=SimpleNamespace(control_step=0),
        horizon=10,
    )
    with pytest.raises(TypeError, match='requires a StructuredActionRequestV1'):
        SelectedReferenceEnv.step(selected, np.zeros(8))
    assert selected._episode_mode is None
