"""Shared value checks/projection only; no solver abstraction."""
import math
import xml.etree.ElementTree as ET

from ...artifacts import CanonicalStateView, PoseWorld
from ...artifacts.execution import RealizedInitialState


def pose(position, quaternion):
    q = tuple(float(v) for v in quaternion)
    norm = math.sqrt(sum(v*v for v in q))
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError('invalid provider quaternion')
    return PoseWorld(tuple(float(v) for v in position), tuple(v/norm for v in q))


class _SessionValues:
    def _initialize_values(self, artifact, source, provider):
        self._artifact, self._source, self._provider = artifact, source, provider
        self._closed, self._reset_done, self._control_step = False, False, 0
        root = ET.fromstring(source.scene_source.xml)
        option = root.find('option')
        if option is None or float(option.get('timestep', 'nan')) != artifact.timebase.physics_dt:
            raise ValueError('source/native physics timestep mismatch')

    def _require_open(self):
        if self._closed:
            raise RuntimeError('session is closed')

    def _require_reset(self):
        self._require_open()
        if not self._reset_done:
            raise RuntimeError('reset required before snapshot/step')

    def _validate_sample(self, sample):
        self._require_open()
        if sample.task_artifact_hash != self._artifact.identity_hash:
            raise ValueError('reset sample/Artifact mismatch')
        if set(sample.joint_position) != set(self._source.joints) or set(sample.poses_world) != set(self._source.free_joints):
            raise ValueError('reset semantic bindings mismatch')
        if sample.settle_steps != 0:
            raise ValueError('nonzero settle steps unsupported in P1.2')

    def _state(self, joints, velocities, poses, time):
        return CanonicalStateView('canonical-state-v0', 'SI_right_handed_z_up_wxyz',
                                  self._control_step, float(time), joints, velocities, poses)

    def _realized(self, sample):
        self._reset_done, self._control_step = True, 0
        return RealizedInitialState('realized-initial-state-v0', sample.sample_id,
                                    self._provider, self.snapshot(), 0)
