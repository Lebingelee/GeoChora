from __future__ import annotations

import os

from task_env.diagnostics.tasks.f05_dg02_core_n2_reader_supervisor import (
    _classify_reader_result,
    _process_group_sample,
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
