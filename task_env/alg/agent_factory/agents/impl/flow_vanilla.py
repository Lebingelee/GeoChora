from dataclasses import dataclass, field
import os

from agent_factory.agents.base_agent import BaseAgent
from agent_factory.agents.mixins.actor.flow_matching import FlowMatchingActorMixin
from agent_factory.agents.registry import register_agent


@dataclass
class AgentSpecialConfig:
    """
    Vanilla flow matching policy config.
    """

    epoch_budget: int = 20
    steps_per_epoch: int = 0
    artifact_identity: dict = field(default_factory=dict)
    iters: int = 100000
    save_dir: str = "run_results"
    exp_name: str = ""


class MainMixin:
    CONFIG_CLASS = AgentSpecialConfig
    CONFIG_KEY = "agent_sp"


@register_agent("Flow_Vanilla")
class FlowVanillaAgent(MainMixin, FlowMatchingActorMixin, BaseAgent):
    """
    Vanilla Flow Matching Policy Agent (pure BC).
    """

    def _init_components(self):
        self._build_actor()

    def _init_optimizers(self):
        pass

    def _resolve_save_dir(self):
        train_cfg = self.cfg.train
        save_root = str(getattr(train_cfg, "save_root", "") or "run_results")
        exp_name = str(getattr(train_cfg, "exp_name", "") or self.cfg.agent_type)
        return os.path.join(save_root, exp_name), exp_name

    def train_loop(self, dataloader, num_steps, save_dir="", validation_loader=None,
                   validation_callback=None):
        from agent_factory.training.flow_metrics import train_loop
        return train_loop(self, dataloader, num_steps, save_dir, validation_loader,
                          validation_callback=validation_callback)

    def save(self, path, meta=None):
        identity = dict(self.cfg.agent_sp.artifact_identity)
        if identity:
            from agent_factory.training.identity import config_identity
            if config_identity(self.cfg) != identity['resolved_config_sha256']:
                raise ValueError('Flow config identity changed before save')
        return super().save(path, meta={**(meta or {}), 'artifact_identity': identity})

    def load(self, path):
        import torch
        from agent_factory.training.identity import config_identity, config_content
        payload = torch.load(path, map_location=self.device, weights_only=False)
        expected = dict(self.cfg.agent_sp.artifact_identity)
        if expected:
            if payload['meta'].get('artifact_identity') != expected:
                raise ValueError('Flow checkpoint artifact identity mismatch')
            if config_identity(payload['config']) != expected['resolved_config_sha256']:
                raise ValueError('Flow checkpoint config content mismatch')
            actual, original = config_content(self.cfg), config_content(payload['config'])
            actual.pop('device', None); original.pop('device', None)
            actual['train'].pop('device', None); original['train'].pop('device', None)
            if actual != original:
                raise ValueError('Flow checkpoint/config compatibility mismatch')
        self.load_state_dict(payload['model'])
        self.step = payload.get('step', 0)
        return payload.get('meta', {})

    def start_train(self, dataset, additional_args=None):
        from torch.utils.data import DataLoader

        cfg = self.cfg
        expert_dataset = dataset["offline"]

        checkpoint_dir, exp_name = self._resolve_save_dir()
        os.makedirs(checkpoint_dir, exist_ok=True)

        if cfg.dataset.dataset_type == 'geochora_canonical_flow':
            if not expert_dataset.training_eligible or dataset.get('validation') is None or not dataset['validation'].training_eligible:
                raise ValueError('full training forbidden: frozen expert dataset has failed episodes')

        self._fit_action_normalizer_from_dataset(expert_dataset)

        loader = DataLoader(
            expert_dataset,
            batch_size=cfg.train.batch_size,
            shuffle=True,
            drop_last=True,
            num_workers=cfg.train.num_workers,
            pin_memory=(cfg.train.num_workers > 0),
        )

        actor_iters = int(getattr(cfg.train, "actor_iters", 0))
        print(f">>> Start Vanilla Flow Matching Policy Training ({actor_iters} steps)")
        validation = dataset.get("validation")
        validation_loader = DataLoader(validation, batch_size=cfg.train.batch_size, shuffle=False,
                                       drop_last=False, num_workers=0) if validation is not None else None
        if cfg.dataset.dataset_type == 'geochora_canonical_flow':
            identity = dict(cfg.agent_sp.artifact_identity)
            if cfg.agent_sp.epoch_budget != 20 or cfg.agent_sp.steps_per_epoch != len(loader) or actor_iters != 20*len(loader):
                raise ValueError('canonical Flow budget must equal20 actual DataLoader epochs')
            if validation is None or expert_dataset.manifest_identity != identity.get('dataset_manifest_sha256'):
                raise ValueError('canonical Flow requires fixed validation and dataset identity')
        self.train_loop(loader, actor_iters, save_dir=checkpoint_dir, validation_loader=validation_loader)

        ckpt_path = os.path.join(checkpoint_dir, f"{exp_name}_final.pth")
        self.save(ckpt_path, meta={"phase": "flow_vanilla_train_done"})
