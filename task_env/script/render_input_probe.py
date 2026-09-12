"""Probe Taichi Forge window keyboard delivery without TaskEnv or PPO.

The probe deliberately uses a 2-D marker instead of the physics renderer.  It
answers one narrow question: does the headed window receive W/S/A/D press and
release events?  The UI shows both the event-maintained state and
``window.is_pressed()`` so a backend/input-method problem can be separated
from a TaskEnv camera-dispatch problem.

Example::

    PYTHONPATH=GeoPhys/src:. python -m task_env.script.render_input_probe
"""

from __future__ import annotations

import argparse
from collections import deque
import time
from typing import Any

import numpy as np

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from task_env.script._bootstrap import get_logger
else:
    from ._bootstrap import get_logger


WATCHED_KEYS = ("w", "a", "s", "d")
_KEY_ALIASES = {"esc": "escape", "return": "enter", "shift_l": "shift"}


def _token(value: Any) -> str:
    """Normalize Forge enum/string values for readable comparisons."""

    if value is None:
        return ""
    name = getattr(value, "name", None)
    text = str(value if name is None else name).strip().lower()
    return text.rsplit(".", 1)[-1].replace(" ", "_")


def normalize_key(value: Any) -> str:
    """Return a stable lower-case key name from a Forge event key."""

    text = _token(value)
    return _KEY_ALIASES.get(text, text)


def _event_type(value: Any) -> str:
    text = _token(value)
    if text in {"etype.press", "press"}:
        return "press"
    if text in {"etype.release", "release"}:
        return "release"
    if text in {"wmclose", "close", "exit"}:
        return "close"
    return text


def consume_key_events(
    events: list[Any],
    held: set[str],
    event_log: deque[str],
) -> list[tuple[str, str]]:
    """Update event-held keys and return normalized events for the UI loop."""

    observed: list[tuple[str, str]] = []
    for event in events:
        event_type = _event_type(getattr(event, "type", None))
        key = normalize_key(getattr(event, "key", None))
        if event_type == "press" and key in WATCHED_KEYS:
            held.add(key)
        elif event_type == "release" and key in WATCHED_KEYS:
            held.discard(key)
        if event_type == "close":
            key = "window"
        if event_type or key:
            observed.append((event_type, key))
            event_log.appendleft(f"{event_type or '?'}:{key or '?'}")
    return observed


def _native_pressed(window: Any, key: str) -> bool:
    try:
        return bool(window.is_pressed(key))
    except (AttributeError, RuntimeError, TypeError):
        return False


def _move_marker(
    position: np.ndarray,
    held: set[str],
    dt: float,
    width: int,
    height: int,
) -> None:
    """Move the probe marker using the effective held-key state."""

    direction = np.zeros(2, dtype=np.float32)
    if "a" in held:
        direction[0] -= 1.0
    if "d" in held:
        direction[0] += 1.0
    if "w" in held:
        direction[1] -= 1.0
    if "s" in held:
        direction[1] += 1.0
    norm = float(np.linalg.norm(direction))
    if norm:
        direction /= norm
        position += direction * (260.0 * min(max(dt, 0.0), 0.05))
    position[0] = np.clip(position[0], 24.0, width - 25.0)
    position[1] = np.clip(position[1], 145.0, height - 25.0)


def _make_frame(width: int, height: int, position: np.ndarray) -> np.ndarray:
    """Build a small visible playfield for the keyboard probe."""

    frame = np.empty((height, width, 4), dtype=np.uint8)
    frame[:, :, :3] = (22, 30, 43)
    frame[:, :, 3] = 255
    frame[:120, :, :3] = (34, 46, 64)

    grid_color = np.asarray((43, 58, 78), dtype=np.uint8)
    for x in range(24, width - 20, 48):
        frame[144:, x : x + 1, :3] = grid_color
    for y in range(144, height - 20, 48):
        frame[y : y + 1, 24 : width - 20, :3] = grid_color
    frame[143:145, 24 : width - 20, :3] = (83, 104, 132)
    frame[height - 21 : height - 19, 24 : width - 20, :3] = (83, 104, 132)
    frame[144 : height - 20, 23:25, :3] = (83, 104, 132)
    frame[144 : height - 20, width - 21 : width - 19, :3] = (83, 104, 132)

    center_x = int(round(float(position[0])))
    center_y = int(round(float(position[1])))
    frame[center_y - 11 : center_y + 12, center_x - 11 : center_x + 12, :3] = (
        68,
        197,
        158,
    )
    frame[center_y - 2 : center_y + 3, center_x - 17 : center_x + 18, :3] = (
        242,
        202,
        91,
    )
    frame[center_y - 17 : center_y + 18, center_x - 2 : center_x + 3, :3] = (
        242,
        202,
        91,
    )
    return np.ascontiguousarray(frame)


def _read_events(window: Any) -> list[Any]:
    """Read the unconsumed Forge event queue after an explicit poll."""

    window.poll_events()
    try:
        return list(window.get_events(poll=False))
    except TypeError:
        # Compatibility with older Forge builds whose get_events has no
        # keyword-only poll argument.
        return list(window.get_events(None, False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=("cpu", "cuda", "vulkan"), default="cpu")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
    parser.add_argument("--fps-limit", type=int, default=60)
    args = parser.parse_args()
    if args.width < 320 or args.height < 240 or args.fps_limit < 1:
        parser.error("width must be >= 320, height >= 240, and fps-limit must be positive")

    logger = get_logger("task-env-render-input-probe")
    import taichi as ti

    arch = {"cpu": ti.cpu, "cuda": ti.cuda, "vulkan": ti.vulkan}[args.arch]
    logger.info(
        "Starting standalone keyboard input probe",
        event="task_env.render_input_probe.start",
        arch=args.arch,
        watched_keys=WATCHED_KEYS,
        input_method_hint="click the window before pressing keys",
    )
    ti.init(arch=arch, offline_cache=True)
    window = ti.ui.Window(
        "GeoPhys Keyboard Input Probe",
        res=(args.width, args.height),
        vsync=False,
        fps_limit=args.fps_limit,
    )
    canvas = window.get_canvas()
    gui = window.get_gui()
    held_by_event: set[str] = set()
    event_log: deque[str] = deque(maxlen=6)
    marker = np.asarray((args.width / 2.0, (args.height + 144.0) / 2.0), dtype=np.float32)
    previous_time = time.perf_counter()
    event_count = 0
    last_event = "none"

    try:
        while window.running:
            now = time.perf_counter()
            dt = now - previous_time
            previous_time = now
            observed = consume_key_events(
                _read_events(window),
                held_by_event,
                event_log,
            )
            for event_type, key in observed:
                event_count += 1
                last_event = f"{event_type or '?'}:{key or '?'}"
                logger.info(
                    "Keyboard event observed",
                    event="task_env.render_input_probe.key_event",
                    event_type=event_type or "unknown",
                    key=key or "unknown",
                    event_held=sorted(held_by_event),
                )
            if any(event_type == "close" for event_type, _key in observed):
                break

            native = {key: _native_pressed(window, key) for key in WATCHED_KEYS}
            effective = set(held_by_event)
            effective.update(key for key, pressed in native.items() if pressed)
            _move_marker(marker, effective, dt, args.width, args.height)
            canvas.set_image(_make_frame(args.width, args.height, marker))

            if gui is not None:
                gui.text("GeoPhys keyboard input probe")
                gui.text("Click this window, then hold W / S / A / D")
                gui.text("E=event queue   N=is_pressed()   X=effective")
                gui.text(
                    " ".join(
                        f"{key.upper()} E:{int(key in held_by_event)} "
                        f"N:{int(native[key])} X:{int(key in effective)}"
                        for key in WATCHED_KEYS
                    )
                )
                gui.text(f"Last event: {last_event} | Events: {event_count}")
                gui.text(f"Marker: ({marker[0]:.0f}, {marker[1]:.0f})")
                gui.text("Recent: " + (" | ".join(event_log) if event_log else "none"))
            window.show()
    finally:
        logger.success(
            "Standalone keyboard input probe closed",
            event="task_env.render_input_probe.complete",
            observed_events=event_count,
            remaining_event_held=sorted(held_by_event),
            marker=(float(marker[0]), float(marker[1])),
        )


if __name__ == "__main__":
    main()
