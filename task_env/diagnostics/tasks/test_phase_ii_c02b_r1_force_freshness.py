"""S1 validation for the required PickCube R1 actuator-force sample contract."""

from types import SimpleNamespace

import numpy as np
import pytest

from task_env.environment import ActuatorForceMeasurementV1
from task_env.environment.types import RuntimeSnapshot
from task_env.runtime.sessions.control import feedback_value
from task_env.runtime.sessions.geophys import _GeoPhysSession


def _measurement(
    *,
    sequence=4,
    source_generation=7,
    state_revision=12,
    configuration_revision=2,
    native_step_index=0,
    phase="reset_forward",
    valid=True,
    invalid_reason=None,
    actuator_id="actuator8",
    episode_id="episode-a",
    reset_sample_id="sample-a",
    native_sample_time_s=None,
    evaluation_control_step=None,
    evaluation_simulation_time_s=None,
    force_unit="N",
):
    if native_sample_time_s is None and phase == "reset_forward":
        native_sample_time_s = 0.0
    elif native_sample_time_s is None and phase == "native_step_pre_integration":
        native_sample_time_s = max(0, native_step_index - 1) * 0.002
    if evaluation_control_step is None:
        evaluation_control_step = native_step_index // 5
    if evaluation_simulation_time_s is None:
        evaluation_simulation_time_s = evaluation_control_step * 0.01
    return ActuatorForceMeasurementV1(
        schema_version="task-env-actuator-force-sample-v1",
        source_generation=source_generation,
        sample_sequence=sequence,
        state_revision=state_revision,
        configuration_revision=configuration_revision,
        native_step_index=native_step_index,
        phase=phase,
        valid=valid,
        force_unit=force_unit,
        invalid_reason=invalid_reason,
        actuator_id=actuator_id,
        episode_id=episode_id,
        reset_sample_id=reset_sample_id,
        evaluation_control_step=evaluation_control_step,
        evaluation_simulation_time_s=evaluation_simulation_time_s,
        native_sample_time_s=native_sample_time_s,
    )


def _session():
    session = object.__new__(_GeoPhysSession)
    session._artifact = SimpleNamespace(
        timebase=SimpleNamespace(physics_dt=0.002, control_substeps=5)
    )
    session._force_source_generation = 7
    session._reset_force_measurement = _measurement()
    session._last_reset_force_sequence = 4
    session._source = SimpleNamespace(open_actuators=("actuator8",))
    session._episode_id = "episode-a"
    session._reset_sample_id = "sample-a"
    session._last_actuator_force_measurement = None
    return session


def _snapshot(measurement, force=-30.0):
    return RuntimeSnapshot(
        qpos=np.zeros(1, dtype=np.float32),
        qvel=np.zeros(1, dtype=np.float32),
        actuator_force=np.asarray([force], dtype=np.float32),
        actuator_force_measurement=measurement,
    )


def test_r1_feedback_gate_accepts_only_the_current_reset_forward_sample():
    session = _session()
    session._validate_actuator_force_measurement(
        SimpleNamespace(control_step=0, simulation_time=0.0),
        _snapshot(session._reset_force_measurement),
    )

    stale = _measurement(sequence=3)
    with pytest.raises(ValueError, match="first R1 feedback"):
        session._validate_actuator_force_measurement(
            SimpleNamespace(control_step=0, simulation_time=0.0),
            _snapshot(stale),
        )


@pytest.mark.parametrize(
    "measurement, force, message",
    [
        (None, -30.0, "no validity contract"),
        (_measurement(valid=False, invalid_reason="state write"), -30.0, "is invalid"),
        (_measurement(source_generation=8), -30.0, "another solver identity"),
        (_measurement(actuator_id="other-actuator"), -30.0, "wrong actuator identity"),
        (_measurement(phase="native_step_pre_integration", native_step_index=0), -30.0, "first R1 feedback"),
        (_measurement(), float("nan"), "non-finite or missing"),
    ],
)
def test_r1_feedback_gate_rejects_invalid_or_misidentified_reset_samples(
    measurement, force, message
):
    session = _session()
    with pytest.raises(ValueError, match=message):
        session._validate_actuator_force_measurement(
            SimpleNamespace(control_step=0, simulation_time=0.0),
            _snapshot(measurement, force),
        )


def test_actuator_force_measurement_rejects_unsupported_units():
    with pytest.raises(ValueError, match="unit must be N"):
        _measurement(force_unit="Nm")


def test_r1_feedback_gate_requires_latest_completed_native_preintegration_sample():
    session = _session()
    state = SimpleNamespace(control_step=1, simulation_time=0.01)

    valid = _measurement(
        sequence=5,
        native_step_index=5,
        phase="native_step_pre_integration",
    )
    session._validate_actuator_force_measurement(state, _snapshot(valid))

    stale_index = _measurement(
        sequence=5,
        native_step_index=4,
        phase="native_step_pre_integration",
    )
    with pytest.raises(ValueError, match="native index"):
        session._validate_actuator_force_measurement(state, _snapshot(stale_index))

    wrong_phase = _measurement(
        sequence=5,
        native_step_index=5,
        phase="reset_forward",
        evaluation_control_step=1,
    )
    with pytest.raises(ValueError, match="completed native-step"):
        session._validate_actuator_force_measurement(state, _snapshot(wrong_phase))


def test_raw_signed_force_keeps_the_existing_canonical_closing_projection():
    from task_env.controllers.canonical.kinematics import FINGERS

    state = SimpleNamespace(
        control_step=0,
        simulation_time=0.0,
        joint_position={name: 0.04 for name in FINGERS},
        to_mapping=lambda: {"boundary": "reset"},
    )
    session = SimpleNamespace(
        _require_reset=lambda: None,
        _control_binding=SimpleNamespace(gripper_semantic_id="panda-main/gripper"),
        snapshot=lambda: state,
    )
    feedback = feedback_value(session, state, -30.0)
    assert feedback.gripper.closing_force_N == 30.0
    assert feedback.gripper.semantic_id == "panda-main/gripper"
