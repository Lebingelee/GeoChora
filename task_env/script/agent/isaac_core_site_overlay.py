"""Filtered Python dependency overlay for tools running inside Isaac Sim."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def populate_isaac_core_site_overlay(core_site, overlay):
    """Expose Core dependencies without shadowing Isaac's OpenUSD packages."""
    core_site = Path(core_site).resolve(strict=True)
    overlay = Path(overlay).resolve()
    overlay.mkdir(parents=True, exist_ok=True)
    excluded = []
    included = []
    for item in sorted(core_site.iterdir(), key=lambda entry: entry.name):
        name = item.name
        if name == 'pxr' or (
            name.lower().startswith('usd_core-') and name.endswith('.dist-info')
        ):
            excluded.append(name)
            continue
        (overlay / name).symlink_to(item, target_is_directory=item.is_dir())
        included.append(name)
    names_digest = hashlib.sha256(
        json.dumps(included, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    ).hexdigest()
    return {
        'schema_version': 'isaac-core-site-overlay-v1',
        'source_site_packages': str(core_site),
        'excluded_entries': excluded,
        'included_entry_count': len(included),
        'included_names_sha256': names_digest,
    }
