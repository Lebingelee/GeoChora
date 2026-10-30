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


def test_all_ten_negative_cases_reject_at_their_inner_gate():
    rows = AUDIT.negative_cases()
    assert len(rows) == 10
    assert AUDIT.verify_negative_suite(rows)
    assert {row["status"] for row in rows} == {"REJECTED"}
    assert {row["id"] for row in rows} == {
        "missing_mesh",
        "wrong_sha",
        "wrong_revision",
        "frame_COM_mismatch",
        "degree_radian_error",
        "joint_order_permutation",
        "lost_equality_mimic",
        "lost_tendon_transmission",
        "drive_gain_force_semantic_drift",
        "forged_upstream_or_native_consumption",
    }


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
