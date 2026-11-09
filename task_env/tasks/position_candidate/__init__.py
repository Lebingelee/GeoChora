"""Explicit, state-only Position candidate registration; no native initialization."""

from pathlib import Path
import tempfile

from ...registry import register_env
from ...environment.reference_env import SelectedReferenceEnv


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
            if set(values) - {'versioned_input', 'horizon', 'controller_config', 'physical_execution'}:
                raise ValueError('versioned Position candidate has unsupported configuration fields')
            from .builder import (
                F04PositionCandidateInputV1,
                F05NativePositionCandidateInputV1,
                build_versioned_position_candidate,
            )
            versioned_input = values['versioned_input']
            if type(versioned_input) not in (F04PositionCandidateInputV1,
                                             F05NativePositionCandidateInputV1):
                raise TypeError('versioned_input must be an exact supported F04/F05 native Position input')
            versioned_input.validate()
            horizon = values.get('horizon', 8)
            if type(horizon) is not int or not 1 <= horizon <= 6000:
                raise ValueError('Position candidate horizon must be an integer in [1, 6000]')
            controller_config = values.get('controller_config')
            if controller_config is not None:
                from ...environment.config import ActionConfig
                if isinstance(controller_config, dict):
                    controller_config = ActionConfig(**controller_config)
                if type(controller_config) is not ActionConfig:
                    raise TypeError('controller_config must be the exact ActionConfig contract')
            options = {}
            if 'physical_execution' in values:
                options['physical_execution'] = values['physical_execution']
            return build_versioned_position_candidate(
                versioned_input, horizon=horizon, environment_type=cls,
                controller_config=controller_config, **options,
            ).env
        if set(values) - {'provider', 'backend', 'horizon', 'source_workspace', 'camera_observation', 'physical_profile', 'task_probe_force_y_N'}:
            raise ValueError('Position candidate has unsupported configuration fields')
        provider = values.get('provider', 'geophys')
        backend = values.get('backend', 'cpu')
        horizon = values.get('horizon', 6000)
        if type(horizon) is not int or not 1 <= horizon <= 6000:
            raise ValueError('Position candidate horizon must be an integer in [1, 6000]')
        camera_config = values.get('camera_observation')
        physical_profile = values.get('physical_profile')
        if physical_profile not in (None, 'panda-direct-effort-v1', 'panda-direct-effort-wrench-v1',
                                     'panda-direct-effort-object-wrench-v1', 'panda-split-direct-effort-v1',
                                     'panda-fixed-frame-point-wrench-v1', 'panda-free-body-point-wrench-v1',
                                     'panda-free-body-wrench-only-v1', 'panda-direct-effort-home-v1'):
            raise ValueError('unsupported physical control profile')
        if backend != 'cpu' or (provider != 'geophys' and not (
                provider == 'mujoco' and physical_profile is not None)):
            raise ValueError('Position candidate admits GeoPhys CPU, or MuJoCo CPU with a physical profile')
        if physical_profile is not None and camera_config is not None:
            raise ValueError('physical control profile does not admit camera observation')
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

        options = {} if physical_profile is None else {'physical_profile': physical_profile}
        if 'task_probe_force_y_N' in values:
            options['task_probe_force_y_N'] = values['task_probe_force_y_N']
        return build_position_candidate(
            workspace, provider=provider, horizon=horizon, environment_type=cls,
            camera_observation_config=camera_config, **options,
        ).env


__all__ = ['PositionCandidateEnv']
