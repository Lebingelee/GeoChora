"""Lazy compatibility exports; optional algorithms load only on request."""
from importlib import import_module

_EXPORTS = {'DiffusionIQLAgent': '.impl.diffusion_iql', 'DiffusionITQCAgent': '.impl.diffusion_itqc', 'DiffusionVanillaAgent': '.impl.diffusion_vanilla', 'FlowVanillaAgent': '.impl.flow_vanilla', 'DiffusionCPIQLDACAgent': '.impl.diffusion_cpiql_dac', 'CPIQLOnlyAgent': '.impl.cpiql_only', 'CPIQLRatioOnlyAgent': '.impl.cpiql_ratio_only', 'CPIQLRNNAgent': '.impl.cpiql_rnn', 'IQLAdvantageOnlyAgent': '.impl.iql_advantage_only', 'DSRLAgent': '.impl.dsrl', 'IdentityAgent': '.impl.identity', 'TDQCMLPAgent': '.impl.tdqc_mlp', 'TDQCRNNAgent': '.impl.tdqc_rnn', 'Pi0VanillaAgent': '.impl.pi0_vanilla', 'SmolVLAVanillaAgent': '.impl.smolvla_vanilla'}
__all__ = list(_EXPORTS)

def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(_EXPORTS[name], __name__), name)
    globals()[name] = value
    return value
