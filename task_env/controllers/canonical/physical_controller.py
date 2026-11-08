"""Pure, configurable named-effort Controller using the public model boundary."""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from ...artifacts.contracts import Contract, FrameReference, _choice, _name
from .contracts import digest
from .model import ControllerModelRequirementV1, ModelOutputV1
from .physical_commands import (
    ContributionPolicyV1, JointEffortV1, PhysicalCommandBatchV1,
    PhysicalCommandContextV1, PhysicalControlBindingV1,
)


@dataclass(frozen=True)
class LinearEffortProfileV1(Contract):
    """Explicit action-to-effort coefficients; no Robot dimension is assumed."""
    schema_version: str
    controller_id: str
    action_names: tuple[str, ...]
    channel_keys: tuple[str, ...]
    action_to_effort: tuple[tuple[float, ...], ...]
    model_requirement: ControllerModelRequirementV1
    composition: str = 'exclusive'

    def validate(self):
        _choice(self.schema_version, {'linear-effort-profile-v1'}, 'effort profile schema')
        _name(self.controller_id)
        if not self.action_names or len(set(self.action_names)) != len(self.action_names):
            raise ValueError('profile needs unique named actions')
        for value in (*self.action_names, *self.channel_keys):
            _name(value)
        if not self.channel_keys or len(set(self.channel_keys)) != len(self.channel_keys):
            raise ValueError('profile needs unique ordered channels')
        if len(self.action_to_effort) != len(self.channel_keys) or any(
                len(row) != len(self.action_names) for row in self.action_to_effort):
            raise ValueError('action-to-effort matrix shape differs from profile')
        if self.model_requirement.joint_names != self.channel_keys:
            raise ValueError('model joint order differs from Controller output order')
        if self.model_requirement.requiredness != 'required':
            raise ValueError('linear effort Controller requires its model output')
        _choice(self.composition, {'exclusive', 'sum'}, 'composition')

    @property
    def identity_hash(self):
        return digest(self.to_mapping())


class LinearEffortControllerV1:
    """Compute named contributions using an injected, source-bound pure model."""

    def __init__(self, profile: LinearEffortProfileV1, binding: PhysicalControlBindingV1, model):
        if type(profile) is not LinearEffortProfileV1 or type(binding) is not PhysicalControlBindingV1:
            raise TypeError('effort Controller requires typed profile and binding')
        if getattr(model, 'requirement', None) != profile.model_requirement or not callable(getattr(model, 'evaluate', None)):
            raise ValueError('model does not satisfy the exact Controller requirement')
        if (profile.model_requirement.source_id, profile.model_requirement.source_closure_sha256) != (
                binding.source_id, binding.source_closure_sha256):
            raise ValueError('model and Controller binding source differ')
        channels = {f'{x.entity_id}/{x.joint_id}': x for x in binding.channels}
        if not set(profile.channel_keys) <= set(channels) or any(
                profile.controller_id not in channels[key].owner_ids for key in profile.channel_keys):
            raise ValueError('Controller channels differ from its binding')
        if tuple(channels[key].unit for key in profile.channel_keys) != profile.model_requirement.output_units:
            raise ValueError('model output units differ from effort channels')
        self.profile, self.binding, self.model = profile, binding, model
        self.writer_id = profile.controller_id
        self._channels = tuple(channels[key] for key in profile.channel_keys)
        self.identity = digest({'profile': profile.identity_hash, 'binding': binding.identity_hash,
                                'model': model.identity_hash})

    @property
    def action_shape(self):
        return (len(self.profile.action_names),)

    def compute(self, action, state, context: PhysicalCommandContextV1):
        if type(context) is not PhysicalCommandContextV1:
            raise TypeError('Controller requires a typed interval context')
        if isinstance(action, (tuple, list)) and any(isinstance(x, (bool, np.bool_)) for x in action):
            raise ValueError('Controller action shape or finite values are invalid')
        raw = np.asarray(action)
        if (raw.shape != (len(self.profile.action_names),)
                or raw.dtype.kind not in {'i', 'u', 'f'} or not np.isfinite(raw).all()):
            raise ValueError('Controller action shape or finite values are invalid')
        values = tuple(float(x) for x in raw)
        if (context.source_id, context.source_closure_sha256, context.artifact_sha256) != (
                self.binding.source_id, self.binding.source_closure_sha256, self.binding.artifact_sha256):
            raise ValueError('Controller context source differs from binding')
        if state.boundary != context.boundary or state.sample_clock != context.clock:
            raise ValueError('Controller state is stale or foreign')
        requirement = self.profile.model_requirement
        if not math.isclose(context.cadence_s, requirement.cadence_s, rel_tol=0, abs_tol=1e-12):
            raise ValueError('Controller interval differs from model cadence')
        # This Controller evaluates its model at every exact state boundary;
        # it does not cache model output across boundaries.
        output = self.model.evaluate(state)
        if (type(output) is not ModelOutputV1 or output.requirement_sha256 != requirement.identity_hash
                or output.model_sha256 != self.model.identity_hash
                or output.source_closure_sha256 != context.source_closure_sha256
                or output.boundary != context.boundary or output.clock != context.clock
                or output.joint_names != requirement.joint_names or output.units != requirement.output_units
                or output.frame != requirement.output_frame):
            raise ValueError('required model output identity, units, or boundary differs')
        efforts = []
        for index, channel in enumerate(self._channels):
            value = sum(c*x for c, x in zip(self.profile.action_to_effort[index], values, strict=True)) + output.values[index]
            policy = ContributionPolicyV1('physical-contribution-policy-v1',
                f'{self.profile.controller_id}/channel-{index}', f'{self.profile.controller_id}/effect-{index}',
                self.profile.controller_id, self.profile.composition, 'reject_outside', 'one_interval')
            efforts.append(JointEffortV1('joint-effort-v1', context, policy, channel.entity_id,
                channel.joint_id, channel.dof_id, channel.kind, channel.axis, channel.axis_frame,
                channel.sign, channel.unit, value, channel.effort_range, 'other_declared'))
        return PhysicalCommandBatchV1('physical-command-batch-v1', context, tuple(efforts), (), ())


@dataclass(frozen=True)
class WrenchControlProfileV1(Contract):
    """Typed direct force/torque input at an explicitly declared body and frames."""
    schema_version: str
    controller_id: str
    entity_id: str
    body_id: str
    expression_frame: FrameReference
    point: tuple[float, float, float]
    point_frame: FrameReference
    moment_reference: tuple[float, float, float]
    moment_reference_frame: FrameReference
    composition: str

    def validate(self):
        from ...artifacts.contracts import FrameReference
        _choice(self.schema_version, {'wrench-control-profile-v1'}, 'wrench profile schema')
        for value in (self.controller_id, self.entity_id, self.body_id):
            _name(value)
        for frame in (self.expression_frame, self.point_frame, self.moment_reference_frame):
            if type(frame) is not FrameReference:
                raise TypeError('wrench Controller requires explicit typed frames')
        _choice(self.composition, {'exclusive', 'sum'}, 'composition')


class WrenchControllerV1:
    """Pure direct wrench input; no live provider handle or physics operation."""
    def __init__(self, profile, binding):
        if type(profile) is not WrenchControlProfileV1 or type(binding) is not PhysicalControlBindingV1:
            raise TypeError('wrench Controller requires typed profile and binding')
        if (profile.entity_id, profile.body_id, profile.controller_id) not in {
                (x.entity_id, x.body_id, owner) for x in binding.bodies for owner in x.owner_ids}:
            raise ValueError('wrench Controller body is absent from binding')
        self.profile, self.binding = profile, binding
        self.writer_id = profile.controller_id
        self.identity = digest({'profile': profile.to_mapping(), 'binding': binding.identity_hash})

    @property
    def action_shape(self):
        return (6,)

    def compute(self, action, state, context):
        from .physical_commands import BodyWrenchV1
        if isinstance(action, (tuple, list)) and any(isinstance(x, (bool, np.bool_)) for x in action):
            raise ValueError('wrench action must contain six finite real values')
        values = np.asarray(action)
        if values.shape != (6,) or values.dtype.kind not in {'i','u','f'} or not np.isfinite(values).all():
            raise ValueError('wrench action must contain six finite real values')
        if state.boundary != context.boundary or state.sample_clock != context.clock:
            raise ValueError('wrench Controller state is stale or foreign')
        if (context.source_id, context.source_closure_sha256, context.artifact_sha256) != (
                self.binding.source_id, self.binding.source_closure_sha256, self.binding.artifact_sha256):
            raise ValueError('wrench Controller context differs from source binding')
        policy = ContributionPolicyV1('physical-contribution-policy-v1',
            f'{self.profile.controller_id}/wrench', f'{self.profile.controller_id}/effect',
            self.profile.controller_id, self.profile.composition, 'reject_outside', 'one_interval')
        wrench = BodyWrenchV1('body-wrench-v1',context,policy,self.profile.entity_id,self.profile.body_id,
            self.profile.expression_frame,self.profile.point,self.profile.point_frame,
            self.profile.moment_reference,self.profile.moment_reference_frame,
            tuple(float(x) for x in values[:3]),tuple(float(x) for x in values[3:]))
        return PhysicalCommandBatchV1('physical-command-batch-v1',context,(),(wrench,),())

class DirectJointEffortControllerV1:
    """Bounded named torque inputs mapped one-to-one to declared physical channels.

    The action tree and channel order are caller declarations, independent of
    any task or provider.  All output remains subject to the normal compiled
    physical-binding and session admission checks.
    """

    def __init__(self, binding, *, controller_id, channel_keys, action_key='torque'):
        from gymnasium.spaces import Box, Dict
        if type(binding) is not PhysicalControlBindingV1:
            raise TypeError('direct effort requires a typed physical binding')
        _name(controller_id)
        _name(action_key)
        keys = tuple(channel_keys)
        if not keys or len(set(keys)) != len(keys):
            raise ValueError('direct effort requires unique ordered channel keys')
        channels = {f'{c.entity_id}/{c.joint_id}': c for c in binding.channels}
        if any(key not in channels or controller_id not in channels[key].owner_ids for key in keys):
            raise ValueError('direct effort channels differ from their declared writer')
        self.binding, self.writer_id = binding, controller_id
        self._channels = tuple(channels[key] for key in keys)
        self._action_key = action_key
        self.identity = digest({'schema_version': 'direct-joint-effort-controller-v1',
            'binding': binding.identity_hash, 'controller_id': controller_id,
            'channels': keys, 'action_key': action_key})
        low = np.asarray([c.effort_range[0] for c in self._channels], dtype=np.float32)
        high = np.asarray([c.effort_range[1] for c in self._channels], dtype=np.float32)
        self.action_space = Dict({action_key: Box(low=low, high=high, dtype=np.float32)})
        self._episode_id = None
        self.last_action = None

    def compatibility_feedback(self, resolved, ack, *, mode, include_diagnostics):
        """Project a validated unit-transmission command, not a force measurement."""
        if (self.last_action is None or resolved.input_batch.identity_hash != ack.batch_sha256
                or ack.stage != 'native_write_ack' or ack.context != resolved.input_batch.context
                or ack.contribution_ids != resolved.accepted_receipt.contribution_ids):
            raise ValueError('direct effort feedback requires the matching accepted native write')
        channels = self._channels
        if (len(resolved.joints) != len(channels) or resolved.body_wrenches or resolved.extensions
                or any(c.sign != 1 or c.transmission_coefficient != 1.0 or c.native_drive != 'disabled'
                       or c.unit != 'N*m' for c in channels)):
            raise ValueError('direct effort compatibility requires isolated unit-gear torque channels')
        resolved_by_key = {(x.entity_id, x.joint_id, x.dof_id): x for x in resolved.joints}
        values = []
        for channel, requested in zip(channels, self.last_action, strict=True):
            item = resolved_by_key.get(channel.target_key)
            if (item is None or item.unit != channel.unit or item.clipped_before_sum or item.clipped_after_sum
                    or len(item.contribution_ids) != 1 or float(item.value) != float(requested)):
                raise ValueError('admitted effort does not match the declared direct command')
            values.append(item.value)
        value = np.asarray(values, dtype=np.float32)
        action = {name: value.copy() for name in
                  ('requested', 'external', 'controller_target', 'requested_ctrl', 'applied_ctrl', 'universal_action')}
        action['mode'] = mode
        feedback = {'action': action, **{name: value.copy() for name in
                    ('requested_action', 'external_action', 'controller_target', 'requested_ctrl', 'applied_ctrl', 'universal_action')},
                    'control_application': 'generalized-effort command; source motor isolated; not a force measurement'}
        if include_diagnostics:
            action.update(clipped=False, action_clipped=False, ctrl_clipped=False)
            feedback.update(action_clipped=False, ctrl_clipped=False)
        return feedback

    def reset_from_realized_state(self, state):
        if state.boundary.scene_identity_hash != self.binding.scene_sha256:
            raise ValueError('direct effort reset state differs from bound Scene')
        self._episode_id = state.boundary.episode_id
        self.last_action = np.zeros(len(self._channels), dtype=np.float32)

    def compute(self, action, state, context):
        from collections.abc import Mapping
        if type(context) is not PhysicalCommandContextV1:
            raise TypeError('direct effort requires a typed interval context')
        if isinstance(action, Mapping):
            if set(action) != {self._action_key}:
                raise ValueError('direct effort action tree differs from its declaration')
            action = action[self._action_key]
        raw = np.asarray(action)
        if (raw.shape != (len(self._channels),) or raw.dtype.kind not in {'i', 'u', 'f'}
                or not np.isfinite(raw).all()):
            raise ValueError('direct effort action shape or finite values are invalid')
        values = np.asarray(raw, dtype=np.float32)
        if not self.action_space.spaces[self._action_key].contains(values):
            raise ValueError('direct effort action exceeds its declared bounds')
        if (context.source_id, context.source_closure_sha256, context.artifact_sha256) != (
                self.binding.source_id, self.binding.source_closure_sha256, self.binding.artifact_sha256):
            raise ValueError('direct effort context source differs from binding')
        if state.boundary != context.boundary or state.sample_clock != context.clock:
            raise ValueError('direct effort state is stale or foreign')
        if self._episode_id is None or context.boundary.episode_id != self._episode_id:
            raise ValueError('direct effort must be reset for the current episode')
        efforts = []
        for index, (channel, value) in enumerate(zip(self._channels, values, strict=True)):
            policy = ContributionPolicyV1('physical-contribution-policy-v1',
                f'{self.writer_id}/channel-{index}', f'{self.writer_id}/effect-{index}',
                self.writer_id, 'exclusive', 'reject_outside', 'one_interval')
            efforts.append(JointEffortV1('joint-effort-v1', context, policy,
                channel.entity_id, channel.joint_id, channel.dof_id, channel.kind,
                channel.axis, channel.axis_frame, channel.sign, channel.unit,
                float(value), channel.effort_range, 'other_declared'))
        result = PhysicalCommandBatchV1('physical-command-batch-v1', context, tuple(efforts), (), ())
        self.last_action = values.copy()
        return result
