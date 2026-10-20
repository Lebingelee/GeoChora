"""Provider-free S1 contracts for the Phase II D02a state boundary."""

from __future__ import annotations

import copy

import pytest

from task_env.artifacts import (
    ArticulationDefinition,
    AssetDefinition,
    CanonicalStateView,
    CanonicalStateViewV1,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    JointDefinition,
    NativeIntervalEvidence,
    NativeIntervalSample,
    NativeSignalValue,
    PoseWorld,
    SceneDefinition,
    StateBoundaryIdentity,
    StateFieldRequirement,
    StateRequirements,
    StateSampleClock,
    StateViewLifetime,
    TypedFrameStateValue,
    TypedJointStateValue,
    UnavailableStateValue,
    decode_canonical_state_view,
    project_canonical_state_v0,
)


IDENTITY = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
SCENE_HASH = "a" * 64


def _joint(kind="revolute", *, joint_id="joint1"):
    layouts = {
        "revolute": ("axis", (0.0, 0.0, 1.0), "radian", "radian_per_second", 1, 1),
        "prismatic": ("axis", (1.0, 0.0, 0.0), "meter", "meter_per_second", 1, 1),
        "spherical": (None, None, "quaternion_wxyz", "angular_xyz_radian_per_second", 4, 3),
        "floating": (
            None,
            None,
            "xyz_meter_quaternion_wxyz",
            "linear_xyz_meter_per_second_angular_xyz_radian_per_second",
            7,
            6,
        ),
    }
    axis, axis_value, pos, vel, pos_size, vel_size = layouts[kind]
    del axis
    return JointDefinition(
        "joint-definition-v1",
        joint_id,
        FrameReference("robot", "base"),
        FrameReference("robot", "link"),
        IDENTITY,
        IDENTITY,
        kind,
        axis_value,
        pos,
        vel,
        pos_size,
        vel_size,
    )


def _scene(definition=None):
    definition = definition or _joint()
    frames = tuple(
        FrameDefinition("frame-definition-v1", "robot", name, "runtime", None, None)
        for name in ("base", "link")
    )
    articulation = ArticulationDefinition(
        "articulation-definition-v1",
        "robot",
        "base",
        ("base", "link"),
        (definition,),
    )
    return SceneDefinition(
        "scene-definition-v2",
        "scene-v2",
        (AssetDefinition("asset-definition-v1", "robot", "v1", "procedural://test/robot"),),
        (EntityInstance("entity-instance-v1", "robot", "robot", "v1"),),
        frames,
        (articulation,),
    )


def _boundary(scene_hash=SCENE_HASH, *, control_step=0, state_revision=0):
    return StateBoundaryIdentity(
        "state-boundary-identity-v1",
        "episode-1",
        "reset-" + "b" * 64,
        scene_hash,
        "scene-instance-1",
        "mujoco-materialization-1",
        control_step,
        state_revision,
    )


def _clock(control_step=0, time_s=0.0):
    return StateSampleClock("state-sample-clock-v1", "evaluation_boundary", control_step, time_s)


def _scalar_state(definition=None):
    definition = definition or _joint()
    return TypedJointStateValue(
        "typed-joint-state-v1",
        "robot",
        definition.joint_id,
        definition.kind,
        definition.position_representation,
        (0.25,),
        definition.velocity_representation,
        (0.5,),
    )


def _requirement(field, *, requiredness="required", sample_domain="evaluation_boundary"):
    values = {
        "joint_position": ("joint", "joint1", "joint-definition", "joint_state_query", None),
        "joint_velocity": ("joint", "joint1", "joint-definition", "joint_state_query", None),
        "frame_pose_world": ("frame", "link", "meter+quaternion_wxyz", "frame_pose_query", None),
        "contact_force": ("entity", "contacts", "newton", "contact_detection", FrameReference("robot", "base")),
        "contact_impulse": ("entity", "contacts", "newton_second", "contact_impulse", FrameReference("robot", "base")),
        "actuator_force": ("actuator", "gripper", "newton", "actuator_force_query", None),
    }
    subject_kind, subject_id, unit, capability, frame = values[field]
    return StateFieldRequirement(
        "state-field-requirement-v1",
        field,
        subject_kind,
        "robot",
        subject_id,
        requiredness,
        sample_domain,
        unit,
        capability,
        frame,
    )


def test_typed_joint_state_uses_a02_layout_and_requires_multi_dof_velocity_frames():
    scalar = _joint("revolute")
    scalar_value = _scalar_state(scalar)
    scalar_value.validate_against(scalar)

    spherical = _joint("spherical", joint_id="wrist")
    spherical_value = TypedJointStateValue(
        "typed-joint-state-v1", "robot", "wrist", "spherical", "quaternion_wxyz",
        (1.0, 0.0, 0.0, 0.0), "angular_xyz_radian_per_second", (0.0, 0.0, 0.0),
        FrameReference("robot", "base"),
    )
    spherical_value.validate_against(spherical)

    floating = _joint("floating", joint_id="root")
    floating_value = TypedJointStateValue(
        "typed-joint-state-v1", "robot", "root", "floating", "xyz_meter_quaternion_wxyz",
        (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),
        "linear_xyz_meter_per_second_angular_xyz_radian_per_second",
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        FrameReference("robot", "base"), FrameReference("robot", "link"),
    )
    floating_value.validate_against(floating)

    with pytest.raises(ValueError, match="position/velocity dimensions"):
        TypedJointStateValue(
            "typed-joint-state-v1", "robot", "root", "floating", "xyz_meter_quaternion_wxyz",
            (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),
            "linear_xyz_meter_per_second_angular_xyz_radian_per_second", (0.0,) * 7,
            FrameReference("robot", "base"), FrameReference("robot", "link"),
        )
    with pytest.raises(ValueError, match="expression frame"):
        TypedJointStateValue(
            "typed-joint-state-v1", "robot", "wrist", "spherical", "quaternion_wxyz",
            (1.0, 0.0, 0.0, 0.0), "angular_xyz_radian_per_second", (0.0, 0.0, 0.0),
        )


def test_v1_boundary_identity_distinguishes_same_step_state_publications_and_entity_views_are_projections():
    first_boundary = _boundary(state_revision=4)
    second_boundary = _boundary(state_revision=5)
    assert first_boundary.control_step == second_boundary.control_step
    assert first_boundary.boundary_id != second_boundary.boundary_id

    joint = _scalar_state()
    frame = TypedFrameStateValue("typed-frame-state-v1", FrameReference("robot", "link"), IDENTITY)
    state = CanonicalStateViewV1(
        "canonical-state-v1", "SI_right_handed_z_up_wxyz", first_boundary, _clock(), (joint,), (frame,)
    )
    scene = _scene()
    matching_state = CanonicalStateViewV1(
        "canonical-state-v1", "SI_right_handed_z_up_wxyz",
        _boundary(scene.identity_hash, state_revision=4), _clock(), (joint,), (frame,),
    )
    matching_state.validate_against_scene(scene)
    assert state.joints_for_entity("robot")[0] is state.joints[0]
    assert state.frames_for_entity("robot")[0] is state.frames[0]
    assert "entities" not in state.to_mapping()
    assert CanonicalStateViewV1.from_mapping(state.to_mapping()) == state
    assert decode_canonical_state_view(state.to_mapping()) == state


def test_required_contact_never_defaults_to_zero_and_optional_absence_is_explicit():
    contact_unavailable = UnavailableStateValue(
        "unavailable-state-value-v1", "contact_force", "entity", "robot", "contacts",
        "evaluation_boundary", "provider did not admit contact_detection",
    )
    state = CanonicalStateViewV1(
        "canonical-state-v1", "SI_right_handed_z_up_wxyz", _boundary(), _clock(),
        (_scalar_state(),), (), (contact_unavailable,),
    )
    state.validate_requirements(StateRequirements(
        "state-requirements-v1", "controller", "grasp-controller",
        (_requirement("joint_position"), _requirement("contact_force", requiredness="optional")),
    ))
    with pytest.raises(ValueError, match="required state field unavailable"):
        state.validate_requirements(StateRequirements(
            "state-requirements-v1", "task", "contact-success",
            (_requirement("contact_force"),),
        ))

    silent_omission = CanonicalStateViewV1(
        "canonical-state-v1", "SI_right_handed_z_up_wxyz", _boundary(), _clock(),
        (_scalar_state(),), (), (),
    )
    with pytest.raises(ValueError, match="omitted without unavailable evidence"):
        silent_omission.validate_requirements(StateRequirements(
            "state-requirements-v1", "observation", "contact-observation",
            (_requirement("contact_force", requiredness="optional"),),
        ))
    with pytest.raises(ValueError, match="native interval requirements"):
        silent_omission.validate_requirements(StateRequirements(
            "state-requirements-v1", "task", "native-contact-guard",
            (_requirement("contact_impulse", sample_domain="native_step_interval"),),
        ))
    with pytest.raises(ValueError, match="native interval requirement is not supported"):
        _requirement("joint_velocity", sample_domain="native_step_interval")


def test_native_interval_evidence_keeps_real_half_open_steps_and_rejects_gaps():
    before = _boundary(control_step=2, state_revision=8)
    after = _boundary(control_step=3, state_revision=9)
    signal = NativeSignalValue(
        "native-signal-value-v1", "contact_impulse", "entity", "robot", "contacts",
        (0.0, 0.0, 0.02), "newton_second", FrameReference("robot", "base"),
    )
    force_unavailable = UnavailableStateValue(
        "unavailable-state-value-v1", "contact_force", "entity", "robot", "contacts",
        "native_step_interval", "provider does not publish a contact force signal",
    )
    samples = tuple(
        NativeIntervalSample(
            "native-interval-sample-v1", 24 + index, 0.04 + index * 0.002,
            0.042 + index * 0.002, (signal,), (force_unavailable,),
        )
        for index in range(5)
    )
    evidence = NativeIntervalEvidence(
        "native-interval-evidence-v1", "interval-2-3", before, after,
        _clock(2, 0.04), _clock(3, 0.05), 0.002, 5, 24, samples,
        "trajectory://episode-1/native/2",
    )
    assert len(evidence.samples) == 5
    assert evidence.samples[0].interval_start_s == 0.04
    assert evidence.samples[-1].interval_end_s == 0.05
    assert NativeIntervalEvidence.from_mapping(evidence.to_mapping()) == evidence
    evidence.validate_requirements(StateRequirements(
        "state-requirements-v1", "controller", "native-guard",
        (
            _requirement("contact_impulse", sample_domain="native_step_interval"),
            _requirement("contact_force", requiredness="optional", sample_domain="native_step_interval"),
        ),
    ))
    with pytest.raises(ValueError, match="required native state field unavailable"):
        evidence.validate_requirements(StateRequirements(
            "state-requirements-v1", "task", "native-contact-success",
            (_requirement("contact_force", sample_domain="native_step_interval"),),
        ))

    broken = list(samples)
    broken[2] = NativeIntervalSample(
        "native-interval-sample-v1", 26, 0.045, 0.047, (signal,)
    )
    with pytest.raises(ValueError, match="contiguous half-open physics intervals"):
        NativeIntervalEvidence(
            "native-interval-evidence-v1", "interval-2-3", before, after,
            _clock(2, 0.04), _clock(3, 0.05), 0.002, 5, 24, tuple(broken),
            "trajectory://episode-1/native/2",
        )


def test_provider_alias_lifetime_is_bounded_and_owned_snapshots_may_be_retained():
    boundary = _boundary(state_revision=5)
    snapshot_lifetime = StateViewLifetime(
        "state-view-lifetime-v1", "runtime-session-1", boundary, 5, "owned_snapshot", "retained"
    )
    alias_lifetime = StateViewLifetime(
        "state-view-lifetime-v1", "runtime-session-1", boundary, 5, "provider_alias", "next_mutation"
    )
    assert snapshot_lifetime.may_be_retained
    assert not alias_lifetime.may_be_retained
    with pytest.raises(ValueError, match="provider alias lifetime"):
        StateViewLifetime(
            "state-view-lifetime-v1", "runtime-session-1", boundary, 5, "provider_alias", "retained"
        )


def test_v0_projection_requires_explicit_scene_bindings_and_preserves_v0_mapping():
    definition = _joint()
    scene = _scene(definition)
    old = CanonicalStateView(
        "canonical-state-v0", "SI_right_handed_z_up_wxyz", 0, 0.0,
        {"legacy_joint": 0.25}, {"legacy_joint": 0.5}, {"legacy_base": IDENTITY},
    )
    old_mapping = copy.deepcopy(old.to_mapping())
    boundary = _boundary(scene.identity_hash)
    projected = project_canonical_state_v0(
        old,
        scene=scene,
        boundary=boundary,
        sample_clock=_clock(),
        joint_bindings={"legacy_joint": definition},
        frame_bindings={"legacy_base": FrameReference("robot", "base")},
    )
    assert projected.schema_version == "canonical-state-v1"
    assert projected.joints[0].joint_id == "joint1"
    assert projected.frames[0].frame == FrameReference("robot", "base")
    assert old.to_mapping() == old_mapping

    floating = _joint("floating", joint_id="root")
    floating_scene = _scene(floating)
    with pytest.raises(ValueError, match="cannot represent multi-DOF"):
        project_canonical_state_v0(
            old,
            scene=floating_scene,
            boundary=_boundary(floating_scene.identity_hash),
            sample_clock=_clock(),
            joint_bindings={"legacy_joint": floating},
            frame_bindings={"legacy_base": FrameReference("robot", "base")},
        )

    with pytest.raises(ValueError, match="exactly"):
        project_canonical_state_v0(
            old,
            scene=scene,
            boundary=boundary,
            sample_clock=_clock(),
            joint_bindings={},
            frame_bindings={"legacy_base": FrameReference("robot", "base")},
        )


def test_v0_decoder_remains_exact_and_unknown_schema_does_not_guess():
    old = CanonicalStateView(
        "canonical-state-v0", "SI_right_handed_z_up_wxyz", 0, 0.0, {}, {}, {}
    )
    assert decode_canonical_state_view(old.to_mapping()) == old
    assert CanonicalStateView.from_mapping(old.to_mapping()).to_mapping() == old.to_mapping()
    with pytest.raises(ValueError, match="unsupported canonical state schema"):
        decode_canonical_state_view({"schema_version": "canonical-state-v2"})

    typed = CanonicalStateViewV1(
        "canonical-state-v1", "SI_right_handed_z_up_wxyz", _boundary(), _clock(), (), ()
    )
    with pytest.raises(ValueError, match="unknown CanonicalStateViewV1 fields"):
        CanonicalStateViewV1.from_mapping({**typed.to_mapping(), "unreviewed_extension": True})
    with pytest.raises(ValueError, match="unsupported state schema"):
        CanonicalStateViewV1.from_mapping({**typed.to_mapping(), "schema_version": "canonical-state-v2"})
