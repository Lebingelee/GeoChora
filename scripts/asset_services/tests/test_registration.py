# 作用：验证新服务注册只修改指定配置块且可重复执行。
# 输入输出：临时客户端配置 -> 替换旧服务、保留其他入口与一次备份。
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deployment import register_mcp


class RegistrationTests(unittest.TestCase):
    """验证注册脚本的配置保留和幂等性。"""

    def test_preserve_existing_and_repeat(self):
        """替换资产服务入口，保留其他设置并验证重复运行无变化。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.toml'
            original = (
                'model = "existing-model"\n'
                '[mcp_servers.trellis2]\ncommand = "existing-python"\n'
                '[mcp_servers.trellis2.env]\nCUSTOM = "keep"\n'
                '[mcp_servers.trellis2-new]\ncommand = "outdated"\n'
                '[mcp_servers.trellis2-new.env]\nOLD = "remove"\n'
                '[mcp_servers.unrelated]\ncommand = "keep-python"\n'
                '[projects.example]\ntrust_level = "trusted"\n')
            config.write_text(original, encoding='utf-8')
            (root / 'deployment').mkdir()
            for name in register_mcp.SERVICES.values():
                (root / 'services' / name).mkdir(parents=True)
                (root / 'services' / name / 'server.py').touch()
            with patch.multiple(register_mcp, ROOT=root, DEPENDENCIES=root, CONFIG=config, TRELLIS_PYTHON=Path(sys.executable)):
                register_mcp.main()
                first = config.read_text(encoding='utf-8')
                parsed = tomllib.loads(first)
                self.assertEqual(parsed['mcp_servers']['trellis2']['args'], [str(root / 'services/trellis2/server.py')])
                self.assertNotIn('trellis2-new', parsed['mcp_servers'])
                self.assertEqual(parsed['mcp_servers']['unrelated'], {'command': 'keep-python'})
                self.assertEqual(parsed['model'], 'existing-model')
                self.assertEqual(parsed['projects'], tomllib.loads(original)['projects'])
                self.assertEqual(len(parsed['mcp_servers']), 4)
                register_mcp.main()
                self.assertEqual(config.read_text(encoding='utf-8'), first)
                backups = list(root.glob('config.before-*.toml'))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_text(encoding='utf-8'), original)


if __name__ == '__main__':
    unittest.main()
