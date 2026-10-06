from dataclasses import dataclass

from agent_factory.agents.base_agent import BaseAgent
from agent_factory.agents.mixins.actor.pi0 import Pi0ActorMixin
from agent_factory.agents.registry import register_agent


@dataclass
class Pi0AgentSpecialConfig:
    save_dir: str = "run_results"
    exp_name: str = "pi0"


class MainMixin:
    CONFIG_CLASS = Pi0AgentSpecialConfig
    CONFIG_KEY = "agent_sp"


@register_agent("pi0")
class Pi0VanillaAgent(MainMixin, Pi0ActorMixin, BaseAgent):
    """
    pi0 policy wrapper agent.

    Training is expected to happen through LeRobot. This agent exists so
    agent_factory can load pi0 checkpoints for rollout and feature extraction.
    """

    def _init_components(self):
        self._build_actor()

    def _init_optimizers(self):
        pass

    def start_train(self, dataset, additional_args=None):
        del dataset, additional_args
        raise NotImplementedError(
            "pi0 training is not implemented inside agent_factory in A3. "
            "Use H5 -> LeRobotDataset conversion followed by lerobot-train --policy.type=pi0."
        )
