"""Explicit DG01 N0/N1 MuJoCo diagnostics through the frozen Core candidate."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _write_once(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def run_n0(output: Path):
    from task_env.runtime.sessions.api import materialize
    from task_env.tasks.position_candidate.builder import build_f05_dg01_mujoco_candidate

    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = _utc_now()
    candidate = build_f05_dg01_mujoco_candidate(output / 'candidate-build', horizon=300)
    session = None
    try:
        session = materialize(
            candidate.artifact, candidate.execution,
            source=candidate.source,
            _f05_dg01_mujoco_input=candidate.candidate_input,
        )
        model_receipt = getattr(session, '_f05_dg01_model_receipt', None)
        if not isinstance(model_receipt, dict):
            raise RuntimeError('DG01 Core Materialize returned without a public model receipt')
        if (getattr(session, '_native_steps', None) != 0
                or float(session._data.time) != 0.0
                or getattr(session, '_reset_done', None)):
            raise RuntimeError('N0 must end after model compile with zero reset, forward or physics steps')
        payload = {
            'schema_version': 'f05-dg01-n0-core-model-receipt-v1',
            'run_id': output.name,
            'started_utc': started,
            'finished_utc': _utc_now(),
            'native_invocations': 1,
            'physics_steps': 0,
            'physics_time_s': float(session._data.time),
            'reset_performed': False,
            'forward_calls': 0,
            'task_source_identity_sha256': candidate.task_source.identity_hash,
            'task_artifact_identity_sha256': candidate.artifact.identity_hash,
            'scene_identity_sha256': candidate.scene.identity_hash,
            'execution_identity_sha256': candidate.execution.identity_hash,
            'panda_source_closure_sha256': candidate.panda_closure_digest,
            'panda_source_file_count': candidate.panda_file_count,
            'derived_source_xml_sha256': candidate.derived_source_sha256,
            'runtime_source_closure_sha256': candidate.source_closure_digest,
            'task_scene_recipe_sha256': candidate.recipe_sha256,
            'model_receipt': model_receipt,
            'model_receipt_identity_sha256': model_receipt['identity_sha256'],
            'closed_at_zero_steps': False,
        }
    finally:
        if session is not None:
            session.close()
            if getattr(session, '_closed', False) is not True:
                raise RuntimeError('N0 RuntimeSession did not close')
        candidate.env.close()
    payload['closed_at_zero_steps'] = True
    _write_once(output / 'n0_model_receipt.json', payload)
    _write_once(output / 'n0_close_receipt.json', {
        'schema_version': 'f05-dg01-n0-close-receipt-v1',
        'run_id': output.name,
        'native_steps': 0,
        'physics_time_s': 0.0,
        'session_closed': True,
        'model_receipt_identity_sha256': payload['model_receipt_identity_sha256'],
    })
    return payload


def _write_jsonl(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        json.dump(payload, stream, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()


def _finger_addresses(model, mujoco):
    result = {}
    for name in ('finger_joint1', 'finger_joint2'):
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_id < 0:
            raise RuntimeError(f'exact DG01 model lacks {name}')
        result[name] = (
            int(model.jnt_qposadr[joint_id]), int(model.jnt_dofadr[joint_id]),
        )
    return result


def _set_finger_state(data, addresses, q, dq):
    for name, position, velocity in zip(
            ('finger_joint1', 'finger_joint2'), q, dq, strict=True):
        qpos_address, dof_address = addresses[name]
        data.qpos[qpos_address] = float(position)
        data.qvel[dof_address] = float(velocity)


def _actuator_joint_readback(model, data, mujoco, *, variant):
    actuator_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, 'actuator8')
    if actuator_id < 0:
        raise RuntimeError('exact DG01 model lacks actuator8')
    addresses = _finger_addresses(model, mujoco)
    dofs = [addresses[name][1] for name in ('finger_joint1', 'finger_joint2')]
    tendon_length = float(data.actuator_length[actuator_id])
    tendon_velocity = float(data.actuator_velocity[actuator_id])
    control = float(data.ctrl[actuator_id])
    gain = float(model.actuator_gainprm[actuator_id, 0])
    bias = [float(value) for value in model.actuator_biasprm[actuator_id, :3]]
    unclipped_scalar_force = gain * control + bias[0] + bias[1] * tendon_length + bias[2] * tendon_velocity
    scalar_force = float(data.actuator_force[actuator_id])
    row_start = int(data.moment_rowadr[actuator_id])
    row_count = int(data.moment_rownnz[actuator_id])
    row_columns = [int(value) for value in data.moment_colind[row_start:row_start + row_count]]
    row_values = [float(value) for value in data.actuator_moment[row_start:row_start + row_count]]
    sparse_moment = dict(zip(row_columns, row_values, strict=True))
    moment = [sparse_moment.get(dof, 0.0) for dof in dofs]
    projected_force = [float(data.qfrc_actuator[dof]) for dof in dofs]
    return {
        'variant': variant,
        'actuator_id': actuator_id,
        'control': control,
        'tendon_length_m': tendon_length,
        'tendon_velocity_m_s': tendon_velocity,
        'gain': gain,
        'bias_parameters': bias,
        'unclipped_scalar_force_N': unclipped_scalar_force,
        'compiled_scalar_force_N': scalar_force,
        'tendon_generalized_force_moment': moment,
        'finger_qfrc_actuator_N': projected_force,
        'scalar_force_from_moment_prediction_N': [value * scalar_force for value in moment],
        'effective_force_range_N': [
            float(value) for value in model.actuator_forcerange[actuator_id]
        ],
        'active_equality_ids': [int(index) for index, value in enumerate(data.eq_active) if value],
        'public_model_dimensions': {
            name: int(getattr(model, name))
            for name in ('nq', 'nv', 'nu', 'njnt', 'neq', 'ntendon')
        },
    }


def _disable_all_actuator_forces(model):
    model.actuator_forcelimited[:] = 1
    model.actuator_forcerange[:] = 0.0


def _run_equality_probe(model, mujoco, *, equality_active, steps, variant):
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    _disable_all_actuator_forces(model)
    data.ctrl[:] = 0.0
    data.eq_active[:] = 1 if equality_active else 0
    addresses = _finger_addresses(model, mujoco)
    _set_finger_state(data, addresses, (0.028, 0.012), (0.0, 0.0))
    mujoco.mj_forward(model, data)
    trace = [{
        'step': 0,
        'simulation_time_s': float(data.time),
        'finger_q_m': [float(data.qpos[addresses[name][0]])
                       for name in ('finger_joint1', 'finger_joint2')],
        'finger_dq_m_s': [float(data.qvel[addresses[name][1]])
                          for name in ('finger_joint1', 'finger_joint2')],
    }]
    for index in range(steps):
        mujoco.mj_step(model, data)
        trace.append({
            'step': index + 1,
            'simulation_time_s': float(data.time),
            'finger_q_m': [float(data.qpos[addresses[name][0]])
                           for name in ('finger_joint1', 'finger_joint2')],
            'finger_dq_m_s': [float(data.qvel[addresses[name][1]])
                              for name in ('finger_joint1', 'finger_joint2')],
        })
    initial_difference = trace[0]['finger_q_m'][0] - trace[0]['finger_q_m'][1]
    final_difference = trace[-1]['finger_q_m'][0] - trace[-1]['finger_q_m'][1]
    return {
        'schema_version': 'f05-dg01-n1-equality-probe-v1',
        'variant': variant,
        'equality_active': equality_active,
        'actuator_forces_disabled': True,
        'actuator_force_range_variant': [0.0, 0.0],
        'steps': steps,
        'initial_difference_m': initial_difference,
        'final_difference_m': final_difference,
        'absolute_difference_reduction_ratio': (
            1.0 - abs(final_difference) / abs(initial_difference)
        ),
        'trace': trace,
    }


def _core_request(candidate, env):
    from task_env.controllers.canonical.contracts import (
        ControlGroupActionV1,
        StructuredActionRequestV1,
    )

    hand = [item for item in env.typed_state.view.frames
            if item.frame.entity_id == 'panda-main' and item.frame.frame_id == 'hand']
    if len(hand) != 1:
        raise RuntimeError('DG01 Core reset did not publish the exact Panda hand Frame')
    pose = hand[0].pose_world
    binding = env.controller.controller_binding()
    schema_id = binding.action_schema.schema_id
    request = StructuredActionRequestV1(
        'structured-action-request-v1', env.position_scene.identity_hash,
        env.position_plan.identity_hash,
        (
            ControlGroupActionV1(
                'control-group-action-v1', 'panda-main', 'arm', schema_id,
                tuple(float(value) for value in (*pose.position, *pose.quaternion_wxyz)),
            ),
            ControlGroupActionV1(
                'control-group-action-v1', 'panda-main', 'gripper', schema_id, (-0.5,),
            ),
        ),
    )
    request.validate()
    return request


def run_n1(output: Path, *, expected_model_receipt_identity_sha256: str,
           max_integration_steps: int = 105):
    """Run one ≤500-step feature probe on public MuJoCo and the actual Core Env."""
    import hashlib
    import xml.etree.ElementTree as ET

    import mujoco

    from task_env.runtime.sessions.source import lower_mujoco_scene_source
    from task_env.tasks.position_candidate.builder import build_f05_dg01_mujoco_candidate

    if type(max_integration_steps) is not int or not 1 <= max_integration_steps <= 500:
        raise ValueError('DG01 N1 integration-step cap must be in [1, 500]')
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    event_path = output / 'n1_probe_events.jsonl'
    if event_path.exists():
        raise FileExistsError(event_path)
    started = _utc_now()
    candidate = build_f05_dg01_mujoco_candidate(output / 'candidate-build', horizon=300)
    env = candidate.env
    core_session = None
    actual_steps = 0
    try:
        lowered_xml, assets = lower_mujoco_scene_source(
            candidate.source.scene_source,
            candidate.source.scene_definition,
            candidate.source.source_closure_digest,
        )
        lowered_sha = hashlib.sha256(lowered_xml.encode('utf-8')).hexdigest()
        source_model = mujoco.MjModel.from_xml_string(lowered_xml, assets=assets)
        dimensions = {
            name: int(getattr(source_model, name))
            for name in ('nq', 'nv', 'nu', 'njnt', 'neq', 'ntendon')
        }
        expected_dimensions = {
            'nq': 16, 'nv': 15, 'nu': 8, 'njnt': 10, 'neq': 1, 'ntendon': 1,
        }
        if dimensions != expected_dimensions:
            raise RuntimeError(f'N1 exact public source model dimensions changed: {dimensions!r}')

        equality_id = 0
        equality_record = {
            'type': int(source_model.eq_type[equality_id]),
            'object_ids': [
                int(source_model.eq_obj1id[equality_id]),
                int(source_model.eq_obj2id[equality_id]),
            ],
            'solref': [float(value) for value in source_model.eq_solref[equality_id]],
            'solimp': [float(value) for value in source_model.eq_solimp[equality_id]],
        }
        if equality_record['type'] != int(mujoco.mjtEq.mjEQ_JOINT):
            raise RuntimeError(f'N1 expected source joint equality, observed {equality_record!r}')

        data = mujoco.MjData(source_model)
        mujoco.mj_resetData(source_model, data)
        finger_addresses = _finger_addresses(source_model, mujoco)
        _set_finger_state(data, finger_addresses, (0.028, 0.012), (0.2, -0.1))
        data.eq_active[:] = 0  # isolate tendon actuation from the separate source equality relation
        data.ctrl[:] = 0.0
        actuator_id = mujoco.mj_name2id(
            source_model, mujoco.mjtObj.mjOBJ_ACTUATOR, 'actuator8',
        )
        data.ctrl[actuator_id] = 255.0
        mujoco.mj_forward(source_model, data)
        tendon_baseline = _actuator_joint_readback(
            source_model, data, mujoco, variant='exact_source_joint_equality_disabled_for_isolation',
        )
        if abs(tendon_baseline['compiled_scalar_force_N']
               - tendon_baseline['unclipped_scalar_force_N']) > 1e-8:
            raise RuntimeError(f'N1 source tendon law mismatch: {tendon_baseline!r}')
        if any(abs(actual - predicted) > 1e-8 for actual, predicted in zip(
                tendon_baseline['finger_qfrc_actuator_N'],
                tendon_baseline['scalar_force_from_moment_prediction_N'], strict=True)):
            raise RuntimeError(f'N1 source tendon projection mismatch: {tendon_baseline!r}')
        _write_jsonl(event_path, {'phase': 'exact_tendon_law', 'readback': tendon_baseline})

        source_model.actuator_forcerange[actuator_id] = (-0.5, 0.5)
        cap_data = mujoco.MjData(source_model)
        mujoco.mj_resetData(source_model, cap_data)
        _set_finger_state(cap_data, finger_addresses, (0.028, 0.012), (0.2, -0.1))
        cap_data.eq_active[:] = 0
        cap_data.ctrl[:] = 0.0
        cap_data.ctrl[actuator_id] = 255.0
        mujoco.mj_forward(source_model, cap_data)
        tendon_cap = _actuator_joint_readback(
            source_model, cap_data, mujoco,
            variant='exact_compiled_source_with_probe_only_scalar_force_cap_0.5N',
        )
        if abs(tendon_cap['compiled_scalar_force_N'] - 0.5) > 1e-8:
            raise RuntimeError(f'N1 scalar force cap was not applied before tendon projection: {tendon_cap!r}')
        if any(abs(actual - predicted) > 1e-8 for actual, predicted in zip(
                tendon_cap['finger_qfrc_actuator_N'],
                tendon_cap['scalar_force_from_moment_prediction_N'], strict=True)):
            raise RuntimeError(f'N1 force cap was not projected through public tendon moment: {tendon_cap!r}')
        _write_jsonl(event_path, {'phase': 'scalar_cap_before_projection', 'readback': tendon_cap})

        root = ET.fromstring(lowered_xml)
        fixed = root.find("./tendon/fixed[@name='split']")
        if fixed is None:
            raise RuntimeError('N1 tendon ablation cannot locate exact split tendon in derived source XML')
        wraps = list(fixed.findall('joint'))
        removed = [item for item in wraps if item.attrib.get('joint') == 'finger_joint2']
        if len(wraps) != 2 or len(removed) != 1:
            raise RuntimeError('N1 tendon negative control requires exactly two authored wraps and one finger_joint2 wrap')
        fixed.remove(removed[0])
        ablation_xml = ET.tostring(root, encoding='unicode')
        ablation_sha = hashlib.sha256(ablation_xml.encode('utf-8')).hexdigest()
        ablated_model = mujoco.MjModel.from_xml_string(ablation_xml, assets=assets)
        ablated_data = mujoco.MjData(ablated_model)
        mujoco.mj_resetData(ablated_model, ablated_data)
        ablated_addresses = _finger_addresses(ablated_model, mujoco)
        _set_finger_state(ablated_data, ablated_addresses, (0.028, 0.012), (0.2, -0.1))
        if ablated_model.neq != 1:
            raise RuntimeError('N1 tendon ablation changed the source equality count')
        ablated_data.eq_active[0] = 0
        ablated_actuator = mujoco.mj_name2id(
            ablated_model, mujoco.mjtObj.mjOBJ_ACTUATOR, 'actuator8',
        )
        ablated_data.ctrl[:] = 0.0
        ablated_data.ctrl[ablated_actuator] = 255.0
        mujoco.mj_forward(ablated_model, ablated_data)
        tendon_ablation = _actuator_joint_readback(
            ablated_model, ablated_data, mujoco,
            variant='negative_control_source_derived_xml_without_finger_joint2_tendon_wrap',
        )
        if abs(tendon_ablation['tendon_generalized_force_moment'][1]) > 1e-10:
            raise RuntimeError(f'N1 negative tendon control still routes force to finger_joint2: {tendon_ablation!r}')
        _write_jsonl(event_path, {
            'phase': 'tendon_ablation_negative_control',
            'source_model_xml_sha256': lowered_sha,
            'derived_ablation_xml_sha256': ablation_sha,
            'removed_wrap': {'joint': 'finger_joint2', 'coef': 0.5},
            'readback': tendon_ablation,
        })

        disable_model = mujoco.MjModel.from_xml_string(lowered_xml, assets=assets)
        equality_steps_per_variant = 50
        if equality_steps_per_variant * 2 + 5 > max_integration_steps:
            raise ValueError('N1 step plan does not reserve both equality variants and the Core interval')
        equality_positive = _run_equality_probe(
            disable_model, mujoco, equality_active=True, steps=equality_steps_per_variant,
            variant='exact_source_joint_equality_active_actuators_force_disabled',
        )
        actual_steps += equality_positive['steps']
        _write_jsonl(event_path, {'phase': 'equality_positive', 'readback': equality_positive})
        equality_negative = _run_equality_probe(
            disable_model, mujoco, equality_active=False, steps=equality_steps_per_variant,
            variant='negative_control_source_joint_equality_disabled_actuators_force_disabled',
        )
        actual_steps += equality_negative['steps']
        _write_jsonl(event_path, {'phase': 'equality_negative_control', 'readback': equality_negative})
        if equality_positive['absolute_difference_reduction_ratio'] < 0.90:
            raise RuntimeError(f'N1 positive equality coupling did not converge as frozen: {equality_positive!r}')
        if equality_negative['absolute_difference_reduction_ratio'] > 0.10:
            raise RuntimeError(f'N1 equality ablation did not retain an uncoupled gap: {equality_negative!r}')

        reset_obs, reset_info = env.reset(seed=31)
        core_session = env.session
        if env.state.control_step != 0 or env.state.simulation_time != 0.0:
            raise RuntimeError('N1 Core reset advanced physics before the probe interval')
        core_model_receipt = getattr(core_session, '_f05_dg01_model_receipt', None)
        if (not isinstance(core_model_receipt, dict)
                or core_model_receipt.get('identity_sha256') != expected_model_receipt_identity_sha256):
            raise RuntimeError('N1 Core reset compiled a model different from the frozen N0 receipt')
        request = _core_request(candidate, env)
        step_obs, reward, terminated, truncated, info = env.step(request)
        actual_steps += int(getattr(core_session, '_native_steps', 0))
        write_receipt = getattr(core_session, '_last_dg01_position_application', None)
        advances = tuple(getattr(core_session, '_last_dg01_interval_advances', ()))
        applied = env.last_position_transition[2]
        if (env.state.control_step != 1 or abs(env.state.simulation_time - 0.01) > 1e-12
                or len(advances) != 5 or not isinstance(write_receipt, dict)
                or write_receipt.get('model_receipt_identity_sha256') != expected_model_receipt_identity_sha256
                or write_receipt['gripper']['effective_force_range_N'] != [-5.0, 5.0]
                or abs(write_receipt['gripper']['applied_opening_m'] - 0.02) > 1e-12
                or abs(applied.gripper_force_limit_N - 5.0) > 1e-12):
            raise RuntimeError('N1 actual Core interval did not publish its exact 5-substep position/force receipt')
        core_result = {
            'schema_version': 'f05-dg01-n1-core-interval-v1',
            'selected_reference_env': type(env).__name__,
            'task_source_identity_sha256': candidate.task_source.identity_hash,
            'task_artifact_identity_sha256': candidate.artifact.identity_hash,
            'scene_identity_sha256': candidate.scene.identity_hash,
            'execution_identity_sha256': candidate.execution.identity_hash,
            'control_binding_plan_identity_sha256': env.position_plan.identity_hash,
            'controller_identity_sha256': env.controller.identity,
            'model_receipt_identity_sha256': core_model_receipt['identity_sha256'],
            'reset_advanced_physics_steps': 0,
            'reset_info_provider': reset_info.get('provider'),
            'request': {
                'schema_version': request.schema_version,
                'scene_identity_hash': request.scene_identity_hash,
                'binding_identity_hash': request.binding_identity_hash,
                'groups': [
                    {
                        'schema_version': group.schema_version,
                        'entity_id': group.entity_id,
                        'group_id': group.group_id,
                        'action_schema_id': group.action_schema_id,
                        'values': list(group.values),
                    }
                    for group in request.groups
                ],
            },
            'reward': float(reward),
            'terminated': bool(terminated),
            'truncated': bool(truncated),
            'control_step': int(env.state.control_step),
            'simulation_time_s': float(env.state.simulation_time),
            'accepted_native_steps': len(advances),
            'interval_advance_receipts': [dict(item) for item in advances],
            'mujoco_position_write_receipt': dict(write_receipt),
            'applied_gripper_opening_m': float(applied.gripper_servo_opening_m),
            'applied_gripper_force_limit_N': float(applied.gripper_force_limit_N),
            'task_metrics': dict(env.evaluation.metrics),
            'returned_info_task_semantics': info.get('task_semantics'),
            'final_finger_positions_m': {
                item.joint_id: float(item.position[0])
                for item in env.typed_state.view.joints
                if item.entity_id == 'panda-main'
                and item.joint_id in ('finger_joint1', 'finger_joint2')
            },
        }
        if actual_steps > max_integration_steps:
            raise RuntimeError(f'N1 integration steps {actual_steps} exceeded plan cap {max_integration_steps}')
        _write_jsonl(event_path, {'phase': 'selected_reference_core_interval', 'readback': core_result})
        env.close()
        if not getattr(core_session, '_closed', False):
            raise RuntimeError('N1 SelectedReferenceEnv did not close its RuntimeSession')
        payload = {
            'schema_version': 'f05-dg01-n1-feature-probe-v1',
            'run_id': output.name,
            'started_utc': started,
            'finished_utc': _utc_now(),
            'native_invocations': 1,
            'integration_steps': actual_steps,
            'integration_step_cap': max_integration_steps,
            'physics_dt_s': 0.002,
            'physics_time_s_by_integration_steps': actual_steps * 0.002,
            'explicit_public_model_forward_calls_not_counted_as_integration': 5,
            'source_lowered_xml_sha256': lowered_sha,
            'tendon_actuator_law': tendon_baseline,
            'scalar_force_cap_before_projection': tendon_cap,
            'tendon_ablation_negative_control': {
                'derived_xml_sha256': ablation_sha,
                'readback': tendon_ablation,
            },
            'joint_equality_positive': equality_positive,
            'joint_equality_negative_control': equality_negative,
            'selected_reference_core_interval': core_result,
            'core_session_closed': True,
        }
        _write_once(output / 'n1_result.json', payload)
        return payload
    finally:
        if not getattr(env, '_closed', False):
            env.close()


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('n0', 'n1'), required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expected-model-receipt-identity-sha256')
    parser.add_argument('--max-integration-steps', type=int, default=105)
    args = parser.parse_args(argv)
    if args.mode == 'n0':
        result = run_n0(args.output)
        print(json.dumps({
            'mode': args.mode,
            'native_invocations': result['native_invocations'],
            'physics_steps': result['physics_steps'],
            'model_receipt_identity_sha256': result['model_receipt_identity_sha256'],
        }, sort_keys=True))
    elif args.mode == 'n1':
        if not args.expected_model_receipt_identity_sha256:
            parser.error('--mode n1 requires --expected-model-receipt-identity-sha256')
        result = run_n1(
            args.output,
            expected_model_receipt_identity_sha256=args.expected_model_receipt_identity_sha256,
            max_integration_steps=args.max_integration_steps,
        )
        print(json.dumps({
            'mode': args.mode,
            'native_invocations': result['native_invocations'],
            'integration_steps': result['integration_steps'],
            'tendon_force_N': result['tendon_actuator_law']['compiled_scalar_force_N'],
            'equality_reduction_ratio': result['joint_equality_positive']['absolute_difference_reduction_ratio'],
            'equality_negative_reduction_ratio': result['joint_equality_negative_control']['absolute_difference_reduction_ratio'],
            'core_control_step': result['selected_reference_core_interval']['control_step'],
            'core_model_receipt_identity_sha256': result['selected_reference_core_interval']['model_receipt_identity_sha256'],
        }, sort_keys=True))


if __name__ == '__main__':
    main()
