"""F05 Menagerie source/GeoPhys control S1 through the existing Core owners."""
from __future__ import annotations

import builtins
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import h5py
import numpy as np
import pytest
import yaml

from task_env.recorders import load_structured_control_records_h5
from task_env.diagnostics.tasks.f04_candidate_s1_support import _action_for
from task_env.diagnostics.tasks.f05_source_control_support import (
    SyntheticGeoPhysNativeIO, build_input, lower_public_model,
)


def _read_meta_json(dataset):
    value = dataset[()]
    return json.loads(value.decode("utf-8") if isinstance(value, bytes) else str(value))


def _write_meta_json(dataset, value):
    dataset[()] = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _read_meta_yaml(dataset):
    value = dataset[()]
    return yaml.safe_load(value.decode("utf-8") if isinstance(value, bytes) else str(value))


def _write_meta_yaml(dataset, value):
    dataset[()] = yaml.safe_dump(value, sort_keys=True, allow_unicode=True)


def _run_independent_reader(h5_path, witness_path, contract_path):
    reader = Path(__file__).with_name("f05_independent_h5_reader.py")
    argv = [sys.executable, str(reader), "--h5", str(h5_path),
            "--witness", str(witness_path), "--contract", str(contract_path)]
    result = subprocess.run(argv, cwd=Path(__file__).resolve().parents[3],
                            capture_output=True, text=True, timeout=30, check=False)
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception as error:
        raise AssertionError(f"independent reader did not return JSON: {result.stdout!r} {result.stderr!r}") from error
    return result, payload


def _observation_digest(observation):
    fields = {}
    def visit(value, prefix=""):
        if isinstance(value, dict):
            for key in sorted(value):
                visit(value[key], f"{prefix}/{key}" if prefix else str(key))
            return
        array = np.asarray(value)
        fields[prefix] = {
            "dtype": array.dtype.str,
            "shape": list(array.shape),
            "bytes_sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest(),
        }
    visit(observation)
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest(), fields


def _public_boundary(observation, info):
    digest, fields = _observation_digest(observation)
    required = ("state_boundary_identity", "state_boundary_id", "state_sample_clock",
                "canonical_state_view_v1", "control_step", "simulation_time_s")
    if any(key not in info for key in required):
        raise AssertionError(f"public reset/step omitted boundary witness fields: {required}")
    return {
        "control_step": int(info["control_step"]),
        "simulation_time_s": float(info["simulation_time_s"]),
        "state_boundary_identity": info["state_boundary_identity"],
        "state_boundary_id": info["state_boundary_id"],
        "state_sample_clock": info["state_sample_clock"],
        "canonical_state_view_v1": info["canonical_state_view_v1"],
        "observation_identity_sha256": digest,
        "observation_fields": fields,
    }


def test_f05_menagerie_geo_usd_same_core_env_two_episode_synthetic_s1(tmp_path):
    """Only the bottom NativeRuntimeIO port is synthetic; Core stays real."""
    from task_env.registry import make_env
    from task_env.runtime.sessions import api
    from task_env.runtime.sessions.geophys_source import compile_geophys_usd_position_drive_receipt

    input_v1, setup = build_input("menagerie-panda")
    repo_root = Path(__file__).resolve().parents[3]
    support_module = sys.modules["task_env.diagnostics.tasks.f05_source_control_support"]
    support_path = Path(support_module.__file__).resolve()
    reader_path = Path(__file__).with_name("f05_independent_h5_reader.py").resolve()
    for owner_path in (Path(__file__).resolve(), support_path, reader_path):
        owner_path.relative_to(repo_root)
    setup["f05_tracked_owner_source_proof"] = {
        "test": {
            "path": str(Path(__file__).resolve()),
            "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "support": {
            "module": support_module.__name__,
            "path": str(support_path),
            "sha256": hashlib.sha256(support_path.read_bytes()).hexdigest(),
        },
        "independent_reader": {
            "path": str(reader_path),
            "sha256": hashlib.sha256(reader_path.read_bytes()).hexdigest(),
            "invocation": "absolute sibling source path in a fresh subprocess",
        },
        "all_sources_under_repo": True,
        "diagnostic_owner": "task_env/diagnostics/tasks",
        "ignored_output_python_imports": [],
    }
    created = []
    def lowest_io_factory(*, artifact, execution, source, drive_receipt, input_v1):
        imported, model, _bridge, _report = lower_public_model(source)
        independently_compiled = compile_geophys_usd_position_drive_receipt(
            source, imported, model, execution,
            provider_build_identity=drive_receipt.provider_build_identity,
            provenance_kind="synthetic_fixture",
            host_model_producer_identity=input_v1.host_model_producer_identity,
        )
        if independently_compiled.identity_sha256 != drive_receipt.identity_sha256:
            raise AssertionError("S1 fixture receipt differs from independently lowered public host model")
        io = SyntheticGeoPhysNativeIO(
            artifact=artifact, execution=execution, source=source,
            drive_receipt=independently_compiled, input_v1=input_v1,
        )
        created.append(io)
        return io

    output = Path(os.environ["F05_S1_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    runtime_source = input_v1.runtime_source
    task_scene = runtime_source.scene_source
    delivery = task_scene.loaded_delivery.delivery
    contract = {
        "schema_version": "f05-s1-independent-input-contract-v2",
        "family": "menagerie-panda",
        "source_id": runtime_source.source_id,
        "source_closure_sha256": runtime_source.source_closure_digest,
        "task_source_identity_sha256": input_v1.task_source.identity_hash,
        "task_artifact_identity_sha256": input_v1.artifact.identity_hash,
        "scene_identity_sha256": runtime_source.scene_definition.identity_hash,
        "execution_identity_sha256": input_v1.execution.identity_hash,
        "representation": {
            "identity_sha256": task_scene.representation.identity_hash,
            "provider": task_scene.representation.provider,
            "provider_build_identity": task_scene.representation.provider_build_identity,
            "runtime_admitted": task_scene.representation.runtime_admitted,
            "source_verified": task_scene.source_verified,
            "provenance_kind": delivery.provenance_kind,
            "locally_validated": task_scene.locally_validated,
            "requested_target_build_identity": task_scene.representation.provider_build_identity,
        },
        "host_model_producer_identity": input_v1.host_model_producer_identity.to_mapping(),
        "host_model_producer_identity_sha256": input_v1.host_model_producer_identity.identity_sha256,
        "delivery": {
            "source_reference": delivery.asset_definition.source_reference,
            "asset_identity_sha256": delivery.asset_identity_hash,
            "delivery_sha256": delivery.delivery_sha256,
            "closure_sha256": delivery.closure_sha256,
            "source_revision": delivery.source_revision,
            "entry_file": delivery.entry_file,
            "entry_sha256": hashlib.sha256(
                task_scene.loaded_delivery.file_bytes[delivery.entry_file]
            ).hexdigest(),
            "validation_report_sha256": task_scene.validation_report_identity_sha256,
        },
        "receipt_identity_sha256": input_v1.native_drive_receipt.identity_sha256,
        "public_model_identity_sha256": input_v1.native_drive_receipt.public_model_identity_sha256,
        "native_position_drive_receipt": asdict(input_v1.native_drive_receipt),
        "native_dof_order": [row.native_dof_name for row in input_v1.native_drive_receipt.drives],
        "physics_dt_s": input_v1.artifact.timebase.physics_dt,
        "control_substeps": input_v1.artifact.timebase.control_substeps,
    }
    (output / "input_contract.json").write_text(
        json.dumps(contract, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )
    env = make_env(
        "panda-position-servo-candidate-v1",
        config={"versioned_input": input_v1, "horizon": 8},
    )
    paths = []
    witnesses = []
    low_level_runs = []
    with api._f05_s1_native_io_context(input_v1, lowest_io_factory):
        try:
            for episode in range(2):
                observation, info = env.reset(seed=input_v1.reset_plan.reset_sample.task_seed)
                assert env.execution is input_v1.execution
                assert env.session._declared_execution_spec_v1 is input_v1.execution
                assert env.session._drive_receipt.identity_sha256 == input_v1.native_drive_receipt.identity_sha256
                assert env.session._drive_receipt.provenance_kind == "synthetic_fixture"
                assert env.session._native_io.execution_provenance_kind == "synthetic_fixture"
                assert env.state.control_step == 0
                assert env.state.simulation_time == 0.0
                public = [_public_boundary(observation, info)]
                path = output / f"episode-{episode:02d}.h5"
                env.start_recording(path)
                for interval in range(8):
                    observation, _reward, _terminated, _truncated, info = env.step(
                        _action_for(env, interval % 4)
                    )
                    public.append(_public_boundary(observation, info))
                result = env.finish_recording("horizon")
                assert result["transition_count"] == 8
                assert result["observation_count"] == 9
                assert created[-1].advance_count == 40
                assert created[-1].reset_count == 1
                for operation_index, operation in enumerate(created[-1].operations):
                    if operation["op"] in {"metadata", "read_state"}:
                        assert operation["advance_count"] == sum(
                            item["op"] == "advance" for item in created[-1].operations[:operation_index]
                        )
                assert all(np.isfinite(value) for row in created[-1].control_history
                           for control in row["controls"] for value in control[2:])
                low_level_runs.append({
                    "episode_ordinal": episode,
                    "execution_provenance_kind": created[-1].execution_provenance_kind,
                    "operation_log": created[-1].operations,
                    "target_history": created[-1].target_history,
                    "control_history": created[-1].control_history,
                })
                loaded = load_structured_control_records_h5(path)
                assert loaded["transition_count"] == 8
                assert loaded["observation_count"] == 9
                profile = loaded["env_meta"]["reference_profile"]
                assert profile["profile_id"] == "f05-geophys-usd-position-synthetic-io-s1-v1"
                assert profile["provenance_kind"] == "synthetic_fixture"
                assert profile["runtime_admitted"] is False
                assert profile["source_validation_provenance_kind"] == "local-validated"
                assert profile["execution_identity_sha256"] == input_v1.execution.identity_hash
                assert path.stat().st_size <= 32 * 1024 * 1024
                witnesses.append({
                    "schema_version": "f05-public-boundary-witness-v1",
                    "witness_source": "SelectedReferenceEnv public reset/step observation and info",
                    "episode_ordinal": episode,
                    "h5_path": str(path),
                    "h5_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "transition_count": result["transition_count"],
                    "observation_count": result["observation_count"],
                    "public_boundaries": public,
                })
                paths.append(path)
            assert len(created) == 2
            assert created[0].close_count == 1
            assert created[1].close_count == 0
        finally:
            env.close()
    assert created[1].close_count == 1
    assert len(paths) == 2
    assert sum(path.stat().st_size for path in paths) <= 128 * 1024 * 1024
    assert all(len(item["public_boundaries"]) == 9 for item in witnesses)
    assert setup["public_model_counts"]["dofs"] == 15
    assert setup["public_model_counts"]["actuators"] == 9
    (output / "public_boundary_witnesses.json").write_text(
        json.dumps(witnesses, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output / "producer_setup.json").write_text(
        json.dumps(setup, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output / "low_level_synthetic_io_log.json").write_text(
        json.dumps(low_level_runs, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    independent_results = []
    reader_source_identity = {
        "path": str(reader_path),
        "sha256": hashlib.sha256(reader_path.read_bytes()).hexdigest(),
    }
    contract_path = output / "input_contract.json"
    witness_paths = [output / "public_boundary_witnesses.json"]
    for episode, path in enumerate(paths):
        one_witness = output / f"episode-{episode:02d}.public-boundary-witness.json"
        one_witness.write_text(json.dumps(witnesses[episode], sort_keys=True, indent=2, allow_nan=False) + "\n",
                               encoding="utf-8")
        result, payload = _run_independent_reader(path, one_witness, contract_path)
        assert result.returncode == 0 and payload.get("accepted") is True
        assert payload["verified_boundary_rows"] == 9
        assert payload["verified_observation_rows"] == 9
        assert payload["verified_transitions"] == 8
        assert payload["verified_synthetic_advances"] == 40
        independent_results.append({"kind": "valid", "episode_ordinal": episode,
                                    "reader_source_identity": reader_source_identity,
                                    "returncode": result.returncode, "reader": payload})

    source_h5 = paths[0]
    source_witness = output / "episode-00.public-boundary-witness.json"
    tamper_root = output / "reader_tamper_copies"
    tamper_root.mkdir(exist_ok=True)
    tamper_results = []
    def witness_bound_to_copy(copied, name):
        altered = json.loads(source_witness.read_text(encoding="utf-8"))
        altered["h5_path"] = str(copied.resolve())
        altered["h5_sha256"] = hashlib.sha256(copied.read_bytes()).hexdigest()
        target = tamper_root / f"{name}.public-boundary-witness.json"
        target.write_text(json.dumps(altered, sort_keys=True, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")
        return target
    cases = {
        "final_observation": ("observation_witness", lambda root: root["obs/state/joint_position"].__setitem__((-1, 0), float(root["obs/state/joint_position"][-1, 0]) + 0.0125)),
        "final_boundary_digest": ("boundary_digest", lambda root: root["obs/state/boundary_identity_sha256"].__setitem__((-1, 0), int(root["obs/state/boundary_identity_sha256"][-1, 0]) ^ 1)),
    }
    for name, (expected_reason, mutate) in cases.items():
        copied = tamper_root / f"{name}.h5"
        shutil.copy2(source_h5, copied)
        with h5py.File(copied, "r+") as root:
            mutate(root)
        copied_witness = witness_bound_to_copy(copied, name)
        result, payload = _run_independent_reader(copied, copied_witness, contract_path)
        assert result.returncode == 2 and payload.get("reason") == expected_reason
        tamper_results.append({"kind": name, "reader_source_identity": reader_source_identity,
                               "returncode": result.returncode, "reader": payload})

    for name, expected_reason, dataset_name, mutator in (
        ("episode_identity", "episode_outcome", "meta/episode_outcome_v1_json", lambda data: data.__setitem__("episode_id", "episode-tampered")),
        ("source_identity", "native_io_metadata", "meta/env_meta", lambda data: data["reference_profile"]["native_runtime_io_metadata"].__setitem__("source_id", "tampered-source")),
        ("receipt_identity", "receipt_identity", "meta/env_meta", lambda data: data["reference_profile"].__setitem__("native_position_drive_receipt_identity_sha256", "0" * 64)),
        ("ack_identity", "ack_identity", "meta/structured_controls_v1_json", lambda data: data[0]["writer_controls"][0]["applied_control"]["payload"]["native_position_write_ack_v1"].__setitem__("target_identity_sha256", "0" * 64)),
    ):
        copied = tamper_root / f"{name}.h5"
        shutil.copy2(source_h5, copied)
        with h5py.File(copied, "r+") as root:
            dataset = root[dataset_name]
            raw = dataset[()]
            decoded = (_read_meta_yaml(dataset) if dataset_name == "meta/env_meta"
                       else json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)))
            mutator(decoded)
            if dataset_name == "meta/env_meta":
                _write_meta_yaml(dataset, decoded)
            else:
                _write_meta_json(dataset, decoded)
        copied_witness = witness_bound_to_copy(copied, name)
        result, payload = _run_independent_reader(copied, copied_witness, contract_path)
        assert result.returncode == 2 and payload.get("reason") == expected_reason
        tamper_results.append({"kind": name, "reader_source_identity": reader_source_identity,
                               "returncode": result.returncode, "reader": payload})

    def state_row(mapping, row_index):
        return mapping["public_boundaries"][row_index]["canonical_state_view_v1"]

    def edit_typed_extension(copied, mutator):
        with h5py.File(copied, "r+") as root:
            dataset = root["meta/f05_public_typed_state_witness_v1_json"]
            extension = _read_meta_json(dataset)
            mutator(extension["rows"])
            _write_meta_json(dataset, extension)

    def save_witness_copy(copied, name, altered, mutation=None):
        altered["h5_path"] = str(copied.resolve())
        altered["h5_sha256"] = hashlib.sha256(copied.read_bytes()).hexdigest()
        if mutation is not None:
            mutation(altered)
        target = tamper_root / f"{name}.public-boundary-witness.json"
        target.write_text(json.dumps(altered, sort_keys=True, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")
        return target

    def run_typed_tamper(name, *, h5_mutation=None, witness_mutation=None,
                         expected_reason, contract_source=None, public_row=8):
        copied = tamper_root / f"{name}.h5"
        shutil.copy2(source_h5, copied)
        if h5_mutation is not None:
            edit_typed_extension(copied, h5_mutation)
        altered = json.loads(source_witness.read_text(encoding="utf-8"))
        if witness_mutation is not None:
            witness_mutation(altered)
        copied_witness = save_witness_copy(copied, name, altered)
        selected_contract = contract_source or contract_path
        result, payload = _run_independent_reader(copied, copied_witness, selected_contract)
        assert result.returncode == 2 and payload.get("reason") == expected_reason, (name, payload)
        tamper_results.append({"kind": name, "returncode": result.returncode, "reader": payload})

    def change_joint_position(mapping, row_index, joint_id, delta):
        row = next(item for item in state_row(mapping, row_index)["joints"]
                   if item["joint_id"] == joint_id)
        row["position"][0] += delta

    def change_joint_velocity(rows, row_index, joint_id, delta):
        state = rows[row_index]["canonical_state_view_v1"]
        row = next(item for item in state["joints"] if item["joint_id"] == joint_id)
        row["velocity"][0] += delta

    # Both H5 and public witness must agree on the typed row, then the
    # independent observation numeric comparison must reject the mismatch.
    run_typed_tamper(
        "typed_final_joint_position",
        h5_mutation=lambda rows: change_joint_position(
            {"public_boundaries": rows}, 8, "finger_joint1", 0.01),
        witness_mutation=lambda mapping: change_joint_position(
            mapping, 8, "finger_joint1", 0.01),
        expected_reason="typed_joint_observation",
    )
    # Velocity is part of the public typed state and persisted in the F05 H5
    # sidecar. It has no observation leaf, so compare both storage directions
    # independently against the captured public witness.
    run_typed_tamper(
        "typed_joint_velocity_h5",
        h5_mutation=lambda rows: change_joint_velocity(rows, 8, "finger_joint1", 0.01),
        expected_reason="typed_state_h5_mismatch",
    )
    run_typed_tamper(
        "typed_joint_velocity_public_witness",
        witness_mutation=lambda mapping: next(
            row for row in state_row(mapping, 8)["joints"] if row["joint_id"] == "finger_joint1"
        )["velocity"].__setitem__(0, state_row(mapping, 8)["joints"][0]["velocity"][0] + 0.01),
        expected_reason="typed_state_h5_mismatch",
    )

    def change_free_body_velocity(rows, row_index, delta):
        state = rows[row_index]["canonical_state_view_v1"]
        row = next(item for item in state["joints"] if item["joint_id"] == "floating_root")
        row["velocity"][0] += delta

    run_typed_tamper(
        "typed_free_body_velocity_h5",
        h5_mutation=lambda rows: change_free_body_velocity(rows, 8, 0.01),
        expected_reason="typed_state_h5_mismatch",
    )

    def change_free_body_unit(container, row_index):
        state = (container["rows"][row_index]["canonical_state_view_v1"]
                 if "rows" in container else state_row(container, row_index))
        row = next(item for item in state["joints"] if item["joint_id"] == "floating_root")
        row["velocity_representation"] = "meter_per_second"

    run_typed_tamper(
        "typed_wrong_free_body_velocity_unit",
        h5_mutation=lambda rows: change_free_body_unit({"rows": rows}, 8),
        witness_mutation=lambda mapping: change_free_body_unit(mapping, 8),
        expected_reason="typed_free_body_unit",
    )

    def mutate_hand_pose(container, row_index, delta):
        state = (container["rows"][row_index]["canonical_state_view_v1"]
                 if "rows" in container else state_row(container, row_index))
        hand = next(row for row in state["frames"]
                    if row["frame"] == {"entity_id": "panda-main", "frame_id": "hand"})
        hand["pose_world"]["position"][0] += delta

    run_typed_tamper(
        "typed_hand_pose_final",
        h5_mutation=lambda rows: mutate_hand_pose({"rows": rows}, 8, 0.01),
        witness_mutation=lambda mapping: mutate_hand_pose(mapping, 8, 0.01),
        expected_reason="typed_hand_pose",
    )

    def mutate_body_pose(container, row_index, delta):
        state = (container["rows"][row_index]["canonical_state_view_v1"]
                 if "rows" in container else state_row(container, row_index))
        body = next(row for row in state["frames"]
                    if row["frame"] == {"entity_id": "square-peg-instance", "frame_id": "peg1"})
        body["pose_world"]["position"][0] += delta
        free = next(row for row in state["joints"] if row["joint_id"] == "floating_root")
        free["position"][0] += delta

    run_typed_tamper(
        "typed_free_body_pose_final",
        h5_mutation=lambda rows: mutate_body_pose({"rows": rows}, 8, 0.01),
        witness_mutation=lambda mapping: mutate_body_pose(mapping, 8, 0.01),
        expected_reason="typed_free_body_pose",
    )

    def remove_finger(rows):
        rows[8]["canonical_state_view_v1"]["joints"] = [
            row for row in rows[8]["canonical_state_view_v1"]["joints"]
            if row["joint_id"] != "finger_joint1"
        ]

    run_typed_tamper(
        "typed_missing_canonical_joint",
        h5_mutation=remove_finger,
        witness_mutation=lambda mapping: remove_finger(mapping["public_boundaries"]),
        expected_reason="typed_joint_resources",
    )

    def change_joint_unit(container, row_index):
        state = (container["rows"][row_index]["canonical_state_view_v1"]
                 if "rows" in container else state_row(container, row_index))
        row = next(item for item in state["joints"] if item["joint_id"] == "joint1")
        row["position_representation"] = "meter"

    run_typed_tamper(
        "typed_wrong_joint_unit",
        h5_mutation=lambda rows: change_joint_unit({"rows": rows}, 8),
        witness_mutation=lambda mapping: change_joint_unit(mapping, 8),
        expected_reason="typed_joint_unit",
    )

    def swap_observed_arm_order(copied, mapping):
        with h5py.File(copied, "r+") as root:
            dataset = root["obs/state/joint_position"]
            row = np.asarray(dataset[8]).copy()
            row[[0, 1]] = row[[1, 0]]
            dataset[8] = row
            fields = {}
            def visit(name, item):
                if isinstance(item, h5py.Dataset):
                    value = np.asarray(item[8])
                    fields[name] = {"dtype": value.dtype.str, "shape": list(value.shape),
                                    "bytes_sha256": hashlib.sha256(value.tobytes(order="C")).hexdigest()}
            root["obs"].visititems(visit)
        mapping["public_boundaries"][8]["observation_fields"] = fields
        mapping["public_boundaries"][8]["observation_identity_sha256"] = hashlib.sha256(
            json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()

    copied = tamper_root / "typed_wrong_h5_dof_order.h5"
    shutil.copy2(source_h5, copied)
    altered = json.loads(source_witness.read_text(encoding="utf-8"))
    swap_observed_arm_order(copied, altered)
    copied_witness = save_witness_copy(copied, "typed_wrong_h5_dof_order", altered)
    result, payload = _run_independent_reader(copied, copied_witness, contract_path)
    assert result.returncode == 2 and payload.get("reason") == "typed_joint_observation", payload
    tamper_results.append({"kind": "typed_wrong_h5_dof_order",
                           "reader_source_identity": reader_source_identity,
                           "returncode": result.returncode,
                           "reader": payload})

    # Reset clock and final row coverage are checked directly, before a valid
    # decoder result can be reported.
    run_typed_tamper(
        "typed_reset_clock_error",
        witness_mutation=lambda mapping: mapping["public_boundaries"][0]["state_sample_clock"].__setitem__(
            "sample_index", 1),
        expected_reason="boundary_clock", public_row=0,
    )
    def remove_final_public_row(mapping):
        mapping["public_boundaries"] = mapping["public_boundaries"][:-1]
        mapping["observation_count"] -= 1
    run_typed_tamper(
        "typed_missing_final_public_observation",
        witness_mutation=remove_final_public_row,
        expected_reason="witness_count",
    )

    missing_final = tamper_root / "missing_final_h5_observation.h5"
    shutil.copy2(source_h5, missing_final)
    with h5py.File(missing_final, "r+") as root:
        datasets = []
        root["obs"].visititems(lambda name, item: datasets.append((name, item[...], dict(item.attrs)))
                               if isinstance(item, h5py.Dataset) else None)
        for name, value, attrs in datasets:
            if value.ndim and value.shape[0] == 9:
                parent_path, _, leaf = name.rpartition("/")
                parent = root["obs/" + parent_path] if parent_path else root["obs"]
                del parent[leaf]
                replacement = parent.create_dataset(leaf, data=value[:-1])
                for key, item in attrs.items():
                    replacement.attrs[key] = item
        root.attrs["observation_count"] = 8
    missing_witness = save_witness_copy(
        missing_final, "missing_final_h5_observation",
        json.loads(source_witness.read_text(encoding="utf-8")),
    )
    result, payload = _run_independent_reader(missing_final, missing_witness, contract_path)
    assert result.returncode == 2 and payload.get("reason") == "t_plus_one_count", payload
    tamper_results.append({"kind": "missing_final_h5_observation",
                           "reader_source_identity": reader_source_identity,
                           "returncode": result.returncode,
                           "reader": payload})

    stale_final = tamper_root / "stale_final_h5_observation.h5"
    shutil.copy2(source_h5, stale_final)
    with h5py.File(stale_final, "r+") as root:
        datasets = []
        root["obs"].visititems(lambda name, item: datasets.append(name)
                               if isinstance(item, h5py.Dataset) and item.shape and item.shape[0] == 9 else None)
        for name in datasets:
            dataset = root["obs/" + name]
            dataset[-1] = dataset[-2]
    stale_witness = json.loads(source_witness.read_text(encoding="utf-8"))
    with h5py.File(stale_final, "r") as root:
        fields = {}
        def visit_stale(name, item):
            if isinstance(item, h5py.Dataset):
                value = np.asarray(item[8])
                fields[name] = {"dtype": value.dtype.str, "shape": list(value.shape),
                                "bytes_sha256": hashlib.sha256(value.tobytes(order="C")).hexdigest()}
        root["obs"].visititems(visit_stale)
    stale_witness["public_boundaries"][8]["observation_fields"] = fields
    stale_witness["public_boundaries"][8]["observation_identity_sha256"] = hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    stale_witness_path = save_witness_copy(stale_final, "stale_final_h5_observation", stale_witness)
    result, payload = _run_independent_reader(stale_final, stale_witness_path, contract_path)
    assert result.returncode == 2 and payload.get("reason") in {
        "boundary_digest", "typed_joint_observation", "typed_hand_pose", "typed_free_body_pose",
    }, payload
    tamper_results.append({"kind": "stale_final_h5_observation",
                           "reader_source_identity": reader_source_identity,
                           "returncode": result.returncode,
                           "reader": payload})

    # Sol's frozen attempt001 counterexample remains a regression oracle: the
    # old closed H5 is still accepted unchanged, while its witness-only typed
    # position mutation must now be rejected.
    repo_root = Path(__file__).resolve().parents[3]
    handoff_root = repo_root / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001"
    old_root = handoff_root / "f05_001/evidence/s1/menagerie_run080"
    old_h5 = old_root / "episode-00.h5"
    old_witness = old_root / "episode-00.public-boundary-witness.json"
    old_contract = old_root / "input_contract.json"
    old_result, old_payload = _run_independent_reader(old_h5, old_witness, old_contract)
    assert old_result.returncode == 0 and old_payload.get("accepted") is True
    old_tampered = json.loads(old_witness.read_text(encoding="utf-8"))
    old_state = old_tampered["public_boundaries"][-1]["canonical_state_view_v1"]
    old_finger = next(row for row in old_state["joints"] if row["joint_id"] == "finger_joint1")
    old_finger["position"][0] = 0.028999999105930326
    old_tampered_path = tamper_root / "sol_old_typed_position_counterexample.public-boundary-witness.json"
    old_tampered_path.write_text(json.dumps(old_tampered, sort_keys=True, indent=2, allow_nan=False) + "\n",
                                 encoding="utf-8")
    old_bad_result, old_bad_payload = _run_independent_reader(old_h5, old_tampered_path, old_contract)
    assert old_bad_result.returncode == 2 and old_bad_payload.get("reason") == "typed_joint_observation"
    tamper_results.append({"kind": "sol_old_typed_position_counterexample",
                           "reader_source_identity": reader_source_identity,
                           "returncode": old_bad_result.returncode,
                           "reader": old_bad_payload})

    from task_env.runtime.sessions.leaf_control import GeoPhysHostModelProducerIdentityV1

    def run_contract_tamper(name, mutator, expected_reason):
        altered = json.loads(contract_path.read_text(encoding="utf-8"))
        mutator(altered)
        contract_copy = tamper_root / f"{name}.input-contract.json"
        contract_copy.write_text(json.dumps(altered, sort_keys=True, indent=2, allow_nan=False) + "\n",
                                 encoding="utf-8")
        result, payload = _run_independent_reader(source_h5, source_witness, contract_copy)
        assert result.returncode == 2 and payload.get("reason") == expected_reason, (name, payload)
        tamper_results.append({"kind": name, "reader_source_identity": reader_source_identity,
                               "returncode": result.returncode, "reader": payload})

    def replace_producer_identity(contract, *, commit=None, module_hash=None,
                                  origin_url=None, requested_target_build_identity=None):
        old = contract["host_model_producer_identity"]
        rows = [tuple(row) for row in old["module_sources"]]
        if module_hash is not None:
            rows[0] = (rows[0][0], rows[0][1], module_hash)
        identity = GeoPhysHostModelProducerIdentityV1(
            old["schema_version"],
            requested_target_build_identity or old["requested_target_build_identity"],
            old["repository_root"], origin_url or old["origin_url"],
            commit or old["commit_sha"], old["worktree_clean"], tuple(rows),
        )
        contract["host_model_producer_identity"] = identity.to_mapping()
        contract["host_model_producer_identity_sha256"] = identity.identity_sha256

    def downgrade_producer_contract(contract):
        contract["schema_version"] = "f05-s1-independent-input-contract-v1"
        for key in ("host_model_producer_identity", "host_model_producer_identity_sha256"):
            contract.pop(key, None)

    run_contract_tamper("producer_contract_schema_downgrade", downgrade_producer_contract,
                        "input_contract_schema")

    run_contract_tamper(
        "producer_wrong_head",
        lambda contract: replace_producer_identity(contract, commit="0" * len(
            contract["host_model_producer_identity"]["commit_sha"])),
        "producer_identity",
    )
    run_contract_tamper(
        "producer_wrong_module_bytes",
        lambda contract: replace_producer_identity(contract, module_hash="0" * 64),
        "producer_identity",
    )

    def wrong_declared_import_root(contract):
        mapping = contract["host_model_producer_identity"]
        mapping["repository_root"] = "/home/lly/Program_Files/Geochora"
        payload = {key: value for key, value in mapping.items() if key != "identity_sha256"}
        mapping["identity_sha256"] = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")).hexdigest()
        contract["host_model_producer_identity_sha256"] = mapping["identity_sha256"]

    run_contract_tamper("producer_wrong_import_root", wrong_declared_import_root,
                        "producer_identity")
    run_contract_tamper(
        "producer_wrong_origin_url",
        lambda contract: replace_producer_identity(
            contract, origin_url="https://example.invalid/unrelated/GeoPhys.git"),
        "producer_identity",
    )
    run_contract_tamper(
        "producer_wrong_requested_target_build",
        lambda contract: replace_producer_identity(
            contract, requested_target_build_identity="geophys-unrelated-target-build"),
        "producer_identity",
    )
    run_contract_tamper(
        "old_pinned_receipt_graft",
        lambda contract: contract.__setitem__("receipt_identity_sha256",
                                                "1253ea4a222e52bc2393bf3afd89b0b8358daf59f16d9c086647a00155bc9289"),
        "receipt_identity",
    )
    run_contract_tamper(
        "public_model_identity_graft",
        lambda contract: contract.__setitem__("public_model_identity_sha256", "0" * 64),
        "public_model_identity",
    )
    run_contract_tamper(
        "representation_options_identity_graft",
        lambda contract: contract["representation"].__setitem__("identity_sha256", "0" * 64),
        "source_identity",
    )

    (output / "independent_reader_results.json").write_text(
        json.dumps({"valid": independent_results, "tamper_rejections": tamper_results},
                   sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("failure", "faults", "phase"),
    (
        ("startup_metadata", {"metadata_error": True}, "reset"),
        ("partial_reset", {"partial_reset": True}, "reset"),
        ("snapshot_readback", {"read_state_error_at": 4}, "step"),
        ("prewrite", {"prewrite_error": True}, "step"),
        ("partial_apply", {"partial_apply": True}, "step"),
        ("missing_ack", {"missing_ack": True}, "step"),
        ("advance_interruption", {"advance_error_at": 1}, "step"),
        ("close", {"close_error": True}, "close"),
    ),
)
def test_f05_s1_core_faults_latch_primary_and_release_low_io_once(failure, faults, phase):
    """Faults enter through the bottom I/O port while Core owners stay active."""
    from task_env.registry import make_env
    from task_env.runtime.sessions import api
    from task_env.runtime.sessions.geophys_source import compile_geophys_usd_position_drive_receipt

    input_v1, _setup = build_input("menagerie-panda")
    created = []

    def lowest_io_factory(*, artifact, execution, source, drive_receipt, input_v1):
        imported, model, _bridge, _report = lower_public_model(source)
        independently_compiled = compile_geophys_usd_position_drive_receipt(
            source, imported, model, execution,
            provider_build_identity=drive_receipt.provider_build_identity,
            provenance_kind="synthetic_fixture",
            host_model_producer_identity=input_v1.host_model_producer_identity,
        )
        if independently_compiled.identity_sha256 != drive_receipt.identity_sha256:
            raise AssertionError("fault S1 receipt differs from independently lowered public host model")
        io = SyntheticGeoPhysNativeIO(
            artifact=artifact, execution=execution, source=source,
            drive_receipt=independently_compiled, input_v1=input_v1, faults=faults,
        )
        created.append(io)
        return io

    env = make_env(
        "panda-position-servo-candidate-v1",
        config={"versioned_input": input_v1, "horizon": 2},
    )
    primary = None
    try:
        with api._f05_s1_native_io_context(input_v1, lowest_io_factory):
            if phase == "close":
                env.reset(seed=input_v1.reset_plan.reset_sample.task_seed)
                with pytest.raises(RuntimeError, match="close sentinel") as caught:
                    env.close()
                primary = caught.value
            elif phase == "reset":
                with pytest.raises((RuntimeError, ValueError)) as caught:
                    env.reset(seed=input_v1.reset_plan.reset_sample.task_seed)
                primary = caught.value
                assert env._execution_fault is not None
                assert env.session is None
            else:
                env.reset(seed=input_v1.reset_plan.reset_sample.task_seed)
                with pytest.raises((RuntimeError, TypeError, ValueError)) as caught:
                    env.step(_action_for(env, 0))
                primary = caught.value
                assert env._execution_fault is not None
                assert env.session is not None
    finally:
        if not env._closed:
            env.close()
    assert primary is not None
    assert created and created[0].close_count == 1
    if failure == "close":
        assert "close sentinel" in str(primary)
    else:
        assert "close sentinel" not in str(primary)
    result_root = Path(os.environ["F05_FAULT_OUTPUT"])
    result_root.mkdir(parents=True, exist_ok=True)
    result_path = result_root / f"{failure}.json"
    result_path.write_text(json.dumps({
        "failure": failure, "phase": phase, "faults": faults,
        "primary_type": type(primary).__name__, "primary": str(primary),
        "execution_fault": None if env._execution_fault is None else env._execution_fault.to_mapping(),
        "low_io_close_count": created[0].close_count,
        "low_io_operations": created[0].operations,
    }, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def test_f05_geophys_drive_numeric_oracle_units_offsets_and_unsupported_law(tmp_path):
    """Check public-model mapping against an independent affine-force oracle."""
    from types import SimpleNamespace

    from task_env.artifacts import JointReference
    from task_env.runtime.sessions.geophys_source import (
        inspect_usd_position_drive_model,
    )
    from task_env.runtime.sessions.leaf_control import (
        GeoPhysUsdPositionDriveReceiptV1, GeoPhysUsdPositionDriveV1,
    )
    from task_env.diagnostics.tasks.f05_source_control_support import build_input, lower_public_model

    input_v1, _setup = build_input("menagerie-panda")
    source = input_v1.runtime_source
    imported, model, _bridge, _report = lower_public_model(source)
    actual_receipt = input_v1.native_drive_receipt
    actual_rows = inspect_usd_position_drive_model(source, imported, model)["rows"]
    data = model.joint_data
    actual_oracle = []
    ir_joints = {
        str(joint.dynamics.get("source_name")): joint
        for joint in imported.ir.joints if joint.dynamics.get("source_name")
    }
    for row in actual_rows:
        drive = ir_joints[row["native_joint"]].dynamics.to_dict()["usd_drives"][0]
        angular = drive["axis"] == "angular"
        coordinate_scale = np.pi / 180.0 if angular else float(imported.ir.metadata.length_unit_m)
        effort_scale = float(imported.ir.metadata.mass_unit_kg) * float(imported.ir.metadata.length_unit_m) ** (2 if angular else 1)
        gain_scale = effort_scale / coordinate_scale
        q_index = int(data["name_to_joint"][row["native_joint"]])
        actuator_index = int(data["name_to_actuator"][row["native_actuator"]])
        q0 = float(np.asarray(data["qpos0"])[np.asarray(data["jnt_qposadr"])[q_index]])
        k = float(drive["stiffness"]) * gain_scale
        d = float(drive["damping"]) * gain_scale
        scale = k * float(drive["target_position"]) * coordinate_scale
        scale += d * float(drive["target_velocity"]) * coordinate_scale
        cap = None if drive["max_force"] is None else float(drive["max_force"]) * effort_scale
        assert row["position_unit"] == ("radian" if angular else "meter")
        assert np.isclose(-np.asarray(data["actuator_biasprm"])[actuator_index, 1], k, rtol=1e-5, atol=1e-5)
        assert np.isclose(-np.asarray(data["actuator_biasprm"])[actuator_index, 2], d, rtol=1e-5, atol=1e-5)
        assert np.isclose(np.asarray(data["actuator_biasprm"])[actuator_index, 0], scale, rtol=1e-5, atol=1e-5)
        assert np.isclose(row["joint_q0"], q0, rtol=0.0, atol=1e-12)
        if cap is not None:
            assert np.allclose(row["compiled_force_range"], (-cap, cap), rtol=1e-5, atol=1e-5)
        actual_oracle.append({
            "joint": row["canonical_joint"], "unit": row["position_unit"],
            "coordinate_scale": coordinate_scale, "effort_scale": effort_scale,
            "stiffness_compiled": k, "damping_compiled": d,
            "source_bias0": scale, "q0": q0, "force_cap": cap,
        })

    # A separate numeric vector spans nonzero authored rest targets/velocity,
    # affine gain, coordinate offset, q0, two length/mass systems, and both
    # angular and prismatic coordinates. It checks the receipt consumer's
    # ctrl mapping against the public law f = gain*ctrl+b0-k*q-d*qd.
    canonical = [f"panda-main/joint{i}" for i in range(1, 8)] + [
        "panda-main/finger_joint1", "panda-main/finger_joint2",
    ]
    rows = []
    oracle_units = []
    for i, semantic in enumerate(canonical):
        angular = i < 7
        length_m, mass_kg = ((0.01, 0.25) if i % 2 == 0 else (0.4, 3.0))
        coordinate_scale = np.pi / 180.0 if angular else length_m
        effort_scale = mass_kg * length_m ** (2 if angular else 1)
        gain_scale = effort_scale / coordinate_scale
        authored_k, authored_d = 43.0 + i, 5.0 + i
        stiffness, damping = authored_k * gain_scale, authored_d * gain_scale
        authored_rest = 0.17 if angular else 0.012
        authored_rest_velocity = -0.09 if angular else 0.004
        bias0 = stiffness * authored_rest * coordinate_scale + damping * authored_rest_velocity * coordinate_scale
        name = f"usd_joint_{i}"
        dof_index = (4 * i) % 9
        actuator_index = (5 * i + 1) % 9
        finger = semantic.endswith(("finger_joint1", "finger_joint2"))
        rows.append(GeoPhysUsdPositionDriveV1(
            "geophys-usd-position-drive-v1", JointReference("panda-main", semantic.split("/", 1)[1]),
            name, dof_index, f"actuator_{i}", actuator_index,
            "meter" if finger else "radian", 0.0 if finger else -4.0, 0.04 if finger else 4.0,
            1.25 + i, bias0, stiffness, damping,
            authored_rest_velocity * coordinate_scale,
            0.0015 if finger else 0.013, 0.02 if finger else 0.006,
            True, -1e9, 1e9, True, -1000.0 - i, 1000.0 + i,
        ))
        oracle_units.append({
            "joint": semantic, "length_unit_m": length_m, "mass_unit_kg": mass_kg,
            "coordinate_scale": coordinate_scale, "effort_scale": effort_scale,
            "gain_scale": gain_scale, "authored_rest_target": authored_rest,
            "authored_rest_velocity": authored_rest_velocity,
            "coordinate_offset": rows[-1].coordinate_offset, "joint_q0": rows[-1].joint_q0,
        })
    execution = input_v1.execution
    receipt = GeoPhysUsdPositionDriveReceiptV1(
        "geophys-usd-position-drive-receipt-v1", "synthetic_fixture",
        source.scene_definition.identity_hash, source.source_closure_digest,
        actual_receipt.public_model_identity_sha256, execution.identity_hash,
        actual_receipt.provider_build_identity, execution.physics_profile,
        execution.physics_backend, execution.physics_device, execution.determinism_mode,
        0.002, 5, "panda-main/position-servo-v1", 9, tuple(reversed(rows)),
    )
    arm_targets = {f"panda-main/joint{i}": 0.11 + 0.01 * i for i in range(1, 8)}
    targets = receipt.commands(arm_targets, 0.06)
    assert tuple(index for index, _name, _value in targets) == tuple(range(9))
    assert [value for _index, name, value in targets if name in {"usd_joint_7", "usd_joint_8"}] == [0.03, 0.03]
    actual_controls = receipt.control_inputs(targets)
    target_by_name = {name: value for _index, name, value in targets}
    row_by_name = {row.native_dof_name: row for row in rows}
    expected_controls = []
    for row in rows:
        q_target = target_by_name[row.native_dof_name] + row.coordinate_offset
        ctrl = (row.stiffness * q_target + row.damping * row.desired_velocity - row.bias0) / row.gain
        public_force = row.gain * ctrl + row.bias0 - row.stiffness * q_target - row.damping * row.desired_velocity
        assert abs(public_force) <= 1e-10 * max(1.0, abs(row.bias0), abs(row.stiffness * q_target))
        hold_ctrl = (row.stiffness * row.joint_q0 - row.bias0) / row.gain
        hold_force = row.gain * hold_ctrl + row.bias0 - row.stiffness * row.joint_q0
        assert abs(hold_force) <= 1e-10 * max(1.0, abs(row.bias0))
        expected_controls.append((row.native_actuator_index, row.native_actuator_name, ctrl))
    assert actual_controls == tuple(sorted(expected_controls))
    with pytest.raises(ValueError, match="model-bound receipt"):
        bad_targets = list(targets)
        index, name, _value = bad_targets[0]
        bad_targets[0] = (index, name, float("nan"))
        receipt.control_inputs(tuple(bad_targets))

    def proxy_import_with(drive_change):
        proxy_joints = []
        for joint in imported.ir.joints:
            native_name = joint.dynamics.get("source_name")
            dynamics = joint.dynamics.to_dict()
            if native_name == "joint1":
                drive = dict(dynamics["usd_drives"][0])
                drive_change(drive)
                dynamics["usd_drives"] = (drive,)
            proxy_dynamics = SimpleNamespace(
                get=lambda key, default=None, d=dynamics: d.get(key, default),
                to_dict=lambda d=dynamics: d,
            )
            proxy_joints.append(SimpleNamespace(
                dynamics=proxy_dynamics, type=joint.type, limits=joint.limits,
            ))
        return SimpleNamespace(ir=SimpleNamespace(
            metadata=imported.ir.metadata, joints=tuple(proxy_joints),
        ))

    with pytest.raises(ValueError, match="does not admit 'acceleration' drive semantics"):
        inspect_usd_position_drive_model(
            source, proxy_import_with(lambda drive: drive.__setitem__("type", "acceleration")), model,
        )
    with pytest.raises(ValueError, match="stiffness unit conversion"):
        inspect_usd_position_drive_model(
            source, proxy_import_with(lambda drive: drive.__setitem__("stiffness", float("nan"))), model,
        )
    output_root = Path(os.environ["F05_G4_OUTPUT"])
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "numeric_oracle.json").write_text(json.dumps({
        "schema_version": "f05-geophys-drive-numeric-oracle-v1",
        "actual_menagerie_public_model": actual_oracle,
        "independent_numeric_vectors": oracle_units,
        "custom_receipt_identity_sha256": receipt.identity_sha256,
        "native_index_order": [name for _index, name, _value in targets],
        "actuator_order": [name for _index, name, _value in actual_controls],
        "control_inputs": [list(row) for row in actual_controls],
        "source_max_force_is_receipt_metadata_not_core_force_limit_ack": True,
        "unsupported_semantics_rejections": ["acceleration", "non-finite authored stiffness"],
    }, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def test_f05_geo_usd_production_materialize_remains_fail_closed_outside_s1():
    from task_env.runtime.sessions.api import materialize
    from task_env.diagnostics.tasks.f05_source_control_support import build_input

    input_v1, _setup = build_input("menagerie-panda")
    assert input_v1.runtime_source.scene_source.locally_validated is True
    assert input_v1.runtime_source.scene_source.source_verified is False
    with pytest.raises(ValueError, match="no USD Core RuntimeSession adapter is admitted"):
        materialize(input_v1.artifact, input_v1.execution, source=input_v1.runtime_source)
