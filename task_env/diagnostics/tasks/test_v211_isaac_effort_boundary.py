"""Provider-free failure-sensitive checks for F06 effort ownership."""
import pytest

from task_env.runtime.sessions.isaac_native_io import IsaacSimNativeRuntimeIOV1
from task_env.runtime.sessions.native_io import UsdCoreRuntimeSession


class FakeArticulation:
    def __init__(self):
        self.writes = []
        self.fail = False

    def set_dof_efforts(self, values, *, dof_indices):
        self.writes.append((tuple(values), tuple(dof_indices)))
        if self.fail:
            raise RuntimeError('setter failure')


def _io():
    io = object.__new__(IsaacSimNativeRuntimeIOV1)
    io._closed = False
    io._episode_origin_step = 0
    io._f06_pickcube = True
    io._dof_index = {f'joint{i}': i - 1 for i in range(1, 8)} | {'finger_joint1': 7, 'finger_joint2': 8}
    io._articulation = FakeArticulation()
    io._sync = lambda: None
    return io


def _values():
    return {f'joint{i}': float(i) for i in range(1, 8)} | {'finger_joint1': .4}


def test_f06_effort_owned_write_clear_and_duplicate_rejection():
    io = _io()
    io.write_physical_effort(_values())
    assert io._articulation.writes == [(tuple(_values().values()), tuple(range(8)))]
    with pytest.raises(RuntimeError, match='available reset interval'):
        io.write_physical_effort(_values())
    assert len(io._articulation.writes) == 1
    io.clear_physical_effort()
    assert io._articulation.writes[-1] == ((0.,) * 8, tuple(range(8)))
    assert io._physical_effort_pending is None
    io.write_physical_effort(_values())
    assert len(io._articulation.writes) == 3


def test_f06_invalid_effort_never_reaches_setter_and_setter_failure_faults():
    io = _io()
    with pytest.raises(ValueError):
        io.write_physical_effort({**_values(), 'joint1': float('nan')})
    assert io._articulation.writes == []
    io._articulation.fail = True
    with pytest.raises(RuntimeError, match='setter failure'):
        io.write_physical_effort(_values())
    io._articulation.fail = False
    with pytest.raises(RuntimeError, match='available reset interval'):
        io.write_physical_effort(_values())
    assert len(io._articulation.writes) == 1
    io.clear_physical_effort()
    assert io._articulation.writes[-1] == ((0.,) * 8, tuple(range(8)))
    assert io._physical_effort_pending is None
    with pytest.raises(RuntimeError, match='available reset interval'):
        io.write_physical_effort(_values())


def test_f06_interval_clears_effort_when_advance_fails():
    session = object.__new__(UsdCoreRuntimeSession)
    class Port:
        pending = 'interval'
        cleared = False
        def finish_interval(self):
            self.cleared = True
            self.pending = None
    port = session._physical_port = Port()
    def fail():
        raise RuntimeError('advance failure')
    session._step_native_interval = fail
    with pytest.raises(RuntimeError, match='advance failure'):
        session.step()
    assert port.cleared and port.pending is None


def test_f06_effort_is_reapplied_before_each_native_step():
    from types import SimpleNamespace
    io = _io()
    io.write_physical_effort(_values())
    io._f06_pickcube = False
    io._dg04_native = False
    io._native_step_count = 0
    io._episode_origin_time = 0.0
    io._artifact = SimpleNamespace(timebase=SimpleNamespace(physics_dt=.002))
    counters = [0, 0.]
    io._counter = lambda: tuple(counters)
    def step(*, steps, update_fabric):
        assert steps == 1 and update_fabric is False
        assert len(io._articulation.writes) == counters[0] + 2
        counters[0] += 1
        counters[1] += .002
    io._manager = SimpleNamespace(step=step)
    assert io.advance().native_step_index == 1
    assert io.advance().native_step_index == 2
    io.clear_physical_effort()
    assert len(io._articulation.writes) == 4
    assert io._articulation.writes[-1][0] == (0.,) * 8


def test_f06_contact_reporter_rejects_capacity_and_incomplete_shape():
    from types import SimpleNamespace
    io = _io()
    io._artifact = SimpleNamespace(timebase=SimpleNamespace(physics_dt=.002))
    class Tensor:
        def __init__(self, value): self.value = value
        def numpy(self): return self
        def tolist(self): return self.value
    class ActorIds:
        def to(self, device):
            assert device == 'cpu'
            return self
        def __getitem__(self, value): return list(range(value.start, value.stop))
    class View:
        def __init__(self, count): self.count = count
        def get_raw_contact_data(self, *, dt):
            assert dt == .002
            return (None, None, None, None, Tensor([self.count]), Tensor([0]), ActorIds())
        def get_actor_paths_from_ids(self, ids): return ['/table'] * len(ids)
    io._f06_robot_contact_views = {'/robot/link': View(0)}
    io._free_views = {'cube-v1': View(4)}
    witness = io._read_f06_robot_contact_witness()
    assert witness['total_contacts'] == 0 and witness['cube_contact_count'] == 4
    assert witness['cube_contact_actor_paths'] == ['/table'] * 4
    io._f06_robot_contact_views['/robot/link'].count = 64
    with pytest.raises(ValueError, match='at capacity'):
        io._read_f06_robot_contact_witness()
