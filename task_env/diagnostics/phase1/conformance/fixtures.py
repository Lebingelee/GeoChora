"""Provider-free authored fixtures and analytical oracles. No native execution."""
import hashlib
import json
import math

PROBES = ('asset_frame', 'free_fall', 'joint_tracking', 'camera_depth', 'contact')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def fixtures():
    specifications = {}
    def add(name, body, gravity, steps, bindings, facts, initial, inputs, oracle, tolerance, rationale, diagnostic):
        xml = (f'<mujoco model="p1_3_{name}"><compiler angle="radian" inertiafromgeom="false"/>'
               f'<option timestep="0.002" gravity="{gravity}" integrator="Euler"/>'
               '<statistic extent="1"/><visual><map znear="0.01" zfar="10"/></visual>'
               f'<worldbody>{body}</worldbody>'
               + ('<actuator><general name="servo" joint="hinge" gaintype="fixed" biastype="affine" '
                  'gainprm="1 0 0" biasprm="0 -1 -0.2" ctrllimited="true" ctrlrange="-0.5 0.5"/></actuator>' if name == 'joint_tracking' else '')
               + '</mujoco>')
        recipe = {'schema_version': 'p1_3-recipe-v0', 'fixture_id': name+'/v0', 'source_xml': xml,
                  'semantic_bindings': bindings, 'facts': facts, 'initial_state': initial,
                  'timebase': {'physics_dt': .002, 'steps': steps}, 'inputs': inputs}
        specifications[name] = {'probe_id': name, 'version': 'v0', 'recipe': recipe,
                                'fixture_hash': digest(recipe), 'source_sha256': hashlib.sha256(xml.encode()).hexdigest(),
                                'oracle': oracle, 'metrics': list(tolerance), 'tolerance': tolerance,
                                'tolerance_rationale': rationale,
                                'field_classification': {
                                    'exact_semantic': ['SI', 'gravity', 'dt', 'initial_state', 'geometry', 'mass/inertia', 'frame_offsets', 'joint_limits', 'camera_resolution/FOV/pose'],
                                    'approximate_mapping': ['actuator stiffness/damping', 'contact friction/compliance'],
                                    'provider_native': ['solver iterations/stabilization', 'render backend', 'native depth convention']},
                                'diagnostic_only_fields': diagnostic}
    inertia = '<inertial pos="0 0 0" mass="1" diaginertia="0.01 0.02 0.03"/>'
    add('asset_frame', '<body name="root" pos="1 2 3" quat="0.7071067811865476 0 0 0.7071067811865476"><freejoint name="free"/>'+inertia+
        '<geom name="shape" type="box" size="0.1 0.2 0.3" contype="0" conaffinity="0"/>'
        '<site name="child" pos="0.1 0.2 0.3" quat="1 0 0 0" size="0.001"/></body>',
        '0 0 0', 0, {'bodies': {'probe/root': 'root'}, 'frames': {'probe/child': 'child'}},
        {'gravity': [0.,0.,0.], 'geometry': {'box_half_sizes':[.1,.2,.3]}, 'mass':1., 'inertia':[.01,.02,.03], 'child_offset':[.1,.2,.3]},
        {'root_position':[1.,2.,3.], 'root_wxyz':[math.sqrt(.5),0.,0.,math.sqrt(.5)], 'velocity':[0.]*6}, {},
        {'root_position':[1.,2.,3.], 'child_position':[.8,2.1,3.3], 'root_wxyz':[math.sqrt(.5),0.,0.,math.sqrt(.5)], 'mass':1., 'inertia':[.01,.02,.03], 'geometry':[.1,.2,.3]},
        {'position_max_abs':1e-5,'quaternion_max_abs':1e-5,'materialized_facts_max_abs':1e-6},
        'P1.2 float32 representation scale for composed transforms; inertial/geometry facts at float32 mapping precision.', ['native import diagnostics'])
    add('free_fall', '<body name="fall" pos="0 0 3"><joint name="free" type="free" damping="0" armature="0"/>'
        '<inertial pos="0 0 0" mass="1" diaginertia="0.004 0.004 0.004"/>'
        '<geom name="shape" type="sphere" size="0.1" contype="0" conaffinity="0"/></body>',
        '0 0 -9.81', 50, {'bodies':{'probe/body':'fall'}},
        {'gravity':[0.,0.,-9.81],'geometry':{'sphere_radius':.1},'mass':1.,'inertia':[.004]*3,'damping':0.,'contact':False},
        {'position':[0.,0.,3.],'quaternion_wxyz':[1.,0.,0.,0.],'velocity':[0.]*6}, {},
        {'acceleration':[0.,0.,-9.81],'downward':True,'orientation':[1.,0.,0.,0.]},
        {'vertical_acceleration_error':1e-3,'lateral_acceleration':1e-3,'lateral_displacement':1e-5,'quaternion_drift':1e-5},
        'Short 0.1 s no-contact velocity invariant; ceilings bound float32 accumulation without requiring continuous-time position equality.',
        ['continuous_position_error','pairwise_position_difference'])
    add('joint_tracking', '<body name="link"><joint name="hinge" type="hinge" axis="0 0 1" limited="true" range="-0.5 0.5" damping="0" armature="0"/>'
        '<inertial pos="0 0 0" mass="1" diaginertia="0.01 0.01 0.01"/>'
        '<geom name="shape" type="sphere" size="0.05" contype="0" conaffinity="0"/></body>',
        '0 0 0', 1000, {'joints':{'probe/hinge':'hinge'},'actuators':{'probe/servo':'servo'}},
        {'gravity':[0.,0.,0.],'geometry':{'sphere_radius':.05},'mass':1.,'inertia':[.01]*3,'joint_limits':[-.5,.5],
         'actuator':{'force':'1*(target-q)-0.2*qdot','stiffness':1.,'damping':.2,'force_limit':None}},
        {'joint_position':0.,'joint_velocity':0.}, {'fixed_target':.2},
        {'direction':'positive','final_target':.2,'error_decreases':True,'joint_limits':[-.5,.5]},
        {'initial_error':1e-5,'final_error_rad':.03,'limit_excess':1e-5},
        'Critically damped I=0.01, kp=1, kd=0.2; 2 s is twenty natural time constants. 0.03 rad ceiling does not require actuator equivalence.',
        ['overshoot','settling_time','pairwise_joint_difference','pairwise_bound_rad=0.03 diagnostic only'])
    add('camera_depth', '<camera name="fixed" pos="0 0 2" quat="1 0 0 0" fovy="60"/>'
        '<body name="surface"><geom name="surface_geom" type="box" pos="0 0 -0.05" size="1 1 0.05" rgba="0.8 0.8 0.8 1" contype="0" conaffinity="0"/>'
        '<site name="axis" pos="0 0 0" size="0.001" rgba="0 0 0 0"/><site name="offset" pos="0.4 0 0" size="0.001" rgba="0 0 0 0"/></body>',
        '0 0 0',0,{'frames':{'probe/axis':'axis','probe/offset':'offset'},'cameras':{'probe/fixed':'fixed'}},
        {'gravity':[0.,0.,0.],'geometry':{'surface_top_z':0.,'box_half_sizes':[1.,1.,.05]},'camera':{'width':64,'height':64,'vertical_fov_degrees':60.,'position':[0.,0.,2.],'look_at':[0.,0.,0.],'up':[0.,1.,0.],'near':.01,'far':10.,'pixel_convention':'top-left pixel-edge coordinates; centers at i+0.5,j+0.5'}},
        {'static':True},{'landmarks':[[0.,0.,0.],[.4,0.,0.]]},
        {'pixels':[[32.,32.],[32.+32./math.tan(math.pi/6)*.4/2.,32.]],'center_depth_m':2.},
        {'projection_max_abs_pixels':1.,'center_depth_error_m':.005},
        'One-pixel mapping ceiling; 5 mm native depth ceiling includes even-resolution center pixel ray-vs-axis difference (~0.000163 m).',
        ['RGB','native near/far readback','native ray-vs-camera-axis depth convention'])
    add('contact', '<body name="support" pos="0 0 -0.05"><geom name="support_geom" type="box" size="1 1 0.05" friction="0 0 0"/></body>'
        '<body name="ball" pos="0 0 0.5"><joint name="free" type="free" damping="0" armature="0"/>'
        '<inertial pos="0 0 0" mass="1" diaginertia="0.004 0.004 0.004"/>'
        '<geom name="shape" type="sphere" size="0.1" friction="0 0 0"/></body>',
        '0 0 -9.81',1000,{'bodies':{'probe/body':'ball','probe/support':'support'}},
        {'gravity':[0.,0.,-9.81],'geometry':{'sphere_radius':.1,'support_top_z':0.,'support_box_half_sizes':[1.,1.,.05]},'mass':1.,'inertia':[.004]*3,'contact_material':{'friction':[0.,0.,0.],'compliance':'provider default; approximate mapping; not tuned'}},
        {'position':[0.,0.,.5],'quaternion_wxyz':[1.,0.,0.,0.],'velocity':[0.]*6}, {},
        {'contact_center_height':.1,'settle_window_steps':100,'falls':True,'no_tunneling_center_min':0.},
        {'support_height_error_m':.005,'persistent_penetration_m':.005,'post_settle_vertical_speed':.05},
        'Behavioral support gate after 2 s, last 0.2 s persistent penetration/speed. No native impulse or compliance equality.',
        ['native contact impulse/detection','pairwise_height_difference','maximum_transient_penetration'])
    return specifications
