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


def test_canonical_dls_reset_posture_correction_is_limited_to_the_task_nullspace():
    import numpy as np
    import pytest

    from task_env.artifacts import PoseWorld
    from task_env.controllers.canonical.contracts import RequestedAction
    from task_env.controllers.canonical.controller import CanonicalPandaController
    from task_env.environment import ActionConfig

    class _Kinematics:
        source_sha256 = "a" * 64
        limits = np.tile(np.asarray((-2.0, 2.0)), (7, 1))
        base_transform = np.eye(4)

        @staticmethod
        def fk_jacobian(_q):
            transform = np.eye(4)
            jacobian = np.zeros((6, 7), dtype=np.float64)
            jacobian[:, :6] = np.eye(6)
            return transform, jacobian

    class _State:
        joint_position = {f"panda-v1/joint{index}": 0.0 for index in range(1, 8)}
        pose_world = {"panda-v1/ee": PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))}

    request = RequestedAction(
        "absolute_pose", "world", "quaternion_wxyz",
        (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0),
    )
    config = ActionConfig(joint_position_correction_gain=1.0)
    legacy = CanonicalPandaController(_Kinematics(), artifact_hash="b" * 64, config=config)
    _canonical, legacy_desired, _legacy_servo = legacy._compute_arm(_State(), request)
    np.testing.assert_allclose(legacy_desired, np.zeros(7), atol=1e-12)

    corrected = CanonicalPandaController(
        _Kinematics(), artifact_hash="b" * 64, config=config,
        nullspace_reference_gain=1.0,
    )
    corrected.set_nullspace_reference((0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05))
    _canonical, desired, _servo = corrected._compute_arm(_State(), request)
    np.testing.assert_allclose(desired[:6], np.zeros(6), atol=1e-12)
    assert desired[6] == pytest.approx(0.045)

    joint_request = RequestedAction(
        "absolute_joint", None, "none", (0.1, -0.1, 0.2, -0.2, 0.3, -0.3, 0.4, 0.0),
    )
    _canonical, joint_desired, _joint_servo = corrected._compute_arm(_State(), joint_request)
    np.testing.assert_allclose(joint_desired, joint_request.values[:7], atol=1e-12)


def test_accumulated_pose_target_tracks_repeated_targets_and_holds_when_settled():
    import numpy as np

    from task_env.artifacts import PoseWorld
    from task_env.controllers.canonical.contracts import RequestedAction
    from task_env.controllers.canonical.controller import CanonicalPandaController

    class _Kinematics:
        source_sha256 = "a" * 64
        limits = np.tile(np.asarray((-2.0, 2.0)), (7, 1))
        base_transform = np.eye(4)

        @staticmethod
        def fk_jacobian(_q):
            transform = np.eye(4)
            jacobian = np.zeros((6, 7), dtype=np.float64)
            jacobian[:, :6] = np.eye(6)
            return transform, jacobian

    class _State:
        joint_position = {f"panda-v1/joint{index}": 0.0 for index in range(1, 8)}
        pose_world = {"panda-v1/ee": PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))}

    request = RequestedAction(
        "absolute_pose", "world", "quaternion_wxyz",
        (0.01, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0),
    )
    stateless = CanonicalPandaController(_Kinematics(), artifact_hash="b" * 64)
    stateful = CanonicalPandaController(
        _Kinematics(), artifact_hash="b" * 64,
        pose_target_method="accumulated_dls_target_until_settled_v1",
    )
    stateful.reset_pose_target_memory(np.zeros(7))

    _canonical, stateless_first, _servo = stateless._compute_arm(_State(), request)
    _canonical, stateless_second, _servo = stateless._compute_arm(_State(), request)
    _canonical, stateful_first, _servo = stateful._compute_arm(_State(), request)
    _canonical, stateful_second, _servo = stateful._compute_arm(_State(), request)
    np.testing.assert_allclose(stateless_second, stateless_first, atol=1e-12)
    assert stateful_second[0] > stateful_first[0] > 0.0

    settled_state = _State()
    settled_state.pose_world = {
        "panda-v1/ee": PoseWorld((0.01, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    }
    held_target = stateful._arm_target.copy()
    _canonical, settled_target, _servo = stateful._compute_arm(settled_state, request)
    np.testing.assert_allclose(settled_target, held_target, atol=1e-12)

    stateful.reset_pose_target_memory(np.full(7, 0.125))
    np.testing.assert_allclose(stateful._arm_target, np.full(7, 0.125), atol=1e-12)


def test_canonical_controller_clips_arm_targets_to_bound_native_limit_intersection():
    import numpy as np

    from task_env.artifacts import PoseWorld
    from task_env.controllers.canonical.contracts import RequestedAction
    from task_env.controllers.canonical.controller import CanonicalPandaController

    class _Kinematics:
        source_sha256 = "a" * 64
        limits = np.tile(np.asarray((-2.0, 4.0)), (7, 1))
        base_transform = np.eye(4)

    class _State:
        joint_position = {f"panda-v1/joint{index}": 0.0 for index in range(1, 8)}
        pose_world = {"panda-v1/ee": PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))}

    native_limits = _Kinematics.limits.copy()
    native_limits[5, 1] = 3.752499969733032
    controller = CanonicalPandaController(
        _Kinematics(), artifact_hash="b" * 64,
        arm_target_limits=native_limits,
        arm_target_limit_source="kinematics_and_geophys_receipt_intersection_v1",
    )
    request = RequestedAction(
        "absolute_joint", None, "none",
        (0.0, 0.0, 0.0, 0.0, 0.0, 3.7525, 0.0, 0.0),
    )
    _canonical, desired, _servo = controller._compute_arm(_State(), request)
    assert desired[5] == native_limits[5, 1]


def test_dg02_cold_reader_accepts_plan_bound_controller_gains_without_hardcoding():
    from task_env.diagnostics.tasks.f05_dg02_core_n2_cold_reader import (
        _controller_method_supported,
    )

    method = {
        "nullspace_reference_gain": 1.0,
        "reference_source": "reset_typed_arm_joint_position",
        "projector": "svd_right_nullspace_v1",
        "pose_target_method": "accumulated_dls_target_until_settled_v1",
        "arm_target_limit_source": "kinematics_and_geophys_receipt_intersection_v1",
    }
    assert _controller_method_supported(method)
    assert _controller_method_supported({**method, "nullspace_reference_gain": 0.2})
    assert not _controller_method_supported({**method, "nullspace_reference_gain": True})
    assert not _controller_method_supported({**method, "nullspace_reference_gain": float("inf")})
    assert not _controller_method_supported({**method, "pose_target_method": "unbound_method"})
