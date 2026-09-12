"""Deployment task's explicit asset boundary.

The mesh/XML is shared with the simulator task, while registration and
observation/reset semantics live in this package.  Keeping this forwarding
module makes the two task packages independently discoverable without
duplicating the canonical asset bytes.
"""

from ..go2_walk.assets import (
    GO2_GROUND_GEOM_NAME,
    GO2_SCENE_UID,
    Go2WalkSceneComposer,
    canonical_xml_digest,
)

__all__ = [
    "GO2_GROUND_GEOM_NAME",
    "GO2_SCENE_UID",
    "Go2WalkSceneComposer",
    "canonical_xml_digest",
]
