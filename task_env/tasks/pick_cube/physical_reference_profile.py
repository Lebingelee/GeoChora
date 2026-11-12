"""Task-declared inputs for Panda reference effort Controllers."""
from pathlib import Path
import hashlib
import json
import math

_MODEL_PATH = Path(__file__).with_name('assets') / 'v211_4b_nominal_reduced_mass.json'
_MODEL_SHA256 = '6d2770cafd825586f99db600dde0afa630667c4cf061987f0800371c96252e65'


def load_pickcube_mass_effort_model(execution, artifact, source, *, kind):
    if kind not in {'joint-mass', 'r3-mass-pose'}:
        raise ValueError('unsupported bounded mass-model controller kind')
    binding = execution.compiled.binding
    if (binding.artifact_sha256 != artifact.identity_hash or binding.source_id != source.source_id
            or binding.source_closure_sha256 != source.source_closure_digest
            or not binding.channels or any(channel.native_drive != 'disabled' for channel in binding.channels)):
        raise ValueError('nominal mass model requires its source-bound isolated Controller')
    raw = _MODEL_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _MODEL_SHA256:
        raise ValueError('nominal mass model bytes changed')
    model = json.loads(raw)
    families = [family for family, closure in model['source_closures'].items()
                if closure == source.source_closure_digest]
    if model.get('schema_version') != 'panda-pickcube-nominal-reduced-mass-v1' or len(families) != 1:
        raise ValueError('nominal mass model source differs from its declared closure')
    family = families[0]
    joints = artifact.initialization.joint_position
    initial = tuple(float(joints[f'panda-v1/joint{i}']) for i in range(1, 8)) + (
        .5 * (float(joints['panda-v1/finger_joint1']) + float(joints['panda-v1/finger_joint2'])),)
    nominal, radius = model['nominal_position'], model['max_abs_deviation']
    if (len(nominal) != len(initial) or len(radius) != len(initial)
            or any(not math.isfinite(value) or abs(value - center) > bound
                   for value, center, bound in zip(initial, nominal, radius, strict=True))):
        from ...environment.types import StageUnavailableError
        raise StageUnavailableError('nominal mass model does not cover the declared initial state')
    return dict(matrix=model['matrices'][family], nominal_position=model['nominal_position'],
                max_abs_deviation=model['max_abs_deviation'], model_sha256=_MODEL_SHA256)


def build_pickcube_effort_profile(direct_execution, artifact, source, *, kind, config,
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
        mass_model = load_pickcube_mass_effort_model(direct_execution, artifact, source, kind=kind)
    return build_panda_effort_profile(direct_execution, kind=kind,
        cadence_s=artifact.timebase.control_dt, end_frame_id=end_frame_id,
        model=model, config=config, artifact_hash=artifact.identity_hash,
        r3_profile=r3_profile, joint_velocity_limit_rad_s=velocity_limit,
        mass_model=mass_model, dynamic_parameters=dynamic_parameters)
