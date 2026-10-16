"""Single selected provider-neutral NutAssembly task route."""

from .task import NutAssemblyReferenceEnv, REFERENCE_ENV_ID


def __getattr__(name):
    if name == "build_reference":
        raise ImportError(
            "the package-level historical build_reference API is retired; "
            "use task_env.tasks.nut_assembly.task.build_reference for the selected route"
        )
    raise AttributeError(name)


__all__ = ["NutAssemblyReferenceEnv", "REFERENCE_ENV_ID"]
