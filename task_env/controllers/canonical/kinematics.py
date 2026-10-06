"""Geochora-owned audited Panda chain FK/Jacobian from neutral source bytes."""
import hashlib
import xml.etree.ElementTree as ET
import numpy as np
from ...utils.rotation import quat_wxyz_to_matrix,rotvec_to_matrix,matrix_to_quat_wxyz
from ...artifacts import PoseWorld

ARM=tuple(f'panda-v1/joint{i}' for i in range(1,8))
FINGERS=('panda-v1/finger_joint1','panda-v1/finger_joint2')


def transform(element):
    if any(k in element.attrib for k in ('euler','axisangle','xyaxes','zaxis')):raise ValueError('unsupported source rotation representation')
    t=np.eye(4);t[:3,3]=np.fromstring(element.get('pos','0 0 0'),sep=' ')
    t[:3,:3]=quat_wxyz_to_matrix(np.fromstring(element.get('quat','1 0 0 0'),sep=' '))
    return t


class PandaKinematics:
    def __init__(self,xml):
        self.source_sha256=hashlib.sha256(xml.encode()).hexdigest();root=ET.fromstring(xml)
        if root.find('compiler').get('angle','degree')!='radian':raise ValueError('kinematic source must use radians')
        body=root.find(".//body[@name='link0']");self.base_transform=transform(body);self.chain=[];self.limits=[]
        defaults=root.find(".//default[@class='panda']/joint").attrib
        for i in range(1,8):
            children=body.findall('body');next_body=next((b for b in children if b.get('name')==f'link{i}'),None)
            if next_body is None:raise ValueError('unsupported Panda chain')
            joints=next_body.findall('joint')
            if len(joints)!=1 or joints[0].get('name')!=f'joint{i}':raise ValueError('unsupported Panda joint structure')
            j=dict(defaults);j.update(joints[0].attrib)
            if j.get('type','hinge')!='hinge' or j.get('ref','0')!='0':raise ValueError('only zero-reference hinges supported')
            axis=np.fromstring(j.get('axis','0 0 1'),sep=' ');axis/=np.linalg.norm(axis)
            pivot=np.fromstring(j.get('pos','0 0 0'),sep=' ')
            self.chain.append((transform(next_body),axis,pivot));self.limits.append(np.fromstring(j['range'],sep=' '));body=next_body
        hand=body.find("body[@name='hand']");site=hand.find("site[@name='nutassembly_ee_site']")
        self.tip=transform(hand)@transform(site);self.limits=np.array(self.limits)

    def fk_jacobian(self,q):
        q=np.asarray(q,dtype=float)
        if q.shape!=(7,) or not np.isfinite(q).all():raise ValueError('seven finite joint coordinates required')
        world=self.base_transform.copy();origins=[];axes=[]
        for value,(fixed,axis,pivot) in zip(q,self.chain,strict=True):
            world=world@fixed;origins.append(world[:3,3]+world[:3,:3]@pivot);axes.append(world[:3,:3]@axis)
            motion=np.eye(4);motion[:3,:3]=rotvec_to_matrix(axis*value);motion[:3,3]=pivot-motion[:3,:3]@pivot
            world=world@motion
        tip=world@self.tip
        jp=np.array([np.cross(axis,tip[:3,3]-origin) for axis,origin in zip(axes,origins,strict=True)]).T
        jr=np.array(axes).T
        return tip,np.vstack((jp,jr))

    def pose(self,q):
        t,_=self.fk_jacobian(q);return PoseWorld(tuple(float(v) for v in t[:3,3]),tuple(float(v) for v in matrix_to_quat_wxyz(t[:3,:3])))
