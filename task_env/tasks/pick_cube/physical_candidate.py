"""Source-traced PickCube MJCF physical-control candidate using the selected Env."""
from __future__ import annotations

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
        from .specialization import make_reference_binding
        return make_reference_binding(source_delivery_manifest=config.source_delivery_manifest,
            resolved_config=config.environment, lift_height_m=lift_height_m, task_config=task_config,
            robot=robot, physical_kind=kind, physical_drive=drive)
    force = dict(config.task_parameters).get('cube_force_z_N')
    return make_physical_binding(
        native_drive=drive, control_kind=kind,
        reset_switch=reset_switch, space_policy=space_policy,
        cube_force_z_N=force, task_config=task_config, resolved_config=config.environment,
        lift_height_m=lift_height_m, robot=robot)


def make_physical_binding(*, native_drive, control_kind,
                          task_config, resolved_config, reset_switch=False,
                          space_policy='dynamic', cube_force_z_N=None, lift_height_m=None, robot=None):
    """Declare task/source/control bindings; the shared factory constructs Env."""
    from ...environment import sample_episode_reset_plan
    from ...environment.reference_binding import ReferenceTaskBinding
    from .specialization import _prepare_reference_source, compile_reference_robot_task
    from .task import (physical_task_binding_fields,
                       physical_execution_info, observe_physical_action)

    from .specialization import _validate_external_readiness_solution
    from ...controllers.canonical.reset_selection import PhysicalResetSelection
    from ...controllers.canonical.r3_effort import (PANDA_SWITCHABLE_EFFORT_KINDS,
                                                    panda_reset_action_schema)
    from ...runtime.sessions.source import close_execution_source_on_failure

    # The common construction request owns the source, not the Task binding.
    # Resets of this admitted route reuse its immutable source and build a new
    # task reset plan; Env.close releases the source receipt once.
    prepared_value = None

    def build(provider, backend, actual_seed, _horizon, sampled):
        nonlocal prepared_value
        if backend != resolved_config.runtime.backend:
            raise ValueError('requested backend differs from the declared Robot source')
        if sampled is not None:
            raise ValueError('PickCube does not accept an externally sampled reset')
        if prepared_value is None:
            prepared = _prepare_reference_source(
                backend=backend, controller_profile='r3_continuous_v1', task_config=task_config,
                resolved_config=resolved_config, lift_height_m=lift_height_m,
                include_readiness=reset_switch, robot=robot)
            legacy_artifact, original, readiness = prepared.artifact, prepared.source, prepared.readiness
            with close_execution_source_on_failure(original):
                import subprocess
                revision = subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parents[3]),
                                                    'rev-parse', 'HEAD'], text=True).strip()
                if reset_switch:
                    from .solution import PickCubeReadinessSolution
                    solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
                selected_robot = original.agents[0]
                task_source, scene, artifact, source, projected, closure = compile_reference_robot_task(
                    task_config, selected_robot, legacy_artifact, original)

                def build_physical(kind, **parameters):
                    from ...runtime.sessions.source_composition_adapters import build_panda_source_effort_profile
                    from .specialization import panda_effort_task_settings
                    return build_panda_source_effort_profile(selected_robot, scene, artifact, source,
                        native_drive=native_drive, kind=kind, config=source.config.action,
                        source_xml=projected, end_frame_id='nutassembly_ee_site',
                        task_settings=panda_effort_task_settings(kind),
                        gripper_force_limit_N=source.config.robot.gripper.force_limit_N if reset_switch else None,
                        dynamic_parameters=parameters if reset_switch else None)

                physical = build_physical(control_kind)
                candidate = {'artifact': artifact, 'task_source': task_source, 'source': source,
                    'controller': physical.controllers[0], 'solution': None,
                    **({'solution_factory': lambda: PickCubeReadinessSolution(config=readiness),
                        'solution_identity': solution_identity, 'readiness': readiness,
                        '_physical_controller_factory': build_physical} if reset_switch else {}),
                    'physical_execution': physical,
                    'construction_id': 'pickcube-mjcf-physical-candidate-v1',
                    'source_revision': revision, 'source_sha256': {
                        'original_closure': original.source_closure_digest,
                        'projected_closure': closure},
                    'resolved_configuration': {'provider': provider, 'backend': backend,
                        'finger_initial_position_m': float(legacy_artifact.initialization.joint_position['panda-v1/finger_joint1']),
                        'drive_mode': 'effort-only' if native_drive == 'disabled' else 'coexist',
                        'control_kind': control_kind,
                        **({'task_com_force_v1': {'cube_force_z_N': cube_force_z_N}}
                           if cube_force_z_N is not None else {}),
                        'original_closure': original.source_closure_digest,
                        'projected_closure': closure, 'physical_binding': physical.compiled.binding.identity_hash}}
                reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=actual_seed)
                prepared_value = candidate
                return {**candidate, 'reset_plan': reset_plan}
        task_source, source, artifact = (prepared_value[key] for key in ('task_source', 'source', 'artifact'))
        reset_plan = sample_episode_reset_plan(task_source, source.scene_definition, artifact, task_seed=actual_seed)
        return {**prepared_value, 'reset_plan': reset_plan}

    return ReferenceTaskBinding(build=build,
        **physical_task_binding_fields(task_config=task_config, lift_height_m=lift_height_m,
            hand_frame_id='hand', cube_force_z_N=cube_force_z_N),
        action_schema=None, action_space_factory=None,
        external_solution_actions=reset_switch,
        validate_external_solution=_validate_external_readiness_solution if reset_switch else None,
        position_execution_info=physical_execution_info if reset_switch else None,
        position_execution_info_key='pickcube_position_execution_info_v1' if reset_switch else None,
        physical_reset_action_schema=panda_reset_action_schema if reset_switch else None,
        physical_reset_selection_factory=(lambda value: PhysicalResetSelection(
            value['_physical_controller_factory'], initial_kind=control_kind,
            allowed_kinds=PANDA_SWITCHABLE_EFFORT_KINDS, space_policy=space_policy,
            declaration=value['physical_execution'])) if reset_switch else None,
        physical_action_observer=observe_physical_action if reset_switch else None)
