"""S1 for strict USD delivery, public consumer boundaries and independent readback."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from task_env.artifacts.contracts import (
    AssetDefinition,
    ProviderRepresentationSelectionV1,
    UsdAssetDeliveryV1,
    UsdDeliveryFileV1,
    UsdValidationReportV1,
)
from task_env.assembly.assets import _source_closure_digest
from task_env.assembly.usd_delivery import (
    load_usd_asset_delivery,
    resolve_provider_representation,
    variant_selection_hash,
)
from task_env.diagnostics.tasks.f02_usd_delivery_fixture import build_fixture


READER = Path(__file__).with_name("f02_usd_delivery_independent_reader.py")


def _read_manifest(root: Path):
    return json.loads((root / "delivery.json").read_text(encoding="utf-8"))


def _write_manifest(root: Path, delivery):
    (root / "delivery.json").write_text(json.dumps(delivery, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _read_report(root: Path, delivery):
    return json.loads((root / delivery["validation_report_path"]).read_text(encoding="utf-8"))


def _write_report_and_manifest(root: Path, delivery, report):
    report_path = root / delivery["validation_report_path"]
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    delivery["validation_report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    _write_manifest(root, delivery)


def _rebuild_closure(root: Path, delivery):
    entries = []
    file_bytes = {}
    for item in delivery["files"]:
        raw = (root / item["path"]).read_bytes()
        item["size_bytes"] = len(raw)
        item["sha256"] = hashlib.sha256(raw).hexdigest()
        file_bytes[item["path"]] = raw
        entries.append(item)
    delivery["closure_sha256"] = _source_closure_digest(file_bytes)
    return file_bytes


def _reader(root: Path):
    return subprocess.run(
        [sys.executable, str(READER), "--delivery", str(root / "delivery.json")],
        text=True,
        capture_output=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "")},
        check=False,
    )


def _tamper(root: Path, case: str):
    delivery = _read_manifest(root)
    report = _read_report(root, delivery)
    if case == "missing-entry":
        (root / delivery["entry_file"]).unlink()
        return
    if case == "missing-prim":
        delivery["entry_prim"] = "/World/Missing"
        report["entry_prim"] = delivery["entry_prim"]
        _write_report_and_manifest(root, delivery, report)
        return
    if case == "missing-variant-set":
        delivery["variant_selections"] = {"/World/Asset#missing": "high"}
        report["variant_selection_sha256"] = variant_selection_hash(delivery["variant_selections"])
        _write_report_and_manifest(root, delivery, report)
        return
    if case == "missing-variant":
        delivery["variant_selections"] = {"/World/Asset#lod": "ultra"}
        report["variant_selection_sha256"] = variant_selection_hash(delivery["variant_selections"])
        _write_report_and_manifest(root, delivery, report)
        return
    if case == "missing-dependency":
        delivery["files"] = [item for item in delivery["files"] if item["path"] != "payloads/extras.usda"]
        _rebuild_closure(root, delivery)
        report["closure_sha256"] = delivery["closure_sha256"]
        report["input_closure_sha256"] = delivery["closure_sha256"]
        report["output_closure_sha256"] = delivery["closure_sha256"]
        _write_report_and_manifest(root, delivery, report)
        return
    if case == "wrong-size":
        delivery["files"][0]["size_bytes"] += 1
        _write_manifest(root, delivery)
        return
    if case == "wrong-file-hash":
        delivery["files"][0]["sha256"] = "0" * 64
        _write_manifest(root, delivery)
        return
    if case == "dependency-changed":
        path = root / "refs/model.usda"
        path.write_bytes(path.read_bytes() + b"\n# changed dependency bytes\n")
        return
    if case == "report-wrong-source":
        report["source_asset_identity_hash"] = "0" * 64
        _write_report_and_manifest(root, delivery, report)
        return
    if case == "report-hash-mismatch":
        (root / delivery["validation_report_path"]).write_bytes(b"{}\n")
        return
    if case == "duplicate-path":
        delivery["files"].append(dict(delivery["files"][0]))
        _write_manifest(root, delivery)
        return
    if case == "path-traversal":
        delivery["files"][0]["path"] = "../escape.usda"
        _write_manifest(root, delivery)
        return
    if case == "remote-uri-path":
        delivery["files"][0]["path"] = "https://assets.invalid/entry.usda"
        _write_manifest(root, delivery)
        return
    if case == "bool-size":
        delivery["files"][0]["size_bytes"] = True
        _write_manifest(root, delivery)
        return
    if case == "unknown-field":
        delivery["unexpected"] = "must reject"
        _write_manifest(root, delivery)
        return
    if case == "duplicate-json-key":
        raw = (root / "delivery.json").read_text(encoding="utf-8")
        (root / "delivery.json").write_text('{"schema_version":"usd-asset-delivery-v1",' + raw.lstrip()[1:], encoding="utf-8")
        return
    if case == "nonfinite-size":
        raw = (root / "delivery.json").read_text(encoding="utf-8")
        token = '"size_bytes": '
        before, after = raw.split(token, 1)
        _, tail = after.split(",", 1)
        (root / "delivery.json").write_text(before + token + "NaN," + tail, encoding="utf-8")
        return
    if case == "symlink-escape":
        target = root / "refs/model.usda"
        outside = root.parent / "f02-reader-outside-model.usda"
        outside.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(outside)
        return
    raise AssertionError(case)


def test_advanced_import_does_not_load_provider_or_usd_modules(tmp_path):
    repo = Path(__file__).resolve().parents[3]
    code = (
        "import sys; from task_env.artifacts import UsdAssetDeliveryV1; "
        "from task_env.assembly import load_usd_asset_delivery, resolve_provider_representation; "
        "names=('isaacsim','omni','taichi','mujoco','pxr'); "
        "assert not any(m==n or m.startswith(n+'.') for m in sys.modules for n in names), "
        "[(n,[m for m in sys.modules if m==n or m.startswith(n+'.')][:5]) for n in names]"
    )
    env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PXR_PLUGINPATH_NAME"}}
    env["PYTHONPATH"] = str(repo)
    result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_contract_roundtrip_and_existing_asset_identity_are_stable(tmp_path):
    manifest_path = build_fixture(tmp_path / "delivery")
    mapping = _read_manifest(manifest_path.parent)
    decoded = UsdAssetDeliveryV1.from_mapping(mapping)
    assert decoded.to_mapping() == mapping
    old = AssetDefinition(
        schema_version="asset-definition-v1",
        asset_id="legacy-asset",
        asset_version="v1",
        source_reference="https://example.invalid/legacy",
        source_revision="r1",
    )
    expected = hashlib.sha256(json.dumps(old.to_mapping(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    assert old.identity_hash == expected
    from task_env.assembly.source import TaskSceneSource

    legacy_source = TaskSceneSource(xml="<mujoco/>", base_dir=None, source_id="legacy-source", diagnostics=())
    assert (legacy_source.xml, legacy_source.base_dir, legacy_source.source_id, legacy_source.diagnostics) == (
        "<mujoco/>", None, "legacy-source", ()
    )
    with pytest.raises((TypeError, ValueError)):
        UsdDeliveryFileV1(path="x.usda", size_bytes=True, sha256="0" * 64)
    with pytest.raises((TypeError, ValueError)):
        UsdAssetDeliveryV1.from_mapping({**mapping, "unknown": 1})


def test_real_core_loader_resolver_catalog_and_mock_asset_boundary(tmp_path):
    manifest = build_fixture(tmp_path / "first-root")
    with pytest.raises(ValueError, match="production upstream-verified gate"):
        load_usd_asset_delivery(manifest)
    loaded = load_usd_asset_delivery(manifest, allow_synthetic=True)
    assert loaded.source_verified is False
    assert loaded.inspection["dependency_layer_count"] == 5
    assert loaded.inspection["asset_dependency_count"] == 1
    assert loaded.inspection["unresolved_count"] == 0

    geophys_src = Path(__file__).resolve().parents[3] / "GeoPhys" / "src"
    sys.path.insert(0, str(geophys_src))
    try:
        from scene.scene_import import SceneSource, import_scene_source

        imported = import_scene_source(SceneSource.usd_path(manifest.parent / "entry.usda", label="f02-synthetic"), cache=False)
    finally:
        sys.path.remove(str(geophys_src))
    assert len(imported.source_graph_hash) == 64
    assert len(imported.dependency_paths) == 6

    relocated = tmp_path / "relocated-root"
    shutil.copytree(manifest.parent, relocated)
    relocated_loaded = load_usd_asset_delivery(relocated / "delivery.json", allow_synthetic=True)
    assert relocated_loaded.closure_sha256 == loaded.closure_sha256
    assert relocated_loaded.delivery_sha256 == loaded.delivery_sha256

    builds = {
        "isaacsim": "isaacsim-6.2.0.0",
        "geophys": "geophys-a53a8cfed7c9d6464274b5c96fca601271dc4ee4",
        "mujoco": "mujoco-3.8.1-libsha256-8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592",
    }
    choices = {name: resolve_provider_representation(loaded, provider=name, provider_build_identity=build).to_mapping()
               for name, build in builds.items()}
    assert choices["isaacsim"]["decision"] == "selected"
    assert choices["geophys"]["decision"] == "selected"
    assert choices["mujoco"]["decision"] == "rejected"
    assert choices["mujoco"]["format_matched"] is False
    assert all(item["runtime_admitted"] is False for item in choices.values())
    assert all(item["source_verified"] is False for item in choices.values())
    another_build = resolve_provider_representation(
        loaded, provider="isaacsim", provider_build_identity="isaacsim-6.3.0.0"
    )
    assert another_build.identity_hash != resolve_provider_representation(
        loaded, provider="isaacsim", provider_build_identity=builds["isaacsim"]
    ).identity_hash
    option_choice = resolve_provider_representation(loaded, provider="isaacsim", provider_build_identity=builds["isaacsim"], options={"load_payloads": False})
    assert option_choice.options_sha256 != choices["isaacsim"]["options_sha256"]

    repo = Path(__file__).resolve().parents[3]
    agent_dir = repo / "task_env" / "script" / "agent"
    sys.path.insert(0, str(agent_dir))
    try:
        # The CLI runs with its own directory on sys.path for its legacy sibling imports.
        from catalog_query import build_catalog
        from asset_check import check_assets

        catalog = build_catalog(
            repo,
            providers=("geophys", "mujoco"),
            asset_deliveries=[manifest],
            asset_provider_build_identities=builds,
            allow_synthetic_asset_deliveries=True,
        )
        assert len(catalog["asset_deliveries"]) == 1
        assert "f02-synthetic-usd-asset" not in catalog.get("external_assets", {})
        assert catalog["asset_deliveries"][0]["runtime_admitted"] is False
        assert set(catalog["asset_deliveries"][0]["provider_selections"]) == set(builds)
        spec = SimpleNamespace(
            object_config={"object_uid": "f02-synthetic-usd-asset"},
            scene_config={"fixtures": []},
            required_capabilities=(),
            spec_sha256=lambda: "f" * 64,
        )
        report = check_assets(spec, catalog)
        assert report.status == "fail"
        assert any(finding.code == "asset_missing" for finding in report.findings)
        from harness_compiler import CompilationRejected, compile_candidate
        from harness_spec_schema import CandidateSpec

        candidate = CandidateSpec(
            schema_version="harness-candidate-spec-v0",
            task_id="suite/f02-v1",
            template="pick-lift-v0",
            scene_config={"table_top_z": 0.462, "table_center_xy": [0.5545, 0.0], "table_half_size": [0.28, 0.20, 0.01]},
            object_config={"object_uid": "f02-synthetic-usd-asset", "initial_pos_xy": [0.5545, 0.0], "reset_half_extent_m": 0.06, "reset_z_fixed": True},
            success_config={"lift_height_m": 0.10, "reach_distance_m": 0.09, "gripper_closed_opening_m": 0.045},
            timebase_config={"physics_dt": 0.002, "control_substeps": 5},
            required_capabilities=catalog["template_details"]["pick-lift-v0"]["spec_template"]["required_capabilities"],
            horizon=6000,
        )
        with pytest.raises(CompilationRejected) as rejected:
            compile_candidate(candidate, catalog, provider="mujoco")
        assert any(finding.code == "asset_missing" for finding in rejected.value.report.findings)
    finally:
        sys.path.remove(str(agent_dir))


@pytest.mark.parametrize(
    "case",
    [
        "missing-entry", "missing-prim", "missing-variant-set", "missing-variant",
        "missing-dependency", "wrong-size", "wrong-file-hash", "dependency-changed",
        "report-wrong-source", "report-hash-mismatch", "duplicate-path", "path-traversal",
        "bool-size", "unknown-field", "duplicate-json-key", "nonfinite-size", "symlink-escape", "remote-uri-path",
    ],
)
def test_production_and_independent_reader_reject_tampered_deliveries(tmp_path, case):
    root = tmp_path / case
    build_fixture(root)
    _tamper(root, case)
    with pytest.raises((ValueError, TypeError, OSError)):
        load_usd_asset_delivery(root / "delivery.json", allow_synthetic=True)
    result = _reader(root)
    print(json.dumps({"case": case, "reader_exit": result.returncode, "stdout": result.stdout.strip()}))
    assert result.returncode != 0


def test_resolver_detects_stale_dependency_after_load(tmp_path):
    manifest = build_fixture(tmp_path / "stale")
    loaded = load_usd_asset_delivery(manifest, allow_synthetic=True)
    changed = manifest.parent / "refs/model.usda"
    changed.write_bytes(changed.read_bytes() + b"\n# changed after validation\n")
    with pytest.raises(ValueError, match="stale USD source dependency"):
        resolve_provider_representation(loaded, provider="geophys", provider_build_identity="geophys-test-build")


def test_independent_reader_accepts_saved_delivery_and_checks_inactive_variant(tmp_path):
    manifest = build_fixture(tmp_path / "good")
    result = _reader(manifest.parent)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["result"] == "PASS"
    assert payload["source_file_count"] == 6
    assert payload["runtime_admitted"] is False


def test_json_cli_exit_codes_and_atomic_report_write_failure(tmp_path):
    manifest = build_fixture(tmp_path / "cli")
    env = {**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "")}
    command = [sys.executable, "-m", "task_env.assembly.usd_delivery_cli", "--manifest", str(manifest)]
    accepted = subprocess.run(
        command + ["--allow-synthetic", "--provider-build", "isaacsim=isaacsim-6.2.0.0", "--output", str(tmp_path / "receipt.json")],
        text=True, capture_output=True, timeout=60, env=env,
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert json.loads(accepted.stdout)["result"] == "PASS"
    assert json.loads((tmp_path / "receipt.json").read_text())["source_verified"] is False

    rejected = subprocess.run(command, text=True, capture_output=True, timeout=60, env=env)
    assert rejected.returncode == 1
    assert json.loads(rejected.stdout)["result"] == "REJECTED"

    output_is_directory = tmp_path / "is-a-directory"
    output_is_directory.mkdir()
    write_failure = subprocess.run(
        command + ["--allow-synthetic", "--output", str(output_is_directory)],
        text=True, capture_output=True, timeout=60, env=env,
    )
    assert write_failure.returncode == 2
    assert json.loads(write_failure.stdout)["error_kind"] == "report-write-failed"
