"""Provider-free F04 Core adapter S1; replaces only the lowest native-I/O port."""
from __future__ import annotations

import builtins
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import numpy as np
import pytest

from task_env.artifacts import FrameReference, PoseWorld
from task_env.recorders import load_structured_control_records_h5
from task_env.runtime.sessions.free_joint_state import PublicRigidBodyReadbackV1
from task_env.runtime.sessions.native_io import (
    NativeAdvanceReceiptV1, NativePositionWriteAckV1, NativeResetWriteReceiptV1,
    NativeRuntimeIOMetadataV1, NativeRuntimeReadbackV1,
)

from task_env.diagnostics.tasks.f04_candidate_s1_support import (
    _action_for, _limits, _native_order, build_candidate,
)


def _flatten_public_observation(value, prefix=""):
    if isinstance(value, dict):
        result = {}
        for key in sorted(value):
            child = f"{prefix}/{key}" if prefix else str(key)
            result.update(_flatten_public_observation(value[key], child))
        return result
    array = np.asarray(value)
    return {prefix: {
        "dtype": array.dtype.str, "shape": list(array.shape),
        "bytes_sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest(),
    }}


def _public_boundary_witness(observation, info):
    boundary = info.get("state_boundary_identity")
    clock = info.get("state_sample_clock")
    boundary_id = info.get("state_boundary_id")
    state_publication = info.get("canonical_state_view_v1")
    if (not isinstance(boundary, dict) or not isinstance(clock, dict)
            or not isinstance(boundary_id, str) or not isinstance(state_publication, dict)):
        raise ValueError("public reset/step result lacks its typed F04 boundary, clock, or state publication")
    fields = _flatten_public_observation(observation)
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {
        "control_step": int(info["control_step"]),
        "simulation_time_s": float(info["simulation_time_s"]),
        "state_boundary_identity": boundary,
        "state_boundary_id": boundary_id,
        "state_sample_clock": clock,
        "canonical_state_view_v1": state_publication,
        "observation_identity_sha256": hashlib.sha256(payload).hexdigest(),
        "observation_fields": fields,
    }


@pytest.mark.parametrize("family", ("official-panda", "menagerie-panda"))
def test_f04_candidate_reset_is_bound_over_the_local_support_recipe(family):
    """The Core reset sample must place the free cube above its delivered support."""
    candidate = build_candidate(family)
    delivery_root = (
        Path(__file__).resolve().parents[3]
        / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f04_002/assets"
        / ("local_official_panda_r007" if family == "official-panda"
           else "local_menagerie_panda_r007")
    )
    delivery = json.loads((delivery_root / "usd_delivery.json").read_text())
    recipe_path = delivery_root / delivery["recipe_path"]
    recipe_bytes = recipe_path.read_bytes()
    assert hashlib.sha256(recipe_bytes).hexdigest() == delivery["recipe_sha256"]
    task_scene = json.loads(recipe_bytes)["task_scene"]
    body, support = task_scene["free_body"], task_scene["support"]
    reset = candidate.reset_plan.reset_sample.poses_world["square-peg-instance/peg1"]
    assert reset.position == tuple(body["center_m"])
    assert body["rigid_body"] and body["collision"] and support["collision"]
    support_top = support["center_m"][2] + support["scale_m"][2] / 2.0
    resting_center = support_top + body["edge_m"] / 2.0
    assert reset.position[2] - resting_center >= 0.25


class _S1NativeIO:
    """Stateful leaf double only: no integration, Core Session, or recorder behavior."""

    execution_provenance_kind = "synthetic_fixture"

    def __init__(self, *, artifact, execution, source, input_v1):
        from task_env.controllers.canonical.kinematics import (
            PANDA_HAND_ORIGIN_TCP_V1, PandaKinematics,
        )

        self.artifact, self.execution, self.source, self.input_v1 = artifact, execution, source, input_v1
        self.model = PandaKinematics(input_v1.kinematics_source_xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1)
        self.native_dof_names = _native_order(source)
        limits = _limits(source)
        self._metadata = NativeRuntimeIOMetadataV1(
            "native-runtime-io-metadata-v1", source.source_id, source.source_closure_digest,
            source.scene_definition.identity_hash, artifact.identity_hash, execution.identity_hash,
            "isaacsim", "isaacsim-6.2.0.0", "cuda", "cuda:0", "best_effort",
            artifact.timebase.physics_dt, artifact.timebase.control_substeps,
            self.native_dof_names, limits,
        )
        self._reverse = {native: semantic for semantic, native in source.joint_targets.items()}
        self.q = {}
        self.free_pose = None
        self.native_index = 0
        self.advances = 0
        self.close_count = 0
        self.runtime_close_count = 0

    def metadata(self):
        return self._metadata

    def write_reset(self, sample, position_targets):
        self.q = dict(sample.joint_position)
        self.free_pose = sample.poses_world["square-peg-instance/peg1"]
        self.native_index = 0
        return NativeResetWriteReceiptV1(
            "native-reset-write-receipt-v1", sample.sample_id,
            tuple(sorted(self.source.joints)), tuple(sorted(self.source.free_joints)),
            tuple(name for _index, name, _value in sorted(position_targets)), True, False,
        )

    def read_state(self):
        from task_env.artifacts import PoseWorld

        arm = [self.q[f"panda-main/joint{i}"] for i in range(1, 8)]
        hand = self.model.pose(arm)
        frames = {}
        for semantic in (*self.source.bodies, *self.source.frames):
            if semantic == "panda-main/hand":
                frames[semantic] = hand
            elif semantic.startswith("square-peg-instance/"):
                frames[semantic] = self.free_pose
            else:
                frames[semantic] = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
        free = {
            semantic: PublicRigidBodyReadbackV1(
                "public-rigid-body-readback-v1",
                self.input_v1.artifact.legacy_frame_bindings[semantic],
                self.free_pose.position, self.free_pose.quaternion_wxyz,
                (0.013, -0.004, 0.009), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0),
                "world", "center_of_mass",
            ) for semantic in self.source.free_joints
        }
        return NativeRuntimeReadbackV1(
            "native-runtime-readback-v1", self.q,
            {name: 0.0 for name in self.source.joints}, frames, free,
            self.native_index * self.artifact.timebase.physics_dt,
        )

    def write_position_targets(self, target_identity_sha256, targets):
        ordered = tuple(sorted(targets))
        for _index, native, value in ordered:
            self.q[self._reverse[native]] = float(value)
        return NativePositionWriteAckV1(
            "native-position-write-ack-v1", target_identity_sha256,
            tuple(item[1] for item in ordered), tuple(float(item[2]) for item in ordered),
            False, len(ordered),
        )

    def advance(self):
        self.native_index += 1
        self.advances += 1
        return NativeAdvanceReceiptV1(
            "native-advance-receipt-v1", 1, self.native_index,
            self.native_index * self.artifact.timebase.physics_dt,
        )

    def close(self):
        self.close_count += 1

    def close_runtime_owner(self):
        self.runtime_close_count += 1


@pytest.mark.parametrize("family", ("official-panda", "menagerie-panda"))
def test_f04_local_delivery_through_real_core_env_recorder_s1(tmp_path, monkeypatch, family):
    """Use actual source admission, Core Session, reset/control, public step and H5 owners."""
    from task_env.registry import make_env
    from task_env.runtime.sessions import isaac_native_io

    provider_imports = {"isaacsim", "omni", "carb", "torch", "mujoco", "GeoPhys"}
    original_import = builtins.__import__

    def import_tripwire(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in provider_imports):
            raise AssertionError(f"provider/native import is forbidden during F04 S1: {name}")
        return original_import(name, *args, **kwargs)

    before_modules = set(sys.modules)
    input_v1 = build_candidate(family)
    created = []

    def low_io_factory(artifact, execution, source):
        io = _S1NativeIO(artifact=artifact, execution=execution, source=source, input_v1=input_v1)
        created.append(io)
        return io

    monkeypatch.setattr(isaac_native_io, "create_isaac_native_runtime_io", low_io_factory)
    monkeypatch.setattr(builtins, "__import__", import_tripwire)
    env = make_env(
        "panda-position-servo-candidate-v1",
        config={"versioned_input": input_v1, "horizon": 4},
    )
    output_root = Path(os.environ["F04_S1_OUTPUT"]) / family
    output_root.mkdir(parents=True, exist_ok=True)
    h5_paths = []
    try:
        for episode in range(2):
            observation, info = env.reset(seed=31)
            public_boundaries = [_public_boundary_witness(observation, info)]
            assert env.execution is input_v1.execution
            assert env.session._declared_execution_spec_v1 is input_v1.execution
            assert env.session._drive_receipt.provenance_kind == "synthetic_fixture"
            assert env.state.control_step == 0
            assert env.state.simulation_time == 0.0
            assert env.session._last_readback.free_joint_readback[
                "square-peg-instance/peg1"
            ].linear_velocity_world_at_com_m_s == (0.0, 0.0, 0.0)
            assert env.session._native_io.execution_provenance_kind == "synthetic_fixture"
            path = output_root / f"episode-{episode:02d}.h5"
            env.start_recording(path)
            for interval in range(4):
                observation, _reward, _terminated, _truncated, info = env.step(_action_for(env, interval))
                public_boundaries.append(_public_boundary_witness(observation, info))
            result = env.finish_recording("horizon")
            assert result["transition_count"] == 4 and result["observation_count"] == 5
            assert created[-1].advances == 20
            loaded = load_structured_control_records_h5(path)
            assert loaded["transition_count"] == 4 and loaded["observation_count"] == 5
            execution_classes = [
                writer["applied_control"]["payload"]["native_io_execution_class"]
                for transition in loaded["structured_controls"]
                for writer in transition.writer_controls
            ]
            assert execution_classes == ["synthetic_fixture_no_physics"] * 4
            profile = loaded["env_meta"]["reference_profile"]
            assert profile["profile_id"] == "f04-local-source-synthetic-io-s1-v1"
            assert profile["provenance_kind"] == "synthetic_fixture"
            assert profile["runtime_admitted"] is False
            assert profile["source_validation_provenance_kind"] == "local-validated"
            assert profile["execution_identity_sha256"] == input_v1.execution.identity_hash
            assert path.stat().st_size <= 32 * 1024 * 1024
            witness = {
                "schema_version": "f04-public-boundary-witness-v1",
                "witness_source": "SelectedReferenceEnv public reset/step observation and info return values",
                "family": family, "episode_ordinal": episode,
                "h5_path": str(path),
                "h5_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "transition_count": result["transition_count"],
                "observation_count": result["observation_count"],
                "public_boundaries": public_boundaries,
            }
            (output_root / f"episode-{episode:02d}.public-boundary-witness.json").write_text(
                json.dumps(witness, sort_keys=True, indent=2, allow_nan=False) + "\n"
            )
            h5_paths.append(path)
        assert len(created) == 2
        assert created[0].close_count == 1
        assert created[1].close_count == 0
    finally:
        monkeypatch.setattr(builtins, "__import__", original_import)
        env.close()
    assert created[1].close_count == 1
    assert created[1].runtime_close_count == 1
    assert sum(path.stat().st_size for path in h5_paths) <= 128 * 1024 * 1024
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in (set(sys.modules) - before_modules) for prefix in provider_imports
    )
    (output_root / "s1_receipt.json").write_text(json.dumps({
        "schema_version": "f04-provider-free-core-s1-v1", "passed": True,
        "family": family, "episodes": 2, "transitions_per_episode": 4,
        "observations_per_episode": 5, "synthetic_advances_per_episode": 20,
        "h5": [{"path": p.name, "size_bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in h5_paths],
        "runtime_provenance": "synthetic_fixture", "runtime_admitted": False,
        "native_imports": [], "kit_started": False, "physics_steps": 0,
    }, indent=2) + "\n")


@pytest.mark.parametrize("family,mutated_relative", (
    ("local_official_panda_r007", "metadata/physx_task_scene_recipe.json"),
    ("local_official_panda_r007", "metadata/f04_local_usd_checker.py"),
    ("local_official_panda_r007", "metadata/local_validation_report.json"),
    ("local_official_panda_r007", "derived/panda.usda"),
    ("local_menagerie_panda_r007", "support/official/report.json"),
    ("local_menagerie_panda_r007", "support/converter_manifest.json"),
))
def test_f04_local_delivery_tampering_fails_core_loader(tmp_path, family, mutated_relative):
    from task_env.assembly.usd_delivery import load_usd_asset_delivery

    root = (Path(__file__).resolve().parents[3] /
            "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f04_002/assets" /
            family)
    copied = tmp_path / family
    shutil.copytree(root, copied)
    target = copied / mutated_relative
    original = target.read_bytes()
    target.write_bytes(original + b"\n# F04 S1 tamper\n")
    with pytest.raises((ValueError, OSError)):
        load_usd_asset_delivery(copied / "usd_delivery.json")
