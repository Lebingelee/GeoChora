"""Bounded trajectory worker for the R07c D01 pilot route.

The worker uses only the SelectedReferenceEnv lifecycle and recording
interfaces.  It owns no reset, control, physics, or recording implementation.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from collections.abc import Mapping
from pathlib import Path
import tarfile
from typing import Any

import numpy as np

from task_env.artifacts import PoseWorld, ResetPlanV1, ResetSampleV1
from task_env.assembly.assets import _source_closure_digest, _source_closure_manifest

from bench_deploy.libero.planners.libero import plan_episode_actions, selected_action_from_planner
from bench_deploy.libero.artifacts.contracts import LIBERO_REVISION, ROBOSUITE_REVISION, TASK_1


_TASK1_COMPOSED_XML_SHA256 = "4a922f3729e3f44004579958e719466dbe66f4bfc4162a8221414622aed57fa0"
_TASK1_COMPOSITION_PLAN_SHA256 = "b00fc11157c4d7ea7fee4ecaf8e099f6bf2d780704af802cdcc88b1f8a0ba656"
_TASK1_SOURCE_MANIFEST_SHA256 = "4ad168e4710f3153d0f1f470389a506df27588e4d5ce1eaec450289807d30a75"
_TASK1_ASSET_CLOSURE_SHA256 = "f56207a835e80c04e7b4746a90fd3fd39b6170326a54b1445df5244d5047ca05"
_TASK1_EXECUTION_SOURCE_CLOSURE_SHA256 = "3881f687e5306ff66b0774b1385bb69716951d52d1f24d9625e1981a40f1a6a7"
_PINNED_MUJOCO_RUNTIME_IDENTITY = {
    "provider_build": {
        "dirty_build_sha256": None,
        "import_origin": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/__init__.py",
        "manifest_version": "package:3.8.1",
        "origin_sha256": "f8e5b528617004b6215e16cb0c945faf1f8c7b5d798e5b92e3aabce19c838497",
        "package_version": "3.8.1", "provider": "mujoco",
        "repository_revision": None,
    },
    "runtime": {
        "api_version": 3008001,
        "binding_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/_functions.cpython-312-x86_64-linux-gnu.so",
        "binding_sha256": "9067239d3126392729430d12d077ab4b298c61d2ea1209c9333823be410359e3",
        "mapped_native_libraries": [{
            "path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/libmujoco.so.3.8.1",
            "sha256": "8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592",
        }],
        "package_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/__init__.py",
        "package_sha256": "f8e5b528617004b6215e16cb0c945faf1f8c7b5d798e5b92e3aabce19c838497",
        "package_version": "3.8.1",
        "public_header_path": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/include/mujoco/mujoco.h",
        "public_header_sha256": "d5ccfb227eb06586edfb4def5812a8082c1cbdf8e6dc5c3176abd9772a57fd07",
        "renderer_initialized": False, "runtime_version": "3.8.1",
    },
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _pose_world_mapping_matches(actual: Any, expected: Any) -> bool:
    """Compare serialized world poses using the Runtime reset pose tolerance.

    MuJoCo may normalize a compiled body quaternion by a few floating-point
    ulps during ``mj_forward``. Position/orientation equality is therefore
    numerical at 1e-12, matching the public Runtime reset contract; quaternion
    sign-equivalent representations are accepted.
    """
    if not isinstance(actual, Mapping) or not isinstance(expected, Mapping):
        return False
    if set(actual) != set(expected):
        return False
    for name in actual:
        actual_pose = actual[name]
        expected_pose = expected[name]
        if not isinstance(actual_pose, Mapping) or not isinstance(expected_pose, Mapping):
            return False
        try:
            actual_position = np.asarray(actual_pose.get("position"), dtype=np.float64)
            expected_position = np.asarray(expected_pose.get("position"), dtype=np.float64)
            actual_quaternion = np.asarray(actual_pose.get("quaternion_wxyz"), dtype=np.float64)
            expected_quaternion = np.asarray(expected_pose.get("quaternion_wxyz"), dtype=np.float64)
        except (TypeError, ValueError):
            return False
        if (actual_position.shape != (3,) or expected_position.shape != (3,)
                or actual_quaternion.shape != (4,) or expected_quaternion.shape != (4,)
                or not np.isfinite(actual_position).all() or not np.isfinite(expected_position).all()
                or not np.isfinite(actual_quaternion).all() or not np.isfinite(expected_quaternion).all()
                or not np.allclose(actual_position, expected_position, rtol=0.0, atol=1e-12)
                or not (np.allclose(actual_quaternion, expected_quaternion, rtol=0.0, atol=1e-12)
                        or np.allclose(actual_quaternion, -expected_quaternion,
                                       rtol=0.0, atol=1e-12))):
            return False
    return True


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _write_solution_source_bundle(output_dir: Path, *,
                                  source_closure_files: Mapping[str, bytes],
                                  composition_plan_bytes: bytes,
                                  raw_source_xml_bytes: bytes | None = None,
                                  model_profile_bytes: bytes | None = None) -> dict[str, Any]:
    """Persist the exact task #1 importer snapshot and selected composition plan."""
    files = dict(source_closure_files)
    if ("canonical-source.xml" not in files or "scene.xml" not in files
            or files["canonical-source.xml"] != files["scene.xml"]):
        raise ValueError("task #1 source bundle must bind identical canonical and importer XML bytes")
    source_xml = files["canonical-source.xml"]
    xml_sha = hashlib.sha256(source_xml).hexdigest()
    closure_digest = _source_closure_digest(files)
    plan = json.loads(bytes(composition_plan_bytes).decode("utf-8"))
    plan_sha = hashlib.sha256(bytes(composition_plan_bytes)).hexdigest()
    profiled = raw_source_xml_bytes is not None or model_profile_bytes is not None
    if profiled:
        if type(raw_source_xml_bytes) is not bytes or type(model_profile_bytes) is not bytes:
            raise ValueError("profiled task source bundle requires raw MJCF and model profile receipt bytes")
        try:
            profile_receipt = json.loads(model_profile_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("task model profile receipt is not valid UTF-8 JSON") from exc
        if _canonical(profile_receipt) != model_profile_bytes:
            raise ValueError("task model profile receipt must use canonical JSON bytes")
        from bench_deploy.libero.assembly.model_profile import (
            LIBERO_OFFICIAL_SOURCE_PLAN_SHA256, ROBOT_MODEL_PROFILE_V3_ID,
            normalize_libero_robosuite_model_xml_v2,
            normalize_libero_robosuite_model_xml_v3,
            validate_libero_official_source_plan_v1,
        )
        profile_id = profile_receipt.get("profile_id")
        official_model_profile = profile_id == ROBOT_MODEL_PROFILE_V3_ID
        if profile_id == "libero-robosuite-panda-layout-seed19-v2":
            expected_xml, expected_profile = normalize_libero_robosuite_model_xml_v2(
                raw_source_xml_bytes,
            )
            expected_source_id_prefix = "libero-spatial-pilot-model-profile-v2"
            expected_bundle_schema = "r07-v210-task-source-bundle-v2"
            expected_raw_sha = _TASK1_COMPOSED_XML_SHA256
        elif official_model_profile:
            expected_xml, expected_profile = normalize_libero_robosuite_model_xml_v3(
                raw_source_xml_bytes,
            )
            validate_libero_official_source_plan_v1(
                bytes(composition_plan_bytes), raw_source_xml_bytes,
            )
            expected_source_id_prefix = "libero-spatial-official-model-profile-v3"
            expected_bundle_schema = "r07-v210-task-source-bundle-v3"
            expected_raw_sha = "9faeed9185d08b2b3d26d45e950ef7eebeec7866b76edf8e8c390fc19ed8cd12"
        else:
            raise ValueError("task Solution model profile id is not an admitted pinned profile")
        expected_profile_bytes = _canonical(expected_profile)
        raw_sha = hashlib.sha256(raw_source_xml_bytes).hexdigest()
        profile_sha = hashlib.sha256(model_profile_bytes).hexdigest()
        source_id = (
            f"{expected_source_id_prefix}:{raw_sha}:{profile_sha}:{xml_sha}"
        )
        if (expected_xml != source_xml or expected_profile_bytes != model_profile_bytes
                or raw_sha != expected_raw_sha
                or profile_receipt.get("raw_source_xml_sha256") != raw_sha
                or profile_receipt.get("runtime_model_xml_sha256") != xml_sha
                or profile_receipt.get("profile_id") != expected_profile.get("profile_id")):
            raise ValueError("profiled task source differs from the deterministic model transform")
    else:
        if (xml_sha != _TASK1_COMPOSED_XML_SHA256
                or closure_digest != _TASK1_EXECUTION_SOURCE_CLOSURE_SHA256):
            raise ValueError("legacy task source bundle differs from its frozen source identity")
        raw_sha = profile_sha = None
        profile_receipt = None
        source_id = f"libero-spatial-pilot-v1:{xml_sha}"
        expected_bundle_schema = "r07-v210-task-source-bundle-v1"
    if profiled and profile_receipt.get("profile_id") == ROBOT_MODEL_PROFILE_V3_ID:
        if plan_sha != LIBERO_OFFICIAL_SOURCE_PLAN_SHA256:
            raise ValueError("official task source bundle differs from its pinned composition plan")
    elif (plan_sha != _TASK1_COMPOSITION_PLAN_SHA256
            or plan.get("schema_version") != "libero-source-composition-mjcf-v4"
            or plan.get("identity", {}).get("task_uid") != TASK_1
            or plan.get("identity", {}).get("manifest_sha256") != _TASK1_SOURCE_MANIFEST_SHA256
            or plan.get("identity", {}).get("asset_closure_sha256") != _TASK1_ASSET_CLOSURE_SHA256
            or plan.get("identity", {}).get("source_revisions") != {
                "libero": LIBERO_REVISION, "robosuite": ROBOSUITE_REVISION,
            }
            or plan.get("output", {}).get("composed_mjcf_sha256")
               != (raw_sha if profiled else xml_sha)):
        raise ValueError("task #1 source bundle differs from the frozen composition/task manifest")
    source_root = output_dir / "source_inputs"
    source_root.mkdir(parents=True, exist_ok=True)
    for logical_path, content in files.items():
        if (type(logical_path) is not str or not logical_path or logical_path.startswith("/")
                or "\\" in logical_path or any(part in {"", ".", ".."} for part in logical_path.split("/"))
                or not isinstance(content, bytes)):
            raise ValueError("task #1 source bundle contains an unsafe path or non-byte payload")
    archive_path = source_root / "closure.tar.gz"
    with tarfile.open(archive_path, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for logical_path, content in sorted(files.items()):
            member = tarfile.TarInfo(name=f"closure/{logical_path}")
            member.type = tarfile.REGTYPE
            member.mode = 0o644
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            member.mtime = 0
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    archive_bytes = archive_path.read_bytes()
    archive_manifest = {
        "schema_version": "r07-v210-source-closure-archive-manifest-v1",
        "archive_path": "closure.tar.gz",
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "archive_size_bytes": len(archive_bytes),
        "archive_verified": True,
        "expanded_size_bytes": sum(len(content) for content in files.values()),
        "file_count": len(files),
        "entries": [
            {"kind": "file", "relative_path": f"closure/{row['path']}",
             "size_bytes": row["size_bytes"], "sha256": row["sha256"], "mode": 0o644}
            for row in _source_closure_manifest(files)
        ],
    }
    archive_manifest_bytes = _canonical(archive_manifest)
    archive_manifest_path = source_root / "closure_archive_manifest.json"
    archive_manifest_path.write_bytes(archive_manifest_bytes)
    plan_path = source_root / "composition_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_bytes(bytes(composition_plan_bytes))
    if profiled:
        (source_root / "raw-composed-source.xml").write_bytes(raw_source_xml_bytes)
        (source_root / "model-profile.json").write_bytes(model_profile_bytes)
    result = {
        "schema_version": expected_bundle_schema,
        "source_id": source_id,
        "canonical_xml_sha256": xml_sha,
        "importer_xml_sha256": hashlib.sha256(files["scene.xml"]).hexdigest(),
        "source_closure_digest": closure_digest,
        "closure_files": list(_source_closure_manifest(files)),
        "closure_archive": {
            "relative_path": "source_inputs/closure.tar.gz",
            "bytes": len(archive_bytes),
            "sha256": archive_manifest["archive_sha256"],
            "expanded_bytes": archive_manifest["expanded_size_bytes"],
            "file_count": archive_manifest["file_count"],
        },
        "closure_archive_manifest": {
            "relative_path": "source_inputs/closure_archive_manifest.json",
            "bytes": len(archive_manifest_bytes),
            "sha256": hashlib.sha256(archive_manifest_bytes).hexdigest(),
        },
        "composition_plan": {
            "relative_path": "source_inputs/composition_plan.json",
            "bytes": len(composition_plan_bytes),
            "sha256": plan_sha,
        },
    }
    if profiled:
        result.update({
            "raw_source_xml_sha256": raw_sha,
            "model_profile_id": profile_receipt["profile_id"],
            "model_profile_receipt_sha256": profile_sha,
            "raw_source": {
                "relative_path": "source_inputs/raw-composed-source.xml",
                "bytes": len(raw_source_xml_bytes), "sha256": raw_sha,
            },
            "model_profile": {
                "relative_path": "source_inputs/model-profile.json",
                "bytes": len(model_profile_bytes), "sha256": profile_sha,
            },
        })
    return result


def _verify_solution_source_bundle(bundle_path: Path, source_bundle: Any) -> dict[str, Any]:
    """Independently reread and recompute the task #1 immutable source closure."""
    source_bundle_schema = (
        source_bundle.get("schema_version") if isinstance(source_bundle, Mapping) else None
    )
    profiled = source_bundle_schema in {
        "r07-v210-task-source-bundle-v2", "r07-v210-task-source-bundle-v3",
    }
    official_profiled = source_bundle_schema == "r07-v210-task-source-bundle-v3"
    if (not isinstance(source_bundle, Mapping)
            or source_bundle.get("schema_version") not in {
                "r07-v210-task-source-bundle-v1", "r07-v210-task-source-bundle-v2",
                "r07-v210-task-source-bundle-v3",
            }):
        raise ValueError("task Solution bundle omits its versioned immutable source inputs")
    closure_rows = source_bundle.get("closure_files")
    if not isinstance(closure_rows, list) or not closure_rows:
        raise ValueError("task Solution source bundle closure manifest is empty")
    bundle_root = Path(bundle_path).resolve(strict=True)
    if bundle_root.is_file():
        bundle_root = bundle_root.parent
    if not bundle_root.is_dir():
        raise ValueError("task Solution bundle root is not a directory")
    source_root = bundle_root / "source_inputs"
    if source_root.is_symlink() or source_root.resolve(strict=True) != source_root:
        raise ValueError("task Solution source root is unsafe")

    def safe_file(root: Path, raw_path: str | Path) -> Path:
        root = root.resolve(strict=True)
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = root / candidate
        current = candidate
        while current != root and root in current.parents:
            if current.is_symlink():
                raise ValueError("task Solution source archive path contains a symlink")
            current = current.parent
        resolved = candidate.resolve(strict=True)
        if root not in resolved.parents or not resolved.is_file():
            raise ValueError("task Solution source archive escaped its approved root")
        return resolved

    def file_rows_from_archive_manifest(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for row in manifest.get("entries", ()):
            if not isinstance(row, Mapping) or row.get("kind") != "file":
                continue
            relative = row.get("relative_path")
            if type(relative) is not str:
                raise ValueError("task Solution archive manifest file path is malformed")
            logical = relative[len("closure/"):] if relative.startswith("closure/") else relative
            rows.append({
                "path": logical,
                "size_bytes": row.get("size_bytes"),
                "sha256": row.get("sha256"),
            })
        return rows

    from bench_deploy.libero.controllers.source_gravity import read_source_closure_archive

    closure_root = source_root / "closure"
    if closure_root.exists():
        if closure_root.is_symlink() or closure_root.resolve(strict=True) != closure_root:
            raise ValueError("task Solution source closure root is unsafe")
        files: dict[str, bytes] = {}
        for row in closure_rows:
            if not isinstance(row, Mapping):
                raise ValueError("task Solution source closure manifest row is malformed")
            logical = row.get("path")
            if (type(logical) is not str or not logical or logical.startswith("/")
                    or "\\" in logical or any(part in {"", ".", ".."} for part in logical.split("/"))
                    or logical in files):
                raise ValueError("task Solution source closure path is unsafe or duplicated")
            source_path = safe_file(closure_root, logical)
            content = source_path.read_bytes()
            if (len(content) != row.get("size_bytes")
                    or hashlib.sha256(content).hexdigest() != row.get("sha256")
                    or source_path.stat().st_nlink != 1):
                raise ValueError(f"task Solution source closure bytes differ from their manifest: {logical}")
            files[logical] = content
        nodes = list(closure_root.rglob("*"))
        if any(path.is_symlink() for path in nodes):
            raise ValueError("task Solution source closure contains a symlink")
        actual_paths = {path.relative_to(closure_root).as_posix() for path in nodes if path.is_file()}
        if actual_paths != set(files):
            raise ValueError("task Solution source closure contains missing or unlisted files")
    else:
        archive_info = source_bundle.get("closure_archive")
        if isinstance(archive_info, Mapping):
            archive_rel = archive_info.get("relative_path")
            manifest_info = source_bundle.get("closure_archive_manifest")
            if (archive_rel != "source_inputs/closure.tar.gz"
                    or not isinstance(manifest_info, Mapping)
                    or manifest_info.get("relative_path") != "source_inputs/closure_archive_manifest.json"):
                raise ValueError("task Solution archive identity paths are unsupported")
            archive_path = safe_file(bundle_root, archive_rel)
            archive_manifest_path = safe_file(bundle_root, manifest_info["relative_path"])
            archive_bytes = archive_path.read_bytes()
            manifest_bytes = archive_manifest_path.read_bytes()
            if (len(archive_bytes) != archive_info.get("bytes")
                    or hashlib.sha256(archive_bytes).hexdigest() != archive_info.get("sha256")
                    or len(manifest_bytes) != manifest_info.get("bytes")
                    or hashlib.sha256(manifest_bytes).hexdigest() != manifest_info.get("sha256")):
                raise ValueError("task Solution source archive or manifest bytes differ from their identity")
            archive_manifest = json.loads(manifest_bytes.decode("utf-8"))
            if (archive_manifest.get("schema_version") != "r07-v210-source-closure-archive-manifest-v1"
                    or archive_manifest.get("archive_verified") is not True
                    or archive_manifest.get("archive_sha256") != archive_info.get("sha256")
                    or archive_manifest.get("archive_size_bytes") != len(archive_bytes)
                    or archive_manifest.get("expanded_size_bytes") != archive_info.get("expanded_bytes")
                    or archive_manifest.get("file_count") != archive_info.get("file_count")):
                raise ValueError("task Solution source archive manifest does not match the archive identity")
            files = read_source_closure_archive(archive_path, closure_rows)
            manifest_rows = file_rows_from_archive_manifest(archive_manifest)
            if sorted(manifest_rows, key=lambda row: row["path"]) != sorted(
                    [{key: row.get(key) for key in ("path", "size_bytes", "sha256")} for row in closure_rows],
                    key=lambda row: row["path"]):
                raise ValueError("task Solution archive member set differs from its manifest")
        else:
            reuse_path = source_root / "source_closure_reuse_receipt.json"
            if not reuse_path.is_file() or reuse_path.is_symlink():
                raise FileNotFoundError("task Solution bundle has no expanded or archived source closure")
            reuse = json.loads(reuse_path.read_text(encoding="utf-8"))
            runs_root = bundle_root.parent.parent.resolve(strict=True)
            archive_path = safe_file(runs_root, reuse.get("canonical_archive_path", ""))
            archive_manifest_path = safe_file(runs_root, reuse.get("canonical_archive_manifest_path", ""))
            report_path = bundle_root / "worker_result.json"
            report_bytes = report_path.read_bytes()
            archive_bytes = archive_path.read_bytes()
            manifest_bytes = archive_manifest_path.read_bytes()
            if (reuse.get("schema_version") != "r07-v210-native-run-source-closure-reuse-v1"
                    or reuse.get("status") != "verified_identical_closure_referenced"
                    or reuse.get("run_id") != bundle_root.parent.name
                    or reuse.get("worker_result_path") != str(report_path)
                    or hashlib.sha256(report_bytes).hexdigest() != reuse.get("worker_result_sha256")
                    or (reuse.get("worker_closure_digest") is not None
                        and reuse.get("worker_closure_digest") != source_bundle.get("source_closure_digest"))
                    or reuse.get("raw_closure_matches_worker_result_file_hashes") is not True
                    or hashlib.sha256(archive_bytes).hexdigest() != reuse.get("canonical_archive_sha256")
                    or hashlib.sha256(manifest_bytes).hexdigest() != reuse.get("canonical_archive_manifest_sha256")):
                raise ValueError("task Solution source archive reuse receipt is not bound to this worker bundle")
            archive_manifest = json.loads(manifest_bytes.decode("utf-8"))
            if (archive_manifest.get("archive_verified") is not True
                    or archive_manifest.get("archive_sha256") != reuse.get("canonical_archive_sha256")
                    or archive_manifest.get("file_count") != reuse.get("canonical_archive_file_count")
                    or archive_manifest.get("expanded_size_bytes") != reuse.get("canonical_archive_expanded_bytes")
                    or archive_path.stat().st_size != archive_manifest.get("archive_size_bytes")):
                raise ValueError("task Solution canonical source archive manifest is inconsistent")
            files = read_source_closure_archive(archive_path, closure_rows)
            manifest_rows = file_rows_from_archive_manifest(archive_manifest)
            if sorted(manifest_rows, key=lambda row: row["path"]) != sorted(
                    [{key: row.get(key) for key in ("path", "size_bytes", "sha256")} for row in closure_rows],
                    key=lambda row: row["path"]):
                raise ValueError("task Solution canonical archive members differ from the worker result")

    if _source_closure_digest(files) != source_bundle.get("source_closure_digest"):
        raise ValueError("task Solution source closure digest does not recompute")
    canonical_xml = files.get("canonical-source.xml")
    importer_xml = files.get("scene.xml")
    if (canonical_xml is None or importer_xml != canonical_xml
            or hashlib.sha256(canonical_xml).hexdigest() != source_bundle.get("canonical_xml_sha256")
            or hashlib.sha256(importer_xml).hexdigest() != source_bundle.get("importer_xml_sha256")
            or (not profiled and (
                source_bundle.get("source_closure_digest") != _TASK1_EXECUTION_SOURCE_CLOSURE_SHA256
                or source_bundle.get("canonical_xml_sha256") != _TASK1_COMPOSED_XML_SHA256
                or source_bundle.get("source_id") != f"libero-spatial-pilot-v1:{_TASK1_COMPOSED_XML_SHA256}"
            ))):
        raise ValueError("task Solution source XML identity differs from the pinned task composition")
    plan_info = source_bundle.get("composition_plan")
    if not isinstance(plan_info, Mapping) or plan_info.get("relative_path") != "source_inputs/composition_plan.json":
        raise ValueError("task Solution bundle omits its source composition plan")
    plan_path = (bundle_root / plan_info["relative_path"]).resolve(strict=True)
    if bundle_root not in plan_path.parents:
        raise ValueError("task Solution composition plan escaped the worker bundle")
    plan_bytes = plan_path.read_bytes()
    if (len(plan_bytes) != plan_info.get("bytes")
            or hashlib.sha256(plan_bytes).hexdigest() != plan_info.get("sha256")):
        raise ValueError("task Solution composition plan bytes differ from the pinned plan")
    if official_profiled:
        from bench_deploy.libero.assembly.model_profile import LIBERO_OFFICIAL_SOURCE_PLAN_SHA256
        if plan_info.get("sha256") != LIBERO_OFFICIAL_SOURCE_PLAN_SHA256:
            raise ValueError("official task Solution composition plan differs from pinned bytes")
    elif plan_info.get("sha256") != _TASK1_COMPOSITION_PLAN_SHA256:
        raise ValueError("task Solution composition plan bytes differ from the pinned plan")
    plan = json.loads(plan_bytes.decode("utf-8"))
    identity = plan.get("identity", {})
    if official_profiled:
        valid_official_plan_shell = (
            plan.get("schema_version") == "libero-official-source-composition-plan-v1"
            and identity.get("task_uid") == TASK_1
            and identity.get("libero_revision") == LIBERO_REVISION
            and identity.get("robosuite_revision") == ROBOSUITE_REVISION
            and identity.get("source_model_id") == "libero-official-model-builder-v1"
            and identity.get("seed") == 19
            and plan.get("output", {}).get("composed_mjcf_sha256")
                == source_bundle.get("raw_source_xml_sha256")
            and plan.get("output", {}).get("status") == "SOURCE_MJCF_COMPOSED_NOT_NATIVE_COMPILED"
        )
        if not valid_official_plan_shell:
            raise ValueError("official task Solution composition plan is not the pinned source plan")
    elif (plan.get("schema_version") != "libero-source-composition-mjcf-v4"
            or identity.get("task_uid") != TASK_1
            or identity.get("manifest_sha256") != _TASK1_SOURCE_MANIFEST_SHA256
            or identity.get("asset_closure_sha256") != _TASK1_ASSET_CLOSURE_SHA256
            or identity.get("source_revisions") != {
                "libero": LIBERO_REVISION, "robosuite": ROBOSUITE_REVISION,
            }
            or plan.get("output", {}).get("composed_mjcf_sha256") != (
                source_bundle.get("raw_source_xml_sha256") if profiled
                else source_bundle.get("canonical_xml_sha256")
            )):
        raise ValueError("task Solution composition plan is not the pinned task #1 source plan")
    result = {
        "schema_version": "r07-v210-task-source-bundle-readback-v1",
        "status": "verified_source_closure_and_plan",
        "source_id": source_bundle["source_id"],
        "source_closure_digest": source_bundle["source_closure_digest"],
        "canonical_xml_sha256": source_bundle["canonical_xml_sha256"],
        "composition_plan_sha256": plan_info["sha256"],
        "closure_file_count": len(files),
        "_canonical_xml_bytes": canonical_xml,
    }
    if profiled:
        raw_info = source_bundle.get("raw_source")
        profile_info = source_bundle.get("model_profile")
        if (not isinstance(raw_info, Mapping) or not isinstance(profile_info, Mapping)
                or raw_info.get("relative_path") != "source_inputs/raw-composed-source.xml"
                or profile_info.get("relative_path") != "source_inputs/model-profile.json"):
            raise ValueError("profiled task source bundle omits raw-source or profile metadata")
        raw_path = safe_file(bundle_root, raw_info["relative_path"])
        profile_path = safe_file(bundle_root, profile_info["relative_path"])
        raw_xml = raw_path.read_bytes()
        profile_bytes = profile_path.read_bytes()
        if (len(raw_xml) != raw_info.get("bytes")
                or hashlib.sha256(raw_xml).hexdigest() != raw_info.get("sha256")
                or len(profile_bytes) != profile_info.get("bytes")
                or hashlib.sha256(profile_bytes).hexdigest() != profile_info.get("sha256")
                or source_bundle.get("raw_source_xml_sha256") != raw_info.get("sha256")
                or source_bundle.get("model_profile_receipt_sha256") != profile_info.get("sha256")):
            raise ValueError("profiled task source metadata differs from its recorded hashes")
        try:
            profile = json.loads(profile_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("profiled task model receipt is not valid UTF-8 JSON") from exc
        from bench_deploy.libero.assembly.model_profile import (
            LIBERO_OFFICIAL_REBASED_MODEL_SHA256, ROBOT_MODEL_PROFILE_V3_ID,
            normalize_libero_robosuite_model_xml_v2,
            normalize_libero_robosuite_model_xml_v3,
            validate_libero_official_source_plan_v1,
        )
        profile_id = profile.get("profile_id")
        if profile_id == "libero-robosuite-panda-layout-seed19-v2":
            expected_xml, expected_profile = normalize_libero_robosuite_model_xml_v2(raw_xml)
            source_id_prefix = "libero-spatial-pilot-model-profile-v2"
            expected_raw_sha = _TASK1_COMPOSED_XML_SHA256
        elif profile_id == ROBOT_MODEL_PROFILE_V3_ID:
            expected_xml, expected_profile = normalize_libero_robosuite_model_xml_v3(raw_xml)
            validate_libero_official_source_plan_v1(plan_bytes, raw_xml)
            source_id_prefix = "libero-spatial-official-model-profile-v3"
            expected_raw_sha = LIBERO_OFFICIAL_REBASED_MODEL_SHA256
        else:
            raise ValueError("task Solution bundle uses an unsupported model profile")
        profile_sha = hashlib.sha256(profile_bytes).hexdigest()
        source_id = (
            f"{source_id_prefix}:{raw_info['sha256']}:{profile_sha}:"
            f"{source_bundle['canonical_xml_sha256']}"
        )
        if (official_profiled != (profile_id == ROBOT_MODEL_PROFILE_V3_ID)
                or raw_info["sha256"] != expected_raw_sha
                or profile_bytes != _canonical(profile)
                or profile_bytes != _canonical(expected_profile)
                or expected_xml != canonical_xml
                or profile.get("profile_id") != source_bundle.get("model_profile_id")
                or profile.get("runtime_model_xml_sha256") != source_bundle.get("canonical_xml_sha256")
                or source_bundle.get("source_id") != source_id):
            raise ValueError("profiled task source transform or profile identity does not recompute")
        result.update({
            "raw_source_xml_sha256": raw_info["sha256"],
            "model_profile_id": profile["profile_id"],
            "model_profile_receipt_sha256": profile_sha,
            "_raw_source_xml_bytes": raw_xml,
            "_model_profile_bytes": profile_bytes,
        })
    return result


def _task1_iterative_resolver_identity(source_xml_bytes: bytes, task_artifact_identity: str,
                                       diagnostics: Mapping[str, Any], *,
                                       high_precision_profile: bool = False) -> str:
    """Rebuild the public provider-free resolver profile from verified source bytes."""
    from task_env.controllers.canonical import CanonicalPandaController, PandaKinematics
    from task_env.controllers.canonical.kinematics import derive_panda_tcp_profile_v2
    from task_env.environment import ActionConfig

    required = (
        "max_iterations", "position_tolerance_m", "orientation_tolerance_rad",
        "model_position_tolerance_m", "model_orientation_tolerance_rad",
    )
    if not isinstance(diagnostics, Mapping) or any(key not in diagnostics for key in required):
        raise ValueError("task Solution v4 omits the iterative resolver configuration receipt")
    profile = derive_panda_tcp_profile_v2(
        source_xml_bytes, tcp_id="libero-mounted-panda-v1/gripper0-grip-site-v1",
        hand_frame_id="robot0_right_hand", site_name="gripper0_grip_site",
    )
    kinematics = PandaKinematics(
        source_xml_bytes, tcp_profile=profile, native_prefix="robot0_",
        base_body_id="robot0_link0",
    )
    resolver_config = ActionConfig()
    if high_precision_profile:
        from dataclasses import replace
        resolver_config = replace(
            resolver_config,
            ik_position_deadband=0.0005,
            ik_rotation_deadband=0.0025,
        )
    resolver = CanonicalPandaController(
        kinematics, artifact_hash=task_artifact_identity, config=resolver_config,
    )
    return resolver.iterative_resolution_identity_v1(
        max_iterations=diagnostics["max_iterations"],
        position_tolerance_m=diagnostics["position_tolerance_m"],
        orientation_tolerance_rad=diagnostics["orientation_tolerance_rad"],
        model_position_tolerance_m=diagnostics["model_position_tolerance_m"],
        model_orientation_tolerance_rad=diagnostics["model_orientation_tolerance_rad"],
    )


def _public_motion_metrics(initial_joints: np.ndarray, final_joints: np.ndarray,
                           initial_ee_pose: np.ndarray, final_ee_pose: np.ndarray) -> dict[str, float]:
    """Measure arm, TCP, and signed Panda finger-aperture motion from public state."""
    initial = np.asarray(initial_joints, dtype=np.float64)
    final = np.asarray(final_joints, dtype=np.float64)
    initial_ee = np.asarray(initial_ee_pose, dtype=np.float64)
    final_ee = np.asarray(final_ee_pose, dtype=np.float64)
    if (initial.shape != (9,) or final.shape != (9,)
            or initial_ee.shape != (7,) or final_ee.shape != (7,)
            or not all(np.isfinite(values).all() for values in (initial, final, initial_ee, final_ee))):
        raise ValueError("public motion gate requires finite seven-arm/two-finger and TCP pose receipts")
    # Panda finger_joint2 uses a negative signed coordinate.  Aggregate
    # opening is q1 - q2, matching the public controller's [opening/2,
    # -opening/2] mapping; summing the signed coordinates cancels symmetric
    # motion and understates the physical aperture change.
    initial_opening = float(initial[7] - initial[8])
    final_opening = float(final[7] - final[8])
    return {
        "arm_joint_max_abs_delta_rad": float(np.max(np.abs(final[:7] - initial[:7]))),
        "tcp_translation_delta_m": float(np.linalg.norm(final_ee[:3] - initial_ee[:3])),
        "aggregate_finger_position_delta_m": abs(final_opening - initial_opening),
    }


def _validate_public_motion_gate(summary: Mapping[str, Any], initial_joints: np.ndarray,
                                 final_joints: np.ndarray, initial_ee_pose: np.ndarray,
                                 final_ee_pose: np.ndarray, *, require_thresholds: bool) -> dict[str, float]:
    """Cross-check worker summary against H5 state and enforce the full pilot gate."""
    actual = _public_motion_metrics(initial_joints, final_joints, initial_ee_pose, final_ee_pose)
    for name, value in actual.items():
        reported = summary.get(name)
        if (isinstance(reported, bool) or not isinstance(reported, (int, float))
                or not np.isfinite(reported) or not np.isclose(float(reported), value, rtol=0.0, atol=1e-7)):
            raise ValueError(f"worker motion summary {name} differs from independent public H5 state")
    if require_thresholds:
        if actual["arm_joint_max_abs_delta_rad"] < 0.05 and actual["tcp_translation_delta_m"] < 0.02:
            raise ValueError("per-episode public motion gate requires arm delta >=0.05 rad or TCP delta >=0.02 m")
        if actual["aggregate_finger_position_delta_m"] < 0.005:
            raise ValueError("per-episode public motion gate requires aggregate finger opening delta >=0.005 m")
    return actual


def _validate_physical_state_monitor(
    monitor: Any, progress: Mapping[str, Any], compiled: Mapping[str, Any],
    observed_joints: np.ndarray,
) -> dict[str, Any]:
    """Check the provider's per-native-step physical receipt independently."""
    if not isinstance(monitor, Mapping) or monitor != progress.get("physical_state_monitor"):
        raise ValueError("episode physical-state monitor is missing or differs from public RuntimeSession progress")
    native_steps = progress.get("native_step_count")
    if (monitor.get("schema_version") != "physical-state-monitor-v1"
            or monitor.get("status") != "passed"
            or monitor.get("first_violation") is not None
            or type(native_steps) is not int or native_steps < 0
            or monitor.get("native_step_count") != native_steps
            or monitor.get("samples_including_reset") != native_steps + 1
            or monitor.get("source_id") != progress.get("source_id")
            or monitor.get("source_closure_digest") != progress.get("source_closure_digest")
            or monitor.get("provider_materialization_id") != progress.get("provider_materialization_id")
            or monitor.get("episode_id") != progress.get("episode_id")
            or monitor.get("reset_sample_id") != progress.get("reset_sample_id")
            or monitor.get("canonical_xml_sha256") != compiled.get("canonical_xml_sha256")):
        raise ValueError("physical-state monitor identity, status, or per-step count is invalid")
    expected_model_hash = hashlib.sha256(json.dumps(
        compiled, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if monitor.get("compiled_model_identity_sha256") != expected_model_hash:
        raise ValueError("physical-state monitor is bound to a different compiled model")
    tolerance = monitor.get("tolerance")
    if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
            or not np.isfinite(tolerance) or not 0.0 <= float(tolerance) <= 1.0e-8):
        raise ValueError("physical-state monitor tolerance exceeds the frozen numeric bound")
    limits = compiled.get("named_joint_limits")
    addresses = compiled.get("named_joint_addresses")
    ranges = monitor.get("joint_ranges")
    if not isinstance(limits, Mapping) or not isinstance(addresses, Mapping) or not isinstance(ranges, Mapping):
        raise ValueError("physical-state monitor omits compiled limited-joint bindings")
    expected_limited = {name: row for name, row in limits.items() if row.get("limited") is True}
    if set(ranges) != set(expected_limited):
        raise ValueError("physical-state monitor does not cover every compiled limited scalar joint")
    maximum_excursion = 0.0
    for name, expected in expected_limited.items():
        row = ranges[name]
        low, high = expected.get("range", ())
        if (row.get("joint_name") != expected.get("joint_name")
                or row.get("qpos_address") != addresses.get(name, [None])[0]
                or row.get("range") != expected.get("range")):
            raise ValueError(f"physical-state monitor source range differs from compiled joint: {name}")
        minimum, maximum = row.get("minimum_observed"), row.get("maximum_observed")
        if (type(minimum) not in (int, float) or type(maximum) not in (int, float)
                or not np.isfinite((minimum, maximum)).all() or minimum > maximum):
            raise ValueError(f"physical-state monitor extrema are malformed: {name}")
        excursion = max(0.0, float(low) - float(minimum), float(maximum) - float(high))
        maximum_excursion = max(maximum_excursion, excursion)
        if excursion > float(tolerance):
            raise ValueError(f"measured physical state exceeded a compiled joint limit: {name}")
    reported_excursion = monitor.get("maximum_excursion")
    if (isinstance(reported_excursion, bool) or not isinstance(reported_excursion, (int, float))
            or not np.isfinite(reported_excursion)
            or not np.isclose(float(reported_excursion), maximum_excursion, rtol=0.0, atol=1e-12)):
        raise ValueError("physical-state monitor maximum excursion differs from its recorded extrema")
    warning_counts = monitor.get("warning_counts")
    if (not isinstance(warning_counts, list)
            or len(warning_counts) != 7
            or any(type(value) is not int or value < 0 for value in warning_counts)
            or any(warning_counts)):
        raise ValueError("physical-state monitor omits warning counters or records a MuJoCo warning")
    joint_names = [*(f"joint{i}" for i in range(1, 8)), "finger_joint1", "finger_joint2"]
    if observed_joints.shape[1] != len(joint_names):
        raise ValueError("H5 joint observations do not cover the task's mapped monitor channels")
    for index, name in enumerate(joint_names):
        row = ranges.get(name)
        if row is None:
            raise ValueError(f"physical-state monitor omitted observed task joint: {name}")
        # H5 state channels are float32; this tolerance only accounts for that
        # serialization quantization, not for source-limit excursion.
        if (float(np.min(observed_joints[:, index])) < float(row["minimum_observed"]) - 2.0e-7
                or float(np.max(observed_joints[:, index])) > float(row["maximum_observed"]) + 2.0e-7):
            raise ValueError(f"public H5 joint observations escape the native-step monitor extrema: {name}")
    return {
        "status": "verified_physical_state_monitor",
        "native_step_count": native_steps,
        "samples_including_reset": monitor["samples_including_reset"],
        "limited_joint_count": len(ranges),
        "warning_counts": list(warning_counts),
        "maximum_excursion": float(reported_excursion),
        "tolerance": float(tolerance),
        "compiled_model_identity_sha256": expected_model_hash,
    }




def _state_observation_receipt(observation: dict[str, Any]) -> dict[str, Any]:
    state = observation["state"]
    return {
        "joint_position": [float(value) for value in np.asarray(state["joint_position"]).reshape(-1)],
        "ee_pose": [float(value) for value in np.asarray(state["ee_pose"]).reshape(-1)],
        "boundary_identity_sha256": bytes(
            np.asarray(state["boundary_identity_sha256"], dtype=np.uint8).reshape(32)
        ).hex(),
        "privileged_state": {
            name: np.asarray(value).reshape(-1).astype(np.float64).tolist()
            for name, value in observation["privileged_state"].items()
        },
    }


def _episode_record(env, *, output_dir: Path, episode_index: int, row_index: int,
                    seed: int, steps: int) -> dict[str, Any]:
    reset_observation, reset_info = env.reset(
        seed=seed, options={"init_row_index": row_index},
    )
    previous_close = None
    if episode_index:
        # SelectedReferenceEnv closes the previous RuntimeSession before it
        # materializes the next one.  The read-only receipt is captured via
        # its public lifecycle property after that transition.
        previous_close = env.close_receipt
    episode_id = reset_info.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        raise ValueError("SelectedReferenceEnv reset omitted its RuntimeSession episode identity")
    reset_sample = reset_info.get("reset_sample_v1")
    reset_realization = reset_info.get("reset_realization_v1")
    reset_readback = reset_info.get("reset_readback_v1")
    if not all(isinstance(item, dict) for item in (reset_sample, reset_realization, reset_readback)):
        raise ValueError("SelectedReferenceEnv reset omitted the versioned source/realization/readback receipts")
    episode_dir = output_dir / f"episode_{episode_index:02d}_row_{row_index:02d}"
    h5_path = episode_dir / "trajectory.h5"
    env.start_recording(h5_path)
    planner_actions = plan_episode_actions(reset_observation, row_index=row_index, steps=steps)
    action_trace = []
    final_info = dict(reset_info)
    final_observation = reset_observation
    terminated = truncated = False
    for planner_action in planner_actions:
        selected_action = selected_action_from_planner(planner_action)
        observation, reward, terminated, truncated, info = env.step(selected_action)
        final_observation, final_info = observation, info
        action_trace.append({
            "planner_action": [float(value) for value in planner_action],
            "selected_public_action": [float(value) for value in selected_action],
            "planner_to_selected_opening_m": float(selected_action[7]),
            "reward": float(reward),
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "control_step": int(info.get("control_step", -1)),
            "simulation_time_s": float(info.get("simulation_time_s", float("nan"))),
            "mixed_actuator_command_v1": info.get("mixed_actuator_command_v1"),
            "applied_mixed_actuator_command_v1": info.get("applied_mixed_actuator_command_v1"),
        })
        if terminated or truncated:
            break
    if len(action_trace) != steps:
        raise ValueError(f"selected episode ended after {len(action_trace)} of {steps} planned actions")
    if not (terminated or truncated):
        episode_end = env.stop("bounded_worker_complete")
        end_reason = episode_end.outcome.end_reason
    else:
        end_payload = final_info.get("episode_end_v1")
        if not isinstance(end_payload, dict):
            raise ValueError("terminal public step omitted EpisodeEndV1")
        end_reason = end_payload.get("outcome", {}).get("end_reason")
        if not isinstance(end_reason, str):
            end_reason = "horizon_reached" if truncated else "terminated"
    finalized = env.finish_recording(end_reason)
    h5_path = Path(finalized["path"]).resolve(strict=True)
    h5_bytes = h5_path.read_bytes()
    progress = env.get_runtime_progress_receipt()
    if (progress.get("episode_id") != episode_id
            or progress.get("native_step_count") != steps * 25
            or progress.get("control_step") != steps):
        raise ValueError("public RuntimeSession progress receipt disagrees with the planned episode")
    final_joints = np.asarray(final_observation["state"]["joint_position"], dtype=np.float64)
    initial_joints = np.asarray(reset_observation["state"]["joint_position"], dtype=np.float64)
    if final_joints.shape != (9,) or initial_joints.shape != (9,):
        raise ValueError("public reset/step observation omitted the nine mapped joint positions")
    return {
        "schema_version": "r07c-d01-libero-episode-result-v1",
        "episode_index": episode_index,
        "row_index": row_index,
        "seed": seed,
        "episode_id": episode_id,
        "task_artifact_identity_hash": env.get_record_metadata()["candidate_identity"]["task_artifact_identity_hash"],
        "source_id": reset_info.get("source_id"),
        "source_closure_digest": reset_info.get("source_closure_digest"),
        "compiled_model_layout_v1": reset_info.get("compiled_model_layout_v1"),
        "pre_reset_compiled_validation_v1": reset_info.get("pre_reset_compiled_validation_v1"),
        "reset_sample": reset_sample,
        "reset_realization": reset_realization,
        "reset_readback": reset_readback,
        "prior_session_close_receipt": previous_close,
        "control_plan": env.get_record_metadata()["control_plan"],
        "action_trace": action_trace,
        "motion_summary": _public_motion_metrics(
            initial_joints, final_joints,
            np.asarray(reset_observation["state"]["ee_pose"], dtype=np.float64),
            np.asarray(final_observation["state"]["ee_pose"], dtype=np.float64),
        ),
        "initial_observation": _state_observation_receipt(reset_observation),
        "final_observation": _state_observation_receipt(final_observation),
        "final_info": {
            "predicate_v1": final_info.get("predicate_v1"),
            "contact_summary_v2": final_info.get("contact_summary_v2"),
            "mixed_actuator_command_v1": final_info.get("mixed_actuator_command_v1"),
            "applied_mixed_actuator_command_v1": final_info.get("applied_mixed_actuator_command_v1"),
            "episode_end_v1": final_info.get("episode_end_v1"),
        },
        "runtime_progress": progress,
        "physical_state_monitor": progress.get("physical_state_monitor"),
        "finalizer": finalized,
        "h5": {
            "relative_path": str(h5_path.relative_to(output_dir.resolve())),
            "bytes": len(h5_bytes),
            "sha256": hashlib.sha256(h5_bytes).hexdigest(),
            "schema_version": finalized.get("schema_version"),
            "transition_count": finalized.get("transition_count"),
            "observation_count": finalized.get("observation_count"),
            "episode_id": episode_id,
            "final_boundary": steps,
        },
    }


def _episode_solution_record(env, *, output_dir: Path, episode_index: int,
                             row_index: int, seed: int, max_steps: int,
                             solution_factory) -> dict[str, Any]:
    """Run one task-owned Solution through the same SelectedReferenceEnv."""
    solution = solution_factory(output_dir)
    solution_schema = getattr(solution, "solution_schema_version", None)
    if solution_schema == "libero-bowl-to-plate-solution-v4":
        version_suffix = "v4"
    elif solution_schema == "libero-bowl-to-plate-solution-v5":
        version_suffix = "v5"
    elif solution_schema == "libero-bowl-to-plate-solution-v6":
        version_suffix = "v6"
    elif solution_schema == "libero-bowl-to-plate-solution-v7":
        version_suffix = "v7"
    elif solution_schema == "libero-bowl-to-plate-solution-v8":
        version_suffix = "v8"
    elif solution_schema == "libero-bowl-to-plate-solution-v3":
        version_suffix = "v3"
    elif solution_schema == "libero-bowl-to-plate-solution-v2":
        version_suffix = "v2"
    elif solution_schema == "libero-bowl-to-plate-solution-v1":
        version_suffix = "v1"
    else:
        raise ValueError("task Solution factory returned an unsupported frozen schema version")
    if type(getattr(solution, "identity", None)) is not str or len(solution.identity) != 64:
        raise TypeError("task Solution factory must return a versioned 64-hex identity")
    reset_observation, reset_info = env.reset_for_solution(
        solution, seed=seed, options={"init_row_index": row_index},
    )
    previous_close = env.close_receipt if episode_index else None
    episode_id = reset_info.get("episode_id")
    reset_sample = reset_info.get("reset_sample_v1")
    reset_realization = reset_info.get("reset_realization_v1")
    reset_readback = reset_info.get("reset_readback_v1")
    if (type(episode_id) is not str or not episode_id
            or not all(isinstance(value, dict) for value in (
                reset_sample, reset_realization, reset_readback,
            ))):
        raise ValueError("Solution reset omitted its public episode/source/readback receipts")
    episode_dir = output_dir / f"episode_{episode_index:02d}_row_{row_index:02d}"
    episode_dir.mkdir(parents=True, exist_ok=False)
    pre_reset = reset_info.get("pre_reset_compiled_validation_v1")
    if not isinstance(pre_reset, Mapping):
        raise ValueError("Solution reset omitted its pre-reset compiled/runtime identity receipt")
    start_receipt = {
        "schema_version": f"r07-v210-task-solution-start-receipt-{version_suffix}",
        "episode_index": episode_index, "row_index": row_index, "seed": seed,
        "task_uid": env.artifact.task_id,
        "task_artifact_identity_hash": env.artifact.identity_hash,
        "solution_identity": solution.identity,
        "episode_id": episode_id,
        "source_id": reset_info.get("source_id"),
        "source_xml_sha256": reset_info.get("source_xml_sha256"),
        "source_closure_digest": reset_info.get("source_closure_digest"),
        "compiled_model_layout_v1": reset_info.get("compiled_model_layout_v1"),
        "pre_reset_compiled_validation_v1": dict(pre_reset),
        "reset_sample": reset_sample,
        "reset_realization": reset_realization,
        "reset_readback": reset_readback,
    }
    _write_json(episode_dir / "start_receipt.json", start_receipt)
    start_receipt_bytes = (episode_dir / "start_receipt.json").read_bytes()
    h5_path = episode_dir / "trajectory.h5"
    env.start_recording(h5_path)
    final_info = dict(reset_info)
    final_observation = reset_observation
    action_trace = []
    terminated = truncated = False
    try:
        for _ in range(max_steps):
            observation, reward, terminated, truncated, info = env.step_with_solution(solution)
            final_observation, final_info = observation, info
            action_trace.append({
                "solution_action": [float(value) for value in info.get("external_action", ())],
                "solution_stage": info.get("selected_solution_action_v1", {}).get("stage"),
                "solution_diagnostics": info.get("selected_solution_action_v1", {}).get("diagnostics"),
                "solution_action_receipt": info.get("last_action_receipt"),
                "reward": float(reward),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "control_step": int(info.get("control_step", -1)),
                "simulation_time_s": float(info.get("simulation_time_s", float("nan"))),
                "mixed_actuator_command_v1": info.get("mixed_actuator_command_v1"),
                "applied_mixed_actuator_command_v1": info.get("applied_mixed_actuator_command_v1"),
                "post_step_public_state": _state_observation_receipt(observation),
            })
            if terminated or truncated or solution.done or solution.failed:
                break
    except BaseException as exc:
        fault = getattr(env, "execution_fault", None)
        failure_receipt = {
            "schema_version": f"r07-v210-task-solution-failure-receipt-{version_suffix}",
            "episode_index": episode_index, "row_index": row_index, "seed": seed,
            "task_uid": env.artifact.task_id,
            "task_artifact_identity_hash": env.artifact.identity_hash,
            "solution_identity": solution.identity,
            "episode_id": episode_id,
            "source_id": reset_info.get("source_id"),
            "source_xml_sha256": reset_info.get("source_xml_sha256"),
            "source_closure_digest": reset_info.get("source_closure_digest"),
            "last_successful_control_step": int(final_info.get("control_step", -1)),
            "next_control_step_attempted": int(final_info.get("control_step", -1)) + 1,
            "last_successful_public_state": _state_observation_receipt(final_observation),
            "last_successful_public_boundary": {
                key: final_info.get(key) for key in (
                    "source_id", "source_closure_digest", "provider_materialization_id",
                    "episode_id", "reset_sample_id", "control_step", "simulation_time_s",
                    "state_revision",
                )
            },
            "solution": solution.outcome_report(),
            "completed_action_trace": action_trace,
            "execution_fault": fault.to_mapping() if hasattr(fault, "to_mapping") else None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
        _write_json(episode_dir / "failure_receipt.json", failure_receipt)
        raise
    if not action_trace:
        raise RuntimeError("task Solution produced no public action")
    episode_end = final_info.get("episode_end_v1")
    if not isinstance(episode_end, dict):
        episode_end = env.stop("bounded_solution_worker_complete").to_mapping()
    end_reason = episode_end.get("outcome", {}).get("end_reason")
    if type(end_reason) is not str or not end_reason:
        raise ValueError("task Solution episode omitted a typed end reason")
    finalized = env.finish_recording(end_reason)
    h5_path = Path(finalized["path"]).resolve(strict=True)
    h5_bytes = h5_path.read_bytes()
    progress = env.get_runtime_progress_receipt()
    transition_count = len(action_trace)
    if (progress.get("episode_id") != episode_id
            or progress.get("native_step_count") != transition_count * 25
            or progress.get("control_step") != transition_count):
        raise ValueError("public runtime progress differs from the task Solution action trace")
    initial_joints = np.asarray(reset_observation["state"]["joint_position"], dtype=np.float64)
    final_joints = np.asarray(final_observation["state"]["joint_position"], dtype=np.float64)
    initial_ee = np.asarray(reset_observation["state"]["ee_pose"], dtype=np.float64)
    final_ee = np.asarray(final_observation["state"]["ee_pose"], dtype=np.float64)
    return {
        "schema_version": f"r07-v210-task-solution-episode-{version_suffix}",
        "episode_index": episode_index,
        "row_index": row_index,
        "seed": seed,
        "episode_id": episode_id,
        "task_uid": env.artifact.task_id,
        "task_artifact_identity_hash": env.artifact.identity_hash,
        "solution_identity": solution.identity,
        "source_id": reset_info.get("source_id"),
        "source_xml_sha256": reset_info.get("source_xml_sha256"),
        "source_closure_digest": reset_info.get("source_closure_digest"),
        "compiled_model_layout_v1": reset_info.get("compiled_model_layout_v1"),
        "pre_reset_compiled_validation_v1": reset_info.get("pre_reset_compiled_validation_v1"),
        "start_receipt": {
            "relative_path": str((episode_dir / "start_receipt.json").relative_to(output_dir.resolve())),
            "bytes": len(start_receipt_bytes),
            "sha256": hashlib.sha256(start_receipt_bytes).hexdigest(),
            "receipt": start_receipt,
        },
        "reset_sample": reset_sample,
        "reset_realization": reset_realization,
        "reset_readback": reset_readback,
        "prior_session_close_receipt": previous_close,
        "control_plan": env.get_record_metadata()["control_plan"],
        "action_trace": action_trace,
        "task_success": bool(final_info.get("is_success", False)),
        "solution_completed": bool(solution.done),
        "solution_failed": bool(solution.failed),
        "solution_failure_reason": getattr(solution, "failure_reason", None),
        "gravity_compensation": (
            solution.gravity_compensation_receipt()
            if version_suffix == "v2"
            and callable(getattr(solution, "gravity_compensation_receipt", None)) else None
        ),
        "solution_schema_version": solution_schema,
        "action_schema_id": getattr(solution, "action_schema_id", None),
        "episode_end_v1": episode_end,
        "final_info": {
            "is_success": final_info.get("is_success"),
            "task_metrics": final_info.get("task_metrics"),
            "predicate_v1": final_info.get("predicate_v1"),
            "contact_summary_v2": final_info.get("contact_summary_v2"),
            "selected_policy_execution_complete": final_info.get("selected_policy_execution_complete"),
            "selected_policy_execution_failed": final_info.get("selected_policy_execution_failed"),
            "solution_stage": final_info.get("solution_stage"),
        },
        "motion_summary": _public_motion_metrics(initial_joints, final_joints, initial_ee, final_ee),
        "initial_observation": _state_observation_receipt(reset_observation),
        "final_observation": _state_observation_receipt(final_observation),
        "runtime_progress": progress,
        "physical_state_monitor": progress.get("physical_state_monitor"),
        "finalizer": finalized,
        "h5": {
            "relative_path": str(h5_path.relative_to(output_dir.resolve())),
            "bytes": len(h5_bytes),
            "sha256": hashlib.sha256(h5_bytes).hexdigest(),
            "schema_version": finalized.get("schema_version"),
            "transition_count": finalized.get("transition_count"),
            "observation_count": finalized.get("observation_count"),
            "episode_id": episode_id,
            "final_boundary": transition_count,
        },
    }


def _contact_endpoint_plan(base_sample: ResetSampleV1, *, positive: bool) -> ResetPlanV1:
    """Make an explicit diagnostic pose override without touching runtime state."""
    base_sample.validate()
    plate = base_sample.poses_world["plate_1"]
    offset = 0.0 if positive else 0.20
    height = 0.0 if positive else 0.05
    bowl_pose = PoseWorld(
        (plate.position[0] + offset, plate.position[1], plate.position[2] + height),
        plate.quaternion_wxyz,
    )
    values = base_sample.to_mapping()
    values["poses_world"] = {**base_sample.poses_world, "akita_black_bowl_1": bowl_pose}
    sample = ResetSampleV1.create(**values)
    plan = ResetPlanV1(
        schema_version="reset-plan-v1", reset_sample=sample,
        purpose="diagnostic_contact_endpoint",
    )
    plan.validate()
    return plan


def _source_on_predicate_oracle_v1(contact, bowl_pose, plate_pose) -> bool:
    """Independent transcription of the pinned object-object On rule."""
    dx = float(bowl_pose[0]) - float(plate_pose[0])
    dy = float(bowl_pose[1]) - float(plate_pose[1])
    return bool(
        int(contact["pair_counts"]["akita_black_bowl_1/plate_1"]) > 0
        and float(bowl_pose[2]) >= float(plate_pose[2])
        and (dx * dx + dy * dy) ** 0.5 < 0.03
    )


def _run_contact_endpoints(env, *, base_sample_mapping: dict) -> list[dict[str, Any]]:
    base_sample = ResetSampleV1.from_mapping(base_sample_mapping)
    endpoints = []
    for name, positive in (("negative", False), ("positive", True)):
        plan = _contact_endpoint_plan(base_sample, positive=positive)
        observation, info = env.reset(
            seed=plan.reset_sample.task_seed, options={"reset_plan_v1": plan},
        )
        contact = info.get("contact_summary_v2")
        predicate = info.get("predicate_v1", {}).get("on_bowl_plate")
        if not isinstance(contact, dict) or not isinstance(predicate, dict):
            raise ValueError("public ResetPlan endpoint omitted contact or On predicate evidence")
        poses = _state_observation_receipt(observation)["privileged_state"]
        bowl = poses["bowl_body_pose"]
        plate = poses["plate_body_pose"]
        source_value = _source_on_predicate_oracle_v1(contact, bowl, plate)
        if predicate.get("status") != "available" or predicate.get("value") is not source_value:
            raise ValueError("Core On predicate differs from independent source rule at ResetPlan endpoint")
        if source_value is not positive:
            raise ValueError(f"public diagnostic {name} ResetPlan endpoint did not realize its expected source predicate")
        endpoints.append({
            "endpoint": name,
            "reset_plan_v1": plan.to_mapping(),
            "reset_plan_identity_sha256": plan.identity_hash,
            "reset_plan_evidence_v1": info.get("reset_plan_evidence_v1"),
            "reset_readback_v1": info.get("reset_readback_v1"),
            "contact_summary_v2": contact,
            "core_predicate_v1": predicate,
            "source_predicate_oracle": {"schema_version": "libero-on-source-oracle-v1", "value": source_value},
            "public_observation": _state_observation_receipt(observation),
            "runtime_progress": env.get_runtime_progress_receipt(),
        })
    return endpoints


def run_libero_candidate_worker(env, *, output_dir: Path, seed: int = 19,
                                rows: tuple[int, ...] = (0, 1, 2), steps: int = 64,
                                solution_factory=None,
                                source_closure_files: Mapping[str, bytes] | None = None,
                                composition_plan_bytes: bytes | None = None,
                                source_raw_xml_bytes: bytes | None = None,
                                source_model_profile_bytes: bytes | None = None,
                                solution_resource_closer=None) -> dict[str, Any]:
    """Run same-instance public resets, action route, H5 closure and receipts."""
    output_dir = Path(output_dir).resolve()
    rows = tuple(rows)
    if (not rows or len(set(rows)) != len(rows)
            or any(type(row) is not int or row not in (0, 1, 2) for row in rows)
            or (solution_factory is None and rows != (0, 1, 2))
            or type(seed) is not int or seed != 19):
        raise ValueError("LIBERO worker freezes seed 19 and ordered unique source rows from (0,1,2)")
    maximum_steps = 1000 if solution_factory is not None else 64
    if type(steps) is not int or not 1 <= steps <= maximum_steps:
        raise ValueError(f"LIBERO worker supports 1..{maximum_steps} public outer steps per episode")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"worker output directory must be fresh and empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    episodes = []
    diagnostic_endpoints = []
    source_bundle = None
    worker_error = None
    close_error = None
    close_receipt = None
    solution_resource_close_error = None
    solution_resource_close_receipt = None
    try:
        if solution_factory is not None:
            if source_closure_files is None or not isinstance(composition_plan_bytes, bytes):
                raise ValueError("task Solution worker requires exact source closure files and composition-plan bytes")
            source_bundle = _write_solution_source_bundle(
                output_dir, source_closure_files=source_closure_files,
                composition_plan_bytes=composition_plan_bytes,
                raw_source_xml_bytes=source_raw_xml_bytes,
                model_profile_bytes=source_model_profile_bytes,
            )
        for index, row_index in enumerate(rows):
            if solution_factory is None:
                episodes.append(_episode_record(
                    env, output_dir=output_dir, episode_index=index,
                    row_index=row_index, seed=seed, steps=steps,
                ))
            else:
                episodes.append(_episode_solution_record(
                    env, output_dir=output_dir, episode_index=index, row_index=row_index,
                    seed=seed, max_steps=steps, solution_factory=solution_factory,
                ))
        if solution_factory is None:
            diagnostic_endpoints = _run_contact_endpoints(
                env, base_sample_mapping=episodes[-1]["reset_sample"],
            )
    except BaseException as exc:
        worker_error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        if callable(solution_resource_closer):
            try:
                solution_resource_close_receipt = solution_resource_closer()
            except BaseException as exc:
                solution_resource_close_error = {"type": type(exc).__name__, "message": str(exc)}
        try:
            env.close()
            close_receipt = env.close_receipt
        except BaseException as exc:
            close_error = {"type": type(exc).__name__, "message": str(exc)}
            try:
                close_receipt = env.close_receipt
            except BaseException:
                pass
    solution_route = solution_factory is not None
    attempted_episode_receipts = []
    failed_episode_receipts = []
    if solution_route:
        for start_path in sorted(output_dir.glob("episode_*_row_*/start_receipt.json")):
            raw_start = start_path.read_bytes()
            attempted_episode_receipts.append({
                "relative_path": str(start_path.relative_to(output_dir.resolve())),
                "bytes": len(raw_start),
                "sha256": hashlib.sha256(raw_start).hexdigest(),
                "receipt": json.loads(raw_start.decode("utf-8")),
            })
        for failure_path in sorted(output_dir.glob("episode_*_row_*/failure_receipt.json")):
            raw_failure = failure_path.read_bytes()
            failed_episode_receipts.append({
                "relative_path": str(failure_path.relative_to(output_dir.resolve())),
                "bytes": len(raw_failure),
                "sha256": hashlib.sha256(raw_failure).hexdigest(),
                "receipt": json.loads(raw_failure.decode("utf-8")),
            })
    payload = {
        "schema_version": (
            getattr(solution_factory, "worker_result_schema_version",
                    "r07-v210-task-solution-worker-result-v8") if solution_route
            else "r07c-d01-libero-worker-result-v1"
        ),
        "status": "complete" if (worker_error is None and close_error is None
                                  and solution_resource_close_error is None
                                  and len(episodes) == len(rows)
                                  and (solution_route or len(diagnostic_endpoints) == 2)) else "failed",
        "episode_count": len(episodes),
        "episode_rows": [int(item["row_index"]) for item in episodes],
        "run_scope": (
            "task1_final_rows_0_1_2" if solution_route and rows == (0, 1, 2)
            else "task1_bounded_probe" if solution_route
            else "diagnostic_full_rows_0_1_2"
        ),
        "transition_count": sum(int(item["h5"]["transition_count"] or 0) for item in episodes),
        "observation_count": sum(int(item["h5"]["observation_count"] or 0) for item in episodes),
        "native_step_count": sum(int(item["runtime_progress"]["native_step_count"]) for item in episodes),
        "episodes": episodes,
        "attempted_episode_receipts": attempted_episode_receipts if solution_route else None,
        "failed_episode_receipts": failed_episode_receipts if solution_route else None,
        "source_bundle": source_bundle,
        "diagnostic_endpoints": diagnostic_endpoints,
        "reset_count": len(episodes) + len(diagnostic_endpoints),
        "solution_coverage": {
            "task_success_episodes": sum(bool(item.get("task_success")) for item in episodes),
            "solution_completed_episodes": sum(bool(item.get("solution_completed")) for item in episodes),
            "failed_episodes": sum(bool(item.get("solution_failed")) for item in episodes),
        } if solution_route else None,
        "final_session_close_receipt": close_receipt,
        "solution_resource_close_receipt": solution_resource_close_receipt,
        "solution_resource_close_error": solution_resource_close_error,
        "worker_error": worker_error,
        "close_error": close_error,
        "worker_process_group_cleanup": "parent_must_confirm_after_worker_exit",
        "evidence_class": "synthetic_fixture" if any(
            item.get("reset_sample", {}).get("evidence_class") == "synthetic_fixture" for item in episodes
        ) else "runtime_candidate",
    }
    result = {**payload, "result_sha256": hashlib.sha256(_canonical(payload)).hexdigest()}
    _write_json(output_dir / "worker_result.json", result)
    return result
















__all__ = ["run_libero_candidate_worker"]
