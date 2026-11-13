"""The examples must not replay failed construction or training on CPU."""

import pytest

from task_env.script._bootstrap import backend_candidates, with_backend_fallback


class Logger:
    def __init__(self):
        self.events = []

    def info(self, message, **fields):
        self.events.append((message, fields))


@pytest.mark.parametrize("requested, expected", [("auto", "cuda"), ("cuda", "cuda"), ("cpu", "cpu"), ("vulkan", "vulkan")])
def test_backend_selection_calls_factory_once_and_reports_request(requested, expected):
    logger = Logger()
    calls = []
    backend, result = with_backend_fallback(
        requested, lambda value: calls.append(value) or object(),
        logger=logger, operation="fake",
    )
    assert result is not None
    assert backend == expected
    assert calls == [expected]
    assert logger.events[0][1]["requested_backend"] == requested
    assert logger.events[0][1]["backend"] == expected


@pytest.mark.parametrize("requested", ["auto", "cuda"])
def test_configuration_or_training_failure_is_not_replayed(requested):
    error = ValueError("invalid configuration or training failure")
    calls = []

    def factory(backend):
        calls.append(backend)
        raise error

    with pytest.raises(ValueError) as caught:
        with_backend_fallback(requested, factory, logger=Logger(), operation="fake")
    assert caught.value is error
    assert calls == ["cuda"]


def test_invalid_backend_is_rejected_before_factory():
    with pytest.raises(ValueError):
        backend_candidates("unknown")
