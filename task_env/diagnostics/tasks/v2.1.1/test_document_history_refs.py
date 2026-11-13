"""Focused historical source-reference checks for the documentation validator."""
import importlib.util
from pathlib import Path
import subprocess

import pytest


def _validator():
    path = Path(__file__).resolve().parents[4] / '.agents/skills/geochora-doc-governance/scripts/validate_docs.py'
    spec = importlib.util.spec_from_file_location('geochora_docs_validator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(('anchor', 'expected'), [
    ('L1', True), ('L1-L3', True), ('L2-L2', True),
    ('L0', False), ('L2-L4', False), ('L3-L2', False),
    ('section', True), ('missing', False),
])
def test_source_line_ranges_and_markdown_anchors(monkeypatch, anchor, expected):
    validator = _validator()
    monkeypatch.setattr(validator, 'show', lambda ref, path: b'# Section\nline two\nline three\n')
    assert validator.source_link_exists('ref', 'doc.md', 'source.py', anchor) is expected


def test_missing_source_does_not_become_valid(monkeypatch):
    validator = _validator()
    def missing(ref, path):
        raise subprocess.CalledProcessError(1, 'git show')
    monkeypatch.setattr(validator, 'show', missing)
    assert not validator.source_link_exists('ref', 'doc.md', 'missing.py', 'L1')
