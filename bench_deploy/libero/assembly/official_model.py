"""Capture a source model from the pinned upstream LIBERO model builder."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from bench_deploy.libero.artifacts.contracts import (
    LIBERO_REVISION, ROBOSUITE_REVISION, TASK_1, TASK_2, TASK_3,
    task_source_contract_v1,
)


_CONTROL_OPTIONS = {
    "robots": ["Panda"], "controller": "OSC_POSE", "gripper_types": "default",
    "use_camera_obs": False, "has_renderer": False,
    "has_offscreen_renderer": False, "control_freq": 20, "horizon": 1000,
    "ignore_done": True, "hard_reset": True, "camera_names": [],
}
_TASKS = {"task1": TASK_1, "task2": TASK_2, "task3": TASK_3}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _revision(root: Path, expected: str) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"upstream source root must be an existing directory: {root}")
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    if result.stdout.strip() != expected:
        raise ValueError(f"upstream source revision differs at {root}")


def _control_env(libero_root: Path, robosuite_root: Path, bddl_path: Path):
    for root in (robosuite_root, libero_root):
        value = str(root)
        if value in sys.path:
            sys.path.remove(value)
        sys.path.insert(0, value)
    module = importlib.import_module("libero.libero.envs.env_wrapper")
    module_path = Path(module.__file__).resolve(strict=True)
    if not module_path.is_relative_to(libero_root):
        raise ValueError("LIBERO ControlEnv resolved outside the pinned source tree")
    robosuite = importlib.import_module("robosuite")
    if not Path(robosuite.__file__).resolve(strict=True).is_relative_to(robosuite_root):
        raise ValueError("robosuite resolved outside the pinned source tree")
    return module.ControlEnv(bddl_file_name=str(bddl_path), **_CONTROL_OPTIONS)


def _capture(env, *, task_uid: str, seed: int, source_closure_sha256: str) -> tuple[bytes, dict]:
    error = None
    result = None
    try:
        env.seed(seed)
        env.reset()
        model = getattr(getattr(env, "env", None), "model", None)
        get_xml = getattr(model, "get_xml", None)
        if not callable(get_xml):
            raise TypeError("official LIBERO model has no get_xml() method")
        value = get_xml()
        xml = value.encode("utf-8") if isinstance(value, str) else value
        if type(xml) is not bytes:
            raise TypeError("official model get_xml() must return UTF-8 text or bytes")
        root = ET.fromstring(xml)
        if root.tag != "mujoco":
            raise ValueError("official model output is not a MuJoCo XML document")
        cameras = [node.get("name") for node in root.iter("camera") if node.get("name")]
        result = {
            "schema_version": "libero-official-model-capture-v1",
            "identity": {
                "source_model_id": "libero-official-model-builder-v1",
                "task_uid": task_uid,
                "libero_revision": LIBERO_REVISION,
                "robosuite_revision": ROBOSUITE_REVISION,
                "seed": seed,
                "source_closure_sha256": source_closure_sha256,
            },
            "builder_options": dict(_CONTROL_OPTIONS),
            "camera_names_in_model": cameras,
            "output": {
                "status": "SOURCE_MJCF_CAPTURED_NOT_NATIVE_COMPILED",
                "model_xml_bytes": len(xml),
                "model_xml_sha256": _sha(xml),
            },
            "close": {"status": "PENDING"},
        }
    except BaseException as exc:
        error = exc
    try:
        env.close()
        if result is not None:
            result["close"] = {"status": "CLOSED"}
    except BaseException as close_error:
        if error is None:
            error = close_error
        elif hasattr(error, "add_note"):
            error.add_note(f"official model environment close failed: {close_error!r}")
    if error is not None:
        raise error
    assert result is not None
    return xml, result


def build_official_model_capture(
    task_uid: str, *, libero_root: Path, robosuite_root: Path,
    output_dir: Path, source_closure_sha256: str, seed: int = 19,
) -> dict:
    """Run upstream ControlEnv once and save its exact source XML and receipt."""
    contract = task_source_contract_v1(task_uid)
    if seed != 19:
        raise ValueError("the current LIBERO source model capture is pinned to seed 19")
    if (type(source_closure_sha256) is not str or len(source_closure_sha256) != 64
            or any(char not in "0123456789abcdef" for char in source_closure_sha256)):
        raise ValueError("source closure identity must be a lowercase SHA-256")
    libero_root = Path(libero_root).expanduser()
    robosuite_root = Path(robosuite_root).expanduser()
    if libero_root.is_symlink() or robosuite_root.is_symlink():
        raise ValueError("upstream source roots must not be symlinks")
    libero_root = libero_root.resolve(strict=True)
    robosuite_root = robosuite_root.resolve(strict=True)
    _revision(libero_root, LIBERO_REVISION)
    _revision(robosuite_root, ROBOSUITE_REVISION)
    bddl_path = libero_root / contract.bddl_path
    if bddl_path.is_symlink() or _sha(bddl_path.read_bytes()) != contract.bddl_sha256:
        raise ValueError("task BDDL bytes differ from the pinned source contract")

    output = Path(output_dir)
    if output.is_symlink() or output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("official model output must be a new or empty directory")
    env = _control_env(libero_root, robosuite_root, bddl_path)
    xml, receipt = _capture(
        env, task_uid=task_uid, seed=seed,
        source_closure_sha256=source_closure_sha256,
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "official_model.xml").write_bytes(xml)
    (output / "official_model_capture.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=["task1", "task2", "task3"], required=True)
    parser.add_argument("--libero-source-root", type=Path, required=True)
    parser.add_argument("--robosuite-source-root", type=Path, required=True)
    parser.add_argument("--source-closure-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = build_official_model_capture(
        _TASKS[args.task], libero_root=args.libero_source_root,
        robosuite_root=args.robosuite_source_root, output_dir=args.output,
        source_closure_sha256=args.source_closure_sha256,
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
