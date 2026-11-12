"""Capability dispatch for provider-owned Robot source composition."""
from __future__ import annotations

from dataclasses import dataclass, replace
from importlib import import_module
from typing import NamedTuple


class SourceCompositionCapabilityUnavailable(ValueError):
    """The selected provider/backend has no registered source composer."""


def robot_construction_source_paths(robot):
    """Combine Robot-owned source identity with its attachment admission owner."""
    from pathlib import Path

    paths = tuple(robot.construction_source_paths())
    if robot.source_recipe().mode == 'replace-task-subtree':
        from . import mujoco_attachment_admission
        paths = (*paths, Path(mujoco_attachment_admission.__file__).resolve())
    return paths


def apply_declared_provider_source_options(source_xml, *, provider, declarations):
    """Lower provider-owned source options before source snapshotting."""
    if provider == 'geophys':
        return source_xml, None
    if provider == 'mujoco':
        from .mujoco_composition import apply_declared_mjcf_contact_profile
        return apply_declared_mjcf_contact_profile(source_xml, declarations['mujoco'])
    raise ValueError('source options require an admitted MJCF provider')


def validate_effort_source_route(*, provider, backend, deployment, source_delivery_manifest,
                                 drive, kind, reset_selection):
    """Admit the source and reset capabilities before native materialization."""
    from ...controllers.canonical.r3_effort import PANDA_SWITCHABLE_EFFORT_KINDS

    if deployment != 'in_process':
        raise ValueError('physical profile currently requires explicit in_process execution')
    if (provider, backend) not in {('mujoco', 'cpu'), ('geophys', 'cpu'), ('isaacsim', 'cuda')}:
        raise ValueError('physical control requires an admitted CPU or Isaac CUDA route')
    if provider == 'isaacsim':
        if source_delivery_manifest is None:
            raise ValueError('Isaac physical control requires its USD delivery')
    elif source_delivery_manifest is not None:
        raise ValueError('MJCF physical profile does not consume a USD source delivery')
    if reset_selection and ((provider, backend) != ('mujoco', 'cpu') or drive != 'disabled'
                            or kind not in PANDA_SWITCHABLE_EFFORT_KINDS):
        raise ValueError('physical reset selection requires an isolated MuJoCo reference Controller')


def build_panda_direct_effort_execution(robot, scene, artifact, source, *, entity_id,
                                        native_drive, native_ranges, layout=None,
                                        joint_bindings=None, frame_bindings=None,
                                        gripper_force_limit_N=None):
    """Compile a source-admitted Panda declaration and bind its effort Controller."""
    import math
    from ...artifacts import FrameReference
    from ...controllers.canonical.r3_effort import build_panda_direct_effort_controller
    from .physical_control import build_declared_effort_execution
    from ...robots.panda import PandaEffortSourceLayout

    if native_drive not in {'position', 'disabled'}:
        raise ValueError('Panda effort profile requires a declared native drive mode')
    if gripper_force_limit_N is not None:
        if (native_drive != 'disabled' or type(gripper_force_limit_N) not in (int, float)
                or not math.isfinite(gripper_force_limit_N) or gripper_force_limit_N <= 0
                or len(native_ranges) != 8):
            raise ValueError('Panda gripper force limit requires a positive limit and isolated drives')
        native_ranges = (*native_ranges[:7], (-gripper_force_limit_N, gripper_force_limit_N))
    names = robot.physical_joint_names()
    definitions = {j.joint_id: j for a in scene.articulations or ()
                   if a.entity_id == entity_id for j in a.joints}
    if any(name not in definitions or source.joints.get(f'{entity_id}/{name}') != name for name in names):
        raise ValueError('Panda effort profile requires the exact nine named source joints')
    layout = robot.effort_source_layout() if layout is None else layout
    if not isinstance(layout, PandaEffortSourceLayout):
        raise TypeError('Panda effort construction requires a source layout')
    subject, declarations = robot.physical_subject_declaration(
        entity_id=entity_id, source_id=source.source_id,
        source_closure_sha256=source.source_closure_digest, native_ranges=native_ranges,
        native_drive=native_drive, native_actuators=layout.native_actuators,
        transmission_ids=layout.transmission_ids)

    def make_controller(binding, writer):
        return build_panda_direct_effort_controller(binding, writer, entity_id=entity_id,
            joint_names=names, cadence_s=artifact.timebase.control_dt,
            model_id=layout.model_id, finger_action_id=layout.finger_action_id)

    definitions_by_native = {j.joint_id: j for a in scene.articulations or ()
                             for j in a.joints if j.kind != 'fixed'}
    if joint_bindings is None:
        joint_bindings = {semantic: definitions_by_native[native]
                          for semantic, native in (*source.joints.items(), *source.free_joints.items())}
    if frame_bindings is None:
        frame_bindings = {name: (artifact.legacy_frame_bindings[name]
                                 if name in artifact.legacy_frame_bindings
                                 else FrameReference(*name.split('/', 1)))
                          for name in (*source.bodies, *source.frames)}
    return build_declared_effort_execution(scene=scene, artifact=artifact, source=source,
        subject=subject, declarations=declarations, assembly_id=layout.assembly_id,
        nested_component_id=layout.nested_component_id, controller_factory=make_controller,
        state_joint_names=names, joint_bindings=joint_bindings, frame_bindings=frame_bindings)


def build_panda_effort_execution(robot, scene, artifact, source, *, native_drive,
                                 gripper_force_limit_N=None):
    """Bind a Robot's effort channels using the source format's native facts."""
    from .source import RuntimeSource, UsdRuntimeSourceV1

    if isinstance(source, RuntimeSource):
        from .mujoco_composition import checked_panda_effort_source_limits
        limits = checked_panda_effort_source_limits(source, scene)
        return build_panda_direct_effort_execution(
            robot, scene, artifact, source, entity_id=robot.uid, native_drive=native_drive,
            native_ranges=tuple(limits), gripper_force_limit_N=gripper_force_limit_N)
    if isinstance(source, UsdRuntimeSourceV1):
        if gripper_force_limit_N is not None:
            raise ValueError('USD effort source does not admit a gripper force override')
        from .isaac_physical import build_isaac_panda_effort_execution
        return build_isaac_panda_effort_execution(robot, scene, artifact, source,
                                                  native_drive=native_drive)
    raise TypeError('Robot effort construction requires an admitted RuntimeSource')


def prepare_panda_source_effort_factory(robot, scene, artifact, source, *, native_drive,
                                        config, source_xml, end_frame_id, task_settings,
                                        dynamic_parameters=False, gripper_force_limit_N=None):
    """Compile one source-bound Robot and prepare fresh Controller selections."""
    from ...controllers.canonical.r3_effort import PandaEffortProfileFactory
    from .source import RuntimeSource, source_resource_receipt

    physical = build_panda_effort_execution(robot, scene, artifact, source,
        native_drive=native_drive, gripper_force_limit_N=gripper_force_limit_N)

    def validate_source():
        receipt = source_resource_receipt(source)
        if receipt is not None:
            receipt.validate_snapshot()
        if isinstance(source, RuntimeSource):
            from .mujoco_composition import checked_panda_effort_source_limits
            checked_panda_effort_source_limits(source, scene)
        else:
            source.scene_source.assert_fresh()
        physical.validate_source(scene=scene, artifact_sha256=artifact.identity_hash,
            source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)

    return PandaEffortProfileFactory(physical, cadence_s=artifact.timebase.control_dt,
        end_frame_id=end_frame_id, source_xml=source_xml, config=config,
        artifact_hash=artifact.identity_hash, task_settings=task_settings,
        validate_source=validate_source, dynamic_parameters=dynamic_parameters)


def build_panda_source_effort_profile(robot, scene, artifact, source, *, native_drive,
                                      kind, config, source_xml, end_frame_id,
                                      task_settings, dynamic_parameters=None,
                                      gripper_force_limit_N=None):
    """Build one Controller through the same source-bound factory."""
    factory = prepare_panda_source_effort_factory(robot, scene, artifact, source,
        native_drive=native_drive, config=config, source_xml=source_xml, end_frame_id=end_frame_id,
        task_settings=lambda _kind: task_settings, dynamic_parameters=dynamic_parameters is not None,
        gripper_force_limit_N=gripper_force_limit_N)
    return factory(kind, **(dynamic_parameters or {}))


def compile_panda_effort_selection(artifact, source, *, robot, composition,
                                   controller_profile, kind, **factory_options):
    """Compile an effort Controller from the complete, source-bound composition."""
    if (type(composition) is not DeclaredReferenceSource
            or composition.compiled.artifact is not artifact
            or composition.compiled.source is not source
            or composition.scene is None or composition.projected_xml is None):
        raise ValueError('effort Controller requires its exact composed source and Scene')
    frame_key = f'{robot.uid}/ee'
    if frame_key not in source.frames:
        raise ValueError('effort source does not bind the declared Robot end frame')
    scene, intent = composition.scene, composition.intent
    factory = prepare_panda_source_effort_factory(robot, scene, artifact, source,
        source_xml=composition.projected_xml, end_frame_id=source.frames[frame_key],
        config=source.config.action, **factory_options)
    execution = factory(kind)
    validate_effort_robot_intent(intent, source, execution,
                                 controller_profile=controller_profile)
    return factory, execution


def build_usd_panda_control(artifact, source, *, runtime_input, robot, controller_profile, action_config,
                            dynamic_profile, velocity_limit, tcp_profile,
                            physical_kind=None, native_drive=None, effort_settings=None):
    """Bind the selected Position or effort capability to the admitted USD source."""
    if runtime_input.runtime_source is not source or runtime_input.artifact is not artifact:
        raise ValueError('USD Controller input differs from the compiled Artifact or source')
    from ...artifacts import FrameReference
    frame_key = f'{robot.uid}/ee'
    frame = artifact.legacy_frame_bindings.get(frame_key)
    if (type(frame) is not FrameReference or frame.entity_id != robot.uid
            or frame_key not in source.frames):
        raise ValueError('USD Controller requires the Robot end frame bound by its Artifact and source')
    end_frame_id = frame.frame_id
    if physical_kind is None:
        if native_drive is not None or effort_settings is not None:
            raise ValueError('Position capability does not accept effort settings')
        from ...controllers.canonical.execution import build_reference_position_controller
        from .position_subject_binding import bind_position_subjects_to_runtime_input
        controller = build_reference_position_controller(artifact, source,
            profile_id=controller_profile, dynamic_profile=dynamic_profile,
            execution=runtime_input.execution, action_config=action_config,
            joint_velocity_limit_rad_s=velocity_limit, entity_id=robot.uid,
            hand_frame_id=end_frame_id, tcp_profile=tcp_profile)
        runtime_input = bind_position_subjects_to_runtime_input(
            runtime_input, robot, controller, entity_id=robot.uid, end_frame_id=end_frame_id)
        return runtime_input, controller, None
    if native_drive is None or effort_settings is None:
        raise ValueError('effort capability requires its drive and task settings')
    physical = build_panda_source_effort_profile(robot, source.scene_definition, artifact, source,
        native_drive=native_drive, kind=physical_kind, config=action_config,
        source_xml=source.scene_source.xml, end_frame_id=end_frame_id, task_settings=effort_settings)
    from .physical_control import PhysicalControlExecutionV1
    if type(physical) is not PhysicalControlExecutionV1 or len(physical.controllers) != 1:
        raise TypeError('USD effort capability must return one physical execution')
    return runtime_input, physical.controllers[0], physical


@dataclass(frozen=True)
class SourceCompositionAdapterV1:
    provider: str
    backend: str
    capability_id: str
    implementation_module: str
    implementation_name: str

    def compose_robot_source(self, *args, **kwargs):
        implementation = getattr(import_module(self.implementation_module),
                                 self.implementation_name)
        return implementation(*args, **kwargs)


_ROBOT_SOURCE_ADAPTERS = {
    ('geophys', 'cpu'): SourceCompositionAdapterV1(
        'geophys', 'cpu', 'reference-robot-source-composition-v1',
        'task_env.runtime.sessions.source_composition_adapters',
        'compose_reference_robot_source',
    ),
    ('mujoco', 'cpu'): SourceCompositionAdapterV1(
        'mujoco', 'cpu', 'robot-source-composition-v1',
        'task_env.runtime.sessions.mujoco_composition',
        'compose_robot_source',
    ),
}


def resolve_robot_source_adapter(provider, backend):
    """Resolve a real registered adapter before Task source construction begins."""
    if type(provider) is not str or type(backend) is not str:
        raise TypeError('provider and backend selectors must be strings')
    adapter = _ROBOT_SOURCE_ADAPTERS.get((provider, backend))
    if adapter is None:
        raise SourceCompositionCapabilityUnavailable(
            f'no Robot source-composition adapter is registered for '
            f'{provider!r}/{backend!r}'
        )
    return adapter


def _selected_robot_source_recipe(robot, controller_profile):
    """Resolve and admit the Robot's source recipe for the selected Controller."""
    profile_recipe = getattr(robot, 'source_recipe_for_profile', None)
    recipe = (profile_recipe(controller_profile) if controller_profile is not None and callable(profile_recipe)
              else robot.source_recipe())
    if controller_profile is not None and controller_profile not in recipe.control_profiles:
        raise ValueError('selected Robot does not declare this Controller profile')
    return recipe


def reference_task_source_robot(robot, controller_profile):
    """Select the Robot that can be built into the reference Task source."""
    recipe = _selected_robot_source_recipe(robot, controller_profile)
    return robot if recipe.mode == 'reference-task-source' else None


def prepare_robot_source_intent(source, *, robot, controller_profile, existing_robot_entity,
                                task_body_names, task_site_transfers):
    """Freeze and validate the Task/Robot request before source composition."""
    from ...assembly.source_composition import build_source_composition_intent_v1

    recipe = _selected_robot_source_recipe(robot, controller_profile)
    task_entities = tuple(entity for entity, _ in task_body_names)
    intent = build_source_composition_intent_v1(
        task_source=source, task_entity_ids=task_entities,
        existing_robot_entity_ids=(existing_robot_entity,), robot_recipe=recipe,
        task_site_transfers=task_site_transfers)
    validate_robot_source_request(source, robot=robot, composition_intent=intent,
        task_entities=task_entities, existing_robot_entity=existing_robot_entity,
        task_body_names=task_body_names, task_site_transfers=task_site_transfers,
        robot_recipe=recipe, controller_profile=controller_profile)
    return intent, recipe


def prepare_reference_task_robot_source(source, *, robot, controller_profile,
                                        existing_robot_entity, task_body_names,
                                        task_site_transfers, compile_declaration=None):
    """Freeze Robot intent, then bind an optional Task scene to the source."""
    intent, _recipe = prepare_robot_source_intent(source, robot=robot,
        controller_profile=controller_profile, existing_robot_entity=existing_robot_entity,
        task_body_names=task_body_names, task_site_transfers=task_site_transfers)
    if compile_declaration is None:
        return intent, None
    from .source import bind_reference_scene_source
    task_source, scene, artifact, bodies, frames = compile_declaration()
    bound, projected, closure = bind_reference_scene_source(
        source, artifact=artifact, scene=scene, bodies=bodies, frames=frames)
    return intent, (task_source, scene, artifact, bound, projected, closure)


class DeclaredReferenceSource(NamedTuple):
    """Source-stage result; no Task scratch fields are added to Runtime values."""
    compiled: object
    intent: object
    task_source: object = None
    scene: object = None
    projected_xml: str | None = None
    reset_plan: object = None


class PandaReferenceSourcePlan(NamedTuple):
    """Task-owned source inputs prepared before any native source is created."""
    task_config: dict
    config: object
    declaration: object
    artifact: object
    scene_recipe_sha256: str | None
    profile_source: object
    facts: object
    source_inventory: object = None


def compose_declared_reference_source(compiled, *, robot, controller_profile,
                                      existing_robot_entity, task_body_names,
                                      task_site_transfers, compile_declaration,
                                      reset_seed=None):
    """Compose the declared Robot before the shared Controller build stage."""
    intent, declaration = prepare_reference_task_robot_source(
        compiled.source, robot=robot, controller_profile=controller_profile,
        existing_robot_entity=existing_robot_entity, task_body_names=task_body_names,
        task_site_transfers=task_site_transfers, compile_declaration=compile_declaration)
    if declaration is None:
        return DeclaredReferenceSource(compiled, intent)
    task_source, scene, artifact, bound, projected, _closure = declaration
    reset_plan = None
    if reset_seed is not None:
        from ...environment.task_source import sample_episode_reset_plan
        reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=reset_seed)
    return DeclaredReferenceSource(replace(compiled, artifact=artifact, source=bound), intent,
                                   task_source, scene, projected, reset_plan)


def build_panda_reference_stages(*, source_format, backend, controller_profile,
                                 prepare_source, source_context, compile_control,
                                 robot_uid, task_source_path, task_source_paths,
                                 robot=None, delivery_manifest=None,
                                 build_task_scene=None, compile_task_artifact=None,
                                 resolved_config=None,
                                 physical_kind=None,
                                 native_drive=None, reset_selection=False, task_settings=None,
                                 existing_robot_entity=None, task_body_names=(),
                                 task_site_transfers=(), scene_compiler=None,
                                 force_limit_N=None, velocity_limit=None, tcp_profile=None):
    """Build one declared Panda route using the shared source-bound stages.

    Task callbacks produce task facts; this adapter owns source composition,
    native Controller selection and episode reset materialization.
    """
    from ...environment.reference_binding import SourceBoundTaskBuilder
    from ...assembly.compiler import CompiledReferenceTaskV1
    from pathlib import Path

    if Path(task_source_path).resolve() not in {Path(path).resolve() for path in task_source_paths}:
        raise ValueError('Task construction inventory must include its declared owner')
    physical = physical_kind is not None

    def compile_source(request):
        from ...registry import make_agent
        from .source import close_execution_source_on_failure

        selected = make_agent(robot_uid) if robot is None else robot
        if selected.uid != robot_uid:
            raise ValueError('selected Robot differs from the requested identity')
        reference = (reference_task_source_robot(selected, controller_profile)
                     if source_format == 'mjcf' and physical_kind is None else selected)
        plan = prepare_source(request, selected, reference)
        if type(plan) is not PandaReferenceSourcePlan:
            raise TypeError('Panda source preparation must return its declared source plan')
        if source_format == 'usd':
            from pathlib import Path
            from ...assembly.panda_box import panda_box_construction_source_paths
            from .isaac_usd_admission import compile_f06_task_input
            from .provenance import reference_source_inventory

            inventory = reference_source_inventory(Path(__file__).resolve().parents[3],
                task_paths=task_source_paths, asset_paths=panda_box_construction_source_paths(),
                robot=selected, provider=request.provider, profile_source=plan.profile_source)
            plan = plan._replace(source_inventory=inventory)
            runtime_input = compile_f06_task_input(
                delivery_manifest=delivery_manifest, legacy_artifact=plan.artifact, robot=selected,
                task_config=plan.task_config, build_task_scene=build_task_scene,
                compile_task_artifact=compile_task_artifact,
                task_scene_recipe_sha256=plan.scene_recipe_sha256,
                seed=request.seed, horizon=request.horizon, physical_drive=native_drive)
            compiled = CompiledReferenceTaskV1(runtime_input.artifact, runtime_input.runtime_source)
            with close_execution_source_on_failure(compiled.source):
                if compiled.artifact.timebase != plan.artifact.timebase:
                    raise ValueError('USD Artifact timebase differs from the Task readiness declaration')
                return compiled, source_context(plan, compiled, runtime_input, selected, reference)
        from ...assembly.panda_box import compile_panda_box_task
        output = compile_panda_box_task(plan.declaration, config=plan.config, artifact=plan.artifact,
                                        robot=reference, backend=request.backend, own_snapshot=True)
        compiled = CompiledReferenceTaskV1(output.artifact, output.source)
        with close_execution_source_on_failure(compiled.source):
            return compiled, source_context(plan, compiled, None, selected, reference)

    def finish_control(compiled, context, selection, request):
        """Combine Task semantics with the one source/Controller handoff."""
        if source_format == 'usd':
            from pathlib import Path
            from .isaac_usd_admission import f06_construction_facts
            from .provenance import construction_revision

            runtime_input, controller, execution = selection
            provider_facts = f06_construction_facts(runtime_input, context.source_sha256,
                task_path=task_source_path, physical=execution is not None,
                resolved_config=resolved_config, fallback_config=context.config)
            revision = construction_revision(Path(__file__).resolve().parents[3])
            value = {'robot': context.robot, 'artifact': runtime_input.artifact,
                     'source': runtime_input.runtime_source, 'controller': controller,
                     'solution': None, 'execution_spec_v1': runtime_input.execution,
                     'reset_plan': runtime_input.reset_plan,
                     'session_admission_input': runtime_input, 'source_revision': revision,
                     'source_sha256': provider_facts['source_sha256']}
            if execution is not None:
                value['physical_execution'] = execution
        elif physical:
            from pathlib import Path
            from .provenance import construction_revision

            factory, execution = selection
            source_sha256 = {
                'original_closure': context.composition.intent.task_source_closure_sha256,
                'projected_closure': compiled.source.source_closure_digest,
            }
            value = {'artifact': compiled.artifact, 'source': compiled.source,
                     'task_source': context.composition.task_source,
                     'controller': execution.controllers[0], 'solution': None,
                     'physical_execution': execution,
                     'source_revision': construction_revision(Path(__file__).resolve().parents[3]),
                     'source_sha256': source_sha256}
            if reset_selection:
                value['_physical_controller_factory'] = factory
        else:
            from dataclasses import asdict
            from pathlib import Path
            from ...assembly.compiler import reference_task_identity_fields
            from ...assembly.panda_box import panda_box_construction_source_paths
            from ...controllers.canonical.contracts import digest
            from ...controllers.canonical.execution import bind_reference_position_identity
            from .provenance import construction_revision, reference_source_inventory

            revision = construction_revision(Path(__file__).resolve().parents[3])
            source_ids = reference_source_inventory(Path(__file__).resolve().parents[3],
                task_paths=task_source_paths, asset_paths=panda_box_construction_source_paths(),
                robot=context.robot, provider=request.provider, controller=selection,
                profile_source=context.profile_source)
            value = {'artifact': compiled.artifact, 'source': compiled.source,
                     'controller': selection, 'solution': None,
                     'source_revision': revision, 'source_sha256': source_ids}
            if context.composition.reset_plan is not None:
                value['reset_plan'] = context.composition.reset_plan
        task_value = compile_control(compiled, context, selection, request)
        if value.keys() & task_value.keys():
            raise ValueError('Task construction conflicts with source or Controller ownership')
        if source_format == 'usd':
            from ...controllers.canonical.contracts import digest

            runtime_facts = {**provider_facts, 'source_revision': revision,
                             'controller_identity': controller.identity}
            task_facts = task_value.get('resolved_configuration', {})
            if runtime_facts.keys() & task_facts.keys():
                raise ValueError('Task configuration conflicts with Runtime construction facts')
            resolved = {**runtime_facts, **task_facts}
            task_value = {**task_value, 'resolved_configuration': resolved,
                          'recipe_identity': digest(resolved)}
        elif physical:
            runtime_facts = {'provider': request.provider, 'backend': request.backend,
                'source_composition_intent_v1_sha256': context.composition.intent.identity_hash,
                'drive_mode': 'effort-only' if native_drive == 'disabled' else 'coexist',
                'control_kind': physical_kind, **source_sha256,
                'physical_binding': execution.compiled.binding.identity_hash}
            task_facts = task_value.get('resolved_configuration', {})
            if runtime_facts.keys() & task_facts.keys():
                raise ValueError('Task configuration conflicts with Runtime construction facts')
            task_value = {**task_value, 'resolved_configuration': {**runtime_facts, **task_facts}}
        else:
            identity = bind_reference_position_identity(selection, profile_id=controller_profile,
                construction_id=task_value['construction_id'])
            runtime_facts = {
                'input_source_composition_intent_v1_sha256': context.composition.intent.identity_hash,
                'artifact': compiled.artifact.to_mapping(),
                **reference_task_identity_fields(compiled.artifact, compiled.source, selection),
                'resolved_controller_action': asdict(selection.config),
                'resolved_controller_gripper': asdict(selection.gripper_config),
                'source_revision': revision, 'source_sha256': source_ids, **identity,
            }
            task_facts = task_value.get('resolved_configuration', {})
            if runtime_facts.keys() & task_facts.keys():
                raise ValueError('Task configuration conflicts with Runtime construction facts')
            resolved = {**runtime_facts, **task_facts}
            task_value = {**task_value, 'resolved_configuration': resolved,
                          'recipe_identity': digest(resolved)}
        return {**value, **task_value}

    if source_format == 'usd':
        from .isaac_usd_admission import validate_f06_controller_profile
        validate_f06_controller_profile(controller_profile)
        return SourceBoundTaskBuilder(
            compile_source, None, backend='cuda', allow_sampled_reset=False,
            controller_factory=build_usd_panda_control,
            controller_options=lambda compiled, context, request: dict(
                runtime_input=context.runtime_input, robot=context.robot,
                controller_profile=controller_profile, action_config=context.action_config,
                dynamic_profile=context.dynamic_profile, velocity_limit=velocity_limit,
                tcp_profile=tcp_profile, physical_kind=physical_kind, native_drive=native_drive,
                effort_settings=task_settings(physical_kind) if physical_kind is not None else None),
            compile_control=finish_control)
    if source_format != 'mjcf':
        raise ValueError('Panda reference requires an admitted source format')
    def compose(compiled, context, request):
        reference_robot = getattr(context, 'reference_robot', context.robot)
        declaration = (None if reference_robot is None else
            lambda: scene_compiler(context.task_config, reference_robot, compiled.artifact))
        composition = compose_declared_reference_source(
            compiled, robot=context.robot, controller_profile=controller_profile,
            existing_robot_entity=existing_robot_entity, task_body_names=task_body_names,
            task_site_transfers=task_site_transfers, compile_declaration=declaration,
            reset_seed=None if physical else request.seed)
        return composition.compiled, context._replace(composition=composition)

    if physical:
        from ...environment.task_source import sample_episode_reset_plan
        return SourceBoundTaskBuilder(
            compile_source,
            lambda value, request: sample_episode_reset_plan(
                value['task_source'], value['source'].scene_definition,
                value['artifact'], task_seed=request.seed),
            backend=backend, reuse_source=True, allow_sampled_reset=False,
            source_composer=compose, controller_factory=compile_panda_effort_selection,
            controller_options=lambda compiled, context, request: dict(
                robot=context.robot, composition=context.composition,
                controller_profile=controller_profile, native_drive=native_drive,
                kind=physical_kind, task_settings=task_settings, dynamic_parameters=reset_selection,
                gripper_force_limit_N=(compiled.source.config.robot.gripper.force_limit_N
                                       if reset_selection else None)),
            compile_control=finish_control)
    from ...controllers.canonical.execution import build_reference_position_controller
    return SourceBoundTaskBuilder(
        compile_source, None, backend=backend, allow_sampled_reset=False,
        source_composer=compose, controller_factory=build_reference_position_controller,
        controller_options=lambda compiled, context, request: dict(
            profile_id=controller_profile, dynamic_profile=context.dynamic_profile,
            force_limit_N=force_limit_N, joint_velocity_limit_rad_s=velocity_limit),
        compile_control=finish_control)


def validate_effort_robot_intent(intent, source, execution, *, controller_profile):
    """Match source snapshot and compiled writer resources to the frozen request."""
    from ...assembly.source_composition import SourceCompositionIntentV1
    from .physical_control import PhysicalControlExecutionV1
    from .source import source_resource_receipt

    if type(intent) is not SourceCompositionIntentV1 or type(execution) is not PhysicalControlExecutionV1:
        raise TypeError('effort composition requires typed intent and physical execution')
    receipt = source_resource_receipt(source)
    if receipt is not None:
        if (receipt.source_id != intent.task_source_id
                or receipt.source_closure_digest != intent.task_source_closure_sha256):
            raise ValueError('effort source snapshot differs from the composition intent')
        receipt.validate_snapshot()
    elif (source.source_id != intent.task_source_id
          or source.source_closure_digest != intent.task_source_closure_sha256):
        raise ValueError('effort source differs from the composition intent')
    entities = {entity.entity_id for entity in execution.scene.entities}
    if entities != set(intent.task_entity_ids) | set(intent.existing_robot_entity_ids):
        raise ValueError('effort Scene ownership differs from the composition intent')
    subjects = execution.subjects
    if (len(subjects) != 1 or subjects[0].entity_id != intent.robot_uid
            or execution.selection_profile_id != controller_profile
            or controller_profile not in intent.control_profiles
            or tuple(channel.joint_id for channel in execution.compiled.binding.channels)
            != intent.controlled_joints):
        raise ValueError('effort subject or Controller differs from the composition intent')
    writers = {(channel.entity_id, channel.native_actuator, writer)
               for channel in execution.compiled.binding.channels for writer in channel.owner_ids}
    if writers != set(intent.resource_writers):
        raise ValueError('effort writer resources differ from the composition intent')


def declared_robot_source_composer(config, *, robot_uid, existing_robot_entity, task_body_names, task_site_transfers, robot=None):
    """Resolve the provider composer and bind the selected Robot per source."""
    from ...registry import AGENT_REGISTRY

    profile = config.controller_profile
    adapter = resolve_robot_source_adapter(config.physics_provider, config.environment.runtime.backend)
    task_entities = tuple(entity for entity, _ in task_body_names)

    def compose(source, *, artifact, controller):
        existing = tuple(robot for robot in getattr(source, 'agents', ()) if robot.uid == robot_uid)
        if len(existing) > 1:
            raise ValueError('Task source contains multiple Robots with the selected identity')
        selected = robot if robot is not None else (existing[0] if existing else AGENT_REGISTRY.create(robot_uid))
        if selected.uid != robot_uid or (existing and existing[0] is not selected):
            raise ValueError('Task source differs from the selected Robot declaration')
        intent, recipe = prepare_robot_source_intent(source, robot=selected,
            controller_profile=profile, existing_robot_entity=existing_robot_entity,
            task_body_names=task_body_names, task_site_transfers=task_site_transfers)
        return adapter.compose_robot_source(source, robot=selected, composition_intent=intent,
            artifact=artifact, controller=controller, robot_recipe=recipe,
            controller_profile=profile, task_entities=task_entities,
            existing_robot_entity=existing_robot_entity, task_body_names=task_body_names,
            task_site_transfers=task_site_transfers)

    return compose



def validate_robot_source_request(source, *, robot, composition_intent, task_entities,
                                  existing_robot_entity, task_body_names, task_site_transfers,
                                  robot_recipe, controller_profile):
    """Check the selected source, intent, and Robot recipe before composition."""
    from ...assembly.source_composition import SourceCompositionIntentV1
    from ...robots.source_recipe import RobotSourceRecipeV1
    from .source import RuntimeSource, UsdRuntimeSourceV1

    recipe_method = getattr(robot, 'source_recipe', None)
    profile_recipe = getattr(robot, 'source_recipe_for_profile', None)
    recipe = (profile_recipe(controller_profile) if controller_profile is not None and callable(profile_recipe)
              else recipe_method() if callable(recipe_method) else None)
    if type(recipe) is not RobotSourceRecipeV1 or (robot_recipe is not None and robot_recipe != recipe):
        raise ValueError('Robot composition requires the selected provider-neutral recipe')
    if type(composition_intent) is not SourceCompositionIntentV1:
        raise TypeError('Robot source requires a frozen composition intent')
    if type(source) not in (RuntimeSource, UsdRuntimeSourceV1):
        raise TypeError('Robot composition requires a typed RuntimeSource')
    if (type(task_entities) is not tuple or type(task_body_names) is not tuple
            or type(task_site_transfers) is not tuple or set(dict(task_body_names)) != set(task_entities)):
        raise ValueError('Task source roots must cover immutable Task entities')
    expected_mode = {'reference-task-source': 'reference',
                     'replace-task-subtree': 'replace', 'add-source': 'add'}[recipe.mode]
    if (composition_intent.task_source_id != source.source_id
            or composition_intent.task_source_closure_sha256 != source.source_closure_digest
            or composition_intent.task_entity_ids != task_entities
            or composition_intent.existing_robot_entity_ids != (existing_robot_entity,)
            or composition_intent.robot_uid != robot.uid
            or composition_intent.robot_recipe_sha256 != recipe.identity_hash
            or composition_intent.mode != expected_mode
            or composition_intent.task_site_transfers != task_site_transfers):
        raise ValueError('composition intent differs from Task/Robot declarations')
    if isinstance(source, UsdRuntimeSourceV1):
        source.scene_source.assert_fresh()
    elif source.execution_source_receipt is not None:
        source.execution_source_receipt.validate_snapshot()
    elif source.scene_definition is not None and recipe.mode == 'reference-task-source':
        from .source import verify_projected_scene_source
        verify_projected_scene_source(source.scene_source, source.scene_definition,
                                      source.source_closure_digest)
    else:
        raise TypeError('Robot composition requires a verified source snapshot')
    return recipe


def compose_reference_robot_source(source, *, robot, composition_intent, artifact, controller, task_entities,
                                   existing_robot_entity, task_body_names, task_site_transfers,
                                   robot_recipe=None, controller_profile=None):
    """Bind an existing Robot source with the shared source and Controller contract."""
    recipe = validate_robot_source_request(source, robot=robot, composition_intent=composition_intent,
        task_entities=task_entities, existing_robot_entity=existing_robot_entity,
        task_body_names=task_body_names, task_site_transfers=task_site_transfers,
        robot_recipe=robot_recipe, controller_profile=controller_profile)
    if recipe.mode != 'reference-task-source':
        raise ValueError('reference source requires the selected Robot reference recipe')
    return _compose_checked_reference_source(source, robot=robot, recipe=recipe,
        composition_intent=composition_intent, artifact=artifact, controller=controller,
        task_entities=task_entities, existing_robot_entity=existing_robot_entity)


def _compose_checked_reference_source(source, *, robot, recipe, composition_intent, artifact,
                                      controller, task_entities, existing_robot_entity):
    from dataclasses import replace
    from ...assembly.source_composition import (CompositionSourceV1, CompositionSourceV2,
        SourceCompositionPlanV1, SourceCompositionRequestV2)
    from .position_subject_binding import compile_reference_position_source
    position = compile_reference_position_source(
        robot, source, artifact=artifact, controller=controller,
        entity_id=existing_robot_entity, recipe=recipe)
    plan, subject_identity = position.plan, position.subject_identity_sha256
    legacy_task = CompositionSourceV1(source.source_id, source.source_closure_digest,
                                      (*task_entities, existing_robot_entity))
    legacy_robot = CompositionSourceV1(source.source_id, source.source_closure_digest,
                                       (existing_robot_entity,))
    legacy = SourceCompositionPlanV1(legacy_task, task_entities, (existing_robot_entity,),
        robot.uid, (legacy_robot,), 'reference', plan.assembly_identity_hash, None, (),
        plan.identity_hash, subject_identity, position_binding_identity_sha256=position.identity_hash)
    request = SourceCompositionRequestV2('source-composition-request-v2',
        CompositionSourceV2(source.source_id, source.source_closure_digest,
                             (*task_entities, existing_robot_entity)),
        task_entities, (existing_robot_entity,), robot.uid,
        (CompositionSourceV2(source.source_id, source.source_closure_digest,
                             (existing_robot_entity,)),), 'reference',
        plan.assembly_identity_hash,
        resource_writers=tuple(plan.resource_writers),
        intent_identity_sha256=composition_intent.identity_hash)
    if set(recipe.resource_writers) != set(request.resource_writers):
        raise ValueError('resolved Robot resource writers differ from its pre-parse recipe')
    return replace(source, position_subject_binding=position,
                   source_reference_plan=legacy, source_composition_request=request,
                   source_composition_intent=composition_intent)
