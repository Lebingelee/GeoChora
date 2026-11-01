"""Synthetic-lowest-I/O S1 for the production DG04 SelectedReferenceEnv/Core route."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from task_env.diagnostics.tasks.f04_candidate_s1_support import _action_for


DELIVERY_MANIFEST = (
    "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/"
    "f05_diagnostic04/window_002/isaac_usd_v4/delivery_manifest.json"
)


class _SyntheticDg04NativeIO:
    """Replace only the native I/O port; all returned motion/contact is synthetic."""

    execution_provenance_kind = "synthetic_fixture"

    def __init__(self, *, artifact, execution, source, input_v1):
        from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
        from task_env.runtime.sessions.leaf_control import compile_isaac_native_mimic_position_receipt_v1
        from task_env.runtime.sessions.native_io import NativeRuntimeIOMetadataV1

        self.artifact, self.execution, self.source, self.input_v1 = (
            artifact, execution, source, input_v1,
        )
        profile = PandaPositionServoProfileV1.from_usd_source(
            artifact, source, execution=execution,
            kinematics_source_xml=input_v1.kinematics_source_xml,
            config=input_v1.action_config,
        )
        self._model = profile.model
        names = tuple(source.joint_targets.values())
        limits = {
            f"joint{index}": tuple(float(value) for value in profile.model.limits[index - 1])
            for index in range(1, 8)
        }
        root = ET.fromstring(input_v1.kinematics_source_xml)
        finger_defaults = root.find(".//default[@class='finger']/joint")
        if finger_defaults is None or "range" not in finger_defaults.attrib:
            raise ValueError("exact Menagerie finger joint range is absent from the source XML")
        finger_limits = tuple(float(value) for value in finger_defaults.attrib["range"].split())
        limits.update({"finger_joint1": finger_limits, "finger_joint2": finger_limits})
        self._metadata = NativeRuntimeIOMetadataV1(
            "native-runtime-io-metadata-v1", source.source_id, source.source_closure_digest,
            source.scene_definition.identity_hash, artifact.identity_hash, execution.identity_hash,
            "isaacsim", "isaacsim-6.2.0.0", "cuda", "cuda:0", "best_effort",
            artifact.timebase.physics_dt, artifact.timebase.control_substeps, names, limits,
        )
        witness = {
            "schema_version": "isaac-dg04-native-mimic-drive-witness-v1",
            "native_dof_order": list(names),
            "active_drive_dofs": [f"joint{index}" for index in range(1, 8)] + ["finger_joint1"],
            "passive_mimic_dof": "finger_joint2",
            "leader_stiffness_N_m": 2000.0,
            "leader_damping_N_s_m": 100.0,
            "leader_max_effort_N": 100.0,
            "leader_drive_type": "force",
            "follower_stiffness_N_m": 0.0,
            "follower_damping_N_s_m": 0.0,
            "follower_drive_type": "none",
            "mimic_api": "PhysxMimicJointAPI:transX",
            "drive_api": "PhysicsDriveAPI:linear",
            "mimic_reference_joint": "finger_joint1",
            "mimic_follower_joint": "finger_joint2",
            "mimic_gearing": 1.0,
            "mimic_offset_m": 0.0,
            "mimic_natural_frequency_hz": 25.0,
            "mimic_damping_ratio": 1.0,
            "passive_mimic_constraint_authored": True,
        }
        self.drive_receipt = compile_isaac_native_mimic_position_receipt_v1(
            execution=execution, source=source, native_metadata=self._metadata,
            writer_id="panda-main/position-servo-v1", native_drive_witness=witness,
            provenance_kind="synthetic_fixture",
        )
        self.joints = {}
        self.free_pose = None
        self.time_s = 0.0
        self.native_step_index = 0
        self.last_target = None
        self.reset_count = self.position_write_count = self.advance_count = self.close_count = 0
        self.operations = []

    def metadata(self):
        return self._metadata

    def write_reset(self, sample, position_targets):
        from task_env.runtime.sessions.native_io import NativeResetWriteReceiptV1

        self.reset_count += 1
        self.joints = dict(sample.joint_position)
        self.free_pose = sample.poses_world["free-cube/free_cube"]
        self.time_s = 0.0
        self.native_step_index = 0
        self.last_target = None
        names = tuple(name for _index, name, _value in position_targets)
        if len(names) != 8 or "finger_joint2" in names:
            raise ValueError("DG04 reset must target seven Arm joints and only the mimic leader")
        self.operations.append({"op": "reset", "targets": names})
        return NativeResetWriteReceiptV1(
            "native-reset-write-receipt-v1", sample.sample_id,
            tuple(sorted(self.source.joints)), tuple(sorted(self.source.free_joints)),
            names, True, False,
        )

    def read_state(self):
        from task_env.artifacts import PoseWorld
        from task_env.runtime.sessions.free_joint_state import PublicRigidBodyReadbackV1
        from task_env.runtime.sessions.native_io import NativeRuntimeReadbackV1

        arm = tuple(self.joints[f"panda-main/joint{index}"] for index in range(1, 8))
        hand_pose = self._model.pose(arm)
        frames = {
            name: hand_pose if name == "panda-main/hand" else
            self.free_pose if name == "free-cube/free_cube" else
            PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
            for name in (*self.source.bodies, *self.source.frames)
        }
        free = {
            semantic: PublicRigidBodyReadbackV1(
                "public-rigid-body-readback-v1", self.artifact.legacy_frame_bindings[semantic],
                self.free_pose.position, self.free_pose.quaternion_wxyz, (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), "world", "center_of_mass",
            ) for semantic in self.source.free_joints
        }
        return NativeRuntimeReadbackV1(
            "native-runtime-readback-v1", self.joints,
            {name: 0.0 for name in self.source.joints}, frames, free, self.time_s,
        )

    def write_position_targets(self, target_identity_sha256, targets):
        from task_env.runtime.sessions.native_io import NativePositionWriteAckV1

        self.position_write_count += 1
        targets = tuple(targets)
        if len(targets) != 8 or "finger_joint2" in {name for _index, name, _value in targets}:
            raise ValueError("DG04 control must address seven Arm joints and the active leader only")
        for _index, native, value in targets:
            self.joints[f"panda-main/{native}"] = float(value)
        reference = self.joints["panda-main/finger_joint1"]
        self.joints["panda-main/finger_joint2"] = reference
        names = tuple(name for _index, name, _value in targets)
        values = tuple(float(value) for _index, _name, value in targets)
        self.last_target = {
            "target_identity_sha256": target_identity_sha256,
            "reference_target_m": reference,
        }
        self.operations.append({"op": "position_target", **self.last_target})
        return NativePositionWriteAckV1(
            "native-position-write-ack-v1", target_identity_sha256,
            names, values, False, len(targets),
        )

    def advance(self):
        from task_env.runtime.sessions.native_io import NativeAdvanceReceiptV1

        if self.last_target is None:
            raise RuntimeError("synthetic DG04 step requires a current leader target")
        self.native_step_index += 1
        self.advance_count += 1
        self.time_s = self.native_step_index * float(self.artifact.timebase.physics_dt)
        application = {
            "schema_version": "native-physx-mimic-substep-application-v1",
            "profile_id": "isaacsim-6.2-physx-native-mimic-leader-drive-v1",
            "provenance_kind": "synthetic_fixture",
            "drive_receipt_identity_sha256": self.drive_receipt.identity_sha256,
            "target_identity_sha256": self.last_target["target_identity_sha256"],
            "native_step_index": self.native_step_index,
            "reference_joint": "finger_joint1",
            "follower_joint": "finger_joint2",
            "reference_position_m": self.joints["panda-main/finger_joint1"],
            "follower_position_m": self.joints["panda-main/finger_joint2"],
            "reference_velocity_m_s": 0.0,
            "follower_velocity_m_s": 0.0,
            "relation_error_m": 0.0,
            "reference_target_m": self.last_target["reference_target_m"],
            "reference_effort_N": 0.0,
            "maximum_effort_N": 100.0,
            "public_effort_api": "synthetic-no-physics",
            "effort_measurement_semantics": "synthetic-no-physics",
            "native_mimic_api": "PhysxMimicJointAPI:transX",
            "native_drive_api": "PhysicsDriveAPI:linear",
            "public_contact_witness": {
                "schema_version": "f05-dg04-native-contact-witness-v1",
                "provenance_kind": "synthetic_fixture",
                "api": "synthetic-no-physics",
                "sensor_path": "/F05Scene/free_cube",
                "support_path": "/F05Scene/support/collision",
                "physics_dt_s": float(self.artifact.timebase.physics_dt),
                "raw_contact_count": 0,
                "raw_contact_actor_paths": [],
                "raw_contact_normal_forces_N": [],
                "raw_contact_signed_normal_force_scalars_N": [],
                "raw_contact_normals_world": [],
                "raw_contact_separations_m": [],
                "force_magnitude_mapping": "synthetic-no-physics",
                "contact_count": 0,
                "support_contact_normal_forces_N": [],
                "normal_force_sum_N": 0.0,
                "contact_present": False,
                "physical_contact_checked": False,
            },
        }
        self.operations.append({"op": "advance", **application})
        return NativeAdvanceReceiptV1(
            "native-advance-receipt-v1", 1, self.native_step_index,
            self.time_s, None, application,
        )

    def close(self):
        self.close_count += 1


def test_f05_dg04_selected_reference_core_s1_two_episodes(tmp_path):
    """Exercise Core reset/control/step/typed readback/recording with synthetic I/O only."""
    from task_env.recorders import load_structured_control_records_h5
    from task_env.runtime.sessions import api
    from task_env.tasks.position_candidate.builder import build_f05_dg04_isaac_native_candidate

    input_v1, candidate = build_f05_dg04_isaac_native_candidate(
        DELIVERY_MANIFEST, horizon=8,
    )
    created = []
    evidence_root = Path(os.environ.get("F05_DG04_CORE_S1_OUTPUT", tmp_path)).resolve()
    if evidence_root.exists() and evidence_root != tmp_path.resolve():
        raise FileExistsError(f"refusing to overwrite existing DG04 Core S1 evidence: {evidence_root}")
    evidence_root.mkdir(parents=True, exist_ok=True)

    def factory(*, artifact, execution, source, input_v1):
        native_io = _SyntheticDg04NativeIO(
            artifact=artifact, execution=execution, source=source, input_v1=input_v1,
        )
        created.append(native_io)
        return native_io

    env = candidate.env
    episode_receipts = []
    with api._f05_dg03_s1_native_io_context(input_v1, factory):
        try:
            for episode in range(2):
                observation, _info = env.reset(seed=input_v1.reset_plan.reset_sample.task_seed)
                assert observation
                assert env.session._drive_receipt.provenance_kind == "synthetic_fixture"
                assert env.session._native_io.execution_provenance_kind == "synthetic_fixture"
                with pytest.raises(ValueError):
                    env.session._drive_receipt.commands(
                        {f"panda-main/joint{index}": 0.0 for index in range(1, 8)}, 0.081,
                    )
                path = evidence_root / f"dg04-core-s1-{episode:02d}.h5"
                env.start_recording(path)
                for interval in range(8):
                    observation, _reward, _terminated, _truncated, _info = env.step(
                        _action_for(env, interval % 4)
                    )
                    assert observation
                    advances = env.session._last_interval_advances
                    assert len(advances) == 5
                    assert all(
                        row["native_adaptation_application"]["provenance_kind"] == "synthetic_fixture"
                        for row in advances
                    )
                    assert all(
                        row["native_adaptation_application"]["relation_error_m"] == 0.0
                        for row in advances
                    )
                result = env.finish_recording("horizon")
                loaded = load_structured_control_records_h5(path)
                assert result["transition_count"] == loaded["transition_count"] == 8
                assert result["observation_count"] == loaded["observation_count"] == 9
                env_meta = loaded["env_meta"]
                profile = env_meta["reference_profile"]
                assert env_meta["environment"]["name"] == "SelectedReferenceEnv.F05Dg04IsaacNativePosition"
                assert profile["schema_version"] == "f05-dg04-isaac-native-core-position-profile-v1"
                assert profile["profile_id"] == "f05-dg04-isaac-native-mimic-v1"
                assert profile["provenance_kind"] == "synthetic_fixture"
                assert profile["runtime_admitted"] is False
                assert profile["native_position_drive_receipt"]["identity_sha256"] == profile[
                    "native_position_drive_receipt_identity_sha256"
                ]
                assert "native_public_bootstrap_receipt" not in profile
                io = created[-1]
                assert io.reset_count == 1
                assert io.position_write_count == 8
                assert io.advance_count == 40
                episode_receipts.append({
                    "episode_ordinal": episode,
                    "h5_path": str(path),
                    "h5_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "transition_count": result["transition_count"],
                    "observation_count": result["observation_count"],
                    "operation_counts": {
                        operation: sum(row["op"] == operation for row in io.operations)
                        for operation in ("reset", "position_target", "advance")
                    },
                    "synthetic_physics": True,
                })
            report = {
                "schema_version": "f05-dg04-core-s1-evidence-v1",
                "input_identities": {
                    "task_artifact": input_v1.artifact.identity_hash,
                    "source_id": input_v1.runtime_source.source_id,
                    "source_closure_sha256": input_v1.runtime_source.source_closure_digest,
                    "execution": input_v1.execution.identity_hash,
                    "native_drive_receipt": env.session._drive_receipt.identity_sha256,
                },
                "production_route": "SelectedReferenceEnv->RuntimeSession->synthetic lowest NativeRuntimeIO",
                "episodes": episode_receipts,
                "claim_limit": "Core lifecycle/typed-state/action/recording wiring only; no native physics evidence",
            }
        finally:
            env.close()
    assert len(created) == 2
    assert all(io.close_count == 1 for io in created)
    report["closed_native_io_count"] = sum(io.close_count for io in created)
    (evidence_root / "summary.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
