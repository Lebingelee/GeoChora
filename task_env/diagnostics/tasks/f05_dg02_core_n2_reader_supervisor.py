"""Bound the independent DG02 N2 H5 reader as a host-only child process."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


CORE = Path(__file__).resolve().parents[3]
MAINT = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001"
WINDOW = MAINT / "f05_diagnostic_goal02/window_001"
LOCK = MAINT / "shared_native_execution.lock"
PAGE_BYTES = os.sysconf("SC_PAGE_SIZE")
CLK_TCK = os.sysconf("SC_CLK_TCK")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _mem_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable is unavailable")


def _process_group_sample(pgid: int) -> tuple[int, list[int], float]:
    rss_total = 0
    pids: list[int] = []
    cpu_seconds = 0.0
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        try:
            stat = (item / "stat").read_text()
            fields = stat[stat.rfind(")") + 2 :].split()
            if int(fields[2]) != pgid:
                continue
            rss = int((item / "statm").read_text().split()[1]) * PAGE_BYTES
            ticks = int(fields[11]) + int(fields[12])
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
            continue
        pids.append(int(item.name))
        rss_total += rss
        cpu_seconds += ticks / CLK_TCK
    return rss_total, sorted(pids), cpu_seconds


def _lock_available(path: Path = LOCK) -> bool:
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return True


def _file_identity(path: Path) -> dict[str, str]:
    resolved = path.resolve(strict=True)
    return {"path": str(resolved), "sha256": _sha(resolved)}


def _tracked_plan_inputs(plan: dict) -> list[dict[str, str]]:
    rows = list(plan["code"]["tracked_inputs"])
    rows.extend([
        {"path": path, "sha256": digest}
        for path, digest in plan["runtime"]["file_sha256"].items()
    ])
    return rows


def _git_blob_sha(input_head: str, path: Path) -> str:
    relative = path.resolve(strict=True).relative_to(CORE)
    result = subprocess.run(
        ["git", "-C", str(CORE), "show", f"{input_head}:{relative.as_posix()}"],
        check=True, capture_output=True,
    )
    return hashlib.sha256(result.stdout).hexdigest()


def _frozen_reader_source_identity(formal: dict, reader_script: Path) -> dict[str, str]:
    reader_script = reader_script.resolve(strict=True)
    rows = [
        row for row in formal["code"]["tracked_inputs"]
        if Path(row["path"]).resolve(strict=True) == reader_script
    ]
    input_head = formal.get("input_identity", {}).get("core_input_head")
    if len(rows) != 1 or not isinstance(input_head, str):
        raise ValueError("formal plan must contain one frozen cold-reader source identity")
    row = rows[0]
    blob_sha = _git_blob_sha(input_head, reader_script)
    if blob_sha != row["sha256"]:
        raise ValueError("formal cold-reader source identity differs from its input Core HEAD")
    return {
        "path": str(reader_script),
        "sha256": blob_sha,
        "input_head": input_head,
        "verification": "git_blob_at_formal_core_head",
    }


def _reader_plan_input_identities(formal: dict, reader_script: Path) -> list[dict[str, str]]:
    reader_path = reader_script.resolve(strict=True)
    return [
        row for row in _tracked_plan_inputs(formal)
        if Path(row["path"]).resolve(strict=True) != reader_path
    ]


def _verify_frozen_reader_source_identity(formal: dict, identity: dict) -> None:
    reader_script = CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_cold_reader.py"
    expected = _frozen_reader_source_identity(formal, reader_script)
    if identity != expected:
        raise ValueError("reader supervision plan changed the producer's frozen reader identity")


def _verify_identities(rows: list[dict[str, str]]) -> None:
    for row in rows:
        path = Path(row["path"]).resolve(strict=True)
        if _sha(path) != row["sha256"]:
            raise ValueError(f"cold-reader supervised input hash differs: {path}")


def _classify_reader_result(exit_code: int, reader: dict | None) -> str:
    if reader is None:
        return "FAIL_READER_RECEIPT_MISSING"
    status = reader.get("status")
    codes = {item.get("code") for item in reader.get("failure_reasons", [])}
    if exit_code == 0 and status == "PASS_N2_COLD_READ_AND_22_NEGATIVES":
        return "PASS_N2_COLD_READ_AND_22_NEGATIVES"
    if exit_code == 1 and status == "FAIL_N2_COLD_READ" and codes == {"task_predicate"}:
        return "COMPLETED_WITH_TRACKING_GATE_FAILURE"
    return "FAIL_UNEXPECTED_READER_EXIT_OR_RECEIPT"


def build_plan(*, formal_plan_path: Path, formal_sidecar_path: Path,
               supervisor_path: Path, worker_path: Path,
               reader_receipt_path: Path, output_root: Path) -> dict:
    formal_plan_path = formal_plan_path.resolve(strict=True)
    formal_sidecar_path = formal_sidecar_path.resolve(strict=True)
    formal_plan_bytes = formal_plan_path.read_bytes()
    formal_plan_sha = hashlib.sha256(formal_plan_bytes).hexdigest()
    if formal_sidecar_path.read_text(encoding="ascii").split()[0] != formal_plan_sha:
        raise ValueError("formal N2 plan SHA-256 mismatch")
    formal = json.loads(formal_plan_bytes)
    if formal.get("schema_version") != "f05-dg02-core-n2-plan-v1":
        raise ValueError("unsupported formal N2 plan")
    reader_script = CORE / "task_env/diagnostics/tasks/f05_dg02_core_n2_cold_reader.py"
    producer_reader_identity = _frozen_reader_source_identity(formal, reader_script)
    input_identities = _reader_plan_input_identities(formal, reader_script)
    _verify_identities(input_identities)

    supervisor_path = supervisor_path.resolve(strict=True)
    worker_path = worker_path.resolve(strict=True)
    parent = _json(supervisor_path)
    worker = _json(worker_path)
    if (parent.get("run_id") != formal.get("run_id")
            or worker.get("run_id") != formal.get("run_id")
            or parent.get("plan_sha256") != formal_plan_sha
            or worker.get("plan_sha256") != formal_plan_sha
            or parent.get("worker_receipt_sha256") != _sha(worker_path)):
        raise ValueError("formal N2 parent/worker receipts are not bound to this plan")
    h5_paths = [Path(item).resolve(strict=True) for item in formal["output"]["episode_h5_paths"]]
    h5_rows = [_file_identity(path) for path in h5_paths]

    output_root = output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"cold-reader supervision output is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    receipt_path = reader_receipt_path.resolve()
    python = Path(formal["runtime"]["python"]).resolve(strict=True)
    runtime_pythonpath = [str(CORE), *formal["runtime"]["pythonpath"]]
    command = [
        str(python), str(reader_script),
        "--plan", str(formal_plan_path),
        "--plan-sha256", str(formal_sidecar_path),
        "--supervisor", str(supervisor_path),
        "--worker", str(worker_path),
        "--receipt", str(receipt_path),
    ]
    plan = {
        "schema_version": "f05-dg02-core-n2-reader-supervision-plan-v1",
        "run_id": formal["run_id"],
        "supervision_id": f"{formal['run_id']}_COLD_READ_G7_001",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "formal_plan": _file_identity(formal_plan_path),
        "formal_plan_sidecar": _file_identity(formal_sidecar_path),
        "formal_supervisor": _file_identity(supervisor_path),
        "formal_worker": _file_identity(worker_path),
        "supervisor_script": _file_identity(Path(__file__)),
        "h5_files": h5_rows,
        "producer_reader_source_identity": producer_reader_identity,
        "reader": {
            "python": str(python),
            "python_sha256": _sha(python),
            "script": _file_identity(reader_script),
            "pythonpath": runtime_pythonpath,
            "working_directory": str(CORE),
            "command": command,
            "receipt_path": str(receipt_path),
            "environment": {
                "PYTHONDONTWRITEBYTECODE": "1",
                "CUDA_VISIBLE_DEVICES": "",
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            },
        },
        "limits": {
            "minimum_mem_available_bytes": 4 * 1024**3,
            "abort_mem_available_bytes_below": 1 * 1024**3,
            "process_group_rss_bytes_max": 3 * 1024**3,
            "wall_seconds_max": 600,
            "sample_interval_seconds": 0.25,
            "term_grace_seconds": 5,
            "cpu_threads_max": 1,
            "native_starts": 0,
            "physics_steps": 0,
            "shared_native_lock_path": str(LOCK),
        },
        "input_identities": input_identities,
        "output_root": str(output_root),
        "formal_plan_hash": formal_plan_sha,
    }
    plan_path = output_root / "reader_supervision_plan.json"
    plan_sidecar = output_root / "reader_supervision_plan.sha256"
    _atomic_json(plan_path, plan)
    digest = _sha(plan_path)
    plan_sidecar.write_text(f"{digest}  {plan_path.name}\n", encoding="ascii")
    with plan_sidecar.open("rb") as stream:
        os.fsync(stream.fileno())
    return plan


def run(plan_path: Path, sidecar_path: Path) -> dict:
    plan_path = plan_path.resolve(strict=True)
    sidecar_path = sidecar_path.resolve(strict=True)
    plan_hash = _sha(plan_path)
    if sidecar_path.read_text(encoding="ascii").split()[0] != plan_hash:
        raise ValueError("cold-reader supervision plan SHA-256 mismatch")
    plan = _json(plan_path)
    if plan.get("schema_version") != "f05-dg02-core-n2-reader-supervision-plan-v1":
        raise ValueError("unsupported cold-reader supervision plan")
    _verify_identities(plan["input_identities"])
    for label in ("formal_plan", "formal_plan_sidecar", "formal_supervisor", "formal_worker"):
        row = plan[label]
        if _sha(Path(row["path"]).resolve(strict=True)) != row["sha256"]:
            raise ValueError(f"cold-reader supervision {label} identity changed")
    formal = _json(Path(plan["formal_plan"]["path"]).resolve(strict=True))
    _verify_frozen_reader_source_identity(
        formal, plan.get("producer_reader_source_identity", {}),
    )
    supervisor_script = plan["supervisor_script"]
    if _sha(Path(supervisor_script["path"]).resolve(strict=True)) != supervisor_script["sha256"]:
        raise ValueError("cold-reader supervisor implementation changed after plan freeze")
    for row in plan["h5_files"]:
        if _sha(Path(row["path"]).resolve(strict=True)) != row["sha256"]:
            raise ValueError(f"cold-reader supervised H5 identity changed: {row['path']}")
    if _sha(Path(plan["reader"]["script"]["path"])) != plan["reader"]["script"]["sha256"]:
        raise ValueError("cold-reader implementation changed after plan freeze")
    python = Path(plan["reader"]["python"]).resolve(strict=True)
    if _sha(python) != plan["reader"]["python_sha256"]:
        raise ValueError("cold-reader Python executable changed after plan freeze")
    if not _lock_available(Path(plan["limits"]["shared_native_lock_path"])):
        raise RuntimeError("shared native lock is busy before cold-reader start")
    mem_start = _mem_available()
    limits = plan["limits"]
    if mem_start < int(limits["minimum_mem_available_bytes"]):
        raise RuntimeError("MemAvailable is below the frozen cold-reader host start gate")
    output_root = Path(plan["output_root"])
    root_receipt = output_root / "reader_supervisor_receipt.json"
    if root_receipt.exists():
        raise FileExistsError(root_receipt)
    stdout_path, stderr_path = output_root / "stdout.txt", output_root / "stderr.txt"
    env = dict(os.environ)
    env.update(plan["reader"]["environment"])
    env["PYTHONPATH"] = os.pathsep.join(plan["reader"]["pythonpath"])
    env.pop("GEOPHYS_TAICHI_BACKEND", None)
    env.pop("GEOPHYS_TAICHI_ARCH", None)
    command = list(plan["reader"]["command"])
    started = time.monotonic()
    max_rss, max_cpu, max_pids = 0, 0.0, []
    abort_reason = None
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command, cwd=plan["reader"]["working_directory"],
            env=env, stdout=stdout, stderr=stderr, start_new_session=True,
        )
        pgid = process.pid
        while process.poll() is None:
            rss, pids, cpu_seconds = _process_group_sample(pgid)
            max_rss = max(max_rss, rss)
            max_cpu = max(max_cpu, cpu_seconds)
            max_pids = pids if len(pids) >= len(max_pids) else max_pids
            elapsed = time.monotonic() - started
            mem_now = _mem_available()
            if rss > int(limits["process_group_rss_bytes_max"]):
                abort_reason = "cold-reader process-group RSS exceeded frozen maximum"
            elif mem_now < int(limits["abort_mem_available_bytes_below"]):
                abort_reason = "MemAvailable fell below emergency abort threshold"
            elif elapsed > int(limits["wall_seconds_max"]):
                abort_reason = "cold-reader exceeded frozen wall limit"
            if abort_reason:
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=float(limits["term_grace_seconds"]))
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                break
            time.sleep(float(limits["sample_interval_seconds"]))
        worker_exit = process.wait()
    end_rss, remaining_pids, end_cpu = _process_group_sample(pgid)
    max_rss = max(max_rss, end_rss)
    max_cpu = max(max_cpu, end_cpu)
    if remaining_pids:
        terminate_started = time.monotonic()
        while remaining_pids and time.monotonic() - terminate_started <= float(limits["term_grace_seconds"]):
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            time.sleep(0.1)
            _rss, remaining_pids, _cpu = _process_group_sample(pgid)
        if remaining_pids:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            for _ in range(50):
                time.sleep(0.1)
                _rss, remaining_pids, _cpu = _process_group_sample(pgid)
                if not remaining_pids:
                    break
    reader_receipt_path = Path(plan["reader"]["receipt_path"])
    reader_receipt = _json(reader_receipt_path) if reader_receipt_path.is_file() else None
    classified = _classify_reader_result(worker_exit, reader_receipt)
    stdout_bytes, stderr_bytes = stdout_path.stat().st_size, stderr_path.stat().st_size
    lock_available_after = _lock_available(Path(limits["shared_native_lock_path"]))
    duration = time.monotonic() - started
    supervisor_status = (
        "PASS_HOST_SUPERVISED_READER_COMPLETED"
        if not abort_reason and not remaining_pids and lock_available_after
        and classified in {"PASS_N2_COLD_READ_AND_22_NEGATIVES", "COMPLETED_WITH_TRACKING_GATE_FAILURE"}
        else "FAIL_HOST_SUPERVISED_READER"
    )
    receipt = {
        "schema_version": "f05-dg02-core-n2-reader-supervisor-receipt-v1",
        "supervision_id": plan["supervision_id"],
        "run_id": plan["run_id"],
        "supervision_plan_path": str(plan_path),
        "supervision_plan_sha256": plan_hash,
        "formal_plan_sha256": plan["formal_plan_hash"],
        "reader_command": command,
        "reader_worker_exit_code": worker_exit,
        "reader_result": classified,
        "reader_receipt_path": str(reader_receipt_path),
        "reader_receipt_sha256": _sha(reader_receipt_path) if reader_receipt_path.is_file() else None,
        "exit_code": 0 if supervisor_status == "PASS_HOST_SUPERVISED_READER_COMPLETED" else 1,
        "abort_reason": abort_reason,
        "status": supervisor_status,
        "wall_seconds": duration,
        "sample_interval_seconds": float(limits["sample_interval_seconds"]),
        "max_sampled_process_group_rss_bytes": max_rss,
        "max_sampled_process_group_cpu_seconds": max_cpu,
        "max_sampled_process_group_child_count": len(max_pids),
        "max_sampled_process_group_pids": max_pids,
        "remaining_process_group_pids": remaining_pids,
        "mem_available_start_bytes": mem_start,
        "mem_available_end_bytes": _mem_available(),
        "shared_native_lock_available_before": True,
        "shared_native_lock_available_after": lock_available_after,
        "native_starts": 0,
        "physics_steps": 0,
        "stdout_path": str(stdout_path),
        "stdout_bytes": stdout_bytes,
        "stderr_path": str(stderr_path),
        "stderr_bytes": stderr_bytes,
        "input_identities": plan["input_identities"],
        "h5_identities": plan["h5_files"],
    }
    _atomic_json(root_receipt, receipt)
    if supervisor_status != "PASS_HOST_SUPERVISED_READER_COMPLETED":
        raise RuntimeError(f"cold-reader host supervision failed: {supervisor_status}; {abort_reason}")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-plan", type=Path, required=True)
    parser.add_argument("--formal-sidecar", type=Path, required=True)
    parser.add_argument("--formal-supervisor", type=Path, required=True)
    parser.add_argument("--formal-worker", type=Path, required=True)
    parser.add_argument("--reader-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    args = parser.parse_args()
    expected_plan = Path(args.output_root).resolve() / "reader_supervision_plan.json"
    if not expected_plan.exists():
        build_plan(
            formal_plan_path=args.formal_plan,
            formal_sidecar_path=args.formal_sidecar,
            supervisor_path=args.formal_supervisor,
            worker_path=args.formal_worker,
            reader_receipt_path=args.reader_receipt,
            output_root=args.output_root,
        )
    result = run(args.plan, args.plan_sha256)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
