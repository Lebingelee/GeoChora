"""Source predicate requirements and unavailable-state handling."""


def build_evaluation(task_input: dict, manifest: dict) -> dict:
    semantics = task_input["semantics"]
    return {
        "source_goal": manifest["task"]["bddl"]["goal_expression"],
        "native_predicate_owner": "LIBERO object state and predicate sources",
        "required_contact": semantics["contact_evidence"],
        "required_xy_threshold_m": semantics["goal_threshold_m"],
        "required_evidence": semantics["required_evidence"],
        "unavailable_is_not_false": semantics["unavailable_is_not_false"],
        "core_evaluator_owner": "task_env/environment/task_definition.py::TaskDefinitionBase.evaluate_predicates",
        "status": "BLOCKED_PROVIDER_OR_CORE_STATE_CONTRACT",
    }
