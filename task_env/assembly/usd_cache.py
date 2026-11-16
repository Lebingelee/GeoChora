"""Install and locate verified USD deliveries independently of diagnostic runs."""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

_KEY = re.compile(r'[a-z0-9][a-z0-9_.-]*\Z')


def _location(provider: str, robot_uid: str, root: Path | None = None) -> Path:
    if any(type(value) is not str or not _KEY.fullmatch(value) or value in {'.', '..'}
           for value in (provider, robot_uid)):
        raise ValueError('asset provider and Robot uid must be simple identifiers')
    if root is None:
        configured = os.environ.get('GEOCHORA_USD_ASSET_ROOT')
        root = Path(configured).expanduser() if configured else Path.home() / '.cache/geochora/usd'
    return Path(root).expanduser().absolute() / provider / robot_uid


def installed_usd_manifest(provider: str, robot_uid: str, *, root: Path | None = None) -> Path:
    """Find an installed package without importing a provider or inspecting USD."""
    manifest = _location(provider, robot_uid, root) / 'delivery_manifest.json'
    if not manifest.is_file():
        raise ValueError(f'No installed USD asset for Robot {robot_uid!r} and provider {provider!r}; '
                         'install the supported asset package before constructing the environment')
    return manifest


def install_usd_delivery(manifest: str | Path, *, provider: str, robot_uid: str,
                         root: Path | None = None) -> Path:
    """Copy a verified delivery's complete byte closure into the local asset store.

    The destination is immutable: an existing package is reused only if it
    verifies and has the same manifest bytes. No historical directory is linked.
    """
    from .usd_delivery import load_usd_asset_delivery

    loaded = load_usd_asset_delivery(manifest)
    loaded.assert_fresh()
    destination = _location(provider, robot_uid, root)
    if destination.exists():
        existing = load_usd_asset_delivery(destination / 'delivery_manifest.json')
        if existing.manifest_bytes_sha256 != loaded.manifest_bytes_sha256:
            raise FileExistsError('a different USD asset package is already installed for this Robot/provider')
        return existing.manifest_path

    files = {}
    for part in (loaded.file_bytes, loaded.source_input_bytes, loaded.local_support_bytes,
                 {loaded.delivery.validation_report_path: loaded.report_bytes,
                  'delivery_manifest.json': loaded.manifest_path.read_bytes()}):
        for name, data in part.items():
            if name in files and files[name] != data:
                raise ValueError('USD delivery contains conflicting byte paths')
            files[name] = data
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f'.{robot_uid}-', dir=destination.parent))
    try:
        for name, data in files.items():
            path = temporary.joinpath(*PurePosixPath(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        installed = load_usd_asset_delivery(temporary / 'delivery_manifest.json')
        if installed.manifest_bytes_sha256 != loaded.manifest_bytes_sha256:
            raise ValueError('installed USD manifest differs from verified input')
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination / 'delivery_manifest.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', required=True)
    parser.add_argument('--robot', required=True)
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args(argv)
    print(install_usd_delivery(args.manifest, provider=args.provider, robot_uid=args.robot))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
