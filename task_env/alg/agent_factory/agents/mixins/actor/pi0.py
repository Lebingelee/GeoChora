import torch

from agent_factory.config.structure import Pi0ActorConfig
from agent_factory.modules.actors.pi0 import Pi0PolicyWrapper, resolve_pi0_normalization_source


class Pi0ActorMixin:
    """
    Mixin for pi0 policy inference and action-head feature extraction.

    Full pi0 training stays in LeRobot for the first pass. This mixin exposes
    the agent_factory runtime surface needed by rollout and feature export.
    """

    CONFIG_CLASS = Pi0ActorConfig
    CONFIG_KEY = "actor"
    RESOLVE_RULES = {
        "action_dim": {
            "source": "env.action_dim",
            "kind": "derived",
            "required": True,
        },
        "pred_horizon": {
            "source": "env.pred_horizon",
            "kind": "derived",
            "required": True,
        },
    }
    REQUIRED_KEYS = {"observations"}

    def _build_actor(self):
        cfg: Pi0ActorConfig = self.cfg.actor
        resolve_pi0_normalization_source(cfg)
        self.actor = Pi0PolicyWrapper(
            cfg=cfg,
            action_dim=getattr(cfg, "action_dim", self.cfg.env.action_dim),
            pred_horizon=getattr(cfg, "pred_horizon", self.cfg.env.pred_horizon),
        )

    def update_actor(self, batch: dict) -> dict:
        del batch
        raise NotImplementedError(
            "pi0 full fine-tuning is intentionally delegated to LeRobotDataset + lerobot-train in phase B. "
            "agent_factory pi0 update_actor() is not implemented in A3."
        )

    def sample_action(self, obs, initial_noise=None, **kwargs):
        del initial_noise
        was_training = self.actor.training
        self.actor.eval()
        try:
            with torch.no_grad():
                return self.actor.sample_action(obs, **kwargs)
        finally:
            if was_training:
                self.actor.train()

    def normalize_action(self, action: torch.Tensor) -> torch.Tensor:
        """pi0 leaves action normalization to LeRobot; this is intentionally an identity."""
        return action

    def denormalize_action(self, action: torch.Tensor) -> torch.Tensor:
        """pi0 wrapper returns env-native actions; this is intentionally an identity."""
        return action

    def extract_action_head_feature(self, obs, **kwargs):
        was_training = self.actor.training
        self.actor.eval()
        try:
            with torch.no_grad():
                return self.actor.extract_action_head_feature(obs, **kwargs)
        finally:
            if was_training:
                self.actor.train()
