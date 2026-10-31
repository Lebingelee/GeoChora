"""Provider-free source-predicate tests for the three required LIBERO tasks."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from bench_deploy.libero.evaluation import (
    LiberoPredicateBoundaryV1,
    OpenMiddleDrawerEvidenceV1,
    StoveFrontRegionEvidenceV1,
    evaluate_open_middle_drawer_v1,
    evaluate_stove_front_region_v1,
)
from bench_deploy.libero.controller import (
    LiberoMixedControlConfigV1,
    LiberoMixedControllerV1,
)
from bench_deploy.libero.task_contracts import TASK_2, TASK_3
from bench_deploy.libero.solution import (
    LiberoPickPlaceSolutionConfigV1,
    solution_identity_v1, solution_identity_v2, solution_identity_v4,
)
from task_env.controllers.canonical.kinematics import (
    PandaKinematics,
    derive_panda_tcp_profile_v2,
)


MANIFEST_SHA = "a" * 64
CLOSURE_SHA = "b" * 64


def test_task_one_solution_identity_binds_bounded_motion_rate():
    config = LiberoPickPlaceSolutionConfigV1()
    assert config.max_cartesian_increment_m == pytest.approx(0.002)
    assert config.max_joint_increment_rad == pytest.approx(0.01)
    source_sha = "f" * 64
    default_identity = solution_identity_v1(source_sha)
    assert default_identity == solution_identity_v1(source_sha, config)
    slower = replace(config, max_cartesian_increment_m=0.001)
    assert solution_identity_v1(source_sha, slower) != default_identity


def test_task_one_solution_v2_identity_binds_source_gravity_compensation():
    config = LiberoPickPlaceSolutionConfigV1()
    source_sha = "f" * 64
    closure_sha = "e" * 64
    identity = solution_identity_v2(source_sha, closure_sha)
    assert identity == solution_identity_v2(source_sha, closure_sha, config)
    assert solution_identity_v2(source_sha, "d" * 64) != identity
    assert solution_identity_v2("a" * 64, closure_sha) != identity
    slower = replace(config, max_cartesian_increment_m=0.001)
    assert solution_identity_v2(source_sha, closure_sha, slower) != identity


def test_task_one_solution_v3_identity_binds_world_pose_planner_and_frozen_v2_profiles():
    from bench_deploy.libero.controller import legacy_v2_controller_identity_mapping
    from bench_deploy.libero.solution import solution_identity_v2_frozen, solution_identity_v3
    from task_env.planners.cartesian import CartesianPosePlannerConfig

    source_sha, closure_sha = "f" * 64, "e" * 64
    default = solution_identity_v3(source_sha, closure_sha)
    assert solution_identity_v3("d" * 64, closure_sha) != default
    assert solution_identity_v3(source_sha, "c" * 64) != default
    slower = CartesianPosePlannerConfig(max_translation_per_step=0.006)
    assert solution_identity_v3(source_sha, closure_sha, planner_config=slower) != default

    frozen_controller = legacy_v2_controller_identity_mapping(
        "libero-spatial-bowl-to-plate-joint-space-pd-v4",
    )
    frozen = solution_identity_v2_frozen(source_sha, closure_sha, frozen_controller)
    assert frozen == solution_identity_v2_frozen(source_sha, closure_sha, frozen_controller)
    tampered_controller = {**frozen_controller, "kp_Nm_per_rad": [999.0] * 7}
    with pytest.raises(ValueError, match="frozen version manifest"):
        solution_identity_v2_frozen(source_sha, closure_sha, tampered_controller)
    with pytest.raises(ValueError, match="allowlist"):
        legacy_v2_controller_identity_mapping("unreviewed-profile")


def test_task_one_solution_v4_identity_binds_osc_grasp_and_convergence_policy():
    from bench_deploy.libero.controller import LiberoMixedControllerV3
    from task_env.planners.cartesian import CartesianPosePlannerConfig

    source_sha, closure_sha = "f" * 64, "e" * 64
    default = solution_identity_v4(source_sha, closure_sha)
    assert solution_identity_v4(source_sha, closure_sha) == default
    assert solution_identity_v4("d" * 64, closure_sha) != default
    assert solution_identity_v4(source_sha, "c" * 64) != default
    slower = CartesianPosePlannerConfig(max_translation_per_step=0.006)
    assert solution_identity_v4(source_sha, closure_sha, planner_config=slower) != default
    resolver_identity = "d" * 64
    from task_env.controllers.canonical import CanonicalPandaController
    from bench_deploy.libero.controller import LiberoMixedControllerV3
    controller = LiberoMixedControllerV3(arm_resolver_identity=resolver_identity)
    assert controller.identity_mapping()["algorithm"] == (
        "robosuite_osc_pose_uncoupled_lambda_and_nullspace_v1"
    )
    assert controller.identity_mapping()["qualification"] == "diagnostic_only_source_bound_20hz_OSC"


def test_task_one_solution_v5_controller_freezes_reset_nullspace_reference_and_physics_rate_policy():
    from types import SimpleNamespace

    from bench_deploy.libero.controller import LiberoMixedControllerV4
    from bench_deploy.libero.solution import solution_identity_v5

    resolver_identity = "d" * 64
    controller = LiberoMixedControllerV4(arm_resolver_identity=resolver_identity)
    first = np.asarray((0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7), dtype=np.float64)
    state = SimpleNamespace(
        joint_position={f"joint{index + 1}": float(value) for index, value in enumerate(first)},
        joint_velocity={f"joint{index + 1}": 0.0 for index in range(7)},
        control_step=0, simulation_time=0.0,
    )
    controller.reset(state)
    reference, source = controller._nullspace_reference(first + 1.0, np.zeros(7))
    assert source == "reset_initial_joint_v1"
    assert reference == pytest.approx(first)
    policy = controller.identity_mapping()
    assert policy["schema_version"] == "libero-mixed-controller-identity-v4"
    assert policy["hold_policy"] == "torque_recomputed_each_physics_substep_v1"
    assert policy["nullspace_reference_policy"] == "initial_joint_position_captured_at_reset_v1"
    assert policy["arm_resolver_identity"] == resolver_identity
    assert solution_identity_v5(
        "f" * 64, "e" * 64, arm_resolver_identity=resolver_identity,
    ) != solution_identity_v5(
        "f" * 64, "e" * 64, arm_resolver_identity="c" * 64,
    )
    second = first - 0.25
    reset_state = SimpleNamespace(
        joint_position={f"joint{index + 1}": float(value) for index, value in enumerate(second)},
        joint_velocity={f"joint{index + 1}": 0.0 for index in range(7)},
        control_step=0, simulation_time=0.0,
    )
    controller.reset(reset_state)
    reference, _ = controller._nullspace_reference(second + 2.0, np.zeros(7))
    assert reference == pytest.approx(second)


def test_task_one_solution_v5_holds_measured_contact_aperture_after_grasp():
    from bench_deploy.libero.solution import (
        LiberoPickPlaceSolutionV4,
        LiberoPickPlaceSolutionV5,
        solution_identity_v5,
    )

    legacy = object.__new__(LiberoPickPlaceSolutionV4)
    current = object.__new__(LiberoPickPlaceSolutionV5)
    for stage in ("lift", "carry", "place"):
        legacy.stage = current.stage = stage
        assert legacy._opening_for_stage() == pytest.approx(0.08)
        assert current._opening_for_stage() == pytest.approx(0.06)
    current.stage = "grasp"
    assert current._opening_for_stage() == pytest.approx(0.08)
    assert solution_identity_v5(
        "f" * 64, "e" * 64, arm_resolver_identity="d" * 64,
    ) != solution_identity_v5(
        "d" * 64, "e" * 64, arm_resolver_identity="d" * 64,
    )


def test_task_one_v4_bilateral_contact_requires_fresh_covered_left_and_right_pairs():
    from bench_deploy.libero.solution import LiberoPickPlaceSolutionV4

    boundary = {
        "source_id": "source-v1", "source_closure_digest": "a" * 64,
        "provider_materialization_id": "materialization-v1", "episode_id": "episode-v1",
        "reset_sample_id": "sample-v1", "control_step": 3,
        "state_revision": 3, "simulation_time_s": 0.15,
    }
    left = ("akita_black_bowl_1", "panda-v1/finger-left")
    right = ("akita_black_bowl_1", "panda-v1/finger-right")
    contact = {
        "schema_version": "task-contact-summary-v2", "status": "available",
        **boundary,
        "requested_pairs": [list(left), list(right)],
        "covered_pairs": [list(left), list(right)],
        "pair_counts": {"/".join(left): 1, "/".join(right): 2},
    }
    info = {
        **boundary, "boundary_context_v1": dict(boundary),
        "contact_summary_v2": contact,
    }
    assert LiberoPickPlaceSolutionV4._bilateral_finger_contact(info) == (
        True, (1, 2), "available",
    )
    one_sided = {**contact, "pair_counts": {"/".join(left): 1, "/".join(right): 0}}
    assert LiberoPickPlaceSolutionV4._bilateral_finger_contact(
        {**info, "contact_summary_v2": one_sided},
    )[:2] == (False, (1, 0))
    stale = {**contact, "state_revision": 2}
    assert LiberoPickPlaceSolutionV4._bilateral_finger_contact(
        {**info, "contact_summary_v2": stale},
    )[2] == "contact_summary_stale_or_wrong_boundary"


def test_task_one_v4_independent_reader_recomputes_source_osc_torque_and_gripper_mapping():
    from types import SimpleNamespace

    from bench_deploy.libero.controller import LiberoMixedControllerV3
    from bench_deploy.libero.core_candidate_worker import (
        _TASK1_COMPOSED_XML_SHA256, _TASK1_EXECUTION_SOURCE_CLOSURE_SHA256,
        _validate_v4_osc_receipt,
    )

    resolver_identity = "d" * 64
    controller = LiberoMixedControllerV3(arm_resolver_identity=resolver_identity)
    identity = controller.identity_mapping()
    q = np.zeros(7)
    mass = np.eye(7)
    jacobian = np.zeros((6, 7))
    jacobian[:3, :3] = np.eye(3)
    jacobian[3:, 3:6] = np.eye(3)
    bias = np.zeros(7)
    target_position = np.asarray((0.01, 0.0, 0.0))
    target_rotation = np.eye(3)
    position_error = target_position.copy()
    orientation_error = np.zeros(3)
    ee_velocity = np.zeros(6)
    task_torque = np.asarray((1.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    null_torque = np.zeros(7)
    raw_torque = task_torque.copy()
    applied_torque = raw_torque.copy()
    resolution_diagnostics = {
        "schema_version": "canonical-arm-resolution-diagnostics-v1",
        "method_id": "shared_canonical_dls_iterative_v1", "iteration_count": 1,
        "max_iterations": 12,
        "position_residual_m": 0.001, "orientation_residual_rad": 0.001,
        "position_tolerance_m": 0.006, "orientation_tolerance_rad": 0.03,
        "initial_position_gap_m": 0.001, "initial_orientation_gap_rad": 0.002,
        "model_position_tolerance_m": 0.003, "model_orientation_tolerance_rad": 0.03,
        "converged": True,
    }
    source_model_identity = "c" * 64
    receipt = {
        "schema_version": "libero-mixed-control-receipt-v3",
        "controller_identity": controller.identity,
        "algorithm": "robosuite_osc_pose_uncoupled_lambda_and_nullspace_v1",
        "source_state_profile_id": identity["source_state_profile_id"],
        "source_model_identity_sha256": source_model_identity,
        "source_xml_sha256": _TASK1_COMPOSED_XML_SHA256,
        "source_closure_digest": _TASK1_EXECUTION_SOURCE_CLOSURE_SHA256,
        "tcp_site_name": "gripper0_grip_site",
        "canonical_arm_resolution": resolution_diagnostics,
        "target_world_pose": {
            "position_m": target_position.tolist(),
            "quaternion_wxyz": [1.0, 0.0, 0.0, 0.0],
        },
        "current_world_pose": {
            "position_m": [0.0, 0.0, 0.0],
            "rotation_matrix": target_rotation.tolist(),
        },
        "q_rad": q.tolist(), "qdot_rad_s": q.tolist(),
        "mass_matrix_arm": mass.tolist(), "jacobian_world": jacobian.tolist(),
        "bias_minus_passive_Nm": bias.tolist(),
        "position_error_m": position_error.tolist(),
        "orientation_error_rad_vector": orientation_error.tolist(),
        "ee_velocity": ee_velocity.tolist(),
        "task_torque_Nm": task_torque.tolist(),
        "nullspace_torque_Nm": null_torque.tolist(),
        "raw_torque_Nm": raw_torque.tolist(), "applied_torque_Nm": applied_torque.tolist(),
        "torque_clipped": [False] * 7,
        "opening_m": 0.08, "hold_policy": "torque_zero_order_hold_per_outer_step_v1",
    }
    canonical_action = {
        "schema_version": "libero-world-pose-canonical-v1",
        "arm_target_schema_version": "canonical-arm-target-v1",
        "arm_target_source_xml_sha256": _TASK1_COMPOSED_XML_SHA256,
        "arm_target_controller_identity": resolver_identity,
        "controller_identity": controller.identity,
        "arm_resolution_diagnostics": resolution_diagnostics,
        "qdesired_rad": q.tolist(), "controller_receipt": receipt,
        "arm_joint_order": [f"panda-v1/joint{i}" for i in range(1, 8)],
        "qdesired_joint_order": [f"joint{i}" for i in range(1, 8)],
    }
    target = SimpleNamespace(channel_values={
        **{f"joint{i+1}": float(value) for i, value in enumerate(applied_torque)},
        "finger_joint1": 0.04, "finger_joint2": -0.04,
    })
    action = np.asarray((*target_position, 1.0, 0.0, 0.0, 0.0, 1.0))
    close = {"model_identity_sha256": source_model_identity}
    _validate_v4_osc_receipt(
        canonical_action, identity, target, action, np.zeros(9),
        np.asarray((0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)), close,
    )
    broken_target = SimpleNamespace(channel_values={**target.channel_values, "joint1": 2.0})
    with pytest.raises(ValueError, match="independently recomputed OSC torque law"):
        _validate_v4_osc_receipt(
            canonical_action, identity, broken_target, action, np.zeros(9),
            np.asarray((0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)), close,
        )


def test_source_closure_archive_reads_only_manifest_members_and_rejects_tampering(tmp_path):
    import hashlib
    import io
    import tarfile

    from bench_deploy.libero.source_gravity import read_source_closure_archive

    payload = {"canonical-source.xml": b"<mujoco/>", "assets/mesh.bin": b"mesh-bytes"}
    manifest = [
        {"path": name, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        for name, raw in sorted(payload.items())
    ]

    def write_archive(path, members):
        with tarfile.open(path, "w:gz") as archive:
            directory = tarfile.TarInfo("closure/")
            directory.type = tarfile.DIRTYPE
            archive.addfile(directory)
            nested = tarfile.TarInfo("closure/assets/")
            nested.type = tarfile.DIRTYPE
            archive.addfile(nested)
            for name, raw in members:
                info = tarfile.TarInfo("closure/" + name)
                info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))

    valid_path = tmp_path / "valid.tar.gz"
    write_archive(valid_path, sorted(payload.items()))
    assert read_source_closure_archive(valid_path, manifest) == payload

    tampered_path = tmp_path / "tampered-member.tar.gz"
    tampered = dict(payload)
    tampered["assets/mesh.bin"] = b"mesh-bitez"
    write_archive(tampered_path, sorted(tampered.items()))
    with pytest.raises(ValueError, match="member bytes differ"):
        read_source_closure_archive(tampered_path, manifest)

    unsafe_path = tmp_path / "unsafe-member.tar.gz"
    with tarfile.open(unsafe_path, "w:gz") as archive:
        directory = tarfile.TarInfo("closure/")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        info = tarfile.TarInfo("closure/../escape.bin")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="unsafe member path"):
        read_source_closure_archive(
            unsafe_path,
            [{"path": "escape.bin", "size_bytes": 1, "sha256": hashlib.sha256(b"x").hexdigest()}],
        )


def test_independent_reader_binds_gravity_formula_to_controller_gain_identity():
    from bench_deploy.libero.core_candidate_worker import _validate_source_gravity_action

    controller = LiberoMixedControllerV1()
    receipt = controller.identity_mapping()
    bias = np.asarray((0.0, -19.2, 0.1, 18.1, 0.0, 2.1, 0.0))
    planner = np.asarray((0.1, -0.2, 0.3, -2.4, 0.0, 2.2, 0.8))
    offset = bias / np.asarray(receipt["kp_Nm_per_rad"], dtype=np.float64)
    compensated = planner + offset
    diagnostics = {
        "gravity_compensation_profile_id": "libero-source-mjcf-gravity-bias-v1",
        "gravity_bias_Nm": bias.tolist(),
        "gravity_target_offset_rad": offset.tolist(),
        "planner_joint_target_rad": planner.tolist(),
        "gravity_compensated_joint_target_rad": compensated.tolist(),
    }
    action = np.asarray((*compensated, 0.06), dtype=np.float64)
    _validate_source_gravity_action(receipt, diagnostics, action, receipt)

    wrong_controller = {**receipt, "kp_Nm_per_rad": [100.0] * 7}
    with pytest.raises(ValueError, match="controller identity/profile"):
        _validate_source_gravity_action(wrong_controller, diagnostics, action, receipt)

    wrong_offset = {**diagnostics, "gravity_target_offset_rad": (bias / 100.0).tolist()}
    with pytest.raises(ValueError, match="gravity compensation formula"):
        _validate_source_gravity_action(receipt, wrong_offset, action, receipt)


def test_source_gravity_model_uses_verified_closure_and_releases_lowest_primitive(tmp_path):
    import hashlib
    import io
    import json
    from pathlib import Path
    import tarfile
    from types import SimpleNamespace

    from bench_deploy.libero.source_gravity import MujocoSourceGravityBiasV1
    from task_env.assembly.assets import _source_closure_digest

    xml = b'<mujoco><worldbody/></mujoco>'
    closure = {
        "canonical-source.xml": xml,
        "scene.xml": xml,
        "upstream/example.bin": b"source asset bytes",
    }
    bundle = tmp_path / "bundle"
    closure_root = bundle / "source_inputs/closure"
    for logical, raw in closure.items():
        path = closure_root / logical
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    plan = {
        "identity": {"task_uid": "libero_spatial/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate"},
        "output": {"composed_mjcf_sha256": hashlib.sha256(xml).hexdigest()},
    }
    plan_bytes = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    (bundle / "source_inputs/composition_plan.json").write_bytes(plan_bytes)

    class FakeModel:
        nq = nv = njnt = 7
        nbody = 8
        qpos0 = np.zeros(7)
        jnt_qposadr = np.arange(7)
        jnt_dofadr = np.arange(7)

        @classmethod
        def from_xml_path(cls, path):
            assert Path(path).read_bytes() == xml
            return cls()

    class FakeData:
        def __init__(self, model):
            self.qpos = np.zeros(model.nq)
            self.qvel = np.zeros(model.nv)
            self.qfrc_bias = np.zeros(model.nv)
            self.qfrc_passive = np.zeros(model.nv)

    def fake_name2id(model, obj_type, name):
        if obj_type == 1:
            assert name == "gripper0_grip_site"
            return 0
        assert obj_type == 0
        return int(name[-1]) - 1

    def fake_forward(model, data):
        data.qfrc_bias[:] = data.qpos

    fake_mujoco = SimpleNamespace(
        __version__="3.8.1", mj_version=lambda: 3008001,
        MjModel=FakeModel, MjData=FakeData,
        mjtObj=SimpleNamespace(mjOBJ_JOINT=0, mjOBJ_SITE=1),
        mj_name2id=fake_name2id, mj_forward=fake_forward,
    )
    source_xml_sha = hashlib.sha256(xml).hexdigest()
    source_closure = _source_closure_digest(closure)
    model = MujocoSourceGravityBiasV1(
        bundle_root=bundle, source_closure_files=closure,
        source_xml_sha256=source_xml_sha, source_closure_digest=source_closure,
        composition_plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
        mujoco_api=fake_mujoco,
    )
    assert np.array_equal(model.gravity_torque(np.arange(7, dtype=np.float64)), np.arange(7))
    assert model.forward_calls == 1
    close = model.close()
    assert close["closed"] and close["model_released"] and close["data_released"]
    assert close["mj_step_call_count"] == 0
    with pytest.raises(RuntimeError, match="closed"):
        model.gravity_torque(np.zeros(7))

    archived_bundle = tmp_path / "archived_bundle"
    archived_source = archived_bundle / "source_inputs"
    archived_source.mkdir(parents=True)
    (archived_source / "composition_plan.json").write_bytes(plan_bytes)
    with tarfile.open(archived_source / "closure.tar.gz", "w:gz") as archive:
        for directory_name in ("closure/", "closure/upstream/"):
            directory = tarfile.TarInfo(directory_name)
            directory.type = tarfile.DIRTYPE
            archive.addfile(directory)
        for logical, raw in sorted(closure.items()):
            member = tarfile.TarInfo("closure/" + logical)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    assert not (archived_source / "closure").exists()
    archived_model = MujocoSourceGravityBiasV1(
        bundle_root=archived_bundle, source_closure_files=closure,
        source_xml_sha256=source_xml_sha, source_closure_digest=source_closure,
        composition_plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
        mujoco_api=fake_mujoco,
    )
    assert archived_model.source_model_path.endswith("closure.tar.gz#closure/canonical-source.xml")
    assert np.array_equal(archived_model.gravity_torque(np.zeros(7)), np.zeros(7))
    assert archived_model.close()["closed"] is True


def test_task_one_controller_identity_binds_unqualified_braking_experiment():
    config = LiberoMixedControlConfigV1()
    assert config.kp_Nm_per_rad == (20.0,) * 7
    assert config.kd_Nm_s_per_rad == (4.0, 8.0, 4.0, 4.0, 4.0, 4.0, 4.0)
    assert config.gain_status == "diagnostic_unqualified_PD_20Hz_kp20_kd4_8_v6"
    controller = LiberoMixedControllerV1(config)
    receipt = controller.identity_mapping()
    assert receipt["profile_id"] == "libero-spatial-bowl-to-plate-joint-space-pd-v6"
    assert receipt["kp_Nm_per_rad"] == [20.0] * 7
    assert receipt["kd_Nm_s_per_rad"] == [4.0, 8.0, 4.0, 4.0, 4.0, 4.0, 4.0]
    assert receipt["qualification"] == "diagnostic_only_unqualified_gains"


def _boundary(task_uid: str = TASK_2) -> LiberoPredicateBoundaryV1:
    return LiberoPredicateBoundaryV1(
        task_uid=task_uid,
        source_manifest_sha256=MANIFEST_SHA,
        source_id="libero-test-source-v1:" + "c" * 64,
        source_closure_digest=CLOSURE_SHA,
        provider_materialization_id="materialization-1",
        episode_id="episode-1",
        reset_sample_id="reset-1",
        control_step=2,
        state_revision=5,
        simulation_time_s=0.1,
    )


def _region_evidence(expected_boundary: LiberoPredicateBoundaryV1, **changes) -> StoveFrontRegionEvidenceV1:
    values = {
        "boundary": expected_boundary,
        "object_name": "plate_1",
        "site_name": "main_table_stove_front_region",
        "object_position_world_m": (0.0, 0.0, 0.02),
        "site_position_world_m": (0.0, 0.0, 0.0),
        "site_mat_world": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        "site_size_m": (0.1, 0.1, 0.02),
        "site_parent_name": "main_table",
        "parent_geom_group_contact": True,
    }
    values.update(changes)
    return StoveFrontRegionEvidenceV1(**values)


def test_open_uses_exact_source_joint_and_strict_negative_threshold():
    boundary = _boundary()
    is_open = OpenMiddleDrawerEvidenceV1(boundary, "wooden_cabinet_1.middle_level", -0.1400001)
    at_edge = OpenMiddleDrawerEvidenceV1(boundary, "wooden_cabinet_1.middle_level", -0.14)
    is_closed = OpenMiddleDrawerEvidenceV1(boundary, "wooden_cabinet_1.middle_level", -0.1399)
    assert evaluate_open_middle_drawer_v1(is_open, expected_boundary=boundary).value is True
    assert evaluate_open_middle_drawer_v1(at_edge, expected_boundary=boundary).value is False
    assert evaluate_open_middle_drawer_v1(is_closed, expected_boundary=boundary).value is False


def test_open_rejects_wrong_drawer_and_stale_state_identity():
    boundary = _boundary()
    wrong_drawer = OpenMiddleDrawerEvidenceV1(boundary, "wooden_cabinet_1.top_level", -0.2)
    stale = OpenMiddleDrawerEvidenceV1(
        replace(boundary, state_revision=boundary.state_revision - 1),
        "wooden_cabinet_1.middle_level", -0.2,
    )
    assert evaluate_open_middle_drawer_v1(wrong_drawer, expected_boundary=boundary).status == "unavailable"
    stale_result = evaluate_open_middle_drawer_v1(stale, expected_boundary=boundary)
    assert stale_result.status == "unavailable"
    assert stale_result.reason == "stale_state_boundary_identity"
    assert evaluate_open_middle_drawer_v1(None, expected_boundary=boundary).status == "unavailable"


def test_site_under_keeps_source_matrix_operand_order_and_strict_bounds():
    boundary = _boundary(TASK_3)
    identity = evaluate_stove_front_region_v1(_region_evidence(boundary), expected_boundary=boundary)
    assert identity.value is True

    # The source uses site_mat @ (object_position - site_position), directly.
    # A 90 degree frame maps world x into local y; transposing it would fail.
    rotated = _region_evidence(
        boundary,
        object_position_world_m=(0.05, 0.0, 0.02),
        site_mat_world=((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        site_size_m=(0.02, 0.1, 0.02),
    )
    assert evaluate_stove_front_region_v1(rotated, expected_boundary=boundary).value is True

    xy_edge = _region_evidence(boundary, object_position_world_m=(0.1, 0.0, 0.02))
    lower_edge = _region_evidence(boundary, object_position_world_m=(0.0, 0.0, 0.02 - 0.005))
    upper_edge = _region_evidence(boundary, object_position_world_m=(0.0, 0.0, 0.02 + 0.10))
    assert evaluate_stove_front_region_v1(xy_edge, expected_boundary=boundary).value is False
    assert evaluate_stove_front_region_v1(lower_edge, expected_boundary=boundary).value is False
    assert evaluate_stove_front_region_v1(upper_edge, expected_boundary=boundary).value is False


def test_site_under_requires_fresh_parent_contact_and_expected_site_identity():
    boundary = _boundary(TASK_3)
    stale = _region_evidence(boundary, boundary=replace(boundary, episode_id="old-episode"))
    no_contact = _region_evidence(boundary, parent_geom_group_contact=False)
    unavailable_contact = _region_evidence(boundary, parent_geom_group_contact=None)
    wrong_site = _region_evidence(boundary, site_name="main_table_stove_region")
    assert evaluate_stove_front_region_v1(stale, expected_boundary=boundary).status == "unavailable"
    assert evaluate_stove_front_region_v1(no_contact, expected_boundary=boundary).value is False
    assert evaluate_stove_front_region_v1(unavailable_contact, expected_boundary=boundary).status == "unavailable"
    assert evaluate_stove_front_region_v1(wrong_site, expected_boundary=boundary).status == "unavailable"


def test_source_bound_panda_kinematics_includes_mount_and_nested_named_tcp():
    links = "".join(
        f'<body name="robot0_link{i}" pos="0.01 0 0">'
        f'<joint name="robot0_joint{i}" axis="0 0 1" range="-2 2" limited="true"/>'
        for i in range(1, 8)
    )
    close_links = "</body>" * 7
    xml = (
        '<mujoco><compiler angle="radian"/><worldbody>'
        '<body name="mount_frame" pos="1 2 3">'
        '<body name="robot0_link0" pos="0.1 0 0">'
        + links
        + '<body name="robot0_hand" pos="0.02 0 0">'
        '<body name="tcp_mount" pos="0 0 0.03" quat="0.7071067811865476 0 0 0.7071067811865476">'
        '<site name="source_tcp" pos="0 0.04 0" quat="1 0 0 0"/>'
        '</body></body>' + close_links
        + '</body></body></worldbody></mujoco>'
    )
    profile = derive_panda_tcp_profile_v2(
        xml,
        tcp_id="mounted-panda-test/source-tcp-v1",
        hand_frame_id="robot0_hand",
        site_name="source_tcp",
    )
    model = PandaKinematics(xml, tcp_profile=profile, native_prefix="robot0_")
    pose, jacobian = model.fk_jacobian([0.0] * 7)
    assert profile.source_xml_sha256 == model.source_sha256
    assert profile.position_m == pytest.approx((-0.04, 0.0, 0.03))
    assert pose[:3, 3] == pytest.approx((1.15, 2.0, 3.03))
    assert jacobian.shape == (6, 7)
    assert np.isfinite(jacobian).all()
    bad_profile = replace(profile, source_xml_sha256="d" * 64)
    with pytest.raises(ValueError, match="different MJCF bytes"):
        PandaKinematics(xml, tcp_profile=bad_profile, native_prefix="robot0_")

    from task_env.artifacts import PoseWorld
    from task_env.controllers.canonical import CanonicalPandaController
    from task_env.utils.rotation import matrix_to_quat_wxyz

    controller = CanonicalPandaController(model, artifact_hash="test-artifact")
    current_quaternion = matrix_to_quat_wxyz(pose[:3, :3])
    current_pose = PoseWorld(
        tuple(float(value) for value in pose[:3, 3]),
        tuple(float(value) for value in current_quaternion),
    )
    goal_a = np.concatenate((pose[:3, 3] + np.asarray((0.0, 0.01, 0.0)), current_quaternion))
    goal_b = np.concatenate((pose[:3, 3] + np.asarray((0.0, 0.02, 0.0)), current_quaternion))
    arm_a = controller.resolve_world_pose_target_v1(
        current_joint_position_rad=(0.0,) * 7, current_pose_world=current_pose,
        target_pose_world=goal_a, gripper_scalar=0.0,
    )
    arm_b = controller.resolve_world_pose_target_v1(
        current_joint_position_rad=(0.0,) * 7, current_pose_world=current_pose,
        target_pose_world=goal_b, gripper_scalar=0.0,
    )
    assert arm_a.schema_version == "canonical-arm-target-v1"
    assert arm_a.arm_joint_order == arm_b.arm_joint_order
    assert not np.allclose(arm_a.joint_position_rad, arm_b.joint_position_rad)
    assert arm_a.canonical_action.resolved_world_pose.position == pytest.approx(goal_a[:3])
    iterative = controller.resolve_world_pose_target_iterative_v1(
        current_joint_position_rad=(0.0,) * 7, current_pose_world=current_pose,
        target_pose_world=goal_a, gripper_scalar=0.0,
    )
    assert iterative.diagnostics.schema_version == "canonical-arm-resolution-diagnostics-v1"
    assert iterative.diagnostics.converged is True
    assert iterative.diagnostics.position_residual_m <= iterative.diagnostics.position_tolerance_m
    assert iterative.diagnostics.orientation_residual_rad <= iterative.diagnostics.orientation_tolerance_rad
    far_goal = np.concatenate((pose[:3, 3] + np.asarray((0.0, 0.30, 0.0)), current_quaternion))
    bounded = controller.resolve_world_pose_target_iterative_v1(
        current_joint_position_rad=(0.0,) * 7, current_pose_world=current_pose,
        target_pose_world=far_goal, gripper_scalar=0.0, max_iterations=1,
    )
    assert bounded.diagnostics.iteration_count == 1
    assert bounded.diagnostics.converged is False
    assert arm_a.schema_version == "canonical-arm-target-v1"  # frozen one-step route remains available

    from task_env.controllers.canonical.controller import absolute_joint_position_servo
    from bench_deploy.libero.controller import LiberoMixedControllerV3

    with pytest.raises(ValueError, match="canonical named Panda joint order"):
        replace(arm_a, arm_joint_order=tuple(reversed(arm_a.arm_joint_order))).validate()
    nonzero_q = np.asarray((0.025, -0.035, 0.045, -0.055, 0.065, -0.075, 0.085))
    nonzero_transform, _ = model.fk_jacobian(nonzero_q)
    nonzero_pose = PoseWorld(
        tuple(float(value) for value in nonzero_transform[:3, 3]),
        tuple(float(value) for value in matrix_to_quat_wxyz(nonzero_transform[:3, :3])),
    )
    multi_goal = np.concatenate((
        np.asarray(nonzero_pose.position) + np.asarray((0.0, 0.025, 0.0)),
        np.asarray(nonzero_pose.quaternion_wxyz),
    ))
    iterative_multi = controller.resolve_world_pose_target_iterative_v1(
        current_joint_position_rad=tuple(map(float, nonzero_q)),
        current_pose_world=nonzero_pose, target_pose_world=multi_goal,
        gripper_scalar=0.0, max_iterations=6,
        position_tolerance_m=1e-8, orientation_tolerance_rad=1e-8,
    )
    iterative_profile_identity = controller.iterative_resolution_identity_v1(
        max_iterations=6, position_tolerance_m=1e-8,
        orientation_tolerance_rad=1e-8,
    )
    matching_consumer = LiberoMixedControllerV3(
        arm_resolver_identity=iterative_profile_identity,
    )
    assert matching_consumer.map_arm_target_to_control_order(
        iterative_multi.target,
    ) == pytest.approx(iterative_multi.target.joint_position_rad)
    wrong_consumer = LiberoMixedControllerV3(arm_resolver_identity="a" * 64)
    with pytest.raises(ValueError, match="resolver identity or named joint order"):
        wrong_consumer.map_arm_target_to_control_order(iterative_multi.target)
    assert iterative_multi.diagnostics.iteration_count > 1
    expected_desired, expected_servo = absolute_joint_position_servo(
        iterative_multi.target.joint_position_rad, nonzero_q, model.limits,
        controller.config.joint_position_correction_gain,
    )
    assert iterative_multi.target.joint_position_rad == pytest.approx(expected_desired)
    assert iterative_multi.target.servo_position_rad == pytest.approx(expected_servo)
    assert iterative_multi.diagnostics.initial_position_gap_m == pytest.approx(0.0, abs=1e-12)
    assert iterative_multi.diagnostics.model_position_tolerance_m == pytest.approx(0.003)
