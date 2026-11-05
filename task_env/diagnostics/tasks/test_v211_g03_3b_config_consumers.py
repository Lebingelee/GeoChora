"""Concrete CLI and selected configuration precedence checks, without engines."""
from pathlib import Path
from types import SimpleNamespace
import pytest


def executable(path):
    path.write_text('#!/bin/sh\nexit 0\n');path.chmod(0o755);return path


def test_start_cli_overrides_environment_without_running_sdk(monkeypatch,tmp_path):
    from examples import start
    from task_env.utils._paths import GEOPHYS_PROVIDER_ROOT
    cli=executable(tmp_path/'cli python');env_python=executable(tmp_path/'environment python')
    manifest=tmp_path/'delivery.json';manifest.write_text('{}')
    monkeypatch.setenv('ISAAC_SIM_PYTHON',str(env_python))
    calls=[]
    monkeypatch.setattr(start.subprocess,'run',lambda argv,**kwargs: calls.append(argv) or SimpleNamespace(returncode=0))
    assert start.main(['--uid','pick-cube-p16-reference-v1','--provider','isaacsim','--backend','cuda',
        '--renderer','none','--geophys-src',str(GEOPHYS_PROVIDER_ROOT/'src'),
        '--isaac-python',str(cli),'--source-delivery-manifest',str(manifest)])==0
    argv=calls[0];assert argv[argv.index('--isaac-python')+1]==str(cli)


def test_explicit_config_beats_environment_and_inprocess_conflict_rejects(monkeypatch,tmp_path):
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    explicit=str(tmp_path/'explicit-python');implicit=str(tmp_path/'env-python')
    monkeypatch.setenv('ISAAC_SIM_PYTHON',implicit)
    config=resolve_task_env_config(PickCubeReferenceEnv,{'execution':{'physics_provider':'isaacsim',
        'physics_backend':'cuda','physics_device':'cuda:0','deployment':'isolated_worker',
        'interpreter':explicit,'source_delivery_manifest':str(tmp_path/'delivery.json')}})
    assert config.execution_spec_v2.interpreter==explicit
    with pytest.raises(ValueError,match='in-process deployment must use the current interpreter'):
        resolve_task_env_config(PickCubeReferenceEnv,{'execution':{'physics_provider':'mujoco',
            'deployment':'in_process','interpreter':explicit}})
