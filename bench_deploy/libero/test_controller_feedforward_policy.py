"""Regression checks for versioned LIBERO OSC torque compensation policies."""

import hashlib
import json

import numpy as np

from bench_deploy.libero.controller import (
    LiberoMixedControllerV4,
    LiberoMixedControllerV6,
    LiberoMixedControllerV7,
)
from bench_deploy.libero.source_gravity import (
    SOURCE_OPERATIONAL_SPACE_PROFILE_V1,
    SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
)


def _assert_identity_hash(controller):
    mapping = controller.identity_mapping()
    material = {key: value for key, value in mapping.items() if key != "identity_sha256"}
    expected = hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    assert mapping["identity_sha256"] == expected == controller.identity


def test_frozen_v4_keeps_passive_adjusted_feedforward():
    controller = LiberoMixedControllerV4()
    passive_adjusted = np.arange(7, dtype=np.float64)
    upstream_bias = passive_adjusted + 0.25

    assert np.array_equal(controller._source_feedforward_torque({
        "bias_minus_passive_arm_Nm": passive_adjusted,
        "qfrc_bias_arm_Nm": upstream_bias,
    }), passive_adjusted)
    assert controller.identity_mapping()["schema_version"] == "libero-mixed-controller-identity-v4"


def test_v6_uses_qfrc_bias_and_versions_the_source_and_controller_profiles():
    controller = LiberoMixedControllerV6()
    passive_adjusted = np.arange(7, dtype=np.float64)
    upstream_bias = passive_adjusted + 0.25
    identity = controller.identity_mapping()

    assert np.array_equal(controller._source_feedforward_torque({
        "bias_minus_passive_arm_Nm": passive_adjusted,
        "qfrc_bias_arm_Nm": upstream_bias,
    }), upstream_bias)
    assert controller._source_state_contract() == (
        "libero-source-operational-space-state-v2", SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
    )
    assert identity["schema_version"] == "libero-mixed-controller-identity-v6"
    assert identity["gravity_feedforward_source"] == "qfrc_bias_arm_Nm"
    assert identity["gravity_feedforward_receipt_field"] == "gravity_feedforward_Nm"
    _assert_identity_hash(controller)


def test_v6_official_reference_and_v7_rim_profiles_have_distinct_identities():
    official_reference = LiberoMixedControllerV6(
        nullspace_reference_joint_position_rad=np.arange(7, dtype=np.float64),
    )
    rim = LiberoMixedControllerV7()
    official_identity = official_reference.identity_mapping()
    rim_identity = rim.identity_mapping()

    assert official_identity["profile_id"] == LiberoMixedControllerV6.OFFICIAL_REFERENCE_PROFILE_ID
    assert official_identity["nullspace_reference_policy"] == (
        "robosuite_controller_initial_joint_after_set_init_state_v1"
    )
    assert rim_identity["schema_version"] == "libero-mixed-controller-identity-v7"
    assert rim_identity["gravity_feedforward_source"] == "qfrc_bias_arm_Nm"
    assert rim._source_state_contract() == (
        "libero-source-operational-space-state-v2", SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
    )
    assert rim_identity["source_state_profile_id"] == SOURCE_OPERATIONAL_SPACE_PROFILE_V2
    _assert_identity_hash(official_reference)
    _assert_identity_hash(rim)


def test_v1_and_v2_source_state_profiles_remain_separate():
    assert SOURCE_OPERATIONAL_SPACE_PROFILE_V1 != SOURCE_OPERATIONAL_SPACE_PROFILE_V2
    assert LiberoMixedControllerV4()._source_state_contract() == (
        "libero-source-operational-space-state-v1", SOURCE_OPERATIONAL_SPACE_PROFILE_V1,
    )
