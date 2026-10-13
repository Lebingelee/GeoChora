"""Typed agent_factory configuration loading for policy-search profiles."""
from pathlib import Path

from omegaconf import OmegaConf

from agent_factory.config.resolution import general_resolve


def load_variant_config(path):
    """Resolve a saved agent config and preserve the Flow observation normalizer."""
    raw = OmegaConf.load(Path(path))
    obs_norm = OmegaConf.select(raw, "actor.obs_norm", default=None)
    if obs_norm is not None:
        OmegaConf.set_struct(raw, False)
        del raw.actor["obs_norm"]
    cfg, _ = general_resolve(file_config=raw)
    if obs_norm is not None:
        OmegaConf.set_struct(cfg, False)
        cfg.actor.obs_norm = obs_norm
    return cfg
