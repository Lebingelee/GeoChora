"""Bounded public-factory CPU check; SDK step counting is external instrumentation."""
from pathlib import Path
import argparse,datetime,fcntl,json,os,resource,sys,time,traceback
parser=argparse.ArgumentParser();parser.add_argument('--public-ui-check',action='store_true');parser.add_argument('--observer-check',action='store_true');parser.add_argument('--task-renderer', default='mujoco', choices=('mujoco','geophys'));parser.add_argument('--reset-switch',action='store_true');parser.add_argument('--validate-schema',action='store_true');parser.add_argument('--task-rgb',action='store_true');parser.add_argument('--camera-spec',action='store_true');parser.add_argument('--case',required=True);parser.add_argument('--plan',required=True)
parser.add_argument('--provider',choices=('mujoco','geophys'),default='mujoco')
parser.add_argument('--cube-force-z',type=float,default=None)
parser.add_argument('--table-half-x',type=float,default=None)
parser.add_argument('--extra-robot-asset-root',action='store_true')
parser.add_argument('--annotate-robot-source',action='store_true')
parser.add_argument('--relocate-robot-assets',action='store_true')
parser.add_argument('--profile',default=None);parser.add_argument('--robot-uid',default=None);parser.add_argument('--record',action='store_true');parser.add_argument('--sequence',action='store_true');parser.add_argument('--yaml',action='store_true');parser.add_argument('--gravity',action='store_true');parser.add_argument('--solution',action='store_true');parser.add_argument('--controller-kp',type=float,default=None);parser.add_argument('--solution-after-switch',action='store_true');args=parser.parse_args()
if args.solution and args.case != 'panda-r3':raise ValueError('Solution probe requires panda-r3')
if args.controller_kp is not None and not (args.case == 'panda-joint' and args.record):
    raise ValueError('Controller gain probe requires switchable panda-joint recording')
if args.solution_after_switch and not (args.case == 'panda-joint' and args.record):
    raise ValueError('caller-owned Solution probe requires switchable panda-joint recording')
plan=json.loads(Path(args.plan).read_text())
started=time.monotonic();locks=[];env=None;result={'case':args.case,'provider':args.provider,'status':'RUNNING','steps':[],'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'native_substeps':0 if args.provider=='mujoco' else None}
resource.setrlimit(resource.RLIMIT_AS,(plan['rss_address_space_limit_bytes'],)*2)
resource.setrlimit(resource.RLIMIT_CPU,(120,125))
try:
    for path in plan['locks_in_order']:
        handle=open(path,'r+');fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(handle)
    result['locks_acquired']=True
    import numpy as np
    if args.provider=='mujoco':
        import mujoco
        original_step=mujoco.mj_step
        def counted_step(*params,**kwargs):
            count=kwargs.get('nstep',params[2] if len(params)>2 else 1)
            if result['native_substeps']+int(count)>plan['per_run_reserved_physics_substeps']:
                raise RuntimeError('reserved physics substep limit exhausted')
            result['native_substeps']+=int(count)
            return original_step(*params,**kwargs)
        mujoco.mj_step=counted_step
    from task_env import make_env
    from task_env.runtime.sessions.source import source_resource_receipt
    if args.annotate_robot_source:
        if args.case not in {'pendulum', 'two-wheel'}:
            raise ValueError('annotated Robot source probe requires a simple Robot')
        from task_env.robots.pendulum import PendulumEntity
        from task_env.robots.two_wheel_balance import TwoWheelBalanceEntity
        robot_type = PendulumEntity if args.case == 'pendulum' else TwoWheelBalanceEntity
        robot_type.source_xml += '\n<!-- selected Robot source -->'
    if args.extra_robot_asset_root:
        if args.case != 'panda-effort':
            raise ValueError('extra Robot asset root probe requires PickCube effort')
        from dataclasses import replace
        from task_env.robots.panda import PandaAgent
        original_manifest = PandaAgent.asset_manifest
        extra_root = Path('additional-robot-assets').resolve()
        extra_root.mkdir()
        def manifest_with_extra_root(robot):
            manifest = original_manifest(robot)
            return replace(manifest, asset_roots=(*manifest.asset_roots, extra_root))
        PandaAgent.asset_manifest = manifest_with_extra_root
        result['extra_robot_asset_root'] = str(extra_root)
    if args.table_half_x is not None:
        if args.case != 'panda-effort':
            raise ValueError('table declaration probe requires PickCube effort')
        from copy import deepcopy
        from task_env.tasks.pick_cube import specialization
        task_config = deepcopy(specialization._configuration())
        task_config['recipe']['scene']['table_half_size'][0] = args.table_half_x
        specialization.PickCubeReferenceEnv.selected_task_configuration = staticmethod(lambda: task_config)
        result['declared_table_half_x'] = args.table_half_x
    if args.relocate_robot_assets:
        if args.case not in {'assembled-live', 'panda-r3', 'nut'}:
            raise ValueError('relocated Robot source probe requires a tabletop task')
        from dataclasses import replace
        from task_env.robots.assembled_panda import AssembledPandaAgent
        from task_env.robots.panda import PandaAgent
        from task_env.runtime.sessions.source import source_asset_bytes
        robot_type = AssembledPandaAgent if args.case == 'assembled-live' else PandaAgent
        manifest = robot_type().asset_manifest()
        root = Path('declared-robot-assets').resolve()
        root.mkdir()
        for source in manifest.mjcf_sources:
            (root / source.name).write_bytes(source.read_bytes())
            for relative, content in source_asset_bytes(manifest.asset_roots[0], source.read_text()).items():
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
        (root / 'LICENSE').write_bytes((manifest.asset_roots[0] / 'LICENSE').read_bytes())
        relocated = replace(manifest, asset_roots=(root,),
            mjcf_sources=tuple(root / source.name for source in manifest.mjcf_sources))
        robot_type.asset_manifest = lambda _self: relocated
        result['declared_robot_asset_root'] = str(root)
    def construct(uid, config):
        camera_options = {}
        if args.task_rgb:
            from task_env.environment.config import CameraSpec
            from task_env.observations.canonical_camera import CameraGeometry
            camera = CameraSpec('task', width=64, height=48, depth=False)
            if not args.camera_spec:
                preliminary = make_env(uid, config=config)
                try:
                    camera = CameraGeometry.from_camera_spec(camera, task_artifact_hash=preliminary.artifact.identity_hash)
                finally:
                    preliminary.close()
            camera_options = {'task_rgb_camera': camera, 'task_renderer': args.task_renderer}
        if args.observer_check or args.public_ui_check:
            from task_env.environment.config import CameraSpec
            camera_options['observer_camera'] = CameraSpec('observer', width=64, height=48, depth=False)
            camera_options['render_mode'] = 'rgb_array'
        if args.yaml:
            import yaml
            path = Path('formal-task.yaml')
            path.write_text(yaml.safe_dump(config), encoding='utf-8')
            return make_env(uid, config=path, **camera_options)
        return make_env(uid, config=config, **camera_options)
    if args.case in {'panda-r3','panda-gravity','panda-effort','panda-joint','assembled-unreset','assembled-live','nut'}:
        config={'execution':{'physics_provider':args.provider,'physics_backend':'cpu','physics_device':'cpu','deployment':'in_process','interpreter':sys.executable},'episode':{'horizon':8}}
        if args.cube_force_z is not None:config['task']={'cube_force_z_N':args.cube_force_z}
        if args.case=='panda-gravity':config['controller']={'gravity_compensation':True}
        if args.case=='panda-r3' and args.profile:config['controller']={'profile_id':args.profile}
        if args.case=='panda-effort':config['controller']={'profile_id':'panda-direct-effort-v1'}
        if args.case=='panda-joint':
            config['controller']={'profile_id':args.profile or 'panda-joint-effort-reference-v1'}
            if args.record:config['controller']['parameters']={'reset_selection':True}
        if args.case.startswith('assembled'):config.update(robot={'uid':'panda-arm-hand-v1'},controller={'profile_id':'r1_split'})
        if args.gravity:config.setdefault('controller',{})['gravity_compensation']=True
        if args.reset_switch:
            if args.case != 'panda-r3' or args.provider != 'mujoco':
                raise ValueError('reset switch probe requires MuJoCo Panda R3')
            config['execution']['reset_profile'] = 'pickcube-state-only-switch-v1'
        uid='nut-assembly-outcome-reference-v1' if args.case=='nut' else 'pick-cube-p16-reference-v1'
        if args.robot_uid is not None:config['robot']={'uid':args.robot_uid}
        env=construct(uid,config)
        action=np.asarray([.2,0.,0.,0.,0.,0.,0.,0.] if args.case=='panda-effort' else
                          [.4,0.,.4,1.,0.,0.,0.,1.],dtype=np.float32)
        if args.case=='panda-joint':
            q=env.artifact.initialization.joint_position
            action=(np.asarray([.4,0.,.4,1.,0.,0.,0.,1.],dtype=np.float32)
                    if args.profile in {'panda-r3-effort-reference-v1','panda-r3-mass-effort-v1'} else
                    np.asarray([q[f'panda-v1/joint{i}'] + (.002 if i==1 else 0.) for i in range(1,8)]+[.04],dtype=np.float32))
    else:
        uid='pendulum-v1' if args.case=='pendulum' else 'two-wheel-balance-v1'
        config={'execution':{'physics_provider':args.provider,'physics_backend':'cpu','physics_device':'cpu',
                             'deployment':'in_process','interpreter':sys.executable},'episode':{'horizon':8}}
        if args.profile is not None:config['controller']={'profile_id':args.profile}
        if args.robot_uid is not None:config['robot']={'uid':args.robot_uid}
        env=construct(uid,config)
        action={'torque':np.asarray([.25]if args.case=='pendulum'else[.25,-.2],dtype=np.float32)}
    result['uid']=env.uid
    result['constructed']=True
    if args.table_half_x is not None:
        import xml.etree.ElementTree as ET
        table = ET.fromstring(env.value['source'].scene_source.xml).find(".//geom[@name='grasp_table_geom']")
        assert float(table.get('size').split()[0]) == args.table_half_x
    robot=env.robot
    assert robot.declaration is env.binding.robot
    assert robot.uid == robot.declaration.uid
    if args.annotate_robot_source:
        import hashlib
        source = env.value['source']
        expected = hashlib.sha256(robot_type.source_xml.encode()).hexdigest()
        assert source.scene_definition.assets[0].source_content_sha256 == expected
        assert source.scene_source.xml == robot_type.source_xml
        result['robot_source_sha256'] = expected
    result['robot']={'uid':robot.uid,'subjects':[s.subject_id for s in robot.subjects],
        'parents':[s.parent_subject_id for s in robot.subjects],
        'controller_identities':[str(c.identity) for c in robot.controllers]}
    if args.case=='panda-joint' and args.record:
        assert robot.subjects and robot.controller is None and env.controller is None and robot.controllers == ()
        result['robot_before_reset']='declared_without_committed_controller'
    else:
        assert robot.controller is env.controller
    physical_execution = env.value.get('physical_execution')
    if physical_execution is not None and not (args.case=='panda-joint' and args.record):
        assert env.controller is robot.controller is physical_execution.controllers[0]
        assert robot.controllers == physical_execution.controllers
    if args.relocate_robot_assets:
        if args.case == 'assembled-live':
            declaration = env.value['source'].composition_runtime_input.fixed_declaration
            assert declaration.parent_source.base_dir == root
        else:
            import xml.etree.ElementTree as ET
            receipt = source_resource_receipt(env.value['source'])
            compiler = ET.fromstring(receipt.closure_files['canonical-source.xml']).find('compiler')
            assert compiler.get('meshdir') == str(root / 'assets')
        result['resolved_robot_asset_root'] = str(root)
    subject_binding=getattr(env.value['source'],'position_subject_binding',None)
    if args.case in {'nut','panda-r3','assembled-live'}:
        assert subject_binding is not None and robot.subjects == subject_binding.subjects
        result['robot']['binding_identity']=subject_binding.identity_hash
        result['robot']['resource_writers']=list(subject_binding.plan.resource_writers)

    receipt=source_resource_receipt(env.value['source'])
    snapshot=None if receipt is None else str(receipt.snapshot_root)
    physical_source = (Path(env.value['source'].scene_source.base_dir)
                       if args.case == 'panda-joint' and args.record else None)
    if physical_source is not None:
        assert physical_source.exists()
        result['physical_source_before_close'] = str(physical_source)
    result['source_snapshot']=snapshot
    if args.case!='assembled-unreset':
        if args.case=='nut' or args.solution:
            solution=env.value['solution_factory']()
            observation,info=env.reset_for_solution(solution,seed=19 if args.case=='nut' else 31)
        else:
            options = ({'controller': {'kind': 'joint', 'parameters': {'kp': args.controller_kp}}}
                       if args.controller_kp is not None else None)
            observation,info=env.reset(seed=31,options=options)
            if args.controller_kp is not None:
                assert env.physical_action_spec()['parameters'] == {'kp': args.controller_kp}
                result['controller_reset_parameters'] = env.physical_action_spec()['parameters']
        assert env.observation_space.contains(observation)
        if args.validate_schema:
            info['observation_schema'].validate(observation)
            result['observation_fields'] = list(info['observation_schema'].leaf_field_names)
        layout = env.session.build_layout_facts
        assert layout['materialization_id'] == env.session.provider_materialization_id
        assert layout['source_closure'] == env.value['source'].source_closure_digest
        assert layout['objects']['joints']
        result['native_layout'] = layout
        assert env._task_definition is not None
        assert env._task_lifecycle.task_definition is env._task_definition
        task_definition_type = type(env._task_definition)
        artifact_hash = getattr(env._task_definition, 'artifact_hash', None)
        if artifact_hash is not None:
            assert artifact_hash == env.artifact.identity_hash
        semantics = getattr(env._task_definition, 'semantics', None)
        if semantics is not None:
            assert semantics == env.artifact.semantics
        if args.task_rgb:
            assert observation['task_rgb'].shape == (48, 64, 3)
            assert info['task_rgb_v1']['capture_identity']['capture_phase'] == 'reset_initial'
            assert info['task_rgb_v1']['resolved_camera']['capture_control_step'] == 0
            result['rgb_reset_boundary'] = info['task_rgb_v1']['capture_identity']['state_boundary']
        if args.public_ui_check:
            from types import SimpleNamespace
            from task_env.render.base.contracts import RenderMode
            from task_env.render.providers.single import TaskEnvRenderProvider
            source = env.session._observer_render_source
            presenter = TaskEnvRenderProvider(render_source=source, config=SimpleNamespace(
                width=64, height=48, backend='rasterizer', render_preset='interactive'))
            boundary = env.session.state_boundary_identity().to_mapping()
            clock = float(env.state.simulation_time)
            try:
                exported = presenter.render(mode=RenderMode.RGB_ARRAY, snapshot=None)
                assert exported.shape == (48, 64, 3)
                presenter.render(mode=RenderMode.HUMAN, snapshot=None)
                assert presenter._window is not None
                assert env.session.state_boundary_identity().to_mapping() == boundary
                assert float(env.state.simulation_time) == clock
                result['public_ui'] = {'offscreen_shape': list(exported.shape), 'window_created': True,
                    'boundary_unchanged': True, 'clock_before': clock, 'clock_after': float(env.state.simulation_time)}
            finally:
                presenter.close()
        if args.observer_check:
            from task_env.environment.config import CameraSpec
            from task_env.observations.canonical_camera import CameraGeometry
            boundary = env.session.state_boundary_identity().to_mapping()
            clock = float(env.state.simulation_time)
            task_frame = observation['task_rgb'].copy() if args.task_rgb else None
            camera_identity = (info['task_rgb_v1']['capture_identity']['camera_geometry_identity_hash']
                               if args.task_rgb else None)
            observer_a = env.render()
            observer_b = env.render()
            assert observer_a.shape == observer_b.shape == (48, 64, 3)
            assert env.session.state_boundary_identity().to_mapping() == boundary
            assert float(env.state.simulation_time) == clock
            if task_frame is not None:
                np.testing.assert_array_equal(observation['task_rgb'], task_frame)
            alternate = CameraGeometry.from_camera_spec(
                CameraSpec('observer-alternate', width=64, height=48, depth=False, position=(0.1, 0, 0)),
                task_artifact_hash=env.artifact.identity_hash)
            env.set_observer_camera(alternate)
            env.render()
            assert env.session.state_boundary_identity().to_mapping() == boundary
            assert float(env.state.simulation_time) == clock
            if task_frame is not None:
                assert info['task_rgb_v1']['capture_identity']['camera_geometry_identity_hash'] == camera_identity
                np.testing.assert_array_equal(observation['task_rgb'], task_frame)
            result['observer_repeated_render'] = {'physics_clock_before': clock,
                'physics_clock_after': float(env.state.simulation_time), 'boundary_unchanged': True,
                'observer_replaced': alternate.camera_id, 'task_camera_identity': camera_identity,
                'task_frame_retained': task_frame is not None}
        if args.case in {'panda-effort','panda-joint'}:
            for finger in ('panda-v1/finger_joint1','panda-v1/finger_joint2'):
                declared=float(env.artifact.initialization.joint_position[finger])
                assert abs(float(env.state.joint_position[finger])-declared)<1e-5
            result['initial_finger_positions']={name:float(env.state.joint_position[name])
                for name in ('panda-v1/finger_joint1','panda-v1/finger_joint2')}
        if args.case=='panda-joint' and args.record:
            active_robot=env.robot
            committed=env._physical_reset_selection.current.execution
            cap=env.session._build_layout_facts['physical_gripper_force_cap']
            declared=env.value['source'].config.robot.gripper.force_limit_N
            assert cap['source_range_N']==[-5.,5.]
            assert cap['configured_range_N']==[-declared,declared]
            assert cap['source_mjcf_modified'] is False
            result['physical_gripper_force_cap']=cap
            assert active_robot.subjects == committed.subjects
            assert active_robot.controllers == committed.controllers
            assert active_robot.controller is env.controller is committed.controllers[0]
            result['first_physical_controller']=active_robot.controller.identity
        if args.record:env.start_recording(Path('episode.h5').resolve())
        first=env.session.state_boundary_identity().to_mapping()
        if subject_binding is not None:
            live_binding=env.session._source.position_subject_binding
            assert live_binding.identity_hash==env.value['source'].position_subject_binding.identity_hash
        if args.case in {'pendulum','two-wheel'}:
            first_reset_parameters=dict(info['reset_parameters'])
            first_observation=np.asarray(observation['state']['proprioception']).copy()

        if args.sequence:
            from task_env.controllers.canonical.physical_sequence import PhysicalActionSequenceV1, PhysicalActionSliceV1
            spec=env.physical_sequence_spec()
            assert len(spec['controllers']) == 1 and spec['control_substeps'] >= 2
            identity=spec['controllers'][0]['identity']; midpoint=spec['control_substeps']//2
            values=tuple(float(x) for x in action)
            action=PhysicalActionSequenceV1((
                PhysicalActionSliceV1(0,midpoint,((identity,values),)),
                PhysicalActionSliceV1(midpoint,spec['control_substeps'],((identity,tuple(-v for v in values)),))))
            result['physical_sequence_spec']=spec
        if args.cube_force_z is not None:
            force,=env.binding.task_com_wrench_factory(env)
            assert force.force_world_N == (0.,0.,args.cube_force_z)
            result['task_force']=force.to_mapping()
        time_before=float(env.state.simulation_time)
        if args.case=='panda-joint' and args.record:action=env.bind_physical_action(action)
        if args.solution_after_switch:
            dispatch = getattr(env.session, '_control_lifecycle_dispatch', None)
            try:env.step({**action, 'generation': action['generation'] + 1})
            except ValueError:pass
            else:raise AssertionError('stale Controller generation was accepted')
            assert env._execution_fault is None and env.session.state_boundary_identity().to_mapping() == first
            assert getattr(env.session, '_control_lifecycle_dispatch', None) is dispatch
            result['stale_action_rejected_without_fault']=True
        stepped=env.step_with_solution(solution) if args.case=='nut' or args.solution else env.step(action)
        dispatch = env.session._control_lifecycle_dispatch
        submission = env.session._last_control_submission
        assert dispatch.stage == 'committed' and submission['status'] == 'acknowledged'
        assert tuple(submission['controller_identities']) == dispatch.controller_identities
        result['common_control_submission'] = {
            'command_kind': dispatch.command_kind, 'status': submission['status'],
            'controller_identities': list(dispatch.controller_identities)}
        if args.case=='nut' or args.solution:
            assert not solution.failed
            result['solution_step']={'identity':solution.identity,'failed':bool(solution.failed)}
        if args.case == 'assembled-live':
            receipt=env.session._last_control_submission
            bundle=env.controller.last_split_bundle
            assert receipt['status'] == 'acknowledged'
            assert set(receipt['writer_ids']) == {'panda-arm-position-writer', 'panda-hand-position-writer'}
            assert {bundle.arm_identity, bundle.hand_identity} == {item.identity for item in env.robot.controllers}
            assert tuple(receipt['controller_identities']) == (env.controller.identity,)
            result['assembled_submission'] = receipt
        if args.sequence:
            dispatch=env.session._control_lifecycle_dispatch
            receipt=env.session._last_control_submission
            assert dispatch.command_kind == 'physical-effort-sequence' and dispatch.stage == 'committed'
            assert receipt['command_kind'] == dispatch.command_kind and receipt['status'] == 'acknowledged'
            assert receipt['controller_identities'] == list(dispatch.controller_identities) or tuple(receipt['controller_identities']) == dispatch.controller_identities
            result['physical_sequence_submission']=receipt
        if args.task_rgb:
            assert stepped[0]['task_rgb'].shape == (48, 64, 3)
            assert stepped[4]['task_rgb_v1']['capture_identity']['capture_phase'] == 'post_control_step'
            assert stepped[4]['task_rgb_v1']['resolved_camera']['capture_control_step'] == 1
            result['rgb_step_boundary'] = stepped[4]['task_rgb_v1']['capture_identity']['state_boundary']
        second=env.session.state_boundary_identity().to_mapping()
        time_after=float(env.state.simulation_time)
        result['steps'].append({'before':first,'after':second,'time_before':time_before,'time_after':time_after,'reward':float(stepped[1]),'terminated':bool(stepped[2]),'truncated':bool(stepped[3])})
        assert env.observation_space.contains(stepped[0])
        if args.validate_schema:
            info['observation_schema'].validate(stepped[0])
        if args.record:
            result['recording']=env.finish_recording('external_stop')
            if 'transition_count' in result['recording']:
                assert result['recording']['transition_count']==1 and result['recording']['observation_count']==2
            else:
                assert result['recording'].get('byte_exact') or result['recording'].get('logical_mapping_exact')
            assert Path('episode.h5').is_file()
        assert time_after>time_before
        assert abs(time_after-time_before-env.artifact.timebase.control_dt)<1e-9
        if args.case=='panda-joint' and args.record:
            prior_robot=env.robot; prior_spec=env.physical_action_spec()
            try:env.reset(options={'controller':'unsupported'})
            except ValueError:pass
            else:raise AssertionError('invalid controller reset was accepted')
            assert env.robot is prior_robot and env.controller is prior_robot.controller and env.physical_action_spec()==prior_spec
            observation,info=env.reset(seed=31,options={'controller':'r3-pose'})
            committed=env._physical_reset_selection.current.execution
            assert env.robot.subjects == committed.subjects and env.robot.controllers == committed.controllers
            assert env._controller_selection_matches[0].selection_profile_id == 'panda-r3-effort-reference-v1'
            assert env._controller_selection_matches[0].controller_identities == (committed.controllers[0].identity,)
            assert env.robot.controller is env.controller is committed.controllers[0] and env.robot is not prior_robot
            assert env.robot.controller.identity != prior_robot.controller.identity
            result['switched_physical_controller']=env.robot.controller.identity
            result['invalid_reset_preserved_robot']=True
            switched_before=float(env.state.simulation_time)
            switched_action=env.bind_physical_action(np.asarray([.4,0.,.4,1.,0.,0.,0.,1.],dtype=np.float32))
            if args.solution_after_switch:
                from task_env.tasks.pick_cube import build_readiness_solution
                solution = build_readiness_solution(controller_profile='r3_continuous_v1')
                solution.reset(observation, info, env.metadata)
                proposed = solution.act(observation, info)
                observation, reward, terminated, truncated, info = env.step(proposed)
                assert solution._awaiting_observation and env.solution is None
                solution.observe(observation, reward, terminated, truncated, info)
                assert not solution._awaiting_observation and solution.total_control_actions_emitted == 1
                result['caller_solution_observed_once'] = True
            else:
                env.step(switched_action)
            assert abs(float(env.state.simulation_time)-switched_before-env.artifact.timebase.control_dt)<1e-9
            assert env.robot.controller is env.controller is env._physical_reset_selection.current.execution.controllers[0]
            assert env.session._last_control_submission['status'] == 'acknowledged'
            result['switched_controller_advanced']=True
        else:
            options = {'execution': {'physics_provider': 'geophys', 'deployment': 'in_process',
                                     'interpreter': sys.executable}} if args.reset_switch else None
            observation,info=env.reset(seed=19 if args.case=='nut' else 31, options=options)
        if args.reset_switch:
            assert env.provider == 'geophys'
            assert set(observation['privileged_state']) == {'cube_body_pose'}
            assert info['measured_joint_velocity_units'] == ['rad/s'] * 7 + ['m/s'] * 2
            result['switched_provider'] = env.provider
        assert env.observation_space.contains(observation)
        if args.validate_schema:
            info['observation_schema'].validate(observation)
            result['schema_validated_reset_step_reset'] = True
        assert type(env._task_definition) is task_definition_type
        assert env._task_lifecycle.task_definition is env._task_definition
        artifact_hash = getattr(env._task_definition, 'artifact_hash', None)
        if artifact_hash is not None:
            assert artifact_hash == env.artifact.identity_hash
        semantics = getattr(env._task_definition, 'semantics', None)
        if semantics is not None:
            assert semantics == env.artifact.semantics
        result['task_definition'] = {'type': task_definition_type.__name__,
            'artifact_identity': env.artifact.identity_hash,
            'artifact_hash_checked': artifact_hash is not None,
            'semantics_checked': semantics is not None,
            'lifecycle_rebound': True, 'second_observation_in_space': True}
        if args.task_rgb:
            assert observation['task_rgb'].shape == (48, 64, 3)
            assert info['task_rgb_v1']['capture_identity']['capture_phase'] == 'reset_initial'
            result['rgb_second_reset_boundary'] = info['task_rgb_v1']['capture_identity']['state_boundary']
        reset=env.session.state_boundary_identity().to_mapping()
        assert reset['episode_id']!=first['episode_id']
        result['second_reset']=reset
        assert env.robot is not robot
        assert env.robot.declaration is robot.declaration is env.binding.robot
        assert env.robot.controller is env.controller
        physical_execution = env.value.get('physical_execution')
        if physical_execution is not None:
            active = (env._physical_reset_selection.current.execution
                      if getattr(env, '_physical_reset_selection', None) is not None else physical_execution)
            assert env.controller is active.controllers[0]
        result['robot_rebound_after_reset']=True
        if args.case in {'pendulum','two-wheel'}:
            assert env.binding.action_space_factory.__self__ is env.value['physical_execution']
            assert env.action_space == env.value['physical_execution'].action_space()
            result['action_space_uses_rebuilt_controller'] = True
            assert info['reset_parameters']==first_reset_parameters
            np.testing.assert_allclose(observation['state']['proprioception'],first_observation,atol=1e-6)
            observation,info=env.reset(seed=None)
            rng=np.random.default_rng(31)
            limits=([(-np.pi,np.pi),(-1.,1.)] if args.case=='pendulum' else
                    [(-.08,.08),(-.20,.20),(-.02,.02),(-.02,.02),(-.30,.30),(-.30,.30)])
            tuple(rng.uniform(a,b) for a,b in limits)
            expected=tuple(float(rng.uniform(a,b)) for a,b in limits)
            if args.case=='pendulum':expected=tuple(float(np.float32(x)) for x in expected)
            sample=env.value['reset_plan'].reset_sample
            if args.case=='pendulum':
                joints=('pendulum-v1/pendulum_hinge',)
                actual=(sample.joint_position[joints[0]],sample.joint_velocity[joints[0]])
            else:
                joints=tuple('two-wheel-balance-v1/'+n for n in ('chassis_pitch','left_wheel_hinge','right_wheel_hinge'))
                actual=(sample.joint_position[joints[0]],sample.joint_velocity[joints[0]],
                        sample.joint_position[joints[1]],sample.joint_position[joints[2]],
                        sample.joint_velocity[joints[1]],sample.joint_velocity[joints[2]])
            np.testing.assert_allclose(actual,expected,atol=0,rtol=0)
            np.testing.assert_allclose([env.state.joint_position[j] for j in joints],
                                      [sample.joint_position[j] for j in joints],atol=1e-6,rtol=0)
            result['rng_sequence']={'seed':31,'seed_none_after_repeat':list(actual),
                'independent_expected':list(expected),'info_seed':info['seed'],
                'reset_parameters':info['reset_parameters']}

    current_receipt=source_resource_receipt(env.value['source'])
    current_snapshot=None if current_receipt is None else str(current_receipt.snapshot_root)
    result['current_source_snapshot_before_close']=current_snapshot
    env.close();env.close();result['repeated_close_completed']=True
    result['current_source_snapshot_exists_after_close']=None if current_snapshot is None else Path(current_snapshot).exists()
    result['source_snapshot_exists_after_close']=None if snapshot is None else Path(snapshot).exists()
    if physical_source is not None:
        assert not physical_source.exists()
        result['physical_source_removed_after_close'] = True
    result['status']='PASS'
except BaseException as error:
    result['status']='FAIL';result['error']={'type':type(error).__name__,'message':str(error),
        'receipt':getattr(error,'receipt',None)};traceback.print_exc()
finally:
    if env is not None:
        try:env.close()
        except BaseException as error:result['cleanup_error']={'type':type(error).__name__,'message':str(error)};result['status']='FAIL'
    result['wall_s']=time.monotonic()-started;result['max_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    for handle in reversed(locks):fcntl.flock(handle,fcntl.LOCK_UN);handle.close()
    result['locks_released']=True
    Path('result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'case':args.case,'status':result['status'],'native_substeps':result['native_substeps'],'wall_s':result['wall_s']}))
raise SystemExit(0 if result['status']=='PASS'else 1)
