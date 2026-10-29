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
from unittest import mock

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


class F01PlanTests(unittest.TestCase):
    def test_plan_uses_a_non_deadlocking_native_thread_pool(self) -> None:
        plan = worker.default_plan()
        reader_plan = reader._expected_plan("thread-pool-plan-check")

        self.assertEqual(plan["application"]["limit_cpu_threads"], 16)
        self.assertFalse(plan["application"]["fast_shutdown"])
        self.assertEqual(reader_plan["application"]["limit_cpu_threads"], 16)
        self.assertEqual(plan, {key: value for key, value in reader_plan.items() if key != "run_id"})

    def test_native_plan_targets_gpu_physx(self) -> None:
        plan = worker.default_plan()
        self.assertEqual(plan["scene"]["physics_device"], "cuda:0")
        self.assertIs(plan["scene"]["gpu_dynamics"], True)
        self.assertEqual(reader._expected_plan("gpu-plan-check")["scene"], plan["scene"])

    def test_kit_viewport_cameras_are_not_misclassified_as_task_sensors(self) -> None:
        cameras = sorted(reader.KIT_VIEWPORT_CAMERAS)
        identity = {
            "stage_camera_prim_paths": cameras,
            "kit_viewport_camera_prim_paths": cameras,
            "task_camera_prim_paths": [],
        }
        self.assertTrue(reader._camera_inventory_has_no_task_cameras(identity))
        identity["stage_camera_prim_paths"] = cameras + ["/World/task_camera"]
        identity["task_camera_prim_paths"] = ["/World/task_camera"]
        self.assertFalse(reader._camera_inventory_has_no_task_cameras(identity))

    def test_reader_requires_supervisor_observed_worker_vram(self) -> None:
        worker_receipt = {"run_id": "gpu-run", "worker_pid": 42}
        parent = {
            "run_id": "gpu-run",
            "process_monitor": {
                "exit_code": 0, "stop_reason": None, "gpu_process_pid": 42,
                "max_sampled_gpu_process_memory_mib": 1200,
            },
        }
        self.assertTrue(reader._parent_proves_gpu_vram(parent, worker_receipt))
        parent["process_monitor"]["max_sampled_gpu_process_memory_mib"] = 0
        self.assertFalse(reader._parent_proves_gpu_vram(parent, worker_receipt))

    def test_supervisor_reads_vram_for_the_native_worker_pid(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["nvidia-smi"], returncode=0, stdout="41, 900\n42, 1350\n", stderr=""
        )
        with mock.patch.object(supervisor.subprocess, "run", return_value=completed):
            self.assertEqual(supervisor._gpu_process_memory_mib(42), 1350)
            self.assertIsNone(supervisor._gpu_process_memory_mib(99))

    def test_final_counters_are_captured_before_app_close_resets_them(self) -> None:
        class ResetCountersOnClose(worker.FakeDriver):
            def close(self) -> None:
                super().close()
                self._index = 0
                self._time = 0.0

        with tempfile.TemporaryDirectory(prefix="f01-counter-order-") as temp:
            run_dir = Path(temp)
            plan = worker.default_plan()
            plan["run_id"] = "counter-order"
            (run_dir / "run_plan.json").write_text(json.dumps(plan), encoding="utf-8")
            outcome = worker.run_worker(
                run_dir,
                plan,
                driver_factory=ResetCountersOnClose,
                evidence_kind="synthetic_fixture",
            )
        self.assertEqual(outcome["exit_code"], 0)
        report = outcome["report"]
        self.assertEqual(report["physics_steps_at_start"], 3)
        self.assertEqual(report["physics_steps_at_end"], 484)
        self.assertEqual(report["total_physics_steps"], 481)


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


class F01NativeExtensionOrderTests(unittest.TestCase):
    def test_python_module_import_follows_extension_enable_and_app_update(self) -> None:
        events: list[tuple[str, object]] = []

        class AppUtils:
            @staticmethod
            def enable_extension(name: str) -> bool:
                events.append(("enable", name))
                return True

            @staticmethod
            def update_app(*, steps: int) -> None:
                events.append(("update", steps))

        module = object()
        with mock.patch.object(
            worker.importlib,
            "import_module",
            side_effect=lambda name: events.append(("import", name)) or module,
        ):
            loaded = worker._enable_extension_and_import(
                AppUtils(),
                extension_name="isaacsim.robot_motion.examples",
                module_name="isaacsim.robot_motion.examples.manipulation",
            )

        self.assertIs(loaded, module)
        self.assertEqual(
            events,
            [
                ("enable", "isaacsim.robot_motion.examples"),
                ("update", 1),
                ("import", "isaacsim.robot_motion.examples.manipulation"),
            ],
        )

    def test_failed_extension_enable_does_not_attempt_python_import(self) -> None:
        events: list[tuple[str, object]] = []

        class AppUtils:
            @staticmethod
            def enable_extension(name: str) -> bool:
                events.append(("enable", name))
                return False

            @staticmethod
            def update_app(*, steps: int) -> None:
                events.append(("update", steps))

        with mock.patch.object(worker.importlib, "import_module") as import_module:
            with self.assertRaisesRegex(RuntimeError, "extension did not enable"):
                worker._enable_extension_and_import(
                    AppUtils(),
                    extension_name="isaacsim.robot_motion.examples",
                    module_name="isaacsim.robot_motion.examples.manipulation",
                )

        self.assertEqual(events, [("enable", "isaacsim.robot_motion.examples")])
        import_module.assert_not_called()


class F01NativeExitTests(unittest.TestCase):
    def test_native_worker_terminates_only_after_durable_result_exists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f01-native-exit-") as tmp:
            run_dir = Path(tmp)
            plan = worker.default_plan()
            plan["run_id"] = "native-exit"
            (run_dir / "run_plan.json").write_text(json.dumps(plan), encoding="utf-8")
            result_path = run_dir / worker.RESULT_NAME
            outcome = {
                "exit_code": 1,
                "report": {"status": "FAILED_WORKER"},
                "result_path": str(result_path),
                "trace_path": str(run_dir / worker.TRACE_NAME),
            }

            def fake_run_worker(*_args: object, **kwargs: object) -> dict[str, object]:
                self.assertEqual(kwargs["evidence_kind"], "real_native")
                worker._write_json_new(result_path, {"status": "FAILED_WORKER"})
                return outcome

            def fake_terminate(exit_code: int) -> None:
                self.assertEqual(exit_code, 1)
                self.assertEqual(json.loads(result_path.read_text())["status"], "FAILED_WORKER")

            with mock.patch.object(worker, "run_worker", side_effect=fake_run_worker), \
                 mock.patch.object(worker, "_terminate_native_worker", side_effect=fake_terminate) as terminate:
                result = worker.main(["--native-worker", "--run-dir", str(run_dir)])

            self.assertEqual(result, 1)
            terminate.assert_called_once_with(1)


class F01SupervisorMonitorTests(unittest.TestCase):
    def test_eula_block_is_retry_eligible_only_before_physics(self) -> None:
        start = {
            "failure_category": None,
            "stop_reason": None,
            "resource_abort": False,
            "timed_out": False,
            "worker_receipt": {
                "total_physics_steps": 0,
                "physics_steps_at_start": None,
                "bootstrap": [],
                "worker_error": {
                    "type": "SystemExit",
                    "stage": "app_start",
                    "message": "Unable to bootstrap inner kit kernel: EULA not accepted. Set OMNI_KIT_ACCEPT_EULA=YES to accept.",
                },
            },
        }
        self.assertTrue(supervisor._ordinary_prestep_wiring_failure(start))
        start["worker_receipt"]["total_physics_steps"] = 1
        self.assertFalse(supervisor._ordinary_prestep_wiring_failure(start))
        start["worker_receipt"]["total_physics_steps"] = 0
        start["worker_receipt"]["worker_error"]["message"] = "other SystemExit"
        self.assertFalse(supervisor._ordinary_prestep_wiring_failure(start))

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
