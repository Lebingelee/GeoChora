"""Browse TableCraft tasks, prepare shared assets and prepare existing terminal-review jobs."""

from __future__ import annotations

import argparse
import json

from .evaluation import prepare_terminal_review
from .scene import prepare_assets, scene_resources
from .solution import reference_files
from .task import _read, get_task, list_tasks, model_prompt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="列出当前任务集合")
    show = commands.add_parser("show", help="查看公开题面，或显式查看私有验收")
    show.add_argument("task_id")
    show.add_argument("--include-truth", action="store_true")
    show.add_argument("--asset-directory", help="同时核对准备好的公共资源")
    assets = commands.add_parser("prepare-assets", help="从冻结源准备一份共用资源")
    assets.add_argument("--source-release", required=True)
    assets.add_argument("--output-directory", required=True)
    reference = commands.add_parser("reference", help="核对原演示代码、视频与轨迹")
    reference.add_argument("task_id")
    reference.add_argument("--simdatakit-root", required=True)
    review = commands.add_parser("prepare-review", help="使用现有通用管线离线准备判断与复核")
    review.add_argument("task_id")
    review.add_argument("--evidence-bundle", required=True, help="已有 endpoint/evidence JSON")
    review.add_argument("--artifact-root", required=True)
    review.add_argument("--judge-profile", required=True)
    review.add_argument("--verifier-profile", required=True)
    review.add_argument("--output-directory", required=True)
    args = parser.parse_args(argv)
    if args.command == "list":
        result = list_tasks()
    elif args.command == "show":
        result = get_task(args.task_id) if args.include_truth else model_prompt(args.task_id)
        if args.asset_directory:
            result = {"task": result, "scene": scene_resources(args.task_id, args.asset_directory)}
    elif args.command == "prepare-assets":
        result = {"asset_directory": prepare_assets(args.source_release, args.output_directory)}
    elif args.command == "reference":
        result = reference_files(args.task_id, args.simdatakit_root)
    else:
        from validation.terminal.source_run import prepare_source_run

        bundle = _read(args.evidence_bundle)
        request = prepare_terminal_review(args.task_id, bundle["endpoint"],
            model_profile=_read(args.judge_profile), evidence=bundle["evidence"])
        result = prepare_source_run(request, args.artifact_root, args.output_directory,
            verification_model_profile=_read(args.verifier_profile))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0
