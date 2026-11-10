# 作用：验证输入拒绝和交付清单，防止坏网格进入 GPU 或成功返回缺失产物。
# 输入输出：临时 NPZ、图片与结果文件 -> 校验异常或绝对产物路径。
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from common.worker_io import load_mesh, save_image, write_result


class WorkerIOTests(unittest.TestCase):
    """覆盖业务边界的输入与输出数据完整性。"""

    def test_inputs_and_delivery(self):
        """拒绝坏面索引和透明图，结果清单只发布存在的文件。"""
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                vertices = [[0,0,0], [1,0,0], [0,1,0]]
                np.savez('mesh.npz', vertices=vertices, faces=[[0,1,2]])
                self.assertEqual(load_mesh('mesh.npz')[1].tolist(), [[0,1,2]])
                for faces in ([[0,1,3]], [[0,0,1]], [[0.,1.,2.]]):
                    np.savez('bad.npz', vertices=vertices, faces=faces)
                    with self.assertRaises(ValueError):
                        load_mesh('bad.npz')
                Image.new('RGBA', (8,8), (255,0,0,0)).save('empty.png')
                with self.assertRaises(ValueError):
                    save_image('empty.png')
                Image.new('RGB', (8,8), 'red').save('reference.png')
                save_image('reference.png')
                with self.assertRaises(RuntimeError):
                    write_result({'mesh':'missing.npz'}, {})
                write_result({'mesh':'mesh.npz'}, {'units':'meter'})
                result = json.loads(Path('result.json').read_text())
                self.assertEqual(result['artifacts']['mesh'], str(Path('mesh.npz').resolve()))
            finally:
                os.chdir(previous)


if __name__ == '__main__':
    unittest.main()
