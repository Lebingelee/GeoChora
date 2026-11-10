# 作用：隔离模型推理，验证官方归一化输出恢复米制坐标、轴向和材质导出。
# 输入输出：不对称平移网格与模拟官方输出 -> GLB 几何及默认参数断言。
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.texture import worker


class CoordinatesTests(unittest.TestCase):
    """覆盖容易被单位立方体掩盖的平移、尺度及 Y/Z 轴恢复错误。"""

    def test_official_output_restored_with_uv_seams(self):
        """模拟官方归一化及接缝拆点，断言默认参数和落盘几何。"""
        source = trimesh.creation.box(extents=[0.4, 0.7, 1.8])
        source.apply_translation([1.3, -2.1, 0.9])
        calls = {}

        class Pipeline:
            def run(self, mesh, image, **parameters):
                """模拟官方输出归一化 Y-up 网格及 UV 接缝拆点。"""
                calls.update(parameters)
                center = mesh.bounds.mean(axis=0)
                positions = (mesh.vertices - center) * (0.99999 / mesh.extents.max())
                output = trimesh.Trimesh(positions[mesh.faces].reshape(-1, 3),
                    np.arange(len(mesh.faces) * 3).reshape(-1, 3), process=False)
                output.visual = trimesh.visual.TextureVisuals(
                    uv=np.tile([[0, 0], [1, 0], [0, 1]], (len(mesh.faces), 1)),
                    material=trimesh.visual.material.PBRMaterial(
                        baseColorTexture=Image.new('RGB', (2, 2), 'white')))
                return output

        fake = types.ModuleType('services.texture.model_adapter')
        fake.load_pipeline = lambda resolution: Pipeline()
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            np.savez(root / 'input.npz', vertices=source.vertices, faces=source.faces)
            Image.new('RGB', (8, 8), 'white').save(root / 'input.png')
            try:
                os.chdir(root)
                with patch.dict(sys.modules, {'services.texture.model_adapter': fake}), \
                     patch.object(worker, 'configure_runtime'), \
                     patch.object(sys, 'argv', ['worker.py', '--mesh_path', str(root / 'input.npz'),
                                               '--image_path', str(root / 'input.png')]):
                    worker.main()
                result = json.loads((root / 'result.json').read_text(encoding='utf-8'))
                output = trimesh.load(result['artifacts']['glb'], force='mesh', process=False)
                zup = output.vertices[:, [0, 2, 1]] * [1, -1, 1]
                np.testing.assert_allclose(zup[output.faces], source.vertices[source.faces], atol=1e-6)
                self.assertEqual(calls['texture_size'], 2048)
                self.assertEqual(calls['tex_slat_sampler_params'],
                    {'steps': 12, 'guidance_strength': 1.0, 'guidance_interval': [0.6, 0.9]})
                self.assertEqual(set(result['artifacts']), {'glb'})
            finally:
                os.chdir(previous)


if __name__ == '__main__':
    unittest.main()
