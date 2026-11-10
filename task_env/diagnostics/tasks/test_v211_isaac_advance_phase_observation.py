"""Provider-free checks for attributing a failed native-advance clock boundary."""
from types import SimpleNamespace

import pytest

from task_env.runtime.sessions import isaac_native_io


@pytest.mark.parametrize(
    ("setter_steps", "sync_steps", "manager_steps", "post_sync_steps"),
    [(0, 0, 2, 0), (1, 0, 1, 0), (0, 1, 1, 0), (0, 0, 1, 1)],
)
def test_g05_failed_advance_identifies_the_phase(monkeypatch, setter_steps, sync_steps,
                                                manager_steps, post_sync_steps):
    io = object.__new__(isaac_native_io.IsaacSimNativeRuntimeIOV1)
    io._closed = False
    io._episode_origin_step = 0
    io._episode_origin_time = 0.0
    io._native_step_count = 0
    io._g05_effort = True
    io._physical_effort_pending = ([0], [0.75])
    io._dof_names = ("hinge",)
    io._artifact = SimpleNamespace(timebase=SimpleNamespace(physics_dt=0.002))
    io._physics_scene = None
    io._build_layout_facts = {}
    counter = [0]

    def advance_counter(steps):
        counter[0] += steps

    io._counter = lambda: (counter[0], counter[0] * 0.002)
    sync_calls = iter((sync_steps, post_sync_steps))
    io._sync = lambda: advance_counter(next(sync_calls))
    io._articulation = SimpleNamespace(
        set_dof_efforts=lambda *args, **kwargs: advance_counter(setter_steps),
        get_dof_efforts=lambda **kwargs: object(),
    )
    io._manager = SimpleNamespace(
        step=lambda **kwargs: advance_counter(manager_steps),
        get_physics_dt=lambda: 0.002,
        is_simulating=lambda: True,
        is_paused=lambda: False,
    )
    monkeypatch.setattr(isaac_native_io, "_tensor_rows", lambda *args, **kwargs: ((0.75,),))

    with pytest.raises(RuntimeError, match="exactly one configured physics substep") as exc:
        io.advance()
    facts = exc.value._g05_native_last_advance_observation
    for key, expected in (
        ("effort_setter_counter_delta", setter_steps),
        ("effort_sync_counter_delta", sync_steps),
        ("manager_step_counter_delta", manager_steps),
        ("post_manager_counter_delta", post_sync_steps),
    ):
        assert facts[key][0] == expected
        assert facts[key][1] == pytest.approx(expected * 0.002)
    assert io._native_step_count == 0


def test_g05_scene_handoff_captures_only_supported_gravity_and_matching_rate():
    payload = isaac_native_io._g05_scene_handoff_payload(
        scene_path="/task_env_pendulum/PhysicsScene",
        applied_schemas=("PhysxSceneAPI",),
        authored_values={
            "physics:gravityDirection": (0.0, 0.0, -2.0),
            "physics:gravityMagnitude": 9.81,
            "physx:timeStepsPerSecond": 500,
        },
        configured_dt=0.002,
        meters_per_unit=1.0,
    )
    assert payload["gravity_direction_normalized"] == [0.0, 0.0, -1.0]
    assert payload["gravity_world_m_s2"] == [0.0, 0.0, -9.81]
    assert payload["steps_per_second"] == 500
    assert payload["source_bytes_modified"] is False


@pytest.mark.parametrize(
    ("schemas", "values", "match"),
    [
        (("NewtonSceneAPI",), {
            "physics:gravityDirection": (0.0, 0.0, -1.0),
            "physics:gravityMagnitude": 9.81,
        }, "unsupported APIs"),
        ((), {
            "physics:gravityDirection": (0.0, 0.0, -1.0),
            "physics:gravityMagnitude": 9.81,
            "physx:solverType": "TGS",
        }, "unsupported authored properties"),
        ((), {
            "physics:gravityDirection": (0.0, 0.0, -1.0),
            "physics:gravityMagnitude": 9.81,
            "physx:timeStepsPerSecond": 400,
        }, "conflicts with the TaskArtifact timebase"),
        ((), {"physics:gravityMagnitude": 9.81}, "requires explicit authored gravity"),
        ((), {
            "physics:gravityDirection": (0.0, 0.0, 0.0),
            "physics:gravityMagnitude": 9.81,
        }, "is invalid"),
    ],
)
def test_g05_scene_handoff_rejects_unpreserved_semantics(schemas, values, match):
    with pytest.raises(ValueError, match=match):
        isaac_native_io._g05_scene_handoff_payload(
            scene_path="/task_env_pendulum/PhysicsScene",
            applied_schemas=schemas,
            authored_values=values,
            configured_dt=0.002,
            meters_per_unit=1.0,
        )
