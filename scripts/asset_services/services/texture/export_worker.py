# 作用：在 CPU 阶段调用 Blender，将生成的 GLB 打包为可查看文件。
# 输入输出：result.json 中的 glb -> 同名 blend，更新 artifacts.blend。
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.service_config import BLENDER
from common.worker_io import write_result


def main():
    """等待 Blender 打包完成，再发布包含 Blend 的交付清单。

    Returns:
        None: 输出与 GLB 同名的 blend 和更新后的 result.json，失败时非零退出。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--result_path', default='result.json')
    args = parser.parse_args()
    result_path = Path(args.result_path).resolve()
    result = json.loads(result_path.read_text(encoding='utf-8'))
    output = Path(result['artifacts']['glb']).with_suffix('.blend')
    with tempfile.TemporaryDirectory(prefix='asset-texture-export-',
            dir=Path(os.environ['LOCALAPPDATA']) / 'Temp' if os.name == 'nt' else None) as work:
        subprocess.run([
            str(BLENDER), '-b', '--factory-startup', '--python-exit-code', '1',
            '--python', str(Path(__file__).with_name('export_blend.py')), '--',
            str(result_path), str(output),
        ], cwd=work, stdin=subprocess.DEVNULL, check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    result['artifacts']['blend'] = str(output)
    os.chdir(result_path.parent)
    write_result(result['artifacts'], result['metadata'])


if __name__ == '__main__':
    main()
