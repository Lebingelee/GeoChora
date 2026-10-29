"""Independent byte and OpenUSD composition reader for F02 saved deliveries.

This deliberately does not import the Core production delivery loader or trust
its verification flags. It reopens the serialized files in a fresh process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"nonfinite JSON value: {token}")))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _relative(value: str) -> PurePosixPath:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value or "://" in value:
        raise ValueError("nonportable path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("noncanonical or traversing path")
    if re.match(r"^[A-Za-z]:", value):
        raise ValueError("drive path")
    result = PurePosixPath(value)
    if result.as_posix() != value:
        raise ValueError("path normalization changed value")
    return result


def _read(root: Path, name: str) -> bytes:
    relative = _relative(name)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("delivery root is not a real directory")
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise ValueError("directory dependency is a symlink or not a directory")
    path = current / relative.parts[-1]
    if path.is_symlink() or not path.is_file():
        raise ValueError("required file is absent, nonregular or a symlink")
    if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise ValueError("file escaped delivery root")
    return path.read_bytes()


def verify(manifest_path: Path) -> dict[str, object]:
    from pxr import Sdf, Usd, UsdUtils

    root = manifest_path.parent
    delivery = _json(manifest_path)
    required_keys = {
        "schema_version", "asset_definition", "source_revision", "provenance_kind",
        "entry_file", "entry_prim", "variant_selections", "representation_format",
        "representation_id", "closure_policy", "files", "closure_sha256",
        "validation_report_path", "validation_report_sha256",
    }
    if set(delivery) != required_keys or delivery["schema_version"] != "usd-asset-delivery-v1":
        raise ValueError("delivery schema or fields differ")
    if delivery["provenance_kind"] not in {"synthetic-fixture", "upstream-validated"}:
        raise ValueError("unknown delivery provenance")
    if delivery["representation_format"] != "usd" or delivery["closure_policy"] != "usd-authored-all-dependencies-v1":
        raise ValueError("unsupported representation/closure policy")
    if Path(delivery["entry_file"]).suffix.lower() not in {".usd", ".usda", ".usdc"}:
        raise ValueError("unsupported USD entry format")

    asset = delivery["asset_definition"]
    if set(asset) != {"schema_version", "asset_id", "asset_version", "source_reference", "source_revision", "source_content_sha256", "license_id"}:
        raise ValueError("AssetDefinition fields differ")
    asset_hash = _sha(json.dumps(asset, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    if asset["source_revision"] != delivery["source_revision"]:
        raise ValueError("source revision mismatch")

    files = delivery["files"]
    if not isinstance(files, list) or not files:
        raise ValueError("file closure is missing")
    file_bytes = {}
    for binding in files:
        if set(binding) != {"path", "size_bytes", "sha256"} or binding["path"] in file_bytes:
            raise ValueError("file binding fields or paths differ")
        raw = _read(root, binding["path"])
        if type(binding["size_bytes"]) is not int or binding["size_bytes"] != len(raw) or _sha(raw) != binding["sha256"]:
            raise ValueError(f"file binding mismatch: {binding['path']}")
        file_bytes[binding["path"]] = raw
    closure = {
        "schema_version": "source-closure-v1",
        "files": [
            {"path": name, "size_bytes": len(raw), "sha256": _sha(raw)}
            for name, raw in sorted(file_bytes.items())
        ],
    }
    closure_hash = _sha(json.dumps(closure, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    if closure_hash != delivery["closure_sha256"] or delivery["entry_file"] not in file_bytes:
        raise ValueError("closure digest or entry binding mismatch")

    report_raw = _read(root, delivery["validation_report_path"])
    if _sha(report_raw) != delivery["validation_report_sha256"]:
        raise ValueError("report bytes mismatch")
    report = json.loads(
        report_raw.decode("utf-8"),
        object_pairs_hook=_pairs,
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"nonfinite JSON value: {token}")),
    )
    report_keys = {
        "schema_version", "report_id", "provenance_kind", "source_asset_identity_hash",
        "source_revision", "entry_file_sha256", "closure_sha256", "entry_prim",
        "variant_selection_sha256", "representation_format", "representation_id",
        "input_closure_sha256", "output_closure_sha256", "recipe_id", "recipe_version",
        "options_sha256", "checks", "losses", "unconsumed", "passed",
    }
    if set(report) != report_keys or report["schema_version"] != "usd-validation-report-v1":
        raise ValueError("validation report schema or fields differ")
    selections_hash = _sha(json.dumps({"schema_version": "usd-variant-selection-v1", "selections": dict(sorted(delivery["variant_selections"].items()))}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    bound = (
        report["provenance_kind"] == delivery["provenance_kind"]
        and report["source_asset_identity_hash"] == asset_hash
        and report["source_revision"] == delivery["source_revision"]
        and report["entry_file_sha256"] == _sha(file_bytes[delivery["entry_file"]])
        and report["closure_sha256"] == closure_hash
        and report["input_closure_sha256"] == closure_hash
        and report["output_closure_sha256"] == closure_hash
        and report["entry_prim"] == delivery["entry_prim"]
        and report["variant_selection_sha256"] == selections_hash
        and report["representation_format"] == delivery["representation_format"]
        and report["representation_id"] == delivery["representation_id"]
        and {"source-bytes", "usd-composition", "dependency-closure"}.issubset(report["checks"])
        and report["passed"] is True
    )
    if not bound:
        raise ValueError("report pass is not bound to this exact source and representation")

    import tempfile
    with tempfile.TemporaryDirectory(prefix="f02-independent-reader-") as temp:
        snapshot = Path(temp)
        for name, raw in file_bytes.items():
            target = snapshot.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        entry = snapshot.joinpath(*PurePosixPath(delivery["entry_file"]).parts)
        root_layer = Sdf.Layer.FindOrOpen(str(entry))
        layers, assets, unresolved = UsdUtils.ComputeAllDependencies(root_layer.identifier)
        required = {Path(layer.identifier).resolve(strict=True).relative_to(snapshot.resolve()).as_posix() for layer in layers}
        for asset_path in assets:
            required.add(Path(str(asset_path)).resolve(strict=True).relative_to(snapshot.resolve()).as_posix())
        if unresolved or required != set(file_bytes):
            raise ValueError(f"independent USD closure mismatch: unresolved={len(unresolved)}, missing={sorted(required-set(file_bytes))}, extra={sorted(set(file_bytes)-required)}")
        stage = Usd.Stage.Open(str(entry), load=Usd.Stage.LoadAll)
        if stage is None:
            raise ValueError("USD stage failed to compose")
        for key, value in delivery["variant_selections"].items():
            if key.count("#") != 1:
                raise ValueError("bad variant key")
            prim_path, set_name = key.rsplit("#", 1)
            prim = stage.GetPrimAtPath(prim_path)
            variant_set = prim.GetVariantSets().GetVariantSet(set_name) if prim else None
            if not variant_set or value not in variant_set.GetVariantNames() or not variant_set.SetVariantSelection(value):
                raise ValueError(f"variant selection failed: {key}={value}")
        entry_prim = stage.GetPrimAtPath(delivery["entry_prim"])
        if not entry_prim or not entry_prim.IsValid():
            raise ValueError("entry prim does not exist")
    return {
        "result": "PASS",
        "reader": "f02-independent-reader-v1",
        "asset_identity_hash": asset_hash,
        "closure_sha256": closure_hash,
        "delivery_sha256": _sha(json.dumps(delivery, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()),
        "source_file_count": len(file_bytes),
        "dependency_layer_count": len(layers),
        "asset_dependency_count": len(assets),
        "entry_prim_valid": True,
        "report_binding_valid": True,
        "passed_flag_source": report["passed"],
        "runtime_admitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify(args.delivery.absolute())
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"result": "REJECTED", "error_type": type(error).__name__, "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
