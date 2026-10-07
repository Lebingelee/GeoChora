"""Explicit bounded PickCube timebase variants; historical default stays exact."""
from dataclasses import replace
from ...artifacts import TaskArtifact, Timebase
from .candidate import build_candidate

PROFILES = {'TB-500': (1, .002), 'TB-100': (5, .010), 'TB-50': (10, .020)}


def build_timebase_candidate(profile: str) -> TaskArtifact:
    if profile not in PROFILES:
        raise ValueError('unsupported explicit PickCube timebase profile')
    default = build_candidate()
    if profile == 'TB-500':
        return default
    substeps, dt = PROFILES[profile]
    return replace(default, artifact_version='ver_p1_8_d_' + profile.lower().replace('-', ''),
                   timebase=Timebase(default.timebase.physics_dt, substeps, dt))


def require_timebase_family(artifact: TaskArtifact) -> str:
    """Admit only exact declared variants, including all unchanged semantic fields."""
    if not isinstance(artifact, TaskArtifact):
        raise TypeError('TaskArtifact required')
    mapping = artifact.to_mapping()
    for profile in PROFILES:
        expected = build_timebase_candidate(profile)
        if mapping == expected.to_mapping() and artifact.identity_hash == expected.identity_hash:
            return profile
    raise ValueError('Artifact is not an exact declared PickCube timebase variant')
