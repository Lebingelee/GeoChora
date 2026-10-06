"""Provider-independent defect detectors and render admission negatives."""
from dataclasses import replace
import json
import math
from unittest.mock import patch
import numpy as np
import yaml
from ....artifacts import CanonicalStateView, CapabilityAdmissionError, ExecutionSpec, PoseWorld
from ....observations.canonical_camera import CameraGeometry, MOUNT_FROM_CAMERA, resolve_camera, intrinsics, fov_x, inverse_transform, project_world, back_project_world, lower_legacy_camera
from ....observations.canonical_camera.geometry import optical_depth
from ....observations.canonical_camera.images import normalize_rgb, CanonicalCameraObservation
from ....render.camera import create_camera_session, render_manifest
from .fixtures import camera, render_source, fixture_artifact


def state(step=0,time=0,x=0):
    return CanonicalStateView('canonical-state-v0','SI_right_handed_z_up_wxyz',step,time,
        {'calibration/slide':x},{'calibration/slide':.5},
        {'calibration/parent':PoseWorld((x,0.,0.),(1.,0.,0.,0.))})


def pure_checks(tolerance):
    c = camera('calibration/parent')
    m = resolve_camera(c,state(x=.3))
    T = np.array(m.T_world_from_camera)
    points = np.array([[.1,-.15,0.],[.5,.1,0.]])
    pixels = project_world(m,points)
    K = intrinsics(c)
    results = {'inverse':np.max(abs(T@inverse_transform(T)-np.eye(4))) <= tolerance,
        'proper_mount_rotation':abs(np.linalg.det(np.array(MOUNT_FROM_CAMERA)[:3,:3])-1) <= tolerance,
        'optical_axes':np.array_equal(np.array(MOUNT_FROM_CAMERA)[:3,:3],[[0,0,1],[-1,0,0],[0,-1,0]]),
        'transform_composition':np.max(abs(T-np.array([[1,0,0,.4],[0,-1,0,-.15],[0,0,-1,2],[0,0,0,1]])))<=tolerance,
        'K':abs(K[0,0]-32/math.tan(math.pi/6))<=tolerance and K[0,2]==40 and K[1,2]==32,
        'fov_y_fy_roundtrip':abs(2*math.atan(c.height/(2*K[1,1]))-c.fov_y)<=tolerance,
        'fov_x':abs(fov_x(c)-2*math.atan(80/64*math.tan(math.pi/6)))<=tolerance,
        'projection_back_projection':np.max(abs(back_project_world(m,pixels,np.full(2,2.))-points))<=tolerance,
        'pixel_center':np.max(abs(back_project_world(m,[[40.5,32.5]],[2.])[0]-[.4+1/K[0,0],-.15-1/K[1,1],0]))<=tolerance,
        'camera_JSON_roundtrip':CameraGeometry.from_mapping(json.loads(json.dumps(c.to_mapping()))).identity_hash==c.identity_hash,
        'camera_YAML_roundtrip':CameraGeometry.from_mapping(yaml.safe_load(yaml.safe_dump(c.to_mapping()))).identity_hash==c.identity_hash,
        'metadata_roundtrip':type(m).from_mapping(m.to_mapping()).to_mapping()==m.to_mapping()}
    yy,xx=np.indices((c.height,c.width))
    ray_norm=np.sqrt(1+((xx+.5-40)/K[0,0])**2+((yy+.5-32)/K[1,1])**2)
    results['ray_depth_conversion']=np.max(abs(optical_depth(2*ray_norm,m,native_convention='ray_distance_m')-2))<=tolerance
    rgb=np.linspace(0,1,c.height*c.width*3,dtype=np.float32).reshape(c.height,c.width,3)
    for layout in ('HWC','CHW'):
        for dtype in ('float32','uint8'):
            option=replace(c,rgb_layout=layout,rgb_dtype=dtype)
            image=normalize_rgb(rgb,option)
            expected=rgb if dtype=='float32' else np.rint(rgb*255).astype(np.uint8)
            if layout=='CHW':expected=expected.transpose(2,0,1)
            obs=CanonicalCameraObservation(image,np.ones((c.height,c.width),dtype=np.float32),resolve_camera(option,state()))
            results[f'RGB_{layout}_{dtype}']=np.array_equal(obs.rgb,expected) and obs.rgb.dtype==np.dtype(dtype)
    for label,values in (('unknown',dict(c.to_mapping(),extrinsic=[])),('schema',dict(c.to_mapping(),schema_version='camera-observation-v9')),
                         ('reflection',dict(c.to_mapping(),T_mount_from_camera=((1,0,0,0),(0,1,0,0),(0,0,-1,0),(0,0,0,1))))):
        try:CameraGeometry.from_mapping(values);results[f'reject_{label}']=False
        except (ValueError,TypeError):results[f'reject_{label}']=True
    from ....environment.config import CameraSpec
    legacy=CameraSpec('legacy',position=(.1,-.15,2.))
    lowered=lower_legacy_camera(legacy,task_artifact_hash=fixture_artifact().identity_hash,parent_frame='world')
    results['legacy_mount_preserved']=np.array_equal(np.array(lowered.T_parent_from_mount)[:3,:3],np.eye(3)) and lowered.T_mount_from_camera==MOUNT_FROM_CAMERA
    results['missing_semantic_parent_fails']=False
    try:resolve_camera(replace(c,parent_frame='absent/parent'),state())
    except KeyError:results['missing_semantic_parent_fails']=True
    return {k:bool(v) for k,v in results.items()}


def admission_checks():
    c=camera('world');source=render_source();checks={}
    for provider in ('geophys','mujoco'):
        actual=render_manifest(provider)
        execution=ExecutionSpec(provider,'p1_4_microfixture',provider,'cpu',0,'strict')
        restricted=replace(actual,capabilities=tuple(v for v in actual.capabilities if v.name!='depth_camera'))
        with patch('task_env.render.camera.api._construct_admitted',side_effect=AssertionError('native construction entered')) as constructor:
            try:create_camera_session(c,execution,source=source,manifest=restricted);rejected=False
            except CapabilityAdmissionError:rejected=True
            checks[provider]={'rejected':rejected,'native_construction_count':constructor.call_count}
        with patch('task_env.render.camera.api._construct_admitted',return_value='admitted') as constructor:
            accepted=create_camera_session(c,execution,source=source)=='admitted'
            checks[provider]['positive_admission']=accepted and constructor.call_count==1
    with patch('task_env.render.camera.api._construct_admitted') as constructor:
        try:create_camera_session(c,ExecutionSpec('geophys','fixture','unsupported','cpu',0,'strict'),source=source);rejected=False
        except CapabilityAdmissionError:rejected=True
        checks['unsupported']={'rejected':rejected,'native_construction_count':constructor.call_count}
    with patch('task_env.render.camera.api._construct_admitted') as constructor:
        try:create_camera_session(c,ExecutionSpec('geophys','fixture','mujoco','cpu',0,'strict'),source=source);rejected=False
        except CapabilityAdmissionError:rejected=True
        checks['cross_pairing']={'rejected':rejected,'native_construction_count':constructor.call_count}
    return checks
