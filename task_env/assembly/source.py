"""Stage 1 将消费的任务场景 source 描述。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path
import tempfile


_SHA256 = re.compile(r'[0-9a-f]{64}\Z')


class UsdSnapshotLeaseV1:
    """Session-owned temporary tree copied only from a verified delivery's bytes."""

    def __init__(self, directory: tempfile.TemporaryDirectory):
        self._directory = directory
        self.root = Path(directory.name)
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if not self._closed:
            self._directory.cleanup()
            self._closed = True

    def __enter__(self):
        if self._closed:
            raise RuntimeError('USD snapshot lease is closed')
        return self

    def __exit__(self, *_exc):
        self.close()


@dataclass(frozen=True)
class UsdTaskSceneSourceV1:
    """Versioned source identity bound to one Core-verified USD delivery."""

    schema_version: str
    loaded_delivery: object
    representation: object
    task_source_identity_sha256: str
    scene_identity_sha256: str

    def validate(self) -> None:
        from .usd_delivery import LoadedUsdDeliveryV1
        from ..artifacts import ProviderRepresentationSelectionV1

        if self.schema_version != 'usd-task-scene-source-v1':
            raise ValueError('unsupported USD TaskSceneSource schema')
        if type(self.loaded_delivery) is not LoadedUsdDeliveryV1:
            raise TypeError('USD TaskSceneSource requires the verified LoadedUsdDeliveryV1 owner value')
        if type(self.representation) is not ProviderRepresentationSelectionV1:
            raise TypeError('USD TaskSceneSource requires ProviderRepresentationSelectionV1')
        if not _SHA256.fullmatch(self.task_source_identity_sha256):
            raise ValueError('USD TaskSceneSource requires a TaskSource identity SHA-256')
        if not _SHA256.fullmatch(self.scene_identity_sha256):
            raise ValueError('USD TaskSceneSource requires a Scene identity SHA-256')
        delivery = self.loaded_delivery.delivery
        selection = self.representation
        selection.validate()
        if (
            selection.asset_identity_hash,
            selection.delivery_sha256,
            selection.closure_sha256,
            selection.representation_format,
            selection.representation_id,
            selection.source_verified,
            selection.runtime_admitted,
            selection.decision,
            selection.format_matched,
            selection.representation_preparable,
        ) != (
            delivery.asset_identity_hash,
            delivery.delivery_sha256,
            delivery.closure_sha256,
            delivery.representation_format,
            delivery.representation_id,
            self.loaded_delivery.source_verified,
            False,
            'selected',
            True,
            True,
        ):
            raise ValueError('USD representation decision does not bind the exact loaded delivery')
        delivery.asset_definition.validate()

    @property
    def source_id(self) -> str:
        self.validate()
        return (
            f'usd-task-scene-source-v1:{self.loaded_delivery.delivery.delivery_sha256}:'
            f'{self.representation.identity_hash}:{self.scene_identity_sha256}:'
            f'{self.task_source_identity_sha256}'
        )

    @property
    def source_closure_sha256(self) -> str:
        self.validate()
        return self.loaded_delivery.closure_sha256

    @property
    def source_verified(self) -> bool:
        self.validate()
        return bool(self.loaded_delivery.source_verified)

    @property
    def locally_validated(self) -> bool:
        """Return the distinct local-sample validation state without upgrading upstream provenance."""
        self.validate()
        return bool(getattr(self.loaded_delivery, 'locally_validated', False))

    @property
    def validation_report_identity_sha256(self) -> str:
        self.validate()
        return hashlib.sha256(self.loaded_delivery.report_bytes).hexdigest()

    def assert_fresh(self) -> None:
        self.validate()
        self.loaded_delivery.assert_fresh()

    def acquire_snapshot(self) -> UsdSnapshotLeaseV1:
        """Create an owned snapshot from immutable verified bytes, never from re-resolved paths."""
        self.assert_fresh()
        directory = tempfile.TemporaryDirectory(prefix='geochora-usd-session-')
        root = Path(directory.name)
        try:
            for relative, raw in self.loaded_delivery.file_bytes.items():
                if type(relative) is not str or type(raw) is not bytes:
                    raise TypeError('verified USD closure must map relative paths to immutable bytes')
                target = root.joinpath(*relative.split('/'))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            report = root.joinpath(*self.loaded_delivery.delivery.validation_report_path.split('/'))
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_bytes(self.loaded_delivery.report_bytes)
            for relative, expected in self.loaded_delivery.file_bytes.items():
                actual = root.joinpath(*relative.split('/')).read_bytes()
                if actual != expected:
                    raise ValueError(f'owned USD snapshot byte mismatch: {relative}')
            return UsdSnapshotLeaseV1(directory)
        except BaseException:
            directory.cleanup()
            raise


@dataclass(frozen=True)
class TaskSceneSource:
    xml: str
    base_dir: Path
    source_id: str
    diagnostics: tuple[str, ...] = ()


__all__ = ["TaskSceneSource", "UsdSnapshotLeaseV1", "UsdTaskSceneSourceV1"]
