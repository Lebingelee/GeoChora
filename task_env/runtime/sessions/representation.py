"""Public scalar set/read calibration; exact native representation admission."""
import math
import numpy as np


def calibrate_timestep(scene, requested_dt):
    """Discriminate binary32/binary64 via independent public roundtrip probes.

    Python's float return type does not identify the native scalar. Unknown or
    ambiguous representations fail closed. This performs no simulation step.
    """
    probes = (0.1, 0.1 + 2.0**-30, 1.0 / 73.0)
    observations = []
    try:
        for value in probes:
            scene.set_timestep(value)
            observations.append(float(scene.get_timestep()))
    finally:
        scene.set_timestep(requested_dt)
    candidates = [name for name, dtype in [('binary32', np.float32), ('binary64', np.float64)]
                  if all(actual == float(dtype(value)) for value, actual in zip(probes, observations))]
    if len(candidates) != 1:
        raise ValueError('unknown/ambiguous public native timestep representation')
    evidence = {'native_scalar_representation': candidates[0],
                'derivation': 'independent public set_timestep/get_timestep roundtrip calibration',
                'calibration': [{'requested': v, 'native': n} for v, n in zip(probes, observations)]}
    return timestep_gate(requested_dt, scene.get_timestep(), evidence)


def timestep_gate(requested_dt, native_dt, representation):
    dtype = {'binary32': np.float32, 'binary64': np.float64}[representation['native_scalar_representation']]
    expected = float(dtype(requested_dt))
    return {**representation, 'requested_dt': float(requested_dt), 'native_dt': float(native_dt),
            'expected_native_dt': expected,
            'pass': bool(math.isfinite(native_dt) and requested_dt > 0 and float(native_dt) == expected)}
