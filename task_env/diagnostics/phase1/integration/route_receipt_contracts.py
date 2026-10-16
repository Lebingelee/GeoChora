"""Provider-free reusable checks for recorded reference-route receipts."""
import math


def validate_transition_boundaries(transitions, boundaries, *, control_dt, substeps):
    """Validate T transitions, T+1 clock boundaries, and optional native indices."""
    transition_count = len(transitions)
    if len(boundaries) != transition_count + 1:
        raise ValueError('recording must contain T transitions and T+1 boundaries')
    control_dt = float(control_dt)
    if not math.isfinite(control_dt) or control_dt <= 0:
        raise ValueError('control_dt must be finite and positive')
    if not isinstance(substeps, int) or substeps <= 0:
        raise ValueError('substeps must be a positive integer')
    for index, boundary in enumerate(boundaries):
        if int(boundary['control_step']) != index:
            raise ValueError(f'control-step boundary mismatch at {index}')
        observed = float(boundary['simulation_time'])
        if not math.isfinite(observed):
            raise ValueError(f'control-clock mismatch at boundary {index}')
        expected = index * control_dt
        tolerance = 8 * max(math.ulp(observed), math.ulp(expected), math.ulp(float(control_dt)))
        if abs(observed - expected) > tolerance:
            raise ValueError(f'control-clock mismatch at boundary {index}')
        native_step_index = boundary.get('native_step_index')
        if native_step_index is not None and int(native_step_index) != index * substeps:
            raise ValueError(f'native-step boundary mismatch at {index}')
    return transition_count


def validate_native_step_counts(task, provider, transition_count, counts, *, substeps):
    """Check public adapter counts, including PickCube's GeoPhys grouped step."""
    if task not in {'pickcube', 'nutassembly'} or provider not in {'geophys', 'mujoco'}:
        raise ValueError(f'unsupported route receipt scope: {task}/{provider}')
    expected_native = transition_count * substeps
    grouped_calls = int(counts.get('grouped_control_interval_calls', 0))
    grouped_substeps = int(counts.get('grouped_native_substeps_requested', 0))
    native_calls = int(counts.get('native_physics_step_calls', 0))
    if task == 'pickcube' and provider == 'geophys':
        valid = grouped_calls == transition_count and grouped_substeps == expected_native
    else:
        valid = native_calls == expected_native and grouped_calls == 0
    if not valid:
        raise ValueError(
            f'native-step count mismatch for {task}/{provider}: '
            f'expected {expected_native} native applications over {transition_count} transitions'
        )
    return expected_native
