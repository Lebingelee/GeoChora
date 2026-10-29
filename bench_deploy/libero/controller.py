"""Native controller identity and unresolved Core timing/drive equivalence."""


def build_controller(task_input: dict) -> dict:
    native = task_input["native_reference"]["controller"]
    return {
        "native_reference": native,
        "control_frequency_hz": native["control_frequency_hz"],
        "control_timestep_seconds": native["control_timestep_seconds"],
        "hold_policy": native["hold_policy"],
        "core_candidate_frequency_hz": task_input["requested_core_candidate"]["control_frequency_hz"],
        "core_equivalence": "NOT_ESTABLISHED; do not map native OSC_POSE to Core Position or silently replace the native 20 Hz period with the Core candidate rate",
        "current_core_owner": "task_env/controllers/absolute_joint.py and task_env/runtime/sessions/control.py",
    }
