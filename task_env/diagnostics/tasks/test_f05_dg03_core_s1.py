"""Provider-free DG03 S1 through the production SelectedReferenceEnv/Core owners."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import hashlib
import json
import os
from pathlib import Path

import pytest

from task_env.diagnostics.tasks.f04_candidate_s1_support import _action_for


DELIVERY_MANIFEST = (
    "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/"
    "f05_diagnostic_goal03/window_001/isaac_usd_v1/delivery_v1_005/delivery_manifest.json"
)


class _SyntheticDg03NativeIO:
    """Replace only the native I/O port; intentionally performs no physics."""

    execution_provenance_kind = "synthetic_fixture"

    def __init__(self, *, artifact, execution, source, input_v1):
        from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
        from task_env.runtime.sessions.leaf_control import compile_isaac_source_tendon_receipt_v1
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
            artifact.timebase.physics_dt, artifact.timebase.control_substeps,
            names, limits,
        )
        self.drive_receipt = compile_isaac_source_tendon_receipt_v1(
            execution=execution, source=source, native_metadata=self._metadata,
            writer_id="panda-main/position-servo-v1", provenance_kind="synthetic_fixture",
        )
        self.joints = {}
        self.free_pose = None
        self.time_s = 0.0
        self.native_step_index = 0
        self.reset_count = 0
        self.position_write_count = 0
        self.tendon_write_count = 0
        self.advance_count = 0
        self.close_count = 0
        self.operations = []
        self.last_tendon_target = None

    def metadata(self):
        return self._metadata

    def write_reset(self, sample, position_targets):
        from task_env.runtime.sessions.native_io import NativeResetWriteReceiptV1

        self.reset_count += 1
        self.joints = dict(sample.joint_position)
        self.free_pose = sample.poses_world["free-cube/free_cube"]
        self.time_s = 0.0
        self.native_step_index = 0
        self.last_tendon_target = None
        names = tuple(name for _index, name, _value in position_targets)
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
        for _index, native, value in targets:
            self.joints[f"panda-main/{native}"] = float(value)
        names = tuple(name for _index, name, _value in targets)
        values = tuple(float(value) for _index, _name, value in targets)
        self.operations.append({"op": "arm-target", "target": target_identity_sha256})
        return NativePositionWriteAckV1(
            "native-position-write-ack-v1", target_identity_sha256,
            names, values, False, len(targets),
        )

    def write_source_tendon_target(
        self, target_identity_sha256, receipt_identity_sha256, actuator_name,
        control_value, scalar_force_limit_N,
    ):
        from task_env.runtime.sessions.native_io import NativeSourceTendonWriteAckV1

        self.tendon_write_count += 1
        self.last_tendon_target = {
            "target_identity_sha256": target_identity_sha256,
            "receipt_identity_sha256": receipt_identity_sha256,
            "actuator_name": actuator_name,
            "control_value": float(control_value),
            "scalar_force_limit_N": float(scalar_force_limit_N),
        }
        self.operations.append({"op": "tendon-target", **self.last_tendon_target})
        return NativeSourceTendonWriteAckV1(
            "native-source-tendon-write-ack-v1", target_identity_sha256,
            receipt_identity_sha256, actuator_name, float(control_value),
            float(scalar_force_limit_N), False,
        )

    def advance(self):
        from task_env.runtime.sessions.native_io import NativeAdvanceReceiptV1

        if self.last_tendon_target is None:
            raise RuntimeError("synthetic DG03 substep requires a current source tendon target")
        self.native_step_index += 1
        self.advance_count += 1
        self.time_s = self.native_step_index * float(self.artifact.timebase.physics_dt)
        receipt = self.drive_receipt
        q = tuple(self.joints[f"panda-main/{name}"] for name in receipt.tendon_native_joint_names)
        qd = (0.0, 0.0)
        length = sum(a * b for a, b in zip(receipt.tendon_coefficients, q, strict=True))
        rate = sum(a * b for a, b in zip(receipt.tendon_coefficients, qd, strict=True))
        target = self.last_tendon_target
        raw = (receipt.actuator_gain * target["control_value"]
               + receipt.actuator_length_bias * length
               + receipt.actuator_rate_bias * rate)
        limit = min(target["scalar_force_limit_N"], receipt.actuator_force_range[1])
        force = min(limit, max(-limit, min(receipt.actuator_force_range[1],
                                           max(receipt.actuator_force_range[0], raw))))
        application = {
            "schema_version": "native-source-tendon-substep-v1",
            "target_identity_sha256": target["target_identity_sha256"],
            "receipt_identity_sha256": target["receipt_identity_sha256"],
            "actuator_name": target["actuator_name"],
            "control_value": target["control_value"],
            "scalar_force_limit_N": target["scalar_force_limit_N"],
            "native_step_index": self.native_step_index,
            "public_effort_api": "synthetic-no-physics",
            "effort_write_attempted_count": 2,
            "effort_write_completed_count": 2,
            "native_finger_joint_names": receipt.tendon_native_joint_names,
            "native_finger_dof_indices": tuple(
                self._metadata.native_dof_names.index(name)
                for name in receipt.tendon_native_joint_names
            ),
            "finger_positions_m": q,
            "finger_velocities_m_s": qd,
            "tendon_coefficients": receipt.tendon_coefficients,
            "tendon_length_m": length,
            "tendon_rate_m_s": rate,
            "unclipped_scalar_force_N": raw,
            "scalar_force_N": force,
            "dof_efforts_N": tuple(a * force for a in receipt.tendon_coefficients),
        }
        self.operations.append({"op": "advance", **application})
        return NativeAdvanceReceiptV1(
            "native-advance-receipt-v1", 1, self.native_step_index, self.time_s, application,
        )

    def close(self):
        self.close_count += 1


def test_f05_dg03_selected_reference_core_s1_two_episodes(tmp_path):
    """Exercise exact Core reset/control/readback/recording with synthetic I/O only."""
    from task_env.recorders import load_structured_control_records_h5
    from task_env.runtime.sessions import api
    from task_env.tasks.position_candidate.builder import build_f05_dg03_isaac_usd_candidate

    input_v1, candidate = build_f05_dg03_isaac_usd_candidate(DELIVERY_MANIFEST, horizon=8)
    created = []
    evidence_root = Path(os.environ.get("F05_DG03_CORE_S1_OUTPUT", tmp_path)).resolve()
    if evidence_root.exists() and evidence_root != tmp_path.resolve():
        raise FileExistsError(f"refusing to overwrite existing DG03 Core S1 evidence: {evidence_root}")
    evidence_root.mkdir(parents=True, exist_ok=True)
    episode_receipts = []

    def factory(*, artifact, execution, source, input_v1):
        native_io = _SyntheticDg03NativeIO(
            artifact=artifact, execution=execution, source=source, input_v1=input_v1,
        )
        created.append(native_io)
        return native_io

    env = candidate.env
    with api._f05_dg03_s1_native_io_context(input_v1, factory):
        try:
            for episode in range(2):
                observation, _info = env.reset(seed=input_v1.reset_plan.reset_sample.task_seed)
                assert observation
                assert env.session._drive_receipt.provenance_kind == "synthetic_fixture"
                assert env.session._native_io.execution_provenance_kind == "synthetic_fixture"
                path = evidence_root / f"dg03-core-s1-{episode:02d}.h5"
                env.start_recording(path)
                for interval in range(8):
                    observation, _reward, _terminated, _truncated, _info = env.step(
                        _action_for(env, interval % 4)
                    )
                    assert observation
                    assert len(env.session._last_interval_advances) == 5
                    assert all("source_tendon_application" in item
                               for item in env.session._last_interval_advances)
                result = env.finish_recording("horizon")
                loaded = load_structured_control_records_h5(path)
                assert result["transition_count"] == 8
                assert result["observation_count"] == 9
                assert loaded["transition_count"] == 8
                assert loaded["observation_count"] == 9
                io = created[-1]
                assert io.reset_count == 1
                assert io.position_write_count == 8
                assert io.tendon_write_count == 8
                assert io.advance_count == 40
                assert len([row for row in io.operations if row["op"] == "advance"]) == 40
                episode_receipts.append({
                    "episode_ordinal": episode,
                    "h5_path": str(path),
                    "h5_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "transition_count": result["transition_count"],
                    "observation_count": result["observation_count"],
                    "operation_counts": {
                        operation: sum(item["op"] == operation for item in io.operations)
                        for operation in ("reset", "arm-target", "tendon-target", "advance")
                    },
                    "operation_log": io.operations,
                })
            session = env.session
            good = dict(session._last_interval_advances[-1]["source_tendon_application"])
            tamper_cases = {
                "finger_position": lambda row: row.__setitem__(
                    "finger_positions_m", (row["finger_positions_m"][0] + 0.01,
                                            row["finger_positions_m"][1]),
                ),
                "finger_velocity": lambda row: row.__setitem__(
                    "finger_velocities_m_s", (row["finger_velocities_m_s"][0] + 0.01,
                                               row["finger_velocities_m_s"][1]),
                ),
                "tendon_length": lambda row: row.__setitem__(
                    "tendon_length_m", row["tendon_length_m"] + 0.01,
                ),
                "tendon_rate": lambda row: row.__setitem__(
                    "tendon_rate_m_s", row["tendon_rate_m_s"] + 0.01,
                ),
                "unclipped_force": lambda row: row.__setitem__(
                    "unclipped_scalar_force_N", row["unclipped_scalar_force_N"] + 1.0,
                ),
                "clipped_force": lambda row: row.__setitem__(
                    "scalar_force_N", row["scalar_force_N"] + 1.0,
                ),
                "effort_vector": lambda row: row.__setitem__(
                    "dof_efforts_N", (row["dof_efforts_N"][0] + 1.0,
                                       row["dof_efforts_N"][1]),
                ),
                "native_indices": lambda row: row.__setitem__(
                    "native_finger_dof_indices", tuple(reversed(row["native_finger_dof_indices"])),
                ),
                "native_names": lambda row: row.__setitem__(
                    "native_finger_joint_names", tuple(reversed(row["native_finger_joint_names"])),
                ),
                "effort_api": lambda row: row.__setitem__("public_effort_api", "private-solver-state"),
                "write_count": lambda row: row.__setitem__("effort_write_completed_count", 1),
                "tendon_coefficients": lambda row: row.__setitem__("tendon_coefficients", (1.0, 0.0)),
            }
            for mutation in tamper_cases.values():
                changed = dict(good)
                mutation(changed)
                with pytest.raises((TypeError, ValueError)):
                    session._validate_source_tendon_application(
                        changed, session._last_native_source_tendon_ack,
                        session._native_step_count,
                    )
        finally:
            env.close()
    assert len(created) == 2
    assert [io.close_count for io in created] == [1, 1]
    receipt = {
        "schema_version": "f05-dg03-isaac-core-s1-receipt-v1",
        "status": "PASS_SYNTHETIC_CORE_S1_ONLY",
        "task_artifact_identity_sha256": input_v1.artifact.identity_hash,
        "runtime_source_id": input_v1.runtime_source.source_id,
        "source_closure_sha256": input_v1.runtime_source.source_closure_digest,
        "execution_identity_sha256": input_v1.execution.identity_hash,
        "scene_identity_sha256": input_v1.runtime_source.scene_definition.identity_hash,
        "source_verified": False,
        "locally_validated": True,
        "runtime_admitted": False,
        "execution_provenance_kind": "synthetic_fixture",
        "native_starts": 0,
        "physics_steps": 0,
        "episodes": episode_receipts,
        "source_tendon_mutation_cases_rejected": 12,
        "native_io_close_counts": [io.close_count for io in created],
    }
    (evidence_root / "core_s1_receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def test_f05_dg03_native_route_fails_closed_before_isaac_app(monkeypatch):
    """Unproved source consumers cannot turn a local USD candidate into native admission."""
    from task_env.artifacts import CapabilityAdmissionError
    from task_env.runtime.sessions import isaac_native_io
    from task_env.tasks.position_candidate.builder import build_f05_dg03_isaac_usd_candidate

    input_v1, candidate = build_f05_dg03_isaac_usd_candidate(DELIVERY_MANIFEST, horizon=8)

    def forbidden_app_owner():
        pytest.fail("DG03 unproven source feature gate must reject before Isaac App ownership")

    monkeypatch.setattr(isaac_native_io, "_process_app_owner", forbidden_app_owner)
    try:
        with pytest.raises(CapabilityAdmissionError, match="BLOCKED_BY_FEATURE"):
            candidate.env.reset(seed=input_v1.reset_plan.reset_sample.task_seed)
    finally:
        candidate.env.close()
