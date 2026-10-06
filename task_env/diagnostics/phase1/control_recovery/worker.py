"""Isolated R1 prerequisite routes only. No expert/C2 route."""
import traceback
from pathlib import Path
import numpy as np
from ....artifacts.execution import ResetSample
from ....controllers.canonical import ProductionCanonicalPandaController, RequestedAction, CanonicalControlTarget
from ....controllers.canonical.kinematics import ARM, FINGERS
from ....runtime.sessions.control import materialize_control, ControlBinding
from ..p1_2_runtime import execution, write_json
from ..control.spec import context, free_space_source
from ..control.worker import tick, positions, replay
from .spec import verify


def run(provider, route, oracle, output):
    spec, lock = verify(oracle)
    artifact, source, model, _ = context()
    sample = ResetSample.from_mapping(spec['samples'][0])
    original = sample.to_mapping()
    result = {'provider': provider, 'route': route, 'oracle_sha256': lock['sha256'], 'closed': False}
    session = None
    stage = 'materialization'
    try:
        session = materialize_control(artifact, execution(provider),
            source=free_space_source(source) if route in ('gripper', 'C1_A') else source,
            binding=ControlBinding('panda-v1/gripper', source.config.action.gripper_opening_range_m))
        session.reset(sample)
        state = session.snapshot()
        feedback = session.control_feedback(state)
        stage = route
        if route == 'gripper':
            controller = ProductionCanonicalPandaController.from_source(artifact, source)
            controller.reset(state, feedback)
            mirror = ProductionCanonicalPandaController.from_source(artifact, source)
            mirror.reset(state, feedback)
            trace, rows = [], []
            deterministic = True
            q = tuple(sample.joint_position[n] for n in ARM)
            for phase, scalar in (('open', 1.), ('close', -1.), ('reopen', 1.)):
                first_close = None
                activations = []
                for phase_tick in range(1, spec['gripper'][phase + '_ticks'] + 1):
                    before = state
                    input_feedback = feedback
                    request = RequestedAction('absolute_joint', None, 'none', q + (scalar,))
                    canonical, target = controller.compute(state, feedback, request)
                    repeated = mirror.compute(state, feedback, request)
                    deterministic &= repeated == (canonical, target) and mirror.memory() == controller.memory()
                    memory = controller.memory()
                    state, row = tick(session, artifact, target, request, canonical)
                    feedback = session.control_feedback(state)
                    feedback.require_state(state, 'panda-v1/gripper', FINGERS)
                    row.update(phase=phase, phase_tick=phase_tick, input_state=before.to_mapping(),
                        canonical_control_feedback=input_feedback.to_mapping(), post_control_feedback=feedback.to_mapping(),
                        desired_opening_m=memory.desired_opening_m, commanded_opening_m=memory.commanded_opening_m,
                        servo_opening_m=target.gripper.servo_opening_m, force_limit_N=memory.force_limit_N,
                        measured_closing_force_N=input_feedback.gripper.closing_force_N,
                        force_mode_active=memory.force_mode_active, force_mode_initialized=memory.force_mode_initialized,
                        realized_opening_m=feedback.gripper.opening_m)
                    trace.append(row)
                    if phase == 'close' and feedback.gripper.opening_m <= spec['bounds']['gripper_close_max_m'] and first_close is None:
                        first_close = phase_tick
                    if memory.force_mode_active:
                        activations.append(phase_tick)
                passed = feedback.gripper.opening_m <= spec['bounds']['gripper_close_max_m'] if phase == 'close' else feedback.gripper.opening_m >= spec['bounds']['gripper_open_min_m']
                rows.append({'phase': phase, 'ticks': phase_tick, 'opening_m': feedback.gripper.opening_m,
                    'first_close_tick': first_close, 'force_mode_first_tick': activations[0] if activations else None,
                    'force_mode_ticks': len(activations), 'pass': passed})
            result.update(rows=rows, deterministic_history_target=bool(deterministic),
                controller_identity=controller.identity, pass_all=all(r['pass'] for r in rows) and deterministic)
            result['pass'] = bool(result.pop('pass_all'))
            write_json(output.parent / 'trace.json', trace)
        elif route == 'C1_A':
            metrics, trace = replay(session, artifact, model, sample, spec['C1_A'], spec['bounds']['C1_A_joint_error'])
            result.update(metrics=metrics, **{'pass': metrics['pass']})
            write_json(output.parent / 'trace.json', trace)
        elif route == 'C1_B':
            metrics, trace = replay(session, artifact, model, sample, spec['C1_B'], spec['bounds']['C1_B_joint_error'], np.array(spec['C1_B_goal_world']))
            moving_end = metrics
            target = CanonicalControlTarget.from_mapping(spec['C1_B'][-1])
            frozen = target.to_mapping()
            final_q = np.array([target.arm_position[n] for n in ARM])
            checkpoints = []
            first_crossing = None
            for hold_tick in range(spec['C1_B_evaluation']['hold_ticks'] + 1):
                if hold_tick:
                    state, row = tick(session, artifact, target)
                    row.update(hold_tick=hold_tick, canonical_control_feedback=session.control_feedback(state).to_mapping())
                    trace.append(row)
                else:
                    state = session.snapshot()
                err = float(np.max(np.abs(positions(state) - final_q)))
                if err <= spec['bounds']['C1_B_joint_error'] and first_crossing is None:
                    first_crossing = hold_tick
                if hold_tick in (0, 5, 10, 20, 40, 80, spec['C1_B_evaluation']['hold_ticks']):
                    checkpoints.append({'hold_ticks': hold_tick, 'joint_error': err,
                        'EE_error_m': float(np.linalg.norm(np.array(state.pose_world['panda-v1/ee'].position) - model.pose(final_q).position)),
                        'velocity_norm': float(np.linalg.norm([state.joint_velocity[n] for n in ARM]))})
                if target.to_mapping() != frozen:
                    raise ValueError('hold target mutated')
            trajectory = np.array([[r['arm_joint_position'][n] for n in ARM] for r in trace])
            margin = min(float(np.min(trajectory - model.limits[:, 0])), float(np.min(model.limits[:, 1] - trajectory)))
            metrics = dict(moving_end, final_joint_error=err, final_joint=positions(state).tolist(),
                final_EE=list(state.pose_world['panda-v1/ee'].position), finite=bool(np.isfinite(trajectory).all()), joint_limit_margin=margin)
            metrics['pass'] = err <= spec['bounds']['C1_B_joint_error'] and metrics['finite'] and margin >= -spec['bounds']['joint_limit_slack'] and moving_end['correct_direction'] and moving_end['EE_progress'] and not moving_end['task_failure']
            result.update(metrics=metrics, moving_end=moving_end, checkpoints=checkpoints,
                first_below_bound_hold_tick=first_crossing, complete_hold_target_unchanged=target.to_mapping() == frozen,
                **{'pass': metrics['pass']})
            write_json(output.parent / 'trace.json', trace)
        else:
            raise ValueError('unsupported recovery route; C2 is outside R1')
        result['sample_unchanged'] = original == sample.to_mapping()
        result['pass'] &= result['sample_unchanged']
        if not result['pass']:
            result['first_boundary'] = stage
    except Exception as error:
        result.update({'pass': False, 'first_boundary': stage, 'error': str(error), 'traceback': traceback.format_exc()})
    finally:
        if session is not None:
            try:
                session.close()
                result['closed'] = True
            except Exception as error:
                result.update({'pass': False, 'close_error': str(error)})
    write_json(output, result)
