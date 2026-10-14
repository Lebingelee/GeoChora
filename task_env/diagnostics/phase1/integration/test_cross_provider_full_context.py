"""Provider-profile admission for the P1.8 cross-provider FULL runner."""

import json
from pathlib import Path

from task_env.diagnostics.phase1.integration.grasp_height_probe import context as base_context
from task_env.diagnostics.phase1.integration.lifecycle_full import (
    _validate_cross_provider_contract,
    context,
)


CONTRACT_PATH = (
    Path(__file__).resolve().parents[4] / "docs/module/task_env/p1_8_integration"
    / "cross_provider_acceptance_v2_20261014/acceptance_contract.json"
)
CANDIDATE = "guarded-primary-readiness-alternative-8n-v2-v5-clearance"


def test_geo_and_mujoco_context_share_task_controller_and_solution_contract():
    contract = json.loads(CONTRACT_PATH.read_text())
    base = base_context(50)
    geo = context(50, CANDIDATE, provider="geophys")
    mujoco = context(50, CANDIDATE, provider="mujoco")

    assert geo["artifact"].identity_hash == mujoco["artifact"].identity_hash
    assert geo["artifact"].identity_hash == base["artifact"].identity_hash
    assert geo["solution_identity"] == mujoco["solution_identity"]
    assert geo["controller_identity"] == mujoco["controller_identity"]
    assert geo["source"].scene_source.xml == base["source"].scene_source.xml
    assert mujoco["source"].scene_source.xml != base["source"].scene_source.xml
    assert geo["artifact"].timebase.physics_dt == 0.002
    assert geo["artifact"].timebase.control_substeps == 10
    assert geo["controller"].inner.version == "native-gripper-500hz-v1"
    assert mujoco["controller"].inner.version == "native-gripper-500hz-v1"
    assert geo["solution"].version == contract["frozen_execution"]["task_path"]

    _validate_cross_provider_contract(geo, contract)
    _validate_cross_provider_contract(mujoco, contract)
