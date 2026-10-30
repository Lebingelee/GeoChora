import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("f05_source_family_audit.py")
SPEC = importlib.util.spec_from_file_location("f05_source_family_audit", MODULE_PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_strict_json_rejects_duplicate_nonfinite_and_overflow():
    with pytest.raises(ValueError, match="duplicate key"):
        AUDIT.strict_json_bytes(b'{"x":1,"x":2}', "duplicate")
    with pytest.raises(ValueError, match="non-finite JSON token"):
        AUDIT.strict_json_bytes(b'{"x":NaN}', "nan")
    with pytest.raises(ValueError, match="non-finite value"):
        AUDIT.strict_json_bytes(b'{"x":1e999}', "overflow")


def test_mjcf_inventory_keeps_effective_defaults_and_angle_units():
    source = b"""<mujoco model="synthetic"><compiler angle="degree"/><default><joint damping="2" range="-90 90"/></default><worldbody><body name="arm"><joint name="j1" type="hinge"/><geom name="g1" type="sphere" size="0.1"/></body></worldbody><actuator><position name="a1" joint="j1" kp="20" kv="3"/></actuator></mujoco>"""
    result = AUDIT.parse_mjcf_bytes(source)
    joint = result["joints"][0]
    assert joint["effective"]["damping"] == "2"
    assert joint["range_normalized"] == pytest.approx([-1.57079632679, 1.57079632679])
    assert result["compiler"]["angle"] == "degree"
    assert result["complete_xml_tree"]["tag"] == "mujoco"
    assert result["actuators"][0]["target"] == "j1"


def test_mjcf_default_degree_autolimits_and_byte_bound_include_expansion():
    source = b"""<mujoco model="synthetic"><compiler autolimits="true"/><worldbody><body name="arm"><include file="parts/joint.xml"/></body></worldbody></mujoco>"""
    included = b"""<mujocoinclude><joint name="j1" range="-90 90"/><geom name="g1" type="sphere" size="0.1"/></mujocoinclude>"""
    result = AUDIT.parse_mjcf_bytes(source, include_files={"parts/joint.xml": included})
    joint = result["joints"][0]
    assert result["compiler_effective"] == {"angle": "degree", "autolimits": True}
    assert joint["range_normalized"] == pytest.approx([-1.57079632679, 1.57079632679])
    assert joint["limited_effective"] is True
    assert result["include_expansion"][0]["resolved_path"] == "parts/joint.xml"
    with pytest.raises(ValueError, match="not present in the verified source closure"):
        AUDIT.parse_mjcf_bytes(source)


def test_fifteen_semantic_negative_cases_reject_through_report_gates():
    rows = AUDIT.negative_cases()
    assert len(rows) == 15
    assert AUDIT.verify_negative_suite(rows)
    assert {row["status"] for row in rows} == {"REJECTED"}
    assert all(row["expected_stage"] == row["actual_stage"] for row in rows)
    assert {row["id"] for row in rows} == {
        "missing_mesh",
        "wrong_sha",
        "wrong_revision",
        "frame_COM_mismatch",
        "degree_radian_error",
        "joint_address_mismatch",
        "lost_equality_mimic",
        "lost_tendon_transmission",
        "drive_gain_force_semantic_drift",
        "forged_upstream_or_native_consumption",
        "unregistered_schema_omission",
        "inertia_rotation_error",
        "limit_force_projection_order",
        "missing_required_or_broken_reference",
        "stale_clock_consumer_evidence",
    }


def test_legal_joint_traversal_permutation_is_an_explicit_bijection():
    assert AUDIT.validate_ordered_mapping(["joint1", "joint2", "joint3"], ["joint3", "joint1", "joint2"])
    with pytest.raises(ValueError, match="one-to-one"):
        AUDIT.validate_ordered_mapping(["joint1", "joint2"], ["joint1", "joint1"])


def test_complete_valid_r009_shaped_report_can_pass_inventory_and_remain_blocked():
    report = AUDIT._synthetic_semantic_report()
    status = AUDIT.validate_semantic_report(report)
    assert status["inventory_status"] == "PASS"
    assert status["readiness"] == "BLOCKED_BY_FEATURE"
    assert status["blocked_by_feature"] == sorted(AUDIT.REQUIRED_AUDIT_FEATURES)


def test_tendon_and_equality_checks_bind_relation_and_component_values():
    equality = [{"name": "mimic", "joint1": "j1", "joint2": "j2", "polycoef": [0.0, -1.0]}]
    assert AUDIT.validate_equality_mapping(
        equality,
        [{"source_name": "mimic", "joint1": "j1", "target_name": "j2", "polycoef": [0.0, -1.0]}],
    )
    with pytest.raises(ValueError, match="target relation changed"):
        AUDIT.validate_equality_mapping(
            equality,
            [{"source_name": "mimic", "joint1": "j1", "target_name": "j3", "polycoef": [0.0, -1.0]}],
        )
    tendon = [{"name": "hand", "components": [{"kind": "joint", "joint": "j1", "coef": [1.0]}]}]
    assert AUDIT.validate_tendon_mapping(
        tendon,
        [{"source_name": "hand", "components": [{"kind": "joint", "joint": "j1", "coef": [1.0]}]}],
    )
    with pytest.raises(ValueError, match="component path or ratio changed"):
        AUDIT.validate_tendon_mapping(
            tendon,
            [{"source_name": "hand", "components": [{"kind": "joint", "joint": "j2", "coef": [1.0]}]}],
        )


def test_typed_nonfinite_values_remain_explicit():
    assert AUDIT._value(float("inf")) == {"kind": "non_finite", "token": "+inf"}


def test_source_drive_oracle_clips_control_then_force_then_projects_tendon_jacobian():
    actuator = {
        "name": "gripper", "target": "split", "target_kind": "tendon",
        "gainprm": [0.01568627451, 0.0, 0.0], "biasprm": [0.0, -100.0, -10.0],
        "ctrlrange": [0.0, 255.0], "forcerange": [-100.0, 100.0],
        "ctrllimited_effective": True, "forcelimited_effective": True,
    }
    state = {
        "q_by_joint": {"finger_joint1": 0.028, "finger_joint2": 0.012},
        "dq_by_joint": {"finger_joint1": 0.01, "finger_joint2": -0.004},
        "ctrl_requested": 256.0,
    }
    row = AUDIT._source_drive_sample(actuator, state, tendon_components=[
        {"joint": "finger_joint1", "coef": [0.5]},
        {"joint": "finger_joint2", "coef": [0.5]},
    ])
    assert row["ctrl_used_after_control_limit"] == 255.0
    assert row["generalized_length_or_position"] == pytest.approx(0.02)
    assert row["generalized_rate"] == pytest.approx(0.003)
    assert row["raw_scalar_actuator_force_before_force_limit"] == pytest.approx(1.97000000005)
    assert row["projected_joint_forces"]["finger_joint1"] == pytest.approx(0.985000000025)
    assert row["projected_joint_forces"]["finger_joint2"] == pytest.approx(0.985000000025)
    saturated = AUDIT._source_drive_sample(actuator, {
        "q_by_joint": {"finger_joint1": -0.1, "finger_joint2": -0.1},
        "dq_by_joint": {"finger_joint1": -10.0, "finger_joint2": -10.0},
        "ctrl_requested": 0.0,
    }, tendon_components=[
        {"joint": "finger_joint1", "coef": [0.5]},
        {"joint": "finger_joint2", "coef": [0.5]},
    ])
    assert saturated["raw_scalar_actuator_force_before_force_limit"] == pytest.approx(110.0)
    assert saturated["scalar_actuator_force_after_force_limit"] == 100.0
    assert saturated["projected_joint_forces"] == {"finger_joint1": 50.0, "finger_joint2": 50.0}


def test_independent_normalization_oracle_rotates_full_tensor_and_parallel_axis_term():
    source = b"""<mujoco><worldbody><body name=\"rot\"><inertial mass=\"2\" pos=\"1 0 0\" quat=\"0.7071067811865476 0 0 0.7071067811865475\" diaginertia=\"1 2 3\"/><joint name=\"hinge\" axis=\"1 0 0\"/></body></worldbody></mujoco>"""
    mjcf = AUDIT.parse_mjcf_bytes(source)
    oracle = AUDIT._normalization_oracle(mjcf, {"prims": [], "prim_count": 0}, {}, {})
    inertial = oracle["bodies"][0]["inertia_normalization"]
    assert [value for row in inertial["inertia_at_COM_body_frame_kg_m2"] for value in row] == pytest.approx([2, 0, 0, 0, 1, 0, 0, 0, 3])
    assert [value for row in inertial["inertia_about_body_origin_body_frame_kg_m2"] for value in row] == pytest.approx([2, 0, 0, 0, 3, 0, 0, 0, 5])
    assert oracle["joints"][0]["world_axis_q0"] == pytest.approx([1, 0, 0])


def test_geom_inventory_binds_source_body_group_kind_and_collision_schema_counts():
    source = b"""<mujoco><asset><mesh name=\"part\" file=\"part.stl\"/></asset><worldbody><body name=\"arm\"><geom name=\"visual\" type=\"mesh\" mesh=\"part\" group=\"2\" contype=\"0\" conaffinity=\"0\"/><geom name=\"contact\" type=\"box\" size=\".1 .2 .3\" group=\"3\"/></body></worldbody></mujoco>"""
    mjcf = AUDIT.parse_mjcf_bytes(source)
    visual = {
        "path": "/panda/Geometry/arm/part", "type": "Mesh", "applied_schemas": [],
        "api_schemas": {"authored_tokens": [], "unregistered_or_unapplied_authored_tokens": []},
        "attributes": [{"name": "mjc:group", "value": 2}], "relationships": [],
    }
    collision = {
        "path": "/panda/Geometry/arm/Box", "type": "Cube",
        "applied_schemas": ["PhysicsCollisionAPI"],
        "api_schemas": {"authored_tokens": ["PhysicsCollisionAPI"], "unregistered_or_unapplied_authored_tokens": []},
        "attributes": [
            {"name": "mjc:group", "value": 3},
            {"name": "physics:collisionEnabled", "value": True},
        ], "relationships": [],
    }
    oracle = AUDIT._normalization_oracle(mjcf, {"prims": [visual, collision], "prim_count": 2}, {}, {})
    comparison = oracle["geometry_inventory_comparison"]
    assert comparison["source_geom_count"] == comparison["target_geometry_prim_count"] == 2
    assert comparison["all_bucket_counts_match"] is True
    assert comparison["all_collision_schema_counts_match_source_group"] is True
    assert comparison["all_collision_enabled_values_match_source_group"] is True
    assert all(row["static_shape_transform_contact_equivalence"] == "NOT_ESTABLISHED" for row in comparison["buckets"])

    collision["applied_schemas"] = []
    collision["attributes"][1]["value"] = False
    broken = AUDIT._normalization_oracle(mjcf, {"prims": [visual, collision], "prim_count": 2}, {}, {})
    assert broken["geometry_inventory_comparison"]["all_bucket_counts_match"] is True
    assert broken["geometry_inventory_comparison"]["all_collision_schema_counts_match_source_group"] is False
    assert broken["geometry_inventory_comparison"]["all_collision_enabled_values_match_source_group"] is False
