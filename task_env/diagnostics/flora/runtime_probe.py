"""Probe an installed Flora checkout without starting a Vulkan device.

Run from the repository root::

    PYTHONPATH=GeoPhys/src:. python -m task_env.diagnostics.flora.runtime_probe \
        --flora-root /home/zyf/lly_project/Flora
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from task_env.render.flora.runtime import FloraRuntimeConfig, probe_flora_runtime


LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT = Path("temp_outputs/task_env/flora/runtime_probe.json")


def run(root: str | Path, *, output: str | Path | None = None) -> dict[str, object]:
    config = FloraRuntimeConfig.resolve(runtime_root=root)
    report = probe_flora_runtime(config).describe()
    if output is not None:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    LOGGER.info("Flora runtime probe: %s", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flora-root", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = run(args.flora_root, output=args.output)
    return 0 if bool(report["available"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
