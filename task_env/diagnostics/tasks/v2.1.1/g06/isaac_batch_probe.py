"""Native Isaac batch feasibility probe used by the supervised G06 runner."""
from __future__ import annotations


def run():
    import gc
    import os
    import sys
    import numpy as np
    import torch
    import warp as wp
    # Import only Core's Gymnasium before starting the SDK, then immediately
    # remove its site directory. Leaving it on sys.path can shadow Isaac's
    # OpenUSD distribution. Production receives already-built declarations.
    core_site = os.environ['GEOCHORA_DIAGNOSTIC_CORE_SITE']
    sys.path.append(core_site)
    try:
        import gymnasium  # noqa: F401
    finally:
        sys.path.remove(core_site)
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY
    from task_env.runtime.sessions.isaac_native_io import IsaacSimAppOwnerV1
    from task_env.runtime.sessions.source import close_source_and_task_resources

    owner = IsaacSimAppOwnerV1()
    binding = source = lease = context = articulation = None
    manager = app_utils = None
    result = None
    try:
        owner.open()
        import omni.usd
        from pxr import Gf, PhysxSchema, Sdf, UsdGeom, UsdPhysics
        from isaacsim.core.cloner import Cloner
        from isaacsim.core.experimental.prims import Articulation
        from isaacsim.core.experimental.utils import app as app_utils
        from isaacsim.core.simulation_manager import SimulationManager as manager

        task = ENV_REGISTRY.get('pendulum-v1')
        config = resolve_task_env_config(task, {'execution': {'physics_provider': 'isaacsim',
            'physics_backend': 'cuda', 'physics_device': 'cuda:0',
            'deployment': 'in_process', 'interpreter': sys.executable}, 'episode': {'seed': 73, 'horizon': 20}})
        binding = task._build_selected_binding(config)
        built = binding.build_for_request('isaacsim', 'cuda', 73, 20)
        source = built['source']
        built['physical_execution'].validate_source(scene=source.scene_definition,
            artifact_sha256=built['artifact'].identity_hash, source_id=source.source_id,
            source_closure_sha256=source.source_closure_digest, source=source)
        lease = source.scene_source.acquire_snapshot()
        delivery = source.scene_source.loaded_delivery.delivery
        entry = lease.root.joinpath(*delivery.entry_file.split('/'))
        context = omni.usd.get_context()
        if context.get_stage() is not None:
            context.close_stage()
        context.new_stage()
        stage = context.get_stage()
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        root = '/World/envs/env_0'
        prim = UsdGeom.Xform.Define(stage, root).GetPrim()
        if not prim.GetReferences().AddReference(str(entry), Sdf.Path(delivery.entry_prim)):
            raise ValueError('verified USD source reference failed')
        for key, value in delivery.variant_selections.items():
            source_path, name = key.rsplit('#', 1)
            if source_path != delivery.entry_prim:
                raise ValueError('probe supports only an entry-root variant selection')
            if not prim.GetVariantSets().GetVariantSet(name).SetVariantSelection(value):
                raise ValueError('source variant selection failed')
        scene_paths = [str(p.GetPath()) for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]
        for path in scene_paths:
            stage.GetPrimAtPath(path).SetActive(False)
        paths = [f'/World/envs/env_{index}' for index in range(3)]
        cloner = Cloner()
        cloner.clone(root, paths, positions=np.zeros((3, 3)), copy_from_source=True)
        manager.setup_simulation(dt=.002, device='cuda:0')
        scenes = manager.get_physics_scenes()
        if len(scenes) != 1:
            raise ValueError('expected one native PhysX scene')
        physics = scenes[0]
        physics.set_gravity(Gf.Vec3f(0., 0., -9.81))
        physics.set_enabled_gpu_dynamics(True)
        if not physics.get_enabled_gpu_dynamics():
            raise RuntimeError('native GPU dynamics are disabled')
        cloner.filter_collisions(str(physics.path), '/World/collisions', paths)
        if not PhysxSchema.PhysxSceneAPI(physics.prim).GetInvertCollisionGroupFilterAttr().Get():
            raise ValueError('native collision group inversion is not enabled')
        groups = []
        for index, path in enumerate(paths):
            group_path = f'/World/collisions/group{index}'
            group = stage.GetPrimAtPath(group_path)
            includes = [str(value) for value in group.GetRelationship('collection:colliders:includes').GetTargets()]
            filtered = [str(value) for value in group.GetRelationship('physics:filteredGroups').GetTargets()]
            if includes != [path] or filtered != [group_path]:
                raise ValueError(f'native collision filtering differs for {path}')
            groups.append({'path': group_path, 'includes': includes, 'filtered_groups': filtered})
        roots = [str(p.GetPath()) for p in stage.Traverse()
                 if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
        rows = []
        for path in paths:
            matches = [value for value in roots if value.startswith(path + '/')]
            if len(matches) != 1:
                raise ValueError(f'expected one source articulation below {path}: {matches}')
            rows.append(matches[0])
        articulation = Articulation(rows)
        app_utils.play()
        app_utils.update_app(steps=2)
        app_utils.pause()
        if not articulation.is_physics_tensor_entity_valid():
            raise RuntimeError('native batch articulation view unavailable')
        if len(articulation) != 3 or len(articulation.dof_names) != 1:
            raise ValueError('native articulation batch or DOF layout differs')
        link_paths = articulation.link_paths
        for row, expected in enumerate(paths):
            if not link_paths[row] or any(not str(path).startswith(expected + '/') for path in link_paths[row]):
                raise ValueError('native tensor articulation order differs from environment order')
        articulation.set_dof_gains([0.], [0.], update_default_gains=False)
        q = torch.tensor([[-.3], [.4], [.7]], dtype=torch.float32, device='cuda')
        v = torch.zeros_like(q)
        articulation.set_dof_positions(wp.from_torch(q))
        articulation.set_dof_velocities(wp.from_torch(v))
        sim = manager.get_physics_simulation_view()
        before_reset = int(manager.get_num_physics_steps())
        if sim.update_articulations_kinematic() is False:
            raise RuntimeError('native kinematic refresh failed')
        torch.cuda.synchronize()
        if int(manager.get_num_physics_steps()) != before_reset:
            raise RuntimeError('native reset advanced physics')
        actual_initial = wp.to_torch(articulation.get_dof_positions()).clone()
        if not torch.allclose(actual_initial, q, atol=1e-6, rtol=0):
            raise ValueError('native reset did not preserve row identities')
        forces = torch.tensor([[1.], [0.], [-1.]], dtype=torch.float32, device='cuda')
        for _ in range(25):
            articulation.set_dof_efforts(wp.from_torch(forces))
            manager.step(steps=1, update_fabric=False)
        torch.cuda.synchronize()
        if int(manager.get_num_physics_steps()) - before_reset != 25:
            raise AssertionError('native manager step counter differs')
        measured_q = wp.to_torch(articulation.get_dof_positions()).clone().cpu().numpy().reshape(-1)
        measured_v = wp.to_torch(articulation.get_dof_velocities()).clone().cpu().numpy().reshape(-1)
        expected_q, expected_v = np.array([-.3, .4, .7]), np.zeros(3)
        for _ in range(25):
            expected_v += .002 * (np.array([1., 0., -1.]) + 9.81 * .25 * np.sin(expected_q)
                                  - .05 * expected_v) / .1125
            expected_q += .002 * expected_v
        if np.max(np.abs(measured_q - expected_q)) > .01 or np.max(np.abs(measured_v - expected_v)) > .05:
            raise AssertionError(f'native source fails frozen hinge oracle: q={measured_q}, v={measured_v}')
        before = wp.to_torch(articulation.get_dof_positions()).clone()
        tick = int(manager.get_num_physics_steps())
        articulation.set_dof_positions(wp.from_torch(torch.tensor([[.1], [-.1]], device='cuda')), indices=[0, 2])
        articulation.set_dof_velocities(wp.from_torch(torch.zeros((2, 1), device='cuda')), indices=[0, 2])
        sim.update_articulations_kinematic()
        torch.cuda.synchronize()
        after = wp.to_torch(articulation.get_dof_positions()).clone()
        if not torch.equal(before[1], after[1]) or int(manager.get_num_physics_steps()) != tick:
            raise AssertionError('masked reset changed another row or advanced physics')
        result = {'scope': 'Isaac native overlapping Pendulum batch feasibility; not factory admission',
                'batch': 3, 'articulation_roots': rows, 'link_paths': link_paths,
                'filter_path': '/World/collisions', 'collision_groups': groups, 'coincident_origins': True,
                'dof_names': list(articulation.dof_names), 'q': measured_q.tolist(),
                'qdot': measured_v.tolist(), 'expected_q': expected_q.tolist(),
                'expected_qdot': expected_v.tolist(), 'masked_reset_preserved_row': True,
                'native_steps': 25, 'source_closure_sha256': source.source_closure_digest}
        return result
    finally:
        if app_utils is not None:
            app_utils.stop()
        articulation = None
        gc.collect()
        if context is not None and context.get_stage() is not None:
            context.close_stage()
        if lease is not None:
            lease.close()
        if source is not None and binding is not None:
            close_source_and_task_resources(source, binding)
        owner.close()
        if result is not None:
            result['app_close'] = owner.close_receipt()
            if not result['app_close']['close_completed']:
                raise RuntimeError('Isaac App owner did not complete close')
def run_pickcube_collision_filter(*, participant='cube', cross_cube_height=.6245, inject_failure=False):
    """Compare the same cloned source with filtering enabled and disabled."""
    import gc
    import os
    import sys
    import tempfile
    from pathlib import Path
    import numpy as np
    import torch
    import warp as wp

    if participant not in ('cube', 'robot', 'cross'):
        raise ValueError('collision control participant must be cube, robot or cross')

    core_site = os.environ['GEOCHORA_DIAGNOSTIC_CORE_SITE']
    sys.path.append(core_site)
    try:
        import gymnasium  # noqa: F401
    finally:
        sys.path.remove(core_site)
    from task_env.assembly.usd_cache import installed_usd_manifest
    from task_env.assembly.usd_delivery import load_usd_asset_delivery
    from task_env.runtime.sessions.isaac_native_io import IsaacSimAppOwnerV1

    owner = IsaacSimAppOwnerV1()
    context = manager = app_utils = None
    result = None
    failure_message = None
    try:
        owner.open()
        loaded = load_usd_asset_delivery(installed_usd_manifest('isaacsim', 'panda-v1'))
        with tempfile.TemporaryDirectory(prefix='isaac-filter-source-', dir=os.getcwd()) as temp:
            root = Path(temp)
            for name, data in loaded.file_bytes.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            entry = root / loaded.delivery.entry_file
            import omni.usd
            from pxr import Gf, PhysxSchema, Sdf, UsdGeom, UsdPhysics
            from isaacsim.core.cloner import Cloner
            from isaacsim.core.experimental.prims import Articulation
            from isaacsim.core.experimental.utils import app as app_utils
            from isaacsim.core.simulation_manager import SimulationManager as manager

            context = omni.usd.get_context()
            trials = []
            for filtered in (True, False):
                if context.get_stage() is not None:
                    context.close_stage()
                context.new_stage()
                stage = context.get_stage()
                UsdGeom.SetStageMetersPerUnit(stage, 1.0)
                UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
                paths = [f'/World/envs/env_{index}' for index in range(3)]
                prim = UsdGeom.Xform.Define(stage, paths[0]).GetPrim()
                if not prim.GetReferences().AddReference(str(entry), Sdf.Path(loaded.delivery.entry_prim)):
                    raise RuntimeError('source reference failed')
                for key, selection in loaded.delivery.variant_selections.items():
                    source_path, name = key.rsplit('#', 1)
                    if source_path != loaded.delivery.entry_prim:
                        raise ValueError('filter probe supports entry-root variants only')
                    if not prim.GetVariantSets().GetVariantSet(name).SetVariantSelection(selection):
                        raise ValueError('source variant selection failed')
                for scene in [p for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]:
                    scene.SetActive(False)
                cloner = Cloner()
                origins = (np.zeros((3, 3)) if participant in ('cube', 'cross')
                           else np.asarray([[0., 0., 0.], [.01, 0., 0.], [-.01, 0., 0.]]))
                cloner.clone(paths[0], paths, positions=origins, copy_from_source=True)
                for path in paths:
                    if participant == 'cube':
                        robot = stage.GetPrimAtPath(path + '/panda')
                        if not robot or not robot.SetActive(False):
                            raise RuntimeError('could not isolate the source cubes for the collision control')
                    else:
                        root_prim = stage.GetPrimAtPath(path)
                        for child in root_prim.GetChildren():
                            keep = (child.GetName() == 'panda' if participant == 'robot'
                                    else ((path == paths[0] and child.GetName() == 'panda')
                                          or (path == paths[1] and child.GetName() == 'cube_v1')))
                            if not keep and not child.SetActive(False):
                                raise RuntimeError('could not isolate source robots for the collision control')
                if participant == 'cube':
                    for path, x in zip(paths, (.90, .91, .89), strict=True):
                        cube = stage.GetPrimAtPath(path + '/cube_v1')
                        operations = UsdGeom.Xformable(cube).GetOrderedXformOps()
                        translations = [op for op in operations if op.GetOpType() == UsdGeom.XformOp.TypeTranslate]
                        if len(translations) != 1 or translations[0].Set(Gf.Vec3d(x, .40, .80)) is False:
                            raise RuntimeError('could not initialize the source cube position')
                manager.setup_simulation(dt=.002, device='cuda:0')
                scenes = manager.get_physics_scenes()
                if len(scenes) != 1:
                    raise RuntimeError('expected one PhysX scene per trial')
                physics = scenes[0]
                physics.set_gravity(Gf.Vec3f(0., 0., -9.81))
                physics.set_enabled_gpu_dynamics(True)
                if filtered:
                    cloner.filter_collisions(str(physics.path), '/World/collisions', paths)
                    if not PhysxSchema.PhysxSceneAPI(physics.prim).GetInvertCollisionGroupFilterAttr().Get():
                        raise RuntimeError('native collision filter inversion is absent')
                if participant in ('robot', 'cross'):
                    roots = [str(p.GetPath()) for p in stage.Traverse()
                             if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
                    row_roots = []
                    robot_paths = paths if participant == 'robot' else paths[:1]
                    for path in robot_paths:
                        matches = [value for value in roots if value.startswith(path + '/')]
                        if len(matches) != 1:
                            raise ValueError('source robot control requires one articulation per row')
                        row_roots.append(matches[0])
                    articulation = Articulation(row_roots)
                app_utils.play()
                app_utils.update_app(steps=2)
                app_utils.pause()
                simulation = manager.get_physics_simulation_view()
                if participant in ('robot', 'cross'):
                    if not articulation.is_physics_tensor_entity_valid() or len(articulation) != len(robot_paths):
                        raise RuntimeError('source robot articulation batch unavailable')
                    for row, path in enumerate(robot_paths):
                        if not articulation.link_paths[row] or any(
                                not str(link).startswith(path + '/') for link in articulation.link_paths[row]):
                            raise ValueError('source robot row mapping differs')
                    articulation.set_dof_gains([0.] * len(articulation.dof_names),
                                               [0.] * len(articulation.dof_names), update_default_gains=False)
                    initial_by_name = {'joint1': -.17, 'joint2': 0., 'joint3': 0.,
                                       'joint4': -1.5707963268, 'joint5': 0., 'joint6': 1.5707963268,
                                       'joint7': -.7853981634, 'finger_joint1': .04, 'finger_joint2': .04}
                    if set(articulation.dof_names) != set(initial_by_name):
                        raise ValueError('source robot DOF names differ')
                    q = torch.tensor([[initial_by_name[name] for name in articulation.dof_names]] * len(robot_paths),
                                     dtype=torch.float32, device='cuda')
                    articulation.set_dof_positions(wp.from_torch(q))
                    articulation.set_dof_velocities(wp.from_torch(torch.zeros_like(q)))
                    if simulation.update_articulations_kinematic() is False:
                        raise RuntimeError('source robot kinematic refresh failed')
                    cross_cube = None
                    if participant == 'cross':
                        cross_cube = simulation.create_rigid_body_view([paths[1] + '/cube_v1'])
                        if [str(path) for path in cross_cube.prim_paths] != [paths[1] + '/cube_v1']:
                            raise ValueError('cross-world cube row differs')
                        raw = cross_cube.get_transforms()
                        transform = (raw if isinstance(raw, torch.Tensor) else wp.to_torch(raw)).clone()
                        transform[0] = torch.tensor([.5465, -.0938, cross_cube_height, 0., 0., 0., 1.], device='cuda')
                        velocity = torch.zeros((1, 6), dtype=torch.float32, device='cuda')
                        indices = torch.tensor([0], dtype=torch.int32, device='cuda')
                        if isinstance(raw, torch.Tensor):
                            cross_cube.set_transforms(transform.contiguous(), indices)
                            cross_cube.set_velocities(velocity, indices)
                        else:
                            native_indices = wp.from_torch(indices, dtype=wp.uint32)
                            cross_cube.set_transforms(wp.from_torch(transform.contiguous()), native_indices)
                            cross_cube.set_velocities(wp.from_torch(velocity), native_indices)
                        torch.cuda.synchronize()
                        placed = cross_cube.get_transforms()
                        cube_initial = (placed if isinstance(placed, torch.Tensor) else wp.to_torch(placed)).clone().cpu().numpy()
                        if inject_failure:
                            raise RuntimeError('diagnostic native-view cleanup check')
                    before = int(manager.get_num_physics_steps())
                    manager.step(steps=25, update_fabric=False)
                    torch.cuda.synchronize()
                    if int(manager.get_num_physics_steps()) - before != 25:
                        raise RuntimeError('robot filter trial advanced an unexpected native step count')
                    values = wp.to_torch(articulation.get_dof_positions()).clone().cpu().numpy()
                    trial = {'filter_enabled': filtered, 'initial_q': q.cpu().numpy().tolist(),
                             'final_q': values.tolist(), 'dof_names': list(articulation.dof_names),
                             'origins_m': origins.tolist(), 'native_steps': 25}
                    if participant == 'cross':
                        last_cube = cross_cube.get_transforms()
                        last_cube = last_cube if isinstance(last_cube, torch.Tensor) else wp.to_torch(last_cube)
                        trial['cube_initial_pose'] = cube_initial.tolist()
                        trial['cube_final_pose'] = last_cube.clone().cpu().numpy().tolist()
                    trials.append(trial)
                    articulation = cross_cube = simulation = None
                    if participant == 'cross':
                        raw = transform = velocity = indices = native_indices = placed = last_cube = None
                    torch.cuda.synchronize()
                    gc.collect()
                    app_utils.stop()
                    context.close_stage()
                    gc.collect()
                    continue
                expected = [path + '/cube_v1' for path in paths]
                cubes = simulation.create_rigid_body_view(expected)
                actual = [str(path) for path in cubes.prim_paths]
                if len(actual) != 3 or set(actual) != set(expected):
                    raise RuntimeError('native cube view rows differ from source environments')
                row_order = torch.tensor([actual.index(path) for path in expected], dtype=torch.int64, device='cuda')
                raw_transform = cubes.get_transforms()
                torch.cuda.synchronize()
                transform = (raw_transform if isinstance(raw_transform, torch.Tensor)
                             else wp.to_torch(raw_transform)).clone()
                initial = torch.tensor([[.90, .40, .80, 0., 0., 0., 1.],
                                        [.91, .40, .80, 0., 0., 0., 1.],
                                        [.89, .40, .80, 0., 0., 0., 1.]], device='cuda')
                transform[row_order] = initial
                velocity = torch.zeros((3, 6), dtype=torch.float32, device='cuda')
                indices = torch.arange(3, device='cuda', dtype=torch.int32)
                native_indices = None
                torch.cuda.synchronize()
                if isinstance(raw_transform, torch.Tensor):
                    cubes.set_transforms(transform.contiguous(), indices)
                    cubes.set_velocities(velocity, indices)
                else:
                    native_indices = wp.from_torch(indices, dtype=wp.uint32)
                    cubes.set_transforms(wp.from_torch(transform.contiguous()), native_indices)
                    cubes.set_velocities(wp.from_torch(velocity), native_indices)
                torch.cuda.synchronize()
                before = int(manager.get_num_physics_steps())
                manager.step(steps=25, update_fabric=False)
                torch.cuda.synchronize()
                if int(manager.get_num_physics_steps()) - before != 25:
                    raise RuntimeError('filter trial advanced an unexpected native step count')
                raw_final = cubes.get_transforms()
                torch.cuda.synchronize()
                final_tensor = raw_final if isinstance(raw_final, torch.Tensor) else wp.to_torch(raw_final)
                final = final_tensor.index_select(0, row_order).clone().cpu().numpy()
                initial_cpu = initial.cpu().numpy()
                horizontal = np.linalg.norm(final[:, :2] - initial_cpu[:, :2], axis=1)
                trials.append({'filter_enabled': filtered, 'initial_xyz': initial_cpu[:, :3].tolist(),
                               'final_xyz': final[:, :3].tolist(),
                               'horizontal_displacements_m': horizontal.tolist(), 'native_steps': 25})
                raw_transform = raw_final = final_tensor = transform = velocity = indices = native_indices = cubes = simulation = None
                torch.cuda.synchronize()
                gc.collect()
                app_utils.stop()
                context.close_stage()
                gc.collect()
            on, off = trials
            if participant == 'cube':
                if max(on['horizontal_displacements_m']) > 1e-4:
                    failure_message = f'filtered worlds affected each other: {on}'
                elif max(off['horizontal_displacements_m']) < .005:
                    failure_message = f'filter-off control did not expose cross-world collision: {off}'
                scope = 'overlapping source cube filter on/off control, Panda inactive; not a complete task gate'
            elif participant == 'robot':
                filtered_q, unfiltered_q = np.asarray(on['final_q']), np.asarray(off['final_q'])
                same_rows = float(np.max(np.abs(filtered_q - filtered_q[:1])))
                exposed = float(np.max(np.abs(unfiltered_q - filtered_q)))
                if not np.isfinite(unfiltered_q).all() or same_rows > .001 or exposed < .01:
                    failure_message = (f'robot filter control failed: filtered row error={same_rows}, '
                                       f'filter-off difference={exposed}, trials={trials}')
                scope = 'overlapping source robots with cross-world filter on/off; other scene bodies inactive'
                on['max_row_difference_rad_or_m'] = same_rows
                off['max_difference_from_filtered_rad_or_m'] = exposed
            else:
                filtered_q, unfiltered_q = np.asarray(on['final_q']), np.asarray(off['final_q'])
                exposed = float(np.max(np.abs(unfiltered_q - filtered_q)))
                if not np.isfinite(unfiltered_q).all() or exposed < .01:
                    failure_message = (f'robot/cube cross-world filter-off effect too small: {exposed}, '
                                       f'trials={trials}')
                scope = 'source robot/cube cross-world filter on/off; other scene bodies inactive'
                off['max_difference_from_filtered_rad_or_m'] = exposed
            result = {'status': 'FAIL' if failure_message is not None else 'PASS',
                      'scope': scope, 'source_closure_sha256': loaded.delivery.closure_sha256,
                      'trials': trials, 'failure': failure_message}
    except Exception as error:
        import traceback
        details = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        result = {'status': 'FAIL', 'failure': f'{type(error).__name__}: {error}',
                  'diagnostic_traceback': details}
        error.__traceback__ = None
    finally:
        # Release native views before the App tears down Warp, including on error.
        articulation = cross_cube = simulation = None
        raw = transform = velocity = indices = native_indices = placed = last_cube = None
        if torch.cuda.is_initialized():
            torch.cuda.synchronize()
        gc.collect()
        if app_utils is not None:
            app_utils.stop()
        if context is not None and context.get_stage() is not None:
            context.close_stage()
        owner.close()
        if result is not None:
            result['app_close'] = owner.close_receipt()
            if not result['app_close']['close_completed']:
                raise RuntimeError('Isaac App owner did not complete close')
        else:
            import json
            print('diagnostic_app_close=' + json.dumps(owner.close_receipt()), flush=True)
    return result
