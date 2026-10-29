"""Strict USD byte-delivery loading and bounded provider representation choice.

This module imports OpenUSD only when a delivery is actually loaded. It does
not create a RuntimeSource, start a provider, or admit runtime execution.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from types import MappingProxyType

from ..artifacts.contracts import (
    ProviderRepresentationSelectionV1,
    UsdAssetDeliveryLocalV1,
    UsdAssetDeliveryV1,
    UsdDeliveryFileV1,
    UsdLocalValidationReportV1,
    UsdValidationReportV1,
)
from .assets import _source_closure_digest, _source_closure_manifest


_REQUIRED_REPORT_CHECKS = frozenset(
    {"source-bytes", "usd-composition", "dependency-closure"}
)
_SUPPORTED_USD_EXTENSIONS = {".usd", ".usda", ".usdc"}
_MAX_CLOSURE_BYTES = 512 * 1024 * 1024
_LOADER_TOKEN = object()
_LOCAL_REPORT_CHECKS = frozenset({
    "source-bytes", "derived-output-bytes", "usd-composition", "dependency-closure",
    "selected-scene-structure", "panda-dof-units-limits", "physx-drive-profile",
    "free-body-and-support", "source-losses-recorded",
})


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _strict_json_bytes(raw: bytes, *, label: str):
    if not isinstance(raw, bytes):
        raise TypeError(f"{label} must be bytes")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON number: {value}")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from error


def _canonical_hash(value) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def variant_selection_hash(selections: Mapping[str, str]) -> str:
    return _canonical_hash({"schema_version": "usd-variant-selection-v1", "selections": dict(sorted(selections.items()))})


def _validate_relative_path(value: str, *, label: str) -> PurePosixPath:
    if type(value) is not str or not value or "\\" in value or value.startswith("/"):
        raise ValueError(f"{label} must be a root-relative POSIX path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} is noncanonical or traverses its root")
    if "://" in value or re.match(r"^[A-Za-z]:", value):
        raise ValueError(f"{label} cannot contain URI or drive paths")
    path = PurePosixPath(value)
    if path.as_posix() != value:
        raise ValueError(f"{label} is not canonical")
    return path


def _safe_read(root: Path, relative: str, *, label: str, max_bytes: int = _MAX_CLOSURE_BYTES) -> bytes:
    rel = _validate_relative_path(relative, label=label)
    root = root.absolute()
    if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
        raise ValueError("USD delivery root must be a real directory, not a symlink")
    current = root
    for segment in rel.parts[:-1]:
        current = current / segment
        info = current.lstat()
        if current.is_symlink() or not current.is_dir():
            raise ValueError(f"{label} contains a symlink or non-directory component")
    target = current / rel.parts[-1]
    info = target.lstat()
    if target.is_symlink() or not target.is_file():
        raise ValueError(f"{label} must resolve to a regular file without symlinks")
    if info.st_size > max_bytes:
        raise ValueError(f"{label} exceeds its bounded read size")
    resolved_root = root.resolve(strict=True)
    resolved_target = target.resolve(strict=True)
    if not resolved_target.is_relative_to(resolved_root):
        raise ValueError(f"{label} escaped its delivery root")
    with target.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError(f"{label} grew beyond its bounded read size")
    return raw


def _layer_path(layer) -> str:
    identifier = getattr(layer, "identifier", None)
    if type(identifier) is not str:
        raise ValueError("OpenUSD dependency returned a non-file layer")
    return identifier


def _snapshot_relative(path_value: str, root: Path, *, label: str) -> str:
    if "://" in path_value or path_value.startswith("anon:"):
        raise ValueError(f"unsupported nonportable USD dependency: {path_value!r}")
    path = Path(path_value)
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(root.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as error:
        raise ValueError(f"{label} is outside the frozen USD byte snapshot: {path_value!r}") from error
    return str(_validate_relative_path(relative, label=label))


def _inspect_snapshot(
    snapshot_root: Path,
    entry_path: Path,
    entry_prim: str,
    variant_selections: Mapping[str, str],
):
    """Compose a closed local snapshot and return required root-relative paths."""
    try:
        from pxr import Ar, Sdf, Usd, UsdUtils
    except Exception as error:  # pxr is deliberately a use-time dependency
        raise RuntimeError("OpenUSD is unavailable in this Python environment") from error

    root = snapshot_root.resolve(strict=True)
    entry_path = entry_path.resolve(strict=True)
    if not entry_path.is_relative_to(root):
        raise ValueError("USD entry layer is outside its frozen byte snapshot")
    root_layer = Sdf.Layer.FindOrOpen(str(entry_path))
    if root_layer is None:
        raise ValueError("OpenUSD could not open the delivery entry layer")
    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(root_layer.identifier)
    if unresolved:
        raise ValueError(f"USD dependency closure contains unresolved paths: {list(unresolved)!r}")
    resolver = Ar.GetResolver()
    resolved_root = resolver.Resolve(root_layer.identifier)
    if not resolved_root:
        raise ValueError("Ar could not resolve the USD entry layer")
    required = set()
    for layer in layers:
        resolved = resolver.Resolve(_layer_path(layer))
        if not resolved:
            raise ValueError(f"Ar could not resolve USD layer dependency: {_layer_path(layer)!r}")
        required.add(_snapshot_relative(str(resolved), root, label="USD layer dependency"))
    for path in assets:
        resolved = resolver.Resolve(str(path))
        if not resolved:
            raise ValueError(f"Ar could not resolve USD asset dependency: {str(path)!r}")
        required.add(_snapshot_relative(str(resolved), root, label="USD asset dependency"))
    stage = Usd.Stage.Open(str(entry_path), load=Usd.Stage.LoadAll)
    if stage is None:
        raise ValueError("OpenUSD could not compose the delivery entry stage")
    for key, selection in variant_selections.items():
        if key.count("#") != 1:
            raise ValueError(f"variant key must be '<absolute-prim-path>#<set>': {key!r}")
        prim_path, set_name = key.rsplit("#", 1)
        if not prim_path.startswith("/") or not set_name or not selection:
            raise ValueError(f"invalid USD variant selection: {key!r}")
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            raise ValueError(f"variant prim does not exist: {prim_path}")
        variant_set = prim.GetVariantSets().GetVariantSet(set_name)
        if not variant_set or not variant_set.IsValid():
            raise ValueError(f"variant set does not exist: {key}")
        if selection not in variant_set.GetVariantNames():
            raise ValueError(f"unknown USD variant selection: {key}={selection}")
        if not variant_set.SetVariantSelection(selection):
            raise ValueError(f"OpenUSD rejected variant selection: {key}={selection}")
    prim = stage.GetPrimAtPath(entry_prim)
    if not prim or not prim.IsValid():
        raise ValueError(f"USD entry prim does not exist after composition: {entry_prim}")
    return required, {
        "pxr_version": list(Usd.GetVersion()),
        "ar_resolver": type(resolver).__name__,
        "entry_layer_identifier": root_layer.identifier,
        "entry_prim_valid": True,
        "selected_variants": dict(sorted(variant_selections.items())),
        "dependency_layer_count": len(layers),
        "asset_dependency_count": len(assets),
        "unresolved_count": len(unresolved),
        "closure_policy": "usd-authored-all-dependencies-v1",
    }


@dataclass(frozen=True)
class LoadedUsdDeliveryV1:
    delivery: UsdAssetDeliveryV1 | UsdAssetDeliveryLocalV1
    report: UsdValidationReportV1 | UsdLocalValidationReportV1
    manifest_path: Path
    manifest_bytes_sha256: str
    file_bytes: Mapping[str, bytes]
    report_bytes: bytes
    inspection: Mapping[str, object]
    source_verified: bool
    source_input_bytes: Mapping[str, bytes] = field(default_factory=lambda: MappingProxyType({}))
    local_support_bytes: Mapping[str, bytes] = field(default_factory=lambda: MappingProxyType({}))
    _verification_token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self._verification_token is not _LOADER_TOKEN:
            raise TypeError("LoadedUsdDeliveryV1 values can only be created by the verified Core loader")

    @property
    def delivery_sha256(self) -> str:
        return self.delivery.delivery_sha256

    @property
    def closure_sha256(self) -> str:
        return self.delivery.closure_sha256

    @property
    def locally_validated(self) -> bool:
        return type(self.delivery) is UsdAssetDeliveryLocalV1 and type(self.report) is UsdLocalValidationReportV1

    def assert_fresh(self) -> None:
        """Refuse a resolver decision if any original delivery byte changed."""
        manifest_raw = _safe_read(self.manifest_path.parent, self.manifest_path.name, label="delivery manifest")
        if hashlib.sha256(manifest_raw).hexdigest() != self.manifest_bytes_sha256:
            raise ValueError("stale USD delivery manifest")
        for relative, original in self.file_bytes.items():
            current = _safe_read(self.manifest_path.parent, relative, label="USD source file")
            if current != original:
                raise ValueError(f"stale USD source dependency: {relative}")
        for relative, original in self.source_input_bytes.items():
            current = _safe_read(self.manifest_path.parent, relative, label="local USD original source")
            if current != original:
                raise ValueError(f"stale local USD original source input: {relative}")
        for relative, original in self.local_support_bytes.items():
            current = _safe_read(self.manifest_path.parent, relative, label="local USD validation support")
            if current != original:
                raise ValueError(f"stale local USD validation support: {relative}")
        report_raw = _safe_read(self.manifest_path.parent, self.delivery.validation_report_path, label="USD validation report")
        if report_raw != self.report_bytes:
            raise ValueError("stale USD validation report")


def load_usd_asset_delivery(
    manifest_path: str | os.PathLike[str], *, allow_synthetic: bool = False
) -> LoadedUsdDeliveryV1:
    """Decode, byte-bind, compose and report-link one portable USD delivery."""
    manifest_path = Path(manifest_path).absolute()
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("USD delivery manifest must be a regular file")
    root = manifest_path.parent
    if root.is_symlink():
        raise ValueError("USD delivery root cannot be a symlink")
    manifest_raw = _safe_read(root, manifest_path.name, label="delivery manifest", max_bytes=16 * 1024 * 1024)
    manifest_mapping = _strict_json_bytes(manifest_raw, label="USD delivery manifest")
    schema = manifest_mapping.get("schema_version") if isinstance(manifest_mapping, Mapping) else None
    if schema == "usd-asset-delivery-v1":
        delivery = UsdAssetDeliveryV1.from_mapping(manifest_mapping)
    elif schema == "usd-local-derived-delivery-v1":
        delivery = UsdAssetDeliveryLocalV1.from_mapping(manifest_mapping)
    else:
        raise ValueError(f"unsupported USD delivery schema: {schema!r}")
    if delivery.representation_format != "usd":
        raise ValueError("F02 loader only accepts USD source representations")
    if Path(delivery.entry_file).suffix.lower() not in _SUPPORTED_USD_EXTENSIONS:
        raise ValueError("USDZ and unsupported entry formats are not admitted by this delivery loader")
    if delivery.provenance_kind == "synthetic-fixture" and not allow_synthetic:
        raise ValueError("synthetic USD delivery is not accepted by the production upstream-verified gate")

    file_bytes = {}
    total_bytes = 0
    for binding in delivery.files:
        remaining = _MAX_CLOSURE_BYTES - total_bytes
        if binding.size_bytes > remaining:
            raise ValueError(f"USD closure exceeds bounded Core loader limit: {_MAX_CLOSURE_BYTES} bytes")
        raw = _safe_read(root, binding.path, label="USD closure file", max_bytes=remaining)
        total_bytes += len(raw)
        if total_bytes > _MAX_CLOSURE_BYTES:
            raise ValueError(f"USD closure exceeds bounded Core loader limit: {_MAX_CLOSURE_BYTES} bytes")
        if len(raw) != binding.size_bytes:
            raise ValueError(f"USD closure size mismatch: {binding.path}")
        if hashlib.sha256(raw).hexdigest() != binding.sha256:
            raise ValueError(f"USD closure SHA-256 mismatch: {binding.path}")
        file_bytes[binding.path] = raw
    actual_closure = _source_closure_digest(file_bytes)
    if actual_closure != delivery.closure_sha256:
        raise ValueError("USD delivery closure digest does not match exact file bytes")
    report_raw = _safe_read(root, delivery.validation_report_path, label="USD validation report", max_bytes=16 * 1024 * 1024)
    if hashlib.sha256(report_raw).hexdigest() != delivery.validation_report_sha256:
        raise ValueError("USD validation report SHA-256 mismatch")
    report_mapping = _strict_json_bytes(report_raw, label="USD validation report")
    report_schema = report_mapping.get("schema_version") if isinstance(report_mapping, Mapping) else None
    if report_schema == "usd-validation-report-v1":
        report = UsdValidationReportV1.from_mapping(report_mapping)
    elif report_schema == "usd-local-validation-report-v1":
        report = UsdLocalValidationReportV1.from_mapping(report_mapping)
    else:
        raise ValueError(f"unsupported USD validation report schema: {report_schema!r}")
    entry_sha = hashlib.sha256(file_bytes[delivery.entry_file]).hexdigest()
    if type(delivery) is UsdAssetDeliveryLocalV1:
        if type(report) is not UsdLocalValidationReportV1:
            raise ValueError("locally derived USD delivery requires the distinct local validation report schema")
        source_manifest_raw = _safe_read(root, delivery.source_manifest_path, label="local USD source inventory", max_bytes=16 * 1024 * 1024)
        recipe_raw = _safe_read(root, delivery.recipe_path, label="local USD derivation recipe", max_bytes=16 * 1024 * 1024)
        checker_raw = _safe_read(root, delivery.checker_path, label="local USD checker source", max_bytes=16 * 1024 * 1024)
        if hashlib.sha256(source_manifest_raw).hexdigest() != delivery.source_manifest_sha256:
            raise ValueError("local USD source inventory manifest SHA-256 mismatch")
        if hashlib.sha256(recipe_raw).hexdigest() != delivery.recipe_sha256:
            raise ValueError("local USD derivation recipe SHA-256 mismatch")
        if hashlib.sha256(checker_raw).hexdigest() != delivery.checker_sha256:
            raise ValueError("local USD validation checker SHA-256 mismatch")
        support_file_bytes: dict[str, bytes] = {}
        for binding in delivery.support_files:
            raw = _safe_read(root, binding.path, label="local USD validation support file", max_bytes=16 * 1024 * 1024)
            if len(raw) != binding.size_bytes or hashlib.sha256(raw).hexdigest() != binding.sha256:
                raise ValueError(f"local USD validation support byte mismatch: {binding.path}")
            support_file_bytes[binding.path] = raw
        source_file_bytes: dict[str, bytes] = {}
        source_total_bytes = 0
        for binding in delivery.source_files:
            remaining = _MAX_CLOSURE_BYTES - source_total_bytes
            raw = _safe_read(root, binding.path, label="local USD original source byte", max_bytes=remaining)
            source_total_bytes += len(raw)
            if len(raw) != binding.size_bytes or hashlib.sha256(raw).hexdigest() != binding.sha256:
                raise ValueError(f"local USD original source byte mismatch: {binding.path}")
            source_file_bytes[binding.path] = raw
        if _source_closure_digest(source_file_bytes) != delivery.source_closure_sha256:
            raise ValueError("local USD original source closure does not match exact source bytes")
        source_inventory = _strict_json_bytes(source_manifest_raw, label="local USD source inventory")
        expected_inventory = {
            "schema_version": "f04-local-source-inventory-v1",
            "files": [item.to_mapping() for item in delivery.source_files],
            "source_closure_sha256": delivery.source_closure_sha256,
        }
        if source_inventory != expected_inventory:
            raise ValueError("local USD source inventory content differs from the bound byte manifest")
        if delivery.source_entry_file not in source_file_bytes or hashlib.sha256(
                source_file_bytes[delivery.source_entry_file]).hexdigest() != delivery.source_entry_sha256:
            raise ValueError("local USD original source entry hash is not bound by its inventory")
        source_variant_sha = variant_selection_hash(delivery.source_variant_selections)
        expected_report_binding = (
            report.provenance_kind == delivery.provenance_kind == "local-validated"
            and report.source_asset_identity_hash == delivery.asset_identity_hash
            and report.source_revision == delivery.source_revision
            and report.source_closure_sha256 == delivery.source_closure_sha256
            and report.source_manifest_sha256 == delivery.source_manifest_sha256
            and report.source_entry_sha256 == delivery.source_entry_sha256
            and report.source_variant_selection_sha256 == source_variant_sha == delivery.source_variant_selection_sha256
            and report.entry_file_sha256 == entry_sha
            and report.output_closure_sha256 == delivery.closure_sha256
            and report.entry_prim == delivery.entry_prim
            and report.representation_format == delivery.representation_format
            and report.representation_id == delivery.representation_id
            and report.recipe_sha256 == delivery.recipe_sha256
            and report.options_sha256 == delivery.options_sha256
            and report.checker_sha256 == delivery.checker_sha256
            and _LOCAL_REPORT_CHECKS.issubset(report.checks)
        )
    else:
        source_file_bytes = {}
        support_file_bytes = {}
        local_support_bytes = {}
        if type(report) is not UsdValidationReportV1:
            raise ValueError("F02 v1 USD delivery requires its unchanged upstream/synthetic report schema")
        expected_report_binding = (
            report.provenance_kind == delivery.provenance_kind
            and report.source_asset_identity_hash == delivery.asset_identity_hash
            and report.source_revision == delivery.source_revision
            and report.entry_file_sha256 == entry_sha
            and report.closure_sha256 == delivery.closure_sha256
            and report.input_closure_sha256 == delivery.closure_sha256
            and report.output_closure_sha256 == delivery.closure_sha256
            and report.entry_prim == delivery.entry_prim
            and report.variant_selection_sha256 == variant_selection_hash(delivery.variant_selections)
            and report.representation_format == delivery.representation_format
            and report.representation_id == delivery.representation_id
            and _REQUIRED_REPORT_CHECKS.issubset(report.checks)
        )
    if not expected_report_binding:
        raise ValueError("USD validation report does not bind this source, closure, entry or representation")
    if not report.passed:
        raise ValueError("USD validation report did not pass")

    with tempfile.TemporaryDirectory(prefix="geochora-usd-delivery-") as temporary:
        snapshot = Path(temporary)
        for relative, raw in file_bytes.items():
            target = snapshot.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        inspection_variants = {} if type(delivery) is UsdAssetDeliveryLocalV1 else delivery.variant_selections
        required, inspection = _inspect_snapshot(
            snapshot,
            snapshot.joinpath(*PurePosixPath(delivery.entry_file).parts),
            delivery.entry_prim,
            inspection_variants,
        )
        if required != set(file_bytes):
            missing = sorted(required.difference(file_bytes))
            extra = sorted(set(file_bytes).difference(required))
            raise ValueError(f"USD byte closure differs from OpenUSD dependencies; missing={missing}, extra={extra}")

    return LoadedUsdDeliveryV1(
        delivery=delivery,
        report=report,
        manifest_path=manifest_path,
        manifest_bytes_sha256=hashlib.sha256(manifest_raw).hexdigest(),
        file_bytes=MappingProxyType(dict(file_bytes)),
        report_bytes=report_raw,
        inspection=MappingProxyType(inspection),
        source_verified=type(delivery) is UsdAssetDeliveryV1 and delivery.provenance_kind == "upstream-validated",
        source_input_bytes=MappingProxyType(dict(source_file_bytes)),
        local_support_bytes=MappingProxyType({
            delivery.source_manifest_path: source_manifest_raw,
            delivery.recipe_path: recipe_raw,
            delivery.checker_path: checker_raw,
            **support_file_bytes,
        }) if type(delivery) is UsdAssetDeliveryLocalV1 else MappingProxyType({}),
        _verification_token=_LOADER_TOKEN,
    )


def resolve_provider_representation(
    loaded: LoadedUsdDeliveryV1,
    *,
    provider: str,
    provider_build_identity: str,
    options: Mapping[str, object] | None = None,
) -> ProviderRepresentationSelectionV1:
    """Choose an exact source representation without granting runtime admission."""
    if not isinstance(loaded, LoadedUsdDeliveryV1):
        raise TypeError("loaded must be a Core-verified USD delivery")
    loaded.assert_fresh()
    provider = str(provider).strip().lower()
    builds = {"isaacsim", "geophys", "mujoco"}
    if provider not in builds:
        raise ValueError(f"unsupported provider representation route: {provider!r}")
    options_payload = dict(options or {})
    options_hash = _canonical_hash(options_payload)
    format_matched = provider in {"isaacsim", "geophys"}
    preparable = format_matched
    decision = "selected" if preparable else "rejected"
    inspected_mujoco_build = (
        "mujoco-3.8.1-libsha256-8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592"
    )
    if provider != "mujoco":
        reason = None
        recipe_id = "native-usd-source-v1"
    elif provider_build_identity == inspected_mujoco_build:
        reason = "native USD decoder is not enabled in the inspected MuJoCo 3.8.1 build"
        recipe_id = "mujoco-3.8.1-usd-decoder-rejected-v1"
    else:
        reason = "MuJoCo build identity and USD decoder status have not been verified"
        recipe_id = "mujoco-usd-build-unverified-v1"
    return ProviderRepresentationSelectionV1(
        schema_version="provider-representation-selection-v1",
        asset_identity_hash=loaded.delivery.asset_identity_hash,
        delivery_sha256=loaded.delivery_sha256,
        closure_sha256=loaded.closure_sha256,
        provider=provider,
        provider_build_identity=provider_build_identity,
        representation_format=loaded.delivery.representation_format,
        representation_id=loaded.delivery.representation_id,
        decision=decision,
        format_matched=format_matched,
        source_verified=loaded.source_verified,
        representation_preparable=preparable,
        runtime_admitted=False,
        rejection_reason=reason,
        resolver_version="f02-usd-representation-resolver-v2",
        recipe_id=recipe_id,
        options_sha256=options_hash,
    )


__all__ = [
    "LoadedUsdDeliveryV1",
    "load_usd_asset_delivery",
    "resolve_provider_representation",
    "variant_selection_hash",
]
