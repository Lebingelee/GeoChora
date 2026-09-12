"""Linux Flora runtime discovery for the TaskEnv-owned adapter.

This module is intentionally inert during normal ``task_env`` imports.  It
only validates paths and imports Flora after a caller explicitly asks for a
Flora scene.  The external Flora checkout remains outside GeoPhys.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import sys
from typing import Any


@dataclass(frozen=True)
class FloraRuntimeConfig:
    """Resolved paths and native options for one Linux Flora session."""

    runtime_root: Path
    module_dir: Path
    python_dir: Path
    backend: str = "vulkan"
    device_index: int = -1
    enable_debug: bool = False
    enable_external_interop: bool = False

    @classmethod
    def resolve(
        cls,
        *,
        runtime_root: str | Path | None = None,
        module_dir: str | Path | None = None,
        python_dir: str | Path | None = None,
        backend: str = "vulkan",
        device_index: int = -1,
        enable_debug: bool = False,
        enable_external_interop: bool = False,
    ) -> "FloraRuntimeConfig":
        root_value = runtime_root or os.environ.get("FLORA_ROOT")
        if root_value is None:
            raise RuntimeError(
                "Flora runtime root is not configured; pass runtime_root=... "
                "or set FLORA_ROOT"
            )
        root = Path(root_value).expanduser().resolve()
        resolved_module = Path(module_dir).expanduser().resolve() if module_dir else root / "bin" / "linux-x64"
        resolved_python = Path(python_dir).expanduser().resolve() if python_dir else root / "python"
        return cls(
            runtime_root=root,
            module_dir=resolved_module,
            python_dir=resolved_python,
            backend=str(backend),
            device_index=int(device_index),
            enable_debug=bool(enable_debug),
            enable_external_interop=bool(enable_external_interop),
        )

    def describe(self) -> dict[str, object]:
        return {
            "runtime_root": str(self.runtime_root),
            "module_dir": str(self.module_dir),
            "python_dir": str(self.python_dir),
            "backend": self.backend,
            "device_index": int(self.device_index),
            "enable_debug": bool(self.enable_debug),
            "enable_external_interop": bool(self.enable_external_interop),
        }


@dataclass(frozen=True)
class FloraRuntimeProbe:
    """Non-invasive runtime probe result."""

    config: FloraRuntimeConfig
    root_exists: bool
    module_dir_exists: bool
    native_module_exists: bool
    python_dir_exists: bool
    python_packages: tuple[str, ...]

    @property
    def available(self) -> bool:
        return bool(
            self.root_exists
            and self.module_dir_exists
            and self.native_module_exists
            and self.python_dir_exists
            and not tuple(self.missing_python_packages)
        )

    @property
    def missing_python_packages(self) -> tuple[str, ...]:
        return tuple(
            package
            for package in self.python_packages
            if not (self.config.python_dir / package).exists()
        )

    def describe(self) -> dict[str, object]:
        return {
            "schema": "task_env.flora_runtime_probe.v1",
            **self.config.describe(),
            "available": self.available,
            "root_exists": self.root_exists,
            "module_dir_exists": self.module_dir_exists,
            "native_module_exists": self.native_module_exists,
            "python_dir_exists": self.python_dir_exists,
            "python_packages": list(self.python_packages),
            "missing_python_packages": list(self.missing_python_packages),
            "native_module": str(self.config.module_dir / "FloraRenderPyNative.so"),
        }

    def require(self) -> "FloraRuntimeProbe":
        if not self.available:
            raise RuntimeError(f"Flora runtime is unavailable: {self.describe()}")
        return self


def probe_flora_runtime(
    config: FloraRuntimeConfig,
    *,
    python_packages: tuple[str, ...] = ("flora", "flora_backend"),
) -> FloraRuntimeProbe:
    """Inspect a Flora checkout without loading Vulkan or importing native code."""

    return FloraRuntimeProbe(
        config=config,
        root_exists=config.runtime_root.is_dir(),
        module_dir_exists=config.module_dir.is_dir(),
        native_module_exists=(config.module_dir / "FloraRenderPyNative.so").is_file(),
        python_dir_exists=config.python_dir.is_dir(),
        python_packages=tuple(python_packages),
    )


def load_flora_backend(config: FloraRuntimeConfig) -> Any:
    """Import the installed ``flora_backend`` package after path validation."""

    probe_flora_runtime(config).require()
    for path in (config.python_dir, config.module_dir):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    return importlib.import_module("flora_backend")


__all__ = [
    "FloraRuntimeConfig",
    "FloraRuntimeProbe",
    "load_flora_backend",
    "probe_flora_runtime",
]
