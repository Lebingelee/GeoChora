# 作用：供 asset-creation skill 在不启动仿真器的情况下，对交付 USD 逐项机器核验断言表（claims.json）。
# verify_claims：输入 USD 路径与断言表路径，返回逐项实测值与 passed，并写出结果 JSON。
# collect_meshes：输入 prim 子树，返回世界坐标顶点与三角面，供包围盒与容腔射线测量。
# main：命令行入口，正常核验返回 0 全过、1 存在失败；程序异常直接抛出。
import json
import re
import sys
from pathlib import Path

import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade

DEFAULT_SIZE_TOL = 0.005
DEFAULT_LIMIT_TOL = 0.5
DEFAULT_COVERAGE = 0.3
CAVITY_GRID = 12
RAY_CHUNK = 16
JOINT_TYPES = {'PhysicsRevoluteJoint': 'revolute', 'PhysicsPrismaticJoint': 'prismatic'}
AXES = {'-X': (-1, 0, 0), '-Y': (0, -1, 0), '-Z': (0, 0, -1),
        'X': (1, 0, 0), 'Y': (0, 1, 0), 'Z': (0, 0, 1)}


def collect_meshes(prim):
    """收集 prim 子树内全部网格的世界坐标顶点与三角面。"""
    out = []
    for child in Usd.PrimRange(prim):
        if not child.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(child)
        points = mesh.GetPointsAttr().Get()
        if not points:
            continue
        pts = np.asarray(points, dtype=np.float64)
        transform = np.asarray(
            UsdGeom.Xformable(child).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
        pts = pts @ transform[:3, :3] + transform[3, :3]
        counts = mesh.GetFaceVertexCountsAttr().Get()
        indices = mesh.GetFaceVertexIndicesAttr().Get()
        tris = []
        cursor = 0
        for n in counts:
            face = indices[cursor:cursor + n]
            tris.extend((face[0], face[i], face[i + 1]) for i in range(1, n - 1))
            cursor += n
        out.append((str(child.GetPath()), pts, np.asarray(tris, dtype=np.int64).reshape(-1, 3)))
    return out


def ray_first_hits(origins, direction, tris_all, max_dist):
    """返回每条射线对三角面集的首次命中距离，未命中记 max_dist。"""
    if len(tris_all) == 0:
        return np.full(len(origins), max_dist)
    v0 = tris_all[:, 0]
    e1 = tris_all[:, 1] - v0
    e2 = tris_all[:, 2] - v0
    d = direction / np.linalg.norm(direction)
    pvec = np.cross(d, e2)
    det = np.einsum('tj,tj->t', e1, pvec)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    hits = np.full(len(origins), max_dist)
    for start in range(0, len(origins), RAY_CHUNK):
        chunk = origins[start:start + RAY_CHUNK]
        tvec = chunk[:, None, :] - v0[None, :, :]
        u = np.einsum('rtj,tj->rt', tvec, pvec) * inv
        qvec = np.cross(tvec, e1[None, :, :])
        v = np.einsum('j,rtj->rt', d, qvec) * inv
        t = np.einsum('tj,rtj->rt', e2, qvec) * inv
        valid = ok[None, :] & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6) & (t < max_dist)
        t_masked = np.where(valid, t, max_dist)
        hits[start:start + RAY_CHUNK] = t_masked.min(axis=1)
    return hits


def preview_values(prim):
    """读取 prim 绑定材质的 UsdPreviewSurface 不透明度与金属度，未编写取默认值。"""
    material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    if not material:
        return None
    for child in Usd.PrimRange(material.GetPrim()):
        shader = UsdShade.Shader(child)
        if shader and shader.GetIdAttr().Get() == 'UsdPreviewSurface':
            opacity = shader.GetInput('opacity')
            metallic = shader.GetInput('metallic')
            opacity = opacity.Get() if opacity and opacity.Get() is not None else 1.0
            metallic = metallic.Get() if metallic and metallic.Get() is not None else 0.0
            return float(opacity), float(metallic)
    return 1.0, 0.0


def check_claim(stage, asset_prim, meshes, claim, meters):
    """核验单条断言，返回含 measured 与 passed 的结果字典。"""
    ctype = claim['type']
    result = {'id': claim.get('id', ctype), 'type': ctype, 'passed': False, 'measured': None}
    if ctype == 'bounds':
        pts = np.vstack([m[1] for m in meshes]) * meters
        size = (pts.max(axis=0) - pts.min(axis=0)).tolist()
        tol = claim.get('tol', DEFAULT_SIZE_TOL)
        result['measured'] = [round(v, 5) for v in size]
        result['passed'] = all(abs(a - b) <= tol for a, b in zip(size, claim['size']))
    elif ctype == 'joint':
        joints = []
        for child in Usd.PrimRange(asset_prim):
            kind = JOINT_TYPES.get(child.GetTypeName())
            if kind is None or kind != claim.get('joint_type', kind):
                continue
            if 'pattern' in claim and not re.search(claim['pattern'], child.GetName(), re.I):
                continue
            typed = UsdPhysics.RevoluteJoint(child) if kind == 'revolute' else UsdPhysics.PrismaticJoint(child)
            if 'axis' in claim and typed.GetAxisAttr().Get() != claim['axis']:
                continue
            lower = typed.GetLowerLimitAttr().Get()
            upper = typed.GetUpperLimitAttr().Get()
            scale = 1.0 if kind == 'revolute' else meters
            joints.append({'name': child.GetName(), 'axis': typed.GetAxisAttr().Get(),
                           'lower': round(lower * scale, 5), 'upper': round(upper * scale, 5)})
        result['measured'] = joints
        tol = claim.get('tol', DEFAULT_LIMIT_TOL)
        result['passed'] = len(joints) == claim.get('count', len(joints)) and all(
            ('lower' not in claim or abs(j['lower'] - claim['lower']) <= tol) and
            ('upper' not in claim or abs(j['upper'] - claim['upper']) <= tol) for j in joints)
    elif ctype == 'count':
        names = [child.GetName() for child in Usd.PrimRange(asset_prim)
                 if re.search(claim['pattern'], child.GetName(), re.I)]
        result['measured'] = len(names)
        result['passed'] = len(names) == claim['min'] if claim.get('exact') else len(names) >= claim['min']
    elif ctype == 'material':
        rows = []
        for child in Usd.PrimRange(asset_prim):
            if not re.search(claim['pattern'], child.GetName(), re.I):
                continue
            values = preview_values(child)
            rows.append({'name': child.GetName(),
                         'opacity': None if values is None else round(values[0], 4),
                         'metallic': None if values is None else round(values[1], 4)})
        result['measured'] = rows
        cls = claim['class']
        result['passed'] = bool(rows) and all(
            r['opacity'] is not None and
            (r['opacity'] < 0.99 if cls == 'transparent' else
             r['metallic'] >= 0.9 if cls == 'metal' else
             r['opacity'] >= 0.99 and r['metallic'] < 0.9) for r in rows)
    elif ctype == 'cavity':
        direction = np.asarray(AXES[claim['direction']] if isinstance(claim['direction'], str)
                               else claim['direction'], dtype=np.float64)
        tris = np.vstack([m[1][m[2]] for m in meshes]) * meters
        pts = np.vstack([m[1] for m in meshes]) * meters
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        axis = int(np.argmax(np.abs(direction)))
        face = lo[axis] if direction[axis] > 0 else hi[axis]
        origin_axis_value = face - direction[axis] * 0.001
        u_axis, v_axis = [i for i in range(3) if i != axis]
        grid = np.linspace(0.05, 0.95, CAVITY_GRID)
        origins = []
        for u in grid:
            for v in grid:
                p = [0.0, 0.0, 0.0]
                p[axis] = origin_axis_value
                p[u_axis] = lo[u_axis] + u * (hi[u_axis] - lo[u_axis])
                p[v_axis] = lo[v_axis] + v * (hi[v_axis] - lo[v_axis])
                origins.append(p)
        max_dist = float(hi[axis] - lo[axis]) + 0.01
        depths = ray_first_hits(np.asarray(origins), direction, tris, max_dist)
        min_depth = claim['min_depth']
        seen = depths < max_dist
        coverage = float(np.mean(seen & (depths >= min_depth)))
        result['measured'] = {'coverage': round(coverage, 4),
                              'max_depth': round(float(depths[seen].max()) if seen.any() else 0.0, 5)}
        result['passed'] = coverage >= claim.get('coverage', DEFAULT_COVERAGE) and \
            result['measured']['max_depth'] >= min_depth
    else:
        raise ValueError('未知断言类型：' + ctype)
    return result


def verify_claims(usd_path, claims_path, out_path=None):
    """核验断言表并写出结果。

    Args:
        usd_path: 交付 USD 路径。
        claims_path: 断言表 JSON 路径，含 assets 列表，每项有 id、prim 与 claims。
        out_path: 结果输出路径，默认断言表同级 checks/claims_result.json。

    Returns:
        dict: usd 路径、逐断言结果与总体 passed。
    """
    stage = Usd.Stage.Open(str(usd_path))
    meters = UsdGeom.GetStageMetersPerUnit(stage)
    claims_doc = json.loads(Path(claims_path).read_text(encoding='utf-8-sig'))
    results = []
    for asset in claims_doc.get('assets', []):
        prim = stage.GetPrimAtPath(asset['prim'])
        if not prim:
            for claim in asset.get('claims', []):
                results.append({'asset': asset['id'], 'id': claim.get('id'), 'type': claim['type'],
                                'passed': False, 'measured': 'prim 不存在：' + asset['prim']})
            continue
        meshes = collect_meshes(prim)
        for claim in asset.get('claims', []):
            row = check_claim(stage, prim, meshes, claim, meters)
            row['asset'] = asset['id']
            results.append(row)
    report = {'usd': str(usd_path), 'claims': results,
              'passed': all(r['passed'] for r in results)}
    out_path = Path(out_path) if out_path else Path(claims_path).parent / 'checks' / 'claims_result.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    """命令行入口：python verify_claims.py <usd> <claims.json> [out.json]。"""
    if len(sys.argv) < 3:
        print('用法：verify_claims.py <usd> <claims.json> [out.json]', file=sys.stderr)
        return 2
    report = verify_claims(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    failed = [r for r in report['claims'] if not r['passed']]
    print('断言核验：{} 项，失败 {} 项'.format(len(report['claims']), len(failed)))
    for row in failed:
        print('  失败 {} {}: {}'.format(row.get('asset'), row.get('id'), row.get('measured')))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
