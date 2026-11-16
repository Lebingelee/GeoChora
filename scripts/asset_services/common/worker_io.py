# 作用：校验模型输入并保存统一的交付清单；本模块不使用 GPU。
# 输入输出：load_mesh() -> 顶点和三角面；save_image() -> 图片副本；write_result() -> result.json。
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def load_mesh(path):
    """读取有限、非空、索引有效且无退化面的 NPZ 网格，保持原面顺序。"""
    with np.load(path, allow_pickle=False) as data:
        vertices, faces = data['vertices'], data['faces']
    if (vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices)
            or not np.isfinite(vertices).all()):
        raise ValueError('vertices 必须是非空有限坐标 [N,3]')
    if (faces.ndim != 2 or faces.shape[1] != 3 or not len(faces)
            or not np.issubdtype(faces.dtype, np.integer)
            or faces.min() < 0 or faces.max() >= len(vertices)):
        raise ValueError('faces 必须是索引有效的整数三角面 [M,3]')
    vertices = vertices.astype(np.float32)
    if not np.isfinite(vertices).all():
        raise ValueError('顶点超出 float32 可表示范围')
    triangles = vertices[faces].astype(np.float64)
    area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0],
                                  triangles[:, 2] - triangles[:, 0]), axis=1)
    if not np.all(area > 0):
        raise ValueError('网格包含零面积三角面，请先清理')
    return vertices.astype(np.float32), faces.astype(np.int32)


def save_image(path, output='input.png'):
    """读取图片并在任务目录保存统一朝向的 RGBA 副本，拒绝全透明图片。"""
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert('RGBA')
    if image.getchannel('A').getextrema()[1] == 0:
        raise ValueError('参考图完全透明')
    image.save(output)
    return image


def write_result(artifacts, metadata):
    """验证交付文件非空后原子保存绝对路径清单与生成参数。"""
    paths = {name: str(Path(path).resolve()) for name, path in artifacts.items()}
    for path in paths.values():
        if not Path(path).is_file() or Path(path).stat().st_size == 0:
            raise RuntimeError(f'缺少交付文件：{path}')
    temporary = Path('result.next.json')
    temporary.write_text(json.dumps({'artifacts': paths, 'metadata': metadata},
                                   ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace('result.json')
