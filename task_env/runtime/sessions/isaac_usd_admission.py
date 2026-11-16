"""Exact admission of the reviewed Isaac USD delivery and Task binding.

No SDK is imported here; selection and materialization remain Runtime owners.
"""
from ...artifacts import ExecutionSpecV1
from .source import UsdRuntimeInputV1

F06_PICKCUBE_ISAAC_PROFILE = 'isaac-gpu-physx-pickcube-f06-v1'
F06_PICKCUBE_CONTROLLER_PROFILE = 'r3_continuous_v1'
_F06_DELIVERY_MANIFEST_SHA256_V1 = '6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2'
_F06_REPRESENTATION_V1 = 'isaacsim-6.2.0.0-pickcube-desktop-v1'
_F06_ASSET_OBJECT_MANIFEST_SHA256_V1 = '40b0dd2226d49e22d8d4ad03de5440ea454bbb7d4b4e2eabea3abbe732565d3e'
_F06_ASSET_OBJECT_REPRESENTATION_V1 = 'isaacsim-6.2.0.0-pickcube-asset-object-v1'
_F06_TASK_POLICY_SHA256_V1 = '153dc47bf2993efa78e1efe835eced90c82c80284aef8ec532495b2fa2ea4fcb'


def f06_delivery_identity():
    """Return the exact reviewed delivery identity for bounded consumers."""
    return _F06_DELIVERY_MANIFEST_SHA256_V1, _F06_REPRESENTATION_V1


def f06_admitted_delivery_identities():
    """Return the exact reviewed desktop and asset-object manifest identities."""
    return {
        _F06_DELIVERY_MANIFEST_SHA256_V1: _F06_REPRESENTATION_V1,
        _F06_ASSET_OBJECT_MANIFEST_SHA256_V1: _F06_ASSET_OBJECT_REPRESENTATION_V1,
    }


def validate_f06_controller_profile(profile):
    """Admit the Controller profile frozen by the reviewed USD delivery."""
    if profile != F06_PICKCUBE_CONTROLLER_PROFILE:
        raise ValueError('F06 Isaac freezes the existing r3_continuous_v1 profile')


def f06_capability_manifest(artifact, capabilities):
    """Describe only the exact source-bound Isaac desktop adapter."""
    from ...artifacts import CapabilityClaim, ProviderCapabilityManifest
    import os

    names = sorted(capabilities)
    version = os.environ.get('GEOCHORA_SELECTED_ISAAC_VERSION', '6.2.0.0')
    if version not in {'6.1.0.0', '6.2.0.0'}:
        raise ValueError('F06 capability manifest requires an admitted Isaac release')
    return ProviderCapabilityManifest(
        'provider-capability-v0', 'isaacsim', version,
        'f06-pickcube-desktop-native-mimic-v1', 'cuda', F06_PICKCUBE_ISAAC_PROFILE,
        'none', 'best_effort',
        tuple(CapabilityClaim(name, 'implemented', 'F06-exact-PickCube-desktop-source-bound-cell')
              for name in names),
        ('rgb_camera', 'depth_camera', 'contact_detection', 'contact_impulse'),
        'bounded F06 PickCube Isaac desktop cell; no provider-wide qualification',
    )


def _validate_f06_isaac_delivery(delivery, manifest_sha256):
    """Keep the exact local delivery boundary in the provider admission owner."""
    if (delivery.manifest_bytes_sha256 != manifest_sha256
            or f06_admitted_delivery_identities().get(manifest_sha256) != delivery.delivery.representation_id
            or not delivery.locally_validated or delivery.source_verified):
        raise ValueError('F06 requires its exact locally validated, non-upstream Isaac desktop USD')

def load_f06_isaac_delivery(manifest_path):
    """Load and admit the reviewed desktop USD delivery before building a source."""
    from ...assembly.usd_delivery import load_usd_asset_delivery

    delivery = load_usd_asset_delivery(manifest_path)
    _validate_f06_isaac_delivery(delivery, delivery.manifest_bytes_sha256)
    return delivery

def f06_isaac_robot_geometry_root(delivery):
    """Locate the robot hierarchy within the admitted desktop delivery."""
    _validate_f06_isaac_delivery(delivery, delivery.manifest_bytes_sha256)
    return f'{delivery.delivery.entry_prim}/panda/Geometry'


def f06_construction_source_inventory(runtime_input, declared_sources, *, task_path, physical):
    """Add USD admission and control owners to a Task's declared source inventory."""
    from pathlib import Path
    from .provenance import construction_source_inventory

    root = Path(__file__).resolve().parents[3]
    sources = dict(declared_sources)
    if physical:
        sources.pop('task_env/controllers/canonical/position_profile.py', None)
    paths = [Path(task_path), root / 'task_env/runtime/sessions/source.py',
             root / 'task_env/runtime/sessions/api.py',
             root / 'task_env/controllers/canonical/kinematics.py', Path(__file__)]
    if physical:
        paths.extend((root / 'task_env/runtime/sessions/source_composition_adapters.py',
                      root / 'task_env/runtime/sessions/isaac_physical.py'))
    else:
        paths.append(root / 'task_env/controllers/canonical/position_profile.py')
    sources.update(construction_source_inventory(root, paths))
    delivery = runtime_input.runtime_source.scene_source.loaded_delivery
    sources['f06_delivery_source_entry_sha256'] = delivery.delivery.source_entry_sha256
    sources['f06_delivery_manifest_sha256'] = delivery.manifest_bytes_sha256
    return sources


def f06_construction_facts(runtime_input, declared_sources, *, task_path, physical,
                           resolved_config, fallback_config):
    """Project F06 source, configuration and identity facts for construction."""
    from dataclasses import asdict
    import hashlib
    import json

    config = asdict(fallback_config if resolved_config is None else resolved_config)
    # F06's frozen configuration identity predates this disabled option.
    if resolved_config is not None and not getattr(resolved_config, 'gravity_compensation', False):
        config.pop('gravity_compensation', None)
    config_sha = hashlib.sha256(json.dumps(
        config, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {
        **runtime_input.construction_identity_fields(),
        'runtime_config': config,
        'runtime_config_sha256': config_sha,
        'source_sha256': f06_construction_source_inventory(
            runtime_input, declared_sources, task_path=task_path, physical=physical),
        'f06_delivery_manifest_sha256': runtime_input.delivery_manifest_sha256,
    }


def _validate_usd_task_policy(input_v1, expected_sha256):
    """Verify a pinned task declaration before trusting its binding and limits."""
    from ...controllers.canonical.contracts import digest

    policy = input_v1.admission_policy
    if type(policy) is not dict:
        raise ValueError('USD task admission policy is missing or malformed')
    try:
        valid_identity = digest(policy) == expected_sha256
    except (TypeError, ValueError):
        valid_identity = False
    if not valid_identity:
        raise ValueError('USD task admission policy differs from the trusted policy identity')
    bindings = policy['bindings']
    source = input_v1.runtime_source
    if any(dict(getattr(source, name)) != bindings[name]
           for name in ('joints', 'joint_targets', 'bodies', 'frames', 'free_joints')):
        raise ValueError('USD RuntimeSource differs from its exact task binding map')
    if (input_v1.controller_profile != policy['controller_profile']
            or type(input_v1.horizon) is not int
            or not policy['horizon_min'] <= input_v1.horizon <= policy['horizon_max']):
        raise ValueError('USD task requires its frozen controller and horizon limit')

def _validate_exact_admission_binding(input_v1, artifact, execution, source, message):
    input_v1.validate()
    if (artifact is not input_v1.artifact or source is not input_v1.runtime_source
            or type(execution) is not ExecutionSpecV1
            or execution.identity_hash != input_v1.execution.identity_hash):
        raise ValueError(message)

def _validate_f06_pickcube_isaac_input(input_v1, artifact, execution, source) -> None:
    """Admit the exact locally validated PickCube desktop USD F06 input."""
    if type(input_v1) is not UsdRuntimeInputV1:
        raise TypeError('F06 Isaac materialization requires its exact PickCube RuntimeInputV1')
    _validate_exact_admission_binding(input_v1, artifact, execution, source,
                                      'F06 materialization differs from its exact Task/Scene/Execution identities')
    if input_v1.schema_version != 'pick-cube-isaac-runtime-input-v1':
        raise ValueError('unsupported PickCube Isaac RuntimeInput schema')
    delivery = input_v1.runtime_source.scene_source.loaded_delivery
    _validate_f06_isaac_delivery(delivery, input_v1.delivery_manifest_sha256)
    _validate_usd_task_policy(input_v1, _F06_TASK_POLICY_SHA256_V1)
    if (input_v1.execution.physics_provider, input_v1.execution.physics_backend,
            input_v1.execution.physics_profile, input_v1.execution.physics_device,
            input_v1.execution.provider_seed, input_v1.execution.determinism_mode) != (
            "isaacsim", "cuda", F06_PICKCUBE_ISAAC_PROFILE, "cuda:0",
            input_v1.reset_plan.reset_sample.task_seed, "best_effort"):
        raise ValueError("F06 ExecutionSpec differs from its frozen Isaac provider/seed profile")


    if (execution.physics_provider, execution.physics_backend, execution.physics_device,
            execution.physics_profile, execution.determinism_mode) != (
            'isaacsim', 'cuda', 'cuda:0', F06_PICKCUBE_ISAAC_PROFILE, 'best_effort'):
        raise ValueError('unsupported F06 PickCube Isaac CUDA/PhysX execution intersection')
    representation = source.scene_source.representation
    if (representation.provider, representation.provider_build_identity,
            representation.representation_format, representation.runtime_admitted,
            representation.source_verified, source.scene_source.locally_validated,
            source.scene_source.source_verified) != (
            'isaacsim', 'isaacsim-6.2.0.0', 'usd', False, False, True, False):
        raise ValueError('F06 admission requires its exact locally validated non-upstream USD')
    if (source.scene_source.loaded_delivery.manifest_bytes_sha256
            != input_v1.delivery_manifest_sha256
            or dict(source.joints) != dict(source.joint_targets)):
        raise ValueError('F06 delivery or exact PickCube source Joint identity changed')
    if execution.render_default.provider != 'none' or execution.camera_overrides:
        raise ValueError('F06 Core cell is state-only and does not admit a renderer')


def isaac_cuda_execution_spec(*, profile, seed):
    """Declare the admitted single-session Isaac execution defaults."""
    from ...artifacts import RendererSelectionV1

    return ExecutionSpecV1(
        'execution-spec-v1', 'isaacsim', 'cuda', profile, seed, 'best_effort',
        RendererSelectionV1('renderer-selection-v1', 'none', 'cpu', 'none', None),
        physics_device='cuda:0', camera_overrides=())

def build_usd_task_runtime_input(*, schema_version, task_source, artifact, source,
                                 execution, reset_plan, controller_profile,
                                 horizon, horizon_min, horizon_max):
    """Build source-bound USD admission inputs from the actual Runtime mappings."""
    policy = {
        'schema_version': 'usd-task-admission-policy-v1',
        'bindings': {name: dict(getattr(source, name))
                     for name in ('joints', 'joint_targets', 'bodies', 'frames', 'free_joints')},
        'controller_profile': controller_profile,
        'horizon_min': horizon_min, 'horizon_max': horizon_max,
    }
    return UsdRuntimeInputV1(schema_version, task_source, artifact, source, execution,
        reset_plan, controller_profile, horizon,
        source.scene_source.loaded_delivery.manifest_bytes_sha256, policy)

def compile_usd_task_runtime_input(*, loaded, task_source, artifact, scene, options,
                                   joints, bodies, frames, free_joints, seed, horizon,
                                   schema_version, profile, controller_profile,
                                   horizon_min, horizon_max, provider_build_identity):
    """Compile a USD delivery and reset into a source-bound input.

    The task supplies its scene and semantic mappings; the provider owner
    controls delivery admission, native representation and execution profile.
    """
    from ...environment.task_source import sample_episode_reset_plan
    from .source import build_usd_runtime_source

    source = build_usd_runtime_source(
        loaded=loaded, provider='isaacsim', provider_build_identity=provider_build_identity,
        options=options, task_source_identity_sha256=task_source.identity_hash,
        artifact=artifact, scene=scene, joints=joints, bodies=bodies, frames=frames,
        free_joints=free_joints, joint_targets=joints)
    reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=seed)
    execution = isaac_cuda_execution_spec(profile=profile, seed=seed)
    return build_usd_task_runtime_input(
        schema_version=schema_version, task_source=task_source,
        artifact=artifact, source=source, execution=execution, reset_plan=reset_plan,
        controller_profile=controller_profile, horizon=horizon,
        horizon_min=horizon_min, horizon_max=horizon_max)


def build_f06_task_scene(task_config, *, robot, build_task_scene):
    """Project the exact F06 Panda source identity into the Task's scene declaration."""
    from ...artifacts import AssetDefinition
    from .source_scene_import import declare_panda_scene

    panda = declare_panda_scene(robot, entity_id='panda-v1',
                                scene_id=str(task_config['recipe']['scene_uid']))
    source_asset = panda.assets[0]
    if not source_asset.source_content_sha256:
        raise ValueError('Panda importer must provide the consumed source closure digest')
    asset = AssetDefinition('asset-definition-v1',
        'f05-dg03-menagerie-panda-source-preserving-isaac-usd', 'f05-dg03-isaac-usd-v4',
        source_asset.source_reference, source_asset.source_revision,
        source_asset.source_content_sha256, license_id='bsd-3-clause')
    return build_task_scene(task_config, robot_scene=panda, robot_asset=asset,
                            ee_frame='ee', cube_frame='cube', cube_joint='cube_freejoint',
                            table_frame='top')


def prepare_f06_task_delivery(delivery_manifest, *, seed, horizon, physical_drive):
    """Validate the exact F06 request before Task/Robot source construction."""
    from pathlib import Path

    if type(seed) is not int or seed < 0:
        raise ValueError('F06 PickCube task_seed must be a nonnegative integer')
    if type(horizon) is not int or not 1 <= horizon <= 1000:
        raise ValueError('F06 PickCube horizon must be an integer in [1, 1000]')
    if physical_drive not in (None, 'position', 'disabled'):
        raise ValueError('F06 physical drive must select position or disabled')
    loaded = load_f06_isaac_delivery(Path(delivery_manifest).resolve(strict=True))
    variant = (None if physical_drive is None else
        'pickcube-f06-physical-effort-fixture-v1' if physical_drive == 'position' else
        'pickcube-f06-physical-effort-no-drive-v1')
    return loaded, variant


def compile_f06_task_input(*, delivery_manifest, task_config, legacy_artifact, robot,
                           build_task_scene, compile_task_artifact, task_scene_recipe_sha256,
                           seed, horizon, physical_drive):
    """Admit the delivery and lower Task/Robot declarations to the exact USD input."""
    from dataclasses import replace
    from ...artifacts import FrameReference
    from .source import bind_declared_usd_paths

    loaded, variant = prepare_f06_task_delivery(
        delivery_manifest, seed=seed, horizon=horizon, physical_drive=physical_drive)
    if variant is not None:
        legacy_artifact = replace(legacy_artifact, artifact_id=variant)
    scene = build_f06_task_scene(task_config, robot=robot, build_task_scene=build_task_scene)
    task_source, artifact = compile_task_artifact(task_config, scene, legacy_artifact,
        frame_bindings={'panda-v1/base': FrameReference('panda-v1', 'link0'),
                        'panda-v1/ee': FrameReference('panda-v1', 'ee')}, cube_frame='cube')
    options = {'f06_goal': 'PickCube-Harness-three-backend-example',
               'lowering': 'pickcube-desktop-physx-native-mimic-v1',
               'delivery_manifest_sha256': loaded.manifest_bytes_sha256,
               'task_scene_recipe_sha256': task_scene_recipe_sha256}
    joints, bodies, frames, free_joints = bind_declared_usd_paths(
        scene, artifact, robot_uid=robot.uid,
        geometry_root=f06_isaac_robot_geometry_root(loaded),
        entry_prim=loaded.delivery.entry_prim,
        base_semantic='panda-v1/base',
        robot_frames={'panda-v1/ee': robot.reference_frame_parents()['ee']},
        world_bodies={'cube-v1': 'cube_v1'},
        world_frames={'tabletop-v1/top': 'tabletop_v1/top'},
        free_body_semantics=('cube-v1',))
    result = compile_usd_task_runtime_input(
        loaded=loaded, task_source=task_source, artifact=artifact, scene=scene,
        options=options, joints=joints, bodies=bodies, frames=frames, free_joints=free_joints,
        seed=seed, horizon=horizon, schema_version='pick-cube-isaac-runtime-input-v1',
        profile=F06_PICKCUBE_ISAAC_PROFILE, controller_profile=F06_PICKCUBE_CONTROLLER_PROFILE,
        horizon_min=1, horizon_max=1000, provider_build_identity='isaacsim-6.2.0.0')
    _validate_f06_pickcube_isaac_input(result, artifact, result.execution, result.runtime_source)
    return result
