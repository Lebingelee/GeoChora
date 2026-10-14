"""V5 clearance trajectory composed with guarded close authorization.

The guarded authorization candidate V1 predates the accepted V5 NutAssembly
clearance path.  This version combines the same guard policy with V5 through
multiple inheritance, preserving V1 unchanged for provenance while making the
trajectory dependency explicit in this candidate's version and identity.
"""

from __future__ import annotations

from .clearance_candidate_v5 import NutAssemblyHandClearanceCandidateV5
from .guarded_authorization_candidate import (
    NutAssemblyGuardedAuthorizationCandidateV1,
)


class NutAssemblyGuardedAuthorizationCandidateV2(
    NutAssemblyGuardedAuthorizationCandidateV1,
    NutAssemblyHandClearanceCandidateV5,
):
    """Primary 9 N / alternative 8 N guard on the accepted V5 full-task path."""

    version = (
        "nutassembly-r5-v5-clearance-primary-readiness-"
        "alternative-8n-guarded-v2"
    )


__all__ = ["NutAssemblyGuardedAuthorizationCandidateV2"]
