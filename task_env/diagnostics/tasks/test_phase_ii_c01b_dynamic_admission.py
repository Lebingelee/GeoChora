"""C01b dynamic admission from real selected Artifacts and provider manifests."""

from __future__ import annotations

from dataclasses import replace

import pytest


def _selected_task(task_id: str):
    if task_id == "pick_cube":
        from task_env.tasks.pick_cube.task import (
            build_artifact,
            build_runtime_source,
        )

        artifact = build_artifact()
        return artifact, build_runtime_source(artifact, backend="cpu")
    if task_id == "nut_assembly":
        from task_env.tasks.nut_assembly.task import (
            build_artifact,
            build_runtime_source,
        )

        artifact = build_artifact()
        source, _contact_profile = build_runtime_source(artifact, "geophys")
        return artifact, source
    raise AssertionError(f"unknown selected task fixture: {task_id}")


def _execution(provider: str, *, backend: str = "cpu", render: str = "none"):
    from task_env.artifacts import ExecutionSpec
    from task_env.runtime.sessions.api import PROFILE

    return ExecutionSpec(provider, PROFILE, render, backend, 0, "strict")


@pytest.mark.parametrize("task_id", ("pick_cube", "nut_assembly"))
@pytest.mark.parametrize("provider", ("geophys", "mujoco"))
def test_selected_artifact_requirements_admit_against_selected_build_manifest(
    task_id, provider, monkeypatch
):
    from task_env.runtime.sessions import api as runtime_api
    from task_env.runtime.sessions.provenance import provider_build_identity

    artifact, source = _selected_task(task_id)
    execution = _execution(provider)
    expected_manifest = runtime_api.provider_manifest(provider)
    expected_build = provider_build_identity(provider)
    supported = {
        claim.name
        for claim in expected_manifest.capabilities
        if claim.status in {"implemented", "tested", "qualified"}
    }

    assert set(artifact.required_capabilities.names) <= supported
    assert expected_manifest.provider_name == provider
    assert expected_manifest.provider_version == expected_build["manifest_version"]

    admissions = []
    real_admit = runtime_api.admit_capabilities

    def capture_admission(required, manifest, selected_execution=None):
        admissions.append((required, manifest, selected_execution))
        return real_admit(required, manifest, selected_execution)

    materializations = []
    sentinel = object()

    def materialize_admitted(actual_artifact, actual_execution, actual_source):
        materializations.append((actual_artifact, actual_execution, actual_source))
        return sentinel

    monkeypatch.setattr(runtime_api, "admit_capabilities", capture_admission)
    monkeypatch.setattr(runtime_api, "_materialize_admitted", materialize_admitted)

    session = runtime_api.materialize(artifact, execution, source=source)

    assert session is sentinel
    assert len(admissions) == 1
    required, admitted_manifest, admitted_execution = admissions[0]
    assert required is artifact.required_capabilities
    assert admitted_manifest.identity_hash == expected_manifest.identity_hash
    assert admitted_manifest.provider_version == expected_build["manifest_version"]
    assert admitted_execution == execution
    assert materializations == [(artifact, execution, source)]


def test_actual_manifest_rejects_task_requirement_even_if_caller_manifest_expands_it(
    monkeypatch,
):
    from task_env.artifacts import CapabilityAdmissionError, CapabilityClaim, RequiredCapabilitySet
    from task_env.runtime.sessions import api as runtime_api

    artifact, source = _selected_task("pick_cube")
    artifact = replace(
        artifact,
        required_capabilities=RequiredCapabilitySet(
            (*artifact.required_capabilities.names, "contact_detection")
        ),
    )
    source = replace(source, task_artifact_hash=artifact.identity_hash)
    execution = _execution("geophys")
    actual = runtime_api.provider_manifest("geophys")
    assert "contact_detection" in actual.known_unsupported

    # A caller manifest can make the first, narrower check pass, but cannot
    # add support to the manifest resolved for the actual selected provider.
    expanded = replace(
        actual,
        capabilities=(
            *actual.capabilities,
            CapabilityClaim("contact_detection", "tested", "negative-test-only"),
        ),
        known_unsupported=tuple(
            name for name in actual.known_unsupported if name != "contact_detection"
        ),
    )
    admissions = []
    real_admit = runtime_api.admit_capabilities

    def capture_admission(required, manifest, selected_execution=None):
        admissions.append(manifest)
        return real_admit(required, manifest, selected_execution)

    native_calls = []
    monkeypatch.setattr(runtime_api, "admit_capabilities", capture_admission)
    monkeypatch.setattr(
        runtime_api,
        "_materialize_admitted",
        lambda *args: native_calls.append(args),
    )

    with pytest.raises(CapabilityAdmissionError, match="contact_detection"):
        runtime_api.materialize(
            artifact, execution, source=source, manifest=expanded
        )

    assert [manifest.identity_hash for manifest in admissions] == [
        expanded.identity_hash,
        actual.identity_hash,
    ]
    assert native_calls == []


def test_restrictive_manifest_and_execution_mismatch_fail_before_native_creation(
    monkeypatch,
):
    from task_env.artifacts import CapabilityAdmissionError
    from task_env.runtime.sessions import api as runtime_api

    artifact, source = _selected_task("pick_cube")
    actual = runtime_api.provider_manifest("geophys")
    execution = _execution("geophys")
    claims = tuple(
        replace(claim, status="unsupported")
        if claim.name == "frame_pose_query"
        else claim
        for claim in actual.capabilities
    )
    restrictive = replace(
        actual,
        capabilities=claims,
        known_unsupported=(*actual.known_unsupported, "frame_pose_query"),
    )
    native_calls = []
    monkeypatch.setattr(
        runtime_api,
        "_materialize_admitted",
        lambda *args: native_calls.append(args),
    )

    with pytest.raises(CapabilityAdmissionError, match="frame_pose_query"):
        runtime_api.materialize(
            artifact, execution, source=source, manifest=restrictive
        )
    with pytest.raises(CapabilityAdmissionError, match="execution mismatch: backend"):
        runtime_api.materialize(
            artifact,
            _execution("geophys", backend="cuda"),
            source=source,
        )
    assert native_calls == []


def test_unsupported_render_selection_fails_before_native_creation(monkeypatch):
    from task_env.runtime.sessions import api as runtime_api

    artifact, source = _selected_task("pick_cube")
    native_calls = []
    monkeypatch.setattr(
        runtime_api,
        "_materialize_admitted",
        lambda *args: native_calls.append(args),
    )

    with pytest.raises(ValueError, match="rendering is unsupported"):
        runtime_api.materialize(
            artifact,
            _execution("geophys", render="mujoco"),
            source=source,
        )
    assert native_calls == []
