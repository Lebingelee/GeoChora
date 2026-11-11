"""Source admission for the bounded PickCube USD Panda effort profile."""
from __future__ import annotations


def build_f06_direct_effort_execution(scene, artifact, source):
    """Admit the source-specific drive and mimic facts for the Panda owner."""
    from ...runtime.sessions.source import (
        UsdRuntimeSourceV1, position_joint_bindings_from_artifact,
        position_frame_bindings_from_artifact,
    )
    from ...robots.panda import PandaAgent, PandaEffortSourceLayout, build_panda_direct_effort_execution

    if type(source) is not UsdRuntimeSourceV1:
        raise TypeError('F06 physical profile requires its exact USD RuntimeSource')
    source.validate()
    if (source.source_closure_digest != 'dc2a87a74963e0ec10f3cf98b3e33cc87226350dde78aeddbc88244a0fbdafc6'
            or source.task_artifact.identity_hash != artifact.identity_hash
            or source.scene_definition.identity_hash != scene.identity_hash):
        raise ValueError('F06 physical profile requires the frozen source and Artifact')
    names = PandaAgent.physical_joint_names()
    layout = PandaEffortSourceLayout(
        tuple(name if i < 7 else 'finger_joint1' for i, name in enumerate(names)),
        tuple(f'f06-arm-{i+1}' if i < 7 else 'f06-mimic-pair' for i in range(9)),
        'f06-panda-direct-effort-assembly', 'f06-panda-direct-effort-components',
        'f06-direct-effort-zero-bias-v1', 'finger-pair-effort')
    native_drive = ('disabled' if artifact.artifact_id == 'pickcube-f06-physical-effort-no-drive-v1' else 'position')
    return build_panda_direct_effort_execution(
        scene, artifact, source, entity_id='panda-v1', native_drive=native_drive,
        native_ranges=((-250., 250.),) * 7 + ((-5., 5.),), layout=layout,
        joint_bindings=position_joint_bindings_from_artifact(scene, artifact, source),
        frame_bindings=position_frame_bindings_from_artifact(artifact, source))
