"""Frame-invariant metric verification independent of trace generation."""
import numpy as np
from scipy.spatial.transform import Rotation
from .offline_windows import relative_pose, drift


def test_relative_pose_invariant_to_world_frame_change():
    ee_R=Rotation.from_euler('xyz',[.2,-.1,.3]).as_matrix()
    nut_R=Rotation.from_euler('xyz',[-.4,.5,.6]).as_matrix()
    ee_p=np.array([.4,.2,.7]);nut_p=np.array([.5,.1,.6])
    A=Rotation.from_euler('xyz',[.7,.2,-.8]).as_matrix();b=np.array([3.,-2.,5.])
    p,R=relative_pose(ee_p,ee_R,nut_p,nut_R)
    moved_p,moved_R=relative_pose(A@ee_p+b,A@ee_R,A@nut_p+b,A@nut_R)
    np.testing.assert_allclose(moved_p,p,atol=1e-15)
    np.testing.assert_allclose(moved_R,R,atol=1e-15)


def test_geodesic_metric_known_translation_and_angle():
    p=np.array([.003,.004,0.]);R=Rotation.from_rotvec([0.,0.,.1]).as_matrix()
    translation,angle=drift(p,R,np.zeros(3),np.eye(3))
    np.testing.assert_allclose(translation,.005,atol=1e-15)
    np.testing.assert_allclose(angle,.1,atol=1e-14)
