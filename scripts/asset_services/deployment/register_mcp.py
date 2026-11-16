# 作用：注册三个资产服务，并移除迁移期的 *-new 重复入口。
# 输入输出：本机路径配置 -> mcp_config.toml、用户配置备份及三个正式配置块。
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tomllib

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.service_config import ROOT, TRELLIS_PYTHON, DEPENDENCIES

CONFIG = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml'
SERVICES = {'trellis2':'trellis2', 'ultrashape':'ultrashape', 'trellis-texturing':'texture'}
REPLACED_SERVICES = {*SERVICES, *(name + '-new' for name in SERVICES)}


def configuration():
    """构造三个独立 stdio 服务的 TOML，不加载模型或启动调度器。"""
    blocks = []
    for name, directory in SERVICES.items():
        script = ROOT / 'services' / directory / 'server.py'
        if not script.is_file() or not TRELLIS_PYTHON.is_file():
            raise FileNotFoundError(script)
        blocks.append(
            f'[mcp_servers.{name}]\n'
            f'command = {json.dumps(str(TRELLIS_PYTHON))}\n'
            f'args = {json.dumps([str(script)])}\n'
            'startup_timeout_sec = 30\ntool_timeout_sec = 86400\n'
            f'[mcp_servers.{name}.env]\n'
            f'ASSET_SERVICES_HOME = {json.dumps(str(DEPENDENCIES))}\n'
            'PYTHONIOENCODING = "utf-8"\nPYTHONNOUSERSITE = "1"\n')
    return '\n'.join(blocks)


def main():
    """验证配置，备份后替换资产服务入口，保留其他客户端设置。

    Returns:
        None: 输出片段和注册位置；权限错误直接抛出供人工配置。
    """
    snippet = configuration()
    DEPENDENCIES.mkdir(parents=True, exist_ok=True)
    (DEPENDENCIES / 'mcp_config.toml').write_text(snippet, encoding='utf-8')
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    original = CONFIG.read_text(encoding='utf-8') if CONFIG.exists() else ''
    current = tomllib.loads(original)
    desired = tomllib.loads(snippet)['mcp_servers']
    if (all(current.get('mcp_servers', {}).get(name) == entry for name, entry in desired.items())
            and not any(name + '-new' in current.get('mcp_servers', {}) for name in SERVICES)):
        print('资产服务配置已经一致')
        return
    updated = original
    for name in REPLACED_SERVICES:
        pattern = r'(?ms)^\[mcp_servers\.' + re.escape(name) + r'(?:\.[^\]\r\n]+)?\][^\r\n]*\r?\n.*?(?=^\[|\Z)'
        updated = re.sub(pattern, '', updated)
    updated = updated.rstrip() + '\n\n' + snippet
    parsed = tomllib.loads(updated)
    assert all(parsed['mcp_servers'][name] == entry for name, entry in desired.items())
    for name, entry in current.get('mcp_servers', {}).items():
        if name not in REPLACED_SERVICES:
            assert parsed['mcp_servers'][name] == entry
    if CONFIG.exists():
        backup = CONFIG.with_name('config.before-asset-services-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.toml')
        backup.write_text(original, encoding='utf-8')
    temporary = CONFIG.with_name('config.asset-services.next.toml')
    temporary.write_text(updated, encoding='utf-8')
    temporary.replace(CONFIG)
    print('Registered: ' + ', '.join(SERVICES))


if __name__ == '__main__':
    main()
