"""Create an explicitly synthetic USD delivery exercising F02 composition."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from task_env.artifacts.contracts import (
    AssetDefinition,
    UsdAssetDeliveryV1,
    UsdDeliveryFileV1,
    UsdValidationReportV1,
)
from task_env.assembly.assets import _source_closure_digest, _source_closure_manifest
from task_env.assembly.usd_delivery import variant_selection_hash


def _write_stage(path: Path, author) -> None:
    from pxr import Usd

    stage = Usd.Stage.CreateNew(str(path))
    author(stage)
    stage.GetRootLayer().Save()


def _dependency_paths(entry: Path) -> set[str]:
    from pxr import Sdf, UsdUtils

    root = entry.parent.resolve()
    layer = Sdf.Layer.FindOrOpen(str(entry))
    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(layer.identifier)
    if unresolved:
        raise ValueError(f"synthetic fixture unexpectedly has unresolved dependencies: {list(unresolved)!r}")
    paths = {Path(item.identifier).resolve(strict=True).relative_to(root).as_posix() for item in layers}
    paths.update(Path(str(item)).resolve(strict=True).relative_to(root).as_posix() for item in assets)
    return paths


def build_fixture(output_dir: str | Path) -> Path:
    from pxr import Sdf, UsdGeom, UsdShade

    root = Path(output_dir).absolute()
    root.mkdir(parents=True, exist_ok=False)
    for folder in ("materials", "textures", "refs", "payloads", "variants"):
        (root / folder).mkdir()
    (root / "textures" / "grid.bin").write_bytes(b"synthetic-f02-texture-bytes-v1")

    def material(stage):
        mat = UsdShade.Material.Define(stage, "/Looks/Mat")
        tex = UsdShade.Shader.Define(stage, "/Looks/Mat/Texture")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("../textures/grid.bin"))
        tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        mat.CreateSurfaceOutput()

    _write_stage(root / "materials" / "look.usda", material)

    def payload(stage):
        UsdGeom.Xform.Define(stage, "/Extras")
        UsdGeom.Cube.Define(stage, "/Extras/Marker")

    _write_stage(root / "payloads" / "extras.usda", payload)

    def model(stage):
        UsdGeom.Xform.Define(stage, "/Model")
        UsdGeom.Cube.Define(stage, "/Model/Mesh")
        extras = UsdGeom.Xform.Define(stage, "/Model/Extras")
        extras.GetPrim().GetPayloads().AddPayload("../payloads/extras.usda", "/Extras")

    _write_stage(root / "refs" / "model.usda", model)

    def low(stage):
        UsdGeom.Xform.Define(stage, "/Low")
        UsdGeom.Cube.Define(stage, "/Low/Coarse")

    _write_stage(root / "variants" / "low.usda", low)

    entry = root / "entry.usda"
    from pxr import Usd

    stage = Usd.Stage.CreateNew(str(entry))
    stage.GetRootLayer().subLayerPaths = ["materials/look.usda"]
    asset_prim = UsdGeom.Xform.Define(stage, "/World/Asset").GetPrim()
    variant_set = asset_prim.GetVariantSets().AddVariantSet("lod")
    variants = (("low", "variants/low.usda", "/Low"), ("high", "refs/model.usda", "/Model"))
    for name, layer_path, prim_path in variants:
        variant_set.AddVariant(name)
        variant_set.SetVariantSelection(name)
        with variant_set.GetVariantEditContext():
            content = UsdGeom.Xform.Define(stage, "/World/Asset/Content")
            content.GetPrim().GetReferences().AddReference(layer_path, prim_path)
    variant_set.SetVariantSelection("high")
    mesh_override = stage.OverridePrim("/World/Asset/Content/Mesh")
    UsdShade.MaterialBindingAPI.Apply(mesh_override).Bind(UsdShade.Material.Get(stage, "/Looks/Mat"))
    stage.GetRootLayer().Save()

    files = {}
    for logical_path in sorted(_dependency_paths(entry)):
        files[logical_path] = (root / logical_path).read_bytes()
    closure_sha = _source_closure_digest(files)
    entry_sha = hashlib.sha256(files["entry.usda"]).hexdigest()
    asset = AssetDefinition(
        schema_version="asset-definition-v1",
        asset_id="f02-synthetic-usd-asset",
        asset_version="v1.0.0",
        source_reference="https://fixtures.geochora.invalid/f02/synthetic-usd-asset",
        source_revision="synthetic-fixture-r1",
    )
    selections = {"/World/Asset#lod": "high"}
    report = UsdValidationReportV1(
        schema_version="usd-validation-report-v1",
        report_id="f02/synthetic-fixture/upstream-report-contract",
        provenance_kind="synthetic-fixture",
        source_asset_identity_hash=asset.identity_hash,
        source_revision="synthetic-fixture-r1",
        entry_file_sha256=entry_sha,
        closure_sha256=closure_sha,
        entry_prim="/World/Asset",
        variant_selection_sha256=variant_selection_hash(selections),
        representation_format="usd",
        representation_id="usd-native-v1",
        input_closure_sha256=closure_sha,
        output_closure_sha256=closure_sha,
        recipe_id="synthetic-upstream-report-contract-fixture-v1",
        recipe_version="1",
        options_sha256=hashlib.sha256(b"{}").hexdigest(),
        checks=("source-bytes", "usd-composition", "dependency-closure"),
        losses=(),
        unconsumed=(),
        passed=True,
    )
    report_bytes = json.dumps(report.to_mapping(), sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    (root / "validation_report.json").write_bytes(report_bytes)
    delivery = UsdAssetDeliveryV1(
        schema_version="usd-asset-delivery-v1",
        asset_definition=asset,
        source_revision="synthetic-fixture-r1",
        provenance_kind="synthetic-fixture",
        entry_file="entry.usda",
        entry_prim="/World/Asset",
        variant_selections=selections,
        representation_format="usd",
        representation_id="usd-native-v1",
        closure_policy="usd-authored-all-dependencies-v1",
        files=tuple(
            UsdDeliveryFileV1(path=name, size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            for name, raw in files.items()
        ),
        closure_sha256=closure_sha,
        validation_report_path="validation_report.json",
        validation_report_sha256=hashlib.sha256(report_bytes).hexdigest(),
    )
    delivery_bytes = json.dumps(delivery.to_mapping(), sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    (root / "delivery.json").write_bytes(delivery_bytes)
    return root / "delivery.json"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    path = build_fixture(args.output_dir)
    print(json.dumps({"manifest": str(path), "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
