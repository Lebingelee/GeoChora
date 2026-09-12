"""Private extras shared by the supported TaskEnv RSL-RL rollout path.

The reset-selection optimization is deliberately narrower than the public
VecEnv extras contract.  It is valid only for the immediate sequence

``TaskEnvRslVecAdapter -> installed RSL-RL 5.x PPO.process_env_step -> Logger``.

The installed PPO method is regression-tested under ``torch.inference_mode``
to preserve the exact dones tensor, storage pointer, and contents before the
logger consumes this evidence.  An intermediary that cannot provide the same
read-only guarantee is outside this private contract and must remove both
keys, which selects the logger's generic terminal-selection fallback.
"""

from __future__ import annotations


DEVICE_RESET_SELECTION_EXTRAS_KEY = "_task_env_device_reset_selection"
DEVICE_RESET_SELECTION_CONTRACT_KEY = (
    "_task_env_device_reset_selection_contract"
)
DEVICE_RESET_SELECTION_CONTRACT_VALUE = (
    "task_env.adapter-rsl_ppo5-logger.v1"
)


__all__: list[str] = []
