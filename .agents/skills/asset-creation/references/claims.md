# USD 断言表

本 skill 的 `scripts/verify_claims.py` 使用 Python、NumPy 和 `pxr`，不启动 Isaac Sim。路径参数可使用绝对路径，结果文件可显式指定：

```bash
python /path/to/skills/asset-creation/scripts/verify_claims.py \
  /work/output/assets/example/asset.usda \
  /work/claims.json \
  /work/output/instances/variant_01/checks/claims_result.json
```

省略第三个路径时，结果写入断言表同级的 `checks/claims_result.json`。退出码为 0 表示所有已提供断言通过，1 表示存在失败，2 表示缺少命令行参数；程序错误保留 traceback。

## 基本格式

```json
{
  "assets": [
    {
      "id": "example",
      "prim": "/World/Example",
      "claims": [
        {"id": "dimensions", "type": "bounds", "size": [1.0, 0.5, 0.8], "tol": 0.005},
        {"id": "parts", "type": "count", "pattern": "^Panel", "min": 2, "exact": true}
      ]
    }
  ]
}
```

`prim` 指向被检查资产根节点。名称、尺寸、阈值和断言数量按当前需求填写，示例数值不作为默认需求。必须提供适用的非空断言；脚本的空列表结果不证明检查过任何内容。

## 支持的断言

| type | 字段 | 实际检查 |
| --- | --- | --- |
| `bounds` | `size: [x,y,z]`，可选 `tol`（默认 0.005 m） | 子树 mesh 顶点的世界轴对齐尺寸，换算为米 |
| `joint` | 可选 `joint_type: revolute/prismatic`、`pattern`、`axis`、`count`、`lower`、`upper`、`tol` | 匹配关节的类型、轴与限位；旋转为度，移动为米；默认限位容差 0.5，按当前单位显式选择合适值 |
| `count` | `pattern`、`min`，可选 `exact` | 按正则匹配子树 prim 名；默认至少 `min` 个，`exact: true` 表示恰好 |
| `material` | `pattern`、`class: transparent/metal/opaque` | 读取匹配 prim 绑定的 UsdPreviewSurface 标量不透明度和金属度；`opaque` 为不透明非金属类别 |
| `cavity` | `direction: X/-X/Y/-Y/Z/-Z` 或三维向量、`min_depth`，可选 `coverage`（默认 0.3） | 从外包围盒发射采样射线，估计开口方向的深度和覆盖比例；深度单位为米 |

`pattern` 为忽略大小写的 Python 正则。关节检查应显式设置非零 `count`，避免没有匹配关节时得到空结果。

## 覆盖范围

脚本基于默认时刻的 mesh、属性和材质标量进行核验，不替代 PhysX 操作、碰撞、支撑、连通性与外观审计。几何基元不是 mesh；复杂材质、纹理驱动参数与其他着色系统须另行检查。包围尺寸和容腔只说明该采样方法的结果，不能推断全部物理或视觉要求通过。
