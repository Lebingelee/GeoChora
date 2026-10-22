"""Build the explicit, non-frozen Scene-v3 candidate used by C02b-R1 S2."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import importlib

from task_env.artifacts import StateFieldRequirement, StateRequirements, Timebase
from task_env.controllers.canonical.contracts import digest
from task_env.controllers.canonical.production import ProductionCanonicalPandaController
from task_env.controllers.canonical.kinematics import (
    PANDA_HAND_ORIGIN_TCP_V1,
    PandaKinematics,
)
from task_env.diagnostics.tasks.test_phase_ii_c02a_controller_bindings import (
    ARM_COMPONENTS,
    GRIPPER_COMPONENTS,
)
from task_env.diagnostics.tasks.test_phase_ii_d01a_scene_materialization import (
    _a05_scene,
    _artifact_and_sample,
    _source_input,
)
from task_env.diagnostics.tasks.test_phase_ii_d01b_vnext_materialization import _task_source
from task_env.environment import compile_task_artifact_v1, sample_episode_reset_plan
from task_env.environment.types import ActionModeSpec
from task_env.runtime.sessions.control import (
    ControlBindingPlanV1,
    ControlGroupActionProjectionV1,
    ControllerBindingV1,
    compile_control_binding_plan,
)


R1_CANDIDATE_TASK_ID = 'phase-ii-c02b-r1-typed-force'
R1_CANDIDATE_VERSION = 'candidate-v1'
R1_CANDIDATE_SEED = 31
R1_WRITER_ID = 'panda-main/production-r1'
R1_GRIPPER_ID = 'panda-main/gripper'
R1_FORCE_ENTITY_ID = 'panda-main'
R1_FORCE_ACTUATOR_ID = 'actuator8'


def _feedback_requirements() -> StateRequirements:
    entity = R1_FORCE_ENTITY_ID
    requirements = [
        StateFieldRequirement(
            'state-field-requirement-v1', 'joint_position', 'joint', entity, joint,
            'required', 'evaluation_boundary', 'joint-definition', 'joint_state_query',
        )
        for joint in (
            'joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6', 'joint7',
            'finger_joint1', 'finger_joint2',
        )
    ]
    requirements.extend((
        StateFieldRequirement(
            'state-field-requirement-v1', 'frame_pose_world', 'frame', entity, 'hand',
            'required', 'evaluation_boundary', 'meter+quaternion_wxyz', 'frame_pose_query',
        ),
        StateFieldRequirement(
            'state-field-requirement-v1', 'actuator_force', 'actuator', entity,
            R1_FORCE_ACTUATOR_ID, 'required', 'evaluation_boundary', 'N',
            'actuator_force_query',
        ),
    ))
    return StateRequirements(
        'state-requirements-v1', 'controller', R1_WRITER_ID, tuple(requirements),
    )


def build_r1_force_candidate(workspace: Path | str):
    """Create new, source-bound candidate identities without editing A05 data."""
    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    scene = _a05_scene()
    legacy, _sample = _artifact_and_sample(scene)
    legacy = replace(
        legacy,
        artifact_id='phase-ii-c02b-r1-typed-force-v1',
        task_id=R1_CANDIDATE_TASK_ID,
        artifact_version=R1_CANDIDATE_VERSION,
        timebase=Timebase(0.002, 5, 0.01),
    )
    task_source = replace(
        _task_source(scene), task_id=legacy.task_id, version=legacy.artifact_version,
    )
    artifact = compile_task_artifact_v1(task_source, scene, legacy)
    reset_plan = sample_episode_reset_plan(
        task_source, scene, artifact, task_seed=R1_CANDIDATE_SEED,
    )
    source, imported, closure_digest, panda_digest, panda_file_count = _source_input(
        importlib.import_module('scene'), root / 'source-closure', scene, legacy,
    )
    if imported is None or len(closure_digest) != 64 or len(panda_digest) != 64:
        raise ValueError('R1 candidate source import/closure evidence is incomplete')
    source_config = replace(
        source.config,
        runtime=replace(source.config.runtime, control_substeps=5),
    )
    source = replace(
        source,
        task_artifact_hash=artifact.identity_hash,
        joint_targets={f'panda-main/joint{index}': f'actuator{index}' for index in range(1, 8)},
        open_actuators=(R1_FORCE_ACTUATOR_ID,),
        config=source_config,
        source_closure_digest=closure_digest,
    )

    model = PandaKinematics(
        source.scene_source.xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1,
    )
    controller = ProductionCanonicalPandaController(
        model,
        artifact_hash=artifact.identity_hash,
        config=source.config.action,
        gripper_config=source.config.robot.gripper,
        gripper_semantic_id=R1_GRIPPER_ID,
    )
    action_schema = ActionModeSpec.from_controller_config(SimpleNamespace(
        kind='absolute_pose', reference='world',
        rotation_representation='quaternion_wxyz',
    ))
    binding = ControllerBindingV1(
        'controller-binding-v1',
        R1_WRITER_ID,
        action_schema,
        'canonical-control-feedback',
        'canonical-control-feedback-v0',
        _feedback_requirements(),
        (
            ControlGroupActionProjectionV1(
                'control-group-action-projection-v1', 'panda-main', 'arm', ARM_COMPONENTS,
            ),
            ControlGroupActionProjectionV1(
                'control-group-action-projection-v1', 'panda-main', 'gripper', GRIPPER_COMPONENTS,
            ),
        ),
        controller.identity,
        digest({
            'schema': 'panda-r1-source-kinematics-v1',
            'source_xml_sha256': model.source_sha256,
            'tcp_profile_identity_hash': model.tcp_profile.identity_hash,
        }),
    )
    plan = compile_control_binding_plan(
        scene, (binding,), artifact_identity_hash=artifact.identity_hash,
        source_closure_digest=source.source_closure_digest,
    )

    return SimpleNamespace(
        artifact=artifact,
        controller=controller,
        panda_digest=panda_digest,
        panda_file_count=panda_file_count,
        plan=plan,
        reset_plan=reset_plan,
        scene=scene,
        source=source,
        kinematics=model,
        task_source=task_source,
        writer_id=R1_WRITER_ID,
    )
