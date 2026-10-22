"""C02b-R1 typed raw force contracts and one bounded native execution."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from task_env.artifacts import (
    CanonicalStatePublicationV2,
    CanonicalStateViewV1,
    CanonicalStateViewV2,
    CapabilityAdmissionError,
    ExecutionSpec,
    FrameReference,
    StateBoundaryIdentity,
    StateFieldRequirement,
    StateRequirements,
    StateSampleClock,
    StateViewLifetime,
    TypedActuatorForceStateValue,
    UnavailableStateValue,
    decode_canonical_state_publication,
    decode_canonical_state_view,
)
from task_env.controllers.canonical.contracts import (
    ControlGroupActionV1,
    StructuredActionRequestV1,
)
from task_env.controllers.canonical.kinematics import (
    PANDA_HAND_ORIGIN_TCP_V1,
    PandaKinematics,
)
from task_env.controllers.canonical.production import ProductionCanonicalPandaController
from task_env.diagnostics.tasks.c02b_r1_force_candidate import build_r1_force_candidate
from task_env.diagnostics.tasks.test_phase_ii_d02a_state_contracts import (
    IDENTITY,
    _boundary,
    _clock,
    _scalar_state,
)
from task_env.runtime.sessions import control as control_sessions
from task_env.runtime.sessions import api as session_api
from task_env.runtime.sessions.api import provider_manifest
from task_env.runtime.sessions.control import (
    ControlBinding,
    _c02b_r1_force_capability_manifest,
    execute_plan_bound_r1_control_interval,
    materialize_control,
)


def _force_requirement(*, unit="N"):
    return StateFieldRequirement(
        "state-field-requirement-v1", "actuator_force", "actuator", "robot", "gripper",
        "required", "evaluation_boundary", unit, "actuator_force_query",
    )


def _requirements(*, unit="N"):
    return StateRequirements(
        "state-requirements-v1", "controller", "r1-test", (_force_requirement(unit=unit),),
    )


def _force(boundary=None, **changes):
    boundary = boundary or _boundary()
    values = {
        "schema_version": "typed-actuator-force-state-v1",
        "entity_id": "robot",
        "actuator_id": "gripper",
        "unit": "N",
        "signed_value": 4.0,
        "actuator_control_value": 1.0,
        "valid": True,
        "invalid_reason": None,
        "source_generation": 1,
        "sample_sequence": 3,
        "source_state_revision": 11,
        "configuration_revision": 0,
        "source_closure_digest": "c" * 64,
        "provider_materialization_id": boundary.provider_materialization_id,
        "sample_phase": "reset_forward",
        "native_step_index": 0,
        "native_step_dt_s": 0.002,
        "native_sample_time_s": 0.0,
        "episode_id": boundary.episode_id,
        "reset_sample_id": boundary.reset_sample_id,
        "evaluation_boundary_id": boundary.boundary_id,
        "evaluation_control_step": boundary.control_step,
        "evaluation_simulation_time_s": 0.0,
    }
    values.update(changes)
    return TypedActuatorForceStateValue(**values)


def _view(force=None, *, boundary=None, unavailable=()):
    boundary = boundary or _boundary()
    return CanonicalStateViewV2(
        "canonical-state-v2", "SI_right_handed_z_up_wxyz", boundary, _clock(),
        (), (), () if force is None else (force,), tuple(unavailable),
    )


def _candidate_bindings(scene, source):
    joints = {
        f"{articulation.entity_id}/{joint.joint_id}": joint
        for articulation in scene.articulations or ()
        for joint in articulation.joints
        if joint.kind != "fixed"
    }
    frames = {
        f"{item.entity_id}/{item.frame_id}": FrameReference(item.entity_id, item.frame_id)
        for item in scene.frames or () if item.frame_kind == "runtime"
    }
    assert set(joints) == set(source.joints)
    return joints, frames


def test_c02b_r1_v2_typed_force_is_bound_validated_and_fail_closed():
    boundary = _boundary()
    force = _force(boundary)
    view = _view(force, boundary=boundary)
    view.validate_requirements(_requirements())
    assert decode_canonical_state_view(view.to_mapping()) == view

    lifetime = StateViewLifetime(
        "state-view-lifetime-v1", boundary.provider_materialization_id,
        boundary, boundary.state_revision, "owned_snapshot", "retained",
    )
    publication = CanonicalStatePublicationV2(
        "canonical-state-publication-v2", view, lifetime,
    )
    assert decode_canonical_state_publication(publication.to_mapping()) == publication
    with pytest.raises(ValueError, match="unsupported canonical state schema"):
        decode_canonical_state_view({"schema_version": "canonical-state-v9"})

    missing = _view(unavailable=(
        UnavailableStateValue(
            "unavailable-state-value-v1", "actuator_force", "actuator", "robot", "gripper",
            "evaluation_boundary", "Provider has no admitted raw-force publication",
        ),
    ))
    with pytest.raises(ValueError, match="required state field unavailable"):
        missing.validate_requirements(_requirements())

    invalid = _force(
        boundary, signed_value=None, actuator_control_value=None, valid=False,
        invalid_reason="provider sample invalid",
    )
    with pytest.raises(ValueError, match="required state field invalid"):
        _view(invalid).validate_requirements(_requirements())

    unsupported_phase = _force(boundary, sample_phase="state_restore_forward")
    with pytest.raises(ValueError, match="does not support this sample phase"):
        _view(unsupported_phase).validate_requirements(_requirements())

    with pytest.raises(ValueError, match="does not match its typed state boundary"):
        _view(_force(boundary, episode_id="episode-stale"), boundary=boundary)
    with pytest.raises(ValueError, match="does not match its typed state boundary"):
        _view(_force(boundary, provider_materialization_id="geophys-materialization-stale"), boundary=boundary)
    with pytest.raises(ValueError, match="finite"):
        _force(boundary, signed_value=float("nan"))
    with pytest.raises(ValueError, match="published sample sequence"):
        _force(boundary, sample_sequence=0)
    with pytest.raises(ValueError, match="unit disagrees"):
        _view(force).validate_requirements(_requirements(unit="newton"))


def test_c02b_r1_old_state_v1_mapping_and_hash_remain_unchanged():
    from task_env.artifacts import FrameReference, TypedFrameStateValue

    state = CanonicalStateViewV1(
        "canonical-state-v1", "SI_right_handed_z_up_wxyz", _boundary(), _clock(),
        (_scalar_state(),),
        (TypedFrameStateValue("typed-frame-state-v1", FrameReference("robot", "link"), IDENTITY),),
        (),
    )
    assert state.identity_hash == "81e74045ebce6413b5f9387fa7fc4a1565ff601cbc46f69bba4e0ffcec28c07d"
    assert set(state.to_mapping()) == {
        "schema_version", "convention", "boundary", "sample_clock", "joints", "frames", "unavailable",
    }
    assert decode_canonical_state_view(state.to_mapping()) == state


def test_c02b_r1_force_capability_is_exact_and_unsupported_provider_fails_before_materialize(
    tmp_path, monkeypatch,
):
    candidate = build_r1_force_candidate(tmp_path / "candidate")
    execution = ExecutionSpec("geophys", "p1_2_scalar_cpu_v0", "none", "cpu", 0, "strict")
    manifest = _c02b_r1_force_capability_manifest(
        candidate.artifact, execution, candidate.source, candidate.plan,
        candidate.controller, ControlBinding("panda-main/gripper", 0.08),
    )
    force_claims = [claim for claim in manifest.capabilities if claim.name == "actuator_force_query"]
    assert len(force_claims) == 1 and force_claims[0].status == "tested"
    assert "geophys=git:a53a8cfed7c9d6464274b5c96fca601271dc4ee4" in force_claims[0].evidence_reference
    assert f"plan={candidate.plan.identity_hash}" in force_claims[0].evidence_reference
    assert "actuator_force_query" not in {claim.name for claim in provider_manifest("geophys").capabilities}
    assert "actuator_force_query" not in session_api.CAPABILITIES

    materialize_calls = []
    monkeypatch.setattr(control_sessions, "materialize", lambda *args, **kwargs: materialize_calls.append(args))
    with pytest.raises(CapabilityAdmissionError, match="GeoPhys CPU"):
        materialize_control(
            candidate.artifact,
            ExecutionSpec("mujoco", "p1_2_scalar_cpu_v0", "none", "cpu", 0, "strict"),
            source=candidate.source,
            binding=ControlBinding("panda-main/gripper", 0.08),
            controller_binding_plan=candidate.plan,
            controller_profile=candidate.controller,
        )
    assert materialize_calls == []

    with pytest.raises(CapabilityAdmissionError, match="source/materialization identity"):
        _c02b_r1_force_capability_manifest(
            candidate.artifact, execution,
            replace(candidate.source, source_closure_digest="d" * 64),
            candidate.plan, candidate.controller,
            ControlBinding("panda-main/gripper", 0.08),
        )

    wrong_controller = ProductionCanonicalPandaController(
        PandaKinematics(candidate.source.scene_source.xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1),
        artifact_hash=candidate.artifact.identity_hash,
        config=candidate.source.config.action,
        gripper_config=replace(candidate.source.config.robot.gripper, force_limit_N=29.0),
        gripper_semantic_id="panda-main/gripper",
    )
    with pytest.raises(CapabilityAdmissionError, match="actual R1 Controller or hand-origin TCP"):
        _c02b_r1_force_capability_manifest(
            candidate.artifact, execution, candidate.source, candidate.plan,
            wrong_controller, ControlBinding("panda-main/gripper", 0.08),
        )

    for revision in (
        "eb870f6f8812abea9022594b702df0c395d98d48",
        "9a43b92032deee90c1aef3a7f5f15216dc8e4b42",
    ):
        monkeypatch.setattr(control_sessions, "provider_build_identity", lambda _name, rev=revision: {
            "repository_revision": rev,
            "dirty_build_sha256": None,
            "manifest_version": f"git:{rev}",
        })
        with pytest.raises(CapabilityAdmissionError, match="requires clean GeoPhys repair commit"):
            _c02b_r1_force_capability_manifest(
                candidate.artifact, execution, candidate.source, candidate.plan,
                candidate.controller, ControlBinding("panda-main/gripper", 0.08),
            )


def test_c02b_r1_geophys_cpu_plan_bound_publication_and_control_interval(tmp_path):
    root = Path(os.environ.get(
        "C02B_R1_EVIDENCE_DIR",
        "workspace/maintenance/c02b_r1_typed_force_20261022",
    ))
    root.mkdir(parents=True, exist_ok=True)
    candidate = build_r1_force_candidate(root / "candidate")
    scene = candidate.scene
    joint_bindings, frame_bindings = _candidate_bindings(scene, candidate.source)
    execution = ExecutionSpec("geophys", "p1_2_scalar_cpu_v0", "none", "cpu", 0, "strict")
    session = materialize_control(
        candidate.artifact, execution, source=candidate.source,
        binding=ControlBinding("panda-main/gripper", 0.08),
        controller_binding_plan=candidate.plan, controller_profile=candidate.controller,
    )
    try:
        realized = session.reset_plan(candidate.reset_plan)
        initial_state = session.snapshot()
        requirements = candidate.plan.controller_bindings[0].feedback_requirements
        initial_clock = initial_state.simulation_time
        initial = session.snapshot_v2(
            scene=scene, joint_bindings=joint_bindings, frame_bindings=frame_bindings,
            requirements=requirements,
        )
        assert session.snapshot().simulation_time == initial_clock
        initial_force = initial.view.actuator_forces[0]
        with pytest.raises(ValueError, match="current typed force publication"):
            session.control_feedback(session.snapshot())
        initial_feedback = session.control_feedback(session.snapshot(), actuator_force=initial_force)
        assert session.snapshot().simulation_time == initial_clock
        expected_initial_closing = max(0.0, -initial_force.signed_value)
        assert initial_force.valid and initial_force.sample_phase == "reset_forward"
        assert initial_force.native_step_index == 0 and initial_force.native_sample_time_s == 0.0
        assert initial_force.unit == "N" and initial_force.actuator_id == "actuator8"
        measured_initial = session.actuator_force_measurement
        assert measured_initial is not None and measured_initial.valid
        assert initial_force.signed_value == measured_initial.signed_force_N
        assert initial_force.actuator_control_value == measured_initial.actuator_ctrl
        assert initial_feedback.gripper.closing_force_N == expected_initial_closing

        schema = candidate.plan.controller_bindings[0].action_schema
        request = StructuredActionRequestV1(
            "structured-action-request-v1", candidate.plan.scene_identity_hash,
            candidate.plan.identity_hash,
            (
                ControlGroupActionV1(
                    "control-group-action-v1", "panda-main", "arm", schema.schema_id,
                    (0.35, 0.0, 0.45, 1.0, 0.0, 0.0, 0.0),
                ),
                ControlGroupActionV1(
                    "control-group-action-v1", "panda-main", "gripper", schema.schema_id, (-1.0,),
                ),
            ),
        )
        canonical, target, acknowledgement, stepped, next_publication, feedback = (
            execute_plan_bound_r1_control_interval(
                session, candidate.controller, candidate.plan, request, initial,
                scene=scene, joint_bindings=joint_bindings, frame_bindings=frame_bindings,
            )
        )
        assert acknowledgement.target_hash == target.identity_hash
        assert set(acknowledgement.arm_servo_position) == set(candidate.source.joint_targets)
        assert stepped.control_step == 1 and stepped.simulation_time == pytest.approx(0.01)
        assert next_publication.view.sample_clock.simulation_time_s == pytest.approx(0.01)
        next_force = next_publication.view.actuator_forces[0]
        assert next_force.valid and next_force.sample_phase == "native_step_pre_integration"
        assert next_force.native_step_index == 5
        assert next_force.native_sample_time_s == pytest.approx(0.008)
        assert next_force.evaluation_simulation_time_s == pytest.approx(0.01)
        assert next_force.reset_sample_id == realized.reset_sample_id
        assert next_force.source_closure_digest == candidate.source.source_closure_digest
        assert next_force.provider_materialization_id == initial.view.boundary.provider_materialization_id
        joint_delta = {
            name: float(stepped.joint_position[name]) - float(initial_state.joint_position[name])
            for name in candidate.source.joint_targets
        }
        assert any(abs(value) > 1.0e-10 for value in joint_delta.values())

        after_feedback = session.control_feedback(stepped, actuator_force=next_force)
        assert after_feedback.gripper.closing_force_N == pytest.approx(max(0.0, -next_force.signed_value))
        assert session.snapshot().simulation_time == pytest.approx(0.01)
        provider_build = control_sessions.provider_build_identity("geophys")
        assert provider_build["repository_revision"] == "a53a8cfed7c9d6464274b5c96fca601271dc4ee4"
        assert provider_build["dirty_build_sha256"] is None
        evidence = {
            "schema": "c02b-r1-typed-force-probe-v1",
            "provider": "geophys",
            "provider_revision": provider_build["repository_revision"],
            "provider_manifest_version": provider_build["manifest_version"],
            "backend": "cpu",
            "execution": execution.to_mapping(),
            "artifact_identity": candidate.artifact.identity_hash,
            "scene_identity": scene.identity_hash,
            "source_closure_digest": candidate.source.source_closure_digest,
            "controller_identity": candidate.controller.identity,
            "controller_kinematics_identity": candidate.controller.source_kinematics_identity,
            "plan_identity": candidate.plan.identity_hash,
            "reset_sample_id": realized.reset_sample_id,
            "initial_boundary": initial.view.boundary.to_mapping(),
            "initial_raw_force": initial_force.to_mapping(),
            "initial_canonical_closing_force_N": initial_feedback.gripper.closing_force_N,
            "request": request.to_mapping(),
            "target_hash": target.identity_hash,
            "acknowledgement": acknowledgement.to_mapping(),
            "controller_force_mode_after_first_closing_compute": candidate.controller.memory().force_mode_active,
            "initial_joint_position": dict(initial_state.joint_position),
            "completed_joint_position": dict(stepped.joint_position),
            "completed_joint_delta": joint_delta,
            "completed_boundary": {"control_step": stepped.control_step, "simulation_time_s": stepped.simulation_time},
            "next_raw_force": next_force.to_mapping(),
            "next_canonical_closing_force_N": after_feedback.gripper.closing_force_N,
            "native_steps_in_interval": next_force.native_step_index,
            "canonical_target": canonical.to_mapping(),
        }
        (root / "s2_probe.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    finally:
        session.close()
