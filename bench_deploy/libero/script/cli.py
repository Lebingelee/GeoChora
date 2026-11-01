"""Command line for the bounded LIBERO replay worker and bundle reader."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json

def main(argv: list[str] | None = None) -> int:
    """Native worker and separate provider-free reader entry points."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--run-worker", metavar="OUTPUT_DIR")
    modes.add_argument("--read-bundle", metavar="WORKER_RESULT_JSON")
    parser.add_argument("--parent-run-record", type=Path)
    parser.add_argument("--expected-lock-path", type=Path)
    parser.add_argument("--steps", type=int, default=64)
    parser.add_argument("--rows", type=int, nargs="+", default=(0, 1, 2))
    parser.add_argument("--task-solution", action="store_true",
                        help="run the latest optional demonstration-derived Solution")
    parser.add_argument("--source-xml", type=Path)
    parser.add_argument("--composition-plan", type=Path)
    parser.add_argument("--install-root", type=Path)
    parser.add_argument("--require-motion-thresholds", action="store_true")
    parser.add_argument("--require-mujoco-runtime-identity", action="store_true")
    args = parser.parse_args(argv)
    if args.read_bundle:
        from bench_deploy.libero.trajectory.reader import consume_libero_candidate_bundle

        receipt = consume_libero_candidate_bundle(
            Path(args.read_bundle), parent_run_record_path=args.parent_run_record,
            expected_lock_path=args.expected_lock_path,
            require_motion_thresholds=args.require_motion_thresholds,
            require_mujoco_runtime_identity=args.require_mujoco_runtime_identity,
        )
        print(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
        return 0
    if args.task_solution:
        if not all((args.source_xml, args.composition_plan, args.install_root)):
            parser.error("--task-solution requires --source-xml, --composition-plan, and --install-root")
        from bench_deploy.libero.environment.selected_reference import build_libero_solution_candidate
        from bench_deploy.libero.tasks.solution import LiberoPickPlaceSolutionV8
        from bench_deploy.libero.controllers.source_gravity import MujocoSourceGravityBiasV1
        from bench_deploy.libero.trajectory.worker import run_libero_candidate_worker

        raw_source_xml = args.source_xml.resolve(strict=True).read_bytes()
        composition_plan_path = args.composition_plan.resolve(strict=True)
        plan_bytes = composition_plan_path.read_bytes()
        install_root = args.install_root.resolve(strict=True)
        selected_solution_version = "v8"
        env = build_libero_solution_candidate(
            xml=raw_source_xml,
            composed_mjcf_sha256=hashlib.sha256(raw_source_xml).hexdigest(),
            install_root=install_root, composition_plan_path=composition_plan_path,
            horizon=args.steps,
        )
        source_files = dict(env.value["source"].execution_source_receipt.closure_files)
        profile_bytes = env.value["model_profile_bytes"]
        if not isinstance(profile_bytes, bytes):
            raise ValueError("task Solution candidate omitted its deterministic model profile receipt")

        class _Task1SolutionFactory:
            def __init__(self):
                self.worker_result_schema_version = (
                    f"r07-v210-task-solution-worker-result-{selected_solution_version}"
                )
                self.gravity_model = None
                self.bundle_root = None

            def __call__(self, bundle_root):
                candidate_root = Path(bundle_root).resolve(strict=True)
                if self.gravity_model is None:
                    self.bundle_root = candidate_root
                    self.gravity_model = MujocoSourceGravityBiasV1(
                        bundle_root=candidate_root,
                        source_closure_files=source_files,
                        source_xml_sha256=env.metadata["source_xml_sha256"],
                        source_closure_digest=env.metadata["source_closure_digest"],
                        composition_plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
                        raw_source_xml_bytes=raw_source_xml,
                        model_profile_bytes=profile_bytes,
                    )
                elif candidate_root != self.bundle_root:
                    raise ValueError("same-Env Solution factory received a different worker source bundle")
                env.value["bind_source_gravity_model"](self.gravity_model)
                return LiberoPickPlaceSolutionV8(
                    env.value["runtime_model_xml_bytes"],
                    source_closure_digest=env.metadata["source_closure_digest"],
                    arm_resolver_identity=env.value["arm_resolver_identity"],
                )

            def close_resources(self):
                return env.value['close_task_resources']()

        solution_factory = _Task1SolutionFactory()
        result = run_libero_candidate_worker(
            env, output_dir=Path(args.run_worker), rows=tuple(args.rows), steps=args.steps,
            solution_factory=solution_factory,
            source_closure_files=source_files,
            composition_plan_bytes=plan_bytes,
            source_raw_xml_bytes=raw_source_xml,
            source_model_profile_bytes=profile_bytes,
            solution_resource_closer=solution_factory.close_resources,
        )
    else:
        from bench_deploy.libero.environment.selected_reference import build_libero_selected_candidate
        from bench_deploy.libero.trajectory.worker import run_libero_candidate_worker

        env = build_libero_selected_candidate(horizon=args.steps)
        result = run_libero_candidate_worker(
            env, output_dir=Path(args.run_worker), rows=tuple(args.rows), steps=args.steps,
        )
    print(json.dumps({
        "status": result["status"], "episode_count": result["episode_count"],
        "transition_count": result["transition_count"],
        "observation_count": result["observation_count"],
        "native_step_count": result["native_step_count"],
        "result_sha256": result["result_sha256"],
    }, sort_keys=True))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
