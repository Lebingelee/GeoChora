"""Reusable, snapshot-only geometric relations for terminal-state diagnostics.

No task IDs, trajectory history, planned actions or reference labels. Relations
reuse PredicateResult's available/true, available/false and unavailable
contract. Geometry is evidence of compatibility, not contact causality or full
task success. Z-up metres and scalar-first local-to-world rotations are explicit.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
from itertools import combinations
import math

import numpy as np

from validation.sampling import conjunction, predicate, result_mapping
from validation.geometry import ConvexPiece, box_piece, horizontal_separation, support_measurements
from validation.geometry import quat_wxyz_to_matrix


@dataclass(frozen=True)
class TerminalPolicy:
    """Frozen diagnostic bands, NOT added requirements on the source task.

    The interval between pass/reject bounds is deliberately unresolved. Row
    residual is normalized by object width. No equal-spacing, fixed row heading,
    fixed object identity, or dwell-time requirement is imposed.
    """
    distance_pass_m: float = 0.001
    distance_reject_m: float = 0.003
    angle_pass_deg: float = 2.0
    angle_reject_deg: float = 10.0
    row_pass_widths: float = 0.25
    row_reject_widths: float = 0.75

    def __post_init__(self):
        if any(isinstance(x, bool) or not math.isfinite(x) or x <= 0 for x in asdict(self).values()):
            raise ValueError('finite positive measurement bands required')
        if not (self.distance_pass_m < self.distance_reject_m
                and self.angle_pass_deg < self.angle_reject_deg < 90
                and self.row_pass_widths < self.row_reject_widths):
            raise ValueError('pass band must be narrower than reject band')


def check(value, reason=None, **measurements):
    return {**result_mapping(predicate(value, reason or 'boundary_or_missing_evidence')),
            'measurements': measurements}


def combine(checks):
    return result_mapping(conjunction([predicate(c['value'], c.get('reason') or 'relation_unavailable') for c in checks]))


def band(error, good, bad):
    if not np.isfinite(error):
        return None
    return True if error <= good else False if error >= bad else None


def vector(mapping, name, size):
    value = mapping.get(name)
    if value is None:
        return None
    a = np.asarray(value, float)
    if a.shape != (size,) or not np.isfinite(a).all():
        return None
    return a


class TerminalScene:
    """One observation and explicit asset bindings; missing poses remain unknown.

    Instances own their input snapshot and cache transformed collision pieces.
    Input geometry must describe
    actual collision geometry as closed convex pieces, never an arbitrary mesh
    silently replaced by its convex hull. Sphere symmetry permits missing sphere
    rotations. Rigid/container rotations must be measured unit WXYZ quaternions.
    """

    def __init__(self, *, positions, orientations_wxyz, geometry, policy=TerminalPolicy()):
        geometry = deepcopy(geometry)
        if geometry.get('units') != 'm' or geometry.get('quaternion_order') != 'wxyz':
            raise ValueError('explicit metre/WXYZ geometry required')
        for radius in [s['radius_m'] for s in geometry.get('spheres', {}).values()] + list(geometry.get('gripper_enclosing_radii_m', {}).values()):
            if isinstance(radius, bool) or not math.isfinite(radius) or radius <= 0:
                raise ValueError('geometry radii must be finite and positive')
        for body in geometry.get('rigids', {}).values():
            center = np.asarray(body['geometric_center_local_m'], float)
            if center.shape != (3,) or not np.isfinite(center).all() or not body['pieces']:
                raise ValueError('rigid geometry needs a finite geometric center and collision pieces')
            axis = body.get('long_axis_local')
            if axis is not None:
                axis = np.asarray(axis, float)
                width = body['width_m']
                if (axis.shape != (3,) or not np.isfinite(axis).all() or not np.isclose(np.linalg.norm(axis), 1)
                        or isinstance(width, bool) or not math.isfinite(width) or width <= 0):
                    raise ValueError('long-axis binding needs a unit vector and positive width')
        self.positions, self.orientations = deepcopy(positions), deepcopy(orientations_wxyz)
        self.geometry, self.policy = geometry, policy
        self._pieces, self._local, self._gaps = {}, {}, {}
        self.table = box_piece(geometry['table_bounds_world_m'])

    def position(self, name):
        return vector(self.positions, name, 3)

    def rotation(self, name):
        q = vector(self.orientations, name, 4)
        if q is None or abs(np.linalg.norm(q) - 1) > 1e-4:
            return None
        return quat_wxyz_to_matrix(q)

    def pieces(self, name):
        if name in self._pieces:
            return self._pieces[name]
        p, r = self.position(name), self.rotation(name)
        body = self.geometry.get('rigids', {}).get(name)
        if p is None or r is None or body is None:
            return None
        if name not in self._local:
            self._local[name] = [ConvexPiece.from_mesh(s['vertices_m'], s['triangles']) for s in body['pieces']]
        result = [piece.transformed(r, p) for piece in self._local[name]]
        self._pieces[name] = result
        return result

    def _distance(self, error, **measurements):
        return check(band(error, self.policy.distance_pass_m, self.policy.distance_reject_m), **measurements)

    def sphere_inside(self, name, container):
        body = self.geometry.get('spheres', {}).get(name)
        cavity = self.geometry.get('containers', {}).get(container)
        p, o, r = self.position(name), self.position(container), self.rotation(container)
        if body is None or cavity is None or p is None or o is None or r is None:
            return check(None, 'sphere_or_container_pose_binding_missing')
        radius = float(body['radius_m'])
        bounds = np.asarray(cavity['cavity_bounds_local_m'], float)
        if bounds.shape != (2, 3) or not np.isfinite(bounds).all() or np.any(bounds[0] >= bounds[1]):
            raise ValueError('invalid sphere/cavity binding')
        lo, hi = bounds
        local = (p - o) @ r
        margin = float(np.minimum(local - radius - lo, hi - local - radius).min())
        return self._distance(-margin, minimum_cavity_margin_m=margin, center_local_m=local.tolist())

    def sphere_on_table(self, name):
        sphere, p = self.geometry.get('spheres', {}).get(name), self.position(name)
        if sphere is None or p is None:
            return check(None, 'sphere_pose_binding_missing')
        radius = float(sphere['radius_m'])
        if not math.isfinite(radius) or radius <= 0:
            raise ValueError('invalid sphere radius')
        lo, hi = np.asarray(self.geometry['table_bounds_world_m'])
        vertical = abs(float(p[2] - radius - hi[2]))
        margin = float(np.minimum(p[:2] - lo[:2], hi[:2] - p[:2]).min())
        height = self._distance(vertical)
        edge = check(True if margin >= self.policy.distance_pass_m else
                     False if margin <= -self.policy.distance_reject_m else None)
        return {**combine([height, edge]), 'measurements': {'bottom_height_error_m': vertical, 'contact_edge_margin_m': margin},
                'basis': 'sphere_plane_geometric_contact'}

    def released(self, name):
        """Disjoint enclosing spheres prove clearance; overlap proves nothing."""
        p = self.position(name)
        if p is None:
            return check(None, 'object_position_missing')
        if name in self.geometry.get('spheres', {}):
            radius = float(self.geometry['spheres'][name]['radius_m'])
        else:
            body = self.geometry.get('rigids', {}).get(name)
            if body is None:
                return check(None, 'object_geometry_missing')
            radius = max(float(np.linalg.norm(s['vertices_m'], axis=1).max()) for s in body['pieces'])
        radii = self.geometry.get('gripper_enclosing_radii_m', {})
        if not radii:
            return check(None, 'gripper_geometry_missing')
        margins = []
        for link, other_radius in radii.items():
            other = self.position(link)
            if other is None:
                return check(None, 'gripper_position_missing')
            margins.append(float(np.linalg.norm(p - other) - radius - other_radius))
        margin = min(margins)
        return check(True if margin > self.policy.distance_pass_m else None,
                     'enclosing_spheres_overlap_not_proof_of_grasp', minimum_clearance_bound_m=margin)

    def drawer_state(self, name, *, required_opening_m=None):
        config = self.geometry.get('containers', {}).get(name)
        p, r = self.position(name), self.rotation(name)
        if config is None or p is None or r is None:
            return check(None, 'drawer_pose_binding_missing')
        axis = np.asarray(config['opening_axis_world'], float)
        if axis.shape != (3,) or not np.isclose(np.linalg.norm(axis), 1):
            raise ValueError('drawer opening axis must be unit length')
        closed_origin = vector(config, 'closed_origin_world_m', 3)
        if closed_origin is None:
            raise ValueError('finite closed drawer origin required')
        delta = p - closed_origin
        opening = float(delta @ axis)
        lateral = float(np.linalg.norm(delta - opening * axis))
        closed_q = vector(config, 'closed_orientation_wxyz', 4)
        if closed_q is None or abs(np.linalg.norm(closed_q) - 1) > 1e-4:
            return check(None, 'closed_drawer_orientation_binding_missing')
        relative = quat_wxyz_to_matrix(closed_q).T @ r
        angle = float(np.degrees(np.arccos(np.clip((np.trace(relative) - 1) / 2, -1, 1))))
        rail = self._distance(lateral)
        rotation = check(band(angle, self.policy.angle_pass_deg, self.policy.angle_reject_deg))
        if required_opening_m is None:
            target = self._distance(abs(opening))
        else:
            if not math.isfinite(required_opening_m) or required_opening_m <= 0:
                raise ValueError('positive opening clearance required')
            margin = opening - required_opening_m
            target = check(True if margin >= self.policy.distance_pass_m else
                           False if margin <= -self.policy.distance_reject_m else None)
        return {**combine([rail, rotation, target]), 'measurements': {'opening_m': opening,
                'lateral_rail_error_m': lateral, 'rotation_error_deg': angle, 'required_opening_m': required_opening_m}}

    def supported(self, name, lower=None):
        if lower == name:
            raise ValueError('support objects must be distinct')
        upper = self.pieces(name)
        base = [self.table] if lower is None else self.pieces(lower)
        if upper is None or base is None:
            return check(None, 'collision_geometry_or_pose_missing')
        body = self.geometry['rigids'][name]
        center = self.rotation(name) @ np.asarray(body['geometric_center_local_m']) + self.position(name)
        av, bv = np.concatenate([s.vertices for s in base]), np.concatenate([s.vertices for s in upper])
        gap = float(np.maximum(av.min(0) - bv.max(0), bv.min(0) - av.max(0)).max())
        if gap > self.policy.distance_reject_m:
            return check(False, enclosing_box_gap_m=gap)
        result, measurements = support_measurements(base, upper, center,
            self.policy.distance_pass_m, self.policy.distance_reject_m)
        reason = measurements.pop('reason', None)
        return {**check(result, reason, **measurements),
                'basis': 'convex_collision_faces_and_geometric_center_not_contact_force_or_true_COM'}

    def parallel_row(self, names):
        """Parallel axes and a separated row in the horizontal world-XY plane."""
        if len(names) < 3 or len(set(names)) != len(names):
            raise ValueError('at least three distinct objects required')
        centers, axes, widths = [], [], []
        for name in names:
            body = self.geometry.get('rigids', {}).get(name)
            p, r = self.position(name), self.rotation(name)
            if body is None or body.get('long_axis_local') is None or p is None or r is None:
                return check(None, 'long_axis_or_pose_binding_missing')
            centers.append((r @ np.asarray(body['geometric_center_local_m']) + p)[:2])
            axes.append(r @ np.asarray(body['long_axis_local']))
            widths.append(body['width_m'])
        angle = max(float(np.degrees(np.arccos(np.clip(abs(a @ b), 0, 1)))) for a, b in combinations(axes, 2))
        points = np.asarray(centers)
        minimum_center_spacing = min(float(np.linalg.norm(a - b)) for a, b in combinations(points, 2))
        center_check = check(True if minimum_center_spacing > self.policy.distance_reject_m else None,
                             'horizontal_row_centers_not_distinct')
        _, _, vt = np.linalg.svd(points - points.mean(0), full_matrices=False)
        row_error = float(np.max(np.abs((points - points.mean(0)) @ vt[-1])) / min(widths))
        angle_check = check(band(angle, self.policy.angle_pass_deg, self.policy.angle_reject_deg))
        row_check = check(band(row_error, self.policy.row_pass_widths, self.policy.row_reject_widths))
        # Separation and collinearity refer to the same horizontal plane.
        # A vertical gap does not turn stacked objects into a horizontal row.
        pair_checks, gaps = [], []
        for a, b in combinations(names, 2):
            pa, pb = self.pieces(a), self.pieces(b)
            if pa is None or pb is None:
                pair_checks.append(check(None, 'collision_geometry_missing'))
                continue
            key = tuple(sorted((a, b)))
            if key not in self._gaps:
                bounds = []
                for x in pa:
                    for y in pb:
                        bound = float(np.maximum(x.vertices[:, :2].min(0) - y.vertices[:, :2].max(0),
                                                 y.vertices[:, :2].min(0) - x.vertices[:, :2].max(0)).max())
                        bounds.append(bound if bound >= self.policy.distance_pass_m else horizontal_separation(x, y))
                self._gaps[key] = min(bounds)
            gap = self._gaps[key]
            gaps.append(gap)
            pair_checks.append(check(True if gap >= self.policy.distance_pass_m else
                                     False if gap <= -self.policy.distance_reject_m else None))
        return {**combine([angle_check, row_check, center_check, *pair_checks]), 'measurements': {
            'projection_plane': 'world_xy',
            'minimum_projected_center_spacing_m': minimum_center_spacing,
            'maximum_axis_angle_deg': angle, 'maximum_row_residual_widths': row_error,
            'minimum_separating_axis_gap_lower_bound_m': min(gaps) if gaps else None}}
