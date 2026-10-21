"""C04 observation, info, and optional-diagnostics contract checks."""

from collections import OrderedDict
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.environment.config import ObservationConfig, RenderConfig
from task_env.environment.metadata import (
    observation_schema_metadata,
    validate_task_info,
)
from task_env.environment.types import (
    CameraMetadata,
    CameraPose,
    ObservationSchema,
    RuntimeSnapshot,
    SensorObservation,
)
from task_env.observations.state import StateObservationBuilder


def _assert_observations_equal(left, right):
    assert tuple(left) == tuple(right)
    for group in left:
        assert tuple(left[group]) == tuple(right[group])
        for field in left[group]:
            np.testing.assert_array_equal(left[group][field], right[group][field])


def _reset_info(*, simulation_time_s=0.0):
    return {
        "seed": 4,
        "reset_parameters": {},
        "task_uid": "test-task",
        "stage": "stage4_gym_contract",
        "is_success": False,
        "elapsed_steps": 0,
        "task_metrics": {},
        "reward_terms": {},
        "task_reward": 0.0,
        "task_failure": None,
        "success_definition": "test-success",
        "observation_schema": ObservationSchema(
            version="test-info-v1",
            fields=(),
            groups=(),
        ),
        "resolved_control_metadata": {},
        "simulation_time_s": simulation_time_s,
    }


def test_real_pendulum_reset_step_schema_clock_and_diagnostics_independence():
    from task_env import make_env

    config = {
        "runtime": {"backend": "cpu"},
        "episode": {"horizon": 3},
    }
    enabled = make_env(
        "pendulum-v1",
        config={**config, "observation": {"include_diagnostics": True}},
    )
    disabled = make_env(
        "pendulum-v1",
        config={**config, "observation": {"include_diagnostics": False}},
    )
    try:
        reset_on = enabled.reset(seed=213)
        reset_off = disabled.reset(seed=213)
        _assert_observations_equal(reset_on[0], reset_off[0])
        assert enabled.observation_space.contains(reset_on[0])
        assert disabled.observation_space.contains(reset_off[0])
        assert reset_on[1]["observation_schema"] == reset_off[1]["observation_schema"]
        assert reset_on[1]["simulation_time_s"] == reset_off[1]["simulation_time_s"] == 0.0
        validate_task_info(reset_on[1], phase="reset")
        validate_task_info(reset_off[1], phase="reset")

        field_specs = enabled.metadata["observation_schema"]["leaf_specs"]
        assert field_specs == disabled.metadata["observation_schema"]["leaf_specs"]
        assert field_specs[0]["path"] == "state.proprioception"
        assert field_specs[0]["shape"] == (3,)
        assert field_specs[0]["dtype"] == "float32"
        assert field_specs[0]["unit"] == "1, 1, rad/s"
        assert field_specs[0]["frame"] == "pendulum_hinge joint coordinates"
        assert field_specs[0]["time_reference"] == "same_reset_or_step_boundary"
        assert field_specs[0]["required"] is True
        assert field_specs[0]["visibility"] == "public"
        info_fields = enabled.metadata["info_schema"]["fields"]
        time_spec = next(field for field in info_fields if field["path"] == "simulation_time_s")
        assert time_spec["shape"] == ()
        assert time_spec["dtype"] == "float64"
        assert time_spec["unit"] == "s"
        assert time_spec["time_reference"] == "current_boundary"
        assert time_spec["required"] is True
        feedback_spec = next(field for field in info_fields if field["path"] == "applied_ctrl")
        assert feedback_spec["category"] == "required_feedback"
        assert feedback_spec["required"] is True
        camera_spec = next(field for field in info_fields if field["path"] == "camera_capture")
        assert camera_spec["category"] == "optional_capture_reference"
        assert camera_spec["required"] is False

        action = np.asarray([0.25], dtype=np.float32)
        step_on = enabled.step(action)
        step_off = disabled.step(action)
        assert len(step_on) == len(step_off) == 5
        _assert_observations_equal(step_on[0], step_off[0])
        assert enabled.observation_space.contains(step_on[0])
        assert disabled.observation_space.contains(step_off[0])
        assert step_on[1:4] == step_off[1:4]
        assert step_on[4]["task_metrics"] == step_off[4]["task_metrics"]
        assert step_on[4]["reward_terms"] == step_off[4]["reward_terms"]
        assert step_on[4]["task_reward"] == step_off[4]["task_reward"]
        assert step_on[4]["observation_schema"] == reset_on[1]["observation_schema"]
        assert step_off[4]["observation_schema"] == reset_off[1]["observation_schema"]
        assert step_on[4]["elapsed_steps"] == step_off[4]["elapsed_steps"] == 1
        assert step_on[4]["simulation_time_s"] == step_off[4]["simulation_time_s"]
        assert step_on[4]["simulation_time_s"] == pytest.approx(
            enabled.config.runtime.physics_dt * enabled.config.runtime.control_substeps
        )
        for key in (
            "requested_action",
            "external_action",
            "controller_target",
            "requested_ctrl",
            "applied_ctrl",
            "universal_action",
        ):
            np.testing.assert_array_equal(step_on[4][key], step_off[4][key])
        for key in (
            "requested",
            "external",
            "controller_target",
            "requested_ctrl",
            "applied_ctrl",
            "universal_action",
        ):
            np.testing.assert_array_equal(step_on[4]["action"][key], step_off[4]["action"][key])
        validate_task_info(step_on[4], phase="step")
        validate_task_info(step_off[4], phase="step")

        assert "action_clipped" in step_on[4] and "ctrl_clipped" in step_on[4]
        assert "action_clipped" not in step_off[4] and "ctrl_clipped" not in step_off[4]
        assert "clipped" in step_on[4]["action"]
        assert "clipped" not in step_off[4]["action"]
        optional_diagnostics = [
            field for field in info_fields if field["category"] == "optional_diagnostic"
        ]
        assert optional_diagnostics and all(field["required"] is False for field in optional_diagnostics)
    finally:
        enabled.close()
        disabled.close()


def test_panda_private_state_keeps_legacy_name_meaning_and_fails_on_missing_source():
    panda = SimpleNamespace(
        arm_qpos_ids=np.arange(7),
        arm_dof_ids=np.arange(7),
        gripper_qpos_ids=np.asarray([7, 8]),
        base_body_id=0,
        eef_site_id=0,
    )
    references = SimpleNamespace(agents={"panda-v1": panda}, objects={})
    builder = StateObservationBuilder(
        references=references,
        config=ObservationConfig(schema_version="task-env-state-v2"),
        render_config=RenderConfig(),
    )
    snapshot = RuntimeSnapshot(
        qpos=np.arange(9, dtype=np.float32),
        qvel=np.arange(7, dtype=np.float32),
        body_xpos=np.asarray([[1.0, 2.0, 3.0]], dtype=np.float32),
        body_xquat=np.asarray([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32),
        site_xpos=np.asarray([[4.0, 5.0, 6.0]], dtype=np.float32),
        site_xquat=np.asarray([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32),
    )

    observation = builder.build(snapshot)
    assert builder.observation_space.contains(observation)
    assert tuple(observation) == ("state", "privileged_state", "private_state")
    np.testing.assert_array_equal(
        observation["private_state"]["robot_base_pose_world"],
        np.asarray([1, 2, 3, 1, 0, 0, 0], dtype=np.float32),
    )
    metadata = observation_schema_metadata(builder.schema)
    private_spec = next(
        field for field in metadata["leaf_specs"]
        if field["path"] == "private_state.robot_base_pose_world"
    )
    assert private_spec["visibility"] == "private"
    assert private_spec["unit"] == "m + unit_quaternion"
    assert private_spec["frame"] == "world"
    assert metadata["group_semantics"]["private_state"].startswith("legacy private")
    assert "private_state.robot_base_pose_world" in builder.schema.leaf_field_names

    missing_private_source = RuntimeSnapshot(
        qpos=snapshot.qpos,
        qvel=snapshot.qvel,
        site_xpos=snapshot.site_xpos,
        site_xquat=snapshot.site_xquat,
    )
    with pytest.raises(ValueError, match="private_state requires resolved robot base body pose"):
        builder.build(missing_private_source)

    missing_ee_source = RuntimeSnapshot(
        qpos=snapshot.qpos,
        qvel=snapshot.qvel,
        body_xpos=snapshot.body_xpos,
        body_xquat=snapshot.body_xquat,
    )
    with pytest.raises(ValueError, match="state observation requires site pose"):
        builder.build(missing_ee_source)

    malformed = OrderedDict(observation.items())
    malformed["private_state"] = OrderedDict()
    with pytest.raises(ValueError, match="keys do not match schema"):
        builder.schema.validate(malformed)


def test_required_info_clock_and_required_fields_fail_explicitly():
    info = _reset_info()
    validate_task_info(info, phase="reset")
    del info["simulation_time_s"]
    with pytest.raises(ValueError, match="missing required field simulation_time_s"):
        validate_task_info(info, phase="reset")

    info = _reset_info(simulation_time_s=float("nan"))
    with pytest.raises(ValueError, match="simulation_time_s must be finite"):
        validate_task_info(info, phase="reset")


def test_controller_snapshot_and_required_feedback_survive_diagnostics_toggle():
    from task_env.environment.env import BaseTaskEnv

    snapshot = RuntimeSnapshot(
        qpos=np.asarray([0.0], dtype=np.float32),
        qvel=np.asarray([0.0], dtype=np.float32),
        simulation_time=0.1,
    )
    converted = []

    class Controller:
        def convert(self, action, controller_snapshot):
            converted.append((action, controller_snapshot))
            return "controller-command"

    for diagnostics in (True, False):
        env = object.__new__(BaseTaskEnv)
        env.config = SimpleNamespace(
            agents=SimpleNamespace(agent_uids=("panda-v1",)),
            observation=ObservationConfig(include_diagnostics=diagnostics),
            task=SimpleNamespace(success_definition="controller-feedback"),
        )
        env._robot = SimpleNamespace(controller=Controller())
        env._action_adapter = None
        assert BaseTaskEnv._convert_action(env, "requested", snapshot) == "controller-command"

    assert len(converted) == 2
    assert all(action == "requested" and seen_snapshot is snapshot for action, seen_snapshot in converted)

    def formatted_info(diagnostics):
        env = object.__new__(BaseTaskEnv)
        env.config = SimpleNamespace(
            task=SimpleNamespace(success_definition="controller-feedback"),
            observation=ObservationConfig(include_diagnostics=diagnostics),
        )
        env._observation_builder = SimpleNamespace(
            schema=ObservationSchema(version="test-info-v1", fields=(), groups=())
        )
        env._last_camera_metadata = {}
        command = SimpleNamespace(
            requested_action=np.asarray([1.0], dtype=np.float32),
            external_action=np.asarray([1.0], dtype=np.float32),
            controller_target=np.asarray([0.5], dtype=np.float32),
            requested_ctrl=np.asarray([0.4], dtype=np.float32),
            universal_action=np.asarray([0.4], dtype=np.float32),
            mode="position",
            action_clipped=False,
        )
        applied = SimpleNamespace(
            requested_ctrl=np.asarray([0.4], dtype=np.float32),
            applied_ctrl=np.asarray([0.35], dtype=np.float32),
            clipped=True,
        )
        evaluation = SimpleNamespace(
            success=False,
            metrics={"position_error_m": 0.2},
            reward_terms={"distance": -0.2},
            reward=-0.2,
            failure=None,
        )
        result = SimpleNamespace(
            snapshot=snapshot,
            evaluation=evaluation,
            command=command,
            applied=applied,
            observation={"state": {}},
            terminated=False,
            truncated=False,
            elapsed_steps=2,
        )
        lifecycle = SimpleNamespace(episode_finished=False)
        return BaseTaskEnv._format_step_result(env, lifecycle, result)[4]

    with_diagnostics = formatted_info(True)
    without_diagnostics = formatted_info(False)
    for key in (
        "requested_action",
        "external_action",
        "controller_target",
        "requested_ctrl",
        "applied_ctrl",
        "universal_action",
    ):
        np.testing.assert_array_equal(with_diagnostics[key], without_diagnostics[key])
    np.testing.assert_allclose(without_diagnostics["controller_target"], [0.5])
    np.testing.assert_allclose(without_diagnostics["requested_ctrl"], [0.4])
    np.testing.assert_allclose(without_diagnostics["applied_ctrl"], [0.35])
    assert "action_clipped" in with_diagnostics and "action_clipped" not in without_diagnostics
    validate_task_info(without_diagnostics, phase="step")


def test_camera_capture_reference_uses_sensor_metadata_and_same_boundary():
    from task_env.environment.env import BaseTaskEnv

    pose = CameraPose(
        position=np.asarray([1.0, 2.0, 3.0], dtype=np.float32),
        quaternion_wxyz=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        look_at=np.asarray([2.0, 2.0, 3.0], dtype=np.float32),
        up=np.asarray([0.0, 0.0, 1.0], dtype=np.float32),
    )
    metadata = CameraMetadata(
        name="front",
        width=16,
        height=12,
        rgb=True,
        depth=False,
        frame="world",
        parent=None,
        fov_y=1.0,
        near=0.01,
        far=10.0,
        pose=pose,
        intrinsic=np.eye(3, dtype=np.float32),
        extrinsic=np.eye(4, dtype=np.float32),
    )
    snapshot = RuntimeSnapshot(
        qpos=np.asarray([0.0], dtype=np.float32),
        qvel=np.asarray([0.0], dtype=np.float32),
        simulation_time=0.35,
    )

    class SensorProvider:
        def capture(self, _snapshot):
            return SensorObservation(camera_metadata={"front": metadata})

    class ObservationBuilder:
        def build(self, _snapshot, sensor_observation):
            assert sensor_observation.camera_metadata["front"] is metadata
            return {"state": {}}

    env = object.__new__(BaseTaskEnv)
    env._sensor_provider = SensorProvider()
    env._observation_builder = ObservationBuilder()
    env._last_camera_metadata = {"stale": metadata}
    assert BaseTaskEnv._build_observation_fallback(env, snapshot) == {"state": {}}

    capture = env._camera_capture_info(elapsed_steps=7, simulation_time_s=0.35)
    assert capture["source"] == "SensorObservation.camera_metadata"
    assert capture["observation_boundary"] == {
        "elapsed_steps": 7,
        "simulation_time_s": 0.35,
    }
    assert capture["cameras"]["front"]["frame"] == "world"
    assert capture["cameras"]["front"]["pose"]["position"] == [1.0, 2.0, 3.0]
