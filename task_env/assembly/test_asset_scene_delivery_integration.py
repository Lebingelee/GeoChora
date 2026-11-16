"""Relocation and adversarial checks against a real generated lemon delivery.

Set GEOCHORA_ASSET_SCENE_TEST_PREPARATION to a generated preparation.json on
the remote Isaac host. These tests are not synthetic proof of runtime admission.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from task_env.assembly.asset_scene import load_asset_scene_preparation
from task_env.assembly.asset_scene_structure import validate_asset_scene_structure
from task_env.assembly.assets import _source_closure_digest


SOURCE = os.environ.get("GEOCHORA_ASSET_SCENE_TEST_PREPARATION")
pytestmark = pytest.mark.skipif(not SOURCE, reason="requires an explicit real asset-scene delivery")


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


@pytest.fixture
def delivery(tmp_path):
    source = Path(SOURCE).resolve(strict=True)
    assert source.name == "preparation.json"
    destination = tmp_path / "moved" / "delivery"
    shutil.copytree(source.parent, destination)
    return destination


def _rebind_delivery(root):
    """Re-sign self-declared hashes so negative tests reach structural checks."""
    manifest_path = root / "delivery_manifest.json"
    report_path = root / "metadata/asset_scene_local_validation_v1.json"
    manifest = json.loads(manifest_path.read_text())
    files = {}
    for entry in manifest["files"]:
        raw = (root / entry["path"]).read_bytes()
        entry.update(size_bytes=len(raw), sha256=_digest(raw))
        files[entry["path"]] = raw
    manifest["closure_sha256"] = _source_closure_digest(files)
    report = json.loads(report_path.read_text())
    report["entry_file_sha256"] = _digest(files[manifest["entry_file"]])
    report["output_closure_sha256"] = manifest["closure_sha256"]
    _write_json(report_path, report)
    manifest["validation_report_sha256"] = _digest(report_path.read_bytes())
    _write_json(manifest_path, manifest)

    preparation_path = root / "preparation.json"
    preparation = json.loads(preparation_path.read_text())
    preparation["delivery_manifest"].update(
        size_bytes=manifest_path.stat().st_size, sha256=_digest(manifest_path.read_bytes()),
    )
    preparation["delivery_closure_sha256"] = manifest["closure_sha256"]
    input_value = deepcopy(preparation)
    input_value.pop("evidence")
    input_hash = _digest(json.dumps(input_value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode())
    for check in preparation["evidence"]:
        check["input_preparation_sha256"] = input_hash
        result_path = root / check["result"]["path"]
        result = json.loads(result_path.read_text())
        result["input_preparation_sha256"] = input_hash
        _write_json(result_path, result)
        check["result"].update(
            size_bytes=result_path.stat().st_size, sha256=_digest(result_path.read_bytes()),
        )
    _write_json(preparation_path, preparation)


def _stage(root):
    from pxr import Usd

    stage = Usd.Stage.Open(str(root / "asset_scene.usda"), load=Usd.Stage.LoadAll)
    assert stage is not None
    return stage


def test_relocated_real_delivery_and_preparation(delivery):
    from pxr import Usd, UsdGeom, UsdShade

    loaded = load_asset_scene_preparation(delivery / "preparation.json", require_passed=False)
    loaded.assert_fresh()
    result = validate_asset_scene_structure(loaded)
    assert result["target_body"] == "/AssetScene/lemon_v1"
    assert result["collision_meshes"] == ["/AssetScene/lemon_v1/collision"]
    assert not result["runtime_admitted"] and not result["native_physics_checked"]
    stage = Usd.Stage.Open(str(delivery / "asset_scene.usda"), load=Usd.Stage.LoadAll)
    visual = UsdGeom.Mesh(stage.GetPrimAtPath("/AssetScene/lemon_v1/visual"))
    uv = UsdGeom.PrimvarsAPI(visual).GetPrimvar("st")
    assert uv.GetInterpolation() == UsdGeom.Tokens.faceVarying
    assert len(uv.Get()) == sum(visual.GetFaceVertexCountsAttr().Get())
    material, _ = UsdShade.MaterialBindingAPI(visual.GetPrim()).ComputeBoundMaterial()
    texture = UsdShade.Shader(stage.GetPrimAtPath("/AssetScene/materials/lemon/color"))
    assert material and texture.GetIdAttr().Get() == "UsdUVTexture"
    assert Path(texture.GetInput("file").Get().resolvedPath).is_file()
    assert texture.GetInput("st").GetConnectedSource()
    with pytest.raises(ValueError, match="not passing"):
        loaded.preparation.require_passed()


def test_rejects_tampered_delivery_manifest(delivery):
    path = delivery / "delivery_manifest.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="byte mismatch"):
        load_asset_scene_preparation(delivery / "preparation.json", require_passed=False)


def test_rejects_tampered_mesh_before_structure(delivery):
    path = delivery / "asset_scene.usda"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="USD closure (size|SHA-256) mismatch"):
        load_asset_scene_preparation(delivery / "preparation.json", require_passed=False)


def test_rejects_rebound_mesh_geometry(delivery):
    from pxr import Gf, UsdGeom

    stage = _stage(delivery)
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath("/AssetScene/lemon_v1/visual"))
    points = list(mesh.GetPointsAttr().Get())
    points[0] = Gf.Vec3f(float(points[0][0]) + 0.001, float(points[0][1]), float(points[0][2]))
    mesh.GetPointsAttr().Set(points)
    stage.GetRootLayer().Save()
    _rebind_delivery(delivery)
    loaded = load_asset_scene_preparation(delivery / "preparation.json", require_passed=False)
    with pytest.raises(ValueError, match="scaled source OBJ geometry"):
        validate_asset_scene_structure(loaded)


def test_rejects_rebound_wrong_joint_endpoints(delivery):
    from pxr import UsdPhysics

    stage = _stage(delivery)
    path = "/AssetScene/panda/Geometry/link0/link1/joint1"
    joint = UsdPhysics.Joint(stage.GetPrimAtPath(path))
    joint.GetBody0Rel().SetTargets(["/AssetScene/panda/Geometry/link0/link1"])
    stage.GetRootLayer().Save()
    _rebind_delivery(delivery)
    loaded = load_asset_scene_preparation(delivery / "preparation.json", require_passed=False)
    with pytest.raises(ValueError, match="joint body mapping differs"):
        validate_asset_scene_structure(loaded)


def test_rejects_rebound_wrong_aabb(delivery):
    preparation_path = delivery / "preparation.json"
    preparation = json.loads(preparation_path.read_text())
    preparation["geometry"]["local_aabb_max_m"][0] += 0.01
    _write_json(preparation_path, preparation)
    _rebind_delivery(delivery)
    loaded = load_asset_scene_preparation(preparation_path, require_passed=False)
    with pytest.raises(ValueError, match="maximum bounds differ"):
        validate_asset_scene_structure(loaded)


def test_rejects_rebound_mesh_transform(delivery):
    from pxr import Gf, UsdGeom

    stage = _stage(delivery)
    visual = stage.GetPrimAtPath("/AssetScene/lemon_v1/visual")
    UsdGeom.Xformable(visual).AddTranslateOp().Set(Gf.Vec3d(0.01, 0, 0))
    stage.GetRootLayer().Save()
    _rebind_delivery(delivery)
    loaded = load_asset_scene_preparation(delivery / "preparation.json", require_passed=False)
    with pytest.raises(ValueError, match="minimum bounds differ"):
        validate_asset_scene_structure(loaded)


@pytest.mark.parametrize("prim_path", [
    "/AssetScene/lemon_v1", "/AssetScene/support",
])
def test_rejects_rebound_initial_support_gap(delivery, prim_path):
    from pxr import Gf, UsdGeom

    stage = _stage(delivery)
    prim = stage.GetPrimAtPath(prim_path)
    op = UsdGeom.Xformable(prim).GetOrderedXformOps()[0]
    position = op.Get()
    shift = 0.001 if prim_path.endswith("lemon_v1") else -0.001
    op.Set(Gf.Vec3d(float(position[0]), float(position[1]), float(position[2]) + shift))
    stage.GetRootLayer().Save()
    _rebind_delivery(delivery)
    loaded = load_asset_scene_preparation(delivery / "preparation.json", require_passed=False)
    with pytest.raises(ValueError, match="support height is not composed flush"):
        validate_asset_scene_structure(loaded)


@pytest.mark.parametrize("mutation,match", [
    ("dynamic", "support subtree cannot contain dynamic rigid bodies"),
    ("animated", "support subtree cannot contain animated transforms"),
])
def test_rejects_rebound_moving_support_subtree(delivery, mutation, match):
    from pxr import Gf, UsdGeom, UsdPhysics

    stage = _stage(delivery)
    support = stage.GetPrimAtPath("/AssetScene/support/collision")
    if mutation == "dynamic":
        UsdPhysics.RigidBodyAPI.Apply(support).CreateRigidBodyEnabledAttr(True)
    else:
        xform = UsdGeom.Xformable(support)
        op = xform.GetOrderedXformOps()[0]
        op.Set(Gf.Vec3f(0.28, 0.20, 0.01), 0.0)
        op.Set(Gf.Vec3f(0.28, 0.20, 0.02), 1.0)
    stage.GetRootLayer().Save()
    _rebind_delivery(delivery)
    loaded = load_asset_scene_preparation(delivery / "preparation.json", require_passed=False)
    with pytest.raises(ValueError, match=match):
        validate_asset_scene_structure(loaded)
