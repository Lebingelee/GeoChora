"""Convert a Go2 policy checkpoint between RSL-RL 1.x and 5.x layouts.

Only actor/critic tensors and the explicit policy manifest are transferred.
Optimizer/RND state is intentionally omitted: those objects are not portable
across the two RSL-RL APIs and must be recreated by the target runner.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--direction", choices=("legacy-to-current", "current-to-legacy"), required=True)
    parser.add_argument("--observation-dim", type=int, default=48)
    parser.add_argument("--action-dim", type=int, default=12)
    parser.add_argument("--hidden-dims", type=int, nargs="+", default=(512, 256, 128))
    parser.add_argument("--activation", default="elu")
    parser.add_argument("--std-parameterization", choices=("scalar", "log"), default="scalar")
    parser.add_argument("--observation-schema", default="task-env-go2-walk-observation-v1")
    parser.add_argument("--action-schema", default="task-env.go2.position-target.v2")
    args = parser.parse_args()

    import torch
    from task_env.diagnostics.go2.checkpoint_compat import (
        PolicyArchitecture,
        convert_current_to_legacy,
        convert_legacy_to_current,
        load_tensor_checkpoint,
    )

    architecture = PolicyArchitecture(
        observation_dim=args.observation_dim,
        action_dim=args.action_dim,
        actor_hidden_dims=tuple(args.hidden_dims),
        critic_hidden_dims=tuple(args.hidden_dims),
        activation=args.activation,
        std_parameterization=args.std_parameterization,
    )
    payload = load_tensor_checkpoint(args.input)
    if args.direction == "legacy-to-current":
        converted = convert_legacy_to_current(
            payload,
            architecture,
            target_observation_schema=args.observation_schema,
            target_action_schema=args.action_schema,
        )
    else:
        converted = convert_current_to_legacy(
            payload,
            architecture,
            target_observation_schema=args.observation_schema,
            target_action_schema=args.action_schema,
        )
    torch.save(converted, args.output)
    print(f"wrote {args.output} ({converted['source_api']} -> {converted['target_api']})")


if __name__ == "__main__":
    main()
