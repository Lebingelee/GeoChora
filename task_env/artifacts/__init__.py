"""Advanced Phase-I data contracts; production runtime integration is deferred."""
from .contracts import (
    ActionIntent, CanonicalStateView, CapabilityAdmissionError, CapabilityClaim,
    EntityDefinition, ExecutionSpec, InitializationContract, PoseWorld,
    ProviderCapabilityManifest, RequiredCapabilitySet, SemanticDefinition,
    TaskArtifact, Timebase, UniformDimension, WorldDefinition, admit_capabilities,
)

__all__ = [
    'ActionIntent', 'CanonicalStateView', 'CapabilityAdmissionError', 'CapabilityClaim',
    'EntityDefinition', 'ExecutionSpec', 'InitializationContract', 'PoseWorld',
    'ProviderCapabilityManifest', 'RequiredCapabilitySet', 'SemanticDefinition',
    'TaskArtifact', 'Timebase', 'UniformDimension', 'WorldDefinition', 'admit_capabilities',
]
