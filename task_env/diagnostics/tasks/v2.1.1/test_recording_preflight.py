"""Unavailable H5 support must be rejected before recording begins."""
import builtins
import pytest

from task_env.recorders.recorder import begin_structured_recording


def test_missing_h5py_rejected_before_recorder_or_metadata(tmp_path, monkeypatch):
    original = builtins.__import__
    def without_h5py(name, *args, **kwargs):
        if name == 'h5py':
            raise ModuleNotFoundError("No module named 'h5py'", name='h5py')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', without_h5py)
    def metadata():
        pytest.fail('metadata must not be prepared after failed dependency preflight')
    with pytest.raises(ModuleNotFoundError, match='h5py'):
        begin_structured_recording(tmp_path / 'episode.h5', horizon=8,
                                   observation={}, reset_info={}, metadata_factory=metadata)
    assert not (tmp_path / 'episode.h5').exists()
