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
    action_key: str | None = None
    action_low: tuple[float, ...] = ()
    action_high: tuple[float, ...] = ()
    selection_profile_id: str | None = None

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
        if self.action_key is None:
            if self.action_low or self.action_high:
                raise ValueError('bounded action values require an explicit action key')
        else:
            _name(self.action_key)
            if (len(self.action_low) != len(self.action_names)
                    or len(self.action_high) != len(self.action_names)
                    or any(not math.isfinite(value) for value in (*self.action_low, *self.action_high))
                    or any(low > high for low, high in zip(self.action_low, self.action_high, strict=True))):
                raise ValueError('linear effort action bounds must cover its ordered inputs')
        if self.selection_profile_id is not None:
            _name(self.selection_profile_id)

    @property
    def identity_hash(self):
        payload = self.to_mapping()
        # Preserve accepted identities for existing profiles that do not use
        # the additive public action-tree and selection metadata.
        for name, value in (('action_key', self.action_key), ('action_low', self.action_low),
                            ('action_high', self.action_high),
                            ('selection_profile_id', self.selection_profile_id)):
            if value is None or value == ():
                payload.pop(name, None)
        return digest(payload)


class LinearEffortControllerV1:
    """Compute named contributions using an injected, source-bound pure model."""

    @classmethod
    def zero_bias(cls, binding, *, writer_id, channel_keys, action_names,
                  action_to_effort, cadence_s, model_id, selection_profile_id=None):
        """Construct a source-bound linear Controller for declared channels."""
        from .model import AffineJointBiasModelV1

        if type(binding) is not PhysicalControlBindingV1:
            raise TypeError('zero-bias Controller requires a typed physical binding')
        by_key = {f'{channel.entity_id}/{channel.joint_id}': channel for channel in binding.channels}
        if (not channel_keys or len(set(channel_keys)) != len(channel_keys)
                or any(key not in by_key or writer_id not in by_key[key].owner_ids for key in channel_keys)):
            raise ValueError('zero-bias Controller channels differ from its writer binding')
        channels = tuple(by_key[key] for key in channel_keys)
        requirement = ControllerModelRequirementV1(
            'controller-model-requirement-v1', model_id, 'geochora', 'v1', 'stdlib',
            binding.source_id, binding.source_closure_sha256, tuple(channel_keys),
            tuple('rad' if channel.kind == 'revolute' else 'm' for channel in channels),
            'joint_bias', tuple(channel.unit for channel in channels), 'joint-axis',
            'evaluation_boundary', cadence_s, 0., 'pure_no_physics_step', writer_id, 'none', 'required')
        zero = (0.,) * len(channels)
        model = AffineJointBiasModelV1('affine-joint-bias-model-v1', requirement, zero, zero, zero)
        profile = LinearEffortProfileV1('linear-effort-profile-v1', writer_id,
            tuple(action_names), tuple(channel_keys), tuple(action_to_effort), requirement,
            selection_profile_id=selection_profile_id)
        return cls(profile, binding, model)

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
        input_units = tuple('rad' if channels[key].kind == 'revolute' else 'm'
                            for key in profile.channel_keys)
        if input_units != profile.model_requirement.joint_units:
            raise ValueError('model input units differ from bound joint kinds')
        self.profile, self.binding, self.model = profile, binding, model
        self.writer_id = profile.controller_id
        self.profile_id = profile.selection_profile_id or profile.model_requirement.profile_id
        self._channels = tuple(channels[key] for key in profile.channel_keys)
        self._device_binding_hash = binding.identity_hash
        self.identity = digest({'profile': profile.identity_hash, 'binding': binding.identity_hash,
                                'model': model.identity_hash})
        self._episode_id = None
        self.last_action = None
        self.action_space = None
        self._device_constants = {}
        if profile.action_key is not None:
            from gymnasium.spaces import Box, Dict
            self.action_space = Dict({profile.action_key: Box(
                low=np.asarray(profile.action_low, dtype=np.float32),
                high=np.asarray(profile.action_high, dtype=np.float32), dtype=np.float32)})

    @property
    def action_shape(self):
        return (len(self.profile.action_names),)

    @property
    def channel_keys(self):
        """Ordered physical targets produced by this Controller."""
        return tuple(channel.target_key for channel in self._channels)

    def device_action_space(self):
        """Describe the bounded named inputs for an isolated device batch.

        A rectangular input space is only derived when every output depends on
        one input. General coupled linear maps need an explicit admissible set.
        """
        from gymnasium.spaces import Box, Dict
        from .model import AffineJointBiasModelV1

        model = self.model
        if (type(model) is not AffineJointBiasModelV1 or any(model.offsets)
                or any(model.position_coefficients) or any(model.velocity_coefficients)):
            raise ValueError('device linear effort requires the declared zero-bias model')
        low = np.full(self.action_shape, -np.inf, dtype=np.float64)
        high = np.full(self.action_shape, np.inf, dtype=np.float64)
        for channel, row in zip(self._channels, self.profile.action_to_effort, strict=True):
            nonzero = [(index, coefficient) for index, coefficient in enumerate(row) if coefficient != 0]
            if len(nonzero) != 1:
                raise ValueError('device linear effort requires separable input bounds')
            index, coefficient = nonzero[0]
            first, second = (value / coefficient for value in channel.effort_range)
            low[index] = max(low[index], min(first, second))
            high[index] = min(high[index], max(first, second))
        if self.profile.action_key is not None:
            low = np.maximum(low, self.profile.action_low)
            high = np.minimum(high, self.profile.action_high)
        if not np.isfinite(low).all() or not np.isfinite(high).all() or np.any(low > high):
            raise ValueError('device linear effort cannot derive finite action bounds')
        return Dict({self.profile.action_key or 'effort': Box(
            low=low.astype(np.float32), high=high.astype(np.float32), dtype=np.float32)})

    def convert_device_batch(self, action, state):
        """Apply the source-bound linear effort map on CUDA for every row."""
        from collections.abc import Mapping
        import torch
        from .physical_commands import DeviceJointEffortCommand
        from ...runtime.contracts import DeviceBatchState

        if not isinstance(state, DeviceBatchState) or state.identity is None:
            raise TypeError('device linear effort requires an identified state publication')
        if state.episode_ids is None or state.episode_steps is None:
            raise ValueError('device linear effort requires per-row episode identity and clocks')
        boundary = state.identity
        if (boundary.source_id, boundary.source_closure_sha256, boundary.artifact_sha256) != (
                self.binding.source_id, self.binding.source_closure_sha256, self.binding.artifact_sha256):
            raise ValueError('device linear effort state differs from Controller source binding')
        key = self.profile.action_key or 'effort'
        if not isinstance(action, Mapping) or set(action) != {key}:
            raise ValueError('device linear effort action tree differs from its declaration')
        values = action[key]
        if (not isinstance(values, torch.Tensor) or str(values.device) != state.device
                or values.device.type != 'cuda' or values.dtype != torch.float32
                or tuple(values.shape) != (state.num_envs, *self.action_shape)):
            raise ValueError('device linear effort requires CUDA float32 values with shape (B, inputs)')
        if values.device not in self._device_constants:
            space = self.device_action_space().spaces[key]
            self._device_constants[values.device] = (
                torch.as_tensor(space.low, device=values.device),
                torch.as_tensor(space.high, device=values.device),
                torch.tensor(self.profile.action_to_effort, dtype=values.dtype, device=values.device))
        low, high, matrix = self._device_constants[values.device]
        if not bool(torch.isfinite(values).all()) or bool(((values < low) | (values > high)).any()):
            raise ValueError('device linear effort is nonfinite or exceeds its declared bounds')
        efforts = (values @ matrix.T).contiguous()
        return DeviceJointEffortCommand(boundary, self._device_binding_hash, self.writer_id,
            tuple(channel.target_key for channel in self._channels), efforts,
            state.episode_ids.clone(), state.episode_steps.clone())

    def close_device(self):
        """Release the Controller-owned device constants."""
        self._device_constants.clear()

    def reset_from_realized_state(self, state):
        if state.boundary.scene_identity_hash != self.binding.scene_sha256:
            raise ValueError('linear effort reset state differs from bound Scene')
        self._episode_id = state.boundary.episode_id
        self.last_action = np.zeros(len(self.profile.action_names), dtype=np.float32)

    def compute(self, action, state, context: PhysicalCommandContextV1):
        from collections.abc import Mapping
        if type(context) is not PhysicalCommandContextV1:
            raise TypeError('Controller requires a typed interval context')
        if isinstance(action, Mapping):
            if self.profile.action_key is None or set(action) != {self.profile.action_key}:
                raise ValueError('linear effort action tree differs from its declaration')
            action = action[self.profile.action_key]
        if isinstance(action, (tuple, list)) and any(isinstance(x, (bool, np.bool_)) for x in action):
            raise ValueError('Controller action shape or finite values are invalid')
        raw = np.asarray(action)
        if (raw.shape != (len(self.profile.action_names),)
                or raw.dtype.kind not in {'i', 'u', 'f'} or not np.isfinite(raw).all()):
            raise ValueError('Controller action shape or finite values are invalid')
        values = tuple(float(x) for x in raw)
        if self.profile.action_key is not None and any(
                not low <= value <= high for value, low, high in zip(
                    values, self.profile.action_low, self.profile.action_high, strict=True)):
            raise ValueError('linear effort action exceeds its declared bounds')
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
        self.last_action = np.asarray(values, dtype=np.float32).copy()
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

    profile_id = 'direct_joint_effort_v1'

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
        self._binding_hash = binding.identity_hash
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
        self._device_limits = {}

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

    @property
    def channel_keys(self):
        """Ordered physical targets consumed by this Controller."""
        return tuple(channel.target_key for channel in self._channels)

    def reset_from_realized_state(self, state):
        if state.boundary.scene_identity_hash != self.binding.scene_sha256:
            raise ValueError('direct effort reset state differs from bound Scene')
        self._episode_id = state.boundary.episode_id
        self.last_action = np.zeros(len(self._channels), dtype=np.float32)

    def convert_device_batch(self, action, state):
        """Consume one named device action at the published state boundary."""
        from collections.abc import Mapping
        import torch
        from .physical_commands import DeviceJointEffortCommand
        from ...runtime.contracts import DeviceBatchState

        if not isinstance(state, DeviceBatchState) or state.identity is None:
            raise TypeError('direct device effort requires an identified state publication')
        if state.episode_ids is None or state.episode_steps is None:
            raise ValueError('direct device effort requires per-row episode identity and clocks')
        boundary = state.identity
        if (boundary.source_id, boundary.source_closure_sha256, boundary.artifact_sha256) != (
                self.binding.source_id, self.binding.source_closure_sha256, self.binding.artifact_sha256):
            raise ValueError('device effort state differs from Controller source binding')
        if not isinstance(action, Mapping) or set(action) != {self._action_key}:
            raise ValueError('direct effort action tree differs from its declaration')
        values = action[self._action_key]
        if (not isinstance(values, torch.Tensor) or str(values.device) != state.device
                or values.dtype != torch.float32 or tuple(values.shape) != (state.num_envs, len(self._channels))):
            raise ValueError('direct device effort requires CUDA float32 values with shape (B, channels)')
        if values.device.type != 'cuda' or not bool(torch.isfinite(values).all()):
            raise ValueError('direct device effort must be finite and CUDA-resident')
        if values.device not in self._device_limits:
            self._device_limits[values.device] = (
                torch.tensor([c.effort_range[0] for c in self._channels], device=values.device),
                torch.tensor([c.effort_range[1] for c in self._channels], device=values.device))
        low, high = self._device_limits[values.device]
        if bool(((values < low) | (values > high)).any()):
            raise ValueError('direct device effort exceeds its declared bounds')
        return DeviceJointEffortCommand(boundary, self._binding_hash, self.writer_id,
                                        tuple(channel.target_key for channel in self._channels),
                                        values.contiguous(), state.episode_ids.clone(), state.episode_steps.clone())

    def close_device(self):
        """Release Controller-owned device constants after the batch closes."""
        self._device_limits.clear()

    def validate_action(self, action):
        from collections.abc import Mapping
        if isinstance(action, Mapping):
            if set(action) != {self._action_key}:
                raise ValueError('direct effort action tree differs from its declaration')
            action = action[self._action_key]
        if isinstance(action, (tuple, list)) and any(isinstance(value, (bool, np.bool_)) for value in action):
            raise ValueError('direct effort action shape or finite values are invalid')
        raw = np.asarray(action)
        if (raw.shape != (len(self._channels),) or raw.dtype.kind not in {'i', 'u', 'f'}
                or not np.isfinite(raw).all()):
            raise ValueError('direct effort action shape or finite values are invalid')
        # Compare the caller's original precision before converting to the
        # public float32 action space; rounding must not admit an out-of-range
        # value such as 2.0 + 1e-9 on a channel limited to 2 N*m.
        if any(not channel.effort_range[0] <= value <= channel.effort_range[1]
               for channel, value in zip(self._channels, raw, strict=True)):
            raise ValueError('direct effort action exceeds its declared bounds')
        values = np.asarray(raw, dtype=np.float32)
        if not self.action_space.spaces[self._action_key].contains(values):
            raise ValueError('direct effort action exceeds its declared bounds')
        return values

    def compute(self, action, state, context):
        if type(context) is not PhysicalCommandContextV1:
            raise TypeError('direct effort requires a typed interval context')
        values = self.validate_action(action)
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


def _subject_effort_channels(subject, binding, *, writer_id, units):
    """Resolve exactly the subject's source-bound ordered writable channels."""
    from ...runtime.sessions.physical_control import ControlledSubjectV1

    if type(subject) is not ControlledSubjectV1 or type(binding) is not PhysicalControlBindingV1:
        raise TypeError('effort Controller requires a typed subject and physical binding')
    if (binding.source_id, binding.source_closure_sha256) != (subject.source_id, subject.source_closure_sha256):
        raise ValueError('Controller binding differs from subject source')
    if writer_id not in subject.controller_writers:
        raise ValueError('Controller writer is not declared by subject')
    if type(units) is not tuple or len(units) != len(subject.channel_paths):
        raise ValueError('Controller requires one explicit unit per subject channel')
    channels = []
    for path, unit in zip(subject.channel_paths, units, strict=True):
        matches = tuple(channel for channel in binding.channels
                        if channel.entity_id == subject.entity_id and channel.component_path == path)
        if len(matches) != 1:
            raise ValueError('Controller channel is missing or ambiguous')
        channel = matches[0]
        if writer_id not in channel.owner_ids or channel.unit != unit:
            raise ValueError('Controller channel writer or unit differs from declaration')
        channels.append(channel)
    return tuple(channels)


def bind_subject_direct_effort_controller(subject, binding, *, writer_id, units, action_key='torque'):
    """Bind the default direct effort Controller to a subject's declared channels."""
    channels = _subject_effort_channels(subject, binding, writer_id=writer_id, units=units)
    keys = tuple(f'{channel.entity_id}/{channel.joint_id}' for channel in channels)
    return DirectJointEffortControllerV1(binding, controller_id=writer_id,
                                          channel_keys=keys, action_key=action_key)


def select_subject_effort_controller(subject, binding, *, profile_id, writer_id, units,
                                     cadence_s, action_key='torque'):
    """Construct the selected source-bound effort Controller for a declared subject."""
    from ...runtime.sessions.physical_control import ControlledSubjectV1
    from .model import AffineJointBiasModelV1

    if type(subject) is not ControlledSubjectV1:
        raise TypeError('effort Controller selection requires a typed subject')
    if profile_id not in subject.supported_controller_profiles:
        raise ValueError('selected Controller profile is not declared by the subject')
    if profile_id == 'direct_joint_effort_v1':
        controller = bind_subject_direct_effort_controller(
            subject, binding, writer_id=writer_id, units=units, action_key=action_key)
        controller.profile_id = profile_id
        return controller
    if profile_id != 'velocity_damped_joint_effort_v1':
        raise ValueError('subject does not implement the selected Controller profile')
    channels = _subject_effort_channels(subject, binding, writer_id=writer_id, units=units)
    keys = tuple(f'{channel.entity_id}/{channel.joint_id}' for channel in channels)
    if any(channel.kind != 'revolute' or channel.unit != 'N*m' for channel in channels):
        raise ValueError('velocity-damped effort currently requires revolute torque channels')
    if not math.isfinite(float(cadence_s)) or float(cadence_s) <= 0:
        raise ValueError('velocity-damped effort requires a positive finite cadence')
    requirement = ControllerModelRequirementV1(
        'controller-model-requirement-v1', f'{subject.subject_id}-velocity-damped-effort-v1',
        'geochora', 'v1', 'stdlib', binding.source_id, binding.source_closure_sha256,
        keys, ('rad',) * len(keys), 'joint_bias', ('N*m',) * len(keys), 'joint-axis',
        'evaluation_boundary', float(cadence_s), 0.0, 'pure_no_physics_step', writer_id, 'none', 'required')
    profile = LinearEffortProfileV1(
        'linear-effort-profile-v1', writer_id, tuple(f'effort-{i}' for i in range(len(keys))), keys,
        tuple(tuple(1.0 if row == column else 0.0 for column in range(len(keys)))
              for row in range(len(keys))), requirement, action_key=action_key,
        action_low=tuple(channel.effort_range[0] for channel in channels),
        action_high=tuple(channel.effort_range[1] for channel in channels),
        selection_profile_id=profile_id)
    model = AffineJointBiasModelV1('affine-joint-bias-model-v1', requirement,
        (0.0,) * len(keys), (0.0,) * len(keys), (-0.25,) * len(keys))
    controller = LinearEffortControllerV1(profile, binding, model)
    controller.profile_id = profile_id
    return controller
