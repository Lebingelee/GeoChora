"""Provider-free S1 contracts for the unqualified LIBERO pilot candidates."""

from __future__ import annotations

from types import SimpleNamespace
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from bench_deploy.libero.evaluation import (
    ON_THRESHOLD_M,
    PILOT_TASK_UID,
    OnBowlPlateEvidenceV1,
    evaluate_on_bowl_plate_v1,
)
from bench_deploy.libero.assembly import build_source_composition_plan
from bench_deploy.libero.task import (
    LiberoPilotControlHookV1,
    PILOT_ACTIVE_SCENE_XML_SHA256,
    PILOT_SOURCE_ID,
)
from task_env.assembly import AgentReferences, SceneNameTable, TaskReferences, resolve_task_references
from task_env.environment import ReferenceSpec
from task_env.environment.task_definition import TaskDefinitionBase
from task_env.controllers.mounted_panda_mixed import MountedPandaServoConfigV1
from task_env.environment import (
    ActionModeSpec,
    ContactSummary,
    EpisodePhysicsState,
    RuntimeSnapshot,
    SnapshotRequest,
    TaskEvaluationContextV1,
)
from task_env.environment.env import BaseTaskEnv
from task_env.runtime.boundary import GeoPhysRuntimeBoundary


_JOINTS = tuple(
    f"robot0_joint{index}" for index in range(1, 8)
) + ("robot0_finger_joint1", "robot0_finger_joint2")
_ACTUATORS = tuple(
    f"robot0_torq_j{index}" for index in range(1, 8)
) + ("robot0_gripper_finger_joint1", "robot0_gripper_finger_joint2")
_CTRL_RANGE = np.asarray(
    [(-80.0, 80.0)] * 5 + [(-12.0, 12.0)] * 2 + [(0.0, 0.04), (-0.04, 0.0)],
    dtype=np.float32,
)
_MANIFEST_SHA = "4ad168e4710f3153d0f1f470389a506df27588e4d5ce1eaec450289807d30a75"


def _references(*, joints=_JOINTS, actuators=_ACTUATORS, ctrl_range=_CTRL_RANGE):
    joint_ids = np.arange(9, dtype=np.int32)
    actuator_ids = np.arange(9, dtype=np.int32)
    agent = AgentReferences(
        uid="libero-mounted-panda-v1",
        arm_joint_ids=joint_ids,
        arm_qpos_ids=joint_ids,
        arm_dof_ids=joint_ids,
        arm_actuator_ids=actuator_ids,
        gripper_joint_ids=np.empty(0, dtype=np.int32),
        gripper_qpos_ids=np.empty(0, dtype=np.int32),
        gripper_actuator_ids=np.empty(0, dtype=np.int32),
        eef_site_id=0,
        hand_body_id=0,
        ctrl_range=ctrl_range,
        joint_names=tuple(joints),
        actuator_names=tuple(actuators),
    )
    return TaskReferences(
        names=SceneNameTable(
            bodies={},
            joints={name: index for index, name in enumerate(joints)},
            sites={},
            geoms={},
            actuators={name: index for index, name in enumerate(actuators)},
        ),
        agents={agent.uid: agent},
        objects={},
    )


def _hook(*, kp=100.0, kd=0.0):
    return LiberoPilotControlHookV1(
        source_id=PILOT_SOURCE_ID,
        source_xml_sha256=PILOT_ACTIVE_SCENE_XML_SHA256,
        agent_uid="libero-mounted-panda-v1",
        servo_config=MountedPandaServoConfigV1(
            kp_Nm_per_rad=(kp,) * 7,
            kd_Nm_s_per_rad=(kd,) * 7,
            gain_status="synthetic_s1_fixture",
        ),
    )


def _snapshot(qpos=None, qvel=None, ctrl=None):
    return RuntimeSnapshot(
        qpos=np.zeros(9, dtype=np.float32) if qpos is None else qpos,
        qvel=np.zeros(9, dtype=np.float32) if qvel is None else qvel,
        ctrl=np.zeros(9, dtype=np.float32) if ctrl is None else ctrl,
    )


def _action():
    return np.asarray([-0.17, 0.0, 0.0, -1.5, 0.0, 1.5, -0.7, 0.04])


def _resolved_references():
    """Use the real name resolver over a provider-free compiled-scene fixture."""
    body_names = tuple(f"robot0_link{index}" for index in range(9))
    links = [
        SimpleNamespace(
            name=body_name,
            joints=[SimpleNamespace(name=joint_name)],
            sites=[SimpleNamespace(name="robot0_eef")] if index == 8 else [],
        )
        for index, (body_name, joint_name) in enumerate(zip(body_names, _JOINTS, strict=True))
    ]
    articulation = SimpleNamespace(
        links=links,
        actuators=[SimpleNamespace(name=name) for name in _ACTUATORS],
    )
    loader_result = SimpleNamespace(articulation=articulation)
    scene_model = SimpleNamespace(joint_data={
        "geom_names": [],
        "jnt_qposadr": np.arange(9, dtype=np.int32),
        "jnt_dofadr": np.arange(9, dtype=np.int32),
        "actuator_ctrlrange": _CTRL_RANGE,
    })

    class Scene:
        uid = "libero-pilot-candidate-scene"

        def reference_spec(self):
            return ReferenceSpec()

    class Agent:
        uid = "libero-mounted-panda-v1"

        def reference_spec(self):
            return ReferenceSpec(
                body_names=body_names,
                joint_names=_JOINTS,
                site_names=("robot0_eef",),
                actuator_names=_ACTUATORS,
            )

        def reference_layout(self):
            return {"base_body_name": body_names[0], "eef_site_name": "robot0_eef"}

    return resolve_task_references(
        loader_result=loader_result,
        scene_model=scene_model,
        scene=Scene(),
        agents=(Agent(),),
        objects=(),
    )


def test_taskdefinition_hook_resolves_real_task_references_and_emits_mixed_control():
    references = _references()
    adapter = _hook(kp=1.0, kd=0.1).create_action_adapter(SimpleNamespace(references=references))
    snapshot = _snapshot()
    adapter.reset(snapshot)
    command = adapter.convert(_action(), snapshot)

    assert command.mode == "libero_mounted_panda_mixed_torque_position_v1"
    assert command.actuator_ctrl.shape == (9,)
    assert command.actuator_ctrl[7] == pytest.approx(0.02)
    assert command.actuator_ctrl[8] == pytest.approx(-0.02)
    assert command.requested_action.shape == (8,)
    assert command.action_clipped is False
    assert isinstance(adapter.action_contract, ActionModeSpec)
    assert adapter.action_profile["provider_admission"] == "NOT_ADMITTED"
    assert adapter.action_profile["timebase"] == {
        "control_period_s": 0.05,
        "physics_dt_s": 0.002,
        "substeps": 25,
    }


def test_taskdefinition_and_core_action_boundary_reach_fake_native_io_and_close_fault():
    class CandidateTaskDefinition(LiberoPilotControlHookV1):
        pass

    assert isinstance(_hook(), TaskDefinitionBase)
    references = _resolved_references()
    definition = CandidateTaskDefinition(
        source_id=PILOT_SOURCE_ID,
        source_xml_sha256=PILOT_ACTIVE_SCENE_XML_SHA256,
        agent_uid="libero-mounted-panda-v1",
        servo_config=MountedPandaServoConfigV1(
            kp_Nm_per_rad=(1.0,) * 7,
            kd_Nm_s_per_rad=(0.1,) * 7,
            gain_status="synthetic_s1_fixture",
        ),
    )
    adapter = definition.create_action_adapter(SimpleNamespace(references=references))
    core_env = SimpleNamespace(
        _robot=None,
        _action_adapter=adapter,
        config=SimpleNamespace(agents=SimpleNamespace(agent_uids=("libero-mounted-panda-v1",))),
    )
    command = BaseTaskEnv._convert_action(core_env, _action(), _snapshot())

    class FakePhysicsIO:
        n_actuators = 9

        def __init__(self):
            self.ctrl = None
            self.fail_write = False

        def write_ctrl(self, values):
            if self.fail_write:
                raise RuntimeError("synthetic ctrl write fault")
            self.ctrl = np.asarray(values).copy()

    physics = FakePhysicsIO()
    boundary = object.__new__(GeoPhysRuntimeBoundary)
    boundary._physics = physics
    boundary._ctrl_range = _CTRL_RANGE
    applied = boundary.apply_control(command)
    assert np.array_equal(physics.ctrl, command.actuator_ctrl)
    assert np.array_equal(applied.applied_ctrl, command.actuator_ctrl)
    assert applied.clipped is False

    physics.fail_write = True
    with pytest.raises(RuntimeError, match="synthetic ctrl write fault"):
        boundary.apply_control(command)

    class CloseFault:
        def __init__(self):
            self.calls = 0

        def close(self):
            self.calls += 1
            raise RuntimeError("synthetic close fault")

    closer = CloseFault()
    close_env = object.__new__(BaseTaskEnv)
    close_env._closed = False
    close_env._ui_render_provider = None
    close_env._sensor_provider = None
    close_env._task_lifecycle = None
    close_env._runtime = closer
    close_env._runtime_assembly = object()
    with pytest.raises(RuntimeError, match="synthetic close fault"):
        BaseTaskEnv.close(close_env)
    assert close_env._closed is True
    BaseTaskEnv.close(close_env)
    assert closer.calls == 1


def test_torque_limits_are_clamped_and_reported_as_clipping():
    adapter = _hook(kp=100.0).create_action_adapter(
        SimpleNamespace(references=_references())
    )
    qpos = np.zeros(9, dtype=np.float64)
    qpos[0] = -2.8
    snapshot = _snapshot(qpos=qpos)
    command = adapter.convert(np.asarray([2.8, 0, 0, -1.5, 0, 1.5, -0.7, 0.04]), snapshot)
    assert command.actuator_ctrl[0] == pytest.approx(80.0)
    assert command.action_clipped is True


@pytest.mark.parametrize(
    "references",
    [
        _references(joints=(_JOINTS[1], _JOINTS[0], *_JOINTS[2:])),
        _references(joints=_JOINTS[:-1]),
        _references(joints=(*_JOINTS[:-1], _JOINTS[0])),
        _references(actuators=(_ACTUATORS[1], _ACTUATORS[0], *_ACTUATORS[2:])),
        _references(actuators=_ACTUATORS[:-1]),
        _references(actuators=(*_ACTUATORS[:-1], _ACTUATORS[0])),
        _references(ctrl_range=np.asarray([(-1.0, 1.0)] * 9, dtype=np.float32)),
    ],
)
def test_wrong_order_or_wrong_source_range_fails_before_adapter_creation(references):
    with pytest.raises(ValueError):
        _hook().create_action_adapter(SimpleNamespace(references=references))


@pytest.mark.parametrize(
    "action",
    [
        np.asarray([0.0] * 7 + [np.nan]),
        np.asarray([3.0, 0, 0, -1.5, 0, 1.5, -0.7, 0.04]),
        np.asarray([-0.17, 0, 0, -1.5, 0, 1.5, -0.7, 0.081]),
        np.asarray([False] * 8),
    ],
)
def test_nonfinite_wrong_units_or_out_of_range_action_is_rejected(action):
    adapter = _hook().create_action_adapter(SimpleNamespace(references=_references()))
    with pytest.raises((TypeError, ValueError)):
        adapter.convert(action, _snapshot())


@pytest.mark.parametrize(
    "snapshot",
    [
        _snapshot(qpos=np.zeros(8, dtype=np.float32)),
        _snapshot(qvel=np.zeros(8, dtype=np.float32)),
        _snapshot(qpos=np.asarray([0.0] * 8 + [np.inf], dtype=np.float32)),
    ],
)
def test_short_or_nonfinite_public_joint_state_is_rejected(snapshot):
    adapter = _hook().create_action_adapter(SimpleNamespace(references=_references()))
    with pytest.raises(ValueError):
        adapter.convert(_action(), snapshot)


def test_candidate_gains_must_be_explicit_real_values_and_native_timebase():
    with pytest.raises(ValueError, match="20 Hz / 2 ms"):
        MountedPandaServoConfigV1(
            kp_Nm_per_rad=(1.0,) * 7,
            kd_Nm_s_per_rad=(0.1,) * 7,
            control_period_s=0.01,
            physics_dt_s=0.002,
        )
    with pytest.raises(TypeError, match="real numbers"):
        MountedPandaServoConfigV1(
            kp_Nm_per_rad=(True,) * 7,
            kd_Nm_s_per_rad=(0.1,) * 7,
        )


def test_wrong_source_or_malformed_composed_mjcf_hash_is_rejected_before_binding():
    with pytest.raises(ValueError, match="frozen pilot manifest"):
        LiberoPilotControlHookV1(
            source_id="libero-pilot-candidate:" + "0" * 64,
            source_xml_sha256=PILOT_ACTIVE_SCENE_XML_SHA256,
            agent_uid="libero-mounted-panda-v1",
            servo_config=MountedPandaServoConfigV1(
                kp_Nm_per_rad=(1.0,) * 7,
                kd_Nm_s_per_rad=(0.1,) * 7,
            ),
        )
    with pytest.raises(ValueError, match="composed MJCF identity"):
        LiberoPilotControlHookV1(
            source_id=PILOT_SOURCE_ID,
            source_xml_sha256="0" * 63,
            agent_uid="libero-mounted-panda-v1",
            servo_config=MountedPandaServoConfigV1(
                kp_Nm_per_rad=(1.0,) * 7,
                kd_Nm_s_per_rad=(0.1,) * 7,
            ),
        )


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


def test_contact_summary_and_task_state_context_preserve_unavailable_status():
    summary = ContactSummary.unavailable("provider_contact_pair_query_not_implemented")
    snapshot = RuntimeSnapshot(
        qpos=np.zeros(1), qvel=np.zeros(1), contact_summary=summary
    )
    context = TaskEvaluationContextV1(state=snapshot)
    assert context.state.contact_summary.status == "unavailable"
    predicate_evaluation = _hook().evaluate_predicates(context)
    assert predicate_evaluation.evaluator_status == "available"
    assert predicate_evaluation.predicates["on_bowl_plate"].status == "unavailable"
    assert predicate_evaluation.predicates["on_bowl_plate"].reason == summary.reason
    request = BaseTaskEnv._snapshot_request(
        SimpleNamespace(_robot=None, _task_definition=SimpleNamespace(requires_contact_summary=True))
    )
    assert request.contact_summary is True


def test_runtime_boundary_reports_unimplemented_contact_query_as_unavailable():
    class ProviderFreeBoundaryDouble:
        n_qpos = n_dof = n_actuators = n_sites = 0

        def snapshot(self):
            return {}

        def restore(self, _state):
            return None

        def synchronize_kinematic_state(self, *, update_site_jacobians):
            assert update_site_jacobians is False

    empty = np.empty(0, dtype=np.float32)
    initial = EpisodePhysicsState(qpos=empty, qvel=empty, qacc=empty, ctrl=empty, act=empty)
    boundary = GeoPhysRuntimeBoundary(
        physics=ProviderFreeBoundaryDouble(),
        scheduler=None,
        physics_dt=0.002,
        ctrl_range=np.empty((0, 2), dtype=np.float32),
        initial_state=initial,
    )
    snapshot = boundary.read_snapshot(
        SnapshotRequest(qacc=False, ctrl=False, body_pose=False, site_pose=False, contact_summary=True)
    )
    assert snapshot.contact_summary.status == "unavailable"
    assert snapshot.contact_summary.reason == "provider_contact_pair_query_not_implemented"


def test_runtime_boundary_consumes_only_typed_public_contact_query():
    class PublicContactReader:
        n_qpos = n_dof = n_actuators = n_sites = 0

        def __init__(self, result):
            self.result = result

        def snapshot(self):
            return {}

        def restore(self, _state):
            return None

        def synchronize_kinematic_state(self, *, update_site_jacobians):
            assert update_site_jacobians is False

        def read_contact_summary(self):
            return self.result

    empty = np.empty(0, dtype=np.float32)
    initial = EpisodePhysicsState(qpos=empty, qvel=empty, qacc=empty, ctrl=empty, act=empty)
    boundary = GeoPhysRuntimeBoundary(
        physics=PublicContactReader(ContactSummary.available({"bowl/plate": 2})),
        scheduler=None,
        physics_dt=0.002,
        ctrl_range=np.empty((0, 2), dtype=np.float32),
        initial_state=initial,
    )
    snapshot = boundary.read_snapshot(
        SnapshotRequest(qacc=False, ctrl=False, body_pose=False, site_pose=False, contact_summary=True)
    )
    assert snapshot.contact_summary.status == "available"
    assert dict(snapshot.contact_summary.pair_counts) == {"bowl/plate": 2}

    boundary = GeoPhysRuntimeBoundary(
        physics=PublicContactReader({"bowl/plate": 2}),
        scheduler=None,
        physics_dt=0.002,
        ctrl_range=np.empty((0, 2), dtype=np.float32),
        initial_state=initial,
    )
    with pytest.raises(TypeError, match="must return ContactSummary"):
        boundary.read_snapshot(
            SnapshotRequest(qacc=False, ctrl=False, body_pose=False, site_pose=False, contact_summary=True)
        )


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
    assert first["core_seam"]["core_native_admission_ready"] is False
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
    sources = {
        ("libero", "libero/libero/assets/scenes/arena.xml"): b'<mujoco model="arena"><worldbody><body name="table"/></worldbody></mujoco>',
        ("libero", "libero/libero/assets/objects/bowl.xml"): b'<mujoco model="bowl"><worldbody><body name="object"><freejoint/><geom name="bowl_geom" type="sphere" size=".03"/></body></worldbody></mujoco>',
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
        "bowl_1": "bowl_1", "bowl_2": "bowl_2", "main_table": "main_table",
    }
    assert 'name="bowl_1"' in xml and 'name="bowl_2"' in xml
    assert 'name="mount__base"' in xml and 'name="panda_base"' in xml
    assert 'name="gripper_finger_joint1"' in xml
    assert first["core_seam"]["compiled_scene_xml_sha256"] == first["output"]["composed_mjcf_sha256"]
