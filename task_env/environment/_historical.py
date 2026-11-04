"""Environment construction for legacy trajectory replay.

This is a compatibility boundary, not exact historical source reconstruction.
"""


def make_replay_env(uid, *, config=None, render_mode=None, **kwargs):
    if uid == 'pick-cube-v1':
        raise RuntimeError(
            'historical PickCube TaskEnv was retired from current develop; '
            'restore the immutable v1.0.0 source for historical execution'
        )
    if uid == 'nut-assembly-square-v1':
        from task_env.environment.configuration import resolve_task_env_config
        from task_env.tasks.nut_assembly.task import NutAssemblyEnv

        return NutAssemblyEnv(
            config=resolve_task_env_config(NutAssemblyEnv, config),
            render_mode=render_mode,
            **kwargs,
        )
    from task_env import make_env

    return make_env(uid, config=config, render_mode=render_mode, **kwargs)
