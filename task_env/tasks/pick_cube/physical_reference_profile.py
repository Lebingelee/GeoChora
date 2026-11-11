"""Task-declared inputs for Panda reference effort Controllers."""
from pathlib import Path
import hashlib
import json

_MODEL_PATH = Path(__file__).with_name('assets') / 'v211_4b_nominal_reduced_mass.json'
_MODEL_SHA256 = '6d2770cafd825586f99db600dde0afa630667c4cf061987f0800371c96252e65'


def load_pickcube_mass_effort_model(artifact, source, *, kind):
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
    return dict(matrix=model['matrices'][family], nominal_position=model['nominal_position'],
                max_abs_deviation=model['max_abs_deviation'], model_sha256=_MODEL_SHA256)


def build_pickcube_effort_profile(direct_execution, artifact, source, *, kind, position,
                                 model, end_frame_id, dynamic_parameters=None):
    """Supply the task's admitted reference inputs to the common Controller owner."""
    from ...controllers.canonical.r3_effort import build_panda_effort_profile

    if kind == 'direct':
        return direct_execution
    r3_profile = velocity_limit = mass_model = None
    if kind in {'r3-pose', 'r3-mass-pose'}:
        from .specialization import _r3_dynamic_profile, PICKCUBE_R3_CONTINUOUS_PROFILE_V1
        r3_profile, _ = _r3_dynamic_profile()
        velocity_limit = PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s']
    if kind in {'joint-mass', 'r3-mass-pose'}:
        mass_model = load_pickcube_mass_effort_model(artifact, source, kind=kind)
    return build_panda_effort_profile(direct_execution, kind=kind,
        cadence_s=artifact.timebase.control_dt, end_frame_id=end_frame_id,
        model=model, config=position.config, artifact_hash=artifact.identity_hash,
        r3_profile=r3_profile, joint_velocity_limit_rad_s=velocity_limit,
        mass_model=mass_model, dynamic_parameters=dynamic_parameters)
