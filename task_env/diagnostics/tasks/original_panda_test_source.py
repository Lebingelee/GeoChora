"""Explicit test-only access to the pinned original Panda assets.

These fixtures do not provide an owned snapshot.  They are for read-only tests
only and must not be used by tests that mutate or remove source assets.
"""
from pathlib import Path
import hashlib
import subprocess


def original_panda_files():
    from task_env.robots.panda import PandaAgent
    from task_env.tasks.position_candidate.source import MENAGERIE_REVISION, EXPECTED_PANDA_CLOSURE
    from task_env.assembly.assets import _source_closure_digest
    from task_env.runtime.sessions.source import source_asset_bytes

    manifest = PandaAgent().asset_manifest()
    xml_path = manifest.mjcf_sources[0].resolve(strict=True)
    revision = subprocess.check_output(
        ['git', '-C', str(xml_path.parent.parent), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != manifest.source_revision or revision != MENAGERIE_REVISION:
        raise ValueError('original Panda source revision differs from the pinned asset')
    xml = xml_path.read_bytes()
    files = {'panda.xml': xml, **source_asset_bytes(xml_path.parent, xml.decode('utf-8'))}
    if len(files) != 68 or _source_closure_digest(files) != EXPECTED_PANDA_CLOSURE:
        raise ValueError('original Panda source closure differs from the pinned receipt')
    return manifest, xml_path.parent, files


def install_position_original_source(monkeypatch):
    from task_env.tasks.position_candidate import source
    from task_env.assembly.assets import _asset_definition_from_manifest, _source_closure_digest

    def use_original(scene_module, _destination, scene):
        manifest, root, files = original_panda_files()
        asset = _asset_definition_from_manifest(manifest)
        if not any(item == asset for item in scene.assets):
            raise ValueError('Scene does not bind the pinned Panda asset declaration')
        discovered = scene_module.import_scene_source(
            scene_module.SceneSource.mjcf_path(root / 'panda.xml'), cache=False)
        paths = {Path(path).resolve().relative_to(root).as_posix()
                 for path in discovered.dependency_paths}
        if paths != set(files):
            raise ValueError('original Panda importer dependencies differ from pinned closure')
        return root, files, _source_closure_digest(files)

    monkeypatch.setattr(source, '_copy_panda_snapshot', use_original)


def install_physical_original_source(monkeypatch):
    from task_env.tasks.position_candidate import source
    from task_env.assembly.assets import _asset_definition_from_manifest, _source_closure_digest

    def use_original(_destination, scene):
        manifest, root, files = original_panda_files()
        asset = _asset_definition_from_manifest(manifest)
        if not any(item == asset for item in scene.assets):
            raise ValueError('Scene does not bind the pinned Panda asset declaration')
        return root, files, _source_closure_digest(files)

    monkeypatch.setattr(source, '_copy_panda_snapshot_from_xml', use_original)


def install_legacy_original_source(monkeypatch):
    """Keep exact receipt type while checking original assets on every use.

    Only the generated XML is virtual; every referenced asset is read from the
    pinned original tree and checked against the receipt's captured bytes.
    The production receipt's owned-snapshot implementation is unchanged.
    """
    from task_env.assembly.assets import _source_closure_digest
    from task_env.runtime.sessions.source import ExecutionSourceReceiptV1

    original_validate = ExecutionSourceReceiptV1.validate_snapshot
    active = {}

    def validate(receipt):
        if active.get(id(receipt)) is not receipt:
            return original_validate(receipt)
        _, root, panda_files = original_panda_files()
        if receipt.snapshot_root != root:
            raise ValueError('test receipt does not bind the original Panda directory')
        files = dict(receipt.closure_files)
        if (files.get('scene.xml') != receipt.importer_xml
                or hashlib.sha256(receipt.importer_xml).hexdigest() != receipt.importer_xml_sha256
                or hashlib.sha256(files['canonical-source.xml']).hexdigest() != receipt.canonical_xml_sha256
                or _source_closure_digest(files) != receipt.source_closure_digest):
            raise ValueError('test receipt XML or closure identity changed')
        for logical, expected in files.items():
            if logical in ('scene.xml', 'canonical-source.xml'):
                continue
            if logical not in panda_files or panda_files[logical] != expected:
                raise ValueError(f'test receipt asset differs from the pinned original: {logical}')

    def create(cls, *, source_id, canonical_xml, importer_xml, closure_files,
               expected_canonical_xml_sha256=None):
        if not isinstance(canonical_xml, bytes) or not isinstance(importer_xml, bytes):
            raise TypeError('execution source XML inputs must be immutable bytes')
        canonical_sha = hashlib.sha256(canonical_xml).hexdigest()
        if expected_canonical_xml_sha256 is not None and canonical_sha != expected_canonical_xml_sha256:
            raise ValueError('canonical source XML bytes differ from the admitted source')
        _, root, _ = original_panda_files()
        files = dict(closure_files)
        files['scene.xml'] = importer_xml
        # Register before dataclass initialization, whose post-init validates.
        receipt = object.__new__(cls)
        active[id(receipt)] = receipt
        try:
            cls.__init__(receipt, source_id, canonical_sha, hashlib.sha256(importer_xml).hexdigest(),
                         _source_closure_digest(files), root, importer_xml, files, None)
        except BaseException:
            active.pop(id(receipt), None)
            raise
        return receipt

    monkeypatch.setattr(ExecutionSourceReceiptV1, 'validate_snapshot', validate)
    monkeypatch.setattr(ExecutionSourceReceiptV1, 'create', classmethod(create))
