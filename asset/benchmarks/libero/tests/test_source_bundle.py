"""Provider-free S1 for the real R07b source/install/recipe CLI."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
CLI = REPO / "asset/benchmarks/libero/tools/source_bundle.py"
PYTHON = Path("/home/lly/miniconda3/envs/geochora/bin/python")


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["NUMEXPR_NUM_THREADS"] = "1"
    return env


def _path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("missing R07b test environment value " + name)
    return Path(value)


def _roots() -> dict[str, str]:
    return json.loads(_path("R07B_SOURCE_ROOTS").read_text(encoding="utf-8"))


def _base_manifest() -> dict:
    return json.loads(_path("R07B_MANIFEST").read_text(encoding="utf-8"))


def _record(case: str, proc: subprocess.CompletedProcess, expected: str | None = None, expect_success: bool = False) -> None:
    log = _path("R07B_S1_NEGATIVE_LOG")
    row = {
        "case": case,
        "exit_code": proc.returncode,
        "expected_diagnostic": expected,
        "stdout": proc.stdout[-1200:],
        "stderr": proc.stderr[-1200:],
        "passed": proc.returncode == 0 if expect_success else proc.returncode != 0 and (expected is None or expected in proc.stderr),
    }
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")


def _cli(args: list[str], *, case: str, expected: str | None = None, expect_success: bool = False, timeout: int = 180) -> subprocess.CompletedProcess:
    proc = subprocess.run([str(PYTHON), str(CLI), *args], cwd=REPO, env=_env(),
                          text=True, capture_output=True, timeout=timeout, check=False)
    _record(case, proc, expected, expect_success)
    return proc


def _write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def _install_args(manifest_path: Path, target: Path) -> list[str]:
    args = ["install", "--manifest", str(manifest_path), "--target", str(target)]
    for key, value in _roots().items():
        args.extend(["--source-root", f"{key}={value}"])
    return args


def _refresh_asset_closure(manifest: dict) -> None:
    files = [row for row in manifest["files"] if row["role"] == "asset_dependency"]
    closure_files = [
        {"repository": row["repository"], "path": row["source_path"],
         "size_bytes": row["size_bytes"], "sha256": row["sha256"]}
        for row in sorted(files, key=lambda item: (item["repository"], item["source_path"]))
    ]
    raw = json.dumps({"schema_version": "libero-pilot-asset-closure-v1", "files": closure_files},
                     sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    manifest["asset_closure"].update({
        "files": closure_files,
        "file_count": len(closure_files),
        "total_bytes": sum(row["size_bytes"] for row in closure_files),
        "sha256": hashlib.sha256(raw).hexdigest(),
    })


def _verify_manifest_variant(tmp_path: Path, mutate, expected: str, label: str) -> None:
    manifest = _base_manifest()
    mutate(manifest)
    variant = _write_json(tmp_path / f"{label}.json", manifest)
    proc = _cli(["verify", "--manifest", str(variant), "--target", str(_path("R07B_INSTALL_A")),
                 "--receipt-out", str(tmp_path / f"{label}.receipt.json")], case=label, expected=expected)
    assert proc.returncode != 0
    assert expected in proc.stderr


@pytest.mark.parametrize(
    "label,mutate,expected",
    [
        ("manifest_schema", lambda m: m.update(schema_version="wrong"), "unsupported source manifest schema"),
        ("manifest_task", lambda m: m["task"].update(task_uid="other/task"), "manifest task UID"),
        ("manifest_revision", lambda m: m["source_revisions"].update(libero="0" * 40), "source repository revisions"),
        ("manifest_duplicate_path", lambda m: m["files"][1].update(install_path=m["files"][0]["install_path"]), "duplicate manifest install path"),
        ("manifest_duplicate_id", lambda m: m["files"][1].update(entry_id=m["files"][0]["entry_id"]), "duplicate manifest entry id"),
        ("manifest_traversal", lambda m: m["files"][0].update(install_path="../outside"), "unsafe or noncanonical"),
        ("manifest_absolute_source", lambda m: m["files"][0].update(source_path="/outside"), "unsafe or noncanonical"),
        ("manifest_bad_digest", lambda m: m["files"][0].update(sha256="xyz"), "manifest SHA-256 is malformed"),
        ("manifest_wrong_file_pin", lambda m: m["files"][0].update(revision="0" * 40), "unexpected repository or revision"),
        ("manifest_missing_notice", lambda m: m["notices"].remove(next(n for n in m["notices"] if n["notice_id"].startswith("family-review-"))), "undeclared notice"),
        ("manifest_unapproved_family", lambda m: next(x for x in m["files"] if x["role"] == "asset_dependency")["license"].update(pilot_source_family="TurboSquid"), "outside the pilot allowlist"),
        ("manifest_redistribution", lambda m: next(x for x in m["files"] if x["role"] == "asset_dependency")["license"].update(redistribution_approved=True), "must not claim redistribution approval"),
        ("manifest_blocked_family_disposition", lambda m: next(x for x in m["files"] if x["role"] == "asset_dependency")["license"].update(first_use_disposition="BLOCKED_TURBOSQUID"), "eligible exact first-use family disposition"),
        ("manifest_wrong_family_notice", lambda m: next(x for x in m["files"] if x["role"] == "asset_dependency")["license"].update(pilot_family_id="different-family"), "family notice does not bind"),
        ("manifest_init_identity", lambda m: m["task"]["selected_pruned_init"].update(sha256="0" * 64), "exact selected .pruned_init identity is missing"),
        ("manifest_closure_hash", lambda m: m["asset_closure"].update(sha256="0" * 64), "asset closure listing, count, bytes, or digest"),
        ("manifest_closure_row", lambda m: m["asset_closure"]["files"].pop(), "asset closure listing, count, bytes, or digest"),
    ],
)
def test_manifest_boundary_rejections(tmp_path: Path, label, mutate, expected):
    _verify_manifest_variant(tmp_path, mutate, expected, label)


@pytest.mark.parametrize(
    "label,mutate,expected",
    [
        ("task_input_schema", lambda x: x.update(schema_version="wrong"), "unsupported deployment task input schema"),
        ("task_input_task_uid", lambda x: x.update(task_uid="other/task"), "different task UID"),
        ("task_input_manifest_hash", lambda x: x.update(source_manifest_sha256="0" * 64), "source manifest hash differs"),
        ("task_input_bddl", lambda x: x["bddl"].update(sha256="0" * 64), "BDDL identity/goal differs"),
        ("task_input_init", lambda x: x["selected_pruned_init"].update(sha256="0" * 64), "init identity differs"),
        ("task_input_revision", lambda x: x["source_revisions"].update(libero="0" * 40), "source pins"),
        ("task_input_actuator_type", lambda x: x["native_reference"]["robot"].update(arm_actuator_types=["position"] * 7), "authentic MountedPanda actuator types"),
        ("task_input_arm_order", lambda x: x["native_reference"]["robot"].update(arm_joint_names=list(reversed(x["native_reference"]["robot"]["arm_joint_names"]))), "arm slot order"),
        ("task_input_slot_range", lambda x: x["native_reference"]["robot"]["actuators"][7].update(control_range_m=[-0.04, 0.0]), "ordered actuator slot/type/range"),
        ("task_input_frame", lambda x: x["native_reference"]["robot"]["frames"].update(core_frame_reference_status="MAPPED"), "Core robot frame mapping"),
        ("task_input_native_clock", lambda x: x["native_reference"]["controller"].update(control_frequency_hz=100), "pinned native reference frequency"),
        ("task_input_native_physics_dt", lambda x: x["native_reference"]["controller"].update(physics_timestep_seconds=0.002), "uncompiled native physics clock"),
        ("task_input_drive", lambda x: x["requested_core_candidate"].update(drive_or_hold_semantics="equivalent to OSC_POSE"), "falsely supplies a drive or frame mapping"),
        ("task_input_candidate_clock", lambda x: x["requested_core_candidate"].update(control_period_seconds=0.05), "Core candidate clock"),
        ("task_input_camera_profile", lambda x: x["requested_core_candidate"].update(observation_profile="rgbd"), "must remain state-only"),
        ("task_input_false_admission", lambda x: x["requested_core_candidate"].update(core_native_admission_ready=True), "cannot claim Core native admission"),
        ("task_input_contact_false", lambda x: x["semantics"].update(contact_evidence=False), "contact semantics cannot be defaulted"),
        ("task_input_unavailable_false", lambda x: x["semantics"].update(unavailable_is_not_false=False), "contact semantics cannot be defaulted"),
        ("task_input_goal_threshold", lambda x: x["semantics"].update(goal_threshold_m=0.04), "changes the pinned bowl-on-plate goal"),
        ("task_input_goal_evidence", lambda x: x["semantics"].update(required_evidence=["lift height"]), "omits or changes a required On predicate"),
    ],
)
def test_recipe_input_boundary_rejections(tmp_path: Path, label, mutate, expected):
    task = json.loads(_path("R07B_TASK_INPUT").read_text(encoding="utf-8"))
    mutate(task)
    task_path = _write_json(tmp_path / f"{label}.json", task)
    proc = _cli(["recipe", "--manifest", str(_path("R07B_MANIFEST")), "--target", str(_path("R07B_INSTALL_A")),
                 "--task-input", str(task_path), "--output", str(tmp_path / f"{label}.recipe.json")],
                case=label, expected=expected)
    assert proc.returncode != 0
    assert expected in proc.stderr
    assert not (tmp_path / f"{label}.recipe.json").exists()


@pytest.mark.parametrize("label,mutation,expected", [
    ("target_payload_tamper", "payload", "size mismatch"),
    ("target_missing_file", "missing", "file set differs"),
    ("target_extra_file", "extra", "file set differs"),
    ("target_symlink", "symlink", "contains a symlink"),
    ("target_receipt_tamper", "receipt", "receipt self-hash mismatch"),
    ("target_cross_install_receipt", "cross_receipt", "different installation target"),
])
def test_installed_target_is_reread_and_bound(label, mutation, expected, tmp_path: Path):
    target = _path("R07B_INSTALL_B")
    relative = "notices/LIBERO-LICENSE.txt"
    payload = target / relative
    original_payload = payload.read_bytes()
    receipt = target / "install_receipt.json"
    original_receipt = receipt.read_bytes()
    try:
        if mutation == "payload":
            payload.write_bytes(original_payload + b"tamper")
        elif mutation == "missing":
            payload.unlink()
        elif mutation == "extra":
            (target / "unexpected.txt").write_text("extra", encoding="utf-8")
        elif mutation == "symlink":
            payload.unlink()
            payload.symlink_to(_path("R07B_TASK_INPUT"))
        elif mutation == "receipt":
            data = json.loads(original_receipt)
            data["manifest_sha256"] = "0" * 64
            receipt.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        elif mutation == "cross_receipt":
            receipt.write_bytes((_path("R07B_INSTALL_A") / "install_receipt.json").read_bytes())
        proc = _cli(["verify", "--manifest", str(_path("R07B_MANIFEST")), "--target", str(target),
                     "--receipt-out", str(tmp_path / f"{label}.json")], case=label, expected=expected)
        assert proc.returncode != 0
        assert expected in proc.stderr
    finally:
        if (target / "unexpected.txt").exists():
            (target / "unexpected.txt").unlink()
        if payload.is_symlink() or payload.exists():
            payload.unlink()
        payload.write_bytes(original_payload)
        receipt.write_bytes(original_receipt)


def test_real_recipe_cli_success(tmp_path: Path):
    output = tmp_path / "recipe.json"
    proc = _cli(["recipe", "--manifest", str(_path("R07B_MANIFEST")), "--target", str(_path("R07B_INSTALL_A")),
                 "--task-input", str(_path("R07B_TASK_INPUT")), "--output", str(output)],
                case="recipe_success", expect_success=True)
    assert proc.returncode == 0, proc.stderr
    recipe = json.loads(output.read_text(encoding="utf-8"))
    claimed_recipe_hash = recipe.pop("recipe_sha256")
    canonical_recipe = json.dumps(recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    assert hashlib.sha256(canonical_recipe).hexdigest() == claimed_recipe_hash
    recipe["recipe_sha256"] = claimed_recipe_hash
    assert recipe["schema_version"] == "libero-deployment-recipe-v1"
    assert recipe["task"]["uid"] == "libero_spatial/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate"
    assert recipe["robot"]["native_reference"]["arm_actuator_types"] == ["motor"] * 7
    assert recipe["controller"]["control_frequency_hz"] == 20
    assert recipe["controller"]["core_equivalence"] == "diagnostic joint-space profile; not OSC_POSE equivalence"
    assert recipe["controller"]["hold_policy"] == "joint_torque_zero_order_hold_per_outer_step_v1"
    assert recipe["observation"]["requested_core_candidate"] == "state-only"
    assert recipe["evaluation"]["unavailable_is_not_false"] is True
    assert recipe["accepted_scope"]["status"] == "ACCEPTED_BOUNDED_R07_A123_TECHNICAL"
    assert recipe["accepted_scope"]["qualification"] is False
    assert recipe["accepted_scope"]["task_success"] is False
    assert recipe["limits"]["file_specific_asset_license_or_attribution"] == "unresolved"
    assert recipe["recording"]["status"] == "recipe_only_no_new_recording_run"


def test_matching_install_is_idempotent():
    proc = _cli(_install_args(_path("R07B_MANIFEST"), _path("R07B_INSTALL_A")),
                case="matching_install_idempotence", expect_success=True)
    assert proc.returncode == 0, proc.stderr
    assert "ALREADY_PRESENT_VERIFIED" in proc.stdout


def test_changed_manifest_cannot_reuse_existing_install(tmp_path: Path):
    manifest = _base_manifest()
    manifest["manifest_id"] += "-different"
    variant = _write_json(tmp_path / "conflicting-manifest.json", manifest)
    proc = _cli(_install_args(variant, _path("R07B_INSTALL_A")), case="different_manifest_conflict",
                expected="producer receipt does not bind this manifest")
    assert proc.returncode != 0
    assert "producer receipt does not bind this manifest" in proc.stderr


@pytest.mark.parametrize("label,kind,expected", [
    ("install_bad_source_hash", "hash", "source SHA-256 mismatch"),
    ("install_bad_source_size", "size", "source byte size mismatch"),
    ("install_missing_source", "missing", "source file is missing"),
])
def test_failed_install_publishes_no_target_or_success_receipt(tmp_path: Path, label, kind, expected):
    manifest = _base_manifest()
    row = next(x for x in manifest["files"] if x["role"] == "asset_dependency" and x["source_root_id"] == "libero-assets")
    if kind == "hash":
        row["sha256"] = "0" * 64
        _refresh_asset_closure(manifest)
    elif kind == "size":
        row["size_bytes"] += 1
        _refresh_asset_closure(manifest)
    variant = _write_json(tmp_path / f"{label}.manifest.json", manifest)
    target = tmp_path / f"{label}-target"
    roots = _roots()
    if kind == "missing":
        empty = tmp_path / "empty-assets"
        empty.mkdir()
        roots["libero-assets"] = str(empty)
    args = ["install", "--manifest", str(variant), "--target", str(target)]
    for key, value in roots.items():
        args.extend(["--source-root", f"{key}={value}"])
    proc = _cli(args, case=label, expected=expected)
    assert proc.returncode != 0
    assert expected in proc.stderr
    assert not target.exists()


def test_no_blocked_engine_import_was_attempted():
    log = _path("R07B_TRIPWIRE_LOG")
    rows = [] if not log.exists() else [json.loads(x) for x in log.read_text().splitlines() if x]
    assert rows == []
