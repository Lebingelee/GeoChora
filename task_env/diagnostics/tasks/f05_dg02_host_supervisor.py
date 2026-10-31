"""Run a bounded, resource-sampled DG02 static provider child process."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


_PAGE_BYTES = os.sysconf("SC_PAGE_SIZE")


def _mem_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable is unavailable")


def _process_table() -> dict[int, tuple[int, int]]:
    table = {}
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        try:
            stat = (item / "stat").read_text()
            end = stat.rfind(")")
            fields = stat[end + 2 :].split()
            ppid = int(fields[1])
            rss_pages = int((item / "statm").read_text().split()[1])
            table[int(item.name)] = (ppid, rss_pages * _PAGE_BYTES)
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
            continue
    return table


def _group_rss(root_pid: int) -> tuple[int, list[int]]:
    table = _process_table()
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _rss) in table.items():
            if ppid in selected and pid not in selected:
                selected.add(pid)
                changed = True
    return sum(table[pid][1] for pid in selected if pid in table), sorted(selected)


def run(*, python: Path, audit: Path, stage: Path, plan: Path, plan_sha256: Path,
        receipt: Path, output_root: Path) -> dict:
    mem_before = _mem_available()
    minimum = 4 * 1024**3
    if mem_before < minimum:
        raise RuntimeError(f"host static child preflight requires {minimum} bytes MemAvailable; saw {mem_before}")
    output_root.mkdir(parents=True, exist_ok=True)
    stdout_path = output_root / "stdout.txt"
    stderr_path = output_root / "stderr.txt"
    command = [
        str(python), str(audit), str(stage), "--plan", str(plan),
        "--plan-sha256", str(plan_sha256), "--receipt", str(receipt),
    ]
    env = dict(os.environ)
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "CUDA_VISIBLE_DEVICES": "",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    })
    env.pop("GEOPHYS_TAICHI_BACKEND", None)
    env.pop("GEOPHYS_TAICHI_ARCH", None)
    started = time.monotonic()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env, start_new_session=True)
        max_rss = 0
        max_pids = [process.pid]
        reason = None
        while process.poll() is None:
            rss, pids = _group_rss(process.pid)
            max_rss = max(max_rss, rss)
            if rss > 3 * 1024**3:
                reason = "provider free child process group RSS exceeded 3 GiB"
            elif time.monotonic() - started > 600:
                reason = "provider free child exceeded 600 seconds"
            if reason:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                break
            max_pids = pids if len(pids) > len(max_pids) else max_pids
            time.sleep(0.25)
        exit_code = process.wait()
    duration = time.monotonic() - started
    result = {
        "schema_version": "f05-dg02-host-supervisor-receipt-v1",
        "command": command,
        "exit_code": exit_code,
        "abort_reason": reason,
        "wall_seconds": duration,
        "sample_interval_seconds": 0.25,
        "max_sampled_process_group_rss_bytes": max_rss,
        "observed_process_ids": max_pids,
        "mem_available_start_bytes": mem_before,
        "mem_available_end_bytes": _mem_available(),
        "native_starts": 0,
        "physics_steps": 0,
        "native_lock_owned": False,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    (output_root / "supervisor_receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    if exit_code != 0 or reason is not None:
        raise RuntimeError(f"bounded host audit failed: exit={exit_code}, reason={reason}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = run(**vars(args))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
