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
    solution_identity_v1, solution_identity_v2,
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
    import json
    from pathlib import Path
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
        assert obj_type == 0
        return int(name[-1]) - 1

    def fake_forward(model, data):
        data.qfrc_bias[:] = data.qpos

    fake_mujoco = SimpleNamespace(
        __version__="3.8.1", mj_version=lambda: 3008001,
        MjModel=FakeModel, MjData=FakeData,
        mjtObj=SimpleNamespace(mjOBJ_JOINT=0),
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


def test_task_one_controller_identity_binds_unqualified_braking_experiment():
    config = LiberoMixedControlConfigV1()
    assert config.kp_Nm_per_rad == (20.0,) * 7
    assert config.kd_Nm_s_per_rad == (4.0, 8.0, 4.0, 4.0, 4.0, 4.0, 4.0)
    assert config.gain_status == "diagnostic_unqualified_PD_20Hz_kp20_kd2_8_v4"
    controller = LiberoMixedControllerV1(config)
    receipt = controller.identity_mapping()
    assert receipt["profile_id"] == "libero-spatial-bowl-to-plate-joint-space-pd-v4"
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
