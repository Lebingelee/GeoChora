"""Provider-neutral joint-reference effort servo over the canonical model seam."""
from dataclasses import dataclass, replace
import math

from ...artifacts.contracts import Contract, _choice, _name
from .contracts import digest
from .model import AffineJointBiasModelV1, ControllerModelRequirementV1
from .physical_controller import LinearEffortControllerV1, LinearEffortProfileV1


@dataclass(frozen=True)
class JointReferenceEffortProfileV1(Contract):
    """Explicit mapping from named reference inputs to joint position references."""
    schema_version: str
    controller_id: str
    action_names: tuple[str, ...]
    channel_keys: tuple[str, ...]
    reference_to_joint: tuple[tuple[float, ...], ...]
    kp: tuple[float, ...]
    kd: tuple[float, ...]
    model_requirement: ControllerModelRequirementV1
    composition: str = 'exclusive'

    def validate(self):
        _choice(self.schema_version, {'joint-reference-effort-profile-v1'}, 'effort servo profile schema')
        _name(self.controller_id)
        if not self.action_names or len(set(self.action_names)) != len(self.action_names):
            raise ValueError('effort servo needs unique named reference inputs')
        if not self.channel_keys or len(set(self.channel_keys)) != len(self.channel_keys):
            raise ValueError('effort servo needs unique named output channels')
        for name in (*self.action_names, *self.channel_keys):
            _name(name)
        n = len(self.channel_keys)
        if (len(self.reference_to_joint) != n or len(self.kp) != n or len(self.kd) != n
                or any(len(row) != len(self.action_names) for row in self.reference_to_joint)):
            raise ValueError('effort servo reference matrix or gain dimensions differ')
        if (any(not math.isfinite(value) for row in self.reference_to_joint for value in row)
                or any(not math.isfinite(value) or value < 0 for value in (*self.kp, *self.kd))):
            raise ValueError('effort servo mapping and gains must be finite and gains nonnegative')
        if self.model_requirement.joint_names != self.channel_keys:
            raise ValueError('effort servo and model joint order differ')
        _choice(self.composition, {'exclusive', 'sum'}, 'composition')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


class JointReferenceEffortControllerV1:
    """Compute full PD plus declared affine feedforward from a named state.

    The existing physical admission rejects this explicit full PD when an
    uncoordinated native position drive is active.  No provider is accessed.
    """
    def __init__(self, profile, binding, model):
        if type(profile) is not JointReferenceEffortProfileV1 or type(model) is not AffineJointBiasModelV1:
            raise TypeError('effort servo requires its exact typed profile and affine model')
        if (model.requirement != profile.model_requirement
                or model.position_coefficients != tuple(-x for x in profile.kp)
                or model.velocity_coefficients != tuple(-x for x in profile.kd)):
            raise ValueError('effort servo model must encode the declared negative PD gains')
        matrix = tuple(tuple(profile.kp[i] * coefficient for coefficient in row)
                       for i, row in enumerate(profile.reference_to_joint))
        linear = LinearEffortProfileV1('linear-effort-profile-v1', profile.controller_id,
            profile.action_names, profile.channel_keys, matrix, profile.model_requirement, profile.composition)
        self._linear = LinearEffortControllerV1(linear, binding, model)
        self.profile = profile
        self.binding = binding
        self.writer_id = profile.controller_id
        self.identity = digest({'profile': profile.identity_hash, 'linear': self._linear.identity,
                                'controller_law': 'explicit_full_pd'})

    @property
    def action_shape(self):
        return self._linear.action_shape

    def compute(self, action, state, context):
        batch = self._linear.compute(action, state, context)
        return replace(batch, joint_efforts=tuple(replace(item, controller_law='explicit_full_pd')
                                                   for item in batch.joint_efforts))
