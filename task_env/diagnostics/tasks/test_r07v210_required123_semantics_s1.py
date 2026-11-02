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
from bench_deploy.libero.artifacts.contracts import TASK_1, TASK_2, TASK_3
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
    assert identity == "b8291a086579f57fa4b9ede5d29435e10af65fb6f5f8e3ac4369301ce32b3598"
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

    from task_env.assembly.assets import _read_source_closure_archive

    read_source_closure_archive = _read_source_closure_archive

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


def test_source_gravity_model_uses_verified_closure_and_releases_lowest_primitive(tmp_path, monkeypatch):
    import hashlib
    import json
    from types import SimpleNamespace

    from bench_deploy.libero.controllers.source_gravity import MujocoSourceGravityBiasV1
    from task_env.runtime.sessions.source import ExecutionSourceReceiptV1

    xml = b'<mujoco><worldbody/></mujoco>'
    expected_model_xml = xml
    closure = {
        "canonical-source.xml": xml,
        "scene.xml": xml,
        "upstream/example.bin": b"source asset bytes",
    }
    plan = {
        "identity": {"task_uid": "libero_spatial/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate"},
        "output": {"composed_mjcf_sha256": hashlib.sha256(xml).hexdigest()},
    }
    plan_bytes = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    source_receipt = ExecutionSourceReceiptV1.create(
        source_id="libero-source-gravity-test-v1", canonical_xml=xml,
        importer_xml=xml, closure_files=closure,
    )

    class FakeModel:
        nq = nv = njnt = 7
        nbody, nsite = 8, 1
        qpos0 = np.zeros(7)
        jnt_qposadr = np.arange(7)
        jnt_dofadr = np.arange(7)

        @classmethod
        def from_xml_string(cls, source_xml, assets):
            assert source_xml.encode("utf-8") == expected_model_xml
            if expected_model_xml == xml:
                assert assets == {"upstream/example.bin": b"source asset bytes"}
            else:
                assert assets == {}
            return cls()

    class FakeData:
        def __init__(self, model):
            self.qpos = np.zeros(model.nq)
            self.qvel = np.zeros(model.nv)
            self.qfrc_bias = np.zeros(model.nv)
            self.qM = np.zeros(model.nv * (model.nv + 1) // 2)
            self.site_xpos = np.zeros((model.nsite, 3))
            self.site_xmat = np.eye(3).reshape(1, 9)

    def fake_name2id(model, obj_type, name):
        if obj_type == 1:
            assert name == "gripper0_grip_site"
            return 0
        assert obj_type == 0
        return int(name[-1]) - 1

    def fake_forward(model, data):
        data.qfrc_bias[:] = data.qpos
        data.site_xpos[0] = data.qpos[:3]

    def fake_full_mass(model, destination, _qM):
        destination[:] = np.eye(model.nv)

    def fake_jacobian(_model, _data, jacp, jacr, _site_id):
        jacp[0, 0] = 1.0
        jacr[0, 1] = 1.0

    fake_mujoco = SimpleNamespace(
        __version__="3.8.1", mj_version=lambda: 3008001,
        MjModel=FakeModel, MjData=FakeData,
        mjtObj=SimpleNamespace(mjOBJ_JOINT=0, mjOBJ_SITE=1),
        mj_name2id=fake_name2id, mj_forward=fake_forward,
        mj_fullM=fake_full_mass, mj_jacSite=fake_jacobian,
    )
    model = MujocoSourceGravityBiasV1(
        source_receipt=source_receipt, composition_plan_bytes=plan_bytes,
        mujoco_api=fake_mujoco,
    )
    state = model.operational_space_state_v2(
        np.arange(7, dtype=np.float64), np.zeros(7),
    )
    assert np.array_equal(state["qfrc_bias_arm_Nm"], np.arange(7))
    assert state["mass_matrix_arm"].shape == (7, 7)
    assert model.forward_calls == 1
    close = model.close()
    assert close["closed"] and close["model_released"] and close["data_released"]
    assert model.close_receipt is close
    assert close["mj_step_call_count"] == 0
    with pytest.raises(RuntimeError, match="closed"):
        model.operational_space_state_v2(np.zeros(7), np.zeros(7))
    source_receipt.close()

    from bench_deploy.libero.assembly import model_profile
    from bench_deploy.libero.assembly.model_profile import ROBOT_MODEL_PROFILE_V3_ID

    profiled_xml = b'<mujoco model="profiled"><worldbody/></mujoco>'
    raw_xml = b'<mujoco model="raw"><worldbody/></mujoco>'
    expected_model_xml = profiled_xml
    profile = {
        "profile_id": ROBOT_MODEL_PROFILE_V3_ID,
        "raw_source_xml_sha256": hashlib.sha256(raw_xml).hexdigest(),
        "runtime_model_xml_sha256": hashlib.sha256(profiled_xml).hexdigest(),
    }
    profile_bytes = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    monkeypatch.setattr(
        model_profile, "normalize_libero_robosuite_model_xml_v3",
        lambda source: (profiled_xml, profile),
    )
    profiled_receipt = ExecutionSourceReceiptV1.create(
        source_id="libero-profiled-source-gravity-test-v1",
        canonical_xml=profiled_xml, importer_xml=profiled_xml,
        closure_files={"canonical-source.xml": profiled_xml},
    )
    profiled_plan = {
        "identity": {"task_uid": TASK_1},
        "output": {"composed_mjcf_sha256": hashlib.sha256(raw_xml).hexdigest()},
    }
    profiled_model = MujocoSourceGravityBiasV1(
        source_receipt=profiled_receipt,
        composition_plan_bytes=json.dumps(
            profiled_plan, sort_keys=True, separators=(",", ":"),
        ).encode(),
        mujoco_api=fake_mujoco, raw_source_xml_bytes=raw_xml,
        model_profile_bytes=profile_bytes,
    )
    assert profiled_model.model_profile_id == ROBOT_MODEL_PROFILE_V3_ID
    assert profiled_model.raw_source_xml_sha256 == hashlib.sha256(raw_xml).hexdigest()
    assert profiled_model.close()["closed"]
    profiled_receipt.close()

    tampered_receipt = ExecutionSourceReceiptV1.create(
        source_id="libero-source-gravity-tamper-test-v1", canonical_xml=xml,
        importer_xml=xml, closure_files=closure,
    )
    source_path = tampered_receipt.snapshot_root / "canonical-source.xml"
    source_path.chmod(0o644)
    source_path.write_bytes(b"<mujoco model='tampered'/>")
    with pytest.raises(ValueError, match="snapshot bytes changed"):
        MujocoSourceGravityBiasV1(
            source_receipt=tampered_receipt, composition_plan_bytes=plan_bytes,
            mujoco_api=fake_mujoco,
        )
    tampered_receipt.close()


def test_source_gravity_disambiguates_duplicate_asset_basenames_without_changing_bytes():
    import xml.etree.ElementTree as ET

    from bench_deploy.libero.controllers.source_gravity import (
        _mujoco_source_asset_name_projection,
    )

    source_xml = (
        b'<mujoco><compiler meshdir="meshes"/><asset>'
        b'<mesh name="cabinet" file="cabinet/metal.png"/>'
        b'<mesh name="stove" file="stove/metal.png"/>'
        b'</asset><worldbody/></mujoco>'
    )
    closure_assets = {
        "meshes/cabinet/metal.png": b"cabinet texture bytes",
        "meshes/stove/metal.png": b"stove texture bytes",
    }

    compiled_xml, compiled_assets, projection_sha = _mujoco_source_asset_name_projection(
        source_xml, closure_assets,
    )

    root = ET.fromstring(compiled_xml)
    names = [node.get("file") for node in root.iter("mesh")]
    assert len(names) == 2 and len(set(names)) == 2
    assert all(name.startswith("geochora-source-") for name in names)
    assert len({path.rsplit("/", 1)[-1] for path in compiled_assets}) == 2
    assert sorted(compiled_assets.values()) == sorted(closure_assets.values())
    assert source_xml == (
        b'<mujoco><compiler meshdir="meshes"/><asset>'
        b'<mesh name="cabinet" file="cabinet/metal.png"/>'
        b'<mesh name="stove" file="stove/metal.png"/>'
        b'</asset><worldbody/></mujoco>'
    )
    assert isinstance(projection_sha, str) and len(projection_sha) == 64


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
