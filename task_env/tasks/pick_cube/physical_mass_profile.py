"""Versioned source-specific nominal mass model for bounded PickCube fixtures."""
from pathlib import Path
import hashlib
import json

from ...controllers.canonical.mass_matrix_effort import build_mass_effort_execution

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
    return build_mass_effort_execution(
        direct_execution, matrix=model['matrices'][family],
        nominal_position=model['nominal_position'], max_abs_deviation=model['max_abs_deviation'],
        model_sha256=_MODEL_SHA256, use_pose_reference=kind == 'r3-mass-pose',
        r3_reference=r3_reference, end_frame_id=end_frame_id)
