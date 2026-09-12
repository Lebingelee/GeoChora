"""Unitree Go2 deployment-contract task package.

This package is intentionally separate from ``go2_walk``: its actor never
receives simulator base linear velocity, starts at the deployment-calibrated
root height, and applies the reference training noise vector.
"""

from .task import Go2WalkDeployEnv, Go2WalkDeployHeightEnv

__all__ = ["Go2WalkDeployEnv", "Go2WalkDeployHeightEnv"]
