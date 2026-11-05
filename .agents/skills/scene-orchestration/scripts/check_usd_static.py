# 作用：供 scene-orchestration 在独立 Isaac Sim 进程中检查完整 USD 的五秒静置变化；给了 --config 时先校验交接包 config.json，机械臂冻结为静态碰撞几何，不修改源文件。
# validate_config_fields：输入 config.json 内容，返回结构错误列表（不读 USD）。
# validate_config_stage：输入 config.json 与已加载 stage，返回路径、相机与机械臂绑定错误列表。
# check_usd_static：输入 USD 路径，返回状态、覆盖范围和逐对象峰值位移/转角/加速度；不生成报告。
# measure_stage：输入已加载的 USD stage，返回实际 PhysX 采样结果。
# main：接收一个 USD 路径，输出短摘要；正常检查返回 0 通过、1 超限，程序异常直接抛出。
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

DURATION_SECONDS = 5.0
STATIC_LIMITS = (1e-5, 0.01)
DYNAMIC_LIMITS = (0.01, 2.0)
# 加速度上限用于识别爆弹与严重初始穿透；正常沉降、自由下落均远低于该值。
ACCELERATION_LIMIT = 50.0
PROCESS_TIMEOUT_SECONDS = 240
RESULT_PREFIX = 'USD_STATIC_RESULT='
ROBOT_ROOTS = ('/World/LeftRobot', '/World/RightRobot')


def freeze_robots(stage, roots=None):
    """仅在 session 层冻结约定路径下的机器人；保留碰撞，解除机器人连接的关节。

    不移动或张开夹指，允许物体被静态几何卡住。机器人以外的任务刚体
    保留动力学。此副本只用于验收，不能作为正式回合初态。
    """
    from pxr import Sdf, Usd, UsdGeom, UsdPhysics

    stage.SetEditTarget(stage.GetSessionLayer())
    roots = ROBOT_ROOTS if roots is None else tuple(roots)
    roots = [Sdf.Path(path) for path in roots if stage.GetPrimAtPath(path)]

    def is_robot(path):
        return any(path.HasPrefix(root) for root in roots)

    # 引用实例内部不能直接编辑；只展开测试副本中的机器人实例。
    while True:
        instances = [p for p in stage.Traverse() if is_robot(p.GetPath()) and p.IsInstance()]
        if not instances:
            break
        for prim in instances:
            prim.SetInstanceable(False)

    prims = list(stage.Traverse())
    cache = UsdGeom.XformCache(Usd.TimeCode(stage.GetStartTimeCode()))
    transforms = [(p, cache.GetLocalToWorldTransform(p)) for p in prims
                  if is_robot(p.GetPath()) and p.IsA(UsdGeom.Xformable)]
    # 先取齐世界位姿，再覆盖变换；避免父节点改变影响后续子节点的采样。
    for prim, matrix in transforms:
        xf = UsdGeom.Xformable(prim)
        attr = prim.GetAttribute('xformOp:transform:staticCheck')
        op = (UsdGeom.XformOp(attr) if attr else
              xf.AddTransformOp(opSuffix='staticCheck'))
        op.Set(matrix)
        xf.SetXformOpOrder([op], resetXformStack=True)

    disabled_joints = []
    for prim in prims:
        if prim.IsA(UsdPhysics.Joint):
            joint = UsdPhysics.Joint(prim)
            targets = joint.GetBody0Rel().GetTargets() + joint.GetBody1Rel().GetTargets()
            if is_robot(prim.GetPath()) or any(is_robot(path) for path in targets):
                joint.CreateJointEnabledAttr(False)
                disabled_joints.append(str(prim.GetPath()))
        if is_robot(prim.GetPath()):
            # 移除动力学 API，避免将静态碰撞误解析为禁用的动态刚体。
            for schema in list(prim.GetAppliedSchemas()):
                if schema in {'PhysicsRigidBodyAPI', 'PhysxRigidBodyAPI', 'PhysicsMassAPI',
                              'PhysicsArticulationRootAPI', 'PhysxArticulationAPI'}:
                    prim.RemoveAppliedSchema(schema)
    return dict(roots=[str(root) for root in roots], disabled_joints=disabled_joints,
                collision_preserved=True)


def pose_delta(initial, current, meters_per_unit):
    """将两组位置和 xyzw 四元数换算为米制距离与最短旋转角。"""
    p0, q0 = initial
    p1, q1 = current
    if not all(math.isfinite(v) for v in (*p0, *p1, *q0, *q1)):
        raise ValueError('位姿包含非有限数值')
    norm0, norm1 = math.sqrt(sum(v*v for v in q0)), math.sqrt(sum(v*v for v in q1))
    if min(norm0, norm1) == 0:
        raise ValueError('位姿四元数为零')
    q0, q1 = [v/norm0 for v in q0], [v/norm1 for v in q1]
    # q 与 -q 等价；atan2 避免 acos 在静态小角度附近丢失精度。
    sign = 1 if sum(a*b for a, b in zip(q0, q1)) >= 0 else -1
    difference = math.sqrt(sum((a-sign*b)**2 for a, b in zip(q0, q1)))
    total = math.sqrt(sum((a+sign*b)**2 for a, b in zip(q0, q1)))
    return math.dist(p0, p1)*meters_per_unit, math.degrees(4*math.atan2(difference, total))



CONFIG_KEYS = ('bindings', 'parameters', 'prims', 'instruction')


def _absolute_prim_path(value):
    """判断是否为绝对 prim 路径（非根路径）；不依赖 pxr，供结构校验单独调用。"""
    return (isinstance(value, str) and value.startswith('/') and value != '/'
            and not value.endswith('/') and '//' not in value)


def validate_config_fields(config):
    """只校验 config.json 的结构与命名，不读 USD；返回错误字符串列表。"""
    if not isinstance(config, dict):
        return ['config.json 必须是 JSON 对象']
    errors = []
    missing = [key for key in CONFIG_KEYS if key not in config]
    extra = sorted(set(config) - set(CONFIG_KEYS))
    if missing:
        errors.append(f'缺少字段：{missing}')
    if extra:
        errors.append(f'存在未定义字段：{extra}')
    instruction = config.get('instruction')
    if not isinstance(instruction, str) or not instruction.strip():
        errors.append('instruction 必须是非空字符串')
    prims = config.get('prims')
    if not isinstance(prims, dict):
        errors.append('prims 必须是对象')
    else:
        if set(prims) != {'robots', 'cameras'}:
            errors.append(f'prims 只能包含 robots 与 cameras，实际为 {sorted(prims)}')
        robots = prims.get('robots')
        if not isinstance(robots, dict) or set(robots) != {'left', 'right'}:
            errors.append('prims.robots 必须以 left、right 为键')
        else:
            for name, path in robots.items():
                if not _absolute_prim_path(path):
                    errors.append(f'prims.robots.{name} 不是绝对 prim 路径：{path!r}')
            if len(set(map(str, robots.values()))) != len(robots):
                errors.append('prims.robots 的两条臂指向同一个根 prim')
        cameras = prims.get('cameras')
        if not isinstance(cameras, dict) or 'head' not in cameras:
            errors.append('prims.cameras 必须包含 head')
        elif set(cameras) - {'head', 'left_wrist', 'right_wrist'}:
            errors.append(f'prims.cameras 出现未定义角色：{sorted(set(cameras) - {"head", "left_wrist", "right_wrist"})}')
        elif not all(_absolute_prim_path(v) for v in cameras.values()):
            errors.append('prims.cameras 的每个值都必须是绝对 prim 路径')
    bindings = config.get('bindings')
    if not isinstance(bindings, dict) or not bindings:
        errors.append('bindings 必须是非空对象')
    else:
        for key, value in bindings.items():
            values = value if isinstance(value, list) else [value]
            if not values or not all(_absolute_prim_path(v) for v in values):
                errors.append(f'bindings.{key} 必须是一个或多个绝对 prim 路径')
    if not isinstance(config.get('parameters'), dict):
        errors.append('parameters 必须是对象')
    return errors


def validate_config_stage(config, stage):
    """校验 config.json 中的路径在 stage 内存在，且机械臂满足绑定要求。"""
    from pxr import Usd, UsdGeom, UsdPhysics

    errors = []
    prims = config['prims']
    cameras = prims['cameras']
    for role, path in cameras.items():
        prim = stage.GetPrimAtPath(path)
        if not prim:
            errors.append(f'相机 {role} 不存在：{path}')
        elif not prim.IsA(UsdGeom.Camera):
            errors.append(f'相机 {role} 不是 UsdGeom.Camera：{path}')
    for key, value in config['bindings'].items():
        for path in (value if isinstance(value, list) else [value]):
            if not stage.GetPrimAtPath(path):
                errors.append(f'bindings.{key} 的路径不存在：{path}')

    for name, path in prims['robots'].items():
        root = stage.GetPrimAtPath(path)
        if not root:
            errors.append(f'机械臂 {name} 的根 prim 不存在：{path}')
            continue
        roots = [p.GetPath() for p in Usd.PrimRange(root) if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
        if len(roots) != 1:
            errors.append(f'机械臂 {name} 的子树内必须恰有一个 ArticulationRootAPI，实际 {len(roots)} 个')
        # 固定底座：机械臂通过 FixedJoint 连接到一个不属于它的静态支撑（不是漂浮底座）。
        fixed = False
        for prim in Usd.PrimRange(root):
            if not prim.IsA(UsdPhysics.FixedJoint):
                continue
            joint = UsdPhysics.FixedJoint(prim)
            targets = [*joint.GetBody0Rel().GetTargets(), *joint.GetBody1Rel().GetTargets()]
            inside = [t for t in targets if t.HasPrefix(root.GetPath())]
            outside = [t for t in targets if not t.HasPrefix(root.GetPath())]
            if len(inside) != 1 or len(outside) != 1:
                continue
            support = stage.GetPrimAtPath(outside[0])
            body = UsdPhysics.RigidBodyAPI(support) if support and support.HasAPI(UsdPhysics.RigidBodyAPI) else None
            static = body is None or not body.GetRigidBodyEnabledAttr().Get()
            if static:
                fixed = True
                break
        if not fixed:
            errors.append(f'机械臂 {name} 没有用 FixedJoint 连接到静态支撑（固定底座）')
    return errors


def validate_config(config, stage):
    """结构校验后做 stage 校验；结构错误时不继续读 USD。"""
    errors = validate_config_fields(config)
    return errors if errors else validate_config_stage(config, stage)


def measure_stage(stage):
    """冻结机器人后，按其余对象的原物理设置逐步检查静置变化。

    Args:
        stage: Isaac Sim 当前上下文中已加载的 USD stage。

    Returns:
        dict: 状态、仿真时长、步数和逐对象峰值位移/转角/线加速度；无法覆盖时抛出异常。
    """
    from pxr import Gf, PhysxSchema, Usd, UsdGeom, UsdPhysics, UsdUtils
    import carb.logging
    import omni.physx

    _, _, unresolved = UsdUtils.ComputeAllDependencies(stage.GetRootLayer().identifier)
    if unresolved or stage.GetCompositionErrors():
        raise ValueError('USD 组合错误或缺失依赖：' + ', '.join(str(p) for p in unresolved[:5]))
    config_path = os.environ.get('USD_STATIC_CONFIG')
    if config_path:
        config = json.loads(Path(config_path).read_text(encoding='utf-8'))
        errors = validate_config(config, stage)
        if errors:
            raise ValueError('config.json 校验失败：' + '；'.join(errors[:8]))
    stage.SetEditTarget(stage.GetSessionLayer())
    roots = json.loads(os.environ.get('USD_STATIC_ROBOT_ROOTS', 'null'))
    frozen_robots = freeze_robots(stage, roots)
    prims = list(Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies()))
    scenes = [p for p in prims if p.IsA(UsdPhysics.Scene)]
    if len(scenes) != 1:
        raise ValueError('要求一个现有 PhysicsScene；缺失或多物理场景不能完整检查')
    rate = PhysxSchema.PhysxSceneAPI(scenes[0]).GetTimeStepsPerSecondAttr().Get() or 60
    if rate <= 0:
        raise ValueError('无效物理时间步')
    dt = 1.0 / rate
    meters = UsdGeom.GetStageMetersPerUnit(stage)
    if not math.isfinite(meters) or meters <= 0:
        raise ValueError('无效长度单位')
    # Kit may add transient viewport/Hydra prims outside the delivered scene.
    # Only authored task-scene prims participate in this delivery check.
    default_prim = stage.GetDefaultPrim()
    scene_root = default_prim.GetPath() if default_prim and default_prim.IsValid() else None
    scene_prims = [p for p in prims if scene_root is not None and p.GetPath().HasPrefix(scene_root)]
    unsupported = [str(p.GetPath()) for p in scene_prims if p.IsA(UsdGeom.PointInstancer) or
                   p.GetTypeName() in {'OmniGraph', 'OmniGraphNode'} or
                   any('Deformable' in s or 'Particle' in s for s in p.GetAppliedSchemas())]
    if unsupported:
        raise ValueError('存在未覆盖的实例化粒子、软体或控制图：' + ', '.join(unsupported[:5]))
    bodies = {str(p.GetPath()): p for p in prims if p.HasAPI(UsdPhysics.RigidBodyAPI)
              and UsdPhysics.RigidBodyAPI(p).GetRigidBodyEnabledAttr().Get()}
    objects = {path: (prim, 'kinematic' if UsdPhysics.RigidBodyAPI(prim).GetKinematicEnabledAttr().Get()
                      else 'dynamic') for path, prim in bodies.items()}
    for prim in prims:
        if not prim.HasAPI(UsdPhysics.CollisionAPI) or not UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get():
            continue
        parent = prim
        while parent and str(parent.GetPath()) not in bodies:
            parent = parent.GetParent()
        if not parent:
            objects[str(prim.GetPath())] = (prim, 'static')
    if not objects:
        raise ValueError('没有可检查的刚体或静态碰撞对象')
    start = stage.GetStartTimeCode() / stage.GetTimeCodesPerSecond()
    cache = UsdGeom.XformCache(Usd.TimeCode(stage.GetStartTimeCode()))
    initial, results = {}, []
    for path, (prim, kind) in objects.items():
        transform = Gf.Transform(cache.GetLocalToWorldTransform(prim))
        q = transform.GetRotation().GetQuat()
        initial[path] = (tuple(transform.GetTranslation()), (*q.GetImaginary(), q.GetReal()))
        limits = STATIC_LIMITS if kind == 'static' else DYNAMIC_LIMITS
        results.append(dict(path=path, kind=kind, max_displacement_m=0.0, max_rotation_deg=0.0,
                            max_acceleration_m_s2=0.0, displacement_limit_m=limits[0],
                            rotation_limit_deg=limits[1], acceleration_limit_m_s2=ACCELERATION_LIMIT,
                            passed=True))
    physics = omni.physx.get_physx_interface()
    errors, observed_steps = [], []
    prev_pos = {path: tuple(c*meters for c in pose[0]) for path, pose in initial.items()}
    prev_vel = {path: (0.0, 0.0, 0.0) for path in initial}

    def on_log(source, level, filename, line, message):
        """保留物理引擎错误，防止解析失败被误判为静止。"""
        if level >= carb.logging.LEVEL_ERROR and ('physx' in source.lower() or 'physics' in source.lower()):
            if len(errors) < 5:
                errors.append(message[:240])

    logging = carb.logging.acquire_logging()
    logger = logging.add_logger(on_log)
    subscription = physics.subscribe_physics_on_step_events(lambda dt: observed_steps.append(dt), False, 0)
    steps = math.ceil(DURATION_SECONDS / dt)
    try:
        physics.start_simulation()
        for step in range(steps):
            now = start + (step + 1)*dt
            physics.update_simulation(dt, now)
            physics.update_transformations(False, True)
            if errors:
                raise ValueError('物理引擎错误：' + '; '.join(errors))
            cache = UsdGeom.XformCache(Usd.TimeCode(now * stage.GetTimeCodesPerSecond()))
            for row in results:
                path = row['path']
                # 动态与关节刚体必须从运行中的 PhysX 读取，读取失败不得回退到静态 USD。
                if row['kind'] != 'static':
                    pose = physics.get_rigidbody_transformation(path)
                    if not pose.get('ret_val'):
                        raise ValueError('PhysX 未提供刚体位姿：' + path)
                    current = (tuple(pose['position']), tuple(pose['rotation']))
                else:
                    transform = Gf.Transform(cache.GetLocalToWorldTransform(objects[path][0]))
                    q = transform.GetRotation().GetQuat()
                    current = (tuple(transform.GetTranslation()), (*q.GetImaginary(), q.GetReal()))
                displacement, rotation = pose_delta(initial[path], current, meters)
                row['max_displacement_m'] = max(row['max_displacement_m'], displacement)
                row['max_rotation_deg'] = max(row['max_rotation_deg'], rotation)
                pos = tuple(c*meters for c in current[0])
                vel = tuple((a-b)/dt for a, b in zip(pos, prev_pos[path]))
                if step:
                    row['max_acceleration_m_s2'] = max(row['max_acceleration_m_s2'],
                                                       math.dist(vel, prev_vel[path]) / dt)
                prev_pos[path], prev_vel[path] = pos, vel
                row['passed'] = (row['max_displacement_m'] <= row['displacement_limit_m'] and
                                 row['max_rotation_deg'] <= row['rotation_limit_deg'] and
                                 row['max_acceleration_m_s2'] <= row['acceleration_limit_m_s2'])
    finally:
        physics.reset_simulation()
        subscription = None
        logging.remove_logger(logger)
    if len(observed_steps) != steps or sum(observed_steps) < DURATION_SECONDS - 1e-6:
        raise ValueError('物理引擎未执行完整观察期')
    failed = sum(not row['passed'] for row in results)
    return dict(status='failed' if failed else 'passed', config_checked=bool(config_path),
                duration_seconds=steps*dt,
                steps=steps, checked=len(results), failed=failed, objects=results,
                frozen_robots=frozen_robots)


def _worker(usd_path):
    """初始化独立仿真进程；成功后释放应用，异常保留完整 traceback 退出。"""
    from isaacsim import SimulationApp
    app = SimulationApp({'headless': True, 'extra_args': ['--/log/level=error', '--/log/outputStreamLevel=error']})
    import omni.usd
    context = omni.usd.get_context()
    if not context.open_stage(str(usd_path)):
        raise ValueError('USD 加载失败')
    while context.get_stage_loading_status()[2] > 0:
        app.update()
    stage = context.get_stage()
    if stage is None:
        raise ValueError('USD stage 不存在')
    result = measure_stage(stage)
    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=True), flush=True)
    # Kit 的快速关闭可能直接退出进程；只在正常完成后调用，避免截断异常 traceback。
    app.close()


def check_usd_static(usd_path, roots=None, config_path=None):
    """启动独立 Isaac Sim 检查；异常、超时和子进程失败直接向上传播。

    Args:
        usd_path: 含必要支撑与 PhysicsScene 的 USD 文件路径。

    Returns:
        dict: status 为 passed 或 failed，objects 为完整逐对象测量。
    """
    usd_path = Path(usd_path).resolve()
    if not usd_path.is_file():
        raise FileNotFoundError(usd_path)
    # 子进程在临时目录中运行，配置文件必须给出绝对路径。
    config_path = Path(config_path).resolve() if config_path is not None else None
    with tempfile.TemporaryDirectory(prefix='usd-static-') as folder:
        with tempfile.TemporaryFile(mode='w+b') as log:
            # stderr 直接继承，子进程的原始 traceback 不进入临时文件或策略反馈。
            environment = dict(os.environ)
            if roots is not None:
                environment['USD_STATIC_ROBOT_ROOTS'] = json.dumps(list(roots))
            if config_path is not None:
                environment['USD_STATIC_CONFIG'] = str(config_path)
            process = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', str(usd_path)],
                                     cwd=folder, stdout=log, timeout=PROCESS_TIMEOUT_SECONDS, env=environment)
            if process.returncode:
                log.seek(0)
                sys.stderr.write(log.read().decode('utf-8', errors='replace'))
                process.check_returncode()
            log.seek(0)
            result = None
            for line in log:
                text = line.decode('utf-8', errors='replace').strip()
                if text.startswith(RESULT_PREFIX):
                    result = json.loads(text[len(RESULT_PREFIX):])
            if result is None:
                log.seek(0)
                sys.stderr.write(log.read().decode('utf-8', errors='replace'))
                raise RuntimeError('仿真进程未返回检查结果')
            return result


def main():
    """运行命令行检查，只打印短摘要并以退出码表达结果。

    Returns:
        int: 正常检查 0 通过、1 超限；命令行用法错误为 2。程序异常不转换为返回值。
    """
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        _worker(Path(sys.argv[2]))
        return 0
    arguments = sys.argv[1:]
    if '--config' in arguments:
        index = arguments.index('--config')
        if index + 1 >= len(arguments) or len(arguments) != 3:
            print('用法：python check_usd_static.py <scene.usd> [--config config.json]')
            return 2
        config = json.loads(Path(arguments[index + 1]).read_text(encoding='utf-8'))
        roots = list(config['prims']['robots'].values())
        config_path = arguments[index + 1]
        usd_path = arguments[0] if index else arguments[2]
    else:
        if len(arguments) != 1:
            print('用法：python check_usd_static.py <scene.usd> [--config config.json]')
            return 2
        roots, usd_path, config_path = None, arguments[0], None
    result = check_usd_static(usd_path, roots, config_path)
    roots = result['frozen_robots']['roots']
    if result.get('config_checked'):
        print('config.json 校验：通过')
    print('冻结机器人（保留碰撞）：' + (', '.join(roots) if roots else '无约定路径的机器人'))
    print(f"静置检查：{result['status']}；{result['duration_seconds']:.3f}s；"
          f"检查 {result['checked']} 个对象，超限 {result['failed']} 个。")
    failed = [row for row in result['objects'] if not row['passed']]
    for row in failed[:5]:
        print(f"{row['path']}：位移 {row['max_displacement_m']:.6g}m / {row['displacement_limit_m']:g}m；"
              f"转角 {row['max_rotation_deg']:.6g}° / {row['rotation_limit_deg']:g}°；"
              f"加速度 {row['max_acceleration_m_s2']:.6g}m/s² / {row['acceleration_limit_m_s2']:g}m/s²")
    return int(bool(result['failed']))


if __name__ == '__main__':
    raise SystemExit(main())
