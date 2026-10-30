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
    solution_identity_v1,
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


def test_task_one_controller_identity_binds_unqualified_braking_experiment():
    config = LiberoMixedControlConfigV1()
    assert config.kp_Nm_per_rad == (100.0,) * 7
    assert config.kd_Nm_s_per_rad == (20.0, 40.0, 20.0, 20.0, 20.0, 20.0, 20.0)
    assert config.gain_status == "diagnostic_unqualified_PD_20Hz_kp100_kd2_40_v3"
    controller = LiberoMixedControllerV1(config)
    receipt = controller.identity_mapping()
    assert receipt["profile_id"] == "libero-spatial-bowl-to-plate-joint-space-pd-v3"
    assert receipt["kp_Nm_per_rad"] == [100.0] * 7
    assert receipt["kd_Nm_s_per_rad"] == [20.0, 40.0, 20.0, 20.0, 20.0, 20.0, 20.0]
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
