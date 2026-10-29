"""Planner facts and bounded candidate status."""


def build_planner(task_input: dict) -> dict:
    native = task_input["native_reference"]["planner"]
    return {
        "native_reference": native,
        "core_candidate": task_input["requested_core_candidate"]["planner"],
        "status": "BLOCKED_CORE_IK_AND_COLLISION_PLANNING; no arbitrary torque controller mapping is implied",
        "current_owners": ["task_env/planners/cartesian.py", "task_env/planners/joint.py"],
    }
