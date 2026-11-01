"""Provider-free checks for the upstream source-model capture lifecycle."""

import hashlib
from types import SimpleNamespace

import pytest

from bench_deploy.libero.assembly.official_model import _capture


class _FakeEnvironment:
    def __init__(self, xml=b'<mujoco><worldbody><camera name="base_camera"/></worldbody></mujoco>', close_error=None):
        self.env = SimpleNamespace(model=SimpleNamespace(get_xml=lambda: xml))
        self.close_error = close_error
        self.calls = []

    def seed(self, value):
        self.calls.append(("seed", value))

    def reset(self):
        self.calls.append(("reset",))

    def close(self):
        self.calls.append(("close",))
        if self.close_error:
            raise self.close_error


def test_official_capture_records_exact_xml_and_closes_environment():
    xml = b'<mujoco><worldbody><camera name="base_camera"/></worldbody></mujoco>'
    env = _FakeEnvironment(xml)
    captured, receipt = _capture(
        env, task_uid="task", seed=19, source_closure_sha256="a" * 64,
    )
    assert captured == xml
    assert receipt["output"]["model_xml_sha256"] == hashlib.sha256(xml).hexdigest()
    assert receipt["camera_names_in_model"] == ["base_camera"]
    assert receipt["close"]["status"] == "CLOSED"
    assert env.calls == [("seed", 19), ("reset",), ("close",)]


def test_official_capture_closes_after_invalid_model_output():
    env = _FakeEnvironment(b"<not-mujoco/>")
    with pytest.raises(ValueError, match="not a MuJoCo XML"):
        _capture(env, task_uid="task", seed=19, source_closure_sha256="b" * 64)
    assert env.calls[-1] == ("close",)
