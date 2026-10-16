"""Historical P1.1 construction entry point; no materialization."""
from ...artifacts import TaskArtifact
from .artifact import HISTORICAL_ARTIFACT_ID, HISTORICAL_ARTIFACT_VERSION, build_task_artifact


def build_candidate() -> TaskArtifact:
    """Explicit default timeline and current reset envelope, still candidate."""
    return build_task_artifact(
        artifact_id=HISTORICAL_ARTIFACT_ID,
        artifact_version=HISTORICAL_ARTIFACT_VERSION,
    )
