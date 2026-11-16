"""Source-bound Robot view over an existing device-batch runtime."""
from __future__ import annotations

from types import MappingProxyType


class RobotBatchView:
    """Describe declared subjects and project their current device state.

    This view owns no simulator or state cache. Static mappings come from the
    compiled source and runtime publication; dynamic values come from the
    same live runtime and retain its generation and boundary identity.
    """

    def __init__(self, *, robot, execution, runtime):
        self.robot = robot
        self._runtime = runtime
        self._binding = execution.compiled.binding
        self.subjects = tuple(execution.subjects)
        self.channels = tuple(self._binding.channels)
        summary = runtime.resource_summary()['device_transition']
        self.joint_qpos_indices = MappingProxyType(dict(summary['joint_qpos_indices']))
        self.body_names = tuple(summary['body_names'])
        self.frame_names = tuple(summary['frame_names'])
        self._generation = execution.generation
        keys = tuple(f'{channel.entity_id}/{channel.joint_id}' for channel in self.channels)
        if len(set(keys)) != len(keys) or not set(keys) <= set(self.joint_qpos_indices):
            raise ValueError('Robot batch joints differ from the source-bound device layout')
        self.controlled_joints = keys

    def _validate_state(self, state):
        from ..runtime.contracts import DeviceBatchState

        if not isinstance(state, DeviceBatchState) or state.identity is None:
            raise TypeError('Robot batch view requires an identified device state')
        identity = state.identity
        if ((identity.source_id, identity.source_closure_sha256, identity.artifact_sha256)
                != (self._binding.source_id, self._binding.source_closure_sha256,
                    self._binding.artifact_sha256)
                or identity.generation != self._generation
                or identity != self._runtime.device_state_identity()):
            raise ValueError('Robot batch view state is stale or belongs to another source')
        return state.arrays

    def joint_positions(self, state, names=None):
        """Return declared named joint positions with shape ``(B, joints)``."""
        arrays = self._validate_state(state)
        keys = self.controlled_joints if names is None else tuple(names)
        try:
            indices = [self.joint_qpos_indices[name] for name in keys]
        except KeyError as error:
            raise ValueError(f'Robot batch has no declared joint {error.args[0]!r}') from error
        return arrays['qpos'][:, indices]

    def frame_pose(self, state, name):
        """Return env-local position and wxyz orientation with shape ``(B, 7)``."""
        import torch

        arrays = self._validate_state(state)
        if name in self.frame_names:
            index, prefix = self.frame_names.index(name), 'frame'
        elif name in self.body_names:
            index, prefix = self.body_names.index(name), 'body'
        else:
            raise ValueError(f'Robot batch has no declared frame {name!r}')
        return torch.cat((arrays[prefix + '_position'][:, index],
                          arrays[prefix + '_orientation'][:, index]), dim=1)

    def read_device_state(self, names):
        """Read the current source-bound publication from the live runtime."""
        state = self._runtime.read_device_state(tuple(names))
        self._validate_state(state)
        return state
