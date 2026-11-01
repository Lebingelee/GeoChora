"""Run a frozen LIBERO A sequence, or the optional V8 policy, through TaskEnv."""
from __future__ import annotations

import json
from pathlib import Path


def _load_actions(path: Path, task_uid: str):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        rows = [row for row in data["results"] if row.get("task_uid") == task_uid]
        if len(rows) != 1:
            raise ValueError("action capture must contain exactly one selected task")
        row = rows[0]
        return row.get("transitions"), row.get("reset_sample_v1")
    if isinstance(data, dict):
        if data.get("task_uid") not in (None, task_uid):
            raise ValueError("action sequence belongs to a different LIBERO task")
        return data.get("transitions", data.get("actions")), data.get("reset_sample_v1")
    return data, None


def _source_gravity(env, plan_bytes: bytes, task_uid: str):
    from bench_deploy.libero.controllers.source_gravity import MujocoSourceGravityBiasV1

    value = env.value
    profile = value.get("model_profile_bytes")
    model = MujocoSourceGravityBiasV1(
        source_receipt=value["source"].execution_source_receipt,
        composition_plan_bytes=plan_bytes,
        raw_source_xml_bytes=value["source_xml_bytes"] if isinstance(profile, bytes) else None,
        model_profile_bytes=profile if isinstance(profile, bytes) else None,
        task_uid=task_uid,
    )
    env.value["bind_source_gravity_model"](model)
    return model


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--run-replay", type=Path, metavar="OUTPUT_DIR")
    modes.add_argument("--read-result", type=Path, metavar="RESULT_JSON")
    parser.add_argument("--task", choices=("task1", "task2", "task3"))
    parser.add_argument("--provider", choices=("mujoco", "geophys"), default="mujoco")
    parser.add_argument("--actions", type=Path)
    parser.add_argument("--reset-sample", type=Path)
    parser.add_argument("--source-xml", type=Path)
    parser.add_argument("--composition-plan", type=Path)
    parser.add_argument("--install-root", type=Path)
    parser.add_argument("--init-path", type=Path)
    parser.add_argument("--solution", action="store_true", help="run the optional V8 policy")
    parser.add_argument("--row", type=int, default=0)
    parser.add_argument("--seed", type=int, default=19)
    parser.add_argument("--maximum-steps", type=int, default=1000)
    args = parser.parse_args(argv)
    if args.read_result:
        from bench_deploy.libero.trajectory.reader import consume_libero_replay_result

        print(json.dumps(consume_libero_replay_result(args.read_result), sort_keys=True, indent=2))
        return 0
    if not all((args.task, args.source_xml, args.composition_plan,
                args.install_root, args.init_path)):
        parser.error("--run-replay requires --task, --source-xml, --composition-plan, --install-root, and --init-path")
    task_uid = f"libero/{args.task}"
    if args.solution:
        transitions, embedded_reset = None, None
    else:
        if args.actions is None:
            parser.error("frozen replay requires --actions")
        transitions, embedded_reset = _load_actions(args.actions, task_uid)
        if not isinstance(transitions, list) or not transitions:
            parser.error("selected action file has no transitions")
    reset_payload = None
    if args.reset_sample:
        reset_payload = json.loads(args.reset_sample.read_text(encoding="utf-8"))
    elif embedded_reset is not None:
        reset_payload = embedded_reset
    reset_options = None
    if args.task != "task1":
        if not isinstance(reset_payload, dict):
            parser.error("task2/3 replay requires a serialized ResetSampleV1 in --reset-sample or the action file")
        from task_env.artifacts import ResetSampleV1

        reset_options = {"task_reset_sample_v1": ResetSampleV1.from_mapping(reset_payload)}
    from bench_deploy.libero.artifacts.contracts import TASK_1, TASK_2, TASK_3
    from bench_deploy.libero.environment.selected_reference import (
        DEFAULT_INSTALL_ROOT, build_libero_selected_candidate,
        PANDA_GRIPPER_DELTA_REPLAY_PROFILE_ID,
    )
    from bench_deploy.libero.trajectory.worker import run_libero_replay

    task_id = {"task1": TASK_1, "task2": TASK_2, "task3": TASK_3}[args.task]
    install_root = args.install_root or DEFAULT_INSTALL_ROOT
    init_path = args.init_path
    plan_path = args.composition_plan.resolve(strict=True)
    plan_bytes = plan_path.read_bytes()
    raw_xml = args.source_xml.resolve(strict=True).read_bytes()
    options = {
        "xml": raw_xml,
        "composition_plan_path": plan_path, "install_root": install_root,
        "init_path": init_path, "horizon": min(1000, max((len(transitions) if transitions else args.maximum_steps) + 1, 1)),
        "provider": args.provider, "task_uid": task_id,
    }
    env = build_libero_selected_candidate(
        **options,
        _execution_profile="v8" if args.solution else "a-reference",
        _gripper_action_profile=(
            None if args.solution else PANDA_GRIPPER_DELTA_REPLAY_PROFILE_ID
        ),
    )
    args.run_replay.parent.mkdir(parents=True, exist_ok=True)
    _source_gravity(env, plan_bytes, task_id)
    solution_factory = None
    if args.solution:
        from bench_deploy.libero.tasks.solution import LiberoPickPlaceSolutionV8

        solution_factory = lambda _root: LiberoPickPlaceSolutionV8(
            env.value["runtime_model_xml_bytes"],
            source_closure_digest=env.metadata["source_closure_digest"],
            arm_resolver_identity=env.value["arm_resolver_identity"],
        )
    result = run_libero_replay(
        env, output_dir=args.run_replay, action_sequence=None if args.solution else transitions,
        solution_factory=solution_factory, seed=args.seed, row_index=args.row,
        reset_options=reset_options, maximum_steps=args.maximum_steps,
    )
    print(json.dumps({"status": result["status"], "result_sha256": result["result_sha256"]}, sort_keys=True))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
