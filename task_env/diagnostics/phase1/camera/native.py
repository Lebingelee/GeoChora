"""Microfixture physics and native projection readback; diagnostics only."""
import numpy as np
from ....artifacts import CanonicalStateView
from ....runtime.sessions.common import pose
from ..conformance.adapters import GeoPhysProbe, MuJoCoProbe


def parent_probe(provider,recipe):
    specification={'probe_id':'p1_4_parent','recipe':{'source_xml':recipe['parent_source_xml'],
        'semantic_bindings':{'bodies':{'calibration/parent':'parent'},'joints':{'calibration/slide':'slide'}}}}
    probe=(GeoPhysProbe if provider=='geophys' else MuJoCoProbe)(specification)
    if provider=='geophys':
        probe.physics.write_qvel(np.array([recipe['initial_velocity_m_s']],dtype=np.float32))
        probe.physics.synchronize_kinematic_state(update_site_jacobians=False)
    else:
        probe.data.qvel[:]=recipe['initial_velocity_m_s']
        probe.mj.mj_forward(probe.model,probe.data)
    return probe


def canonical_parent(probe,step):
    read=probe.read()
    p=read['bodies']['calibration/parent'];j=read['joints']['calibration/slide']
    return CanonicalStateView('canonical-state-v0','SI_right_handed_z_up_wxyz',step,read['time'],
        {'calibration/slide':j['position']},{'calibration/slide':j['velocity']},
        {'calibration/parent':pose(p['position'],p['quaternion_wxyz'])})


def native_projection(provider,session,points):
    c=session._geometry
    if provider=='geophys':
        import taichi as ti
        # Owned public native RayCamera, not a borrowed visualizer private handle.
        camera=session._native_camera
        @ti.kernel
        def project(points:ti.types.ndarray(dtype=ti.f32,ndim=2),pixels:ti.types.ndarray(dtype=ti.f32,ndim=2)):
            for i in range(points.shape[0]):
                x,y,z=camera.project(ti.Vector([points[i,0],points[i,1],points[i,2]]),c.width,c.height)
                pixels[i,0]=x;pixels[i,1]=c.height-y
        result=np.zeros((len(points),2),dtype=np.float32)
        project(np.array(points,dtype=np.float32),result)
        return result.astype(float)
    views=session._renderer.scene.camera
    position=(np.array(views[0].pos)+np.array(views[1].pos))/2
    forward=np.array(views[0].forward,dtype=float);forward/=np.linalg.norm(forward)
    up=np.array(views[0].up,dtype=float);up/=np.linalg.norm(up)
    right=np.cross(forward,up)
    near=float(views[0].frustum_near);top=float(views[0].frustum_top);bottom=float(views[0].frustum_bottom)
    width=(top-bottom)*c.width/c.height;center=float(views[0].frustum_center)
    pixels=[]
    for point in points:
        relative=np.array(point)-position;z=relative@forward
        x=(relative@right)*near/z;y=(relative@up)*near/z
        pixels.append([c.width*(.5+(x-center)/width),c.height*(top-y)/(top-bottom)])
    return np.array(pixels)
