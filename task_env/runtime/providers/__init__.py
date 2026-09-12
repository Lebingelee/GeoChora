"""TaskEnv runtime provider implementations.

Provider implementations are intentionally not imported from this package
root.  The runtime factory selects one explicit provider at construction
time, keeping Taichi/Triton and solver-heavy modules out of ordinary
``import task_env``.
"""

__all__ = []
