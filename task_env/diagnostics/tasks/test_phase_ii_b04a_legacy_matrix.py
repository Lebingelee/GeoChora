"""B04a fixtures for frozen v0 identity and explicit version boundaries.

These checks pin the current TaskArtifact bytes/mapping/identity contract and
exercise only provider-free value codecs. They do not implement vNext decoding
or migrate any frozen Artifact.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from task_env.artifacts import (
    CapabilityClaim,
    CanonicalStateView,
    ExecutionSpec,
    ProviderCapabilityManifest,
    TaskArtifact,
    Timebase,
)
from task_env.artifacts.execution import RealizedInitialState, ResetSample
from task_env.observations.canonical_camera.contracts import CameraGeometry
from task_env.recorders.contracts import RecorderConfig


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "phase_ii_b04a"
REFERENCE_BASELINE = Path(__file__).with_name("reference_construction_baseline.json")

_ARTIFACT_FIXTURES = (
    (
        "pick_cube_task_artifact_v0.json",
        "5ce44d4deaa30071fee0de3cb98aee17878c566e9f32b9216bd48b3e6934b135",
        "fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4",
        "task_env.tasks.pick_cube.task",
    ),
    (
        "nut_assembly_task_artifact_v0.json",
        "e25bb363bd9e6e59b41c0dd6b14316f2e840913c714cd0f4646df05e6374ea09",
        "99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe",
        "task_env.tasks.nut_assembly.task",
    ),
)


def _canonical_json_bytes(mapping: dict) -> bytes:
    return json.dumps(
        mapping,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@pytest.mark.parametrize(
    "filename,fixture_sha256,artifact_identity,builder_module",
    _ARTIFACT_FIXTURES,
)
def test_frozen_task_artifact_v0_fixture_bytes_mapping_and_identity_are_pinned(
    filename,
    fixture_sha256,
    artifact_identity,
    builder_module,
):
    fixture_bytes = (FIXTURE_DIR / filename).read_bytes()
    assert hashlib.sha256(fixture_bytes).hexdigest() == fixture_sha256
    mapping = json.loads(fixture_bytes)
    decoded = TaskArtifact.from_mapping(mapping)

    # Raw fixture bytes, normalized mapping bytes and task identity are distinct
    # oracles: JSON/YAML presentation does not become the frozen identity.
    canonical_bytes = _canonical_json_bytes(decoded.to_mapping())
    assert decoded.to_mapping() == mapping
    assert hashlib.sha256(canonical_bytes).hexdigest() == artifact_identity
    assert decoded.identity_hash == artifact_identity
    assert hashlib.sha256(fixture_bytes).hexdigest() != decoded.identity_hash

    module = __import__(builder_module, fromlist=["build_artifact"])
    assert module.build_artifact().to_mapping() == mapping

    yaml_bytes = yaml.safe_dump(mapping, sort_keys=True, allow_unicode=True).encode("utf-8")
    assert yaml_bytes != fixture_bytes
    assert yaml.safe_load(yaml_bytes) == mapping
    assert TaskArtifact.from_mapping(yaml.safe_load(yaml_bytes)).identity_hash == artifact_identity


def test_existing_nested_v0_contracts_roundtrip_without_entering_task_identity():
    artifact_mapping = json.loads((FIXTURE_DIR / _ARTIFACT_FIXTURES[0][0]).read_bytes())
    artifact = TaskArtifact.from_mapping(artifact_mapping)
    artifact_identity = artifact.identity_hash

    baseline = json.loads(REFERENCE_BASELINE.read_text(encoding="utf-8"))
    sample_mapping = baseline["pickcube"]["resets"]["11"]
    sample = ResetSample.from_mapping(sample_mapping)
    assert sample.schema_version == "reset-sample-v0"
    assert sample.to_mapping() == sample_mapping
    assert sample.sample_id == "reset-" + sample.identity_hash
    assert sample.task_artifact_hash == artifact_identity

    state = CanonicalStateView(
        "canonical-state-v0",
        "SI_right_handed_z_up_wxyz",
        0,
        0.0,
        {},
        {},
        {},
    )
    realized = RealizedInitialState(
        "realized-initial-state-v0", sample.sample_id, "mujoco", state, 0
    )
    assert CanonicalStateView.from_mapping(state.to_mapping()) == state
    assert RealizedInitialState.from_mapping(realized.to_mapping()) == realized

    # Execution provenance stays outside TaskArtifact identity. Replacing the
    # provider never rewrites a frozen Task Semantic Identity.
    execution = ExecutionSpec("mujoco", "cpu", "mujoco", "cpu", 11, "best_effort")
    alternate_execution = ExecutionSpec("geophys", "cpu", "mujoco", "cpu", 11, "best_effort")
    assert ExecutionSpec.from_mapping(execution.to_mapping()) == execution
    assert execution.to_mapping() != alternate_execution.to_mapping()
    assert artifact.identity_hash == artifact_identity
    with pytest.raises(ValueError, match="unknown TaskArtifact fields"):
        TaskArtifact.from_mapping({**artifact_mapping, "execution": execution.to_mapping()})

    timebase = Timebase.from_mapping(artifact.timebase.to_mapping())
    assert timebase == artifact.timebase
    assert timebase.to_mapping() == {
        "physics_dt": artifact.timebase.physics_dt,
        "control_substeps": artifact.timebase.control_substeps,
        "control_dt": artifact.timebase.control_dt,
        "action_hold": artifact.timebase.action_hold,
        "observation_sampling": artifact.timebase.observation_sampling,
        "semantic_sampling": artifact.timebase.semantic_sampling,
    }


def test_current_camera_and_capability_v0_values_are_strict_and_pinned_to_artifact():
    artifact_mapping = json.loads((FIXTURE_DIR / _ARTIFACT_FIXTURES[0][0]).read_bytes())
    artifact = TaskArtifact.from_mapping(artifact_mapping)
    identity = (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    camera = CameraGeometry(
        "camera-observation-v0",
        artifact.identity_hash,
        "fixture-camera",
        "panda-v1/hand",
        identity,
        identity,
        64,
        48,
        0.9,
        0.01,
        10.0,
    )
    camera_copy = CameraGeometry.from_mapping(camera.to_mapping())
    assert camera_copy == camera
    assert camera_copy.task_artifact_hash == artifact.identity_hash
    assert camera_copy.identity_hash == camera.identity_hash

    claim = CapabilityClaim("rgb_camera", "tested", "fixture://camera-evidence")
    manifest = ProviderCapabilityManifest(
        "provider-capability-v0",
        "mujoco",
        "fixture-provider-version",
        "fixture-adapter-version",
        "cpu",
        "cpu",
        "native",
        "best_effort",
        (claim,),
        (),
        "fixture://manifest-evidence",
    )
    assert ProviderCapabilityManifest.from_mapping(manifest.to_mapping()) == manifest
    with pytest.raises(ValueError, match="unsupported capability"):
        ProviderCapabilityManifest(
            "provider-capability-v0",
            "mujoco",
            "fixture-provider-version",
            "fixture-adapter-version",
            "cpu",
            "cpu",
            "native",
            "best_effort",
            (claim,),
            ("segmentation",),
            "fixture://manifest-evidence",
        )


def test_unsupported_versions_and_unversioned_extensions_fail_closed(tmp_path):
    import h5py

    artifact_mapping = json.loads((FIXTURE_DIR / _ARTIFACT_FIXTURES[0][0]).read_bytes())
    with pytest.raises(ValueError, match="artifact schema"):
        TaskArtifact.from_mapping({**artifact_mapping, "schema_version": "task-artifact-v1"})

    world_v1 = copy.deepcopy(artifact_mapping)
    world_v1["world"]["schema_version"] = "world-v1"
    with pytest.raises(ValueError, match="world schema"):
        TaskArtifact.from_mapping(world_v1)

    baseline = json.loads(REFERENCE_BASELINE.read_text(encoding="utf-8"))
    reset_v1 = copy.deepcopy(baseline["pickcube"]["resets"]["11"])
    reset_v1["schema_version"] = "reset-sample-v1"
    with pytest.raises(ValueError, match="unsupported reset schema"):
        ResetSample.from_mapping(reset_v1)

    state = CanonicalStateView(
        "canonical-state-v0", "SI_right_handed_z_up_wxyz", 0, 0.0, {}, {}, {}
    )
    state_v1 = {**state.to_mapping(), "schema_version": "canonical-state-v1"}
    with pytest.raises(ValueError, match="state schema"):
        CanonicalStateView.from_mapping(state_v1)

    realized = RealizedInitialState(
        "realized-initial-state-v0",
        baseline["pickcube"]["resets"]["11"]["sample_id"],
        "mujoco",
        state,
        0,
    )
    realized_v1 = {**realized.to_mapping(), "schema_version": "realized-initial-state-v1"}
    with pytest.raises(ValueError, match="invalid realized initial state"):
        RealizedInitialState.from_mapping(realized_v1)

    timebase = Timebase(0.002, 10, 0.02).to_mapping()
    with pytest.raises(ValueError, match="unknown Timebase fields"):
        Timebase.from_mapping({**timebase, "schema_version": "timebase-v1"})

    execution = ExecutionSpec("mujoco", "cpu", "mujoco", "cpu", 11, "best_effort").to_mapping()
    with pytest.raises(ValueError, match="unknown ExecutionSpec fields"):
        ExecutionSpec.from_mapping({**execution, "schema_version": "execution-spec-v1"})

    camera = CameraGeometry(
        "camera-observation-v0",
        TaskArtifact.from_mapping(artifact_mapping).identity_hash,
        "fixture-camera",
        "panda-v1/hand",
        ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0),
         (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)),
        ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0),
         (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)),
        64,
        48,
        0.9,
        0.01,
        10.0,
    )
    camera_v1 = {**camera.to_mapping(), "schema_version": "camera-observation-v1"}
    with pytest.raises(ValueError, match="camera schema"):
        CameraGeometry.from_mapping(camera_v1)

    manifest = ProviderCapabilityManifest(
        "provider-capability-v0",
        "mujoco",
        "fixture-provider-version",
        "fixture-adapter-version",
        "cpu",
        "cpu",
        "native",
        "best_effort",
        (CapabilityClaim("rgb_camera", "tested", "fixture://camera-evidence"),),
        (),
        "fixture://manifest-evidence",
    )
    manifest_v1 = {**manifest.to_mapping(), "schema_version": "provider-capability-v1"}
    with pytest.raises(ValueError, match="manifest schema"):
        ProviderCapabilityManifest.from_mapping(manifest_v1)

    with pytest.raises(ValueError, match="unsupported TaskEnv H5 schema"):
        RecorderConfig(schema_id="task-env-h5", schema_version="v99")

    # v3 is supported by this recorder owner; use a real unsupported H5
    # version at the typed reader boundary rather than treating the generic
    # metadata inspector as a payload decoder.
    assert RecorderConfig(schema_id="task-env-h5", schema_version="v3").schema_version == "v3"
    from task_env.recorders.h5 import load_structured_control_records_h5
    unknown_structured = tmp_path / "unknown-structured-version.h5"
    with h5py.File(unknown_structured, "w") as handle:
        handle.attrs["schema_id"] = "task-env-h5"
        handle.attrs["schema_version"] = "v99"
    with pytest.raises(ValueError, match="structured control reader requires task-env-h5/v3"):
        load_structured_control_records_h5(unknown_structured)


def test_trajectory_readers_keep_independent_version_routes(tmp_path):
    import h5py

    from task_env.recorders.h5 import inspect_trajectory_h5
    from task_env.trajectory.canonical.execution import (
        FILE_SCHEMA as EXECUTION_FILE_SCHEMA,
        LEGACY_FILE_SCHEMA as LEGACY_EXECUTION_FILE_SCHEMA,
        LEGACY_SCHEMA as LEGACY_EXECUTION_SCHEMA,
        SCHEMA as EXECUTION_SCHEMA,
        validate as validate_execution,
    )
    from task_env.trajectory.canonical.h5 import (
        FILE_SCHEMA as CANONICAL_FILE_SCHEMA,
        FILE_SCHEMA_V1 as CANONICAL_FILE_SCHEMA_V1,
    )
    from task_env.trajectory.canonical.h5 import load as load_canonical_trajectory

    assert (RecorderConfig().schema_id, RecorderConfig().schema_version) == ("task-env-h5", "v2")
    assert (LEGACY_EXECUTION_SCHEMA, EXECUTION_SCHEMA) == (
        "canonical-execution-trajectory-v1",
        "canonical-execution-trajectory-v2",
    )
    assert (LEGACY_EXECUTION_FILE_SCHEMA, EXECUTION_FILE_SCHEMA) == (
        "task-env-canonical-execution-v1",
        "task-env-canonical-execution-v2",
    )
    assert CANONICAL_FILE_SCHEMA == "task-env-canonical-trajectory-v0"
    assert CANONICAL_FILE_SCHEMA_V1 == "task-env-canonical-trajectory-v1"

    with pytest.raises(ValueError, match="execution trajectory schema"):
        validate_execution(
            {
                "schema": "canonical-execution-trajectory-v3",
                "metadata": {},
                "recipe": {},
                "boundaries": [],
                "transitions": [],
                "blobs": {},
                "stop_reason": "",
            }
        )

    unknown_canonical = tmp_path / "unknown-canonical.h5"
    with h5py.File(unknown_canonical, "w") as handle:
        handle.attrs["schema"] = "task-env-canonical-trajectory-v99"
        handle.create_dataset("logical_json", data="{}")
        handle.create_group("numeric")
    with pytest.raises(ValueError, match="unsupported/unknown canonical file schema"):
        load_canonical_trajectory(unknown_canonical)

    # This generic inspector reports outer metadata only; it is not a decoder
    # and must not be counted as evidence that an unknown semantic payload loads.
    summary_only = tmp_path / "summary-only.h5"
    with h5py.File(summary_only, "w") as handle:
        handle.attrs.update(
            schema_id="task-env-h5",
            schema_version="v99",
            transition_count=0,
            observation_count=0,
        )
    summary = inspect_trajectory_h5(summary_only)
    assert summary["schema_version"] == "v99"
    assert "env_meta" not in summary
