"""Build and inspect the canonical Go2 Flora asset bundle."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from task_env.tasks.go2_walk.flora_assets import build_go2_flora_bundle


LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT = Path("temp_outputs/task_env/flora/go2_single")


def run(
    output_dir: str | Path = DEFAULT_OUTPUT,
    *,
    instance_count: int = 1,
    force: bool = False,
) -> dict[str, object]:
    bundle = build_go2_flora_bundle(
        output_dir=output_dir,
        instance_count=instance_count,
        force=force,
    )
    report = bundle.describe()
    scene_payload = json.loads(bundle.scene_path.read_text(encoding="utf-8"))
    report["scene_models"] = len(scene_payload.get("models", ()))
    report["scene_graph_roots"] = len(scene_payload.get("graph", ()))
    LOGGER.info("Go2 Flora asset bundle: %s", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--instances", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run(args.output_dir, instance_count=args.instances, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
