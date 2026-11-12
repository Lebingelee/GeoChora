"""Source-traced PickCube MJCF physical-control candidate using the selected Env."""
from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path


def physical_binding_from_config(config, *, robot=None):
    import json
    options = json.loads(config.controller_parameters_json)
    task_config = json.loads(config.task_configuration_json)
    lift_height_m = dict(config.task_parameters).get('lift_height_m')
    from ...controllers.canonical.r3_effort import resolve_panda_effort_options
    kind, drive, reset_switch, space_policy = resolve_panda_effort_options(
        config.controller_profile, config.native_drive, options)
    if config.physics_provider == 'isaacsim':
        from .physical_isaac_candidate import make_isaac_physical_binding
        return make_isaac_physical_binding(delivery_manifest=config.source_delivery_manifest,
            horizon=config.environment.episode.horizon,
            drive_mode='effort-only' if drive == 'disabled' else 'coexist', control_kind=kind,
            task_config=task_config, resolved_config=config.environment, lift_height_m=lift_height_m, robot=robot)
    force = dict(config.task_parameters).get('cube_force_z_N')
    return make_physical_binding(
        drive_mode='effort-only' if drive == 'disabled' else 'coexist', control_kind=kind,
        reset_switch=reset_switch, space_policy=space_policy,
        cube_force_z_N=force, task_config=task_config, resolved_config=config.environment,
        lift_height_m=lift_height_m, robot=robot)


def make_physical_binding(*, drive_mode, control_kind,
                          task_config, resolved_config, reset_switch=False,
                          space_policy='dynamic', cube_force_z_N=None, lift_height_m=None, robot=None):
    """Declare task/source/control bindings; the shared factory constructs Env."""
    from ...environment import sample_episode_reset_plan
    from ...environment.reference_binding import ReferenceTaskBinding
    from .specialization import _prepare_reference_source, compile_reference_robot_task
    from .task import (physical_task_binding_fields,
                       physical_execution_info, observe_physical_action)

    prepared = _prepare_reference_source(
        backend='cpu', controller_profile='r3_continuous_v1', task_config=task_config,
        resolved_config=resolved_config, lift_height_m=lift_height_m, include_readiness=reset_switch, robot=robot)
    legacy_artifact, original, readiness = prepared.artifact, prepared.source, prepared.readiness
    from ...runtime.sessions.source import close_execution_source_on_failure
    with close_execution_source_on_failure(original):
        import subprocess
        revision = subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parents[3]),
                                            'rev-parse', 'HEAD'], text=True).strip()
        if reset_switch:
            from .solution import PickCubeReadinessSolution
            solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
        receipt = original.execution_source_receipt
    with ExitStack() as resources:
        resources.callback(receipt.close)
        robot = original.agents[0]
        task_source, scene, artifact, source, projected, closure = compile_reference_robot_task(
            task_config, robot, legacy_artifact, original)
        def build_physical(kind, **parameters):
            from ...controllers.canonical.dynamic_mass_effort import validate_reset_effort_parameters
            validate_reset_effort_parameters(parameters)
            if parameters and not reset_switch:
                raise ValueError('controller parameters require physical reset selection')
            from ...runtime.sessions.source_composition_adapters import build_panda_source_effort_profile
            from .specialization import panda_effort_task_settings
            native_drive = 'disabled' if drive_mode == 'effort-only' else 'position'
            return build_panda_source_effort_profile(robot, scene, artifact, source,
                native_drive=native_drive, kind=kind, config=source.config.action,
                source_xml=projected, end_frame_id='nutassembly_ee_site',
                task_settings=panda_effort_task_settings(kind),
                gripper_force_limit_N=source.config.robot.gripper.force_limit_N if reset_switch else None,
                dynamic_parameters=parameters if reset_switch else None)

        physical = build_physical(control_kind)
        def build(provider, backend, actual_seed, _horizon, sampled):
            if backend != source.config.runtime.backend:
                raise ValueError('requested backend differs from the declared Robot source')
            if sampled is not None:
                raise ValueError('PickCube does not accept an externally sampled reset')
            reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=actual_seed)
            return {'artifact': artifact, 'task_source': task_source, 'source': source,
                'controller': physical.controllers[0],
                'solution': None, 'reset_plan': reset_plan,
                **({'solution_factory': lambda: PickCubeReadinessSolution(config=readiness),
                    'solution_identity': solution_identity, 'readiness': readiness} if reset_switch else {}),
                'physical_execution': physical,
                'construction_id': 'pickcube-mjcf-physical-candidate-v1',
                'source_revision': revision, 'source_sha256': {
                    'original_closure': original.source_closure_digest,
                    'projected_closure': closure},
                'resolved_configuration': {'provider': provider, 'backend': backend,
                    'finger_initial_position_m': float(legacy_artifact.initialization.joint_position['panda-v1/finger_joint1']),
                    'drive_mode': drive_mode, 'control_kind': control_kind,
                    **({'task_com_force_v1': {'cube_force_z_N': cube_force_z_N}}
                       if cube_force_z_N is not None else {}),
                    'original_closure': original.source_closure_digest,
                    'projected_closure': closure, 'physical_binding': physical.compiled.binding.identity_hash}}
        from .specialization import _validate_external_readiness_solution
        from ...controllers.canonical.reset_selection import PhysicalResetSelection
        from ...controllers.canonical.r3_effort import panda_reset_action_schema
        owned_resources = ExitStack()
        binding = ReferenceTaskBinding(build=build,
            **physical_task_binding_fields(task_config=task_config, lift_height_m=lift_height_m,
                hand_frame_id='hand',
                cube_force_z_N=cube_force_z_N, reset_sampler=lambda _artifact, actual_seed:
                    sample_episode_reset_plan(task_source, scene, artifact, task_seed=actual_seed).reset_sample),
            close_task_resources=owned_resources.close,
            action_schema=physical.action_schema(),
            action_space_factory=physical.action_space,
            validate_external_solution=_validate_external_readiness_solution if reset_switch else None,
            position_execution_info=physical_execution_info if reset_switch else None,
            position_execution_info_key='pickcube_position_execution_info_v1' if reset_switch else None,
            physical_reset_action_schema=panda_reset_action_schema if reset_switch else None,
            physical_reset_selection_factory=(lambda: PhysicalResetSelection(build_physical,
                initial_kind=control_kind, allowed_kinds=('joint', 'r3-pose'), space_policy=space_policy,
                declaration=physical))
                if reset_switch else None,
            physical_action_observer=observe_physical_action if reset_switch else None)
        owned_resources.callback(resources.pop_all().close)
        return binding
