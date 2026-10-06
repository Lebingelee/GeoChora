"""Provider-free authored calibration source and camera oracle."""
import hashlib
import json
import math
from ....artifacts import ActionIntent, EntityDefinition, InitializationContract, RequiredCapabilitySet, SemanticDefinition, TaskArtifact, Timebase, WorldDefinition
from ....observations.canonical_camera.contracts import CameraGeometry, MOUNT_FROM_CAMERA
from ....render.camera.source import CameraRenderSource, TriangleMesh


def fixture_artifact():
    return TaskArtifact('task-artifact-v0','camera-calibration-v1/phase1','camera-calibration-v1','v0',
        WorldDefinition('world-v0','SI_right_handed_z_up_wxyz',
            (EntityDefinition('calibration/surface','static','calibration-box-v0',(),(),'triangle_mesh','no_contact',{'top_z':0}),
             EntityDefinition('calibration/parent','embodiment','calibration-slide-v0',(),('calibration/slide',),'slide','no_contact',{'mass':1})),
            ActionIntent('absolute_joint',None,'none','arm_joint_position_and_gripper'),('canonical-state-v0',),()),
        InitializationContract('initialization-v0',{}, {'calibration/slide':0.},(), 'named_initial_velocity_0.5_m_s','finite',0),
        SemanticDefinition('semantics-v0','calibration_geometry',('calibration/parent',),('calibration/slide',),{},'diagnostic_only'),
        Timebase(.002,10,.02),RequiredCapabilitySet(('rigid_body','joint_state_query','body_pose_query')))


def render_source():
    # Closed thin box; top z=0. Shared exact vertices/faces consumed by both renderers.
    vertices = ((-2.,-2.,-.1),(2.,-2.,-.1),(2.,2.,-.1),(-2.,2.,-.1),
                (-2.,-2.,0.),(2.,-2.,0.),(2.,2.,0.),(-2.,2.,0.))
    faces = ((0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
             (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7))
    return CameraRenderSource('camera-static-triangles-v0',fixture_artifact().identity_hash,
        (TriangleMesh('calibration/surface',vertices,faces,(.8,.8,.8)),))


def camera(parent):
    # Optical camera looks down world -Z, image-right +X, image-down -Y.
    # Legacy mount forward -Z/up +Y; composed with the fixed proper optical rotation.
    mount = ((0.,-1.,0.,.1),(0.,0.,1.,-.15),(-1.,0.,0.,2.),(0.,0.,0.,1.))
    return CameraGeometry('camera-observation-v0',fixture_artifact().identity_hash,
        'calibration/camera',parent,mount,MOUNT_FROM_CAMERA,80,64,math.pi/3,.01,10.)


PARENT_XML = ('<mujoco model="p1_4_camera_parent"><compiler angle="radian" inertiafromgeom="false"/>'
    '<option timestep="0.002" gravity="0 0 0" integrator="Euler"/>'
    '<worldbody><body name="parent"><joint name="slide" type="slide" axis="1 0 0" damping="0" armature="0"/>'
    '<inertial pos="0 0 0" mass="1" diaginertia="0.01 0.01 0.01"/>'
    '<geom name="hidden" type="sphere" size="0.01" contype="0" conaffinity="0" rgba="0 0 0 0"/>'
    '</body></worldbody></mujoco>')


def digest(mapping):
    return hashlib.sha256(json.dumps(mapping,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def specification():
    recipe = {'artifact':fixture_artifact().to_mapping(),'render_source':render_source().to_mapping(),
        'cameras':{'fixed':camera('world').to_mapping(),'dynamic':camera('calibration/parent').to_mapping()},
        'parent_source_xml':PARENT_XML,'semantic_bindings':{'calibration/parent':'parent','calibration/slide':'slide'},
        'initial_velocity_m_s':.5,'physics_dt':.002,'control_substeps':10,'control_dt':.02,
        'landmarks':[[.1,-.15,0.],[.5,.1,0.],[-.3,-.4,0.]],
        'sample_pixel_indices':[[39,31],[20,15],[60,45]],'surface_top_z':0.}
    return {'schema_version':'p1_4-camera-oracle-v0','recipe':recipe,'recipe_sha256':digest(recipe),
        'conventions':{'world':'SI right-handed +Z up wxyz','optical':'+X right +Y down +Z forward right-handed',
            'legacy_mount':'+X forward +Z up','T_mount_from_camera':MOUNT_FROM_CAMERA,
            'intrinsics':'fy=H/2/tan(fov_y/2);fx=fy;cx=W/2;cy=H/2',
            'fov_x':'2*atan(W/H*tan(fov_y/2))','pixels':'image edges [0,W]x[0,H]; index centers at u+0.5,v+0.5',
            'depth':'positive optical-Z meters float32 HxW; zero invalid/background/clipped',
            'timestamp':'post_control_step same CanonicalStateView as geometry',
            'RGB':'HWC float32 baseline, finite [0,1]; CHW/uint8 normalization supported'},
        'tolerances':{'transform_max_abs':1e-5,'K_max_abs':1e-5,'projection_pixels':1.,'depth_m':.005,'back_projection_m':.005,
                      'pure_geometry':1e-12,'timestamp_s':math.ulp(.02)},
        'rationale':'Transforms/K use float32 representation ceiling. Pixel 1 and 5mm depth/back-projection ceilings bound native camera/raster mapping at 80x64; no photometric/integrator equivalence. Timestamp one ULP of declared control_dt.',
        'oracle':'Analytic pinhole and plane intersection; dynamic transforms derive from measured canonical parent, not provider equality.',
        'native_conventions':{'geophys':'normalized-ray metric distance, bottom-left WH framebuffer; divide ray norm after HWC flip',
                              'mujoco':'Renderer axial metric depth HxW top-left, verify off-axis plane intersections'},
        'field_classification':{'exact_semantic':['source vertices/faces','bindings','frames','K formulas','pixel convention','timestamps','image schema'],
            'approximate_mapping':['native projection/depth precision'],'provider_native':['lighting/photometry','Taichi fields','native GL frusta']}}
