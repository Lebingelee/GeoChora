"""Provider-free source composition and task predicate contract tests."""

import hashlib
import json
from pathlib import Path

import pytest

from bench_deploy.libero.evaluation import (
    ON_THRESHOLD_M, PILOT_TASK_UID, OnBowlPlateEvidenceV1,
    evaluate_on_bowl_plate_v1,
)
from bench_deploy.libero.assembly import build_source_composition_plan
from task_env.environment import ContactSummary

_MANIFEST_SHA = "4ad168e4710f3153d0f1f470389a506df27588e4d5ce1eaec450289807d30a75"


def _on_evidence(*, x=0.0, bowl_z=0.20, plate_z=0.10, contact=True, frame="world"):
    return OnBowlPlateEvidenceV1(
        task_uid=PILOT_TASK_UID,
        source_manifest_sha256=_MANIFEST_SHA,
        frame_id=frame,
        bowl_center_m=(x, 0.0, bowl_z),
        plate_center_m=(0.0, 0.0, plate_z),
        geom_group_contact=contact,
    )


def _on(evidence):
    return evaluate_on_bowl_plate_v1(
        evidence, expected_source_manifest_sha256=_MANIFEST_SHA
    )


def test_on_predicate_requires_contact_vertical_order_and_strict_xy_threshold():
    assert _on(_on_evidence()).value is True
    assert _on(_on_evidence(contact=False)).value is False
    assert _on(_on_evidence(bowl_z=0.09)).value is False
    assert _on(_on_evidence(x=ON_THRESHOLD_M)).value is False
    assert _on(_on_evidence(x=ON_THRESHOLD_M - 1.0e-6)).value is True


def test_missing_or_mismatched_public_on_evidence_is_unavailable_not_false():
    assert _on(None).status == "unavailable"
    assert _on(_on_evidence(contact=None)).status == "unavailable"
    assert _on(_on_evidence(frame="robot0")).status == "unavailable"
    mismatch = evaluate_on_bowl_plate_v1(
        _on_evidence(), expected_source_manifest_sha256="c" * 64
    )
    assert mismatch.status == "unavailable"


def test_unavailable_contact_summary_cannot_hide_counts_or_invalid_schema():
    with pytest.raises(ValueError, match="cannot carry contact counts"):
        ContactSummary(
            pair_counts={"bowl/plate": 1},
            status="unavailable",
            reason="provider_contact_pair_query_not_implemented",
        )
    with pytest.raises(ValueError, match="unsupported ContactSummary schema"):
        ContactSummary(schema_version="task-contact-summary-v0")


def test_source_composition_plan_is_deterministic_and_rejects_changed_install_bytes(tmp_path):
    install = tmp_path / "install"
    manifest = {
        "manifest_id": "libero-test-source-v1",
        "source_revisions": {"libero": "1" * 40, "robosuite": "2" * 40},
        "asset_closure": {
            "sha256": "c" * 64,
            "files": [
                {"path": "libero/assets/scene.xml", "size_bytes": 5},
                {"path": "libero/assets/bowl.xml", "size_bytes": 4},
            ],
        },
        "selected_xml_sources": [
            {"repository": "libero", "path": "libero/assets/scene.xml", "sha256": hashlib.sha256(b"scene").hexdigest()},
            {"repository": "libero", "path": "libero/assets/bowl.xml", "sha256": hashlib.sha256(b"bowl").hexdigest()},
        ],
        "source_code_references": [
            {"repository": "libero", "path": "libero/envs/problems/table.py", "sha256": hashlib.sha256(b"source").hexdigest()},
        ],
        "source_resolution": {"scene_style_properties": {"floor_style": "light-gray"}, "scene_style_rewrite_rules": []},
        "files": [
            {"repository": "libero", "path": "libero/assets/scene.xml", "install_path": "upstream/libero/libero/assets/scene.xml", "sha256": hashlib.sha256(b"scene").hexdigest(), "size_bytes": 5},
            {"repository": "libero", "path": "libero/assets/bowl.xml", "install_path": "upstream/libero/libero/assets/bowl.xml", "sha256": hashlib.sha256(b"bowl").hexdigest(), "size_bytes": 4},
            {"repository": "libero", "path": "libero/envs/problems/table.py", "install_path": "upstream/libero/libero/envs/problems/table.py", "sha256": hashlib.sha256(b"source").hexdigest(), "size_bytes": 6},
        ],
        "task": {
            "task_uid": PILOT_TASK_UID,
            "type_to_source_and_xml": {
                "bowl_type": {"asset_source": "libero/assets/bowl.xml", "class": "Bowl", "class_source": "libero/envs/problems/table.py"},
            },
            "objects_instance_to_type": {"bowl_1": "bowl_type"},
            "fixtures_instance_to_type": {"table_1": "bowl_type"},
        },
    }
    for row in manifest["files"]:
        target = install / row["install_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes({
            "upstream/libero/libero/assets/scene.xml": b"scene",
            "upstream/libero/libero/assets/bowl.xml": b"bowl",
            "upstream/libero/libero/envs/problems/table.py": b"source",
        }[row["install_path"]])
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    task_input = {
        "schema_version": "libero-pilot-deployment-input-v1",
        "task_uid": PILOT_TASK_UID,
        "source_manifest_sha256": manifest_sha,
        "native_reference": {"active_scene_xml": {
            "repository": "libero", "path": "libero/assets/scene.xml",
            "sha256": hashlib.sha256(b"scene").hexdigest(),
        }},
    }
    task_input_bytes = json.dumps(task_input, sort_keys=True, separators=(",", ":")).encode()
    receipt = {
        "schema_version": "libero-pilot-source-verify-receipt-v1",
        "status": "VERIFIED_INDEPENDENT_REREAD",
        "manifest_sha256": manifest_sha,
        "manifest_id": manifest["manifest_id"],
        "asset_closure_sha256": "c" * 64,
        "task_uid": PILOT_TASK_UID,
        "file_count": 3,
        "asset_file_count": 2,
        "asset_bytes": 9,
        "total_bytes": 15,
        "payload_files": [
            {
                "install_path": row["install_path"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
            }
            for row in manifest["files"]
        ],
    }
    receipt["result_sha256"] = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    first = build_source_composition_plan(
        task_input, manifest, task_input_bytes=task_input_bytes,
        manifest_bytes=manifest_bytes, install_root=install,
        verification_receipt=receipt, compose_mjcf=False,
    )
    second = build_source_composition_plan(
        task_input, manifest, task_input_bytes=task_input_bytes,
        manifest_bytes=manifest_bytes, install_root=install,
        verification_receipt=receipt, compose_mjcf=False,
    )
    assert first["composition_plan_sha256"] == second["composition_plan_sha256"]
    assert first["output"]["composed_mjcf_sha256"] is None
    assert first["core_seam"]["runtime_admission"] == "checked by the selected diagnostic candidate before reset"
    assert first["core_seam"]["formal_qualification"] == "NOT_GRANTED"
    assert len(first["ordered_upstream_composition"][2]["semantic_name_mapping"]) == 2

    forged_receipt = dict(receipt)
    forged_receipt["file_count"] = 4
    forged_unsigned = dict(forged_receipt)
    forged_unsigned.pop("result_sha256")
    forged_receipt["result_sha256"] = hashlib.sha256(
        json.dumps(forged_unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="payload/count facts disagree"):
        build_source_composition_plan(
            task_input, manifest, task_input_bytes=task_input_bytes,
            manifest_bytes=manifest_bytes, install_root=install,
            verification_receipt=forged_receipt, compose_mjcf=False,
        )

    (install / "upstream/libero/libero/assets/bowl.xml").write_bytes(b"bowl changed")
    with pytest.raises(ValueError, match="installed source bytes differ"):
        build_source_composition_plan(
            task_input, manifest, task_input_bytes=task_input_bytes,
            manifest_bytes=manifest_bytes, install_root=install,
            verification_receipt=receipt, compose_mjcf=False,
        )


def test_static_mjcf_composition_namespaces_instances_and_binds_exact_output_hash(tmp_path):
    from bench_deploy.libero.assembly import build_source_composition_plan

    install = tmp_path / "install"
    table_geoms = (
        '<geom name="table_collision" type="box" size=".4 .4 .025"/>'
        '<geom name="table_visual" type="box" size=".4 .4 .025"/>'
        '<site name="table_top"/>'
        + "".join(f'<geom name="table_leg{i}_visual" type="cylinder" size=".025 .1"/>' for i in range(1, 5))
    )
    sources = {
        ("libero", "libero/libero/assets/scenes/arena.xml"): (
            '<mujoco model="arena"><worldbody><body name="table">' + table_geoms
            + '</body></worldbody></mujoco>'
        ).encode(),
        ("libero", "libero/libero/assets/objects/bowl.xml"): b'<mujoco model="bowl"><worldbody><body name="wrapper"><body name="object"><geom name="bowl_geom" group="0" type="sphere" size=".03"/></body></body></worldbody></mujoco>',
        ("libero", "libero/libero/bddl_files/test.bddl"): b'(:fixtures main_table - table) (:objects bowl_1 bowl_2 - bowl)',
        ("robosuite", "robosuite/models/assets/robots/panda/robot.xml"): (
            b'<mujoco model="panda"><worldbody><body name="base"><body name="right_hand"/></body></worldbody><actuator>'
            + b"".join(f'<motor name="torq_j{i}" joint="joint{i}" ctrlrange="-80 80"/>'.encode() for i in range(1, 8))
            + b'</actuator></mujoco>'
        ),
        ("robosuite", "robosuite/models/assets/mounts/rethink_mount.xml"): b'<mujoco model="mount"><worldbody><body name="base"/></worldbody></mujoco>',
        ("robosuite", "robosuite/models/assets/grippers/panda_gripper.xml"): (
            b'<mujoco model="gripper"><worldbody><body name="right_gripper"><site name="grip_site"/><body name="eef">'
            b'<body name="leftfinger"><joint name="finger_joint1" type="slide"/></body>'
            b'<body name="rightfinger"><joint name="finger_joint2" type="slide"/></body>'
            b'</body></body></worldbody><actuator>'
            b'<position name="gripper_finger_joint1" joint="finger_joint1" ctrlrange="0 .04"/>'
            b'<position name="gripper_finger_joint2" joint="finger_joint2" ctrlrange="-.04 0"/>'
            b'</actuator></mujoco>'
        ),
    }
    file_rows = []
    for (repository, source_path), data in sources.items():
        install_path = f"upstream/{repository}/{source_path}"
        target = install / install_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        file_rows.append({
            "repository": repository,
            "source_path": source_path,
            "install_path": install_path,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        })
    selected = [
        {"repository": repo, "path": path, "sha256": hashlib.sha256(data).hexdigest()}
        for (repo, path), data in sources.items()
    ]
    manifest = {
        "manifest_id": "r07c-composition-test-v1",
        "source_revisions": {"libero": "1" * 40, "robosuite": "2" * 40},
        "asset_closure": {"sha256": "c" * 64, "files": []},
        "selected_xml_sources": selected,
        "source_code_references": [],
        "source_resolution": {"scene_style_properties": {}, "scene_style_rewrite_rules": []},
        "files": file_rows,
        "task": {
            "task_uid": PILOT_TASK_UID,
            "type_to_source_and_xml": {
                "bowl": {"asset_source": "libero/libero/assets/objects/bowl.xml", "class": "Bowl"},
                "table": {"owner_source": "libero/libero/envs/arenas/table_arena.py", "class": None, "xml_source": "robosuite/models/assets/arenas/table_arena.xml"},
            },
            "objects_instance_to_type": {"bowl_1": "bowl", "bowl_2": "bowl"},
            "fixtures_instance_to_type": {"main_table": "table"},
        },
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    task_input = {
        "schema_version": "libero-pilot-deployment-input-v1",
        "task_uid": PILOT_TASK_UID,
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "native_reference": {
            "active_scene_xml": {
                "repository": "libero", "path": "libero/libero/assets/scenes/arena.xml",
                "sha256": hashlib.sha256(sources[("libero", "libero/libero/assets/scenes/arena.xml")]).hexdigest(),
            },
            "robot": {"actuators": [{"name": f"torq_j{i}"} for i in range(1, 8)]},
        },
        "bddl": {
            "path": "libero/libero/bddl_files/test.bddl",
            "sha256": hashlib.sha256(sources[("libero", "libero/libero/bddl_files/test.bddl")]).hexdigest(),
        },
    }
    task_input_bytes = json.dumps(task_input, sort_keys=True, separators=(",", ":")).encode()
    unsigned_receipt = {
        "schema_version": "libero-pilot-source-verify-receipt-v1",
        "status": "VERIFIED_INDEPENDENT_REREAD",
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest_id": manifest["manifest_id"],
        "asset_closure_sha256": "c" * 64,
        "task_uid": PILOT_TASK_UID,
        "file_count": len(file_rows),
        "asset_file_count": 0,
        "asset_bytes": 0,
        "total_bytes": sum(row["size_bytes"] for row in file_rows),
        "payload_files": [
            {key: row[key] for key in ("install_path", "sha256", "size_bytes")}
            for row in file_rows
        ],
    }
    verification = dict(unsigned_receipt)
    verification["result_sha256"] = hashlib.sha256(
        json.dumps(unsigned_receipt, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    first = build_source_composition_plan(
        task_input, manifest,
        task_input_bytes=task_input_bytes,
        manifest_bytes=manifest_bytes,
        install_root=install,
        verification_receipt=verification,
    )
    second = build_source_composition_plan(
        task_input, manifest,
        task_input_bytes=task_input_bytes,
        manifest_bytes=manifest_bytes,
        install_root=install,
        verification_receipt=verification,
    )
    xml = first["mjcf_xml"]
    assert xml == second["mjcf_xml"]
    assert first["output"]["composed_mjcf_sha256"] == hashlib.sha256(xml.encode()).hexdigest()
    assert first["composition_receipt"]["semantic_body_map"] == {
        "bowl_1": "bowl_1_main", "bowl_2": "bowl_2_main", "main_table": "main_table",
    }
    assert 'name="bowl_1_main"' in xml and 'name="bowl_2_main"' in xml
    assert 'name="bowl_1_joint0" type="free" damping="0.0005"' in xml
    assert 'name="bowl_2_joint0" type="free" damping="0.0005"' in xml
    assert 'name="mount0_base"' in xml and 'name="robot0_base"' in xml
    assert 'name="gripper0_gripper_finger_joint1"' in xml
    assert xml.count('type="free"') == 2
    assert first["composition_receipt"]["movable_object_instances"][0]["semantic_id"] == "bowl_1"
    assert first["core_seam"]["compiled_scene_xml_sha256"] == first["output"]["composed_mjcf_sha256"]
