"""Task-owned shared MJCF/binding recipe; provider conversion stays in adapters."""
from dataclasses import replace
from ...assembly.source import TaskSceneSource
from ...environment import TaskCompositionSpec
from ...environment.configuration import overlay_public_env_config, load_yaml_mapping
from ...registry import make_agent, make_object, make_scene
from ...runtime.sessions.source import RuntimeSource
from .task import NutAssemblyEnv, NUT_ASSEMBLY_SQUARE_SPEC
from .assets import build_nut_assembly_model_xml, EE_SITE_NAME
from .canonical_artifact import require_family


def build_runtime_source(artifact):
    require_family(artifact); spec = NUT_ASSEMBLY_SQUARE_SPEC
    config = overlay_public_env_config(NutAssemblyEnv.default_config(), load_yaml_mapping(NutAssemblyEnv.default_config_path()))
    config = replace(config, runtime=replace(config.runtime, backend='cpu', prewarm=False,
        physics_dt=artifact.timebase.physics_dt, control_substeps=artifact.timebase.control_substeps),
        render=replace(config.render, camera_obs=False), robot=replace(config.robot,
            controller=replace(config.robot.controller, kind='absolute_pose', reference='world', rotation_representation='quaternion_wxyz')))
    xml, base = build_nut_assembly_model_xml()
    return RuntimeSource(artifact.identity_hash, TaskSceneSource(xml, base, 'nut-assembly-square-v1/canonical-source-v0'),
        {n:n.split('/',1)[1] for n in artifact.initialization.joint_position},
        {'square-nut-v1':'SquareNut', 'square-peg-v1':'peg1', 'round-peg-v1':'peg2', 'panda-v1/base':'link0'},
        {'panda-v1/ee':EE_SITE_NAME}, {'square-nut-v1':'SquareNut_joint'},
        {f'panda-v1/joint{i}':f'actuator{i}' for i in range(1,8)}, ('actuator8',),
        TaskCompositionSpec(spec.task_uid,spec.scene_uid,spec.agent_uids,spec.object_uids,success_definition=spec.success_definition),
        config, make_scene(spec.scene_uid), tuple(make_agent(n) for n in spec.agent_uids), tuple(make_object(n) for n in spec.object_uids))
