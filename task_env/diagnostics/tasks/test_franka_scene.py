"""Task-data/resource/protocol contracts; these tests do not run physics or models."""

from collections import Counter
from copy import deepcopy
import hashlib
import json

import pytest

from bench_deploy.tablecraft import (
    get_task, list_tasks, model_prompt, prepare_assets, prepare_terminal_review,
    reference_files, scene_resources, task_source,
)
from bench_deploy.tablecraft import scene, solution, task
from bench_deploy.tablecraft.cli import main


TASK_IDS = tuple(item["task_id"] for item in list_tasks())
REFERENCE_IDS = {
    "fsc2-ball-into-middle", "fsc2-flip-then-store", "fsc2-nearest-brick",
    "fsc2-perpendicular-front", "fsc2-selective-retrieval", "fsc2-store-close",
}


def test_fifty_frozen_task_lines_keep_source_order_ids_and_hashes():
    source = task._source()
    task_bytes = (task.PACKAGE / "tasks.jsonl").read_bytes()
    rows = task_bytes.splitlines()
    assert source["dataset_id"] == "franka-scene-50"
    assert source["release_version"] == "2.0.0"
    assert source["release_digest"] == "24209666f42a14ce7919f3483410d5ac7f4e839d9c50d39d26a93ec25eea2a12"
    assert source["manifest_sha256"] == "f03908a1e653413620ace37257ff899ac8c6f7e3962ce25fc395963835ec8014"
    assert hashlib.sha256(task_bytes).hexdigest() == source["source_tasks_sha256"] == (
        "de01f5a60e77a605558422d63e790340ad4acb83688d727730076486240c5980"
    )
    assert len(TASK_IDS) == len(set(TASK_IDS)) == len(rows) == source["task_count"] == 50
    for listed, line in zip(list_tasks(), rows, strict=True):
        record = json.loads(line)
        task_id = record["task_id"]
        assert listed["task_id"] == task_id
        assert listed["title"] in record["prompt"]
        assert any(ord(char) > 127 for char in listed["title"])
        assert listed["family"] == record["tags"][-1]
        assert record["schema_version"] == "low-detail-task/1.2.0"
        assert hashlib.sha256(line).hexdigest() == source["tasks"][task_id]["source_line_sha256"]
        assert get_task(task_id) == record
    assert {task_id for task_id, item in source["tasks"].items() if item["reference"]} == REFERENCE_IDS
    assert source["reference_count"] == len(REFERENCE_IDS)
    assert source["reference_validation"]["status_counts"] == {
        "fail": 0, "not_run": 50, "pass": 0, "pending": 0, "unsupported": 0,
    }


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_public_input_does_not_expose_truth_and_reads_are_independent(task_id):
    public = model_prompt(task_id)
    full = get_task(task_id)
    assert "truth" not in public
    assert public == {key: value for key, value in full.items() if key != "truth"}
    full["truth"]["acceptance"].clear()
    full["truth"]["goal"].clear()
    public["resources"].clear()
    assert get_task(task_id)["truth"]["acceptance"]["behaviors"]
    assert get_task(task_id)["truth"]["goal"]
    assert model_prompt(task_id)["resources"]


def test_unknown_task_and_tampered_task_file_are_rejected(tmp_path, monkeypatch):
    with pytest.raises(KeyError):
        get_task("not-a-task")
    (tmp_path / "source.json").write_bytes((task.PACKAGE / "source.json").read_bytes())
    (tmp_path / "tasks.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(task, "PACKAGE", tmp_path)
    with pytest.raises(ValueError, match="source bytes changed"):
        get_task(TASK_IDS[0])


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_review_reuses_generic_protocol_with_all_original_requirements(task_id):
    endpoint = {"episode_id": "synthetic-episode", "endpoint_id": "actual-end",
                "asset_family": "franka-scene", "valid": True, "time_s": 3.0}
    evidence = [{"id": "state", "kind": "raw_state", "path": "state.json",
                 "sha256": "a" * 64, "episode_id": "synthetic-episode", "endpoint_id": "actual-end"}]
    request = prepare_terminal_review(task_id, endpoint,
        model_profile={"name": "synthetic-fixture", "reasoning_effort": "none"}, evidence=evidence)
    assert request["schema_version"] == "terminal-source-review-request/0.1"
    assert request["source"] == task_source(task_id)
    assert request["source"]["task"] == get_task(task_id)
    record = request["source"]["task"]
    setup_id = next(resource["id"] for resource in record["resources"] if resource["type"] == "initial_state")
    expected = {
        "/task/prompt", "/task/truth/acceptance", "/task/truth/goal",
        "/dependencies/scene_contract", "/dependencies/object_manifest",
        "/dependencies/predicate_vocabulary", f"/dependencies/{setup_id}",
    }
    expected.update(f"/task/truth/{key}" for key in ("bind", "process") if key in record["truth"])
    assert set(request["required_source_pointers"]) == expected
    assert request["endpoint"] == endpoint
    assert request["evidence"] == evidence
    assert "terminal" not in request and "task_success" not in request


def test_authored_setup_preserves_each_tasks_open_drawers():
    positions_by_setup = {
        "setup_all_closed": (0.0, 0.0, 0.0), "setup_middle_open": (0.0, -0.18, 0.0),
        "setup_lower_open": (-0.18, 0.0, 0.0), "setup_top_open": (0.0, 0.0, -0.18),
        "setup_all_open": (-0.18, -0.18, -0.18),
    }
    setups = Counter()
    for task_id in TASK_IDS:
        source = task_source(task_id)
        setup_id = next(item["id"] for item in source["task"]["resources"] if item["type"] == "initial_state")
        setups[setup_id] += 1
        dependencies = source["dependencies"]
        assert set(dependencies) == {"scene_contract", "object_manifest", "predicate_vocabulary", setup_id}
        assert dependencies[setup_id]["initial_drawer_joint_positions_m"] == dict(zip(
            ("drawer_1", "drawer_2", "drawer_3"), positions_by_setup[setup_id], strict=True,
        ))
    assert setups == {
        "setup_all_closed": 32, "setup_middle_open": 9, "setup_lower_open": 7,
        "setup_top_open": 1, "setup_all_open": 1,
    }


def test_cli_prepares_existing_paired_review_without_calling_a_model(tmp_path, capsys):
    """Exercise the real file transport with synthetic observations, no opinions."""
    raw = tmp_path / "state.json"
    raw.write_text('{"synthetic_fixture": true}', encoding="utf-8")
    endpoint = {"episode_id": "synthetic-episode", "endpoint_id": "actual-end",
                "asset_family": "franka-scene", "valid": True, "time_s": 3.0}
    bundle = {"endpoint": endpoint, "evidence": [{
        "id": "state", "kind": "raw_state", "path": raw.name,
        "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "episode_id": endpoint["episode_id"], "endpoint_id": endpoint["endpoint_id"],
    }]}
    bundle_path = tmp_path / "evidence.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    profiles = []
    for name in ("judge", "verifier"):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"name": f"synthetic-{name}", "reasoning_effort": "none"}),
                        encoding="utf-8")
        profiles.append(path)
    output = tmp_path / "review"
    assert main(["prepare-review", TASK_IDS[0], "--evidence-bundle", str(bundle_path),
                 "--artifact-root", str(tmp_path), "--judge-profile", str(profiles[0]),
                 "--verifier-profile", str(profiles[1]), "--output-directory", str(output)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["schema_version"] == "terminal-source-run/0.1"
    assert plan["original_request"]["source"] == task_source(TASK_IDS[0])
    assert plan["task_success"] is None
    assert (output / "judge/input.json").is_file()
    assert not (output / "run-result.json").exists()


@pytest.fixture
def release(tmp_path, monkeypatch):
    """Small synthetic resource bytes exercise copying, not asset/runtime support."""
    root = tmp_path / "release"
    (root / "resources").mkdir(parents=True)
    source = deepcopy(task._source())
    (root / "manifest.json").write_text("synthetic manifest", encoding="utf-8")
    for name in ("tasks.jsonl", "LICENSE.txt"):
        (root / name).write_bytes((task.PACKAGE / name).read_bytes())
    for item in source["resources"].values():
        target = root / item["path"]
        bundled = task.PACKAGE / item["path"]
        if bundled.is_file():
            target.write_bytes(bundled.read_bytes())
        else:
            target.write_text("synthetic resource: " + target.name, encoding="utf-8")
        item["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    for key, name in (("manifest_sha256", "manifest.json"), ("source_tasks_sha256", "tasks.jsonl"),
                      ("license_sha256", "LICENSE.txt")):
        source[key] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    monkeypatch.setattr(scene, "_source", lambda: deepcopy(source))
    return root, source


def test_resources_are_shared_portable_and_existing_output_is_preserved(release, tmp_path):
    root, source = release
    output = prepare_assets(root, tmp_path / "assets")
    assert (output / "tasks.jsonl").read_bytes() == (task.PACKAGE / "tasks.jsonl").read_bytes()
    resources = [scene_resources(task_id, output) for task_id in TASK_IDS]
    for name in ("scene", "panda_model", "scene_contract", "object_manifest", "predicate_vocabulary"):
        paths = {result["paths"][name] for result in resources}
        assert paths == {output / source["resources"][name]["path"]}
    for result in resources:
        dependencies = task_source(result["task_id"])["dependencies"]
        setup_id = next(key for key in dependencies if key.startswith("setup_"))
        assert result["setup"] == dependencies[setup_id]
        assert result["scene_contract"] == dependencies["scene_contract"]
        assert result["object_manifest"] == dependencies["object_manifest"]
        assert result["predicate_vocabulary"] == dependencies["predicate_vocabulary"]
    assert all((output / item["path"]).is_file() for item in source["resources"].values())
    with pytest.raises(FileExistsError):
        prepare_assets(root, output)
    assert (output / "resources/scene.usdc").read_bytes() == (root / "resources/scene.usdc").read_bytes()


@pytest.mark.parametrize("relative", [
    "manifest.json", "tasks.jsonl", "resources/scene.usdc", "resources/scene-predicates-v1.yaml",
])
def test_changed_source_is_rejected_before_creating_asset_output(release, tmp_path, relative):
    root, _ = release
    (root / relative).write_bytes(b"changed")
    output = tmp_path / "assets"
    with pytest.raises(ValueError, match="source bytes changed"):
        prepare_assets(root, output)
    assert not output.exists()


def test_changed_prepared_scene_cannot_be_used(release, tmp_path):
    root, _ = release
    output = prepare_assets(root, tmp_path / "assets")
    (output / "resources/scene.usdc").write_bytes(b"changed")
    with pytest.raises(ValueError, match="source bytes changed"):
        scene_resources(TASK_IDS[0], output)


def test_reference_lookup_binds_the_full_source_task_and_never_executes_code(tmp_path, monkeypatch):
    metadata = deepcopy(task._source())
    record = get_task(TASK_IDS[0])
    (tmp_path / "demo.py").write_text("raise RuntimeError('must not execute')", encoding="utf-8")
    (tmp_path / "snapshot.json").write_text(json.dumps(record), encoding="utf-8")
    metadata["tasks"][TASK_IDS[0]]["reference"] = {
        key: {"path": name, "sha256": hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()}
        for key, name in (("demo", "demo.py"), ("task_snapshot", "snapshot.json"))
    }
    monkeypatch.setattr(solution, "_source", lambda: metadata)
    assert reference_files(TASK_IDS[0], tmp_path)["demo"] == tmp_path / "demo.py"
    record["truth"]["goal"] = {"all": []}
    (tmp_path / "snapshot.json").write_text(json.dumps(record), encoding="utf-8")
    metadata["tasks"][TASK_IDS[0]]["reference"]["task_snapshot"]["sha256"] = hashlib.sha256(
        (tmp_path / "snapshot.json").read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="different task"):
        reference_files(TASK_IDS[0], tmp_path)


def test_task_without_recorded_reference_is_explicit_and_still_available(tmp_path):
    task_id = "fsc2-only-middle-open"
    assert get_task(task_id)["truth"]["acceptance"]["behaviors"]
    assert task_source(task_id)["dependencies"]["setup_all_open"]
    with pytest.raises(FileNotFoundError, match="no recorded reference execution"):
        reference_files(task_id, tmp_path)
