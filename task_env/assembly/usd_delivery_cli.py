"""Small JSON CLI for inspecting a byte-bound USD delivery without runtime admission."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from .usd_delivery import load_usd_asset_delivery, resolve_provider_representation


def _write_atomic(path: Path, payload: dict) -> None:
    path = path.absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write((json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _provider_builds(values: list[str], parser: argparse.ArgumentParser) -> dict[str, str]:
    builds = {}
    for item in values:
        provider, separator, identity = item.partition("=")
        if not separator or not provider or not identity or provider in builds:
            parser.error("--provider-build requires unique provider=exact-build entries")
        builds[provider] = identity
    return builds


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--allow-synthetic", action="store_true", help="test-only opt-in for synthetic fixture deliveries")
    parser.add_argument("--provider-build", action="append", default=[], help="exact provider=build identity; repeatable")
    parser.add_argument("--output", type=Path, help="optional atomically written JSON receipt")
    args = parser.parse_args(argv)
    builds = _provider_builds(args.provider_build, parser)
    try:
        loaded = load_usd_asset_delivery(args.manifest, allow_synthetic=args.allow_synthetic)
        selections = {
            provider: resolve_provider_representation(
                loaded, provider=provider, provider_build_identity=identity
            ).to_mapping()
            for provider, identity in sorted(builds.items())
        }
        result = {
            "result": "PASS",
            "schema_version": "usd-delivery-inspection-v1",
            "asset_identity_hash": loaded.delivery.asset_identity_hash,
            "delivery_sha256": loaded.delivery_sha256,
            "closure_sha256": loaded.closure_sha256,
            "provenance_kind": loaded.delivery.provenance_kind,
            "source_verified": loaded.source_verified,
            "inspection": dict(loaded.inspection),
            "provider_selections": selections,
            "runtime_admitted": False,
        }
        if args.output is not None:
            try:
                _write_atomic(args.output, result)
            except Exception as error:
                result = {
                    "result": "ERROR",
                    "error_kind": "report-write-failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "runtime_admitted": False,
                }
                print(json.dumps(result, sort_keys=True))
                return 2
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, RuntimeError) as error:
        result = {
            "result": "REJECTED",
            "error_type": type(error).__name__,
            "error": str(error),
            "runtime_admitted": False,
        }
        print(json.dumps(result, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
