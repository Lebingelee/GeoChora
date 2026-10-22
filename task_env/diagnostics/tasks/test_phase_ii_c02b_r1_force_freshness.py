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
    session._inner_interval_active = False
    return session


def _snapshot(measurement, force=-30.0):
    return RuntimeSnapshot(
        qpos=np.zeros(1, dtype=np.float32),
        qvel=np.zeros(1, dtype=np.float32),
        actuator_force=np.asarray([force], dtype=np.float32),
        simulation_time=(
            0.0 if measurement is None
            else float(measurement.evaluation_simulation_time_s)
        ),
        actuator_force_measurement=measurement,
    )


def _native_snapshot(measurement, simulation_time_s, *, snapshot_time_s=None):
    if snapshot_time_s is None:
        snapshot_time_s = simulation_time_s
    return SimpleNamespace(
        simulation_time=float(snapshot_time_s),
        actuator_force=np.asarray([-3.0], dtype=np.float64),
        actuator_force_measurement=measurement,
    )


def _native_measurement(native_step_index, sample_sequence, evaluation_time_s,
                        evaluation_control_step, *, reset_sample_id="sample-a",
                        state_revision=12):
    return _measurement(
        sequence=sample_sequence,
        state_revision=state_revision,
        native_step_index=native_step_index,
        phase="native_step_pre_integration",
        reset_sample_id=reset_sample_id,
        native_sample_time_s=(native_step_index - 1) * 0.002,
        evaluation_control_step=evaluation_control_step,
        evaluation_simulation_time_s=evaluation_time_s,
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
        sequence=9,
        native_step_index=5,
        phase="native_step_pre_integration",
        evaluation_control_step=1,
        evaluation_simulation_time_s=0.01,
    )
    session._validate_actuator_force_measurement(state, _snapshot(valid))

    stale_index = _measurement(
        sequence=9,
        native_step_index=4,
        phase="native_step_pre_integration",
        evaluation_control_step=1,
        evaluation_simulation_time_s=0.01,
    )
    with pytest.raises(ValueError, match="native index"):
        session._validate_actuator_force_measurement(state, _snapshot(stale_index))

    wrong_phase = _measurement(
        sequence=9,
        native_step_index=5,
        phase="reset_forward",
        evaluation_control_step=1,
        evaluation_simulation_time_s=0.01,
    )
    with pytest.raises(ValueError, match="completed native-step"):
        session._validate_actuator_force_measurement(state, _snapshot(wrong_phase))

def test_r1_sampling_accepts_each_contiguous_native_substep_read():
    session = _session()
    session._inner_interval_active = True

    reset_sample = session._reset_force_measurement
    session._validate_actuator_force_measurement(
        SimpleNamespace(control_step=0, simulation_time=0.0),
        _native_snapshot(reset_sample, 0.0),
    )
    session._last_actuator_force_measurement = reset_sample

    for native_step_index in range(1, 5):
        evaluation_time = native_step_index * 0.002
        measurement = _native_measurement(
            native_step_index,
            sample_sequence=4 + native_step_index,
            evaluation_time_s=evaluation_time,
            evaluation_control_step=0,
            state_revision=12 + native_step_index,
        )
        session._validate_actuator_force_measurement(
            SimpleNamespace(control_step=0, simulation_time=evaluation_time),
            _native_snapshot(measurement, evaluation_time),
        )
        session._last_actuator_force_measurement = measurement


def test_r1_sampling_accepts_consecutive_outer_reads_across_five_native_steps():
    session = _session()
    session._inner_interval_active = False

    for control_step in (1, 2):
        native_step_index = control_step * 5
        evaluation_time = control_step * 0.01
        measurement = _native_measurement(
            native_step_index,
            sample_sequence=4 + native_step_index,
            evaluation_time_s=evaluation_time,
            evaluation_control_step=control_step,
            state_revision=12 + native_step_index,
        )
        session._validate_actuator_force_measurement(
            SimpleNamespace(control_step=control_step, simulation_time=evaluation_time),
            _native_snapshot(measurement, evaluation_time),
        )
        session._last_actuator_force_measurement = measurement


def test_r1_sampling_rejects_changed_force_sample_for_the_same_evaluation_state():
    session = _session()
    session._inner_interval_active = True
    previous = _native_measurement(1, 5, 0.002, 0, state_revision=17)
    session._last_actuator_force_measurement = previous
    changed = _native_measurement(1, 6, 0.002, 0, state_revision=18)

    with pytest.raises(ValueError, match="changed within one native evaluation state"):
        session._validate_actuator_force_measurement(
            SimpleNamespace(control_step=0, simulation_time=0.002),
            _native_snapshot(changed, 0.002),
        )


def test_r1_sampling_rejects_sequence_gap_across_two_native_steps():
    session = _session()
    session._inner_interval_active = True
    session._last_actuator_force_measurement = _native_measurement(1, 5, 0.002, 0)
    skipped = _native_measurement(3, 8, 0.006, 0)

    with pytest.raises(ValueError, match="sample does not match the completed native-step gap"):
        session._validate_actuator_force_measurement(
            SimpleNamespace(control_step=0, simulation_time=0.006),
            _native_snapshot(skipped, 0.006),
        )


@pytest.mark.parametrize(
    "measurement, state_time, native_time, message",
    [
        (_native_measurement(3, 7, 0.006, 0), 0.006, 0.004,
         "sample time differs from evaluation boundary"),
        (_native_measurement(3, 7, 0.004, 0), 0.006, 0.006,
         "another evaluation boundary"),
        (_native_measurement(3, 7, 0.006, 0, reset_sample_id="sample-old"), 0.006, 0.006,
         "another ResetSample"),
    ],
)
def test_r1_sampling_rejects_time_boundary_and_reset_sample_mismatch(
    measurement, state_time, native_time, message
):
    session = _session()
    session._inner_interval_active = True
    with pytest.raises(ValueError, match=message):
        session._validate_actuator_force_measurement(
            SimpleNamespace(control_step=0, simulation_time=state_time),
            _native_snapshot(measurement, state_time, snapshot_time_s=native_time),
        )


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
