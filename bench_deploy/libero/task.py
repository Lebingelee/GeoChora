"""Pinned task identity and source-level task semantics."""


def build_task(manifest: dict) -> dict:
    task = manifest["task"]
    predicate = next(
        (row for row in manifest["source_code_references"]
         if row["repository"] == "libero" and row["path"] == "libero/libero/envs/predicates/base_predicates.py"),
        None,
    )
    if predicate is None:
        raise ValueError("pinned LIBERO predicate implementation reference is missing")
    return {
        "uid": task["task_uid"],
        "suite": task["suite"],
        "native_filename": task["native_filename"],
        "language": task["language"],
        "bddl": task["bddl"],
        "objects": task["objects_instance_to_type"],
        "fixtures": task["fixtures_instance_to_type"],
        "native_goal_semantics": {
            "expression": task["bddl"]["goal_expression"],
            "predicate_source": predicate,
            "required_meaning": "object-object On requires geom-group contact, vertical ordering, and strict XY body-centre distance < 0.03 m",
            "core_evaluator_status": "NOT_ADMITTED",
        },
        "native_initialization": {
            "selected_source": task["selected_pruned_init"],
            "loader_policy": "Pinned LIBERO loader selects this .pruned_init; this package verifies and copies bytes only.",
            "unpickle_or_torch_load": False,
            "reset_realization": "NOT_RUN",
            "flat_state_order": "UNKNOWN_NOT_INFERRED",
        },
    }
