#!/usr/bin/env python3
"""Check that a GeoChora checkout is ready for Codex and the Task Harness.

    python scripts/setup/doctor.py [--core DIR] [--codex-home DIR]

Prints one JSON object: overall status, one entry per check (ok / warn /
fail with detail) and the next steps to take. Exit status is 0 when nothing
failed, 1 otherwise. Read-only: it runs interpreters with ``-c`` probes and
never installs, downloads or edits configuration. Standard library only.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None

ASSET_SERVERS = {'trellis2': 'trellis2', 'ultrashape': 'ultrashape', 'trellis-texturing': 'texture'}
MODEL_COUNT = 6
LOCK = 'workspace/locks/shared_native_execution.lock'


def _run(command, *, cwd=None, env=None, timeout=120):
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, f'{type(error).__name__}: {error}'
    if result.returncode == 0:
        return 0, result.stdout.strip()
    last_error = (result.stderr.strip().splitlines() or [result.stdout.strip()])[-1]
    return result.returncode, last_error


class Doctor:
    def __init__(self, core, codex_home):
        self.core = core
        self.codex_home = codex_home
        self.checks = []

    def add(self, name, status, detail, next_step=None):
        self.checks.append({'name': name, 'status': status, 'detail': detail, **({'next': next_step} if next_step else {})})

    def probe_env(self):
        env = dict(os.environ)
        env['PYTHONPATH'] = f'{self.core / "GeoPhys/src"}{os.pathsep}{self.core}'
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        return env

    def git(self):
        code, branch = _run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=self.core)
        _, head = _run(['git', 'rev-parse', '--short', 'HEAD'], cwd=self.core)
        _, status = _run(['git', 'status', '--porcelain'], cwd=self.core)
        lines = [line for line in status.splitlines() if line]
        untracked = [line[3:] for line in lines if line.startswith('??')]
        modified = [line[3:] for line in lines if not line.startswith('??')]
        detail = {'branch': branch, 'head': head, 'modified': modified[:20], 'untracked': untracked[:20]}
        if code:
            self.add('git', 'fail', detail, 'Run doctor inside a GeoChora git checkout.')
        elif modified or untracked:
            self.add('git', 'warn', detail, 'Harness checks require a clean Core checkout: commit, stash or remove these paths.')
        else:
            self.add('git', 'ok', detail)
        _, submodules = _run(['git', 'submodule', 'status'], cwd=self.core)
        missing = [line.split()[1] for line in submodules.splitlines() if line.startswith('-')]
        self.add('submodules', 'fail' if missing else 'ok', {'missing': missing} if missing else 'checked out',
                 'git submodule update --init --recursive' if missing else None)

    def interpreters(self):
        core_python = os.environ.get('GEOCHORA_CORE_PYTHON') or sys.executable
        code, out = _run([core_python, '-c', 'import task_env, mujoco; print(mujoco.__version__)'],
                         cwd=self.core, env=self.probe_env())
        self.add('core_python', 'fail' if code else 'ok', {'python': core_python, 'mujoco' if not code else 'error': out},
                 'Install task_env/requirements.txt into GEOCHORA_CORE_PYTHON.' if code else None)
        geophys_python = os.environ.get('GEOCHORA_GEOPHYS_PYTHON') or core_python
        code, out = _run([geophys_python, '-c', 'import geophys; print(geophys.__file__)'],
                         cwd=self.core, env=self.probe_env())
        self.add('geophys_python', 'warn' if code else 'ok', {'python': geophys_python, 'result': out},
                 'GeoPhys routes need GEOCHORA_GEOPHYS_PYTHON with GeoPhys requirements (Linux x86_64).' if code else None)
        isaac = os.environ.get('GEOCHORA_ISAAC_PYTHON') or str(self.core / 'workspace/environments/isaacsim-6.2.0/bin/python')
        if Path(isaac).is_file() and os.access(isaac, os.X_OK):
            self.add('isaac_python', 'ok', {'python': isaac})
        else:
            self.add('isaac_python', 'warn', {'python': isaac, 'result': 'not found'},
                     'Optional: Isaac routes need GEOCHORA_ISAAC_PYTHON pointing at an Isaac Sim 6.2 interpreter.')

    def lock(self):
        path = self.core / LOCK
        self.add('native_lock', 'ok' if path.is_file() else 'fail', str(path),
                 None if path.is_file() else f'mkdir -p {path.parent} && touch {path}')

    def assets(self):
        home = Path(os.environ.get('ASSET_SERVICES_HOME', self.core / 'workspace/asset-services'))
        receipt = home / 'model-receipt.json'
        models = []
        if receipt.is_file():
            models = sorted(json.loads(receipt.read_text(encoding='utf-8')).get('models', {}))
        runtimes = {name: (home / f'runtime/{name}/bin/python').is_file() for name in ('trellis2', 'ultrashape')}
        blender = os.environ.get('BLENDER_PATH') or shutil.which('blender') or next(
            (str(path) for path in sorted(home.glob('runtime/blender-*/blender'))), None)
        detail = {'home': str(home), 'models': f'{len(models)}/{MODEL_COUNT}', 'runtimes': runtimes, 'blender': blender}
        ready = len(models) >= MODEL_COUNT and all(runtimes.values()) and blender
        self.add('asset_models', 'ok' if ready else 'warn', detail,
                 None if ready else 'Asset generation is optional for the Task Harness; run scripts/setup/setup.sh to prepare it.')
        return home

    def mcp(self, asset_home):
        config = self.codex_home / 'config.toml'
        if tomllib is None or not config.is_file():
            self.add('codex_mcp', 'warn', {'config': str(config), 'result': 'missing' if tomllib else 'needs Python 3.11+'},
                     'Run scripts/setup/setup.sh (or register_mcp.py) to register the asset MCP services.')
            return
        servers = tomllib.loads(config.read_text(encoding='utf-8')).get('mcp_servers', {})
        problems, found = [], {}
        for name, directory in ASSET_SERVERS.items():
            entry = servers.get(name)
            if not entry:
                problems.append(f'{name}: not registered')
                continue
            script = (entry.get('args') or [''])[0]
            found[name] = script
            if Path(script).resolve() != (self.core / 'scripts/asset_services/services' / directory / 'server.py').resolve():
                problems.append(f'{name}: points at {script}, not this checkout')
            home = entry.get('env', {}).get('ASSET_SERVICES_HOME')
            if home and Path(home).resolve() != asset_home.resolve():
                problems.append(f'{name}: ASSET_SERVICES_HOME={home}')
        batch = servers.get('experiment-batch')
        if not batch:
            problems.append('experiment-batch: not registered')
        else:
            code_root = batch.get('env', {}).get('PYTHONPATH', '')
            found['experiment-batch'] = code_root
            if Path(code_root).resolve() != (self.core / 'scripts').resolve():
                problems.append(f'experiment-batch: PYTHONPATH={code_root}, not this checkout')
        detail = {'config': str(config), 'servers': found, **({'problems': problems} if problems else {})}
        self.add('codex_mcp', 'warn' if problems else 'ok', detail,
                 'Run scripts/setup/setup.sh from this checkout to re-register (it backs up config.toml first).'
                 if problems else None)

    def run(self):
        self.git()
        self.interpreters()
        self.lock()
        self.mcp(self.assets())
        status = 'fail' if any(c['status'] == 'fail' for c in self.checks) else \
            'warn' if any(c['status'] == 'warn' for c in self.checks) else 'ok'
        return {'schema': 'geochora-doctor-v1', 'core': str(self.core), 'status': status, 'checks': self.checks,
                'next_steps': [c['next'] for c in self.checks if c.get('next') and c['status'] != 'ok']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--core', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--codex-home', type=Path,
                        default=Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')))
    args = parser.parse_args(argv)
    report = Doctor(args.core.resolve(), args.codex_home).run()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report['status'] == 'fail' else 0


if __name__ == '__main__':
    raise SystemExit(main())
