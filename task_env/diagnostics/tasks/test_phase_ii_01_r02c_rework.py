"""Targeted provider-free regressions for the R02c selected leaf route."""
from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
import json
from pathlib import Path
import re
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.artifacts.state import StateBoundaryIdentity, StateRequirements, StateSampleClock
from task_env.controllers.canonical.leaf_profiles import (
    ArmPositionTargetV1, HandPositionTargetV1,
)
from task_env.runtime.sessions.leaf_control import (
    LeafActuatorPatchV1, LeafPreparedCommandV1, LeafRuntimeClockV1,
    dispatch_leaf_control_interval, prepare_leaf_command,
)
from task_env.runtime.sessions.mujoco import _MuJoCoSession
from task_env.tasks.reference_env import SelectedReferenceEnv
from task_env.tasks.position_candidate.leaf_candidate import build_leaf_position_candidate
from task_env.trajectory.canonical.episode import make_episode_end_v1
from task_env.recorders import RecorderConfig, TransitionRecorder, load_leaf_control_records_h5

from task_env.diagnostics.tasks.test_phase_ii_01_r02b_leaf_execution import (
    _actions, _case, _publication, _receipt, _request, _SyntheticRuntime,
)


def _runtime_identity_fixture(tmp_path):
    package, binding, library = (str(tmp_path / name) for name in (
        "__init__.py", "_functions.so", "libmujoco.so.3.8.1",
    ))
    expected = {
        "package_init_path": package, "binding_path": binding,
        "native_library_path": library, "native_library_sha256": "c" * 64,
        "static_files_sha256": {package: "a" * 64, binding: "b" * 64},
    }
    observed = {
        "version": "3.8.1", "runtime_version": "3.8.1", "mj_version": 3008001,
        "package_path": package, "package_sha256": "a" * 64,
        "binding_path": binding, "binding_sha256": "b" * 64,
        "mapped_native_libraries": [{"path": library, "sha256": "c" * 64}],
    }
    return observed, expected


def test_runtime_version_guard_accepts_the_installed_381_header_without_native_import(tmp_path):
    from importlib.metadata import distribution
    from task_env.diagnostics.tasks.r02c_leaf_position_probe import _validate_mujoco_runtime_identity
    header = Path(distribution("mujoco").locate_file("mujoco/include/mujoco/mujoco.h"))
    api_version = int(re.search(r"^#define mjVERSION_HEADER (\d+)$", header.read_text(), re.MULTILINE)[1])
    observed, expected = _runtime_identity_fixture(tmp_path)
    observed["mj_version"] = api_version
    _validate_mujoco_runtime_identity(observed, expected)
    assert "mujoco" not in __import__("sys").modules


@pytest.mark.parametrize("field,value", [
    ("version", "3.8.0"), ("runtime_version", "3.8.0"),
    ("mj_version", 30801), ("mj_version", True),
    ("package_path", "/wrong/package.py"), ("package_sha256", "d" * 64),
    ("binding_path", "/wrong/binding.so"), ("binding_sha256", "d" * 64),
    ("mapped_native_libraries", []),
    ("mapped_native_libraries", [{"path": "/wrong/lib.so", "sha256": "c" * 64}]),
])
def test_runtime_identity_guard_retains_strict_version_path_and_hash_rejections(tmp_path, field, value):
    from task_env.diagnostics.tasks.r02c_leaf_position_probe import _validate_mujoco_runtime_identity
    observed, expected = _runtime_identity_fixture(tmp_path)
    observed[field] = value
    before = deepcopy(observed)
    with pytest.raises(RuntimeError, match="BLOCKED_PROVIDER") as caught:
        _validate_mujoco_runtime_identity(observed, expected)
    assert observed == before
    if field in {"version", "runtime_version", "mj_version"}:
        assert "3008001" in str(caught.value) and repr(value) in str(caught.value)
    assert "mujoco" not in __import__("sys").modules


def test_continuation_output_gate_protects_history_and_allows_one_native_slot(tmp_path, monkeypatch):
    from task_env.diagnostics.tasks import r02c_leaf_position_probe as probe
    monkeypatch.setattr(probe, "REPO", tmp_path)
    monkeypatch.setattr(probe, "ATTEMPT_ROOT", None)
    base = tmp_path / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001"
    current = base / f"r02c_{probe.CURRENT_ATTEMPT}"
    for raw, mode in ((base / "r02c_002/native_run_002", "native"),
                      (current / "native_run_002", "native"),
                      (current / "native_run_001", "static"),
                      (current / "preflight_001", "native")):
        with pytest.raises(ValueError):
            probe._safe_output_path(str(raw), mode)
        assert not raw.exists()
    for name, mode in (("preflight_001", "static"), ("native_run_001", "native")):
        path = current / name
        assert probe._safe_output_path(str(path), mode) == path
        with pytest.raises(FileExistsError):
            probe._safe_output_path(str(path), mode)


@pytest.mark.parametrize("authorization", [{}, {"reference": "", "user_instruction_reference": ""}])
def test_static_preflight_rejects_empty_authorization_references(authorization):
    from task_env.diagnostics.tasks import r02c_leaf_position_probe as probe
    contract = {"task_id": "PHASE-II-01-R02C", "attempt": probe.CURRENT_ATTEMPT,
                "authorization": authorization}
    with pytest.raises(RuntimeError, match="authorization reference is missing"):
        probe._verify_frozen_inputs(contract, {})


def test_prepared_command_strict_codec_checks_nested_identity_and_slot_order():
    scene, _, _, _, plan = _case()
    receipt = _receipt(plan)
    publication = _publication(scene, receipt, plan=plan)
    action = _actions(plan=plan)[0].action
    writer_id = next(entry.binding.writer_id for entry in plan.leaves
                     if entry.binding.profile_kind == "arm_position")
    command = prepare_leaf_command(
        plan, writer_id, action, publication, receipt, receipt.configuration_revision, scene=scene,
    )
    encoded = json.loads(json.dumps(command.to_mapping()))
    assert LeafPreparedCommandV1.from_mapping(encoded) == command

    unknown = dict(encoded, unrecognized=True)
    with pytest.raises(ValueError, match="unknown or missing"):
        LeafPreparedCommandV1.from_mapping(unknown)
    missing = dict(encoded)
    del missing["state_boundary"]
    with pytest.raises(ValueError, match="unknown or missing"):
        LeafPreparedCommandV1.from_mapping(missing)
    wrong_binding = json.loads(json.dumps(encoded))
    wrong_binding["binding_identity_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="Target/source boundary"):
        LeafPreparedCommandV1.from_mapping(wrong_binding)
    wrong_target = json.loads(json.dumps(encoded))
    wrong_target["target"]["writer_id"] = "other-writer"
    with pytest.raises(ValueError, match="Target/source boundary"):
        LeafPreparedCommandV1.from_mapping(wrong_target)
    duplicate = json.loads(json.dumps(encoded))
    duplicate["slot_values"][1]["ctrl_slot"] = duplicate["slot_values"][0]["ctrl_slot"]
    with pytest.raises(ValueError, match="ctrl slot twice"):
        LeafPreparedCommandV1.from_mapping(duplicate)
    assert "mujoco" not in __import__("sys").modules


def _adapter_runtime(scene, plan, receipt, publication):
    runtime = object.__new__(_MuJoCoSession)
    runtime._leaf_plan = plan
    runtime._leaf_materialization_receipt = receipt
    runtime._leaf_configuration_revision = receipt.configuration_revision
    runtime._leaf_fault = None
    runtime._leaf_interval_active = False
    runtime._leaf_interval_boundary_id = None
    runtime._leaf_interval_source_boundary = None
    runtime._leaf_interval_source_sample_clock = None
    runtime._leaf_interval_source_configuration_revision = None
    runtime._leaf_interval_writers = set()
    runtime._leaf_consumed_boundaries = set()
    runtime._leaf_active_plan_identity = None
    runtime._source = SimpleNamespace(source_closure_digest=plan.source_closure_sha256)
    runtime._data = SimpleNamespace(ctrl=np.zeros(receipt.nu, dtype=np.float64))
    runtime._current_ctrl = runtime._data.ctrl.copy()
    runtime._state_revision = publication.view.boundary.state_revision

    def read_clock():
        boundary = replace(publication.view.boundary, state_revision=runtime._state_revision)
        return LeafRuntimeClockV1(
            "leaf-runtime-clock-v1", boundary, publication.view.sample_clock,
            receipt.configuration_revision,
        )

    runtime.read_leaf_runtime_clock = read_clock
    return runtime


def _patch_for(command, plan, receipt):
    return LeafActuatorPatchV1(
        "leaf-actuator-patch-v1", command.writer_id, command.command_identity_sha256,
        command.target, plan.identity_sha256, receipt.identity_sha256,
        command.state_configuration_revision, command.slot_values,
    )


def test_mujoco_adapter_checks_source_target_before_any_write_and_accepts_two_writers():
    scene, _, _, _, plan = _case()
    receipt = _receipt(plan)
    publication = _publication(scene, receipt, plan=plan)
    commands = tuple(prepare_leaf_command(
        plan, action.writer_id, action.action, publication, receipt,
        receipt.configuration_revision, scene=scene,
    ) for action in _actions(plan=plan))

    stale_publication = _publication(
        scene, receipt, plan=plan, episode="other-episode", reset_id="reset-" + "2" * 64,
    )
    stale = prepare_leaf_command(
        plan, commands[0].writer_id, _actions(plan=plan)[0].action, stale_publication,
        receipt, receipt.configuration_revision, scene=scene,
    )
    arm_command = commands[0]
    base_patch = _patch_for(arm_command, plan, receipt)
    wrong_materialization_boundary = replace(
        arm_command.target.source_boundary, provider_materialization_id="other-materialization",
    )
    wrong_step_boundary = replace(arm_command.target.source_boundary, control_step=1)
    wrong_step_clock = replace(arm_command.target.sample_clock, sample_index=1, simulation_time_s=0.01)
    wrong_clock = replace(arm_command.target.sample_clock,
                          simulation_time_s=arm_command.target.sample_clock.simulation_time_s + 0.1)
    wrong_joint_order = tuple(reversed(arm_command.target.joint_order))
    wrong_order_action = replace(arm_command.target.action, joint_order=wrong_joint_order)
    wrong_order_target = replace(
        arm_command.target, joint_order=wrong_joint_order, action=wrong_order_action,
    )
    rejected = (
        _patch_for(stale, plan, receipt),
        replace(base_patch, target=replace(
            arm_command.target, source_boundary=wrong_materialization_boundary,
        )),
        replace(base_patch, target=replace(
            arm_command.target, source_boundary=wrong_step_boundary, sample_clock=wrong_step_clock,
        )),
        replace(base_patch, target=replace(arm_command.target, sample_clock=wrong_clock)),
        replace(base_patch, target=wrong_order_target),
        replace(base_patch, state_configuration_revision="config-stale"),
    )
    for patch in rejected:
        runtime = _adapter_runtime(scene, plan, receipt, publication)
        runtime.begin_leaf_control_interval(plan.identity_sha256, publication.view.boundary.boundary_id)
        original_ctrl = runtime._data.ctrl.copy()
        with pytest.raises(ValueError, match="consumed leaf evaluation"):
            runtime.apply_leaf_actuator_patch(patch)
        assert np.array_equal(runtime._data.ctrl, original_ctrl)
        assert runtime._state_revision == publication.view.boundary.state_revision
        assert runtime._leaf_interval_writers == set()

    runtime = _adapter_runtime(scene, plan, receipt, publication)
    runtime.begin_leaf_control_interval(plan.identity_sha256, publication.view.boundary.boundary_id)

    for command in commands:
        runtime.apply_leaf_actuator_patch(_patch_for(command, plan, receipt))
    assert runtime._leaf_interval_writers == {item.writer_id for item in commands}
    assert runtime._state_revision == publication.view.boundary.state_revision + 2
    assert np.isfinite(runtime._data.ctrl).all()
    assert "mujoco" not in __import__("sys").modules


@pytest.mark.parametrize("cleanup_raises", [False, True])
def test_materialize_control_closes_new_session_once_when_leaf_admission_fails(
    tmp_path, monkeypatch, cleanup_raises,
):
    from task_env.runtime.sessions import control as control_module
    from task_env.runtime.sessions import provenance

    candidate = build_leaf_position_candidate(
        tmp_path / "candidate", environment_type=SelectedReferenceEnv,
    )
    admission_error = RuntimeError("injected leaf admission failure")

    class Session:
        close_calls = 0

        def admit_leaf_control_plan(self, _plan):
            raise admission_error

        def close(self):
            self.close_calls += 1
            if cleanup_raises:
                raise OSError("injected cleanup failure")

    session = Session()
    monkeypatch.setattr(control_module, "provider_manifest", lambda _provider: object())
    monkeypatch.setattr(control_module, "admit_capabilities", lambda *_args: None)
    monkeypatch.setattr(control_module, "materialize", lambda *_args, **_kwargs: session)
    monkeypatch.setattr(provenance, "provider_build_identity", lambda _provider: candidate.provider_build_identity)
    execution = SimpleNamespace(physics_provider="mujoco", backend="cpu", render_provider="none")
    try:
        with pytest.raises(RuntimeError, match="injected leaf admission failure") as caught:
            control_module.materialize_control(
                candidate.artifact, execution, source=candidate.source, binding=object(),
                leaf_plan=candidate.plan,
            )
        assert caught.value is admission_error
        assert session.close_calls == 1
        if cleanup_raises:
            assert any("injected cleanup failure" in note for note in getattr(caught.value, "__notes__", ()))
    finally:
        candidate.env.close()


def _boundary_observation(boundary):
    digest = boundary.boundary_id.removeprefix("state-boundary-")
    return {"state": {"boundary_identity_sha256": np.frombuffer(bytes.fromhex(digest), dtype=np.uint8)}}


def _recording_profile(candidate, receipt, reset_id):
    scene, plan, preset = candidate.scene, candidate.plan, candidate.preset
    return {
        "schema_version": "leaf-position-recording-profile-v1",
        "profile_id": "r02c-independent-position-leaves-v1",
        "task_artifact_identity_hash": candidate.artifact.identity_hash,
        "task_source_identity_sha256": candidate.artifact.task_source_identity_hash,
        "scene_identity_hash": scene.identity_hash,
        "source_id": candidate.source.scene_source.source_id,
        "source_closure_digest": plan.source_closure_sha256,
        "effective_leaf_plan_identity_sha256": plan.identity_sha256,
        "preset_identity_sha256": preset.identity_sha256,
        "reset_plan_identity_hash": "3" * 64,
        "reset_sample_id": reset_id,
        "provider": "mujoco", "provider_version": "3.8.1",
        "provider_build_sha256": plan.provider_build_sha256,
        "backend": "cpu", "physics_dt_s": 0.002,
        "control_substeps": 5, "control_dt_s": 0.01,
        "materialization_identity_sha256": receipt.identity_sha256,
        "configuration_revision": receipt.configuration_revision,
        "writers": [{
            "writer_id": entry.binding.writer_id,
            "profile_kind": entry.binding.profile_kind,
            "action_schema_id": entry.binding.action_schema_id,
            "binding_identity_sha256": entry.binding.identity_hash,
            "effective_configuration_identity_sha256": entry.effective_configuration_identity_sha256,
            "member_path": entry.binding.member_path,
            "entity_id": entry.binding.entity_id,
            "control_group_id": entry.binding.control_group_id,
            "joint_order": tuple(ref.joint_id for ref in entry.binding.joint_order),
            "actuator_order": tuple(ref.actuator_id for ref in entry.binding.actuator_order),
        } for entry in plan.leaves],
    }


def _runtime_with_real_publication(candidate, receipt, publication):
    """Synthetic IO; use actual MuJoCo projection and shared snapshot owners."""
    runtime = _SyntheticRuntime(candidate.scene, receipt, publication, plan=candidate.plan)
    session = object.__new__(_MuJoCoSession)
    session._source, session._artifact = candidate.source, candidate.artifact
    session._leaf_plan, session._provider = candidate.plan, "mujoco"
    session._closed, session._reset_done = False, True
    session._reset_plan_gate_required, session._inner_interval_active = False, False
    session._joint_addresses = {name: (index, index)
                                for index, name in enumerate(candidate.source.joints)}
    session._free_addresses = {}
    session._bodies = {name: index for index, name in enumerate(candidate.source.bodies)}
    session._frames = {name: index for index, name in enumerate(candidate.source.frames)}
    joints = {f"{item.entity_id}/{item.joint_id}": item for item in publication.view.joints}
    frames = {f"{item.frame.entity_id}/{item.frame.frame_id}": item.pose_world
              for item in publication.view.frames}
    session._data = SimpleNamespace(
        qpos=np.array([joints[name].position[0] for name in session._joint_addresses]),
        qvel=np.array([joints[name].velocity[0] for name in session._joint_addresses]),
        xpos=np.array([frames[name].position if name in frames else (0.0, 0.0, 0.0)
                       for name in session._bodies]),
        xquat=np.array([frames[name].quaternion_wxyz if name in frames else (1.0, 0.0, 0.0, 0.0)
                        for name in session._bodies]),
        site_xpos=np.zeros((len(session._frames), 3)),
        site_xmat=np.tile(np.eye(3).reshape(9), (len(session._frames), 1)), time=0.0,
    )
    session._mj = SimpleNamespace(mju_mat2Quat=lambda output, _matrix: output.__setitem__(
        slice(None), (1.0, 0.0, 0.0, 0.0),
    ))
    original_advance = runtime._advance

    def advance(*, time_delta):
        original_advance(time_delta=time_delta)
        # Match the real adapter's canonical clock; no physics is simulated.
        step = runtime.clock.boundary.control_step
        runtime.clock = replace(runtime.clock, sample_clock=replace(
            runtime.clock.sample_clock, simulation_time_s=step * candidate.artifact.timebase.control_dt,
        ))

    def publish(scene, requirements):
        boundary = runtime.clock.boundary
        for name in ("episode_id", "reset_sample_id", "scene_instance_id",
                     "provider_materialization_id", "control_step", "state_revision"):
            setattr(session, "_" + name, getattr(boundary, name))
        session._native_steps = boundary.control_step * candidate.artifact.timebase.control_substeps
        session._data.time = session._native_steps * candidate.artifact.timebase.physics_dt
        runtime.publish_calls += 1
        return session.publish_leaf_state(scene, requirements)

    runtime._advance, runtime.publish_leaf_state = advance, publish
    return runtime


def test_production_transition_writer_generic_h5_roundtrip_and_nine_tampers(tmp_path):
    candidate = build_leaf_position_candidate(
        tmp_path / "candidate-source", environment_type=SelectedReferenceEnv,
    )
    scene, plan, preset = candidate.scene, candidate.plan, candidate.preset
    receipt = _receipt(plan)
    reset_id = candidate.reset_plan.reset_sample.sample_id
    publication = _publication(scene, receipt, plan=plan, reset_id=reset_id)
    runtime = _runtime_with_real_publication(candidate, receipt, publication)
    with pytest.raises(TypeError, match="requires StateRequirements"):
        runtime.publish_leaf_state(scene, tuple(
            requirement for entry in plan.leaves
            for requirement in entry.binding.required_state.state_requirements.requirements
        ))
    published_requirements = []
    original_publish_leaf_state = runtime.publish_leaf_state

    def capture_publish_leaf_state(published_scene, requirements):
        published_requirements.append(requirements)
        return original_publish_leaf_state(published_scene, requirements)

    runtime.publish_leaf_state = capture_publish_leaf_state
    profile = _recording_profile(candidate, receipt, reset_id)
    metadata = {"env_metadata": {
        "env_name": "SelectedReferenceEnv.R02cSyntheticS1",
        "task_name": "r02c-synthetic-s1", "task_version": "s1",
        "scene_uid": scene.scene_id, "agent_uids": ("panda-main",),
        "physics_dt": 0.002, "control_substeps": 5, "control_frequency": 100.0,
        "action_schema": {"schema_id": "leaf-position-action-set-v1",
                           "components": tuple(f"component-{index}" for index in range(8))},
        "observation_schema": {"leaf_specs": ({
            "path": "state/boundary_identity_sha256",
            "semantic": "state_boundary_identity_sha256",
        },)},
        "reference_profile": profile,
    }}
    recorder = TransitionRecorder(RecorderConfig(schema_version="v3", max_transitions=64))
    initial_obs = _boundary_observation(publication.view.boundary)
    recorder.begin_episode(initial_obs, {"seed": 31, "options": {}}, metadata)

    fake_env = SimpleNamespace(
        leaf_plan=plan, recorder=recorder, obs=initial_obs,
        evaluation=SimpleNamespace(reward=0.0, success=False), info={},
        value={"source": SimpleNamespace(source_closure_digest=plan.source_closure_sha256)},
        session=SimpleNamespace(leaf_materialization_receipt=receipt),
    )
    observed_ctrl = {}
    try:
        for interval in range(1, 65):
            action = __import__(
                "task_env.tasks.position_candidate.leaf_candidate", fromlist=["action_for_interval"],
            ).action_for_interval(scene, plan, interval, arm_active=True, hand_active=True)
            request = action.structured_request(scene, plan)
            result = dispatch_leaf_control_interval(plan, _request(
                plan, receipt, runtime.publication, actions=_actions(
                    arm_action=action.arm, hand_action=action.hand, plan=plan,
                ),
            ), scene=scene, runtime=runtime)
            observed_ctrl[("synthetic-s1", interval)] = [runtime.ctrl[slot] for slot in range(8)]
            fake_env.obs = _boundary_observation(result.next_publication.view.boundary)
            SelectedReferenceEnv._record_leaf_position_transition(
                fake_env, action, request, result, terminated=False, truncated=(interval == 64),
            )
            runtime.publication = result.next_publication

        episode_end = make_episode_end_v1(
            episode_id=publication.view.boundary.episode_id, final_boundary=64,
            end_reason="horizon_reached", terminated=False, truncated=True,
            bootstrap_allowed=True, source="synthetic_s1",
        )
        recorder.end_episode(
            "horizon_reached", outcome=episode_end.outcome, end_event=episode_end.boundary_event,
        )
        h5_path = recorder.save_h5(tmp_path, "synthetic_leaf_roundtrip.h5")
        loaded = load_leaf_control_records_h5(h5_path)
        assert loaded["transition_count"] == 64
        assert loaded["observation_count"] == 65
        assert loaded["leaf_writer_ids"] == tuple(sorted(entry.binding.writer_id for entry in plan.leaves))
        from task_env.diagnostics.tasks.r02c_leaf_position_probe import _validate_h5_commands
        _validate_h5_commands(loaded, observed_ctrl, "synthetic-s1", arm_active=True, hand_active=True)
        changed_ctrl = deepcopy(observed_ctrl)
        changed_ctrl[("synthetic-s1", 1)][0] += 0.001
        with pytest.raises(AssertionError, match="ctrl differs from stored command"):
            _validate_h5_commands(loaded, changed_ctrl, "synthetic-s1", arm_active=True, hand_active=True)
        assert len(published_requirements) == 64
        assert all(type(value) is StateRequirements for value in published_requirements)
        assert all(value.consumer_kind == "controller"
                   and value.consumer_id == "r02c-independent-position-leaves-v1"
                   for value in published_requirements)
        expected_requirement_keys = {
            (requirement.field_key, requirement.sample_domain)
            for entry in plan.leaves
            for requirement in entry.binding.required_state.state_requirements.requirements
        }
        assert all({(item.field_key, item.sample_domain) for item in value.requirements}
                   == expected_requirement_keys for value in published_requirements)
        from task_env.diagnostics.tasks.r02c_leaf_position_probe import _tamper_checks
        checks = _tamper_checks(h5_path, load_leaf_control_records_h5)
        assert len(checks) == 9 and all(item["rejected"] for item in checks)
        assert "mujoco" not in __import__("sys").modules
    finally:
        candidate.env.close()


def test_probe_captures_real_dispatch_progress_before_session_close():
    from task_env.diagnostics.tasks.r02c_leaf_position_probe import _leaf_failure_progress
    scene, _, _, _, plan = _case()
    receipt = _receipt(plan)
    publication = _publication(scene, receipt, plan=plan)
    runtime = _SyntheticRuntime(scene, receipt, publication, plan=plan)

    def rejected_publication(_scene, _requirements):
        raise TypeError("typed state projection requires StateRequirements")

    runtime.publish_leaf_state = rejected_publication
    with pytest.raises(TypeError, match="requires StateRequirements"):
        dispatch_leaf_control_interval(
            plan, _request(plan, receipt, publication), scene=scene, runtime=runtime,
        )
    rows = _leaf_failure_progress([SimpleNamespace(session=runtime), SimpleNamespace(session=None)])
    assert len(rows) == 1
    row = rows[0]
    assert row["failure_phase"] == "leaf-state-publication"
    assert set(row["applied_writers"]) == {entry.binding.writer_id for entry in plan.leaves}
    assert len(row["prepared_commands"]) == len(row["returned_apply_results"]) == 2
    assert len(row["ack_identity_hashes"]) == len(row["command_identity_hashes"]) == 2
    assert row["fault"]["physical_progress"] == "advanced"
    json.dumps(rows, allow_nan=False)
    assert "mujoco" not in __import__("sys").modules
