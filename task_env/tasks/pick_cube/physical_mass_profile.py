"""Versioned source-specific nominal mass model for bounded PickCube fixtures."""
from dataclasses import replace
from pathlib import Path
import hashlib
import json

from ...artifacts.state import StateFieldRequirement, StateRequirements
from ...controllers.canonical.mass_matrix_effort import MassMatrixEffortControllerV1
from ...controllers.canonical.r3_effort import R3ReferenceEffortControllerV1

_MODEL_PATH = Path(__file__).with_name('assets') / 'v211_4b_nominal_reduced_mass.json'
_MODEL_SHA256 = '6d2770cafd825586f99db600dde0afa630667c4cf061987f0800371c96252e65'


def build_pickcube_mass_effort_execution(direct_execution, artifact, source, *, kind,
                                        r3_reference=None, end_frame_id='ee'):
    if kind not in {'joint-mass', 'r3-mass-pose'}:
        raise ValueError('unsupported bounded mass-model controller kind')
    expected = {
        'pickcube-mjcf-physical-effort-no-drive-v1': 'mjcf',
        'pickcube-f06-physical-effort-no-drive-v1': 'f06',
    }
    family = expected.get(artifact.artifact_id)
    if family is None:
        raise ValueError('nominal mass model is restricted to its versioned isolated fixture')
    raw = _MODEL_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _MODEL_SHA256:
        raise ValueError('nominal mass model bytes changed')
    model = json.loads(raw)
    if (model.get('schema_version') != 'panda-pickcube-nominal-reduced-mass-v1'
            or model['source_closures'][family] != source.source_closure_digest):
        raise ValueError('nominal mass model source differs from selected fixture')
    binding = direct_execution.compiled.binding
    cadence = direct_execution.controllers[0].model.requirement.cadence_s
    servo = MassMatrixEffortControllerV1(binding, matrix=model['matrices'][family],
        nominal_position=model['nominal_position'], max_abs_deviation=model['max_abs_deviation'],
        model_sha256=_MODEL_SHA256, cadence_s=cadence)
    requirements = direct_execution.requirements
    if kind == 'r3-mass-pose':
        from ...controllers.canonical.production_r3 import _ProductionR3ArmReference
        if not isinstance(r3_reference, _ProductionR3ArmReference):
            raise TypeError('mass pose control requires the existing production R3 reference')
        entity = binding.channels[0].entity_id
        field = StateFieldRequirement('state-field-requirement-v1', 'frame_pose_world', 'frame', entity,
            end_frame_id, 'required', 'evaluation_boundary', 'meter+quaternion_wxyz', 'frame_pose_query')
        requirements = StateRequirements('state-requirements-v1', 'controller', servo.writer_id,
                                          (*requirements.requirements, field))
        controller = R3ReferenceEffortControllerV1(r3_reference, servo, entity_id=entity,
                                                   end_frame_id=end_frame_id, opening_range_m=.08)
    else:
        controller = servo
    return replace(direct_execution, controllers=(controller,), requirements=requirements)
