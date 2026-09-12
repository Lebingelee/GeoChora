"""Training-time headed rendering controls.

The controller in this module is deliberately outside the PPO/RSL learner.
It only schedules optional ``human`` presentation and polls a renderer-owned
input surface.  Physics stepping, reset/autoreset, actions and optimizer
state remain owned by the wrapped environment/runner.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Mapping

from visualization.input_bindings import ViewportAction


@dataclass(frozen=True)
class TrainingRenderKeyMap:
    """Independent training-window keys.

    ``F`` toggles frame submission. ``Esc`` disables frame submission but does
    not stop the learner. The simulation keys (Space/N/R/P/O/V) are reserved
    and cannot be silently reinterpreted by this controller.
    """

    toggle: str = "f"
    disable: str = "Escape"
    action: ViewportAction = field(
        # GeoPhys main names the viewport presentation toggle
        # ``TOGGLE_RENDER_OVERLAY``.  The training controller's F key remains
        # TaskEnv-owned; this enum value is only the provider action label.
        default=ViewportAction.TOGGLE_RENDER_OVERLAY,
        init=False,
    )

    def __post_init__(self) -> None:
        toggle = str(self.toggle).strip()
        disable = str(self.disable).strip()
        if not toggle or not disable or toggle == disable:
            raise ValueError("training render keys must be non-empty and distinct")
        reserved = {"w", "a", "s", "d", "e", "q", "n", "r", "p", "o", "v"}
        if toggle.lower() in reserved or disable.lower() in reserved:
            raise ValueError(
                "training render toggle key conflicts with camera or viewport controls"
            )
        if toggle == " " or disable == " ":
            raise ValueError("training render keys cannot override Space simulation control")
        object.__setattr__(self, "toggle", toggle)
        object.__setattr__(self, "disable", disable)


@dataclass(frozen=True)
class TrainingRenderEvents:
    """Renderer-owned input events returned between policy ticks."""

    running: bool = True
    toggle: bool = False
    disable: bool = False


@dataclass(frozen=True)
class TrainingRenderSettings:
    """Resolved task-owned settings for a headed parallel training view."""

    backend: str
    width: int
    height: int
    render_num: int
    render_every: int
    columns: int
    cell_width: float
    cell_depth: float
    padding: float
    hard_render: bool = False
    hard_render_num: int = 16

    def layout(self) -> dict[str, float | int]:
        return {
            "cell_width": float(self.cell_width),
            "cell_depth": float(self.cell_depth),
            "columns": int(self.columns),
            "padding": float(self.padding),
        }

    def describe(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "mode": (
                "hard_assets"
                if self.hard_render
                else "shared_assets" if self.backend == "flora" else "simple_geometry"
            ),
            "width": int(self.width),
            "height": int(self.height),
            "parallel": {
                "num": int(self.render_num),
                **self.layout(),
            },
            "training": {"every": int(self.render_every)},
            "hard_render_num": int(self.hard_render_num),
        }


def resolve_training_render_settings(
    render_config: Mapping[str, Any] | object,
    *,
    num_env: int,
    hard_render: bool = False,
    hard_render_num: int = 16,
) -> TrainingRenderSettings:
    """Resolve a ``RenderConfig``/manifest mapping for one training run.

    ``render.parallel.num`` is intentionally an upper bound because the task
    default is shared by runs with different physics batch sizes.  A 256-world
    default therefore becomes 2 for a two-world smoke without a second YAML.
    """

    if isinstance(render_config, Mapping):
        read = render_config.get
        parallel_config = render_config.get("parallel", {})
        training_config = render_config.get("training", {})
    else:
        read = lambda name, default=None: getattr(render_config, name, default)
        parallel_config = getattr(render_config, "parallel", {})
        training_config = getattr(render_config, "training", {})
    if not isinstance(parallel_config, Mapping):
        parallel_config = vars(parallel_config)
    if not isinstance(training_config, Mapping):
        training_config = vars(training_config)

    env_count = int(num_env)
    if env_count < 1:
        raise ValueError("num_env must be positive")
    if int(hard_render_num) not in (16, 32, 64, 96, 128, 256):
        raise ValueError(
            "hard_render_num must be 16, 32, 64, 96, 128, or 256"
        )
    configured_num = parallel_config.get("num", 256)
    if configured_num is None:
        configured_num = 256
    render_num = (
        min(env_count, int(hard_render_num))
        if hard_render
        else min(env_count, int(configured_num))
    )
    if render_num < 1:
        raise ValueError("parallel_render_num must resolve to a positive count")
    return TrainingRenderSettings(
        backend=str(read("backend", "raytracer")),
        width=int(read("width", 640)),
        height=int(read("height", 480)),
        render_num=render_num,
        render_every=int(training_config.get("every", 1)),
        columns=int(parallel_config.get("columns", 16)),
        cell_width=float(parallel_config.get("cell_width", 1.0)),
        cell_depth=float(parallel_config.get("cell_depth", 1.0)),
        padding=float(parallel_config.get("padding", 0.0)),
        hard_render=bool(hard_render),
        hard_render_num=int(hard_render_num),
    )


def _coerce_events(value: object) -> TrainingRenderEvents:
    if isinstance(value, TrainingRenderEvents):
        return value
    if isinstance(value, Mapping):
        return TrainingRenderEvents(
            running=bool(value.get("running", True)),
            toggle=bool(value.get("toggle", False)),
            disable=bool(value.get("disable", False)),
        )
    if value is None:
        return TrainingRenderEvents()
    return TrainingRenderEvents(
        running=bool(getattr(value, "running", True)),
        toggle=bool(getattr(value, "toggle", False)),
        disable=bool(getattr(value, "disable", False)),
    )


class TrainingRenderController:
    """Schedule optional human frames without entering the physics hot path.

    The render environment must expose ``render(mode="human")``.  For
    keyboard control it may additionally expose ``poll_render_events()`` and
    ``consume_render_events()``; those methods are intentionally optional so
    the controller remains usable with a minimal fake or another UI backend.
    """

    def __init__(
        self,
        render_env: object,
        *,
        enabled: bool = False,
        render_every: int = 1,
        render_num: int | None = None,
        keymap: TrainingRenderKeyMap | None = None,
    ) -> None:
        if render_env is None or not callable(getattr(render_env, "render", None)):
            raise ValueError("training render controller requires render_env.render()")
        if isinstance(render_every, bool) or int(render_every) < 1:
            raise ValueError("training render_every must be a positive integer")
        if render_num is not None and int(render_num) < 1:
            raise ValueError("training render_num must be positive when provided")
        self.render_env = render_env
        self.render_every = int(render_every)
        self.keymap = keymap or TrainingRenderKeyMap()
        self._enabled = bool(enabled)
        self._render_num = None if render_num is None else int(render_num)
        self._step = 0
        self._started = False
        self._closed = False
        self._mailbox: deque[str] = deque()
        self._render_count = 0
        self._toggle_count = 0
        self._disable_count = 0
        self._window_closed_count = 0

        set_keys = getattr(render_env, "set_render_control_keys", None)
        if callable(set_keys):
            set_keys(toggle=self.keymap.toggle, disable=self.keymap.disable)

        if self._render_num is not None:
            setter = getattr(render_env, "set_parallel_render_num", None)
            if not callable(setter):
                raise ValueError(
                    "training render_num requires set_parallel_render_num()"
                )
            setter(self._render_num)

    @property
    def enabled(self) -> bool:
        return bool(self._enabled)

    @property
    def step_index(self) -> int:
        return int(self._step)

    def describe(self) -> dict[str, object]:
        """Return a small artifact-safe render lifecycle summary."""

        return {
            "schema": "task_env.training_render.v1",
            "enabled": bool(self._enabled),
            "started": bool(self._started),
            "closed": bool(self._closed),
            "render_every": int(self.render_every),
            "render_num": self._render_num,
            "toggle_count": int(self._toggle_count),
            "disable_count": int(self._disable_count),
            "window_closed_count": int(self._window_closed_count),
            "render_count": int(self._render_count),
            "last_policy_step": int(self._step),
            "toggle_key": self.keymap.toggle,
            "disable_key": self.keymap.disable,
            "toggle_action": self.keymap.action.value,
        }

    def request_toggle(self) -> None:
        """Queue a toggle for the next policy tick."""

        self._mailbox.append("toggle")

    def request_enable(self) -> None:
        """Queue opening/enabling the renderer on the next policy tick."""

        self._mailbox.append("enable")

    def request_disable(self) -> None:
        """Queue frame suppression without stopping the learner."""

        self._mailbox.append("disable")

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("training render controller is closed")
        if self._started:
            return
        self._started = True
        self._apply_mailbox()
        if self._enabled:
            self._render_once()
        else:
            self._poll_and_apply_events()

    def on_policy_step(self) -> None:
        """Advance the display scheduler after one learner environment step."""

        if self._closed:
            return
        if not self._started:
            self.start()
        self._step += 1
        self._apply_mailbox()
        rendered = False
        if self._enabled and self._step % self.render_every == 0:
            self._render_once()
            rendered = True
        else:
            self._poll_and_apply_events()
        # F/enable may arrive while the controller was disabled.  Make the
        # transition visible immediately without adding a second frame when
        # the normal cadence already rendered this tick.
        if self._enabled and not rendered and self._events_enabled_this_tick:
            self._render_once()

    def _apply_mailbox(self) -> None:
        self._events_enabled_this_tick = False
        while self._mailbox:
            command = self._mailbox.popleft()
            if command == "toggle":
                self._enabled = not self._enabled
                self._toggle_count += 1
                self._events_enabled_this_tick |= self._enabled
            elif command == "enable":
                self._enabled = True
                self._events_enabled_this_tick = True
            elif command == "disable":
                self._enabled = False
                self._disable_count += 1
            else:  # pragma: no cover - only internal literals are enqueued
                raise RuntimeError(f"unknown training render command: {command!r}")

    def _poll_and_apply_events(self) -> None:
        poll = getattr(self.render_env, "poll_render_events", None)
        if not callable(poll):
            return
        events = _coerce_events(poll())
        self._apply_events(events)

    def _consume_and_apply_events(self) -> None:
        consume = getattr(self.render_env, "consume_render_events", None)
        if not callable(consume):
            return
        self._apply_events(_coerce_events(consume()))

    def _apply_events(self, events: TrainingRenderEvents) -> None:
        if not events.running:
            if self._enabled:
                self._window_closed_count += 1
            self._enabled = False
            return
        if events.disable:
            self._enabled = False
            self._disable_count += 1
        if events.toggle:
            self._enabled = not self._enabled
            self._toggle_count += 1
            self._events_enabled_this_tick |= self._enabled

    def _render_once(self) -> None:
        self.render_env.render(mode="human")
        self._render_count += 1
        self._consume_and_apply_events()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._enabled = False
        close_render = getattr(self.render_env, "close_render", None)
        if callable(close_render):
            close_render()


class TrainingRenderVecAdapter:
    """Transparent learner wrapper that invokes a render controller per step."""

    def __init__(self, env: object, controller: TrainingRenderController) -> None:
        object.__setattr__(self, "_env", env)
        object.__setattr__(self, "controller", controller)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._env, name)

    def __setattr__(self, name: str, value: object) -> None:
        if name in {"_env", "controller"} or name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        env = self.__dict__.get("_env")
        if env is not None and hasattr(env, name):
            setattr(env, name, value)
            return
        object.__setattr__(self, name, value)

    def step(self, actions: object):
        result = self._env.step(actions)
        self.controller.on_policy_step()
        return result

    def close(self) -> None:
        self.controller.close()
        self._env.close()


__all__ = [
    "TrainingRenderController",
    "TrainingRenderEvents",
    "TrainingRenderKeyMap",
    "TrainingRenderSettings",
    "TrainingRenderVecAdapter",
    "resolve_training_render_settings",
]
