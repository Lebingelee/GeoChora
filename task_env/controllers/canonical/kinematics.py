"""Geochora-owned audited Panda chain FK/Jacobian from neutral source bytes."""
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
import numpy as np
from ...utils.rotation import quat_wxyz_to_matrix,rotvec_to_matrix,matrix_to_quat_wxyz
from ...artifacts import PoseWorld
from ...artifacts.contracts import Contract

ARM=tuple(f'panda-v1/joint{i}' for i in range(1,8))
FINGERS=('panda-v1/finger_joint1','panda-v1/finger_joint2')


def transform(element):
    if any(k in element.attrib for k in ('euler','axisangle','xyaxes','zaxis')):raise ValueError('unsupported source rotation representation')
    t=np.eye(4);t[:3,3]=np.fromstring(element.get('pos','0 0 0'),sep=' ')
    t[:3,:3]=quat_wxyz_to_matrix(np.fromstring(element.get('quat','1 0 0 0'),sep=' '))
    return t


@dataclass(frozen=True)
class PandaTcpProfileV1(Contract):
    """Versioned hand-local TCP transform used by a source-bound Panda profile."""

    schema_version: str
    tcp_id: str
    hand_frame_id: str
    position_m: tuple[float, float, float]
    quaternion_wxyz: tuple[float, float, float, float]

    def validate(self):
        if self.schema_version != 'panda-tcp-profile-v1':
            raise ValueError('unsupported Panda TCP profile schema')
        entity_id, separator, suffix = self.tcp_id.partition('/')
        if not separator or not entity_id or not self.hand_frame_id:
            raise ValueError('unsupported Panda TCP identity/frame')
        if suffix == 'hand-origin-tcp-v1':
            if (tuple(self.position_m) != (0.0, 0.0, 0.0)
                    or tuple(self.quaternion_wxyz) != (1.0, 0.0, 0.0, 0.0)):
                raise ValueError('hand-origin TCP v1 is the identity transform from hand')
        elif suffix == 'pickcube-ee-offset-v1':
            if (entity_id != 'panda-v1' or self.hand_frame_id != 'hand'
                    or tuple(self.position_m) != (0.0, 0.0, 0.0584)
                    or tuple(self.quaternion_wxyz) != (1.0, 0.0, 0.0, 0.0)):
                raise ValueError('PickCube TCP v1 is the exact +58.4 mm hand-local USD frame')
        else:
            raise ValueError('unsupported Panda TCP identity/frame')

    @property
    def identity_hash(self):
        import json
        return hashlib.sha256(json.dumps(
            self.to_mapping(),sort_keys=True,separators=(',',':'),allow_nan=False,
        ).encode('utf-8')).hexdigest()

    def local_transform(self):
        value = np.eye(4)
        value[:3, :3] = quat_wxyz_to_matrix(np.asarray(self.quaternion_wxyz, dtype=float))
        value[:3, 3] = np.asarray(self.position_m, dtype=float)
        return value


@dataclass(frozen=True)
class PandaTcpProfileV2(Contract):
    """Source-hash-bound transform from an authored hand body to a named TCP."""

    schema_version: str
    tcp_id: str
    hand_frame_id: str
    position_m: tuple[float, float, float]
    quaternion_wxyz: tuple[float, float, float, float]
    source_xml_sha256: str
    source_site_name: str

    def validate(self):
        if self.schema_version != 'panda-tcp-profile-v2':
            raise ValueError('unsupported source-bound Panda TCP profile schema')
        if (type(self.tcp_id) is not str or not self.tcp_id.strip()
                or type(self.hand_frame_id) is not str or not self.hand_frame_id.strip()
                or type(self.source_site_name) is not str or not self.source_site_name.strip()):
            raise ValueError('source-bound Panda TCP identity and frame names must be nonempty')
        if (type(self.source_xml_sha256) is not str
                or len(self.source_xml_sha256) != 64
                or any(char not in '0123456789abcdef' for char in self.source_xml_sha256)):
            raise ValueError('source-bound Panda TCP requires a lowercase source XML SHA-256')
        position = np.asarray(self.position_m, dtype=np.float64)
        quaternion = np.asarray(self.quaternion_wxyz, dtype=np.float64)
        if (position.shape != (3,) or quaternion.shape != (4,)
                or not np.isfinite(position).all() or not np.isfinite(quaternion).all()
                or not np.isclose(np.linalg.norm(quaternion), 1.0, rtol=0.0, atol=1e-8)):
            raise ValueError('source-bound Panda TCP transform must be finite with a unit quaternion')

    @property
    def identity_hash(self):
        import json
        return hashlib.sha256(json.dumps(
            self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode('utf-8')).hexdigest()

    def local_transform(self):
        self.validate()
        value = np.eye(4)
        value[:3, :3] = quat_wxyz_to_matrix(np.asarray(self.quaternion_wxyz, dtype=float))
        value[:3, 3] = np.asarray(self.position_m, dtype=float)
        return value


def _body_world_transform(root, body_name):
    """Compose named body ancestors from the MJCF world frame."""
    worldbody = root.find('worldbody')
    if worldbody is None:
        raise ValueError('kinematic MJCF has no worldbody')

    def find(node, path):
        current = path
        if node.tag == 'body':
            current = (*path, node)
            if node.get('name') == body_name:
                return current
        for child in node:
            result = find(child, current)
            if result is not None:
                return result
        return None

    path = find(worldbody, ())
    if path is None:
        raise ValueError(f'kinematic MJCF is missing source body: {body_name}')
    value = np.eye(4)
    for element in path:
        value = value @ transform(element)
    return value


def _hand_to_site_transform(hand, site_name):
    """Resolve one source site through its authored fixed body ancestry."""
    found = []

    def visit(node, parent_transform):
        for child in node:
            if child.tag == 'body':
                visit(child, parent_transform @ transform(child))
            elif child.tag == 'site' and child.get('name') == site_name:
                found.append(parent_transform @ transform(child))

    visit(hand, np.eye(4))
    if len(found) != 1:
        raise ValueError(f'hand frame must contain exactly one source TCP site: {site_name}')
    return found[0]


def derive_panda_tcp_profile_v2(xml, *, tcp_id, hand_frame_id, site_name):
    """Create a source-hash-bound profile from one authored nested MJCF site."""
    root = ET.fromstring(xml)
    source_sha256 = hashlib.sha256(xml.encode() if isinstance(xml, str) else bytes(xml)).hexdigest()
    hand = next((body for body in root.iter('body') if body.get('name') == hand_frame_id), None)
    if hand is None:
        raise ValueError(f'kinematic MJCF is missing TCP hand body: {hand_frame_id}')
    local = _hand_to_site_transform(hand, site_name)
    profile = PandaTcpProfileV2(
        'panda-tcp-profile-v2', str(tcp_id), str(hand_frame_id),
        tuple(float(value) for value in local[:3, 3]),
        tuple(float(value) for value in matrix_to_quat_wxyz(local[:3, :3])),
        source_sha256, str(site_name),
    )
    profile.validate()
    return profile


PANDA_HAND_ORIGIN_TCP_V1 = PandaTcpProfileV1(
    'panda-tcp-profile-v1', 'panda-main/hand-origin-tcp-v1', 'hand',
    (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0),
)
PANDA_PICKCUBE_EE_TCP_V1 = PandaTcpProfileV1(
    'panda-tcp-profile-v1', 'panda-v1/pickcube-ee-offset-v1', 'hand',
    (0.0, 0.0, 0.0584), (1.0, 0.0, 0.0, 0.0),
)


class PandaKinematics:
    def __init__(self,xml,*,tcp_profile=None,native_prefix='',base_body_id=None):
        raw_xml = xml.encode() if isinstance(xml, str) else bytes(xml)
        self.source_sha256=hashlib.sha256(raw_xml).hexdigest();root=ET.fromstring(raw_xml)
        if root.find('compiler').get('angle','degree')!='radian':raise ValueError('kinematic source must use radians')
        native_prefix=str(native_prefix)
        root_body_id = f'{native_prefix}link0' if base_body_id is None else str(base_body_id)
        # Retain the exact source for an optional, lazy gravity calculation.
        # Existing position-only construction and its identity are unchanged.
        self._gravity_source_xml = raw_xml
        self._gravity_native_prefix = native_prefix
        self._gravity_root_body_id = root_body_id
        body=next((item for item in root.iter('body') if item.get('name')==root_body_id),None)
        if body is None:raise ValueError(f'unsupported Panda chain; source root body is absent: {root_body_id}')
        self.base_transform=_body_world_transform(root, root_body_id);self.chain=[];self.limits=[]
        defaults_node=root.find(".//default[@class='panda']/joint")
        defaults={} if defaults_node is None else defaults_node.attrib
        for i in range(1,8):
            children=body.findall('body');next_body=next((b for b in children if b.get('name')==f'{native_prefix}link{i}'),None)
            if next_body is None:raise ValueError('unsupported Panda chain')
            joints=next_body.findall('joint')
            if len(joints)!=1 or joints[0].get('name')!=f'{native_prefix}joint{i}':raise ValueError('unsupported Panda joint structure')
            j=dict(defaults);j.update(joints[0].attrib)
            if j.get('type','hinge')!='hinge' or j.get('ref','0')!='0':raise ValueError('only zero-reference hinges supported')
            axis=np.fromstring(j.get('axis','0 0 1'),sep=' ');axis/=np.linalg.norm(axis)
            pivot=np.fromstring(j.get('pos','0 0 0'),sep=' ')
            self.chain.append((transform(next_body),axis,pivot));self.limits.append(np.fromstring(j['range'],sep=' '));body=next_body
        if tcp_profile is not None and isinstance(tcp_profile, PandaTcpProfileV2):
            hand_name=tcp_profile.hand_frame_id
        else:
            hand_name=f'{native_prefix}hand'
        hand=body.find(f"body[@name='{hand_name}']")
        if hand is None:
            raise ValueError('Panda source is missing the declared hand body')
        if tcp_profile is None:
            site=hand.find("site[@name='nutassembly_ee_site']")
            if site is None:
                raise ValueError('legacy Panda kinematics requires nutassembly_ee_site; provide an explicit TCP profile')
            self.tip=transform(hand)@transform(site)
            self.tcp_profile=None
        else:
            if isinstance(tcp_profile, PandaTcpProfileV2):
                tcp_profile.validate()
                if tcp_profile.source_xml_sha256 != self.source_sha256:
                    raise ValueError('source-bound TCP profile belongs to different MJCF bytes')
                if hand.get('name') != tcp_profile.hand_frame_id:
                    raise ValueError('source-bound TCP profile names a different authored hand body')
            elif not isinstance(tcp_profile,PandaTcpProfileV1):
                raise TypeError('Panda kinematics TCP must be PandaTcpProfileV1 or PandaTcpProfileV2')
            else:
                tcp_profile.validate()
                if hand.get('name') != f'{native_prefix}{tcp_profile.hand_frame_id}':
                    raise ValueError('Panda TCP frame is not the materialized hand body')
            self.tip=transform(hand)@tcp_profile.local_transform()
            self.tcp_profile=tcp_profile
        self.limits=np.array(self.limits)

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

    def gravity_support(self, q, fingers, gravity_world, world_from_base_rotation, *, include_fingers=False):
        """Return Panda arm support torques in N m, from source body mass/COM.

        This is a pure calculation, not an applied-control receipt. The input
        rotation maps base-local vectors to world; gravity is in world m/s².
        Only the exact Panda link/hand/finger subtree is admitted. No scene
        object, contact, payload, velocity or solver state enters this result.
        """
        q = np.asarray(q, dtype=np.float64)
        fingers = np.asarray(fingers, dtype=np.float64)
        gravity = np.asarray(gravity_world, dtype=np.float64)
        rotation = np.asarray(world_from_base_rotation, dtype=np.float64)
        if (q.shape != (7,) or fingers.shape != (2,) or gravity.shape != (3,)
                or rotation.shape != (3, 3) or not all(np.isfinite(x).all()
                    for x in (q, fingers, gravity, rotation))):
            raise ValueError('gravity support requires finite q[7], fingers[2], gravity[3] and rotation[3,3]')
        if type(include_fingers) is not bool:
            raise TypeError('include_fingers must be a boolean')
        if (not np.allclose(rotation.T @ rotation, np.eye(3), rtol=0, atol=1e-8)
                or not np.isclose(np.linalg.det(rotation), 1.0, rtol=0, atol=1e-8)):
            raise ValueError('gravity support base rotation must be a proper orthonormal rotation')
        if not hasattr(self, '_gravity_bodies'):
            self._gravity_bodies = self._compile_gravity_bodies()
        gravity_base = rotation.T @ gravity
        coordinates = dict(zip(
            [*(f'{self._gravity_native_prefix}joint{i}' for i in range(1, 8)),
             *(f'{self._gravity_native_prefix}finger_joint{i}' for i in (1, 2))],
            (*q, *fingers), strict=True,
        ))
        torque = np.zeros(7, dtype=np.float64)
        finger_force = np.zeros(2, dtype=np.float64)
        origins, axes = {}, {}
        world = {self._gravity_root_body_id: np.eye(4)}
        for name, parent, fixed, joint, kind, axis, pivot, mass, com in self._gravity_bodies:
            body = world[parent] @ fixed
            if joint:
                if kind == 'hinge':
                    index = int(joint.removeprefix(self._gravity_native_prefix + 'joint')) - 1
                    origins[index] = body[:3, 3] + body[:3, :3] @ pivot
                    axes[index] = body[:3, :3] @ axis
                    motion = np.eye(4)
                    motion[:3, :3] = rotvec_to_matrix(axis * coordinates[joint])
                    motion[:3, 3] = pivot - motion[:3, :3] @ pivot
                else:
                    finger_index = int(joint.removeprefix(self._gravity_native_prefix + 'finger_joint')) - 1
                    finger_axis = body[:3, :3] @ axis
                    motion = np.eye(4)
                    motion[:3, 3] = axis * coordinates[joint]
                body = body @ motion
            world[name] = body
            position = body[:3, 3] + body[:3, :3] @ com
            force = mass * gravity_base
            if joint and kind == 'slide':
                finger_force[finger_index] -= np.dot(finger_axis, force)
            for index in range(7):
                if index in axes and self._gravity_is_descendant(name, index):
                    torque[index] -= np.dot(axes[index], np.cross(position - origins[index], force))
        return (torque, finger_force) if include_fingers else torque

    def _gravity_is_descendant(self, body, arm_index):
        parents = self._gravity_parent
        anchor = f'{self._gravity_native_prefix}link{arm_index + 1}'
        while body != self._gravity_root_body_id:
            if body == anchor:
                return True
            body = parents[body]
        return False

    def _compile_gravity_bodies(self):
        """Fail closed on anything other than the source-bound Panda subtree."""
        root = ET.fromstring(self._gravity_source_xml)
        prefix = self._gravity_native_prefix
        bases = [b for b in root.iter('body') if b.get('name') == self._gravity_root_body_id]
        if len(bases) != 1:
            raise ValueError('gravity source must contain exactly one selected Panda base')
        base = bases[0]
        allowed = {*(f'{prefix}link{i}' for i in range(1, 8)),
                   f'{prefix}hand', f'{prefix}left_finger', f'{prefix}right_finger'}
        expected_parent = {f'{prefix}link{i}': (self._gravity_root_body_id if i == 1
                            else f'{prefix}link{i-1}') for i in range(1, 8)}
        expected_parent.update({f'{prefix}hand': f'{prefix}link7',
                                f'{prefix}left_finger': f'{prefix}hand',
                                f'{prefix}right_finger': f'{prefix}hand'})
        expected_joint = {f'{prefix}link{i}': (f'{prefix}joint{i}', 'hinge') for i in range(1, 8)}
        expected_joint.update({f'{prefix}left_finger': (f'{prefix}finger_joint1', 'slide'),
                               f'{prefix}right_finger': (f'{prefix}finger_joint2', 'slide')})
        panda_default = root.find(".//default[@class='panda']/joint")
        finger_default = root.find(".//default[@class='finger']/joint")
        defaults = {} if panda_default is None else dict(panda_default.attrib)
        finger_defaults = dict(defaults)
        if finger_default is not None:
            finger_defaults.update(finger_default.attrib)
        rows, parents, seen = [], {}, set()
        def visit(parent):
            for child in parent.findall('body'):
                name = child.get('name')
                if name not in allowed or name in seen:
                    raise ValueError(f'gravity source contains unsupported or repeated robot body {name!r}')
                if parent.get('name') != expected_parent[name]:
                    raise ValueError(f'gravity source body {name!r} has an unsupported parent')
                seen.add(name); parents[name] = parent.get('name')
                inertial = child.find('inertial')
                if inertial is None or inertial.get('mass') is None or inertial.get('pos') is None:
                    raise ValueError(f'gravity source body {name!r} requires explicit mass and COM')
                mass = float(inertial.get('mass')); com = np.fromstring(inertial.get('pos'), sep=' ')
                if not np.isfinite(mass) or mass <= 0 or com.shape != (3,) or not np.isfinite(com).all():
                    raise ValueError(f'gravity source body {name!r} has invalid mass or COM')
                joints = child.findall('joint'); expected = expected_joint.get(name)
                if len(joints) != (1 if expected else 0):
                    raise ValueError(f'gravity source body {name!r} has unsupported joint topology')
                joint = kind = None; axis = pivot = np.zeros(3)
                if expected:
                    raw = dict(finger_defaults if expected[1] == 'slide' else defaults)
                    raw.update(joints[0].attrib); joint = raw.get('name'); kind = raw.get('type', 'hinge')
                    if (joint, kind) != expected or float(raw.get('ref', 0)) != 0:
                        raise ValueError(f'gravity source body {name!r} has unsupported joint')
                    axis = np.fromstring(raw.get('axis', '0 0 1'), sep=' ')
                    pivot = np.fromstring(raw.get('pos', '0 0 0'), sep=' ')
                    if (axis.shape != (3,) or pivot.shape != (3,) or not np.isfinite(axis).all()
                            or not np.isfinite(pivot).all() or np.linalg.norm(axis) < 1e-12):
                        raise ValueError(f'gravity source body {name!r} has invalid joint axis or pivot')
                    axis = axis / np.linalg.norm(axis)
                fixed = transform(child)
                if not np.isfinite(fixed).all():
                    raise ValueError(f'gravity source body {name!r} has invalid transform')
                rows.append((name, parent.get('name'), fixed, joint, kind, axis, pivot, mass, com))
                visit(child)
        visit(base)
        if seen != allowed:
            raise ValueError(f'gravity source does not contain the exact Panda body set: {sorted(allowed - seen)}')
        self._gravity_parent = parents
        return tuple(rows)
