"""Opt-in bounded provider-neutral lifecycle; no root facade or production rewrite."""
from .api import RuntimeSession, materialize, provider_manifest

__all__ = ['RuntimeSession', 'materialize', 'provider_manifest']

_LEAF_CONTROL_EXPORTS = {
    'LeafActuatorPatchV1', 'LeafActuatorSlotValueV1', 'LeafApplyResultV1',
    'LeafControlIntervalRequestV1', 'LeafControlIntervalResultV1',
    'LeafControlRuntime', 'LeafDispatchProgressV1', 'LeafMaterializationReceiptV1',
    'LeafNativeActuatorMappingV1', 'LeafNativeFrameMappingV1',
    'LeafNativeJointMappingV1', 'LeafNativeTendonMappingV1',
    'LeafPreparedCommandV1', 'LeafRuntimeClockV1',
    'dispatch_leaf_control_interval', 'preflight_leaf_control_interval', 'prepare_leaf_command',
}


def __getattr__(name):
    if name not in _LEAF_CONTROL_EXPORTS:
        raise AttributeError(name)
    from . import leaf_control
    value = getattr(leaf_control, name)
    globals()[name] = value
    return value


__all__ += sorted(_LEAF_CONTROL_EXPORTS)
