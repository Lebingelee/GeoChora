"""Execution repository identity; a branch label is never an implementation hash."""
from pathlib import Path
import subprocess


def execution_identity(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[4]
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    return {'head': git('rev-parse', 'HEAD'),
            'branch': git('branch', '--show-current') or None,
            'dirty_status': git('status', '--short', '--branch').splitlines()}
