"""Advanced Phase-I data contracts; production runtime integration is deferred."""
from .contracts import (
    ActionIntent, ActuatorReference, ActuatorResourceDefinition, ArticulationDefinition,
    AssetDefinition, CanonicalStateView, CapabilityAdmissionError, CapabilityClaim,
    ControlGroup, EntityDefinition, EntityInstance,
    ExecutionSpec, FrameDefinition, FrameReference, InitializationContract, JointDefinition, PoseWorld,
    ProviderCapabilityManifest, RequiredCapabilitySet, SemanticDefinition,
    RobotInstance, SceneDefinition, TaskArtifact, Timebase, UniformDimension, WorldDefinition,
    admit_capabilities,
)

__all__ = [
    'ActionIntent', 'ActuatorReference', 'ActuatorResourceDefinition',
    'ArticulationDefinition', 'AssetDefinition', 'CanonicalStateView',
    'CapabilityAdmissionError', 'CapabilityClaim', 'ControlGroup', 'EntityDefinition', 'EntityInstance',
    'ExecutionSpec', 'FrameDefinition', 'FrameReference', 'InitializationContract',
    'JointDefinition', 'PoseWorld',
    'ProviderCapabilityManifest', 'RequiredCapabilitySet', 'SemanticDefinition',
    'RobotInstance', 'SceneDefinition', 'TaskArtifact', 'Timebase', 'UniformDimension', 'WorldDefinition',
    'admit_capabilities',
]
