"""B01 strict Task Source parsing remains separate from execution config and TaskArtifact."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from task_env.environment import (
    TaskSourceV1,
    adapt_legacy_recipe_task_source,
    load_task_source,
)
from task_env.environment.configuration import load_yaml_mapping


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).with_name("fixtures") / "phase_ii_b01" / "task_source_v1.yaml"
PICKCUBE_CONFIG = ROOT / "task_env" / "tasks" / "pick_cube" / "config.yaml"


def test_task_source_v1_load_is_strict_stable_and_roundtrips():
    first = load_task_source(FIXTURE)
    second = load_task_source(FIXTURE)
    assert first == second
    assert TaskSourceV1.from_mapping(first.to_mapping()) == first
    assert list(first.to_mapping()) == [
        "schema_version", "identity", "scene", "roles", "initialization", "hooks",
    ]
    assert first.to_mapping()["initialization"] is None
    assert first.to_mapping()["roles"]["target_block"]["selection"] == {
        "ids": ["red-block-a", "red-block-b"]
    }


def test_task_source_rejects_execution_fields_unknown_roles_and_invalid_hook_placement():
    raw = load_yaml_mapping(FIXTURE)

    with pytest.raises(ValueError, match="unknown Task Source fields"):
        TaskSourceV1.from_mapping({**raw, "environment": {"episode": {"horizon": 10}}})

    unknown_role_type = deepcopy(raw)
    unknown_role_type["roles"]["manipulator"]["entity_type"] = "panda-native-body"
    with pytest.raises(ValueError, match="Task Source role entity_type"):
        TaskSourceV1.from_mapping(unknown_role_type)

    malformed_selection = deepcopy(raw)
    malformed_selection["roles"]["manipulator"]["selection"]["ids"] = "robot-left"
    with pytest.raises(TypeError, match="sequence of identifiers"):
        TaskSourceV1.from_mapping(malformed_selection)

    tag_selector = deepcopy(raw)
    tag_selector["roles"]["target_block"]["selection"] = {"tags": ["red-block"]}
    with pytest.raises(ValueError, match="explicit entity ids only"):
        TaskSourceV1.from_mapping(tag_selector)

    unknown_cardinality = deepcopy(raw)
    unknown_cardinality["roles"]["manipulator"]["cardinality"] = "one_or_more"
    with pytest.raises(ValueError, match="Task Source cardinality"):
        TaskSourceV1.from_mapping(unknown_cardinality)

    unknown_hook = deepcopy(raw)
    unknown_hook["hooks"][0]["kind"] = "controller_hook"
    with pytest.raises(ValueError, match="unsupported Task Source hook kind"):
        TaskSourceV1.from_mapping(unknown_hook)

    bad_hook_inputs = deepcopy(raw)
    bad_hook_inputs["hooks"][0]["inputs"] = "canonical_state"
    with pytest.raises(TypeError, match="sequence of identifiers"):
        TaskSourceV1.from_mapping(bad_hook_inputs)

    wrong_phase = deepcopy(raw)
    wrong_phase["hooks"][0]["evaluation_phase"] = "observation"
    with pytest.raises(ValueError, match="must declare evaluation_phase"):
        TaskSourceV1.from_mapping(wrong_phase)

    seeded_without_seed = deepcopy(raw)
    seeded_without_seed["hooks"][0]["determinism"] = "seeded"
    with pytest.raises(ValueError, match="must declare task_seed"):
        TaskSourceV1.from_mapping(seeded_without_seed)

    stateful_authoring = deepcopy(raw)
    stateful_authoring["hooks"][0].update({
        "kind": "authoring_hook",
        "evaluation_phase": "source_compile",
        "pure_or_stateful": "stateful",
    })
    with pytest.raises(ValueError, match="must be pure"):
        TaskSourceV1.from_mapping(stateful_authoring)

    duplicate_hook_stage = deepcopy(raw)
    duplicate_hook_stage["hooks"].append(deepcopy(raw["hooks"][0]))
    with pytest.raises(ValueError, match="at most one hook per declared phase"):
        TaskSourceV1.from_mapping(duplicate_hook_stage)


def test_shared_yaml_loader_rejects_duplicate_keys_before_mapping_conversion(tmp_path):
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text("schema_version: task-source-v1\nidentity: {}\nidentity: {}\n", encoding="utf-8")
    with pytest.raises(yaml.constructor.ConstructorError, match="duplicate key 'identity'"):
        load_task_source(duplicate)

    merged = tmp_path / "merged.yaml"
    merged.write_text(
        "defaults: &defaults\n  timeout: 10\nvalue:\n  <<: *defaults\n  timeout: 20\n",
        encoding="utf-8",
    )
    assert load_yaml_mapping(merged)["value"] == {"timeout": 20}


def test_pickcube_legacy_recipe_adapts_without_absorbing_environment_config():
    legacy = load_yaml_mapping(PICKCUBE_CONFIG)
    original = deepcopy(legacy)
    source = adapt_legacy_recipe_task_source(legacy)

    assert source.task_id == "pick-cube-v1"
    assert source.version == "ver_p1_6_experimental_100hz"
    assert source.scene_ref == "tabletop-v1"
    assert {role.role_id for role in source.roles} == {"agent_panda-v1", "object_cube-v1"}
    assert "environment" not in source.to_mapping()
    assert legacy == original


def test_task_source_import_and_load_do_not_import_native_providers():
    code = (
        "from task_env.environment.task_source import load_task_source; "
        f"load_task_source({str(FIXTURE)!r}); "
        "import sys; "
        "forbidden = {'geophys', 'mujoco', 'sapien', 'genesis', 'taichi'}; "
        "loaded = {name.split('.')[0] for name in sys.modules}; "
        "assert not (loaded & forbidden), sorted(loaded & forbidden)"
    )
    child_env = dict(os.environ)
    child_env["PYTHONPATH"] = str(ROOT / "GeoPhys" / "src") + os.pathsep + str(ROOT)
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=child_env,
        check=False, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_task_source_v1_keeps_b01_yaml_compatible_when_initialization_is_omitted():
    raw = load_yaml_mapping(FIXTURE)
    assert "initialization" not in raw
    parsed = TaskSourceV1.from_mapping(raw)
    assert parsed.initialization is None
    assert TaskSourceV1.from_mapping(parsed.to_mapping()) == parsed
