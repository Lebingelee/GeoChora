"""Source-traced PickCube MJCF physical-control candidate using the selected Env."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil

from ...registry import register_env
from ...environment.reference_env import SelectedReferenceEnv


def _physical_pickcube_observation(env, state):
    """Keep the task's source EE site distinct from the Panda hand-origin frame."""
    import numpy as np
    from ...observations.selected_reference import build_selected_observation
    obs, info, _ = build_selected_observation(env, state)
    ee = state.pose_world['panda-v1/ee']
    obs['state']['ee_pose'] = np.asarray((*ee.position, *ee.quaternion_wxyz), dtype=np.float32)
    evaluation = env.binding.evaluate(state, env.artifact.semantics)
    info.update(is_success=bool(evaluation.success), task_failure=bool(evaluation.failure),
                task_metrics=dict(evaluation.metrics))
    return obs, info, evaluation


@register_env()
class PickCubePhysicalCandidateEnv(SelectedReferenceEnv):
    """Position compatibility plus typed physical control for PickCube MJCF."""
    uid = 'pickcube-physical-candidate-v1'
    task_rgb_factory_prepares_runtime = True

    @classmethod
    def from_reference_config(cls, config=None, *, render_mode=None, **kwargs):
        values = {} if config is None else dict(config)
        observer_camera = kwargs.pop('observer_camera', None)
        task_camera = kwargs.pop('task_camera', None)
        task_rgb_camera = kwargs.pop('task_rgb_camera', None)
        task_renderer = kwargs.pop('task_renderer', None)
        if (task_rgb_camera is None) != (task_renderer is None):
            raise ValueError('task RGB camera and fixed renderer must be declared together')
        if task_rgb_camera is not None:
            from ...observations.canonical_camera import CameraGeometry
            if type(task_rgb_camera) is not CameraGeometry:
                raise TypeError('task RGB camera must be CameraGeometry')
            task_rgb_camera.validate()
        if task_rgb_camera is not None and task_camera is not None:
            raise ValueError('declare either a task RGB camera or a legacy task camera binding')
        if (task_renderer == 'geophys' and observer_camera is not None
                and (task_rgb_camera.width, task_rgb_camera.height) != (observer_camera.width, observer_camera.height)):
            raise ValueError('GeoPhys task and observer cameras require the same framebuffer extent')
        if kwargs or set(values) - {'provider', 'backend', 'horizon', 'source_workspace', 'seed', 'drive_mode', 'control_kind', 'reset_switch', 'action_space_policy'}:
            raise ValueError('PickCube physical candidate rejects unsupported configuration')
        if task_camera is not None:
            from ...observations.canonical_camera import CameraGeometry
            if type(task_camera) is not CameraGeometry:
                raise TypeError('task camera must be CameraGeometry')
            task_camera.validate()
            if task_camera.parent_frame != 'world' or render_mode is None:
                raise ValueError('task camera requires observer rendering and a world mount')
            if task_camera.camera_id == getattr(observer_camera, 'camera_id', None):
                raise ValueError('task and observer cameras require distinct identities')
        if render_mode is not None:
            from ...render.base.contracts import normalize_render_mode
            from ...observations.canonical_camera import CameraGeometry
            render_mode = normalize_render_mode(render_mode).value
            if not isinstance(observer_camera, CameraGeometry):
                raise ValueError('rendering requires an explicit observer CameraGeometry')
            observer_camera.validate()
            if not observer_camera.rgb or observer_camera.depth or observer_camera.rgb_layout != 'HWC' or observer_camera.rgb_dtype != 'float32':
                raise ValueError('observer requires HWC float32 RGB without depth')
        elif observer_camera is not None:
            raise ValueError('observer camera requires a configured render mode')
        provider, backend = values.get('provider', 'mujoco'), values.get('backend', 'cpu')
        if task_rgb_camera is not None and (provider, backend, task_renderer) not in {
                ('mujoco', 'cpu', 'mujoco'), ('geophys', 'cpu', 'mujoco'),
                ('geophys', 'cpu', 'geophys')}:
            raise ValueError('unsupported fixed task RGB renderer and physics pairing')
        horizon, seed = values.get('horizon', 8), values.get('seed', 31)
        drive_mode, control_kind = values.get('drive_mode', 'coexist'), values.get('control_kind', 'direct')
        reset_switch = values.get('reset_switch', False)
        space_policy = values.get('action_space_policy', 'dynamic')
        if type(reset_switch) is not bool or space_policy not in {'dynamic', 'fixed_semantic'}:
            raise ValueError('invalid physical reset switch or action-space policy')
        if reset_switch and ((provider, backend) != ('mujoco', 'cpu')
                             or drive_mode != 'effort-only' or control_kind not in {'joint', 'r3-pose'}):
            raise ValueError('physical reset switch requires MuJoCo CPU and an isolated reference controller')
        if not reset_switch and space_policy != 'dynamic':
            raise ValueError('physical action-space policy requires reset switching')
        if drive_mode not in {'coexist', 'effort-only'} or control_kind not in {'direct', 'joint', 'r3-pose', 'joint-mass', 'r3-mass-pose'}:
            raise ValueError('unsupported physical drive or controller mode')
        if control_kind != 'direct' and drive_mode != 'effort-only':
            raise ValueError('reference effort requires the isolated drive fixture')
        if (provider, backend) not in {('mujoco', 'cpu'), ('geophys', 'cpu')}:
            raise ValueError('PickCube MJCF physical candidate admits MuJoCo or GeoPhys CPU')
        if render_mode is not None:
            mujoco_observer = (provider, backend) == ('mujoco', 'cpu') and reset_switch
            geophys_observer = ((provider, backend) == ('geophys', 'cpu') and not reset_switch
                                and drive_mode == 'effort-only' and control_kind == 'joint')
            if not (mujoco_observer or geophys_observer):
                raise ValueError('observer requires MuJoCo reset switching or GeoPhys CPU joint effort')
        if type(horizon) is not int or not 1 <= horizon <= 6000 or type(seed) is not int or seed < 0:
            raise ValueError('PickCube physical candidate requires a valid horizon and seed')
        workspace = values.get('source_workspace')
        if not isinstance(workspace, (str, Path)) or not str(workspace):
            raise ValueError('PickCube physical candidate requires a fresh source_workspace')
        root = Path(workspace).resolve()
        if root.exists() and any(root.iterdir()):
            raise ValueError('PickCube physical source_workspace must be fresh or empty')
        env = _build_candidate(root, provider=provider, horizon=horizon, seed=seed, environment_type=cls,
                               drive_mode=drive_mode, control_kind=control_kind, reset_switch=reset_switch,
                               space_policy=space_policy)
        if task_rgb_camera is not None:
            try:
                env._configure_task_rgb(task_rgb_camera, task_renderer)
            except BaseException as error:
                try:
                    env.close()
                except BaseException as cleanup_error:
                    error.add_note(f'task RGB construction cleanup failed: {cleanup_error!r}')
                raise
        if render_mode is not None:
            try:
                if task_camera is not None:
                    import copy
                    if task_camera.task_artifact_hash != env.artifact.identity_hash:
                        raise ValueError('task camera TaskArtifact linkage mismatch')
                    env._declared_task_camera = copy.deepcopy(task_camera)
                env._configure_selected_observer(render_mode, observer_camera)
            except BaseException as error:
                try:
                    env.close()
                except BaseException as cleanup_error:
                    error.add_note(f'candidate observer construction cleanup failed: {cleanup_error!r}')
                raise
        return env


def _pickcube_mjcf_scene(task_config):
    """Bind the authored MJCF names to the existing PickCube/Panda Scene owner."""
    from ...artifacts import SceneDefinition
    from ...robots.panda import PandaAgent
    from .specialization import build_pickcube_isaac_scene
    scene = build_pickcube_isaac_scene(task_config)
    mapping = scene.to_mapping()
    panda = PandaAgent()._scene_definition(entity_id='panda-v1', scene_id=scene.scene_id)
    mapping['assets'] = [panda.assets[0].to_mapping()
        if asset['asset_id'] == 'f05-dg03-menagerie-panda-source-preserving-isaac-usd' else asset
        for asset in mapping['assets']]
    for entity in mapping['entities']:
        if entity['entity_id'] == 'panda-v1':
            entity['asset_id'], entity['asset_version'] = panda.entities[0].asset_id, panda.entities[0].asset_version
    for frame in mapping['frames']:
        key = (frame['entity_id'], frame['frame_id'])
        frame['frame_id'] = {('cube-v1', 'cube'): 'PickCube', ('tabletop-v1', 'top'): 'grasp_table',
                             ('panda-v1', 'ee'): 'nutassembly_ee_site'}.get(key, frame['frame_id'])
    for articulation in mapping['articulations']:
        if articulation['entity_id'] == 'cube-v1':
            articulation['link_frame_ids'] = ['world', 'PickCube']
            joint = articulation['joints'][0]
            joint['joint_id'], joint['child_frame']['frame_id'] = 'PickCube_joint', 'PickCube'
    return SceneDefinition.from_mapping(mapping)


def _build_candidate(root, *, provider, horizon, seed, environment_type, drive_mode, control_kind,
                     reset_switch=False, space_policy='dynamic'):
    from ...artifacts import FrameReference
    from ...assembly.assets import _source_closure_digest
    from ...assembly.source import TaskSceneSource
    from ...controllers.canonical.position_profile import PandaPositionServoProfileV1
    from ...controllers.canonical.contracts import reference_pose_action
    from ...environment import adapt_legacy_recipe_task_source, compile_task_artifact_v1, sample_episode_reset_plan
    from ...environment.reference_binding import ReferenceTaskBinding
    from ...observations.selected_reference import build_selected_observation, selected_reference_observation_spaces
    from ...runtime.sessions.control import ControlBinding, compile_control_binding_plan
    from ...runtime.sessions.source import project_scene_definition_v3_to_mjcf, source_asset_bytes
    from ..position_candidate.physical_profile import build_panda_direct_effort_execution
    from .specialization import _configuration, build_reference, evaluate

    root.mkdir(parents=True, exist_ok=True)
    task_config = _configuration()
    base = build_reference(backend='cpu', include_solution=False, controller_profile='r3_continuous_v1')
    original, legacy_artifact = base['source'], base['artifact']
    # The force-observation fixture starts inside the paired finger limits;
    # it retains PickCube semantics and is a distinct Artifact identity.
    if not reset_switch:
        joint_initial = dict(legacy_artifact.initialization.joint_position)
        joint_initial.update({'panda-v1/finger_joint1': 0.02, 'panda-v1/finger_joint2': 0.02})
        legacy_artifact = replace(legacy_artifact,
            initialization=replace(legacy_artifact.initialization, joint_position=joint_initial))
    if drive_mode == 'effort-only':
        legacy_artifact = replace(legacy_artifact,
            artifact_id=('pickcube-mjcf-physical-effort-task-v1' if reset_switch
                         else 'pickcube-mjcf-physical-effort-no-drive-v1'),
            initialization=replace(legacy_artifact.initialization,
                                   reset_validity=('mjcf-physical-effort-task-v1' if reset_switch
                                                   else 'mjcf-physical-effort-no-drive-v1')))
    receipt = original.execution_source_receipt
    try:
        if (receipt is None or original.source_closure_digest !=
                '02f12b11e8215af606d9eed7f22c411dc5bbd74f7d956331b74400b5a1e6963d'):
            raise ValueError('PickCube physical candidate requires the exact original MJCF closure')
        receipt.validate_snapshot()
        scene = _pickcube_mjcf_scene(task_config)
        task_source = adapt_legacy_recipe_task_source({'recipe': task_config['recipe'], 'environment': task_config['environment']})
        artifact = compile_task_artifact_v1(task_source, scene, legacy_artifact, frame_bindings={
            'panda-v1/base': FrameReference('panda-v1', 'link0'),
            'panda-v1/ee': FrameReference('panda-v1', 'nutassembly_ee_site'),
            'tabletop-v1/top': FrameReference('tabletop-v1', 'grasp_table'),
        })
        frame_aliases = dict(artifact.legacy_frame_bindings)
        frame_aliases['cube-v1'] = FrameReference('cube-v1', 'PickCube')
        for frame in scene.frames or ():
            if frame.entity_id == 'panda-v1' and frame.frame_id != 'nutassembly_ee_site':
                frame_aliases.setdefault(f'panda-v1/{frame.frame_id}', FrameReference('panda-v1', frame.frame_id))
        artifact = replace(artifact, legacy_frame_bindings=frame_aliases)
        artifact.validate_scene(scene)
        destination = root / 'source-snapshot'
        shutil.copytree(receipt.snapshot_root, destination)
        xml = receipt.importer_xml.decode('utf-8')
        projected = project_scene_definition_v3_to_mjcf(xml, scene)
        closure = _source_closure_digest({'scene.xml': projected.encode('utf-8'),
                                          **source_asset_bytes(destination, projected)})
        bodies = {f'panda-v1/{frame.frame_id}': frame.frame_id for frame in scene.frames or ()
                  if frame.entity_id == 'panda-v1' and frame.frame_id != 'nutassembly_ee_site'}
        bodies.update({'cube-v1': 'PickCube', 'tabletop-v1/top': 'grasp_table'})
        source = replace(original, task_artifact_hash=artifact.identity_hash,
            scene_source=TaskSceneSource(xml, destination, f'scene-definition-v3:{scene.identity_hash}'),
            scene_definition=scene, source_closure_digest=closure, execution_source_receipt=None,
            bodies=bodies, frames={'panda-v1/ee': 'nutassembly_ee_site'})
    finally:
        if receipt is not None:
            receipt.close()
    reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=seed)
    position = PandaPositionServoProfileV1.from_source(artifact, source, entity_id='panda-v1')
    plan = compile_control_binding_plan(scene, (position.controller_binding(),))
    def build_physical(kind, **parameters):
        if (set(parameters) - {'kp', 'kd', 'finger_kp', 'finger_kd'}
                or any(type(value) not in (int, float) or not 0. < value <= 5000.
                       for value in parameters.values())):
            raise ValueError('unsupported or invalid physical controller parameters')
        if parameters and not reset_switch:
            raise ValueError('controller parameters require physical reset selection')
        physical = build_panda_direct_effort_execution(scene, artifact, source, entity_id='panda-v1',
            native_drive='disabled' if drive_mode == 'effort-only' else 'position',
            gripper_force_limit=10. if reset_switch else None)
        if kind != 'direct':
            from ...controllers.canonical.r3_effort import build_reference_effort_execution
            reference = None
            if kind in {'r3-pose', 'r3-mass-pose'}:
                from ...controllers.canonical.kinematics import PandaKinematics, PANDA_PICKCUBE_EE_TCP_V1
                from ...controllers.canonical.production_r3 import ProductionCanonicalPandaControllerR3
                from .specialization import _r3_dynamic_profile, PICKCUBE_R3_CONTINUOUS_PROFILE_V1
                model = PandaKinematics(projected, tcp_profile=PANDA_PICKCUBE_EE_TCP_V1)
                r3_profile, _ = _r3_dynamic_profile()
                reference = ProductionCanonicalPandaControllerR3.create_arm_reference(
                    model, artifact_hash=artifact.identity_hash, config=position.config,
                    control_dt=artifact.timebase.control_dt, profile=r3_profile,
                    joint_velocity_limit_rad_s=PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s'])
            if reset_switch:
                from ...controllers.canonical.r3_effort import build_dynamic_reference_effort_execution
                physical = build_dynamic_reference_effort_execution(physical, reference_kind=kind,
                    cadence_s=artifact.timebase.control_dt, r3_reference=reference,
                    end_frame_id='nutassembly_ee_site', **parameters)
            elif kind in {'joint-mass', 'r3-mass-pose'}:
                from .physical_mass_profile import build_pickcube_mass_effort_execution
                physical = build_pickcube_mass_effort_execution(physical, artifact, source, kind=kind,
                    r3_reference=reference, end_frame_id='nutassembly_ee_site')
            else:
                physical = build_reference_effort_execution(physical, reference_kind=kind,
                    r3_reference=reference, end_frame_id='nutassembly_ee_site')
        return physical

    physical = build_physical(control_kind)
    def build(_provider):
        return {'artifact': artifact, 'task_source': task_source, 'source': source,
            'controller': position, 'solution': None, 'reset_plan': reset_plan,
            **({'solution_factory': base['solution_factory'], 'solution_identity': base['solution_identity'],
                'readiness': base['readiness']} if reset_switch else {}),
            'controller_binding_plan': plan, 'construction_id': 'pickcube-mjcf-physical-candidate-v1',
            'source_revision': base['source_revision'], 'source_sha256': {
                'original_closure': '02f12b11e8215af606d9eed7f22c411dc5bbd74f7d956331b74400b5a1e6963d',
                'projected_closure': closure},
            'resolved_configuration': {'provider': _provider, 'backend': 'cpu',
                'finger_initial_position_m': float(legacy_artifact.initialization.joint_position['panda-v1/finger_joint1']),
                'drive_mode': drive_mode, 'control_kind': control_kind,
                'original_closure': '02f12b11e8215af606d9eed7f22c411dc5bbd74f7d956331b74400b5a1e6963d',
                'projected_closure': closure, 'physical_binding': physical.compiled.binding.identity_hash}}
    def fixed_seed(value):
        if type(value) is not int or value != seed:
            raise ValueError('PickCube physical candidate requires its frozen seed')
        return value
    def physical_execution_info(env):
        from .solution import PickCubePositionExecutionInfoV1
        state = env.state
        opening = sum(float(state.joint_position[f'panda-v1/finger_joint{i}']) for i in (1, 2))
        if -1e-6 <= opening < 0.:
            opening = 0.
        speed = sum(abs(float(state.joint_velocity[f'panda-v1/finger_joint{i}'])) for i in (1, 2))
        target = getattr(env, '_last_physical_opening_target', None)
        target = min(.08, max(0., opening)) if target is None else target
        return PickCubePositionExecutionInfoV1('pickcube-position-execution-info-v1',
            int(state.control_step), float(state.simulation_time), opening, speed, target,
            bool(target <= .045 and opening <= .045 and speed <= .005))
    from .specialization import _validate_external_readiness_solution
    binding = ReferenceTaskBinding(build=build, reset_sample=lambda _artifact, _seed: reset_plan.reset_sample,
        evaluate=lambda state, semantics: evaluate(state, semantics),
        object_poses=(('cube-v1', 'cube_v1'),), external_actions=True, interval_mode='grouped',
        recorder_mode='execution', reset_seed=fixed_seed,
        position_control_binding=lambda _value: ControlBinding('panda-v1/gripper', 0.08),
        action_schema={'schema_version': 'physical-control-actions-v1',
                       'controllers': [{'identity': c.identity, 'shape': list(c.action_shape)} for c in physical.controllers]},
        action_space_factory=physical.action_space, prepare_action=reference_pose_action,
        observation_space_factory=selected_reference_observation_spaces,
        observation_projection=_physical_pickcube_observation if reset_switch else build_selected_observation,
        build_external=build if reset_switch else None,
        validate_external_solution=_validate_external_readiness_solution if reset_switch else None,
        position_execution_info=physical_execution_info if reset_switch else None,
        position_execution_info_key='pickcube_position_execution_info_v1' if reset_switch else None,
        physical_control_profile=(lambda env: env._physical_reset_selection.current.execution)
                                 if reset_switch else (lambda _env: physical))
    env = environment_type.from_position_candidate(binding, provider=provider, backend='cpu', horizon=horizon)
    if reset_switch:
        from ...controllers.canonical.reset_selection import PhysicalResetSelection
        env._physical_reset_selection = PhysicalResetSelection(build_physical, initial_kind=control_kind,
            allowed_kinds=('joint', 'r3-pose'), space_policy=space_policy)
    return env
