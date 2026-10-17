from __future__ import annotations

from contextlib import contextmanager
import importlib
import json
from pathlib import Path

import numpy as np
import pytest


def test_rsl_cli_requires_explicit_task_uid():
    parser = importlib.import_module("task_env.script.rl.rsl_ppo")._parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([])
    assert exc.value.code == 2
    assert parser.parse_args(["--env-id", "pendulum-v1"]).env_id == "pendulum-v1"


def test_retired_render_and_camera_routes_fail_with_recovery_guidance(capsys):
    modules = (
        "task_env.script.render_single",
        "task_env.script.camera.static",
        "task_env.script.camera.bound",
        "task_env.script.camera_lighting_probe",
    )
    for name in modules:
        module = importlib.import_module(name)
        assert module.main([]) == 2
        output = capsys.readouterr().err
        assert "retired" in output
        assert "p2_0_s4_5_b_source_recovery.json" in output


def test_example_bounds_are_linux_oriented(monkeypatch):
    from examples._common import bounded_process

    monkeypatch.setattr("examples._common.sys.platform", "darwin")
    with pytest.raises(RuntimeError, match="supported on Linux"):
        with bounded_process(2048, 30):
            pytest.fail("the Linux-specific limit block should not run")


def test_pendulum_example_delegates_to_existing_sb3_runner(tmp_path, monkeypatch, capsys):
    example = importlib.import_module("examples.learning.pendulum_sb3")
    runner = importlib.import_module("task_env.script.rl.pendulum_ppo")

    @contextmanager
    def no_process_limits(memory_limit_mb, time_limit_s):
        yield {"address_space_limit_bytes": 1024, "scope": "test"}

    calls = []

    def fake_train(argv):
        calls.append(list(argv))
        output = Path(argv[argv.index("--output-dir") + 1])
        (output / "summary.json").write_text(
            json.dumps(
                {
                    "batches": [
                        {
                            "backend": "cpu",
                            "batch_physics_layout": "merged_scene",
                            "num_env": 2,
                            "timesteps": 4,
                            "updates_completed": 1,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (output / "return_curve.h5").write_bytes(b"test placeholder")
        return 0

    monkeypatch.setattr(example, "bounded_process", no_process_limits)
    monkeypatch.setattr(runner, "main", fake_train)
    output = tmp_path / "run"
    assert example.main(["--output-dir", str(output)]) == 0
    assert calls and calls[0][calls[0].index("--backend") + 1] == "cpu"
    assert calls[0][calls[0].index("--batch-physics-layout") + 1] == "merged_scene"
    result = json.loads((output / "example_result.json").read_text(encoding="utf-8"))
    assert result["status"] == "PASS_BOUNDED_SMOKE_NOT_QUALIFICATION"
    assert "NOT_QUALIFICATION" in capsys.readouterr().out


def test_pendulum_example_rejects_existing_output_directory(tmp_path):
    example = importlib.import_module("examples.learning.pendulum_sb3")
    with pytest.raises(SystemExit) as exc:
        example.main(["--output-dir", str(tmp_path)])
    assert exc.value.code == 2


def test_render_example_delegates_to_bounded_supported_cli(monkeypatch, capsys):
    example = importlib.import_module("examples.rendering.pendulum_parallel_rgb")
    render_cli = importlib.import_module("task_env.script.render_parallel")

    @contextmanager
    def no_process_limits(memory_limit_mb, time_limit_s):
        yield {"address_space_limit_bytes": 1024, "scope": "test"}

    calls = []
    monkeypatch.setattr(example, "bounded_process", no_process_limits)
    monkeypatch.setattr(render_cli, "main", lambda argv: calls.append(argv) or 0)
    assert example.main([]) == 0
    assert calls and calls[0][calls[0].index("--env-id") + 1] == "pendulum-v1"
    assert calls[0][calls[0].index("--render-backend") + 1] == "rasterizer"
    assert calls[0][calls[0].index("--backend") + 1] == "cpu"
    assert "PASS_BOUNDED_RENDER_SMOKE_NOT_QUALIFICATION" in capsys.readouterr().out


def test_scalar_render_example_uses_current_public_pendulum_api(monkeypatch, capsys):
    example = importlib.import_module("examples.rendering.pendulum_single_rgb")

    @contextmanager
    def no_process_limits(memory_limit_mb, time_limit_s):
        yield {"address_space_limit_bytes": 1024, "scope": "test"}

    class Space:
        def contains(self, value):
            return True

    class FakeEnv:
        observation_space = Space()

        def __init__(self):
            self.calls = []

        def reset(self, *, seed):
            self.calls.append(("reset", seed))
            return {}, {}

        def render(self):
            return np.zeros((24, 32, 3), dtype=np.float32)

        def step(self, action):
            self.calls.append(("step", action))
            return {}, 0.0, False, False, {"task_success": False}

        def close(self):
            self.calls.append(("close",))

    env = FakeEnv()
    calls = []

    def fake_make_env(uid, **kwargs):
        calls.append((uid, kwargs))
        return env

    monkeypatch.setattr(example, "bounded_process", no_process_limits)
    monkeypatch.setattr(example, "bootstrap_imports", lambda: None)
    monkeypatch.setattr("task_env.make_env", fake_make_env)
    assert example.main([]) == 0
    assert calls[0][0] == "pendulum-v1"
    assert calls[0][1]["render_mode"] == "rgb_array"
    assert env.calls[0] == ("reset", 73)
    assert env.calls[-1] == ("close",)
    result = json.loads(capsys.readouterr().out)
    assert result["frame_shape"] == [24, 32, 3]
    assert result["expert_complete"] is None


def test_offline_h5_inspector_reports_validation_without_d0_claim(monkeypatch, capsys, tmp_path):
    inspector = importlib.import_module("examples.recording.inspect_h5")
    monkeypatch.setattr(
        inspector,
        "load_recording_summary",
        lambda path: {
            "schema": "canonical-trajectory-v0",
            "transitions": 4,
            "boundaries": 5,
            "t_plus_one_valid": True,
            "storage_roundtrip": "PASS",
            "D0": "NOT_ASSESSED",
        },
    )
    assert inspector.main(["--input", str(tmp_path / "recording.h5")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PASS"
    assert "not D0 replay" in result["interpretation"]

    monkeypatch.setattr(
        inspector,
        "load_recording_summary",
        lambda path: {"t_plus_one_valid": False, "D0": "NOT_ASSESSED"},
    )
    assert inspector.main(["--input", str(tmp_path / "bad.h5")]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"
