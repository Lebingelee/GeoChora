"""Offline handoff invariants; fixtures are synthetic and never runtime evidence."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from task_env.artifacts import asset_scene as contract
from task_env.assembly import asset_scene as loader
from task_env.assembly.assets import _source_closure_digest


def _ref(path, raw):
    return {"path": path, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _json(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def _loaded_delivery(raw):
    preparation = contract.AssetScenePreparationV1.from_mapping(raw)
    return SimpleNamespace(
        closure_sha256=preparation.delivery_closure_sha256,
        manifest_bytes_sha256=preparation.delivery_manifest.sha256,
        delivery=SimpleNamespace(asset_definition=preparation.target_asset),
        assert_fresh=lambda: None,
    )


def fixture(tmp_path):
    source = b"synthetic source mesh bytes for offline tests only"
    source_path = "src/source.obj"
    sha = "a" * 64
    raw = {
        "schema_version": "asset-scene-preparation-v1",
        "preparation_id": "tests/rigid-v1",
        "profile_id": contract.PANDA_RIGID_SCENE_PROFILE_V1,
        "request": _ref("request.json", b"{}\n"),
        "delivery_manifest": _ref("delivery/manifest.json", b"{}\n"),
        "delivery_closure_sha256": sha,
        "robot_source_identity_sha256": "b" * 64,
        "target_asset": {
            "schema_version": "asset-definition-v1", "asset_id": "test-rigid-object",
            "asset_version": "test-v1", "source_reference": "test-fixture://source/object",
            "source_revision": "test-v1", "license_id": "test-only",
            "source_content_sha256": _source_closure_digest({source_path: source}),
        },
        "target_source_files": [_ref(source_path, source)],
        "source_terms": _ref("source-terms.txt", b"Synthetic offline unit fixture.\n"),
        "bindings": {
            "schema_version": "panda-rigid-scene-bindings-v1",
            "scene_root": "/Scene", "robot_root": "/Scene/panda",
            "articulation_root": "/Scene/panda/root",
            "robot_base": "/Scene/panda/link0", "tcp_frame": "/Scene/panda/tcp",
            "target_body": "/Scene/target", "support_body": "/Scene/support",
            "support_top": "/Scene/support/top",
            "joint_paths": {name: f"/Scene/panda/{name}" for name in
                            [*(f"joint{i}" for i in range(1, 8)), "finger_joint1", "finger_joint2"]},
            "joint_body_paths": {
                **{
                    name: [
                        "/Scene/panda/root" if name == "joint1"
                        else f"/Scene/panda/link{int(name.removeprefix('joint')) - 1}",
                        f"/Scene/panda/link{int(name.removeprefix('joint'))}",
                    ]
                    for name in [f"joint{i}" for i in range(1, 8)]
                },
                "finger_joint1": ["/Scene/panda/link7", "/Scene/panda/left_finger"],
                "finger_joint2": ["/Scene/panda/link7", "/Scene/panda/right_finger"],
            },
        },
        "geometry": {
            "schema_version": "rigid-mesh-geometry-v1",
            "visual_mesh_prims": ["/Scene/target/visual"],
            "collision_mesh_prims": ["/Scene/target/collision"],
            "mesh_content_sha256": {"/Scene/target/visual": "d" * 64,
                                    "/Scene/target/collision": "e" * 64},
            "local_aabb_min_m": [-0.02, -0.02, -0.025],
            "local_aabb_max_m": [0.02, 0.02, 0.025], "mass_kg": 0.08,
            "collision_approximation": "convexHull",
            "approximation_losses": ["Test-only convex hull declaration; not native evidence."],
        },
        "evidence": [],
    }
    claims_path = "handoff/required_claims.json"
    claims_raw = _json({"assets": [{"id": "item", "claims": [
        {"id": f"claim-{index}", "type": "count"} for index in range(3)
    ]}]})
    claims_report = _json({"usd": "fixture.usda", "passed": True, "claims": [
        {"asset": "item", "id": f"claim-{index}", "type": "count",
         "passed": True, "measured": 1}
        for index in range(3)
    ]})
    claims_report_path = "handoff/evidence/required-claims-result.json"
    files = {"request.json": b"{}\n", "delivery/manifest.json": b"{}\n",
             source_path: source, "source-terms.txt": b"Synthetic offline unit fixture.\n",
             claims_path: claims_raw}
    input_hash = contract.AssetScenePreparationV1.from_mapping(raw).input_identity_hash
    for check in sorted(contract.REQUIRED_PREPARATION_CHECKS_V1):
        metrics = {}
        if check == "required-claims":
            metrics = {"required_count": 3, "executed_count": 3, "passed_count": 3,
                       "claim_ids": [f"claim-{index}" for index in range(3)],
                       "claims_path": claims_path,
                       "claims_size_bytes": len(claims_raw),
                       "checker_result_path": claims_report_path,
                       "checker_result_size_bytes": len(claims_report),
                       "claims_sha256": hashlib.sha256(claims_raw).hexdigest(),
                       "result_sha256": hashlib.sha256(claims_report).hexdigest()}
            files[claims_report_path] = claims_report
            result = {"schema_version": "asset-preparation-check-result-v1",
                           "check": check, "status": "pass",
                           "input_preparation_sha256": input_hash,
                           "checker_sha256": "c" * 64,
                           "tool_versions": {"test": "offline-v1"},
                           "scope": "Synthetic offline unit fixture only.",
                           "metrics": metrics}
            files[f"evidence/{check}.json"] = _json(result)
            files[claims_report_path] = claims_report
            raw["evidence"].append({**result,
                                    "schema_version": "asset-preparation-evidence-v1",
                                    "result": _ref(f"evidence/{check}.json", files[f"evidence/{check}.json"])})
            continue
        elif check == "physx-static-stability":
            metrics = {"target_checked": True, "duration_s": 5.0}
        elif check == "material-and-render":
            metrics = {"nonblank": True, "viewed": True}
        result = {"schema_version": "asset-preparation-check-result-v1", "check": check,
                  "status": "pass", "input_preparation_sha256": input_hash,
                  "checker_sha256": "c" * 64, "tool_versions": {"test": "offline-v1"},
                  "scope": "Synthetic offline unit fixture only.", "metrics": metrics}
        path = f"evidence/{check}.json"
        files[path] = _json(result)
        receipt = {**result, "schema_version": "asset-preparation-evidence-v1",
                   "result": _ref(path, files[path])}
        raw["evidence"].append(receipt)
    for path, content in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest = tmp_path / "preparation.json"
    manifest.write_bytes(_json(raw))
    return raw, manifest


def test_contract_roundtrip_and_identity_relocation(tmp_path):
    raw, _ = fixture(tmp_path)
    value = contract.AssetScenePreparationV1.from_mapping(raw)
    value.require_passed()
    assert value.to_mapping() == raw
    assert value.identity_hash == contract.AssetScenePreparationV1.from_mapping(deepcopy(raw)).identity_hash


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(profile_id="dual-arm-v1"),
    lambda x: x["bindings"]["joint_paths"].pop("finger_joint2"),
    lambda x: x["bindings"].update(target_body="/Scene/panda/target"),
    lambda x: x["bindings"].update(tcp_frame="/Other/tcp"),
    lambda x: x["geometry"].update(visual_mesh_prims=[]),
    lambda x: x["geometry"].update(collision_approximation="boundingCube"),
    lambda x: x["geometry"].update(mass_kg=True),
    lambda x: x["target_asset"].update(source_content_sha256=None),
    lambda x: x["evidence"][0].update(input_preparation_sha256="d" * 64),
    lambda x: x.update(unknown_field=1),
])
def test_rejects_invalid_contract(tmp_path, mutation):
    raw, _ = fixture(tmp_path)
    mutation(raw)
    with pytest.raises((TypeError, ValueError)):
        contract.AssetScenePreparationV1.from_mapping(raw)


@pytest.mark.parametrize("check,metrics", [
    ("required-claims", {"required_count": 0, "executed_count": 0, "passed_count": 0}),
    ("required-claims", {"required_count": 1, "executed_count": True, "passed_count": 1}),
    ("physx-static-stability", {"target_checked": False, "duration_s": 5.0}),
    ("physx-static-stability", {"target_checked": True, "duration_s": 4.0}),
    ("material-and-render", {"nonblank": True, "viewed": False}),
])
def test_rejects_vacuous_or_incomplete_required_checks(tmp_path, check, metrics):
    raw, _ = fixture(tmp_path)
    next(e for e in raw["evidence"] if e["check"] == check)["metrics"] = metrics
    value = contract.AssetScenePreparationV1.from_mapping(raw)
    with pytest.raises(ValueError):
        value.require_passed()


def test_loader_binds_bytes_and_detects_staleness(tmp_path, monkeypatch):
    raw, path = fixture(tmp_path)
    # Fake only the already-covered USD loader; this test proves handoff byte checks,
    # not USD structure, native physics, actual renders, or runtime admission.
    monkeypatch.setattr(loader, "load_usd_asset_delivery", lambda _: SimpleNamespace(
        closure_sha256=raw["delivery_closure_sha256"],
        manifest_bytes_sha256=raw["delivery_manifest"]["sha256"],
        delivery=SimpleNamespace(
            asset_definition=contract.AssetScenePreparationV1.from_mapping(raw).target_asset,
        ),
        assert_fresh=lambda: None,
    ))
    value = loader.load_asset_scene_preparation(path)
    value.assert_fresh()
    (tmp_path / "handoff/required_claims.json").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="input changed"):
        value.assert_fresh()
    with pytest.raises(ValueError, match="byte mismatch"):
        loader.load_asset_scene_preparation(path)


def test_loader_rejects_result_receipt_disagreement(tmp_path, monkeypatch):
    raw, path = fixture(tmp_path)
    monkeypatch.setattr(loader, "load_usd_asset_delivery", lambda _: SimpleNamespace(
        closure_sha256=raw["delivery_closure_sha256"],
        manifest_bytes_sha256=raw["delivery_manifest"]["sha256"],
        delivery=SimpleNamespace(
            asset_definition=contract.AssetScenePreparationV1.from_mapping(raw).target_asset,
        ),
    ))
    item = raw["evidence"][0]
    result_path = tmp_path / item["result"]["path"]
    altered = json.loads(result_path.read_text())
    altered["status"] = "fail"
    altered_bytes = _json(altered)
    result_path.write_bytes(altered_bytes)
    item["result"] = _ref(item["result"]["path"], altered_bytes)
    path.write_bytes(_json(raw))
    with pytest.raises(ValueError, match="raw checker result differs"):
        loader.load_asset_scene_preparation(path)


def test_loader_rejects_symlink_source(tmp_path, monkeypatch):
    raw, path = fixture(tmp_path)
    source = tmp_path / "src/source.obj"
    actual = tmp_path / "actual.obj"
    source.rename(actual)
    source.symlink_to(actual)
    with pytest.raises(ValueError, match="without symlinks"):
        loader.load_asset_scene_preparation(path)


@pytest.mark.parametrize("mutation", ["claim-id", "omit-row", "failed-row", "empty-claims"])
def test_loader_rejects_required_claim_report_not_matching_raw_claims(tmp_path, monkeypatch, mutation):
    raw, path = fixture(tmp_path)
    monkeypatch.setattr(loader, "load_usd_asset_delivery", lambda _: SimpleNamespace(
        closure_sha256=raw["delivery_closure_sha256"],
        manifest_bytes_sha256=raw["delivery_manifest"]["sha256"],
        delivery=SimpleNamespace(
            asset_definition=contract.AssetScenePreparationV1.from_mapping(raw).target_asset,
        ),
    ))
    item = next(row for row in raw["evidence"] if row["check"] == "required-claims")
    claims_path = tmp_path / "handoff/required_claims.json"
    claims_path.parent.mkdir(parents=True, exist_ok=True)
    claims = {"assets": [{"id": "item", "prim": "/Scene/target", "claims": [
        {"id": "bounds", "type": "bounds", "size": [0.04, 0.04, 0.05]},
        {"id": "mesh", "type": "count", "min": 2},
        {"id": "material", "type": "material", "class": "nonmetal"},
    ]}]}
    claims_bytes = _json(claims)
    claims_path.write_bytes(claims_bytes)
    result_path = tmp_path / item["result"]["path"]
    result_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"passed": True, "claims": [
        {"asset": "item", "id": claim["id"], "passed": True, "measured": 1}
        for claim in claims["assets"][0]["claims"]
    ]}
    if mutation == "claim-id":
        report["claims"][0]["id"] = "different"
    elif mutation == "omit-row":
        report["claims"].pop()
    elif mutation == "failed-row":
        report["claims"][0]["passed"] = False
    elif mutation == "empty-claims":
        claims["assets"][0]["claims"] = []
        claims_bytes = _json(claims)
        claims_path.write_bytes(claims_bytes)
        report["claims"] = []
    result_bytes = _json(report)
    result_path.write_bytes(result_bytes)
    item["result"] = _ref(item["result"]["path"], result_bytes)
    item["metrics"] = {
        "required_count": len(report["claims"]),
        "executed_count": len(report["claims"]),
        "passed_count": len(report["claims"]),
        "claim_ids": [row["id"] for row in report["claims"]],
        "claims_path": "handoff/required_claims.json",
        "claims_size_bytes": len(claims_bytes),
        "checker_result_path": "handoff/evidence/required-claims-result.json",
        "checker_result_size_bytes": len(result_bytes),
        "claims_sha256": hashlib.sha256(claims_bytes).hexdigest(),
        "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
    }
    checker_result_path = tmp_path / item["metrics"]["checker_result_path"]
    checker_result_path.parent.mkdir(parents=True, exist_ok=True)
    checker_result_path.write_bytes(result_bytes)
    path.write_bytes(_json(raw))
    with pytest.raises(ValueError):
        loader.load_asset_scene_preparation(path, require_passed=False)
