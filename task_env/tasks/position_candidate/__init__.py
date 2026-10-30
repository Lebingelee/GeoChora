"""Explicit, state-only Position candidate registration; no native initialization."""

from pathlib import Path
import tempfile

from ...registry import register_env
from ..reference_env import SelectedReferenceEnv


@register_env()
class PositionCandidateEnv(SelectedReferenceEnv):
    """Bounded single-Panda candidate, without release/freeze or Judge approval."""

    uid = 'panda-position-servo-candidate-v1'

    @classmethod
    def from_reference_config(cls, config=None, *, render_mode=None, **kwargs):
        values = {} if config is None else dict(config)
        if kwargs or render_mode is not None:
            raise ValueError('Position candidate rejects render_mode and extra keyword arguments')
        if 'versioned_input' in values:
            if set(values) - {'versioned_input', 'horizon'}:
                raise ValueError('versioned Position candidate admits only versioned_input and horizon')
            from .builder import (
                F03PositionCandidateInputV1, F04PositionCandidateInputV1,
                F05PositionCandidateInputV1, F05NativePositionCandidateInputV1,
                build_versioned_position_candidate,
            )
            versioned_input = values['versioned_input']
            if type(versioned_input) not in (F03PositionCandidateInputV1, F04PositionCandidateInputV1,
                                             F05PositionCandidateInputV1, F05NativePositionCandidateInputV1):
                raise TypeError('versioned_input must be an exact supported F03/F04/F05 Position input')
            versioned_input.validate()
            horizon = values.get('horizon', 8)
            if type(horizon) is not int or not 1 <= horizon <= 6000:
                raise ValueError('Position candidate horizon must be an integer in [1, 6000]')
            return build_versioned_position_candidate(
                versioned_input, horizon=horizon, environment_type=cls,
            ).env
        if set(values) - {'provider', 'backend', 'horizon', 'source_workspace', 'camera_observation'}:
            raise ValueError('Position candidate config admits provider/backend/horizon/source_workspace and opt-in camera_observation only')
        provider = values.get('provider', 'geophys')
        backend = values.get('backend', 'cpu')
        horizon = values.get('horizon', 6000)
        if provider != 'geophys' or backend != 'cpu':
            raise ValueError('public Position candidate admits GeoPhys scalar CPU only')
        if type(horizon) is not int or not 1 <= horizon <= 6000:
            raise ValueError('Position candidate horizon must be an integer in [1, 6000]')
        camera_config = values.get('camera_observation')
        if camera_config is not None:
            from ...observations.canonical_camera.consumer import CameraObservationConfigV1

            if isinstance(camera_config, dict):
                camera_config = CameraObservationConfigV1.from_mapping(camera_config)
            if not isinstance(camera_config, CameraObservationConfigV1):
                raise TypeError('camera_observation must use camera-observation-consumer-v1')
            camera_config.validate_production_envelope()
            camera_config.capacity(horizon)
        workspace = values.get('source_workspace')
        if workspace is None:
            root = Path('workspace/tasks/phase-ii-c02b-position-servo/candidate-sources')
            root.mkdir(parents=True, exist_ok=True)
            workspace = tempfile.mkdtemp(prefix='source-', dir=root)
        elif not isinstance(workspace, (str, Path)) or not str(workspace):
            raise ValueError('source_workspace must be a nonempty path')
        elif Path(workspace).exists() and any(Path(workspace).iterdir()):
            raise ValueError('source_workspace must be fresh or empty; existing source bytes are preserved')
        from .builder import build_position_candidate

        return build_position_candidate(
            workspace, provider=provider, horizon=horizon, environment_type=cls,
            camera_observation_config=camera_config,
        ).env


__all__ = ['PositionCandidateEnv']
