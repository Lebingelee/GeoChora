"""Explicit recovery-only legacy construction; never imported by active factory.

v1.0.0 is the canonical recovery source. Running current historical modules is
not exact historical source reconstruction and cannot grant old qualification.
Rendering/camera probes and legacy H5 replay use this boundary deliberately.
"""
def make_historical_env(uid, *, config=None, render_mode=None, **kwargs):
    from task_env.environment.configuration import resolve_task_env_config
    if uid == 'pick-cube-v1':
        raise RuntimeError(
            'historical PickCube TaskEnv was retired from current develop; '
            'restore the immutable v1.0.0 source for historical execution'
        )
    elif uid == 'nut-assembly-square-v1':
        from task_env.tasks.nut_assembly.task import NutAssemblyEnv
        cls = NutAssemblyEnv
    else:
        from task_env import make_env
        return make_env(uid, config=config, render_mode=render_mode, **kwargs)
    return cls(config=resolve_task_env_config(cls, config), render_mode=render_mode, **kwargs)
