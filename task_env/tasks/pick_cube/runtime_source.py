"""Task-local Phase-I source bridge; no simulator API or native index resolution."""
from dataclasses import replace

from ...environment import TaskCompositionSpec
from ...environment.configuration import load_yaml_mapping, overlay_public_env_config
from ...registry import make_agent, make_object, make_scene
from ...runtime.sessions.source import RuntimeSource
from .assets import EE_SITE_NAME, PickCubeSceneComposer
from .candidate import build_candidate
from .task import PickCubeEnv, PICK_CUBE_SPEC


def build_runtime_source(artifact):
    if artifact.identity_hash != build_candidate().identity_hash:
        raise ValueError('source bridge only accepts the approved default candidate')
    spec = PICK_CUBE_SPEC
    config = overlay_public_env_config(PickCubeEnv.default_config(), load_yaml_mapping(PickCubeEnv.default_config_path()))
    config = replace(config, runtime=replace(config.runtime, backend='cpu', prewarm=False),
                     render=replace(config.render, camera_obs=False))
    joints = {name: name.split('/', 1)[1] for name in artifact.initialization.joint_position}
    return RuntimeSource(
        task_artifact_hash=artifact.identity_hash,
        scene_source=PickCubeSceneComposer().build_source_description(),
        joints=joints, bodies={'cube-v1': 'PickCube'}, frames={'panda-v1/ee': EE_SITE_NAME},
        free_joints={'cube-v1': 'PickCube_joint'},
        joint_targets={f'panda-v1/joint{i}': f'actuator{i}' for i in range(1, 8)},
        open_actuators=('actuator8',),
        composition=TaskCompositionSpec(spec.task_uid, spec.scene_uid, spec.agent_uids, spec.object_uids,
                                        success_definition=spec.success_definition),
        config=config, scene=make_scene(spec.scene_uid),
        agents=tuple(make_agent(uid) for uid in spec.agent_uids),
        objects=tuple(make_object(uid) for uid in spec.object_uids),
    )
