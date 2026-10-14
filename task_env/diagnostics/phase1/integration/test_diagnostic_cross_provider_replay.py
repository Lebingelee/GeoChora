"""Small checks for canonical H5 diagnostic decoding and D0 diffs."""

import json

from task_env.diagnostics.phase1.integration.diagnostic_cross_provider_replay import (
    _first_mapping_difference,
    _parse_diagnostics,
)


def test_parse_canonical_transition_expert_diagnostics():
    state = {"stage": "descend_to_handle", "policy_id": "shadow-v1"}
    parsed = _parse_diagnostics({
        "expert_diagnostics": {
            "diagnostic_shadow_state": json.dumps(state),
            "diagnostic_shadow_stage": json.dumps("descend_to_handle"),
        }
    })

    assert parsed["diagnostic_shadow_state"] == state
    assert parsed["diagnostic_shadow_stage"] == "descend_to_handle"


def test_first_mapping_difference_reports_native_target_leaf():
    difference = _first_mapping_difference(
        {"arm_position": {"joint1": -0.7}},
        {"arm_position": {"joint1": -0.71}},
    )

    assert difference == {
        "path": "arm_position.joint1",
        "expected": -0.7,
        "actual": -0.71,
    }
