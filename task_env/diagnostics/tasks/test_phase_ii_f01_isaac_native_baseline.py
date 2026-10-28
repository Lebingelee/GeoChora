"""Provider-free F01 worker, supervisor, and independent-reader S1 tests."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from task_env.diagnostics.tasks import f01_isaac_native_baseline as worker
from task_env.diagnostics.tasks import f01_isaac_native_reader as reader
from task_env.diagnostics.tasks import f01_isaac_native_supervisor as supervisor


REPO = Path(__file__).resolve().parents[3]
PYTHON = Path(sys.executable)
ISAAC_PYTHON = REPO / "workspace/environments/isaacsim-6.2.0/bin/python"
WORKER_SCRIPT = REPO / "task_env/diagnostics/tasks/f01_isaac_native_baseline.py"
WORKER_MODULE = "task_env.diagnostics.tasks.f01_isaac_native_baseline"
READER_SCRIPT = Path(reader.__file__)


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.update({"PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})
    return env


class F01WorkerCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="f01-s1-")
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run_worker(self, name: str, *args: str) -> tuple[subprocess.CompletedProcess[str], Path]:
        run_dir = self.root / name
        run_dir.mkdir()
        plan = worker.default_plan()
        plan["run_id"] = name
        (run_dir / "run_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        completed = subprocess.run(
            [str(PYTHON), "-B", "-m", WORKER_MODULE, "--synthetic-s1-worker", "--run-dir", str(run_dir), *args],
            cwd=REPO, env=_env(), text=True, capture_output=True, timeout=120, check=False,
        )
        return completed, run_dir

    def test_real_cli_success_strict_receipt_and_independent_reader(self) -> None:
        completed, run_dir = self._run_worker("success")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        receipt = json.loads((run_dir / "native_result.json").read_text())
        self.assertEqual(receipt["status"], "PASS_SYNTHETIC_S1_ONLY")
        self.assertTrue(receipt["app_closed"])
        self.assertEqual(receipt["app_close_attempts"], 1)
        self.assertEqual(receipt["timeline_stop_attempts"], 1)
        self.assertEqual(receipt["callbacks_registered"], receipt["callbacks_deregistered"])
        self.assertEqual(receipt["total_physics_steps"], 481)
        out = run_dir / "reader.json"
        read = subprocess.run(
            [str(PYTHON), "-B", str(READER_SCRIPT), "--result", str(run_dir / "native_result.json"),
             "--trace", str(run_dir / "native_trace.jsonl"), "--output", str(out), "--allow-synthetic-fixture"],
            cwd=REPO, env=_env(), text=True, capture_output=True, timeout=120, check=False,
        )
        self.assertEqual(read.returncode, 0, read.stdout + read.stderr)
        self.assertEqual(json.loads(out.read_text())["status"], "SYNTHETIC_FIXTURE_VERIFIED_ONLY")
        rejected = reader.verify(run_dir / "native_result.json", run_dir / "native_trace.jsonl")
        self.assertEqual(rejected["status"], "REJECTED_SYNTHETIC_EVIDENCE")
        self.assertFalse(rejected["native_gate"])
        verified = reader.verify(run_dir / "native_result.json", run_dir / "native_trace.jsonl", allow_synthetic_fixture=True)
        self.assertTrue(verified["checks"]["fixed_plan_matches_package"])
        frozen_plan = json.loads((run_dir / "run_plan.json").read_text())
        frozen_plan["scene"]["cube_mass_kg"] = 1.0
        (run_dir / "run_plan.json").write_text(json.dumps(frozen_plan), encoding="utf-8")
        tampered = reader.verify(run_dir / "native_result.json", run_dir / "native_trace.jsonl", allow_synthetic_fixture=True)
        self.assertFalse(tampered["checks"]["fixed_plan_matches_package"])

    def test_primary_and_cleanup_errors_are_both_preserved(self) -> None:
        completed, run_dir = self._run_worker("dual-error", "--synthetic-fault", "primary-and-cleanup")
        self.assertEqual(completed.returncode, 1)
        receipt = json.loads((run_dir / "native_result.json").read_text())
        self.assertEqual(receipt["worker_error"]["type"], "RuntimeError")
        self.assertTrue(any("app_close" == row["stage"] for row in receipt["cleanup_errors"]))
        self.assertEqual(receipt["app_close_attempts"], 1)
        self.assertFalse(receipt["app_closed"])

    def test_close_error_and_nonzero_worker_exit(self) -> None:
        completed, run_dir = self._run_worker("close-error", "--synthetic-fault", "close")
        self.assertEqual(completed.returncode, 1)
        receipt = json.loads((run_dir / "native_result.json").read_text())
        self.assertFalse(receipt["app_closed"])
        self.assertEqual(receipt["app_close_attempts"], 1)
        failed, failed_dir = self._run_worker("prestep-error", "--synthetic-fault", "fail-before-step")
        self.assertEqual(failed.returncode, 1)
        fail_receipt = json.loads((failed_dir / "native_result.json").read_text())
        self.assertEqual(fail_receipt["total_physics_steps"], 0)
        self.assertTrue(fail_receipt["app_closed"])

    def test_partial_progress_is_durable_and_stage_specific(self) -> None:
        completed, run_dir = self._run_worker("partial", "--synthetic-fault", "partial-progress")
        self.assertEqual(completed.returncode, 1)
        progress = json.loads((run_dir / "progress.json").read_text())
        receipt = json.loads((run_dir / "native_result.json").read_text())
        self.assertEqual(progress["total_physics_steps"], 20)
        self.assertEqual(progress["trace_rows"], 21)
        self.assertEqual(receipt["worker_error"]["stage"], "round_1_step_21")
        self.assertEqual(receipt["total_physics_steps"], 21)

    def test_nan_sentinels_fail_gates_and_final_receipt_failure_is_reported(self) -> None:
        completed, run_dir = self._run_worker("nan", "--synthetic-fault", "nan-state")
        self.assertEqual(completed.returncode, 1)
        receipt = json.loads((run_dir / "native_result.json").read_text())
        self.assertTrue(receipt["serialization_warnings"])
        self.assertEqual(receipt["serialization_warnings"][0]["reason"], "non_finite_number")
        independently_read = reader.verify(run_dir / "native_result.json", run_dir / "native_trace.jsonl", allow_synthetic_fixture=True)
        self.assertEqual(independently_read["status"], "SYNTHETIC_FIXTURE_VERIFIED_ONLY")
        self.assertFalse(independently_read["native_gate"])
        self.assertFalse(independently_read["reset_checks"]["1"]["complete_dof_inventory"])
        final, failed_dir = self._run_worker("receipt-write", "--synthetic-fault", "final-receipt-write")
        self.assertEqual(final.returncode, 2)
        self.assertFalse((failed_dir / "native_result.json").exists())
        self.assertIn("FINAL_RECEIPT_WRITE_FAILED", final.stdout)

    def test_existing_outputs_are_never_replaced(self) -> None:
        first, run_dir = self._run_worker("exists")
        self.assertEqual(first.returncode, 0)
        second = subprocess.run(
            [str(PYTHON), "-B", "-m", WORKER_MODULE, "--synthetic-s1-worker", "--run-dir", str(run_dir)],
            cwd=REPO, env=_env(), text=True, capture_output=True, timeout=120, check=False,
        )
        self.assertEqual(second.returncode, 2)
        self.assertIn("existing_output_refused", second.stdout)

    def test_numpy_scalar_and_array_strict_conversion(self) -> None:
        try:
            import numpy as np
        except ImportError:
            self.skipTest("installed target runtime does not expose numpy")
        warnings: list[dict[str, str]] = []
        value = worker._strict_json_value({"scalar": np.float32(1.25), "array": np.asarray([1.0, np.nan])}, warnings)
        self.assertEqual(value["scalar"], 1.25)
        self.assertEqual(value["array"][0], 1.0)
        self.assertEqual(value["array"][1], {"non_finite": "nan"})
        self.assertEqual(len(warnings), 1)

    def test_check_is_metadata_only_and_source_has_no_provider_import(self) -> None:
        checked = subprocess.run(
            [str(ISAAC_PYTHON), "-B", str(WORKER_SCRIPT), "--check"],
            cwd=REPO, env=_env(), text=True, capture_output=True, timeout=120, check=False,
        )
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        payload = json.loads(checked.stdout)
        self.assertTrue(payload["expected_packages_match"])
        self.assertEqual(payload["forbidden_imports_loaded"], [])
        tree = ast.parse(Path(reader.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & {"isaacsim", "omni", "pxr", "mujoco", "f01_isaac_native_baseline"})


class F01SupervisorMonitorTests(unittest.TestCase):
    def test_resource_abort_requires_three_consecutive_violations(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f01-resource-monitor-") as temp:
            log = Path(temp) / "child.log"
            with log.open("wb") as stream:
                started = time.monotonic()
                proc = subprocess.Popen([str(PYTHON), "-B", "-c", "import time; time.sleep(30)"],
                                        stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                low_ram = {"mem_available_bytes": 1, "worker_group_rss_bytes": 0,
                           "gpu0_free_mib": 6000, "host_network_rx_bytes": 10}
                monitor = supervisor.monitor_process(proc, log, started=started, timeout_s=5,
                                                     interval_s=0.02, sample_fn=lambda _pid: low_ram,
                                                     network_baseline=10)
            self.assertEqual(monitor["stop_reason"], "system_available_ram_below_768_mib_three_samples")
            self.assertEqual(len(monitor["samples"]), 3)
            self.assertTrue(monitor["termination"]["term_sent"])

    def test_timeout_terminates_process_group_without_isaac(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f01-monitor-") as temp:
            log = Path(temp) / "child.log"
            with log.open("wb") as stream:
                started = time.monotonic()
                proc = subprocess.Popen([str(PYTHON), "-B", "-c", "import time; time.sleep(30)"],
                                        stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                measured = {"mem_available_bytes": 8 * 1024**3, "worker_group_rss_bytes": 0,
                            "gpu0_free_mib": 6000, "host_network_rx_bytes": 100}
                monitor = supervisor.monitor_process(proc, log, started=started, timeout_s=0.25,
                                                     interval_s=0.05, sample_fn=lambda _pid: measured,
                                                     network_baseline=100)
            self.assertEqual(monitor["stop_reason"], "process_wall_timeout")
            self.assertTrue(monitor["termination"]["term_sent"])
            self.assertNotEqual(monitor["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
