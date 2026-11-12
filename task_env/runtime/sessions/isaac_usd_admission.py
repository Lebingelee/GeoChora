"""Exact admission of the reviewed Isaac USD delivery and Task binding.

No SDK is imported here; selection and materialization remain Runtime owners.
"""
from ...artifacts import ExecutionSpecV1
from .source import UsdRuntimeInputV1

F06_PICKCUBE_ISAAC_PROFILE = 'isaac-gpu-physx-pickcube-f06-v1'
_F06_DELIVERY_MANIFEST_SHA256_V1 = '6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2'
_F06_REPRESENTATION_V1 = 'isaacsim-6.2.0.0-pickcube-desktop-v1'
_F06_TASK_POLICY_SHA256_V1 = '153dc47bf2993efa78e1efe835eced90c82c80284aef8ec532495b2fa2ea4fcb'


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
            or manifest_sha256 != _F06_DELIVERY_MANIFEST_SHA256_V1
            or delivery.delivery.representation_id != _F06_REPRESENTATION_V1
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
