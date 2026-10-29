"""Provider-free F03 gates for typed free-body state and pre-read validation."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.artifacts import (
    ActionIntent,
    ArticulationDefinition,
    AssetDefinition,
    CanonicalStateView,
    CameraRendererOverrideV1,
    EntityDefinition,
    EntityInstance,
    ExecutionSpec,
    ExecutionSpecV1,
    FrameDefinition,
    FrameReference,
    JointDefinition,
    InitializationContract,
    PoseWorld,
    RendererSelectionV1,
    RequiredCapabilitySet,
    SceneDefinition,
    SemanticDefinition,
    StateFieldRequirement,
    StateRequirements,
    TaskArtifact,
    Timebase,
    WorldDefinition,
    decode_execution_spec,
)
from task_env.assembly.source import TaskSceneSource
from task_env.assembly.source import UsdTaskSceneSourceV1
from task_env.assembly.usd_delivery import load_usd_asset_delivery, resolve_provider_representation
from task_env.runtime.sessions.common import _SessionValues
from task_env.runtime.sessions.free_joint_state import (
    PublicRigidBodyReadbackV1,
    body_origin_local_twist_to_world_com,
    world_com_twist_to_body_origin_local,
)
from task_env.runtime.sessions.leaf_control import compile_isaac_named_position_drive_receipt_v1
from task_env.runtime.sessions.source import UsdRuntimeSourceV1
from task_env.artifacts.execution import legacy_execution_projection


def _scene():
    joint = JointDefinition(
        "joint-definition-v1", "free_root",
        FrameReference("cube-v1", "anchor"), FrameReference("cube-v1", "root"),
        PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
        PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
        "floating", None, "xyz_meter_quaternion_wxyz",
        "linear_xyz_meter_per_second_angular_xyz_radian_per_second", 7, 6,
    )
    return SceneDefinition(
        "scene-definition-v2", "f03-free-body-state",
        (AssetDefinition("asset-definition-v1", "f03-cube", "v1", "synthetic://f03/cube"),),
        (EntityInstance("entity-instance-v1", "cube-v1", "f03-cube", "v1"),),
        (
            FrameDefinition("frame-definition-v1", "cube-v1", "anchor", "runtime", None, None),
            FrameDefinition("frame-definition-v1", "cube-v1", "root", "runtime", None, None),
        ),
        (ArticulationDefinition(
            "articulation-definition-v1", "cube-v1", "anchor", ("anchor", "root"), (joint,),
        ),),
    ), joint


def _requirements():
    return StateRequirements(
        "state-requirements-v1", "task", "f03-free-body",
        (
            StateFieldRequirement(
                "state-field-requirement-v1", "joint_position", "joint", "cube-v1", "free_root",
                "required", "evaluation_boundary", "joint-definition", "joint_state_query",
            ),
            StateFieldRequirement(
                "state-field-requirement-v1", "joint_velocity", "joint", "cube-v1", "free_root",
                "required", "evaluation_boundary", "joint-definition", "joint_state_query",
            ),
            StateFieldRequirement(
                "state-field-requirement-v1", "frame_pose_world", "frame", "cube-v1", "root",
                "required", "evaluation_boundary", "meter+quaternion_wxyz", "frame_pose_query",
            ),
        ),
    )


class _CountingSession(_SessionValues):
    def _snapshot_with_native_free_joints(self):
        self.native_reads += 1
        return self.native_state, self.native_free


def _session(scene, joint, *, native_value):
    session = object.__new__(_CountingSession)
    session._closed = False
    session._reset_done = True
    session._reset_plan_gate_required = False
    session._reset_plan_gate_open = True
    session._episode_id = "episode-f03-synthetic"
    session._reset_sample_id = "reset-" + "a" * 64
    session._scene_instance_id = "scene-instance-f03"
    session._provider_materialization_id = "synthetic-materialization-f03"
    session._provider = "synthetic_fixture"
    session._control_step = 0
    session._state_revision = 0
    session.native_reads = 0
    session.native_state = CanonicalStateView(
        "canonical-state-v0", "SI_right_handed_z_up_wxyz", 0, 0.0,
        {}, {}, {"cube-v1": PoseWorld((1.0, 2.0, 3.0), (0.7071067811865476, 0.0, 0.0, 0.7071067811865476))},
    )
    session.native_free = {"cube-v1": native_value}
    session._source = SimpleNamespace(
        scene_definition=scene,
        scene_source=TaskSceneSource("<mujoco/>", Path("."), f"{scene.schema_version}:{scene.identity_hash}"),
        joints={}, bodies={"cube-v1": "cube"}, frames={},
        free_joints={"cube-v1": "cube_free"},
    )
    return session


def _readback():
    return PublicRigidBodyReadbackV1(
        "public-rigid-body-readback-v1", FrameReference("cube-v1", "root"),
        (1.0, 2.0, 3.0),
        (0.7071067811865476, 0.0, 0.0, 0.7071067811865476),
        (0.2, -0.1, 0.3), (0.3, -0.4, 0.7), (0.6, 0.5, -0.2),
        "world", "center_of_mass",
    )


def test_world_com_twist_conversion_roundtrips_nonidentity_pose_and_com_offset():
    value = _readback()
    value.validate()
    local_linear, local_angular = world_com_twist_to_body_origin_local(
        position_world_m=value.position_world_m,
        orientation_world_from_body_wxyz=value.orientation_world_from_body_wxyz,
        com_offset_body_m=value.com_offset_body_m,
        linear_velocity_world_at_com_m_s=value.linear_velocity_world_at_com_m_s,
        angular_velocity_world_rad_s=value.angular_velocity_world_rad_s,
        velocity_frame=value.velocity_frame,
        linear_reference_point=value.linear_reference_point,
    )
    world_linear, world_angular = body_origin_local_twist_to_world_com(
        position_world_m=value.position_world_m,
        orientation_world_from_body_wxyz=value.orientation_world_from_body_wxyz,
        com_offset_body_m=value.com_offset_body_m,
        linear_velocity_body_origin_local_m_s=local_linear,
        angular_velocity_body_local_rad_s=local_angular,
    )
    np.testing.assert_allclose(world_linear, value.linear_velocity_world_at_com_m_s, atol=1e-12)
    np.testing.assert_allclose(world_angular, value.angular_velocity_world_rad_s, atol=1e-12)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"velocity_frame": "body"}, "world frame"),
        ({"linear_reference_point": "body_origin"}, "center_of_mass"),
        ({"com_offset_body_m": (True, 0.0, 0.0)}, "finite number"),
        ({"linear_velocity_world_at_com_m_s": (0.0, float("nan"), 0.0)}, "finite"),
        ({"orientation_world_from_body_wxyz": (2.0, 0.0, 0.0, 0.0)}, "normalized"),
    ],
)
def test_public_velocity_sample_rejects_ambiguous_or_invalid_conventions(changes, message):
    payload = _readback().to_mapping()
    payload.update(changes)
    with pytest.raises((TypeError, ValueError), match=message):
        PublicRigidBodyReadbackV1.from_mapping(payload)


def test_snapshot_v1_static_joint_binding_failure_happens_before_native_read():
    scene, joint = _scene()
    session = _session(scene, joint, native_value=_readback())
    with pytest.raises(TypeError, match="JointDefinition"):
        session.snapshot_v1(
            scene=scene,
            joint_bindings={"cube-v1": "not-a-definition"},
            frame_bindings={"cube-v1": FrameReference("cube-v1", "root")},
            requirements=_requirements(),
        )
    assert session.native_reads == 0


@pytest.mark.parametrize(
    "requirements, frame_bindings, message",
    [
        (
            StateRequirements(
                "state-requirements-v1", "task", "unknown-joint",
                (StateFieldRequirement(
                    "state-field-requirement-v1", "joint_position", "joint",
                    "cube-v1", "missing", "required", "evaluation_boundary",
                    "joint-definition", "joint_state_query",
                ),),
            ),
            {"cube-v1": FrameReference("cube-v1", "root")},
            "Joint target is not in the declared Scene",
        ),
        (
            StateRequirements(
                "state-requirements-v1", "task", "unknown-frame",
                (StateFieldRequirement(
                    "state-field-requirement-v1", "frame_pose_world", "frame",
                    "cube-v1", "missing", "required", "evaluation_boundary",
                    "meter+quaternion_wxyz", "frame_pose_query",
                ),),
            ),
            {"cube-v1": FrameReference("cube-v1", "root")},
            "Frame target is not in the declared Scene",
        ),
        (
            StateRequirements(
                "state-requirements-v1", "task", "unsupported-required-field",
                (StateFieldRequirement(
                    "state-field-requirement-v1", "contact_force", "entity",
                    "cube-v1", "cube-v1", "required", "evaluation_boundary",
                    "newton", "contact_detection", FrameReference("cube-v1", "root"),
                ),),
            ),
            {"cube-v1": FrameReference("cube-v1", "root")},
            "cannot publish required state field",
        ),
    ],
)
def test_snapshot_v1_rejects_invalid_or_unavailable_required_state_before_native_read(
    requirements, frame_bindings, message,
):
    scene, joint = _scene()
    session = _session(scene, joint, native_value=_readback())
    with pytest.raises(ValueError, match=message):
        session.snapshot_v1(
            scene=scene,
            joint_bindings={"cube-v1": joint},
            frame_bindings=frame_bindings,
            requirements=requirements,
        )
    assert session.native_reads == 0


def test_snapshot_v1_projects_explicit_world_com_sample_and_names_reference_point():
    scene, joint = _scene()
    session = _session(scene, joint, native_value=_readback())
    publication = session.snapshot_v1(
        scene=scene,
        joint_bindings={"cube-v1": joint},
        frame_bindings={"cube-v1": FrameReference("cube-v1", "root")},
        requirements=_requirements(),
    )
    assert session.native_reads == 1
    value = publication.view.joints[0]
    assert value.velocity_expressed_in == FrameReference("cube-v1", "root")
    assert value.velocity_reference_point == FrameReference("cube-v1", "root")
    expected_linear, expected_angular = world_com_twist_to_body_origin_local(
        position_world_m=_readback().position_world_m,
        orientation_world_from_body_wxyz=_readback().orientation_world_from_body_wxyz,
        com_offset_body_m=_readback().com_offset_body_m,
        linear_velocity_world_at_com_m_s=_readback().linear_velocity_world_at_com_m_s,
        angular_velocity_world_rad_s=_readback().angular_velocity_world_rad_s,
    )
    np.testing.assert_allclose(value.velocity[:3], expected_linear, atol=1e-12)
    np.testing.assert_allclose(value.velocity[3:], expected_angular, atol=1e-12)


def test_snapshot_v1_rejects_free_joint_pose_that_disagrees_with_measured_frame():
    from dataclasses import replace

    scene, joint = _scene()
    changed = replace(_readback(), position_world_m=(1.1, 2.0, 3.0))
    session = _session(scene, joint, native_value=changed)
    with pytest.raises(ValueError, match="pose differs from its measured child Frame"):
        session.snapshot_v1(
            scene=scene,
            joint_bindings={"cube-v1": joint},
            frame_bindings={"cube-v1": FrameReference("cube-v1", "root")},
            requirements=_requirements(),
        )
    assert session.native_reads == 1


def _execution_v1(*, provider="geophys", backend="cpu", device=None, overrides=()):
    return ExecutionSpecV1(
        "execution-spec-v1", provider, backend, "p1_2_scalar_cpu_v0", 17, "strict",
        RendererSelectionV1("renderer-selection-v1", "none", "cpu", "none", None),
        device, tuple(overrides),
    )


def test_execution_spec_v1_projects_only_when_no_v1_only_choice_would_be_lost():
    declared = _execution_v1()
    decoded = decode_execution_spec(declared.to_mapping())
    assert type(decoded) is ExecutionSpecV1
    assert decoded.identity_hash == declared.identity_hash
    projected = legacy_execution_projection(declared)
    assert type(projected) is ExecutionSpec
    assert projected.to_mapping() == {
        "physics_provider": "geophys",
        "physics_profile": "p1_2_scalar_cpu_v0",
        "render_provider": "none",
        "backend": "cpu",
        "provider_seed": 17,
        "determinism_mode": "strict",
    }
    with pytest.raises(ValueError, match="Isaac Sim.*contract-only.*no Core RuntimeSession adapter"):
        legacy_execution_projection(_execution_v1(provider="isaacsim", backend="cuda", device="cuda:0"))
    override = CameraRendererOverrideV1(
        "camera-renderer-override-v1", "front",
        RendererSelectionV1("renderer-selection-v1", "none", "cpu", "none", None),
    )
    with pytest.raises(ValueError, match="camera overrides"):
        legacy_execution_projection(_execution_v1(overrides=(override,)))
    with pytest.raises(ValueError, match="physics_device"):
        legacy_execution_projection(_execution_v1(backend="cuda", device="cuda:0"))
    with pytest.raises(ValueError, match="unsupported execution spec schema"):
        decode_execution_spec({"schema_version": "execution-spec-v99"})


def _isaac_execution_v1():
    return ExecutionSpecV1(
        "execution-spec-v1", "isaacsim", "cuda", "physx-gpu-f03-s1", 17, "best_effort",
        RendererSelectionV1("renderer-selection-v1", "none", "cpu", "none", None),
        "cuda:0", (),
    )


def test_isaac_named_drive_receipt_resolves_reordered_public_dofs_by_name():
    dof_names = (
        "panda_finger_joint2", "panda_joint4", "panda_joint1", "panda_joint7",
        "panda_finger_joint1", "panda_joint2", "panda_joint6", "panda_joint3",
        "panda_joint5",
    )
    limits = {
        name: ((0.0, 0.04) if name.startswith("panda_finger") else (-3.2, 3.2))
        for name in dof_names
    }
    receipt = compile_isaac_named_position_drive_receipt_v1(
        execution=_isaac_execution_v1(), scene_identity_sha256="a" * 64,
        source_closure_sha256="b" * 64, provider_build_identity="isaacsim-6.2.0.0",
        writer_id="panda-position-writer-v1", native_dof_names=dof_names,
        native_position_limits=limits,
    )
    assert receipt.provenance_kind == "synthetic_fixture"
    assert len(receipt.identity_sha256) == 64
    commands = receipt.commands(
        {f"panda-main/joint{index}": 0.1 * index for index in range(1, 8)},
        0.08,
    )
    assert tuple(command[0] for command in commands) == tuple(range(9))
    command_by_name = {name: value for _index, name, value in commands}
    assert command_by_name["panda_finger_joint1"] == pytest.approx(0.04)
    assert command_by_name["panda_finger_joint2"] == pytest.approx(0.04)
    assert command_by_name["panda_joint6"] == pytest.approx(0.6)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"backend": "cpu"}, "declared CUDA 0 best_effort"),
        ({"determinism_mode": "strict"}, "declared CUDA 0 best_effort"),
        ({"hand_opening_m": 0.081}, "within \\[0, 0.08\\]"),
        ({"hand_opening_m": True}, "finite non-boolean"),
    ],
)
def test_isaac_named_drive_receipt_rejects_wrong_execution_or_hand_range(changes, message):
    from dataclasses import replace

    execution = _isaac_execution_v1()
    if "backend" in changes:
        execution = replace(execution, physics_backend=changes["backend"])
    if "determinism_mode" in changes:
        execution = replace(execution, determinism_mode=changes["determinism_mode"])
    dof_names = tuple(
        [f"panda_joint{index}" for index in range(1, 8)]
        + ["panda_finger_joint1", "panda_finger_joint2"]
    )
    limits = {
        name: ((0.0, 0.04) if name.startswith("panda_finger") else (-3.2, 3.2))
        for name in dof_names
    }
    if "backend" in changes or "determinism_mode" in changes:
        with pytest.raises(ValueError, match=message):
            compile_isaac_named_position_drive_receipt_v1(
                execution=execution, scene_identity_sha256="a" * 64,
                source_closure_sha256="b" * 64, provider_build_identity="isaacsim-6.2.0.0",
                writer_id="panda-position-writer-v1", native_dof_names=dof_names,
                native_position_limits=limits,
            )
        return
    receipt = compile_isaac_named_position_drive_receipt_v1(
        execution=execution, scene_identity_sha256="a" * 64,
        source_closure_sha256="b" * 64, provider_build_identity="isaacsim-6.2.0.0",
        writer_id="panda-position-writer-v1", native_dof_names=dof_names,
        native_position_limits=limits,
    )
    with pytest.raises(ValueError, match=message):
        receipt.commands(
            {f"panda-main/joint{index}": 0.0 for index in range(1, 8)},
            changes["hand_opening_m"],
        )


def test_versioned_usd_source_owns_exact_delivery_snapshot_bytes_and_cleanup(tmp_path):
    from task_env.diagnostics.tasks.f02_usd_delivery_fixture import build_fixture

    manifest = build_fixture(tmp_path / "f02-synthetic-delivery")
    loaded = load_usd_asset_delivery(manifest, allow_synthetic=True)
    selection = resolve_provider_representation(
        loaded, provider="isaacsim", provider_build_identity="isaacsim-6.2.0.0",
    )
    source = UsdTaskSceneSourceV1(
        "usd-task-scene-source-v1", loaded, selection, "c" * 64, "d" * 64,
    )
    source.validate()
    assert source.source_verified is False
    assert source.source_closure_sha256 == loaded.closure_sha256
    assert selection.runtime_admitted is False
    with source.acquire_snapshot() as snapshot:
        assert (snapshot.root / loaded.delivery.entry_file).read_bytes() == loaded.file_bytes[loaded.delivery.entry_file]
        assert (snapshot.root / loaded.delivery.validation_report_path).read_bytes() == loaded.report_bytes
        snapshot_root = snapshot.root
    assert snapshot.closed
    assert not snapshot_root.exists()

    rejected = resolve_provider_representation(
        loaded,
        provider="mujoco",
        provider_build_identity=(
            "mujoco-3.8.1-libsha256-"
            "8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592"
        ),
    )
    mismatched = UsdTaskSceneSourceV1(
        "usd-task-scene-source-v1", loaded, rejected, "c" * 64, "d" * 64,
    )
    with pytest.raises(ValueError, match="does not bind the exact loaded delivery"):
        mismatched.validate()

    entry_path = manifest.parent / loaded.delivery.entry_file
    entry_path.write_bytes(entry_path.read_bytes() + b"\n# stale after load\n")
    with pytest.raises(ValueError, match="stale USD source dependency"):
        source.acquire_snapshot()


def test_usd_runtime_source_binds_task_scene_and_fails_closed_before_session_dispatch(tmp_path, monkeypatch):
    from task_env.diagnostics.tasks.f02_usd_delivery_fixture import build_fixture
    from task_env.environment.task_source import (
        TaskInitializationV1, TaskRoleDeclarationV1, TaskSourceV1,
        compile_task_artifact_v1,
    )
    from task_env.assembly.usd_delivery import load_usd_asset_delivery, resolve_provider_representation
    from task_env.assembly.source import UsdTaskSceneSourceV1
    from task_env.runtime.sessions import api as session_api

    manifest = build_fixture(tmp_path / "f02-runtime-source")
    loaded = load_usd_asset_delivery(manifest, allow_synthetic=True)
    base_scene, free_joint = _scene()
    asset = loaded.delivery.asset_definition
    scene = SceneDefinition(
        "scene-definition-v2", "f03-usd-source-scene",
        (asset,),
        (EntityInstance("entity-instance-v1", "cube-v1", asset.asset_id, asset.asset_version),),
        base_scene.frames,
        base_scene.articulations,
    )
    source_declaration = TaskSourceV1(
        "f03-usd-source-task", "v1", scene.scene_id,
        (TaskRoleDeclarationV1("target", "rigid_body", "ids", ("cube-v1",), "exactly_one"),),
        TaskInitializationV1(
            "f03-reset", "v1", "evaluation",
            "zero_named_joint_and_entity_velocities",
            "arm_targets_at_initial_joints_gripper_open",
        ),
    )
    legacy = TaskArtifact(
        "task-artifact-v0", "f03-usd-source-v0", source_declaration.task_id, "v1",
        WorldDefinition(
            "world-v0", "SI_right_handed_z_up_wxyz",
            (EntityDefinition(
                "cube-v1", "movable", f"{asset.source_reference}@{asset.asset_version}",
                ("cube-v1/anchor", "cube-v1/root"), (),
                "source_asset", "source_retained", {},
            ),),
            ActionIntent("absolute_joint", None, "none", "arm_joint_position_and_gripper"),
            ("canonical-state-v0",), (),
        ),
        InitializationContract(
            "initialization-v0",
            {"cube-v1/root": PoseWorld((0.2, -0.1, 0.4), (1.0, 0.0, 0.0, 0.0))},
            {}, (), "zero_named_joint_and_entity_velocities", "f03-synthetic-reset", 0,
        ),
        SemanticDefinition(
            "semantics-v0", "f03_state_only", ("cube-v1/root",), (), {}, "f03_contract_only",
        ),
        Timebase(0.002, 5, 0.01),
        RequiredCapabilitySet(("rigid_body", "free_body", "joint_state_query", "frame_pose_query")),
    )
    artifact = compile_task_artifact_v1(source_declaration, scene, legacy)
    representation = resolve_provider_representation(
        loaded, provider="isaacsim", provider_build_identity="isaacsim-6.2.0.0",
    )
    task_scene_source = UsdTaskSceneSourceV1(
        "usd-task-scene-source-v1", loaded, representation,
        source_declaration.identity_hash, scene.identity_hash,
    )
    runtime_source = UsdRuntimeSourceV1(
        "usd-runtime-source-v1", artifact, scene, task_scene_source,
        {}, {"cube-v1/root": "root"}, {"cube-v1/anchor": "anchor"},
        {"cube-v1/root": "free-root"}, {},
    )
    calls = []
    monkeypatch.setattr(session_api, "_materialize_admitted", lambda *a, **k: calls.append((a, k)))
    with pytest.raises(ValueError, match="synthetic or unverified USD source"):
        session_api.materialize(artifact, _isaac_execution_v1(), source=runtime_source)
    assert calls == []
