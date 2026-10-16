"""Task-owned guarded V2/V5/R3 construction, without diagnostic/workspace inputs.

An execution policy selects the existing runner behavior, not task semantics.
No native runtime is loaded here. The runner owns session stepping, arm-ramp
installation, recording, diagnostic continuation and teardown.
"""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import yaml

from ...controllers.canonical.contracts import digest
from ...controllers.canonical.execution import StableArmTargetHold
from ...controllers.canonical.production_r3 import ProductionCanonicalPandaControllerR3
from .canonical_artifact import build_nominal_candidate
from .canonical_source import build_runtime_source
from .canonical_solution import CanonicalNutAssemblyConfig
from .guarded_authorization_candidate_v2 import NutAssemblyGuardedAuthorizationCandidateV2
from .reference_execution import ArmRampMemory, ReferenceExecutionController

CONSTRUCTION_ID = 'nutassembly-r5-v5-guarded-reference-construction-v1'
GUARDED_EXPERT = 'nutassembly-guarded-expert-execution-v1'
DIAGNOSTIC_OBSERVATION = 'nutassembly-diagnostic-outcome-observation-v1'
ARM_SCHEDULE = 'linear-native-ramp-after-lift-v2-public-ack-memory'
PROFILE_DIR = Path(__file__).resolve().parent / 'profiles'
ARTIFACT_HASHES = {
    50: '699fc9147a07cb76f40c48decfddc350ed0ad3688beebe8b0da5268374e881e9',
    100: '99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe',
    500: '908cd3c41b6c3391e81dda2415d691dea378c7dd10138dcf8e5ebc4293dfd9f4',
}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_reference(*, rate_hz=100, provider='mujoco', execution_policy=GUARDED_EXPERT):
    """Resolve the selected recipe from tracked package resources only.

    20Hz remains historical MuJoCo-only evidence, outside this common route.
    Diagnostic policy never changes the solution's strict expert gate.
    """
    if type(rate_hz) is not int or rate_hz not in ARTIFACT_HASHES:
        raise ValueError('selected NutAssembly rate must be 50, 100 or 500 Hz')
    if provider not in {'geophys', 'mujoco'}:
        raise ValueError('selected NutAssembly provider must be geophys or mujoco')
    if execution_policy not in {GUARDED_EXPERT, DIAGNOSTIC_OBSERVATION}:
        raise ValueError('unknown selected NutAssembly execution policy')
    profile_path = PROFILE_DIR / 'nutassembly-nominal-v2.json'
    dynamic_path = PROFILE_DIR / 'r5-controller-planner-reference.yaml'
    profile = json.loads(profile_path.read_text())
    dynamic = yaml.safe_load(dynamic_path.read_text())
    # The workspace path in the historical profile is metadata only. Never
    # resolve it: the selected dynamic profile has an explicit tracked owner.
    artifact = build_nominal_candidate('NA-TB' + str(rate_hz))
    if artifact.identity_hash != ARTIFACT_HASHES[rate_hz]:
        raise ValueError('selected NutAssembly Artifact identity mismatch')
    source = build_runtime_source(artifact)
    source = replace(source, config=replace(source.config,
        action=replace(source.config.action, **profile['controller'].get('action_overrides', {})),
        robot=replace(source.config.robot, gripper=replace(source.config.robot.gripper,
            **{**profile['controller'].get('gripper_overrides', {}), 'force_limit_N': 10.}))))
    contact_profile = None
    if provider == 'mujoco':
        # Preserve the authored NoSlip2 transformation, including XML encoding.
        contact_profile = json.loads((PROFILE_DIR / 'mujoco-noslip2-v1.json').read_text())
        if contact_profile['model_option_overrides'] != {'noslip_iterations': 2}:
            raise ValueError('selected MuJoCo NoSlip2 profile mismatch')
        xml = ET.fromstring(source.scene_source.xml)
        xml.find('option').set('noslip_iterations', '2')
        source = replace(source, scene_source=replace(source.scene_source,
            xml=ET.tostring(xml, encoding='unicode')))
    values = {**profile['solution']['config'], **dynamic['planner'],
              'grasp_offset': (0., 0., .045895)}
    config = CanonicalNutAssemblyConfig(**values)
    controller = ProductionCanonicalPandaControllerR3.from_source(artifact, source, profile=dynamic)
    holder = StableArmTargetHold(controller)
    solution = NutAssemblyGuardedAuthorizationCandidateV2(config=config,
        control_dt=artifact.timebase.control_dt, arm_hold=holder,
        physics_dt_s=artifact.timebase.physics_dt)
    base_controller_identity = controller.identity
    source_hash = _sha(Path(__file__))
    support_hash = _sha(Path(__file__).with_name('reference_execution.py'))
    controller.identity = digest({'construction_id': CONSTRUCTION_ID,
        'base_controller_identity': base_controller_identity,
        'solution_identity': solution.identity,
        'construction_source_sha256': source_hash, 'execution_support_sha256': support_hash,
        'cadence': 'native-gripper-500hz-v1', 'arm_schedule': ARM_SCHEDULE})
    policy = {'policy_id': execution_policy,
        'diagnostic_continuation': execution_policy == DIAGNOSTIC_OBSERVATION,
        'strict_expert_gate': 'unchanged', 'historical_failure_labels': 'preserved',
        'grants_full_expert_pass': False,
        'expert_completion_requires_original_gates': True,
        'outcome_oriented_proposal_enabled': False}
    source_ids = {'construction': source_hash, 'execution_support': support_hash,
        'asset_profile': _sha(profile_path), 'dynamic_profile': _sha(dynamic_path),
        'mujoco_contact_profile': _sha(PROFILE_DIR / 'mujoco-noslip2-v1.json')}
    for name in ('assets.py', 'canonical_artifact.py', 'canonical_source.py',
                 'canonical_reset.py', 'canonical_semantics.py', 'canonical_initialization.json',
                 'default.yaml', 'task.py', 'solution.py',
                 'canonical_solution.py', 'canonical_solution_v2.py', 'stable_grasp_candidate.py',
                 'clearance_candidate_v3.py', 'clearance_candidate_v5.py',
                 'guarded_authorization_candidate.py', 'guarded_authorization_candidate_v2.py'):
        source_ids[name] = _sha(Path(__file__).with_name(name))
    canonical_dir = Path(__file__).resolve().parents[2] / 'controllers' / 'canonical'
    for name in ('production_r3.py', 'production_r2.py', 'production.py', 'controller.py',
                 'gripper_execution.py', 'execution.py', 'readiness.py', 'kinematics.py'):
        source_ids['controllers/canonical/' + name] = _sha(canonical_dir / name)
    resolved = {'construction_id': CONSTRUCTION_ID, 'artifact': artifact.to_mapping(),
        'artifact_sha256': artifact.identity_hash, 'runtime_config': asdict(source.config),
        'solution_config': asdict(config),
        'solution_parameters': {name: getattr(solution, name) for name in
            ('version', 'outward_handle_offset_m', 'descend_endpoint_command_bias_m',
             'minimum_pose_wait_s', 'pose_window_s', 'pose_span_m', 'pose_speed_m_s',
             'postclose_hold_s', 'servo_height_compensation_m', 'stable_height_tolerance_m')},
        'dynamic_profile': dynamic,
        'physical_profile': controller.physical_profile,
        'resolved_controller_action': asdict(controller.config),
        'resolved_controller_gripper': asdict(controller.gripper_config),
        'r3_parameters': {name: getattr(controller, name) for name in
            ('feedforward_gain', 'position_feedback_s', 'rotation_feedback_s',
             'joint_velocity_limit_rad_s', 'reference_lead_limit_rad', 'inner_physics_dt_s',
             'dls_damping', 'rotation_row_weight', 'control_dt')},
        'base_controller_identity': base_controller_identity,
        'controller_identity': controller.identity, 'solution_identity': solution.identity,
        'guard_policy': solution.policy_mapping, 'execution_policy': policy,
        'arm_schedule': ARM_SCHEDULE, 'gripper_feedback_hz': 500,
        'contact_profile': 'MuJoCo NoSlip2' if provider == 'mujoco' else 'GeoPhys native Row-PGS',
        'source_xml_sha256': hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
        'source_sha256': source_ids, 'qualification': 'NOT_REQUALIFIED',
        'runtime_source_bindings': {name: dict(getattr(source, name)) for name in
            ('joints', 'bodies', 'frames', 'free_joints', 'joint_targets')},
        'runtime_open_actuators': list(source.open_actuators)}
    recipe_identity = digest(resolved)
    return {'construction_id': CONSTRUCTION_ID, 'artifact': artifact, 'source': source,
        'profile': profile, 'profile_path': str(profile_path), 'profile_sha256': source_ids['asset_profile'],
        'dynamic_profile': dynamic, 'dynamic_profile_path': str(dynamic_path),
        'dynamic_profile_sha256': source_ids['dynamic_profile'],
        'controller': ReferenceExecutionController(holder, artifact.timebase.control_dt),
        'controller_identity': controller.identity, 'solution': solution,
        'solution_identity': solution.identity, 'solution_config': config,
        'recipe': resolved, 'resolved_configuration': resolved, 'recipe_identity': recipe_identity,
        'close_authorization_policy': {**solution.policy_mapping, 'identity': solution.policy_identity},
        'allowed_close_authorization_guards': [solution.primary_guard_id, solution.alternative_guard_id],
        'execution_policy': policy, 'diagnostic_shadow_mode': policy['diagnostic_continuation'],
        '_arm_schedule_memory': ArmRampMemory(), '_diagnostic_case': 'arm_ramp_native_grip',
        '_execution_provider': provider, '_contact_profile': contact_profile}


__all__ = ['build_reference', 'GUARDED_EXPERT', 'DIAGNOSTIC_OBSERVATION']
