"""S1 analytical wrench-reference oracle, independent of runtime outcomes."""
import numpy as np
from .native import wrench_at

def test_gravity_force_moments_about_distinct_points():
    # A 1 N downward force at x=1m: moment +1Nm about origin, +0.5Nm about COM.
    f=np.array([0.,0.,-1.]);point=np.array([1.,0.,0.]);zero=np.zeros(3)
    np.testing.assert_allclose(wrench_at(f,zero,point,zero),[0.,1.,0.],atol=1e-14)
    np.testing.assert_allclose(wrench_at(f,zero,point,np.array([.5,0.,0.])),[0.,.5,0.],atol=1e-14)

def test_wrench_reference_translation_identity():
    f=np.array([2.,3.,5.]);tau=np.array([.1,.2,.3]);p=np.array([.7,.8,.9]);a=np.array([.2,.3,.1]);b=np.array([.4,.2,.5])
    np.testing.assert_allclose(wrench_at(f,tau,p,a)-wrench_at(f,tau,p,b),np.cross(b-a,f),atol=1e-14)
