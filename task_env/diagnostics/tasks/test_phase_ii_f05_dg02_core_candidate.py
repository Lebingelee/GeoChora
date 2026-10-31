"""Provider-free regression checks for the exact DG02 Core candidate contract."""

from __future__ import annotations


def test_dg02_usd_bindings_cover_the_dg01_runtime_frames_and_keep_free_cube_semantics():
    from task_env.tasks.position_candidate.builder import (
        F05_DG02_GEOPHYS_PROFILE,
        F05_DG02_USD_ASSET_VERSION,
        F05_DG02_USD_RECIPE_SHA256,
        _f05_dg02_usd_source_bindings,
    )
    from task_env.tasks.position_candidate.source import (
        F05_DG01_TASK_ID,
        F05_DG01_TASK_VERSION,
        _f05_dg01_scene,
        _f05_dg01_task_source,
    )

    scene = _f05_dg01_scene()
    task_source = _f05_dg01_task_source(scene)
    bodies, joints = _f05_dg02_usd_source_bindings()
    runtime_frames = {
        f"{frame.entity_id}/{frame.frame_id}"
        for frame in scene.frames or () if frame.frame_kind == "runtime"
    }

    assert task_source.task_id == F05_DG01_TASK_ID
    assert task_source.version == F05_DG01_TASK_VERSION
    assert runtime_frames == set(bodies)
    assert bodies["free-cube/free_cube"] == "/F04Scene/free_cube"
    assert bodies["free-cube/world"] == bodies["free-cube/free_cube"]
    assert bodies["support/support"] == "/F04Scene/support"
    assert set(joints) == {
        *(f"panda-main/joint{index}" for index in range(1, 8)),
        "panda-main/finger_joint1",
        "panda-main/finger_joint2",
    }
    assert len(joints) == 9
    assert F05_DG02_USD_ASSET_VERSION == "f05-dg02-usd-v2"
    assert F05_DG02_USD_RECIPE_SHA256 == "003238fb99d5b2574e5550918b6902518d7bc09cd0d6f4ad02049ccc408bb0fd"
    assert F05_DG02_GEOPHYS_PROFILE != "geophys-usd-position-f05-native-v1"


def test_dg02_scalar_source_bindings_allow_taskartifact_fixed_and_floating_joint_bindings():
    from task_env.environment import compile_task_artifact_v1
    from task_env.tasks.position_candidate.builder import _f05_dg02_usd_source_bindings
    from task_env.tasks.position_candidate.source import (
        _f05_dg01_artifact_and_sample,
        _f05_dg01_scene,
        _f05_dg01_task_source,
    )

    scene = _f05_dg01_scene()
    legacy_artifact, _ = _f05_dg01_artifact_and_sample(scene)
    artifact = compile_task_artifact_v1(_f05_dg01_task_source(scene), scene, legacy_artifact)
    _bodies, scalar_bindings = _f05_dg02_usd_source_bindings()

    task_joint_names = set(artifact.legacy_joint_bindings)
    assert set(scalar_bindings) <= task_joint_names
    assert task_joint_names - set(scalar_bindings) == {
        "free-cube/cube_freejoint",
        "panda-main/hand_fixed_mount",
    }


def test_dg02_candidate_input_rejects_unversioned_or_legacy_f05_input_before_native_work():
    import pytest

    from task_env.tasks.position_candidate.builder import F05Dg02GeoPhysUsdCandidateInputV1

    invalid = F05Dg02GeoPhysUsdCandidateInputV1(
        "f05-native-position-candidate-input-v1",
        None, None, None, None, None, "", "", None, None, None,
    )
    with pytest.raises(ValueError, match="unsupported F05 DG02"):
        invalid.validate()
