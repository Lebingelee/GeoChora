"""Observation source defaults and a non-materialized state-only candidate."""


def build_observation(task_input: dict) -> dict:
    return {
        "native_reference_defaults": task_input["native_reference"]["observation"],
        "requested_core_candidate": task_input["requested_core_candidate"]["observation_profile"],
        "status": "STATE_ONLY_CANDIDATE_NOT_MATERIALIZED",
        "missing_fields": ["object/frame-qualified free-body pose", "public contact evidence"],
        "camera_or_rendering_claim": False,
    }
