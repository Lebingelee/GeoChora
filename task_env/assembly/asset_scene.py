"""Load an asset-scene handoff against exact verified delivery and evidence bytes."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from ..artifacts.asset_scene import AssetScenePreparationV1
from ..artifacts.contracts import UsdDeliveryFileV1
from .assets import _source_closure_digest
from .usd_delivery import (
    LoadedUsdDeliveryV1, _MAX_CLOSURE_BYTES, _safe_read, _strict_json_bytes,
    load_usd_asset_delivery,
)


_PREPARATION_TOKEN = object()


@dataclass(frozen=True)
class LoadedAssetScenePreparationV1:
    """Verified preparation receipt; not runtime admission or task validation."""

    preparation: AssetScenePreparationV1
    manifest_path: Path
    manifest_sha256: str
    loaded_delivery: LoadedUsdDeliveryV1
    evidence_bytes: object
    delivery_manifest_sha256: str
    _token: object = field(repr=False, compare=False)

    def __post_init__(self):
        if self._token is not _PREPARATION_TOKEN:
            raise TypeError("asset scene preparation must be created by its loader")

    @property
    def identity_hash(self):
        return self.preparation.identity_hash

    def assert_fresh(self):
        path = self.manifest_path
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != self.manifest_sha256:
            raise ValueError("asset scene preparation manifest changed after inspection")
        for relative, expected in self.evidence_bytes.items():
            actual = _safe_read(path.parent, relative, label="asset scene preparation input")
            if actual != expected:
                raise ValueError(f"asset scene preparation input changed: {relative}")
        self.loaded_delivery.assert_fresh()


def load_asset_scene_preparation(path, *, require_passed=True):
    """Verify handoff bytes and reuse Core's USD loader without starting Isaac."""
    path = Path(path).expanduser().absolute()
    if path.is_symlink():
        raise ValueError("asset scene preparation manifest cannot be a symlink")
    root = path.parent
    raw = _safe_read(root, path.name, label="asset scene preparation manifest", max_bytes=16 * 1024**2)
    value = AssetScenePreparationV1.from_mapping(
        _strict_json_bytes(raw, label="asset scene preparation manifest"),
    )
    if require_passed:
        value.require_passed()
    claims_refs = tuple(
        UsdDeliveryFileV1(item.metrics["claims_path"], item.metrics["claims_size_bytes"],
                          item.metrics["claims_sha256"])
        for item in value.evidence if item.check == "required-claims"
        and isinstance(item.metrics.get("claims_path"), str)
        and type(item.metrics.get("claims_size_bytes")) is int
        and isinstance(item.metrics.get("claims_sha256"), str)
    )
    claims_result_refs = tuple(
        UsdDeliveryFileV1(item.metrics["checker_result_path"],
                          item.metrics["checker_result_size_bytes"],
                          item.metrics["result_sha256"])
        for item in value.evidence if item.check == "required-claims"
        and isinstance(item.metrics.get("checker_result_path"), str)
        and type(item.metrics.get("checker_result_size_bytes")) is int
        and isinstance(item.metrics.get("result_sha256"), str)
    )
    refs = (value.request, value.delivery_manifest, value.source_terms,
            *value.target_source_files, *(item.result for item in value.evidence),
            *claims_refs, *claims_result_refs)
    by_path = {}
    total = 0
    for ref in refs:
        if ref.path in by_path:
            raise ValueError(f"asset scene preparation references must use distinct paths: {ref.path}")
        content = _safe_read(root, ref.path, label="asset scene preparation input",
                             max_bytes=_MAX_CLOSURE_BYTES - total)
        total += len(content)
        if len(content) != ref.size_bytes or hashlib.sha256(content).hexdigest() != ref.sha256:
            raise ValueError(f"asset scene preparation input byte mismatch: {ref.path}")
        by_path[ref.path] = content
    source_bytes = {ref.path: by_path[ref.path] for ref in value.target_source_files}
    if _source_closure_digest(source_bytes) != value.target_asset.source_content_sha256:
        raise ValueError("target source identity does not bind its exact source byte inventory")
    delivery = load_usd_asset_delivery(root / value.delivery_manifest.path)
    if delivery.manifest_bytes_sha256 != value.delivery_manifest.sha256:
        raise ValueError("asset scene preparation delivery manifest byte hash mismatch")
    if delivery.closure_sha256 != value.delivery_closure_sha256:
        raise ValueError("asset scene preparation belongs to another USD delivery closure")
    if delivery.delivery.asset_definition.identity_hash != value.target_asset.identity_hash:
        raise ValueError("prepared USD delivery does not belong to the declared target asset")
    if delivery.delivery.asset_definition.source_content_sha256 != value.target_asset.source_content_sha256:
        raise ValueError("prepared USD delivery source inventory differs from the target source inventory")
    for item in value.evidence:
        result = _strict_json_bytes(by_path[item.result.path], label="preparation checker result")
        expected = {
            "schema_version": "asset-preparation-check-result-v1",
            "check": item.check,
            "status": item.status,
            "input_preparation_sha256": item.input_preparation_sha256,
            "checker_sha256": item.checker_sha256,
            "tool_versions": dict(item.tool_versions),
            "scope": item.scope,
            "metrics": item.to_mapping()["metrics"],
        }
        if (not isinstance(result, dict)
                or json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
                != json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False)):
            raise ValueError(f"raw checker result differs from its preparation receipt: {item.check}")
        if item.check == "required-claims":
            claim_path = item.metrics.get("claims_path")
            claim_bytes = by_path.get(claim_path) if isinstance(claim_path, str) else None
            checker_path = item.metrics.get("checker_result_path")
            checker_bytes = by_path.get(checker_path) if isinstance(checker_path, str) else None
            if claim_bytes is None or hashlib.sha256(claim_bytes).hexdigest() != item.metrics.get("claims_sha256"):
                raise ValueError("required claims evidence does not bind the raw claims input")
            claims_doc = _strict_json_bytes(claim_bytes, label="required claims input")
            checker_result = _strict_json_bytes(checker_bytes, label="required claims checker result") \
                if checker_bytes is not None else None
            rows = checker_result.get("claims") if isinstance(checker_result, dict) else None
            assets = claims_doc.get("assets") if isinstance(claims_doc, dict) else None
            declared = [
                (asset.get("id"), claim.get("id"))
                for asset in assets if isinstance(asset, dict)
                for claim in asset.get("claims", []) if isinstance(claim, dict)
            ] if isinstance(assets, list) else []
            observed = [
                (row.get("asset"), row.get("id"))
                for row in rows if isinstance(row, dict)
            ] if isinstance(rows, list) else []
            metrics = item.metrics
            errors = []
            if checker_bytes is None:
                errors.append("missing checker bytes")
            elif hashlib.sha256(checker_bytes).hexdigest() != metrics.get("result_sha256"):
                errors.append("checker result hash")
            if not declared or declared != observed:
                errors.append(f"claim identities declared={declared!r} observed={observed!r}")
            if not isinstance(checker_result, dict) or checker_result.get("passed") is not True:
                errors.append("checker aggregate status")
            if not isinstance(rows, list) or any(
                    not isinstance(row, dict) or row.get("passed") is not True for row in rows):
                errors.append("per-claim status")
            if metrics.get("required_count") != len(declared):
                errors.append("required count")
            if not isinstance(rows, list) or metrics.get("executed_count") != len(rows):
                errors.append("executed count")
            if not isinstance(rows, list) or metrics.get("passed_count") != len(rows):
                errors.append("passed count")
            if tuple(metrics.get("claim_ids", ())) != tuple(claim_id for _, claim_id in declared):
                errors.append("claim IDs")
            if errors:
                raise ValueError(f"required claims evidence mismatch: {', '.join(errors)}")
    return LoadedAssetScenePreparationV1(
        value, path, hashlib.sha256(raw).hexdigest(), delivery,
        MappingProxyType(by_path), delivery.manifest_bytes_sha256, _PREPARATION_TOKEN,
    )
