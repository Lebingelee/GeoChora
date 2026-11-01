"""Provider-free source-predicate tests for the three required LIBERO tasks."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from bench_deploy.libero.tasks.predicates import (
    LiberoPredicateBoundaryV1,
    OpenMiddleDrawerEvidenceV1,
    StoveFrontRegionEvidenceV1,
    evaluate_open_middle_drawer_v1,
    evaluate_stove_front_region_v1,
)
from bench_deploy.libero.controllers.osc import (
    LiberoMixedControlConfigV1,
    LiberoMixedControllerV1,
)
from bench_deploy.libero.artifacts.contracts import TASK_2, TASK_3
from bench_deploy.libero.tasks.solution import (
    LiberoPickPlaceSolutionConfigV1, solution_identity_v8,
)
from task_env.controllers.canonical.kinematics import (
    PandaKinematics,
    derive_panda_tcp_profile_v2,
)


MANIFEST_SHA = "a" * 64
CLOSURE_SHA = "b" * 64


def test_task_one_solution_v8_identity_binds_source_resolver_and_motion_config():
    config = LiberoPickPlaceSolutionConfigV1()
    values = dict(
        source_xml_sha256="f" * 64,
        source_closure_digest="e" * 64,
        arm_resolver_identity="d" * 64,
    )
    identity = solution_identity_v8(**values, config=config)
    assert len(identity) == 64
    assert identity == solution_identity_v8(**values, config=config)
    assert identity != solution_identity_v8(
        **{**values, "source_closure_digest": "c" * 64}, config=config,
    )
    assert identity != solution_identity_v8(
        **{**values, "arm_resolver_identity": "b" * 64}, config=config,
    )
    stricter_tolerance = replace(config, position_tolerance_m=0.010)
    assert identity != solution_identity_v8(**values, config=stricter_tolerance)


def test_independent_reader_reset_pose_match_uses_runtime_numeric_tolerance():
    from bench_deploy.libero.trajectory.worker import _pose_world_mapping_matches

    expected = {
        "fixture": {
            "position": [0.032160686061349086, -0.26769535926827864, 0.905],
            "quaternion_wxyz": [0.21813924162729167, 0.0, 0.0, 0.9759176559844944],
        },
    }
    mujoco_forward = {
        "fixture": {
            "position": [0.032160686061349086, -0.26769535926827864, 0.905],
            "quaternion_wxyz": [0.2181392416272917, 0.0, 0.0, 0.9759176559844945],
        },
    }
    assert _pose_world_mapping_matches(mujoco_forward, expected)
    sign_equivalent = {
        "fixture": {
            "position": expected["fixture"]["position"],
            "quaternion_wxyz": [-value for value in expected["fixture"]["quaternion_wxyz"]],
        },
    }
    assert _pose_world_mapping_matches(sign_equivalent, expected)
    outside_tolerance = {
        "fixture": {
            "position": [expected["fixture"]["position"][0] + 1.1e-12,
                         *expected["fixture"]["position"][1:]],
            "quaternion_wxyz": expected["fixture"]["quaternion_wxyz"],
        },
    }
    assert not _pose_world_mapping_matches(outside_tolerance, expected)
    assert not _pose_world_mapping_matches({}, expected)


def test_optional_rim_controller_bounds_velocity_feedforward():
    from bench_deploy.libero.controllers.osc import LiberoMixedControllerV7

    controller = LiberoMixedControllerV7(arm_resolver_identity="d" * 64)
    clipped = controller._bound_vector(np.asarray((0.0, 0.0, 0.2)), 0.05)
    assert np.linalg.norm(clipped) == pytest.approx(0.05)
    assert clipped / np.linalg.norm(clipped) == pytest.approx((0.0, 0.0, 1.0))
    identity = controller.identity_mapping()
    assert identity["schema_version"] == "libero-mixed-controller-identity-v7"
    assert identity["desired_twist_limits"] == {
        "linear_m_s": 0.05, "angular_rad_s": 0.5,
    }


def test_solution_bilateral_contact_requires_fresh_covered_left_and_right_pairs():
    from bench_deploy.libero.tasks.solution import LiberoPickPlaceSolutionV8

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
    assert LiberoPickPlaceSolutionV8._bilateral_finger_contact(info) == (
        True, (1, 2), "available",
    )
    one_sided = {**contact, "pair_counts": {"/".join(left): 1, "/".join(right): 0}}
    assert LiberoPickPlaceSolutionV8._bilateral_finger_contact(
        {**info, "contact_summary_v2": one_sided},
    )[:2] == (False, (1, 0))
    stale = {**contact, "state_revision": 2}
    assert LiberoPickPlaceSolutionV8._bilateral_finger_contact(
        {**info, "contact_summary_v2": stale},
    )[2] == "contact_summary_stale_or_wrong_boundary"


def test_source_closure_archive_reads_only_manifest_members_and_rejects_tampering(tmp_path):
    import hashlib
    import io
    import tarfile

    from bench_deploy.libero.controllers.source_gravity import read_source_closure_archive

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


def test_source_gravity_model_uses_verified_closure_and_releases_lowest_primitive(tmp_path):
    import hashlib
    import io
    import json
    from pathlib import Path
    import tarfile
    from types import SimpleNamespace

    from bench_deploy.libero.controllers.source_gravity import MujocoSourceGravityBiasV1
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
    from bench_deploy.libero.controllers.osc import LiberoMixedControllerV6

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
    matching_consumer = LiberoMixedControllerV6(
        arm_resolver_identity=iterative_profile_identity,
    )
    assert matching_consumer.map_arm_target_to_control_order(
        iterative_multi.target,
    ) == pytest.approx(iterative_multi.target.joint_position_rad)
    wrong_consumer = LiberoMixedControllerV6(arm_resolver_identity="a" * 64)
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
