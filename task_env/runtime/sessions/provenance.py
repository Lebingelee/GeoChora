"""Mechanically identify the selected provider without constructing its runtime."""
from importlib import metadata, util
from pathlib import Path
import hashlib
import subprocess


def provider_build_identity(provider):
    if provider not in ('geophys', 'mujoco'):
        raise ValueError('unknown provider')
    spec = util.find_spec(provider)
    if spec is None or spec.origin is None:
        raise ValueError(f'{provider} import source unavailable')
    origin = Path(spec.origin).resolve()
    try:
        package_version = metadata.version(provider)
    except metadata.PackageNotFoundError:
        package_version = None
    revision = None
    dirty = None
    if provider == 'geophys':
        try:
            revision = subprocess.check_output(['git', '-C', str(origin.parent), 'rev-parse', 'HEAD'], text=True).strip()
            # Include tracked changes and nonignored untracked content in a dirty
            # build fingerprint, rather than reporting a clean commit for them.
            status = subprocess.check_output(['git', '-C', str(origin.parent), 'status', '--porcelain'], text=True)
            if status:
                tree = Path(subprocess.check_output(['git', '-C', str(origin.parent), 'rev-parse', '--show-toplevel'], text=True).strip())
                names = subprocess.check_output(['git', '-C', str(tree), 'ls-files', '-z', '--cached', '--others', '--exclude-standard']).split(b'\0')
                digest = hashlib.sha256()
                for name in sorted(n for n in names if n):
                    path = tree / name.decode()
                    digest.update(name)
                    if path.is_file():
                        digest.update(hashlib.sha256(path.read_bytes()).digest())
                dirty = digest.hexdigest()
        except (subprocess.CalledProcessError, FileNotFoundError):
            if package_version is None:
                raise ValueError('GeoPhys build has neither checkout nor package version')
    manifest_version = ('git:' + revision + (':dirty:' + dirty if dirty else '')
                        if revision else 'package:' + package_version)
    return {'provider': provider, 'package_version': package_version,
            'repository_revision': revision, 'dirty_build_sha256': dirty,
            'import_origin': str(origin), 'origin_sha256': hashlib.sha256(origin.read_bytes()).hexdigest(),
            'manifest_version': manifest_version}
