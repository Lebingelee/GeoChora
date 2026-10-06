"""Logical config identity and Flow artifact compatibility checks."""
import copy
import hashlib
import json
from omegaconf import OmegaConf


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def config_content(cfg):
    value = copy.deepcopy(OmegaConf.to_container(cfg, resolve=True))
    value['agent_sp'].pop('artifact_identity', None)
    return value


def config_identity(cfg):
    return digest(config_content(cfg))
