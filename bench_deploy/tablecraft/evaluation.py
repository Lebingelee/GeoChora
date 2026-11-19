"""Bind original task requirements to the existing generic terminal reviewer."""

from __future__ import annotations

from .task import task_source


def prepare_terminal_review(task_id: str, endpoint: dict, *, model_profile: dict,
                            evidence: list[dict]) -> dict:
    """Prepare an offline request from caller-verified endpoint/evidence records.

    The existing source-review protocol receives the authored goal, bindings,
    process requirements and predicate definitions as source for judgment and
    independent confirmation.
    """
    from validation.terminal.reviews import prepare_source_review

    source = task_source(task_id)
    pointers = ["/task/prompt", "/task/truth/acceptance"]
    truth = source["task"]["truth"]
    pointers.extend(f"/task/truth/{field}" for field in ("goal", "bind", "process") if field in truth)
    pointers.extend(f"/dependencies/{key}" for key in source["dependencies"])
    return prepare_source_review(source, endpoint, required_source_pointers=pointers,
                                 model_profile=model_profile, evidence=evidence)
