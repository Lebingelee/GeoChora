from typing import Any, Optional

from omegaconf import DictConfig

from agent_factory.runner.config_utils import runner_config_get
from agent_factory.runner.sim_runner import SimRunner


class Pi0Runner(SimRunner):
    """
    Thin pi0 rollout runner.

    BaseRunner owns a single trajectory rollout and H5 persistence. SimRunner
    owns simulation success semantics. Pi0Runner only names the pi0 collection
    loop and reads how many trajectories should be collected.
    """

    def __init__(self, cfg: DictConfig, agent: Any, env: Any):
        super().__init__(cfg=cfg, agent=agent, env=env)
        self.num_rollout_trajectories = int(
            runner_config_get(
                cfg,
                "num_rollout_trajectories",
                runner_config_get(cfg, "num_trajectories", 1),
            )
        )

    def collect(self, num_trajectories: Optional[int] = None, sleep_between: float = 0.0):
        import time

        target = int(num_trajectories or self.num_rollout_trajectories)
        if target <= 0:
            raise ValueError(f"Pi0Runner.collect expected a positive trajectory count, got {target}.")

        for traj_idx in range(target):
            print(f"[Pi0Runner] Rollout trajectory {traj_idx + 1}/{target}")
            self.run()
            if sleep_between > 0.0 and traj_idx + 1 < target:
                time.sleep(float(sleep_between))
