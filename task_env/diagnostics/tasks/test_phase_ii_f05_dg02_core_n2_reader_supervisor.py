from __future__ import annotations

import os
from pathlib import Path

from task_env.diagnostics.tasks.f05_dg02_core_n2_reader_supervisor import (
    _classify_reader_result,
    _frozen_reader_source_identity,
    _process_group_sample,
    _reader_plan_input_identities,
)


def test_process_group_sample_includes_current_process_and_cpu_counter():
    rss, pids, cpu_seconds = _process_group_sample(os.getpgrp())

    assert os.getpid() in pids
    assert rss > 0
    assert cpu_seconds >= 0.0


def test_reader_tracking_gate_failure_is_a_completed_supervised_read():
    receipt = {
        "status": "FAIL_N2_COLD_READ",
        "failure_reasons": [
            {"code": "task_predicate", "detail": "tracking threshold failed"},
            {"code": "task_predicate", "detail": "tracking threshold failed"},
        ],
    }

    assert _classify_reader_result(1, receipt) == "COMPLETED_WITH_TRACKING_GATE_FAILURE"


def test_unexpected_reader_failure_is_not_misclassified_as_a_gate_result():
    receipt = {
        "status": "FAIL_N2_COLD_READ",
        "failure_reasons": [{"code": "cross_run", "detail": "identity mismatch"}],
    }

    assert _classify_reader_result(1, receipt) == "FAIL_UNEXPECTED_READER_EXIT_OR_RECEIPT"


def test_new_reader_is_bound_separately_from_formal_producer_code(monkeypatch):
    from task_env.diagnostics.tasks import f05_dg02_core_n2_reader_supervisor as supervisor

    reader = Path(supervisor.CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_cold_reader.py")
    other = Path(supervisor.CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_plan.py")
    formal = {
        "input_identity": {"core_input_head": "a" * 40},
        "code": {"tracked_inputs": [
            {"path": str(reader), "sha256": "b" * 64},
            {"path": str(other), "sha256": "c" * 64},
        ]},
        "runtime": {"file_sha256": {}},
    }
    monkeypatch.setattr(supervisor, "_git_blob_sha", lambda _head, _path: "b" * 64)

    identity = _frozen_reader_source_identity(formal, reader)
    remaining = _reader_plan_input_identities(formal, reader)

    assert identity["sha256"] == "b" * 64
    assert identity["verification"] == "git_blob_at_formal_core_head"
    assert [row["path"] for row in remaining] == [str(other)]
