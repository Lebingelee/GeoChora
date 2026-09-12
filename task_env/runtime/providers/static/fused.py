"""Generic fused static-template articulated runtime.

This module is intentionally independent of a task name.  It owns one
immutable local model and all mutable arrays with a leading world dimension
``(B, local_*)``.  The first executable slice is the no-contact articulated
path (free root plus hinge/slide/ball/universal tree joints).  Contact is kept
as a separate capability because contact rows require an additional local
workspace and a dedicated parity gate.

The implementation uses Torch tensors rather than one ``RigidSolver`` per
world.  Python loops are over the fixed local topology only; every numerical
operation is batched over B and therefore does not create global body/geom
identifiers or per-world solver objects.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import os
from typing import Any

import numpy as np

from ...contracts import (
    DeviceBatchState,
    DeviceResetSelection,
    WorldRandomizationBatch,
    validate_device_reset_selection as validate_reset_selection_contract,
)
from ....utils._device_stack import (
    get_device_stack_provenance,
    get_preloaded_triton_modules,
    preload_device_stack,
)


def _resolve_contact_pgs_modules():
    """Resolve only process-order-audited Triton handles.

    A direct import remains available for lightweight consumers, but it goes
    through the process bootstrap so the resulting handles can be identity
    checked.  Once Taichi is present, the bootstrap records a blocked late
    import and no Triton importer runs.
    """

    record = get_device_stack_provenance()
    if record is None:
        record = preload_device_stack()
    triton_module, language_module = get_preloaded_triton_modules()
    return triton_module, language_module, record.to_dict()


_triton, _tl, _CONTACT_PGS_BOOTSTRAP = _resolve_contact_pgs_modules()


_CONTACT_RESPONSE_TRITON_BACKEND = "triton_active_slot_cholesky_f32_v1"
_CONTACT_RESPONSE_TORCH_BACKEND = "torch_full_rhs_cholesky_v1"
_CONTACT_RESPONSE_TOPOLOGY_P1_BACKEND = (
    "triton_active_slot_topology_child_schur_f32_v1"
)
_CONTACT_RESPONSE_TOPOLOGY_P12_BACKEND = (
    "triton_active_slot_topology_child_schur_root6x6_f32_v1"
)


def _contact_pgs_module_provenance() -> dict[str, Any]:
    """Return a detached JSON-compatible snapshot of the import decision."""

    return dict(_CONTACT_PGS_BOOTSTRAP)


def _select_contact_response_backend(
    *,
    device_type: str,
    contact_enabled: bool,
    contact_precision: str,
    n_dof: int,
    fixed_topology_child_schur: bool = False,
    root_factor_6x6: bool = False,
) -> str:
    """Select the statically eligible contact-response implementation."""

    if fixed_topology_child_schur:
        return (
            _CONTACT_RESPONSE_TOPOLOGY_P12_BACKEND
            if root_factor_6x6
            else _CONTACT_RESPONSE_TOPOLOGY_P1_BACKEND
        )
    if (
        contact_enabled
        and device_type == "cuda"
        and str(contact_precision) == "f32"
        and 0 < int(n_dof) <= 32
        and _triton is not None
    ):
        return _CONTACT_RESPONSE_TRITON_BACKEND
    return _CONTACT_RESPONSE_TORCH_BACKEND


def _select_contact_pgs_backend(
    *,
    device_type: str,
    contact_enabled: bool,
    n_dof: int,
) -> str:
    """Choose the initial PGS route from device and trusted module state."""

    if not contact_enabled:
        return "disabled_explicitly"
    if int(n_dof) <= 0:
        return "no_op_no_dofs"
    if device_type != "cuda":
        return "eager_ordered_slot_sweep_v1"
    if _triton is not None and int(n_dof) <= 256:
        return "triton_fused_axis_world_serial_v2"
    if _triton is not None:
        return "eager_ordered_slot_sweep_v1"
    return "eager_fused_axis_world_serial_v1"


def _contact_pgs_initial_fallback_reason(
    *,
    device_type: str,
    contact_enabled: bool,
    n_dof: int,
    selected: str,
) -> str | None:
    if not contact_enabled or device_type != "cuda":
        return None
    if selected == "triton_fused_axis_world_serial_v2":
        return None
    if int(n_dof) <= 0:
        return "specialization:no_degrees_of_freedom"
    if os.environ.get("GEOPHYS_DISABLE_TRITON") == "1":
        return "bootstrap:triton_disabled"
    if _triton is None:
        return f"bootstrap:{_CONTACT_PGS_BOOTSTRAP['status']}"
    return "specialization:n_dof_exceeds_256"


def _sanitized_contact_pgs_failure(stage: str, error: Exception) -> str:
    return f"{stage}:{type(error).__name__}"


def _contact_pgs_fused_launch_config(n_dof: int) -> dict[str, int]:
    """Return the deterministic fused PGS block width and warp count."""

    block_d = 1
    while block_d < int(n_dof):
        block_d *= 2
    num_warps = 1 if block_d <= 32 else 2 if block_d <= 64 else 4
    return {
        "contact_pgs_fused_block_d": block_d,
        "contact_pgs_fused_num_warps": num_warps,
    }


def _synchronize_contact_pgs_cuda_stream(device) -> None:
    """Surface asynchronous launch failures on the current CUDA stream."""

    import torch

    if torch.cuda.is_available():
        torch.cuda.current_stream(device=device).synchronize()


if _triton is not None:
    @_triton.jit
    def _ground_contact_active_slot_prepare_kernel(
        active_ptr,
        world_active_ptr,
        normal_lambda_ptr,
        tangent_lambda_ptr,
        friction_ptr,
        active_slot_ptr,
        active_count_ptr,
        SLOTS: _tl.constexpr,
        BLOCK_S: _tl.constexpr,
    ):
        """Compact effective slots and normalize skipped warm-start state."""
        world = _tl.program_id(0)
        slot = _tl.arange(0, BLOCK_S)
        slot_mask = slot < SLOTS
        active = _tl.load(
            active_ptr + world * SLOTS + slot,
            mask=slot_mask,
            other=False,
        )
        world_active = _tl.load(world_active_ptr + world)
        effective_active = active & world_active
        active_rank = (
            _tl.cumsum(effective_active.to(_tl.int32), axis=0) - 1
        )
        safe_rank = _tl.where(effective_active, active_rank, 0)
        _tl.store(
            active_slot_ptr + world * SLOTS + safe_rank,
            slot.to(_tl.int32),
            mask=slot_mask & effective_active,
        )
        active_count = _tl.sum(
            effective_active.to(_tl.int32), axis=0
        )
        _tl.store(active_count_ptr + world, active_count)

        # The old fixed-slot sweep visited inactive rows once per iteration.
        # Those visits never changed qvel, but they did idempotently normalize
        # warm-start lambdas.  Apply that normalization once before compacted
        # PGS; the explicit f32 boundary matches every old lambda store.
        inactive = slot_mask & ~effective_active
        normal_offset = world * SLOTS + slot
        old_normal = _tl.load(
            normal_lambda_ptr + normal_offset,
            mask=slot_mask,
            other=0.0,
        ).to(_tl.float64)
        normalized_normal_f32 = _tl.maximum(old_normal, 0.0).to(_tl.float32)
        _tl.store(
            normal_lambda_ptr + normal_offset,
            normalized_normal_f32,
            mask=inactive,
        )
        friction = _tl.load(
            friction_ptr + normal_offset,
            mask=inactive,
            other=0.0,
        ).to(_tl.float64)
        cap = friction * normalized_normal_f32.to(_tl.float64)
        tangent_base = world * SLOTS * 2 + slot * 2
        for tangent_id in range(2):
            tangent_offset = tangent_base + tangent_id
            old_tangent = _tl.load(
                tangent_lambda_ptr + tangent_offset,
                mask=slot_mask,
                other=0.0,
            ).to(_tl.float64)
            normalized_tangent = _tl.minimum(
                _tl.maximum(old_tangent, -cap), cap
            )
            _tl.store(
                tangent_lambda_ptr + tangent_offset,
                normalized_tangent.to(_tl.float32),
                mask=inactive,
            )


    @_triton.jit
    def _ground_contact_response_active_kernel(
        factor_ptr,
        jacobian_ptr,
        active_slots_ptr,
        active_count_ptr,
        response_ptr,
        diagonal_ptr,
        BATCH: _tl.constexpr,
        SLOTS: _tl.constexpr,
        DOFS: _tl.constexpr,
        BLOCK_D: _tl.constexpr,
    ):
        """Solve the three response axes for compacted slots in one world."""

        world = _tl.program_id(0)
        lane = _tl.arange(0, BLOCK_D)
        lane_mask = lane < DOFS
        active_count = _tl.load(active_count_ptr + world).to(_tl.int32)

        matrix_row = lane[:, None]
        matrix_column = lane[None, :]
        matrix_mask = (matrix_row < DOFS) & (matrix_column < DOFS)
        factor_tile = _tl.load(
            factor_ptr
            + world * DOFS * DOFS
            + matrix_row * DOFS
            + matrix_column,
            mask=matrix_mask,
            other=0.0,
        ).to(_tl.float32)
        factor_transposed = _tl.load(
            factor_ptr
            + world * DOFS * DOFS
            + matrix_column * DOFS
            + matrix_row,
            mask=matrix_mask,
            other=0.0,
        ).to(_tl.float32)
        factor_diagonal = _tl.load(
            factor_ptr + (world * DOFS + lane) * DOFS + lane,
            mask=lane_mask,
            other=1.0,
        ).to(_tl.float32)
        # factor_tile[i, j] is the lower-triangular Cholesky factor L[i, j].
        # Forward substitution consumes L below the diagonal; backward
        # substitution consumes L.T above it.
        strict_lower = _tl.where(
            matrix_mask & (matrix_column < matrix_row),
            factor_tile,
            0.0,
        )
        strict_upper = _tl.where(
            matrix_mask & (matrix_column > matrix_row),
            factor_transposed,
            0.0,
        )

        active_index = 0
        while active_index < active_count:
            slot = _tl.load(
                active_slots_ptr + world * SLOTS + active_index
            ).to(_tl.int32)
            jacobian_base = (world * 3 * SLOTS + slot) * DOFS + lane
            rhs_0 = _tl.load(
                jacobian_ptr + jacobian_base,
                mask=lane_mask,
                other=0.0,
            ).to(_tl.float32)
            rhs_1 = _tl.load(
                jacobian_ptr + jacobian_base + SLOTS * DOFS,
                mask=lane_mask,
                other=0.0,
            ).to(_tl.float32)
            rhs_2 = _tl.load(
                jacobian_ptr + jacobian_base + 2 * SLOTS * DOFS,
                mask=lane_mask,
                other=0.0,
            ).to(_tl.float32)

            # Strict triangular Jacobi is nilpotent: DOFS fixed iterations are
            # algebraically the same forward/back solve, with lane-parallel
            # updates and no host convergence decision.
            forward_0 = rhs_0 / factor_diagonal
            forward_1 = rhs_1 / factor_diagonal
            forward_2 = rhs_2 / factor_diagonal
            for _forward_iteration in _tl.static_range(0, DOFS):
                forward_0 = (
                    rhs_0
                    - _tl.sum(strict_lower * forward_0[None, :], axis=1)
                ) / factor_diagonal
                forward_1 = (
                    rhs_1
                    - _tl.sum(strict_lower * forward_1[None, :], axis=1)
                ) / factor_diagonal
                forward_2 = (
                    rhs_2
                    - _tl.sum(strict_lower * forward_2[None, :], axis=1)
                ) / factor_diagonal

            solution_0 = forward_0 / factor_diagonal
            solution_1 = forward_1 / factor_diagonal
            solution_2 = forward_2 / factor_diagonal
            for _backward_iteration in _tl.static_range(0, DOFS):
                solution_0 = (
                    forward_0
                    - _tl.sum(strict_upper * solution_0[None, :], axis=1)
                ) / factor_diagonal
                solution_1 = (
                    forward_1
                    - _tl.sum(strict_upper * solution_1[None, :], axis=1)
                ) / factor_diagonal
                solution_2 = (
                    forward_2
                    - _tl.sum(strict_upper * solution_2[None, :], axis=1)
                ) / factor_diagonal

            response_base = (world * DOFS + lane) * SLOTS + slot
            response_stride = BATCH * DOFS * SLOTS
            _tl.store(
                response_ptr + response_base,
                solution_0,
                mask=lane_mask,
            )
            _tl.store(
                response_ptr + response_base + response_stride,
                solution_1,
                mask=lane_mask,
            )
            _tl.store(
                response_ptr + response_base + 2 * response_stride,
                solution_2,
                mask=lane_mask,
            )
            diagonal_base = world * SLOTS + slot
            diagonal_0 = _tl.maximum(
                _tl.sum(rhs_0 * solution_0, axis=0), 1.0e-8
            )
            diagonal_1 = _tl.maximum(
                _tl.sum(rhs_1 * solution_1, axis=0), 1.0e-8
            )
            diagonal_2 = _tl.maximum(
                _tl.sum(rhs_2 * solution_2, axis=0), 1.0e-8
            )
            _tl.store(diagonal_ptr + diagonal_base, diagonal_0)
            _tl.store(
                diagonal_ptr + diagonal_base + BATCH * SLOTS,
                diagonal_1,
            )
            _tl.store(
                diagonal_ptr + diagonal_base + 2 * BATCH * SLOTS,
                diagonal_2,
            )
            active_index += 1


    @_triton.jit
    def _contact_topology_child_schur_factor_kernel(
        mass_ptr,
        factor_ptr,
        child_info_ptr,
        DOFS: _tl.constexpr,
        ROOT_DOFS: _tl.constexpr,
        BLOCK_D: _tl.constexpr,
    ):
        """Factor a fixed free-root/1-DOF-child mass block by reverse Schur.

        The result represents ``M = U D U.T``: child columns hold the upper
        unitriangular coefficients, child diagonals hold scalar pivots, and
        the leading root block is the remaining six-by-six Schur complement.
        One program owns one world, so parent updates remain ordered without
        cross-program synchronization.
        """

        world = _tl.program_id(0)
        lane = _tl.arange(0, BLOCK_D)
        rows = lane[:, None]
        cols = lane[None, :]
        matrix_mask = (rows < DOFS) & (cols < DOFS)
        offsets = world * DOFS * DOFS + rows * DOFS + cols
        matrix = _tl.load(mass_ptr + offsets, mask=matrix_mask, other=0.0).to(
            _tl.float32
        )
        status = 0
        for reverse_index in _tl.static_range(0, DOFS - ROOT_DOFS):
            pivot = DOFS - 1 - reverse_index
            pivot_column = _tl.sum(matrix * (cols == pivot), axis=1)
            pivot_value = _tl.sum(
                pivot_column * (lane == pivot), axis=0
            )
            valid = pivot_value > 1.0e-8
            status = _tl.where(valid, status, 1)
            safe_pivot = _tl.where(valid, pivot_value, 1.0)
            rank_update = (
                pivot_column[:, None] * pivot_column[None, :] / safe_pivot
            )
            matrix = _tl.where(
                (rows < pivot) & (cols < pivot),
                matrix - rank_update,
                matrix,
            )
            matrix = _tl.where(
                (cols == pivot) & (rows < pivot),
                (pivot_column / safe_pivot)[:, None],
                matrix,
            )
            matrix = _tl.where(
                (rows == pivot) & (cols == pivot), safe_pivot, matrix
            )
        _tl.store(factor_ptr + offsets, matrix, mask=matrix_mask)
        _tl.store(child_info_ptr + world, status)


    @_triton.jit
    def _contact_topology_root_factor_kernel(
        factor_ptr,
        root_factor_ptr,
        root_info_ptr,
        DOFS: _tl.constexpr,
        ROOT_DOFS: _tl.constexpr,
        BLOCK_ROOT: _tl.constexpr,
    ):
        """Bounded f32 Cholesky factorization of the reduced 6x6 root."""

        world = _tl.program_id(0)
        lane = _tl.arange(0, BLOCK_ROOT)
        rows = lane[:, None]
        cols = lane[None, :]
        root_mask = (rows < ROOT_DOFS) & (cols < ROOT_DOFS)
        source_offsets = world * DOFS * DOFS + rows * DOFS + cols
        root = _tl.load(factor_ptr + source_offsets, mask=root_mask, other=0.0).to(
            _tl.float32
        )
        lower = _tl.zeros((BLOCK_ROOT, BLOCK_ROOT), dtype=_tl.float32)
        status = 0
        for pivot in _tl.static_range(0, ROOT_DOFS):
            lower_row = _tl.sum(lower * (rows == pivot), axis=0)
            root_column = _tl.sum(root * (cols == pivot), axis=1)
            diagonal = _tl.sum(root_column * (lane == pivot), axis=0)
            diagonal = diagonal - _tl.sum(
                lower_row * lower_row * (lane < pivot), axis=0
            )
            valid = diagonal > 1.0e-8
            status = _tl.where(valid, status, 1)
            safe_diagonal = _tl.where(valid, diagonal, 1.0)
            diagonal_root = _tl.sqrt(safe_diagonal)
            lower = _tl.where(
                (rows == pivot) & (cols == pivot), diagonal_root, lower
            )
            contribution = _tl.sum(
                lower * lower_row[None, :] * (cols < pivot), axis=1
            )
            column_value = (root_column - contribution) / diagonal_root
            lower = _tl.where(
                (cols == pivot) & (rows > pivot) & (rows < ROOT_DOFS),
                column_value[:, None],
                lower,
            )
        target_offsets = world * ROOT_DOFS * ROOT_DOFS + rows * ROOT_DOFS + cols
        _tl.store(root_factor_ptr + target_offsets, lower, mask=root_mask)
        _tl.store(root_info_ptr + world, status)


    @_triton.jit
    def _ground_contact_response_topology_active_kernel(
        factor_ptr,
        root_factor_ptr,
        jacobian_ptr,
        active_slots_ptr,
        active_count_ptr,
        response_ptr,
        diagonal_ptr,
        BATCH: _tl.constexpr,
        SLOTS: _tl.constexpr,
        DOFS: _tl.constexpr,
        ROOT_DOFS: _tl.constexpr,
        BLOCK_D: _tl.constexpr,
    ):
        """Apply fixed topology factors only to compacted active contact rows."""

        world = _tl.program_id(0)
        lane = _tl.arange(0, BLOCK_D)
        lane_mask = lane < DOFS
        rows = lane[:, None]
        cols = lane[None, :]
        matrix_mask = lane_mask[:, None] & lane_mask[None, :]
        factor_offsets = world * DOFS * DOFS + rows * DOFS + cols
        factor = _tl.load(
            factor_ptr + factor_offsets, mask=matrix_mask, other=0.0
        ).to(_tl.float32)
        root_mask = (rows < ROOT_DOFS) & (cols < ROOT_DOFS)
        root_offsets = world * ROOT_DOFS * ROOT_DOFS + rows * ROOT_DOFS + cols
        root_factor = _tl.load(
            root_factor_ptr + root_offsets, mask=root_mask, other=0.0
        ).to(_tl.float32)
        factor_diagonal = _tl.sum(factor * (rows == cols), axis=1)
        factor_diagonal = _tl.where(lane_mask, factor_diagonal, 1.0)
        active_count = _tl.load(active_count_ptr + world).to(_tl.int32)

        active_index = 0
        while active_index < active_count:
            slot = _tl.load(
                active_slots_ptr + world * SLOTS + active_index
            ).to(_tl.int32)
            jacobian_base = (world * 3 * SLOTS + slot) * DOFS + lane
            rhs_0 = _tl.load(
                jacobian_ptr + jacobian_base, mask=lane_mask, other=0.0
            ).to(_tl.float32)
            rhs_1 = _tl.load(
                jacobian_ptr + jacobian_base + SLOTS * DOFS,
                mask=lane_mask,
                other=0.0,
            ).to(_tl.float32)
            rhs_2 = _tl.load(
                jacobian_ptr + jacobian_base + 2 * SLOTS * DOFS,
                mask=lane_mask,
                other=0.0,
            ).to(_tl.float32)
            upper_0 = rhs_0
            upper_1 = rhs_1
            upper_2 = rhs_2
            # Solve U z = rhs.  The root block belongs to D, so its rows only
            # couple to child columns; root-internal entries are ignored here.
            for reverse_index in _tl.static_range(0, DOFS):
                pivot = DOFS - 1 - reverse_index
                factor_row = _tl.sum(factor * (rows == pivot), axis=0)
                if pivot < ROOT_DOFS:
                    coefficient_mask = lane >= ROOT_DOFS
                else:
                    coefficient_mask = lane > pivot
                sum_0 = _tl.sum(
                    factor_row * upper_0 * coefficient_mask, axis=0
                )
                sum_1 = _tl.sum(
                    factor_row * upper_1 * coefficient_mask, axis=0
                )
                sum_2 = _tl.sum(
                    factor_row * upper_2 * coefficient_mask, axis=0
                )
                value_0 = _tl.sum(upper_0 * (lane == pivot), axis=0) - sum_0
                value_1 = _tl.sum(upper_1 * (lane == pivot), axis=0) - sum_1
                value_2 = _tl.sum(upper_2 * (lane == pivot), axis=0) - sum_2
                upper_0 = _tl.where(lane == pivot, value_0, upper_0)
                upper_1 = _tl.where(lane == pivot, value_1, upper_1)
                upper_2 = _tl.where(lane == pivot, value_2, upper_2)

            forward_0 = upper_0
            forward_1 = upper_1
            forward_2 = upper_2
            for pivot in _tl.static_range(0, ROOT_DOFS):
                root_row = _tl.sum(root_factor * (rows == pivot), axis=0)
                root_diagonal = _tl.sum(
                    root_row * (lane == pivot), axis=0
                )
                prefix = lane < pivot
                value_0 = (
                    _tl.sum(forward_0 * (lane == pivot), axis=0)
                    - _tl.sum(root_row * forward_0 * prefix, axis=0)
                ) / root_diagonal
                value_1 = (
                    _tl.sum(forward_1 * (lane == pivot), axis=0)
                    - _tl.sum(root_row * forward_1 * prefix, axis=0)
                ) / root_diagonal
                value_2 = (
                    _tl.sum(forward_2 * (lane == pivot), axis=0)
                    - _tl.sum(root_row * forward_2 * prefix, axis=0)
                ) / root_diagonal
                forward_0 = _tl.where(lane == pivot, value_0, forward_0)
                forward_1 = _tl.where(lane == pivot, value_1, forward_1)
                forward_2 = _tl.where(lane == pivot, value_2, forward_2)

            solved_0 = forward_0
            solved_1 = forward_1
            solved_2 = forward_2
            for reverse_index in _tl.static_range(0, ROOT_DOFS):
                pivot = ROOT_DOFS - 1 - reverse_index
                root_column = _tl.sum(root_factor * (cols == pivot), axis=1)
                root_diagonal = _tl.sum(
                    root_column * (lane == pivot), axis=0
                )
                suffix = (lane > pivot) & (lane < ROOT_DOFS)
                value_0 = (
                    _tl.sum(solved_0 * (lane == pivot), axis=0)
                    - _tl.sum(root_column * solved_0 * suffix, axis=0)
                ) / root_diagonal
                value_1 = (
                    _tl.sum(solved_1 * (lane == pivot), axis=0)
                    - _tl.sum(root_column * solved_1 * suffix, axis=0)
                ) / root_diagonal
                value_2 = (
                    _tl.sum(solved_2 * (lane == pivot), axis=0)
                    - _tl.sum(root_column * solved_2 * suffix, axis=0)
                ) / root_diagonal
                solved_0 = _tl.where(lane == pivot, value_0, solved_0)
                solved_1 = _tl.where(lane == pivot, value_1, solved_1)
                solved_2 = _tl.where(lane == pivot, value_2, solved_2)

            solved_0 = _tl.where(
                lane < ROOT_DOFS, solved_0, upper_0 / factor_diagonal
            )
            solved_1 = _tl.where(
                lane < ROOT_DOFS, solved_1, upper_1 / factor_diagonal
            )
            solved_2 = _tl.where(
                lane < ROOT_DOFS, solved_2, upper_2 / factor_diagonal
            )
            # Solve U.T x = D^-1 z.  Root-internal entries again belong to D.
            solution_0 = solved_0
            solution_1 = solved_1
            solution_2 = solved_2
            for pivot in _tl.static_range(0, DOFS):
                if pivot >= ROOT_DOFS:
                    factor_column = _tl.sum(factor * (cols == pivot), axis=1)
                    prefix = lane < pivot
                    sum_0 = _tl.sum(
                        factor_column * solution_0 * prefix, axis=0
                    )
                    sum_1 = _tl.sum(
                        factor_column * solution_1 * prefix, axis=0
                    )
                    sum_2 = _tl.sum(
                        factor_column * solution_2 * prefix, axis=0
                    )
                    value_0 = (
                        _tl.sum(solved_0 * (lane == pivot), axis=0) - sum_0
                    )
                    value_1 = (
                        _tl.sum(solved_1 * (lane == pivot), axis=0) - sum_1
                    )
                    value_2 = (
                        _tl.sum(solved_2 * (lane == pivot), axis=0) - sum_2
                    )
                    solution_0 = _tl.where(lane == pivot, value_0, solution_0)
                    solution_1 = _tl.where(lane == pivot, value_1, solution_1)
                    solution_2 = _tl.where(lane == pivot, value_2, solution_2)

            response_base = (world * DOFS + lane) * SLOTS + slot
            response_stride = BATCH * DOFS * SLOTS
            _tl.store(response_ptr + response_base, solution_0, mask=lane_mask)
            _tl.store(
                response_ptr + response_base + response_stride,
                solution_1,
                mask=lane_mask,
            )
            _tl.store(
                response_ptr + response_base + 2 * response_stride,
                solution_2,
                mask=lane_mask,
            )
            diagonal_base = world * SLOTS + slot
            _tl.store(
                diagonal_ptr + diagonal_base,
                _tl.maximum(_tl.sum(rhs_0 * solution_0, axis=0), 1.0e-8),
            )
            _tl.store(
                diagonal_ptr + diagonal_base + BATCH * SLOTS,
                _tl.maximum(_tl.sum(rhs_1 * solution_1, axis=0), 1.0e-8),
            )
            _tl.store(
                diagonal_ptr + diagonal_base + 2 * BATCH * SLOTS,
                _tl.maximum(_tl.sum(rhs_2 * solution_2, axis=0), 1.0e-8),
            )
            active_index += 1


    @_triton.jit
    def _ground_contact_pgs_kernel(
        qvel_ptr,
        jacobian_ptr,
        response_ptr,
        diagonal_ptr,
        bias_ptr,
        active_ptr,
        world_active_ptr,
        lambda_ptr,
        friction_ptr,
        normal_lambda_ptr,
        SLOTS: _tl.constexpr,
        DOFS: _tl.constexpr,
        ITERATIONS: _tl.constexpr,
        MODE: _tl.constexpr,
        BLOCK_D: _tl.constexpr,
        LAMBDA_BATCH_STRIDE: _tl.constexpr,
        LAMBDA_SLOT_STRIDE: _tl.constexpr,
    ):
        """Generic ordered row-PGS sweep; one program owns one world."""
        world = _tl.program_id(0)
        dof = _tl.arange(0, BLOCK_D)
        dof_mask = dof < DOFS
        qvel_offsets = world * DOFS + dof
        qvel = _tl.load(qvel_ptr + qvel_offsets, mask=dof_mask, other=0.0)
        qvel_f64 = qvel.to(_tl.float64)
        world_active = _tl.load(world_active_ptr + world)
        for _iteration in _tl.range(0, ITERATIONS, num_stages=1):
            for slot in _tl.range(0, SLOTS, num_stages=1):
                row_offsets = world * SLOTS * DOFS + slot * DOFS + dof
                row = _tl.load(jacobian_ptr + row_offsets, mask=dof_mask, other=0.0).to(_tl.float64)
                row_velocity = _tl.sum(row * qvel_f64, axis=0)
                active = _tl.load(active_ptr + world * SLOTS + slot)
                active = active & world_active
                diagonal = _tl.load(diagonal_ptr + world * SLOTS + slot)
                lambda_offset = world * LAMBDA_BATCH_STRIDE + slot * LAMBDA_SLOT_STRIDE
                old = _tl.load(lambda_ptr + lambda_offset).to(_tl.float64)
                if MODE == 0:
                    target = _tl.load(bias_ptr + world * SLOTS + slot)
                    delta = _tl.where(active, (target - row_velocity) / diagonal, 0.0)
                    updated = _tl.maximum(old + delta, 0.0)
                else:
                    delta = _tl.where(active, -row_velocity / diagonal, 0.0)
                    friction = _tl.load(friction_ptr + world * SLOTS + slot).to(_tl.float64)
                    normal_lambda = _tl.load(normal_lambda_ptr + world * SLOTS + slot).to(_tl.float64)
                    cap = friction * normal_lambda
                    updated = _tl.minimum(_tl.maximum(old + delta, -cap), cap)
                delta = updated - old
                _tl.store(
                    lambda_ptr + lambda_offset + dof * LAMBDA_SLOT_STRIDE,
                    updated.to(_tl.float32),
                    mask=dof == 0,
                )
                response_offsets = world * DOFS * SLOTS + dof * SLOTS + slot
                response = _tl.load(response_ptr + response_offsets, mask=dof_mask, other=0.0)
                qvel = qvel + (response * delta).to(_tl.float32)
                qvel_f64 = qvel.to(_tl.float64)
        _tl.store(qvel_ptr + qvel_offsets, qvel, mask=dof_mask)


    @_triton.jit
    def _ground_contact_pgs_fused_kernel(
        qvel_ptr,
        jacobian_ptr,
        response_ptr,
        diagonal_ptr,
        bias_ptr,
        active_ptr,
        world_active_ptr,
        normal_lambda_ptr,
        tangent_lambda_ptr,
        friction_ptr,
        active_slot_ptr,
        active_count_ptr,
        BATCH: _tl.constexpr,
        SLOTS: _tl.constexpr,
        DOFS: _tl.constexpr,
        ITERATIONS: _tl.constexpr,
        BLOCK_D: _tl.constexpr,
    ):
        """Fuse the ordered normal/x/y sweeps while preserving row order."""
        world = _tl.program_id(0)
        dof = _tl.arange(0, BLOCK_D)
        dof_mask = dof < DOFS
        qvel_offsets = world * DOFS + dof
        qvel = _tl.load(qvel_ptr + qvel_offsets, mask=dof_mask, other=0.0)
        qvel_f64 = qvel.to(_tl.float64)
        world_active = _tl.load(world_active_ptr + world)
        axis_jacobian_stride = BATCH * SLOTS * DOFS
        axis_response_stride = BATCH * DOFS * SLOTS
        axis_diagonal_stride = BATCH * SLOTS
        tangent_lambda_batch_stride = SLOTS * 2
        active_count = _tl.load(active_count_ptr + world)
        for axis in range(3):
            for _iteration in _tl.range(0, ITERATIONS, num_stages=1):
                for active_index in _tl.range(
                    0, active_count, num_stages=1
                ):
                    slot = _tl.load(
                        active_slot_ptr + world * SLOTS + active_index
                    )
                    active = _tl.load(active_ptr + world * SLOTS + slot)
                    active = active & world_active
                    row_offsets = (
                        axis * axis_jacobian_stride
                        + world * SLOTS * DOFS
                        + slot * DOFS
                        + dof
                    )
                    row = _tl.load(
                        jacobian_ptr + row_offsets,
                        mask=active & dof_mask,
                        other=0.0,
                    ).to(_tl.float64)
                    row_velocity = _tl.sum(row * qvel_f64, axis=0)
                    diagonal = _tl.load(
                        diagonal_ptr
                        + axis * axis_diagonal_stride
                        + world * SLOTS
                        + slot,
                        mask=active,
                        other=1.0,
                    )
                    if axis == 0:
                        old = _tl.load(
                            normal_lambda_ptr + world * SLOTS + slot
                        ).to(_tl.float64)
                        target = _tl.load(
                            bias_ptr + world * SLOTS + slot,
                            mask=active,
                            other=0.0,
                        )
                        delta = _tl.where(
                            active,
                            (target - row_velocity) / diagonal,
                            0.0,
                        )
                        updated = _tl.maximum(old + delta, 0.0)
                        _tl.store(
                            normal_lambda_ptr + world * SLOTS + slot,
                            updated.to(_tl.float32),
                        )
                    else:
                        tangent_offset = (
                            world * tangent_lambda_batch_stride
                            + slot * 2
                            + axis
                            - 1
                        )
                        old = _tl.load(
                            tangent_lambda_ptr + tangent_offset
                        ).to(_tl.float64)
                        delta = _tl.where(
                            active,
                            -row_velocity / diagonal,
                            0.0,
                        )
                        friction = _tl.load(
                            friction_ptr + world * SLOTS + slot
                        ).to(_tl.float64)
                        normal_lambda = _tl.load(
                            normal_lambda_ptr + world * SLOTS + slot
                        ).to(_tl.float64)
                        cap = friction * normal_lambda
                        updated = _tl.minimum(
                            _tl.maximum(old + delta, -cap), cap
                        )
                        _tl.store(
                            tangent_lambda_ptr + tangent_offset,
                            updated.to(_tl.float32),
                        )
                    delta = updated - old
                    response_offsets = (
                        axis * axis_response_stride
                        + world * DOFS * SLOTS
                        + dof * SLOTS
                        + slot
                    )
                    response = _tl.load(
                        response_ptr + response_offsets,
                        mask=active & dof_mask,
                        other=0.0,
                    )
                    qvel = qvel + (response * delta).to(_tl.float32)
                    qvel_f64 = qvel.to(_tl.float64)
        _tl.store(qvel_ptr + qvel_offsets, qvel, mask=dof_mask)


def _arr(mapping: Mapping[str, Any], name: str, shape: tuple[int, ...], *, dtype=np.float32, default=None):
    value = mapping.get(name, default)
    if value is None:
        value = np.zeros(shape, dtype=dtype)
    value = np.asarray(value, dtype=dtype)
    if value.shape != shape:
        raise ValueError(f"static fused model field {name!r} has shape {value.shape}, expected {shape}")
    return np.ascontiguousarray(value)


def _quat_normalize(q):
    import torch
    norm = torch.linalg.vector_norm(q, dim=-1, keepdim=True)
    identity = torch.zeros_like(q)
    identity[..., 0] = 1.0
    return torch.where(norm >= 1.0e-8, q / torch.clamp(norm, min=1.0e-8), identity)


def _quat_mul(a, b):
    import torch
    aw, ax, ay, az = a.unbind(-1)
    bw, bx, by, bz = b.unbind(-1)
    return torch.stack((aw * bw - ax * bx - ay * by - az * bz,
                        aw * bx + ax * bw + ay * bz - az * by,
                        aw * by - ax * bz + ay * bw + az * bx,
                        aw * bz + ax * by - ay * bx + az * bw), dim=-1)


def _quat_to_matrix(q):
    import torch
    q = _quat_normalize(q)
    w, x, y, z = q.unbind(-1)
    rows = (
        torch.stack((1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * z * w, 2 * x * z + 2 * y * w), -1),
        torch.stack((2 * x * y + 2 * z * w, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * x * w), -1),
        torch.stack((2 * x * z - 2 * y * w, 2 * y * z + 2 * x * w, 1 - 2 * x * x - 2 * y * y), -1),
    )
    return torch.stack(rows, dim=-2)


def _axis_angle(axis, angle):
    import torch
    half = angle * 0.5
    return torch.cat((torch.cos(half)[..., None], axis * torch.sin(half)[..., None]), dim=-1)


def _quat_integrate(q, omega, dt):
    import torch
    zero = omega.new_zeros(omega.shape[:-1] + (1,))
    dq = 0.5 * _quat_mul(torch.cat((zero, omega), dim=-1), q)
    return _quat_normalize(q + dt * dq)


def _read_model_array(data: Mapping[str, Any], names: tuple[str, ...], shape: tuple[int, ...], *, dtype=np.float32, default=None):
    for name in names:
        if name in data:
            return _arr(data, name, shape, dtype=dtype, default=default)
    return _arr({}, names[0], shape, dtype=dtype, default=default)


def _small_batched_solve(matrix, rhs):
    """Capture-safe Gaussian solve for the fixed six-dimensional root block."""

    import torch

    left = matrix.clone()
    right = rhs.clone()
    size = int(left.shape[-1])
    for pivot in range(size):
        diagonal = left[:, pivot, pivot]
        for row in range(pivot + 1, size):
            factor = left[:, row, pivot] / diagonal
            left[:, row, pivot + 1:] -= factor[:, None] * left[:, pivot, pivot + 1:]
            left[:, row, pivot] = 0.0
            right[:, row, :] -= factor[:, None] * right[:, pivot, :]
    solution = torch.zeros_like(right)
    for row in range(size - 1, -1, -1):
        if row + 1 < size:
            tail = (
                left[:, row, row + 1:, None]
                * solution[:, row + 1:, :]
            ).sum(dim=1)
        else:
            tail = 0.0
        solution[:, row, :] = (right[:, row, :] - tail) / left[:, row, row, None]
    return solution


def _capture_safe_cholesky_solve(matrix, rhs):
    """Solve a fixed-size SPD system without graph-unsafe linalg dispatches.

    ``torch.linalg.cholesky`` is not accepted by the CUDA Graph path on the
    CUDA/Torch combination used by TaskEnv, while ``cholesky_ex`` is.  Use the
    optimized capture-safe factorization and triangular solves because
    ``cholesky_solve`` is not capture-safe here.  No convergence or shape
    decision is made on the host.
    """

    import torch

    factor, _ = torch.linalg.cholesky_ex(matrix, check_errors=False)

    forward = torch.linalg.solve_triangular(
        factor,
        rhs,
        upper=False,
        unitriangular=False,
    )
    return torch.linalg.solve_triangular(
        factor.transpose(-2, -1),
        forward,
        upper=True,
        unitriangular=False,
    )


def _reference_fixed_topology_child_schur_solve(mass, rhs, *, root_dofs: int = 6):
    """Diagnostic f64 reference for P1/P12's fixed block factorization.

    This is intentionally not a production physics path.  It gives the
    CUDA-kernel gate an independent, readable ``U D U.T`` implementation for
    B=1/2/17/32 alignment checks before comparing a candidate to the dense
    f64 ``torch.linalg.solve`` reference.
    """

    import torch

    if mass.ndim != 3 or mass.shape[-1] != mass.shape[-2]:
        raise ValueError("mass must have shape (B, D, D)")
    if rhs.ndim != 3 or rhs.shape[:2] != mass.shape[:2]:
        raise ValueError("rhs must have shape (B, D, R) matching mass")
    dofs = int(mass.shape[-1])
    if not 0 < int(root_dofs) < dofs:
        raise ValueError("root_dofs must be in [1, D-1]")
    factor = mass.clone()
    for pivot in range(dofs - 1, int(root_dofs) - 1, -1):
        column = factor[:, :pivot, pivot].clone()
        diagonal = factor[:, pivot, pivot].clone()
        if bool(torch.any(diagonal <= 0.0)):
            raise RuntimeError("reference child Schur encountered non-positive pivot")
        factor[:, :pivot, :pivot] -= (
            column[:, :, None] * column[:, None, :] / diagonal[:, None, None]
        )
        factor[:, :pivot, pivot] = column / diagonal[:, None]
        factor[:, pivot, pivot] = diagonal
    root_factor = torch.linalg.cholesky(factor[:, :root_dofs, :root_dofs])

    upper_rhs = rhs.clone()
    for pivot in range(dofs - 1, -1, -1):
        if pivot < root_dofs:
            correction = torch.einsum(
                "bi,bir->br",
                factor[:, pivot, root_dofs:],
                upper_rhs[:, root_dofs:, :],
            )
        else:
            correction = torch.einsum(
                "bi,bir->br",
                factor[:, pivot, pivot + 1:],
                upper_rhs[:, pivot + 1:, :],
            )
        upper_rhs[:, pivot, :] -= correction
    diagonal_solution = upper_rhs.clone()
    diagonal_solution[:, :root_dofs, :] = torch.cholesky_solve(
        upper_rhs[:, :root_dofs, :], root_factor
    )
    diagonal_solution[:, root_dofs:, :] /= torch.diagonal(
        factor[:, root_dofs:, root_dofs:], dim1=-2, dim2=-1
    )[:, :, None]
    solution = diagonal_solution.clone()
    for pivot in range(root_dofs, dofs):
        solution[:, pivot, :] -= torch.einsum(
            "bi,bir->br",
            factor[:, :pivot, pivot],
            solution[:, :pivot, :],
        )
    return solution


def _build_actuator_moments(joint_data: Mapping[str, Any], *, n_act: int, n_joints: int, n_dof: int):
    """Resolve actuator -> local dof moments without relying on global IDs."""
    moments = np.zeros((n_act, 6), dtype=np.int32)
    coeff = np.zeros((n_act, 6), dtype=np.float32)
    trnid = np.asarray(joint_data.get("actuator_trnid", np.zeros(n_act)), dtype=np.int32).reshape(-1)
    gear = np.asarray(joint_data.get("actuator_gear", np.zeros((n_act, 6))), dtype=np.float32).reshape(-1, 6)
    dof_adr = np.asarray(joint_data.get("jnt_dofadr", np.zeros(n_joints)), dtype=np.int32).reshape(-1)
    jnt_type = np.asarray(joint_data.get("jnt_type", np.zeros(n_joints)), dtype=np.int32).reshape(-1)
    dof_counts = {0: 6, 1: 3, 2: 1, 3: 1, 4: 2}
    explicit_dof = np.asarray(joint_data.get("actuator_moment_dofadr", np.zeros(0)), dtype=np.int32).reshape(-1)
    explicit_coef = np.asarray(joint_data.get("actuator_moment_coef", np.zeros(0)), dtype=np.float32).reshape(-1)
    adr = np.asarray(joint_data.get("actuator_moment_adr", np.zeros(n_act)), dtype=np.int32).reshape(-1)
    num = np.asarray(joint_data.get("actuator_moment_num", np.zeros(n_act)), dtype=np.int32).reshape(-1)
    if explicit_dof.size and adr.size == n_act:
        for a in range(n_act):
            for k in range(min(6, int(num[a]))):
                index = int(adr[a]) + k
                if 0 <= index < explicit_dof.size and 0 <= int(explicit_dof[index]) < n_dof:
                    moments[a, k] = int(explicit_dof[index])
                    coeff[a, k] = float(explicit_coef[index]) if index < explicit_coef.size else 1.0
        return moments, coeff
    for a in range(n_act):
        joint = int(trnid[a]) if a < trnid.size else -1
        if 0 <= joint < n_joints:
            start = int(dof_adr[joint])
            count = int(dof_counts.get(int(jnt_type[joint]), 1))
            g = gear[a] if a < gear.shape[0] else np.zeros(6, dtype=np.float32)
            for k in range(min(6, count)):
                if start + k < n_dof:
                    moments[a, k] = start + k
                    coeff[a, k] = float(g[k] if abs(float(g[k])) > 0 else (g[0] if k == 0 else 0.0))
    return moments, coeff


class StaticTemplateFusedArticulated:
    """Batched articulated dynamics with a shared local topology.

    ``contact_enabled`` adds a local ground-plane row workspace.  The
    workspace is sized from the immutable template (never from ``B``), and
    every array is indexed ``(world, local_slot, ...)``.  This is deliberately
    a capability switch on the generic runtime rather than a Go2-specific
    branch.
    """

    _DENSE_RNE_BODY_WRENCH_PROVENANCE = "batched_body_terms_v1"
    fused_world_local = True

    JOINT_FREE = 0
    JOINT_BALL = 1
    JOINT_HINGE = 2
    JOINT_SLIDE = 3
    JOINT_UNIVERSAL = 4

    def __init__(
        self,
        *,
        model: Mapping[str, Any],
        num_envs: int,
        control_substeps: int,
        backend: str,
        contact_enabled: bool = False,
        kinematics_backend: str = "torch",
        contact_precision: str = "f64",
        contact_response_backend: str = "auto",
        fixed_topology_child_schur: bool = False,
        root_factor_6x6: bool = False,
        cuda_graph: bool = False,
        world_randomization_enabled: bool = False,
        push_event_capacity: int = 0,
    ):
        import torch

        self.contact_precision = str(contact_precision).strip().lower()
        if self.contact_precision not in {"f64", "f32"}:
            raise ValueError(
                "static fused contact_precision must be one of: f64, f32"
            )
        self._contact_response_requested_backend = str(
            contact_response_backend
        ).strip().lower()
        if self._contact_response_requested_backend not in {
            "auto",
            "active_slot_cholesky_f32_v1",
        }:
            raise ValueError(
                "static fused contact_response_backend must be auto or "
                "active_slot_cholesky_f32_v1"
            )
        self._contact_topology_child_schur_enabled = bool(
            fixed_topology_child_schur
        )
        self._contact_root_factor_6x6_enabled = bool(root_factor_6x6)
        if (
            self._contact_root_factor_6x6_enabled
            and not self._contact_topology_child_schur_enabled
        ):
            raise ValueError(
                "root_factor_6x6 requires fixed_topology_child_schur=True"
            )
        self.num_envs = int(num_envs)
        self.control_substeps = int(control_substeps)
        self.backend = str(backend)
        self.contact_enabled = bool(contact_enabled)
        self._world_randomization_enabled = bool(world_randomization_enabled)
        self._world_push_capacity = int(push_event_capacity)
        if self._world_push_capacity < 0:
            raise ValueError("push_event_capacity must be non-negative")
        if self._world_randomization_enabled and self._world_push_capacity < 1:
            raise ValueError(
                "enabled world randomization requires a positive push_event_capacity"
            )
        self.kinematics_backend = str(kinematics_backend).strip().lower()
        if self.kinematics_backend not in {"torch", "taichi"}:
            raise ValueError(
                "static fused kinematics_backend must be one of: torch, taichi"
            )
        if self.num_envs < 1:
            raise ValueError("num_envs must be positive")
        if self.backend not in {"cpu", "cuda"}:
            raise ValueError("fused articulated runtime supports cpu/cuda")
        if self.backend == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("static fused articulated CUDA runtime requested but CUDA is unavailable")
        # TaskEnv's device bridge exposes the concrete CUDA ordinal (cuda:0),
        # matching RSL/Torch's default learner device rather than the generic
        # ``cuda`` alias.
        self.device = torch.device("cuda:0" if self.backend == "cuda" else "cpu")
        self.physics_dt = float(model["physics_dt"])
        self.integrator = str(model.get("integrator", "euler"))
        self.n_bodies = int(model["n_bodies"])
        self.n_geoms = int(model["n_geoms"])
        self.n_sites = int(model["n_sites"])
        self.n_joints = int(model["n_joints"])
        self.n_qpos = int(model["n_qpos"])
        self.n_dof = int(model["n_dof"])
        self.n_actuators = int(model["n_actuators"])
        self._model: dict[str, torch.Tensor] = {}
        for name, value in model.items():
            if isinstance(value, np.ndarray):
                dtype = torch.int32 if np.issubdtype(value.dtype, np.integer) else torch.float32
                self._model[name] = torch.as_tensor(value, dtype=dtype, device=self.device)

        # Stage 19a: lower all immutable topology traversal once at assembly
        # time.  The steady-state path consumes these host descriptors instead
        # of repeatedly reading scalar topology fields and rebuilding joint
        # lists inside every physics substep.
        self._compile_static_traversal()
        self._contact_topology_schur_capability_reasons = (
            self._topology_schur_capability_check()
        )
        if (
            self._contact_topology_child_schur_enabled
            and self._contact_topology_schur_capability_reasons
        ):
            raise RuntimeError(
                "fixed-topology contact Schur candidate is unavailable: "
                + ", ".join(self._contact_topology_schur_capability_reasons)
            )

        B = self.num_envs
        self._qpos = torch.zeros((B, self.n_qpos), dtype=torch.float32, device=self.device)
        self._qvel = torch.zeros((B, self.n_dof), dtype=torch.float32, device=self.device)
        self._qacc = torch.zeros_like(self._qvel)
        self._ctrl = torch.zeros((B, self.n_actuators), dtype=torch.float32, device=self.device)
        self._act = torch.zeros_like(self._ctrl)
        self._body_xpos = torch.zeros((B, self.n_bodies, 3), dtype=torch.float32, device=self.device)
        self._body_xquat = torch.zeros((B, self.n_bodies, 4), dtype=torch.float32, device=self.device)
        # 每个 FK tick 只为 body 生成一次 world rotation，后续 joint frame、
        # geom/site、CRB 与 RNE 路径共享该稳定 workspace。
        self._body_xmat = torch.zeros((B, self.n_bodies, 3, 3), dtype=torch.float32, device=self.device)
        self._body_linear_vel = torch.zeros_like(self._body_xpos)
        self._body_angular_vel = torch.zeros_like(self._body_xpos)
        self._geom_xpos = torch.zeros((B, self.n_geoms, 3), dtype=torch.float32, device=self.device)
        self._geom_xquat = torch.zeros((B, self.n_geoms, 4), dtype=torch.float32, device=self.device)
        # Immutable local geom/site transforms and body-index gathers are
        # compiled once.  The steady-state FK path uses batched matmul instead
        # of launching one tiny operation per geom/site.
        self._geom_xmat = torch.zeros((B, self.n_geoms, 3, 3), dtype=torch.float32, device=self.device)
        self._site_xpos = torch.zeros((B, self.n_sites, 3), dtype=torch.float32, device=self.device)
        self._site_xquat = torch.zeros((B, self.n_sites, 4), dtype=torch.float32, device=self.device)
        self._body_local_pos_batched = self._v("body_pos_local").unsqueeze(0)
        # Body-local and root orientations are immutable model data.  Keep
        # their normalized forms and world rotation matrices alive across
        # ticks; FK must only rebuild state-dependent rotations.
        self._body_local_quat_batched = _quat_normalize(
            self._v("body_quat_local").unsqueeze(0)
        )
        self._body_local_rot_batched = _quat_to_matrix(self._body_local_quat_batched)
        self._root_quat_batched = _quat_normalize(
            self._v("root_quat").unsqueeze(0)
        )
        self._root_rot_batched = _quat_to_matrix(self._root_quat_batched)
        self._geom_local_pos_batched = self._v("geom_pos").unsqueeze(0)
        self._geom_local_quat_batched = self._v("geom_quat").unsqueeze(0)
        # Geom local orientation is immutable.  Cache its rotation matrix at
        # assembly time so the FK hot path can compose world matrices from
        # the already materialized body rotation instead of rebuilding one
        # quaternion-to-matrix expression for every geom on every substep.
        self._geom_local_rot_batched = _quat_to_matrix(
            _quat_normalize(self._geom_local_quat_batched)
        )
        self._site_local_pos_batched = self._v("site_pos").unsqueeze(0)
        self._site_local_quat_batched = self._v("site_quat").unsqueeze(0)
        self._taichi_fk = None
        # Taichi Forge 的 Torch 外部数组适配器会在每次 kernel 接收 Torch
        # tensor 时重新导入 DLPack storage view。下面这些 tensor 都是 runtime
        # 持久 buffer，逐次导入只会增加 native 生命周期压力，并在当前 Forge
        # 版本的长 rollout 中积累 host-side storage metadata。待所有状态 buffer
        # 建完后延迟创建 cache，后续直接把 view 交给 Taichi。
        # None 表示尚未尝试；空 mapping 表示 managed-view 不可用，继续走旧的
        # raw-pointer 路径。
        self._taichi_external_views: dict[str, Any] | None = None
        self._taichi_world_ids = None
        self._taichi_reset_ids = None
        self._taichi_reset_destinations = None
        self._taichi_reset_ranks = None
        self._taichi_reset_not_selected = None
        if self.kinematics_backend == "taichi":
            from .taichi import StaticTemplateTaichiFK

            taichi_model = {
                name: self._model[name].detach().cpu().numpy()
                for name in (
                    "body_pos_local",
                    "body_quat_local",
                    "jnt_type",
                    "jnt_qposadr",
                    "jnt_dofadr",
                    "jnt_parent_body",
                    "jnt_child_body",
                    "jnt_axis_parent",
                    "jnt_axis_child",
                    "jnt_anchor_child",
                    "geom_pos",
                    "geom_quat",
                    "site_pos",
                    "site_quat",
                    "root_pos",
                    "root_quat",
                )
            }

            taichi_model.update(
                {
                    "n_bodies": np.asarray(self.n_bodies, dtype=np.int32),
                    "n_joints": np.asarray(self.n_joints, dtype=np.int32),
                    "n_geoms": np.asarray(self.n_geoms, dtype=np.int32),
                    "n_sites": np.asarray(self.n_sites, dtype=np.int32),
                    "body_rot_local": self._body_local_rot_batched[0].detach().cpu().numpy(),
                    "geom_rot_local": self._geom_local_rot_batched[0].detach().cpu().numpy(),
                }
            )
            self._taichi_fk = StaticTemplateTaichiFK(
                model=taichi_model,
                body_routes=self._compiled_body_routes,
                geom_bodies=self._compiled_geom_bodies,
                site_bodies=self._compiled_site_bodies,
            )
            # Keep reset selection at a fixed shape.  A dynamic-sized
            # world-id ndarray would make Taichi specialize/cache a kernel
            # for each distinct number of reset worlds.
            self._taichi_world_ids = torch.arange(
                B, dtype=torch.int32, device=self.device
            )
            self._taichi_reset_ids = torch.empty_like(self._taichi_world_ids)
            self._taichi_reset_destinations = torch.empty(
                (B,), dtype=torch.int64, device=self.device
            )
            self._taichi_reset_ranks = torch.empty_like(self._taichi_world_ids)
            self._taichi_reset_not_selected = torch.empty(
                (B,), dtype=torch.bool, device=self.device
            )
        self._compiled_geom_body_indices = torch.as_tensor(
            self._compiled_geom_bodies, dtype=torch.int64, device=self.device
        )
        self._compiled_site_body_indices = torch.as_tensor(
            self._compiled_site_bodies, dtype=torch.int64, device=self.device
        )
        # Fixed local contact workspace.  The original implementation gave
        # every geom eight rows, even when it can never participate in ground
        # contact or has a smaller analytic manifold.  Build a compact layout
        # once from the immutable template instead.  The layout is still
        # entirely local: a row is addressed by ``(world, local_slot)`` and
        # never by a global batched geom id.
        (
            self._ground_contact_geom_ids,
            self._ground_contact_bodies,
            self._ground_contact_slot_offsets,
            self._ground_contact_slot_counts,
            self._ground_contact_shapes,
        ) = self._build_ground_contact_layout()
        self._contact_slots = max(1, sum(self._ground_contact_slot_counts))
        slot_geom_ids: list[int] = []
        slot_body_ids: list[int] = []
        slot_shapes: list[int] = []
        slot_candidates: list[int] = []
        for geom_id, body, shape, count in zip(
            self._ground_contact_geom_ids,
            self._ground_contact_bodies,
            self._ground_contact_shapes,
            self._ground_contact_slot_counts,
        ):
            for candidate_id in range(count):
                slot_geom_ids.append(int(geom_id))
                slot_body_ids.append(int(body))
                slot_shapes.append(int(shape))
                slot_candidates.append(candidate_id)
        if slot_geom_ids:
            self._contact_slot_geom_indices = torch.as_tensor(
                slot_geom_ids, dtype=torch.int64, device=self.device
            )
            self._contact_slot_body_indices = torch.as_tensor(
                slot_body_ids, dtype=torch.int64, device=self.device
            )
            self._contact_slot_shape_ids = torch.as_tensor(
                slot_shapes, dtype=torch.int32, device=self.device
            )
            self._contact_slot_candidate_ids = torch.as_tensor(
                slot_candidates, dtype=torch.int64, device=self.device
            )
        else:
            self._contact_slot_geom_indices = torch.zeros((0,), dtype=torch.int64, device=self.device)
            self._contact_slot_body_indices = torch.zeros((0,), dtype=torch.int64, device=self.device)
            self._contact_slot_shape_ids = torch.zeros((0,), dtype=torch.int32, device=self.device)
            self._contact_slot_candidate_ids = torch.zeros((0,), dtype=torch.int64, device=self.device)
        self._contact_shape_slot_indices = {
            shape: torch.as_tensor(
                [i for i, value in enumerate(slot_shapes) if value == shape],
                dtype=torch.int64,
                device=self.device,
            )
            for shape in (0, 1, 2, 3, 4)
        }
        self._contact_active = torch.zeros((B, self._contact_slots), dtype=torch.bool, device=self.device)
        self._contact_world_active = torch.zeros((B,), dtype=torch.bool, device=self.device)
        self._contact_body = torch.full((B, self._contact_slots), -1, dtype=torch.int64, device=self.device)
        self._contact_geom = torch.full((B, self._contact_slots), -1, dtype=torch.int64, device=self.device)
        self._contact_point = torch.zeros((B, self._contact_slots, 3), dtype=torch.float32, device=self.device)
        self._contact_normal = torch.zeros_like(self._contact_point)
        self._contact_distance = torch.full((B, self._contact_slots), 1.0e6, dtype=torch.float32, device=self.device)
        self._contact_normal_lambda = torch.zeros_like(self._contact_distance)
        self._contact_tangent_lambda = torch.zeros((B, self._contact_slots, 2), dtype=torch.float32, device=self.device)
        # Fixed storage for per-world active-slot compaction.  These tensors
        # are allocated once so their addresses remain valid across CUDA Graph
        # capture, replay, snapshot restoration, and masked resets.
        self._contact_pgs_active_slots = torch.zeros(
            (B, self._contact_slots), dtype=torch.int32, device=self.device
        )
        self._contact_pgs_active_count = torch.zeros(
            (B,), dtype=torch.int32, device=self.device
        )
        self._contact_count = torch.zeros((B, self.n_bodies), dtype=torch.int32, device=self.device)
        self._contact_summary_active = torch.zeros((B, self.n_bodies), dtype=torch.bool, device=self.device)
        self._contact_summary_distance = torch.zeros((B, self.n_bodies), dtype=torch.float32, device=self.device)
        # 这些公开 summary 张量由 device-field plan 持有稳定引用，只分配一次，
        # 避免每次命名状态读取都新建 zeros。
        self._body_contact_active = torch.zeros_like(self._contact_summary_active)
        self._body_contact_count = torch.zeros_like(self._contact_count)
        self._contact_jacobian = torch.zeros((B, self._contact_slots, max(1, self.n_dof)), dtype=torch.float32, device=self.device)
        # Stage 19：固定形状的 dynamics/contact 临时量一次分配并在 tick 间复用。
        self._contact_axes = torch.zeros((B, 3, self._contact_slots, 3), dtype=torch.float32, device=self.device)
        self._contact_jacobians = torch.zeros(
            (B, 3, self._contact_slots, max(1, self.n_dof)),
            dtype=torch.float32,
            device=self.device,
        )
        contact_response_dtype = (
            torch.float64
            if self.device.type == "cuda" and self.contact_precision == "f64"
            else torch.float32
        )
        # Store the three mass-response RHS in axis-major order so each axis
        # slice is contiguous for the ordered PGS backend.
        self._contact_mass_response = torch.zeros(
            (3, B, max(1, self.n_dof), self._contact_slots),
            dtype=contact_response_dtype,
            device=self.device,
        )
        self._contact_jacobian_axes = torch.zeros(
            (3, B, self._contact_slots, max(1, self.n_dof)),
            dtype=contact_response_dtype,
            device=self.device,
        )
        self._contact_mass_diagonal = torch.zeros(
            (3, B, self._contact_slots),
            dtype=contact_response_dtype,
            device=self.device,
        )
        # The active response route and CUDA Graph capture both require stable
        # factor/output addresses.  Keep the factorization result and status in
        # constructor-owned storage so eager and CUDA Graph routes share the
        # same stable factor/output addresses.
        self._contact_response_factor = torch.zeros(
            (B, max(1, self.n_dof), max(1, self.n_dof)),
            # The only eligible route is explicitly f32; keeping this storage
            # f32 avoids charging the unchanged default f64 route twice.
            dtype=torch.float32,
            device=self.device,
        )
        self._contact_response_factor_info = torch.zeros(
            (B,), dtype=torch.int32, device=self.device
        )
        # P1/P12 own a separate fixed factor workspace.  Keeping it distinct
        # from the active-slot Cholesky storage makes the production P0 path
        # byte-for-byte unchanged when the candidate is disabled.
        if self._contact_topology_child_schur_enabled:
            self._contact_topology_factor = torch.zeros(
                (B, max(1, self.n_dof), max(1, self.n_dof)),
                dtype=torch.float32,
                device=self.device,
            )
            self._contact_topology_root_factor = torch.zeros(
                (B, 6, 6), dtype=torch.float32, device=self.device
            )
            self._contact_topology_child_info = torch.zeros(
                (B,), dtype=torch.int32, device=self.device
            )
            self._contact_topology_root_info = torch.zeros(
                (B,), dtype=torch.int32, device=self.device
            )
        else:
            self._contact_topology_factor = None
            self._contact_topology_root_factor = None
            self._contact_topology_child_info = None
            self._contact_topology_root_info = None
        self._contact_bias = torch.zeros(
            (B, self._contact_slots),
            dtype=contact_response_dtype,
            device=self.device,
        )
        self._contact_motion_rot = torch.zeros((B, max(1, self.n_dof), 3), dtype=torch.float32, device=self.device)
        self._contact_motion_lin = torch.zeros_like(self._contact_motion_rot)
        self._passive_force = torch.zeros_like(self._qvel)
        self._eye3 = torch.eye(3, dtype=torch.float32, device=self.device)
        self._eye_dof = torch.eye(max(1, self.n_dof), dtype=torch.float32, device=self.device)
        self._basis_vectors = self._eye3
        self._contact_friction = torch.zeros((B, self._contact_slots), dtype=torch.float32, device=self.device)
        # Randomization owns only world-local tensors.  The shared model,
        # topology and graph-storage addresses remain immutable.  Disabled
        # tasks intentionally retain their previous dense/contact hot path.
        self._world_randomization_summary: dict[str, Any] = {
            "configured": self._world_randomization_enabled,
            "enabled": False,
            "schema_id": None,
            "reference_profile": None,
            "lifetime": None,
            "inertia_policy": "reference_mass_only",
        }
        if self._world_randomization_enabled:
            self._world_friction_mu = torch.ones(
                (B,), dtype=torch.float32, device=self.device
            )
            self._world_base_mass_delta = torch.zeros(
                (B,), dtype=torch.float32, device=self.device
            )
            self._world_body_mass = self._v("body_mass").unsqueeze(0).expand(
                B, -1
            ).clone()
            self._world_body_inertia = self._v("body_inertia").unsqueeze(0).expand(
                B, -1, -1
            ).clone()
            self._world_push_event_steps = torch.full(
                (B, self._world_push_capacity),
                -1,
                dtype=torch.int32,
                device=self.device,
            )
            self._world_push_velocity_xy = torch.zeros(
                (B, self._world_push_capacity, 2),
                dtype=torch.float32,
                device=self.device,
            )
            self._world_push_cursor = torch.zeros(
                (B,), dtype=torch.int32, device=self.device
            )
            self._world_episode_step = torch.zeros(
                (B,), dtype=torch.int32, device=self.device
            )
            self._world_randomization_initialized = torch.zeros(
                (B,), dtype=torch.bool, device=self.device
            )
            self._world_push_on_reset_boundary = torch.zeros(
                (B,), dtype=torch.bool, device=self.device
            )
            self._root_linear_dof_indices = self._resolve_root_linear_dof_indices()
        else:
            self._world_friction_mu = None
            self._world_base_mass_delta = None
            self._world_body_mass = None
            self._world_body_inertia = None
            self._world_push_event_steps = None
            self._world_push_velocity_xy = None
            self._world_push_cursor = None
            self._world_episode_step = None
            self._world_randomization_initialized = None
            self._world_push_on_reset_boundary = None
            self._root_linear_dof_indices = torch.zeros(
                (0,), dtype=torch.int64, device=self.device
            )
        self._contact_ground_height = float(model.get("ground_height", 0.0))
        self._contact_margin = float(model.get("ground_contact_margin", 1.0e-6))
        self._contact_bias_relaxation = float(model.get("contact_bias_relaxation", 0.2))
        self._contact_bias_max_velocity = float(model.get("contact_bias_max_velocity", 0.25))
        self._contact_iterations = max(1, int(model.get("contact_solver_iterations", 1)))
        self._contact_triton_disabled = False
        self._contact_pgs_fused_disabled = False
        self._contact_pgs_backend_selected = _select_contact_pgs_backend(
            device_type=self.device.type,
            contact_enabled=self.contact_enabled,
            n_dof=self.n_dof,
        )
        self._contact_pgs_backend_effective = self._contact_pgs_backend_selected
        self._contact_pgs_fused_attempted = False
        self._contact_pgs_fused_qualified = False
        self._contact_pgs_failed_closed = False
        self._contact_pgs_fallback_reason = _contact_pgs_initial_fallback_reason(
            device_type=self.device.type,
            contact_enabled=self.contact_enabled,
            n_dof=self.n_dof,
            selected=self._contact_pgs_backend_selected,
        )
        self._contact_response_backend_selected = _select_contact_response_backend(
            device_type=self.device.type,
            contact_enabled=self.contact_enabled,
            contact_precision=self.contact_precision,
            n_dof=self.n_dof,
            fixed_topology_child_schur=(
                self._contact_topology_child_schur_enabled
            ),
            root_factor_6x6=self._contact_root_factor_6x6_enabled,
        )
        self._contact_response_backend_effective = (
            _CONTACT_RESPONSE_TORCH_BACKEND
        )
        self._contact_response_triton_attempted = False
        self._contact_response_triton_qualified = False
        self._contact_response_triton_disabled = False
        self._contact_response_failed_closed = False
        self._contact_response_fallback_reason: str | None = None
        self._contact_topology_qualified = False
        self._contact_topology_failed_closed = False
        self._contact_topology_error: str | None = None
        # 只由 developer profiling 临时挂载；默认值保持 None，不进入正常 tick 计时。
        self._profile_collector = None
        # CUDA Graph ownership is immutable construction policy.  The runtime
        # may invalidate and recapture the configured graph, but cannot change
        # this capture mode through a post-build setter.
        self._cuda_graph_enabled = bool(cuda_graph)
        if self._cuda_graph_enabled and self.device.type != "cuda":
            raise RuntimeError("CUDA Graph requires the CUDA backend")
        self._cuda_graph = None
        self._cuda_graph_key = None
        self._cuda_graph_status = "armed" if self._cuda_graph_enabled else "disabled"
        self._cuda_graph_invalidation_reason = (
            "construction_configured" if self._cuda_graph_enabled else "not_enabled"
        )
        self._cuda_graph_error = None
        self._qM = torch.zeros((B, max(1, self.n_dof), max(1, self.n_dof)), dtype=torch.float32, device=self.device)
        self._qfrc_bias = torch.zeros_like(self._qvel)
        self._crb_H = torch.zeros((B, self.n_bodies, 3, 3), dtype=torch.float32, device=self.device)
        # Dense dynamics and RNE share the same world-space body inertia for a
        # tick.  Materialize it once instead of rebuilding the quaternion
        # rotation separately in CRB and bias assembly.
        self._body_inertia_world = torch.zeros(
            (B, self.n_bodies, 3, 3), dtype=torch.float32, device=self.device
        )
        self._crb_mcom = torch.zeros((B, self.n_bodies, 3), dtype=torch.float32, device=self.device)
        self._crb_m = torch.zeros((B, self.n_bodies), dtype=torch.float32, device=self.device)
        self._rne_alin = torch.zeros_like(self._body_xpos)
        self._rne_aang = torch.zeros_like(self._body_xpos)
        self._rne_fsp = torch.zeros_like(self._body_xpos)
        self._rne_tsp = torch.zeros_like(self._body_xpos)
        self._xanchor = torch.zeros((B, self.n_joints, 3), dtype=torch.float32, device=self.device)
        self._xaxis = torch.zeros_like(self._xanchor)
        self._univ_axis0 = torch.zeros_like(self._xanchor)
        self._univ_axis1 = torch.zeros_like(self._xanchor)
        self._support = self._build_support()
        self._support_device = torch.as_tensor(
            self._support, dtype=torch.bool, device=self.device
        )
        self._dof_body_host = tuple(
            int(route[3]) for route in self._compiled_dof_routes
        )
        self._dof_body_indices = torch.as_tensor(
            self._dof_body_host, dtype=torch.int64, device=self.device
        )
        self._support_dof_indices = tuple(
            torch.as_tensor(
                np.flatnonzero(self._support[body, :self.n_dof]),
                dtype=torch.int64,
                device=self.device,
            )
            for body in range(self.n_bodies)
        )
        self._ground_contact_dof_indices = tuple(
            tuple(np.flatnonzero(self._support[body, :self.n_dof]).tolist())
            for body in self._ground_contact_bodies
        )
        (
            slot_dof_indices,
            slot_dof_mask,
            pair_slots,
            pair_dofs,
        ) = self._build_ground_contact_slot_indexing()
        self._contact_slot_dof_mask_host = slot_dof_mask
        self._contact_slot_dof_indices = torch.as_tensor(
            slot_dof_indices,
            dtype=torch.int64,
            device=self.device,
        )
        self._contact_slot_dof_mask = torch.as_tensor(
            slot_dof_mask,
            dtype=torch.bool,
            device=self.device,
        )
        self._contact_pair_slots = torch.as_tensor(
            pair_slots,
            dtype=torch.int64,
            device=self.device,
        )
        self._contact_pair_dofs = torch.as_tensor(
            pair_dofs,
            dtype=torch.int64,
            device=self.device,
        )
        if self.n_dof:
            self._contact_dof_joint_indices = self._v("dof_joint")[:self.n_dof].to(dtype=torch.int64)
            self._contact_dof_sub_indices = self._v("dof_subdof")[:self.n_dof].to(dtype=torch.int64)
            self._contact_dof_types = self._v("jnt_type").index_select(
                0, self._contact_dof_joint_indices
            )
            self._contact_dof_joint_host = tuple(
                int(value) for value in self._contact_dof_joint_indices.detach().cpu().tolist()
            )
            self._contact_dof_sub_host = tuple(
                int(value) for value in self._contact_dof_sub_indices.detach().cpu().tolist()
            )
            self._contact_dof_type_host = tuple(
                int(value) for value in self._contact_dof_types.detach().cpu().tolist()
            )
        else:
            self._contact_dof_joint_indices = torch.zeros((0,), dtype=torch.int64, device=self.device)
            self._contact_dof_sub_indices = torch.zeros((0,), dtype=torch.int64, device=self.device)
            self._contact_dof_types = torch.zeros((0,), dtype=torch.int32, device=self.device)
            self._contact_dof_joint_host = ()
            self._contact_dof_sub_host = ()
            self._contact_dof_type_host = ()
        self._joint_dof_count = tuple(self._dof_count(int(v)) for v in self._model["jnt_type"].detach().cpu().numpy())
        self._device_state_field_names = (
            "qpos", "qvel", "qacc", "ctrl", "act",
            "body_xpos", "body_xquat", "geom_xpos", "geom_xquat",
            "site_xpos", "site_xquat",
        ) + (
            (
                "ground_contact_active", "body_contact_active",
                "ground_contact_count", "body_contact_count", "ground_contact_geom",
            ) if self.contact_enabled else ()
        )
        self._device_state_field_set = frozenset(self._device_state_field_names)
        self._device_fields = {
            "qpos": self._qpos,
            "qvel": self._qvel,
            "qacc": self._qacc,
            "ctrl": self._ctrl,
            "act": self._act,
            "body_xpos": self._body_xpos,
            "body_xquat": self._body_xquat,
            "geom_xpos": self._geom_xpos,
            "geom_xquat": self._geom_xquat,
            "site_xpos": self._site_xpos,
            "site_xquat": self._site_xquat,
        }
        if self.contact_enabled:
            self._device_fields.update({
                "ground_contact_active": self._contact_summary_active,
                "body_contact_active": self._body_contact_active,
                "ground_contact_count": self._contact_count,
                "body_contact_count": self._body_contact_count,
                "ground_contact_geom": self._contact_geom,
            })
        self._kinematics_valid = False
        self._refresh_kinematics()

    @staticmethod
    def _dof_count(joint_type: int) -> int:
        return {0: 6, 1: 3, 2: 1, 3: 1, 4: 2}.get(int(joint_type), 0)

    def _compile_static_traversal(self) -> None:
        """Lower immutable tree/index routes used by the hot path once."""

        def host(name: str, *, dtype=np.int32) -> np.ndarray:
            return self._model[name].detach().cpu().numpy().astype(dtype, copy=False)

        parent = host("body_parentid")
        body_joint_start = host("body_jntadr")
        body_joint_count = host("body_jntnum")
        joint_type = host("jnt_type")
        qpos_adr = host("jnt_qposadr")
        dof_adr = host("jnt_dofadr")
        joint_parent = host("jnt_parent_body")
        joint_child = host("jnt_child_body")
        dof_joint = host("dof_joint")
        dof_subdof = host("dof_subdof")

        body_routes: list[tuple[int, int, tuple[tuple[int, int, int, int, int], ...], bool]] = []
        for body in range(self.n_bodies):
            start = int(body_joint_start[body])
            count = int(body_joint_count[body])
            joints = tuple(
                (
                    joint,
                    int(joint_type[joint]),
                    int(qpos_adr[joint]),
                    int(dof_adr[joint]),
                    self._dof_count(int(joint_type[joint])),
                )
                for joint in range(start, min(start + count, self.n_joints))
            )
            body_routes.append(
                (body, int(parent[body]), joints, bool(joints and joints[0][1] == self.JOINT_FREE))
            )

        dof_routes = tuple(
            (
                dof,
                int(dof_joint[dof]),
                int(dof_subdof[dof]),
                int(joint_child[int(dof_joint[dof])]),
                int(joint_type[int(dof_joint[dof])]),
            )
            for dof in range(self.n_dof)
        )
        joint_routes = tuple(
            (
                joint,
                int(joint_parent[joint]),
                int(joint_child[joint]),
                int(joint_type[joint]),
                int(qpos_adr[joint]),
                int(dof_adr[joint]),
                self._dof_count(int(joint_type[joint])),
            )
            for joint in range(self.n_joints)
        )
        geom_bodies = tuple(int(value) for value in host("geom_bodyid"))
        site_bodies = tuple(int(value) for value in host("site_bodyid"))
        reverse_bodies = tuple((body, parent_id) for body, parent_id, _, _ in reversed(body_routes))

        moments = host("actuator_moment_dofadr")
        coefficients = self._model["actuator_moment_coef"].detach().cpu().numpy().astype(np.float32, copy=False)
        actuator_routes = tuple(
            tuple(
                (int(moments[actuator, slot]), float(coefficients[actuator, slot]))
                for slot in range(6)
                if float(coefficients[actuator, slot]) != 0.0
            )
            for actuator in range(self.n_actuators)
        )
        digest_payload = (
            tuple(body_routes),
            dof_routes,
            joint_routes,
            geom_bodies,
            site_bodies,
            actuator_routes,
        )
        self._compiled_body_routes = tuple(body_routes)
        self._compiled_reverse_bodies = reverse_bodies
        self._compiled_dof_routes = dof_routes
        self._compiled_joint_routes = joint_routes
        self._compiled_joint_type_host = tuple(route[3] for route in joint_routes)
        self._compiled_geom_bodies = geom_bodies
        self._compiled_site_bodies = site_bodies
        self._compiled_actuator_routes = actuator_routes
        self._compiled_traversal_digest = hashlib.sha256(repr(digest_payload).encode("utf-8")).hexdigest()[:16]

    def _build_support(self):
        support = np.zeros((self.n_bodies, max(1, self.n_dof)), dtype=np.bool_)
        parent = self._model["body_parentid"].detach().cpu().numpy().astype(np.int32)
        child_for_joint = self._model["jnt_child_body"].detach().cpu().numpy().astype(np.int32)
        dof_joint = self._model["dof_joint"].detach().cpu().numpy().astype(np.int32)
        for body in range(self.n_bodies):
            ancestors = set()
            node = body
            while node >= 0:
                ancestors.add(node)
                node = int(parent[node])
            for d in range(self.n_dof):
                j = int(dof_joint[d])
                if 0 <= j < self.n_joints and int(child_for_joint[j]) in ancestors:
                    support[body, d] = True
        return support

    def _build_ground_contact_layout(self):
        """Return immutable compact ground-row metadata for this template.

        This deliberately uses the same eligibility and candidate semantics as
        ``_contact_support_candidates`` used before layout compression.  It
        only removes unused rows; it does not change geometric contact or
        collision-mask policy.
        """
        geom_type = self._model["geom_type"].detach().cpu().numpy().astype(np.int32)
        geom_body = self._model["geom_bodyid"].detach().cpu().numpy().astype(np.int32)
        geom_contype = self._model["geom_contype"].detach().cpu().numpy().astype(np.int32)
        geom_conaffinity = self._model["geom_conaffinity"].detach().cpu().numpy().astype(np.int32)
        candidate_counts = {
            0: 8,  # box corners
            1: 1,  # sphere
            2: 2,  # capsule endpoints
            3: 2,  # cylinder cap rims
            4: 1,  # convex proxy
        }
        geom_ids: list[int] = []
        bodies: list[int] = []
        offsets: list[int] = []
        counts: list[int] = []
        shapes: list[int] = []
        offset = 0
        for geom_id in range(self.n_geoms):
            body = int(geom_body[geom_id])
            if body < 0 or body >= self.n_bodies:
                continue
            # Match the previous runtime test exactly: either side carrying
            # the ground collision bit makes this geom eligible.
            if (int(geom_contype[geom_id]) & 1) == 0 and (int(geom_conaffinity[geom_id]) & 1) == 0:
                continue
            count = candidate_counts.get(int(geom_type[geom_id]), 0)
            if count == 0:
                continue
            geom_ids.append(geom_id)
            bodies.append(body)
            offsets.append(offset)
            counts.append(count)
            shapes.append(int(geom_type[geom_id]))
            offset += count
        return tuple(geom_ids), tuple(bodies), tuple(offsets), tuple(counts), tuple(shapes)

    def _build_ground_contact_slot_indexing(self):
        """Compile the slot-to-DOF gather map for the immutable template.

        A contact geom has one fixed support set for every candidate point.  The
        old Jacobian path rediscovered that set and called ``_motion`` for each
        slot/DOF.  Keep the map private and local, then let the device path
        gather all support motions in one batched operation.  ``-1`` entries
        are represented as index zero plus a false mask so an empty support
        set remains an all-zero Jacobian without a host/device branch.
        """
        width = max(1, self.n_dof)
        indices = np.zeros((self._contact_slots, width), dtype=np.int64)
        mask = np.zeros((self._contact_slots, width), dtype=np.bool_)
        pair_slots: list[int] = []
        pair_dofs: list[int] = []
        for layout_id, dofs in enumerate(self._ground_contact_dof_indices):
            base = self._ground_contact_slot_offsets[layout_id]
            count = self._ground_contact_slot_counts[layout_id]
            if not dofs:
                continue
            dof_array = np.asarray(dofs, dtype=np.int64)
            for local_id in range(count):
                slot = base + local_id
                indices[slot, dof_array] = dof_array
                mask[slot, dof_array] = True
                pair_slots.extend([slot] * int(dof_array.size))
                pair_dofs.extend(int(value) for value in dof_array)
        return indices, mask, np.asarray(pair_slots, dtype=np.int64), np.asarray(pair_dofs, dtype=np.int64)

    def _v(self, name: str):
        return self._model[name]

    def _resolve_root_linear_dof_indices(self):
        """Resolve free-root translational velocity coordinates once."""

        import torch

        if self.n_dof < 3:
            return torch.zeros((0,), dtype=torch.int64, device=self.device)
        joint_types = self._model.get("jnt_type")
        joint_dof = self._model.get("jnt_dofadr")
        if joint_types is not None and joint_dof is not None:
            for joint, kind in enumerate(joint_types.detach().cpu().tolist()):
                if int(kind) == self.JOINT_FREE:
                    start = int(joint_dof[joint].item())
                    if 0 <= start and start + 3 <= self.n_dof:
                        return torch.arange(
                            start,
                            start + 3,
                            dtype=torch.int64,
                            device=self.device,
                        )
        # Static profiles with no free joint remain valid.  This fallback is
        # only reachable when their YAML explicitly asks for push scheduling.
        return torch.arange(0, 3, dtype=torch.int64, device=self.device)

    def _topology_schur_capability_check(self) -> tuple[str, ...]:
        """Return construction-time guards for the P1/P12 contact path.

        The lowering intentionally accepts one free six-DOF root followed by
        fixed one-DOF hinge/slide children in the local coordinate order.  It
        never changes an unsupported task into a dense candidate implicitly.
        """

        reasons: list[str] = []
        if not self.contact_enabled:
            reasons.append("ground_contact_required")
        if self.device.type != "cuda":
            reasons.append("cuda_required")
        if self.contact_precision != "f32":
            reasons.append("f32_contact_precision_required")
        if _triton is None:
            reasons.append("triton_required")
        if self.n_dof < 7 or self.n_dof > 32:
            reasons.append("dof_count_must_be_in_7_to_32")
        if not self._compiled_body_routes:
            reasons.append("empty_body_routes")
            return tuple(reasons)

        root_candidates = [
            route
            for route in self._compiled_body_routes
            if int(route[1]) < 0
        ]
        if len(root_candidates) != 1:
            reasons.append("exactly_one_root_body_required")
            return tuple(reasons)
        root_body, _, root_joints, _ = root_candidates[0]
        if int(root_body) != 0 or len(root_joints) != 1:
            reasons.append("body_zero_must_own_one_free_root_joint")
        else:
            _, root_type, _, root_start, root_count = root_joints[0]
            if (
                int(root_type) != self.JOINT_FREE
                or int(root_start) != 0
                or int(root_count) != 6
            ):
                reasons.append("root_must_be_dof_0_to_5_free_joint")

        child_dofs: list[int] = []
        for body, parent, joints, _ in self._compiled_body_routes:
            if int(body) == 0:
                continue
            if int(parent) < 0 or len(joints) != 1:
                reasons.append(f"body_{body}_must_have_one_parent_joint")
                continue
            _, joint_type, _, dof_start, dof_count = joints[0]
            if int(joint_type) not in {self.JOINT_HINGE, self.JOINT_SLIDE}:
                reasons.append(f"body_{body}_joint_type_not_hinge_or_slide")
                continue
            if int(dof_count) != 1:
                reasons.append(f"body_{body}_must_have_one_dof")
                continue
            child_dofs.append(int(dof_start))
        if sorted(child_dofs) != list(range(6, self.n_dof)):
            reasons.append("child_dofs_must_cover_contiguous_6_to_n_minus_1")
        return tuple(reasons)

    def set_profile_collector(self, collector) -> None:
        """挂载可选的 Stage 17 分段计时 collector。"""

        self._profile_collector = collector
        if collector is not None:
            self._invalidate_cuda_graph("profiling_collector_attached")

    def _masked_device_reset_tensor_pointers(self) -> dict[str, int]:
        """Return every persistent tensor whose storage a reset may touch."""

        import torch

        pointers: dict[str, int] = {}
        for name, value in self._device_fields.items():
            if isinstance(value, torch.Tensor):
                pointers[f"state.{name}"] = int(value.data_ptr())
        for name in (
            "_body_xpos",
            "_body_xquat",
            "_body_xmat",
            "_body_linear_vel",
            "_body_angular_vel",
            "_geom_xpos",
            "_geom_xquat",
            "_geom_xmat",
            "_site_xpos",
            "_site_xquat",
            "_xanchor",
            "_xaxis",
            "_univ_axis0",
            "_univ_axis1",
        ):
            value = getattr(self, name, None)
            if isinstance(value, torch.Tensor):
                pointers[f"fk.{name}"] = int(value.data_ptr())
        for name, value in vars(self).items():
            if name.startswith("_contact_") and isinstance(value, torch.Tensor):
                pointers[f"contact.{name}"] = int(value.data_ptr())
        return pointers

    def runtime_boundary_snapshot(self) -> dict[str, Any]:
        """Return diagnostic-only storage and stream provenance.

        The Taichi FK path receives these Torch tensors as external ndarrays;
        no copy is expected at this boundary.  This method is intentionally
        called by diagnostics/resource inspection, never from the simulation
        tick, so pointer and stream queries cannot become hot-path syncs.
        """

        import torch

        names = (
            "qpos",
            "qvel",
            "body_xpos",
            "body_xquat",
            "body_xmat",
            "body_linear_vel",
            "body_angular_vel",
            "geom_xpos",
            "geom_xquat",
            "geom_xmat",
            "site_xpos",
            "site_xquat",
            "xanchor",
            "xaxis",
            "univ_axis0",
            "univ_axis1",
        )
        fields = {
            "qpos": self._qpos,
            "qvel": self._qvel,
            "body_xpos": self._body_xpos,
            "body_xquat": self._body_xquat,
            "body_xmat": self._body_xmat,
            "body_linear_vel": self._body_linear_vel,
            "body_angular_vel": self._body_angular_vel,
            "geom_xpos": self._geom_xpos,
            "geom_xquat": self._geom_xquat,
            "geom_xmat": self._geom_xmat,
            "site_xpos": self._site_xpos,
            "site_xquat": self._site_xquat,
            "xanchor": self._xanchor,
            "xaxis": self._xaxis,
            "univ_axis0": self._univ_axis0,
            "univ_axis1": self._univ_axis1,
        }
        stream_id = None
        if self.device.type == "cuda":
            stream_id = int(torch.cuda.current_stream(self.device).cuda_stream)
        pointers = {name: int(fields[name].data_ptr()) for name in names}
        external_ndarray_pointers = dict(pointers)
        if self.contact_enabled:
            pointers.update(self._contact_response_fixed_tensor_pointers())
        return {
            "device": str(self.device),
            "stream_id": stream_id,
            "torch_tensor_pointers": pointers,
            "taichi_external_ndarray_pointers": (
                external_ndarray_pointers
                if self.kinematics_backend == "taichi"
                else {}
            ),
            "external_ndarray_policy": (
                "shared_torch_storage_zero_copy_v1"
                if self.kinematics_backend == "taichi"
                else "not_applicable_torch_fk"
            ),
            "external_ndarray_lifetime": (
                "persistent_view_per_buffer_v1"
                if self.kinematics_backend == "taichi"
                else "not_applicable_torch_fk"
            ),
            "pointer_fields": list(pointers),
            "masked_device_reset_tensor_pointers": (
                self._masked_device_reset_tensor_pointers()
            ),
        }

    def _ensure_taichi_external_views(self) -> dict[str, Any]:
        """每个持久 Torch buffer 只导入一次 Taichi storage view。

        普通 Taichi kernel 适配器会把每个 Torch 参数转成新的 DLPack
        ``ExternalDenseView``。本 runtime 的状态和输出 tensor 形状固定，因此
        view 属于生命周期资源，不应成为每次 launch 的临时参数。复用每个 buffer
        的 view 可以保留零拷贝，同时避开重复 native import/retire。

        Forge interop 缺失或不支持时回退到既有 raw-pointer 路径，保持 CPU 与旧版
        Taichi 安装的兼容性，不改变 public runtime contract。
        """

        if self._taichi_external_views is not None:
            return self._taichi_external_views
        if self._taichi_fk is None:
            raise RuntimeError("Taichi FK must be initialized before importing external views")

        fields = {
            "qpos": self._qpos,
            "qvel": self._qvel,
            "reset_ids": self._taichi_reset_ids,
            "body_xpos": self._body_xpos,
            "body_xquat": self._body_xquat,
            "body_xmat": self._body_xmat,
            "body_linear_vel": self._body_linear_vel,
            "body_angular_vel": self._body_angular_vel,
            "geom_xpos": self._geom_xpos,
            "geom_xquat": self._geom_xquat,
            "geom_xmat": self._geom_xmat,
            "site_xpos": self._site_xpos,
            "site_xquat": self._site_xquat,
            "xanchor": self._xanchor,
            "xaxis": self._xaxis,
            "univ_axis0": self._univ_axis0,
            "univ_axis1": self._univ_axis1,
        }
        if any(value is None for value in fields.values()):
            raise RuntimeError("Taichi external-view fields were initialized incompletely")

        try:
            from taichi_forge.interop import from_dlpack

            views = {name: from_dlpack(value) for name, value in fields.items()}
        except (ImportError, AttributeError, BufferError, RuntimeError, TypeError, ValueError):
            # 支持的 backend 仍可使用直接 Torch ndarray ABI，不把可选的 managed
            # view 提升为硬依赖。
            for view in locals().get("views", {}).values():
                close = getattr(view, "close", None)
                if callable(close):
                    close()
            views = {}
        self._taichi_external_views = views
        return views

    def _close_taichi_external_views(self) -> None:
        """在 runtime 关闭时释放持久 Taichi storage view。"""

        views = self._taichi_external_views
        self._taichi_external_views = {}
        if not views:
            return
        for view in views.values():
            close = getattr(view, "close", None)
            if callable(close):
                close()

    def _cuda_graph_capture_scope(self) -> str:
        """Return the capture scope that is safe for this runtime instance.

        Taichi FK launches use a runtime/stream boundary that cannot be
        nested in PyTorch's CUDA Graph capture.  The Taichi/contact route
        therefore captures one complete Torch physics substep and refreshes
        FK eagerly between graph replays.  The Torch-FK ground-contact
        profile uses a fixed capture-safe Cholesky path and records the
        complete tick.
        """

        if self.contact_enabled and self.kinematics_backend == "taichi":
            return "contact_core_full_v5"
        if self.contact_enabled:
            return "contact_full_v4"
        if self.kinematics_backend == "taichi":
            return "core_v2"
        return "full_v1"

    def _cuda_graph_capture_key(self) -> tuple[Any, ...]:
        """Build the immutable key required for safe replay reuse."""

        return (
            "static_template_cuda_graph_v3",
            self._compiled_traversal_digest,
            "articulated_fused_contact" if self.contact_enabled else "articulated_fused_no_contact",
            self.kinematics_backend,
            self.contact_precision,
            str(self._contact_mass_response.dtype),
            self._cuda_graph_capture_scope(),
            self.num_envs,
            str(self._ctrl.dtype),
            str(self.device),
            self.control_substeps,
            self._contact_iterations if self.contact_enabled else 0,
            (
                "world_randomization_fixed_capacity_v1",
                self._world_randomization_enabled,
                self._world_push_capacity if self._world_randomization_enabled else 0,
            ),
            (
                "world_local_ascending_compaction_v1"
                if self.contact_enabled
                else "disabled_explicitly"
            ),
            (
                self._next_contact_response_backend()
                if self.contact_enabled
                else "disabled_explicitly"
            ),
            (
                "contact_response_shape_and_candidate_v1",
                self._contact_response_requested_backend,
                self.n_dof if self.contact_enabled else 0,
                self._contact_slots if self.contact_enabled else 0,
                self._contact_topology_child_schur_enabled,
                self._contact_root_factor_6x6_enabled,
            ),
            (
                "constructor_owned_graph_stable_v1"
                if self.contact_enabled
                else "disabled_explicitly"
            ),
        )

    def _invalidate_cuda_graph(self, reason: str) -> None:
        """Drop a capture whenever state shape/profile/topology can change."""

        self._cuda_graph = None
        self._cuda_graph_key = None
        self._cuda_graph_invalidation_reason = str(reason)
        self._cuda_graph_error = None
        self._cuda_graph_status = "armed" if self._cuda_graph_enabled else "disabled"

    def _cuda_graph_state_snapshot(self):
        snapshot = {
            name: field.clone()
            for name, field in (
                ("qpos", self._qpos),
                ("qvel", self._qvel),
                ("qacc", self._qacc),
                ("ctrl", self._ctrl),
                ("act", self._act),
            )
        }
        if self.contact_enabled:
            # The capture warm-up must preserve semantically live PGS state.
            # Response/Jacobian workspaces are overwritten by every complete
            # contact preparation, while tangent lambdas are intentionally
            # warm-started and therefore require explicit restoration.
            snapshot["contact_normal_lambda"] = self._contact_normal_lambda.clone()
            snapshot["contact_tangent_lambda"] = self._contact_tangent_lambda.clone()
            snapshot["contact_pgs_active_slots"] = (
                self._contact_pgs_active_slots.clone()
            )
            snapshot["contact_pgs_active_count"] = (
                self._contact_pgs_active_count.clone()
            )
        return snapshot

    def _cuda_graph_synchronize_torch_stream(self) -> None:
        """Complete the current PyTorch producer stream before Taichi reads."""

        import torch

        torch.cuda.current_stream(device=self.device).synchronize()

    def _cuda_graph_synchronize_taichi_runtime(self) -> None:
        """Complete Taichi external-view writes before PyTorch reads them."""

        import taichi as ti

        ti.sync()

    def _refresh_taichi_kinematics_at_graph_boundary(self) -> None:
        """Bridge the two asynchronous runtimes at a graph/FK boundary.

        Persistent DLPack views preserve storage ownership but do not repeat
        the producer-stream hand-off performed when the view is first
        imported.  Until the runtimes expose event-level stream interop, host
        fences provide the explicit producer/consumer ordering required by
        each contact-core replay.
        """

        self._cuda_graph_synchronize_torch_stream()
        self._kinematics_valid = False
        try:
            self._refresh_kinematics()
        finally:
            # Drain even when a later FK launch raises: an earlier pose kernel
            # may already own the shared external storage.
            self._cuda_graph_synchronize_taichi_runtime()

    def _restore_cuda_graph_state_snapshot(self, snapshot) -> None:
        for name, field in (
            ("qpos", self._qpos),
            ("qvel", self._qvel),
            ("qacc", self._qacc),
            ("ctrl", self._ctrl),
            ("act", self._act),
        ):
            field.copy_(snapshot[name])
        if self.contact_enabled:
            self._contact_normal_lambda.copy_(snapshot["contact_normal_lambda"])
            self._contact_tangent_lambda.copy_(snapshot["contact_tangent_lambda"])
            self._contact_pgs_active_slots.copy_(
                snapshot["contact_pgs_active_slots"]
            )
            self._contact_pgs_active_count.copy_(
                snapshot["contact_pgs_active_count"]
            )
        if (
            self.device.type == "cuda"
            and self._cuda_graph_capture_scope() == "contact_core_full_v5"
        ):
            self._refresh_taichi_kinematics_at_graph_boundary()
        else:
            self._refresh_kinematics()

    def _cuda_graph_resource_summary(self) -> dict[str, Any]:
        """Describe the graph policy without triggering any device work."""

        capture_scope = self._cuda_graph_capture_scope()
        contact_core = capture_scope == "contact_core_full_v5"
        return {
            "available": self.device.type == "cuda",
            "enabled": self._cuda_graph_enabled,
            "status": self._cuda_graph_status,
            "scope": capture_scope,
            "key": list(self._cuda_graph_key) if self._cuda_graph_key is not None else None,
            "invalidation_reason": self._cuda_graph_invalidation_reason,
            "error": self._cuda_graph_error,
            "capture_policy": "lazy_first_step_fixed_scope_v3",
            "capture_unit": (
                "one_complete_torch_core_substep"
                if contact_core
                else "complete_tick_or_fixed_torch_core"
            ),
            "fk_outside_graph": capture_scope in {
                "core_v2",
                "contact_core_v3",
                "contact_core_full_v5",
            },
            "inter_substep_fk": (
                "eager_taichi_refresh" if contact_core else "not_applicable"
            ),
            "interop_ordering": (
                "host_fenced_v1" if contact_core else "native_scope_policy_v1"
            ),
            "invalidates_on": [
                "host_full_reset",
                "failed_masked_device_reset",
                "state_write",
                "workspace_reset",
                "kinematics_refresh",
                "prewarm",
                "profile_collector",
            ],
            "preserves_on": ["fixed_pointer_masked_device_reset"],
            "masked_device_reset_storage_policy": (
                "all_state_fk_contact_compaction_pointers_v1"
            ),
        }

    def _capture_cuda_graph(self) -> bool:
        """Capture one fixed-shape tick or Torch-only core segment.

        ``full_v1`` records the complete no-contact dense tick.  ``core_v2``
        records only dynamics/contact/integration.  ``contact_core_full_v5``
        records one complete dense/contact/PGS/integration substep and replays
        it once per control substep, refreshing Taichi FK outside the graph
        after every replay.
        """

        import torch

        if not self._cuda_graph_enabled or self.device.type != "cuda":
            return False
        if self._profile_collector is not None:
            self._invalidate_cuda_graph("profiling_collector_attached")
            return False
        snapshot = self._cuda_graph_state_snapshot()
        graph = torch.cuda.CUDAGraph()
        capture_scope = self._cuda_graph_capture_scope()
        try:
            if capture_scope == "contact_core_full_v5":
                # Recompute unconditionally.  A preceding masked reset writes
                # qpos/qvel on Torch's stream before launching asynchronous
                # Taichi FK, so merely draining that old FK could preserve a
                # stale read.  The fenced refresh makes the capture independent
                # of reset-side ordering.
                self._refresh_taichi_kinematics_at_graph_boundary()
            elif (
                capture_scope in {"core_v2", "contact_core_v3"}
                and not self._kinematics_valid
            ):
                self._refresh_kinematics()
            # First-use kernel compilation and allocator setup are not capture
            # safe on all Torch/CUDA combinations.  Warm once, restore the
            # public state, then capture the exact first tick/core segment.
            if capture_scope in {"full_v1", "contact_full_v4"}:
                self._step_eager(self.control_substeps)
            elif capture_scope == "contact_core_full_v5":
                # Qualify/compile the fused Triton contact backend before
                # capture.  Qualification may synchronize and allocate
                # snapshots, neither of which may occur inside capture.
                with torch.no_grad():
                    self._step_one_core()
            elif capture_scope == "contact_core_v3":
                for _ in range(self.control_substeps):
                    self._prepare_contact_graph(1)
                    self._step_contact_graph_segment(1)
            else:
                self._step_core(self.control_substeps)
            if self.contact_enabled:
                # PGS qualification from the warm step is the backend proof
                # required by the f32 active response route.  Complete its own
                # compile/sync/fallback decision now; capture and replay then
                # execute only the already-qualified fixed route.
                self._qualify_contact_response_before_cuda_graph()
            self._restore_cuda_graph_state_snapshot(snapshot)
            torch.cuda.synchronize()
            if capture_scope == "contact_core_v3":
                self._prepare_contact_graph(1)
            torch.cuda.synchronize()
            with torch.cuda.graph(graph):
                if capture_scope in {"full_v1", "contact_full_v4"}:
                    self._step_eager(self.control_substeps)
                elif capture_scope == "contact_core_full_v5":
                    with torch.no_grad():
                        self._step_one_core()
                elif capture_scope == "contact_core_v3":
                    self._step_contact_graph_segment(1)
                else:
                    self._step_core(self.control_substeps)
            # CUDA graph capture records operations but does not apply them.
            # Replay once so the first public call is exactly one tick/core
            # segment rather than a zero-tick arm operation.
            graph.replay()
            if capture_scope == "contact_core_full_v5":
                self._refresh_taichi_kinematics_at_graph_boundary()
                for _ in range(1, self.control_substeps):
                    graph.replay()
                    self._refresh_taichi_kinematics_at_graph_boundary()
            elif capture_scope == "contact_core_v3":
                for _ in range(1, self.control_substeps):
                    self._prepare_contact_graph(1)
                    graph.replay()
            torch.cuda.synchronize()
            if capture_scope in {"core_v2", "contact_core_v3"}:
                self._kinematics_valid = False
                self._refresh_kinematics()
        except Exception as exc:  # pragma: no cover - driver/version dependent
            self._restore_cuda_graph_state_snapshot(snapshot)
            self._cuda_graph = None
            self._cuda_graph_key = None
            self._cuda_graph_error = f"{type(exc).__name__}: {exc}"
            self._cuda_graph_status = "fallback"
            self._cuda_graph_invalidation_reason = "capture_failed"
            return False
        self._cuda_graph = graph
        self._cuda_graph_key = self._cuda_graph_capture_key()
        self._cuda_graph_status = "ready"
        self._cuda_graph_invalidation_reason = None
        self._cuda_graph_error = None
        return True

    def _run_cuda_graph_or_eager(self) -> None:
        if not self._cuda_graph_enabled:
            self._step_eager(self.control_substeps)
            return
        capture_scope = self._cuda_graph_capture_scope()
        if capture_scope == "contact_core_full_v5" and not self._kinematics_valid:
            self._refresh_taichi_kinematics_at_graph_boundary()
        elif (
            capture_scope in {"core_v2", "contact_core_v3"}
            and not self._kinematics_valid
        ):
            self._refresh_kinematics()
        if self._cuda_graph_key != self._cuda_graph_capture_key():
            self._invalidate_cuda_graph("capture_key_changed")
        if self._cuda_graph is None:
            if not self._capture_cuda_graph():
                self._step_eager(self.control_substeps)
            return
        if capture_scope == "contact_core_full_v5":
            for _ in range(self.control_substeps):
                self._cuda_graph.replay()
                self._refresh_taichi_kinematics_at_graph_boundary()
        elif capture_scope == "contact_core_v3":
            for _ in range(self.control_substeps):
                self._prepare_contact_graph(1)
                self._cuda_graph.replay()
        else:
            self._cuda_graph.replay()
        if capture_scope in {"core_v2", "contact_core_v3"}:
            self._kinematics_valid = False
            self._refresh_kinematics()

    def _step_eager(self, substeps: int) -> None:
        if int(substeps) != self.control_substeps:
            raise ValueError(f"static fused control_substeps={self.control_substeps}, got {substeps}")
        for _ in range(self.control_substeps):
            self._step_one()

    def _step_core(self, substeps: int) -> None:
        """Run the Torch-only dynamics/contact/integration portion of a tick."""

        import torch

        if int(substeps) != self.control_substeps:
            raise ValueError(f"static fused control_substeps={self.control_substeps}, got {substeps}")
        with torch.no_grad():
            for _ in range(self.control_substeps):
                self._step_one_core()

    def _prepare_contact_graph(self, substeps: int) -> None:
        """Run one eager preparation immediately before a PGS graph replay."""

        import torch

        if int(substeps) != 1:
            raise ValueError("contact CUDA Graph preparation must cover exactly one substep")
        with torch.no_grad():
            self._step_one_core(solve_contact=False, integrate=False)

    def _step_contact_graph_segment(self, substeps: int) -> None:
        """Replayable fixed one-substep PGS/integration tail."""

        import torch

        if int(substeps) != 1:
            raise ValueError("contact CUDA Graph segment must cover exactly one substep")
        with torch.no_grad():
            self._run_ground_contact_pgs()
            self._step_one_integration()

    def _contact_dof_motion_vectors(self):
        """Return world spatial motion vectors for all local DOFs in one pass.

        The fixed local-DOF loop deliberately keeps the old ``(B, 3)`` motion
        arithmetic for each DOF.  This avoids changing CUDA's reduction or
        elementwise tiling choice as B changes, while the expensive slot loop
        is still removed from Jacobian construction.
        """
        import torch

        rot = self._contact_motion_rot[:, :self.n_dof]
        lin = self._contact_motion_lin[:, :self.n_dof]
        rot.zero_()
        lin.zero_()
        for d, (joint, sub, typ) in enumerate(
            zip(self._contact_dof_joint_host, self._contact_dof_sub_host, self._contact_dof_type_host)
        ):
            axis = self._xaxis[:, joint]
            pivot = self._xanchor[:, joint]
            if typ == self.JOINT_HINGE:
                rot[:, d] = axis
                lin[:, d] = torch.cross(pivot, axis, dim=-1)
            elif typ == self.JOINT_SLIDE:
                lin[:, d] = axis
            elif typ in (self.JOINT_BALL, self.JOINT_FREE):
                component = sub if sub < 3 else sub - 3
                basis = self._basis_vectors[component].expand(self.num_envs, 3)
                if typ == self.JOINT_FREE and sub < 3:
                    lin[:, d] = basis
                else:
                    rot[:, d] = basis
                    lin[:, d] = torch.cross(pivot, basis, dim=-1)
            elif typ == self.JOINT_UNIVERSAL:
                rot[:, d] = self._univ_axis0[:, joint] if sub == 0 else self._univ_axis1[:, joint]
                lin[:, d] = torch.cross(pivot, rot[:, d], dim=-1)
        return rot, lin

    def _contact_jacobians_for_axes(self, axes: Any, *, motion=None):
        """Build one or more local row Jacobians with static batched gathers.

        ``axes`` has shape ``(B, axis_count, local_slot, 3)``.  The point
        velocity calculation is shared by normal/x/y rows; only the final
        three-vector contraction differs.  This keeps the fixed row order for
        PGS while removing the per-axis/per-slot Python construction loop.
        """
        import torch

        if motion is None:
            motion = self._contact_dof_motion_vectors()
        rot, lin = motion
        batch = self.num_envs
        slots = self._contact_slots
        width = max(1, self.n_dof)
        point = self._contact_point
        jac = self._contact_jacobians[:, : int(axes.shape[1]), :, :width]
        jac.zero_()
        if self._contact_pair_slots.numel() == 0:
            return jac
        pair_slots = self._contact_pair_slots
        pair_dofs = self._contact_pair_dofs
        pair_rot = rot.index_select(1, pair_dofs)
        pair_lin = lin.index_select(1, pair_dofs)
        pair_point = point.index_select(1, pair_slots)
        pair_velocity = pair_lin + torch.cross(pair_rot, pair_point, dim=-1)
        projected = pair_velocity[:, None, :, :] * axes.index_select(2, pair_slots)
        # Contract the fixed three-vector explicitly to avoid a batch-extent
        # dependent reduction.  Only statically supported (slot, DOF) pairs
        # are evaluated; inactive rows are then zeroed exactly as before.
        values = projected[..., 0] + projected[..., 1] + projected[..., 2]
        values = values * self._contact_active.index_select(1, pair_slots)[:, None, :]
        for axis_id in range(int(axes.shape[1])):
            jac[:, axis_id, pair_slots, pair_dofs] = values[:, axis_id]
        return jac

    def _joint_frames(self):
        axis_parent = self._v("jnt_axis_parent")
        root_rot = self._root_rot_batched.expand(self.num_envs, 3, 3)
        for j, p, c, _, _, _, _ in self._compiled_joint_routes:
            cp = self._body_xpos[:, c]
            child_rot = self._body_xmat[:, c]
            self._xanchor[:, j] = cp + torch_bmm_vec(child_rot, self._v("jnt_anchor_child")[j])
            if p >= 0:
                parent_rot = self._body_xmat[:, p]
                self._xaxis[:, j] = torch_bmm_vec(parent_rot, axis_parent[j])
                self._univ_axis0[:, j] = parent_rot[:, :, 0]
                self._univ_axis1[:, j] = parent_rot[:, :, 1]
            else:
                self._xaxis[:, j] = torch_bmm_vec(root_rot, axis_parent[j])
                self._univ_axis0[:, j] = root_rot[:, :, 0]
                self._univ_axis1[:, j] = root_rot[:, :, 1]

    def _refresh_kinematics(self):
        import torch
        with torch.no_grad():
            if self.kinematics_backend == "taichi":
                self._refresh_kinematics_taichi()
                self._kinematics_valid = True
                return
            root_quat = self._root_quat_batched.expand(self.num_envs, 4)
            root_rot = self._root_rot_batched.expand(self.num_envs, 3, 3)
            for body, parent_id, joints, free in self._compiled_body_routes:
                if free:
                    qp = joints[0][2]
                    pos = self._qpos[:, qp:qp + 3]
                    quat = _quat_normalize(self._qpos[:, qp + 3:qp + 7])
                else:
                    pos = self._body_local_pos_batched[:, body].expand(self.num_envs, 3)
                    quat = self._body_local_quat_batched[:, body].expand(self.num_envs, 4)
                    rest_pos = pos
                    rest_rot = self._body_local_rot_batched[:, body].expand(self.num_envs, 3, 3)
                    for j, typ, qa, _, _ in joints:
                        if typ == self.JOINT_HINGE:
                            quat = _quat_mul(quat, _axis_angle(self._v("jnt_axis_child")[j].expand(self.num_envs, 3), self._qpos[:, qa]))
                            anchor_parent = rest_pos + torch_bmm_vec(rest_rot, self._v("jnt_anchor_child")[j])
                            pos = anchor_parent - torch_bmm_vec(_quat_to_matrix(quat), self._v("jnt_anchor_child")[j])
                        elif typ == self.JOINT_SLIDE:
                            pos = pos + self._v("jnt_axis_parent")[j] * self._qpos[:, qa, None]
                        elif typ == self.JOINT_BALL:
                            quat = _quat_mul(quat, _quat_normalize(self._qpos[:, qa:qa + 4]))
                            anchor_parent = rest_pos + torch_bmm_vec(rest_rot, self._v("jnt_anchor_child")[j])
                            pos = anchor_parent - torch_bmm_vec(_quat_to_matrix(quat), self._v("jnt_anchor_child")[j])
                        elif typ == self.JOINT_UNIVERSAL:
                            qx = _axis_angle(self._basis_vectors[0].expand(self.num_envs, 3), self._qpos[:, qa])
                            qy = _axis_angle(self._basis_vectors[1].expand(self.num_envs, 3), self._qpos[:, qa + 1])
                            quat = _quat_mul(quat, _quat_mul(qx, qy))
                            anchor_parent = rest_pos + torch_bmm_vec(rest_rot, self._v("jnt_anchor_child")[j])
                            pos = anchor_parent - torch_bmm_vec(_quat_to_matrix(quat), self._v("jnt_anchor_child")[j])
                p = parent_id
                if p >= 0:
                    pquat = self._body_xquat[:, p]
                    pos = self._body_xpos[:, p] + torch_bmm_vec(self._body_xmat[:, p], pos)
                    quat = _quat_normalize(_quat_mul(pquat, quat))
                else:
                    root_pos = self._v("root_pos").expand(self.num_envs, 3)
                    if not free:
                        pos = root_pos + torch_bmm_vec(root_rot, pos)
                        quat = _quat_normalize(_quat_mul(root_quat, quat))
                self._body_xpos[:, body] = pos
                self._body_xquat[:, body] = quat
                self._body_xmat[:, body] = _quat_to_matrix(quat)

            # Tree velocities are derived from the same fixed local topology.
            for body, parent_id, joints, free in self._compiled_body_routes:
                if free:
                    d = joints[0][3]
                    self._body_linear_vel[:, body] = self._qvel[:, d:d + 3]
                    self._body_angular_vel[:, body] = self._qvel[:, d + 3:d + 6]
                    continue
                p = parent_id
                if p >= 0:
                    pp = self._body_xpos[:, p]
                    pl = self._body_linear_vel[:, p]; pa = self._body_angular_vel[:, p]
                    pos = self._body_xpos[:, body]
                    linear = pl + torch.cross(pa, pos - pp, dim=-1)
                    angular = pa.clone()
                else:
                    linear = torch.zeros((self.num_envs, 3), device=self.device)
                    angular = torch.zeros_like(linear)
                    pp = self._v("root_pos").expand(self.num_envs, 3)
                parent_rot = root_rot if p < 0 else self._body_xmat[:, p]
                body_rot = self._body_xmat[:, body]
                for j, typ, _, d, _ in joints:
                    if typ == self.JOINT_HINGE:
                        axis = torch_bmm_vec(parent_rot, self._v("jnt_axis_parent")[j])
                        rel = self._qvel[:, d, None] * axis
                        pivot = self._body_xpos[:, body] + torch_bmm_vec(body_rot, self._v("jnt_anchor_child")[j])
                        linear = linear + torch.cross(rel, self._body_xpos[:, body] - pivot, dim=-1)
                        angular = angular + rel
                    elif typ == self.JOINT_SLIDE:
                        axis = torch_bmm_vec(parent_rot, self._v("jnt_axis_parent")[j])
                        linear = linear + self._qvel[:, d, None] * axis
                    elif typ == self.JOINT_BALL:
                        rel = self._qvel[:, d:d + 3]
                        pivot = self._body_xpos[:, body] + torch_bmm_vec(body_rot, self._v("jnt_anchor_child")[j])
                        linear = linear + torch.cross(rel, self._body_xpos[:, body] - pivot, dim=-1)
                        angular = angular + rel
                    elif typ == self.JOINT_UNIVERSAL:
                        axis0 = parent_rot[:, :, 0]; axis1 = parent_rot[:, :, 1]
                        rel = self._qvel[:, d, None] * axis0 + self._qvel[:, d + 1, None] * axis1
                        pivot = self._body_xpos[:, body] + torch_bmm_vec(body_rot, self._v("jnt_anchor_child")[j])
                        linear = linear + torch.cross(rel, self._body_xpos[:, body] - pivot, dim=-1)
                        angular = angular + rel
                self._body_linear_vel[:, body] = linear
                self._body_angular_vel[:, body] = angular

            if self.n_geoms:
                geom_body_pos = self._body_xpos.index_select(1, self._compiled_geom_body_indices)
                geom_body_rot = self._body_xmat.index_select(1, self._compiled_geom_body_indices)
                geom_local_pos = self._geom_local_pos_batched
                geom_local_quat = self._geom_local_quat_batched
                self._geom_xpos.copy_(
                    geom_body_pos
                    + torch.matmul(geom_body_rot, geom_local_pos.unsqueeze(-1)).squeeze(-1)
                )
                geom_quat = _quat_normalize(_quat_mul(
                    self._body_xquat.index_select(1, self._compiled_geom_body_indices),
                    geom_local_quat,
                ))
                self._geom_xquat.copy_(geom_quat)
                # ``geom_quat`` remains the public orientation field.  The
                # contact path consumes the equivalent world rotation matrix;
                # compose it from cached immutable local rotations to avoid
                # re-materializing the same quaternion-to-matrix graph.
                self._geom_xmat.copy_(torch.matmul(geom_body_rot, self._geom_local_rot_batched))
            if self.n_sites:
                site_body_pos = self._body_xpos.index_select(1, self._compiled_site_body_indices)
                site_body_rot = self._body_xmat.index_select(1, self._compiled_site_body_indices)
                site_local_pos = self._site_local_pos_batched
                site_local_quat = self._site_local_quat_batched
                self._site_xpos.copy_(
                    site_body_pos
                    + torch.matmul(site_body_rot, site_local_pos.unsqueeze(-1)).squeeze(-1)
                )
                self._site_xquat.copy_(_quat_normalize(_quat_mul(
                    self._body_xquat.index_select(1, self._compiled_site_body_indices),
                    site_local_quat,
                )))
            self._joint_frames()
            self._kinematics_valid = True

    def _refresh_kinematics_taichi(self):
        """Run the optional fixed-topology Taichi FK/geom backend."""

        if self._taichi_fk is None:
            raise RuntimeError("Taichi FK backend was not initialized")
        views = self._ensure_taichi_external_views()
        profile = self._profile_collector
        if profile is not None:
            # This is an envelope for the external-ndarray call boundary. It
            # intentionally overlaps the FK span; the Stage A report marks
            # it as non-additive and uses pointer stability to detect copies.
            profile.begin("runtime_handoff")
        try:
            self._taichi_fk.refresh_pose(
                views.get("qpos", self._qpos),
                views.get("body_xpos", self._body_xpos),
                views.get("body_xquat", self._body_xquat),
                views.get("body_xmat", self._body_xmat),
                views.get("geom_xpos", self._geom_xpos),
                views.get("geom_xquat", self._geom_xquat),
                views.get("geom_xmat", self._geom_xmat),
                views.get("site_xpos", self._site_xpos),
                views.get("site_xquat", self._site_xquat),
                views.get("xanchor", self._xanchor),
                views.get("xaxis", self._xaxis),
                views.get("univ_axis0", self._univ_axis0),
                views.get("univ_axis1", self._univ_axis1),
            )
            self._taichi_fk.refresh_velocity(
                views.get("qvel", self._qvel),
                views.get("body_xpos", self._body_xpos),
                views.get("body_xmat", self._body_xmat),
                views.get("body_linear_vel", self._body_linear_vel),
                views.get("body_angular_vel", self._body_angular_vel),
            )
        finally:
            if profile is not None:
                profile.end("runtime_handoff")

    def _refresh_kinematics_taichi_selected(
        self,
        selected,
        selected_count: int,
        *,
        selected_slots: np.ndarray | None = None,
        force_full: bool = False,
    ):
        """Refresh FK/geom/velocity caches only for reset worlds.

        Normal ticks keep the existing full-batch kernels.  This reset-only
        route avoids launching Taichi FK over all worlds when autoreset has a
        sparse mask, while preserving the fixed full-batch Torch storage.
        """

        if self._taichi_fk is None:
            raise RuntimeError("Taichi FK backend was not initialized")
        import torch

        selected_count = int(selected_count)
        if selected_count == 0:
            return
        views = self._ensure_taichi_external_views()
        # A large reset already pays for almost the whole FK.  Reuse the
        # established full-batch kernels in that case; compact selection is
        # reserved for sparse autoresets where it can skip whole worlds.
        if force_full or selected_count * 2 >= self.num_envs:
            if self.device.type == "cuda":
                self._cuda_graph_synchronize_torch_stream()
            try:
                self._refresh_kinematics_taichi()
            finally:
                self._cuda_graph_synchronize_taichi_runtime()
            return
        if selected_slots is not None:
            slot_ids = torch.tensor(
                selected_slots,
                dtype=self._taichi_reset_ids.dtype,
                device=self._taichi_reset_ids.device,
            )
            self._taichi_reset_ids[:selected_count].copy_(slot_ids)
        else:
            torch.cumsum(
                selected,
                dim=0,
                dtype=torch.int32,
                out=self._taichi_reset_ranks,
            )
            self._taichi_reset_ranks.sub_(1)
            self._taichi_reset_destinations.copy_(self._taichi_reset_ranks)
            torch.logical_not(selected, out=self._taichi_reset_not_selected)
            self._taichi_reset_destinations.masked_fill_(
                self._taichi_reset_not_selected,
                self.num_envs - 1,
            )
            self._taichi_reset_ids.scatter_(
                0,
                self._taichi_reset_destinations,
                self._taichi_world_ids,
            )
        if self.device.type == "cuda":
            self._cuda_graph_synchronize_torch_stream()
        try:
            self._taichi_fk.refresh_pose_selected(
                views.get("reset_ids", self._taichi_reset_ids),
                selected_count,
                views.get("qpos", self._qpos),
                views.get("body_xpos", self._body_xpos),
                views.get("body_xquat", self._body_xquat),
                views.get("body_xmat", self._body_xmat),
                views.get("geom_xpos", self._geom_xpos),
                views.get("geom_xquat", self._geom_xquat),
                views.get("geom_xmat", self._geom_xmat),
                views.get("site_xpos", self._site_xpos),
                views.get("site_xquat", self._site_xquat),
                views.get("xanchor", self._xanchor),
                views.get("xaxis", self._xaxis),
                views.get("univ_axis0", self._univ_axis0),
                views.get("univ_axis1", self._univ_axis1),
            )
            self._taichi_fk.refresh_velocity_selected(
                views.get("reset_ids", self._taichi_reset_ids),
                selected_count,
                views.get("qvel", self._qvel),
                views.get("body_xpos", self._body_xpos),
                views.get("body_xmat", self._body_xmat),
                views.get("body_linear_vel", self._body_linear_vel),
                views.get("body_angular_vel", self._body_angular_vel),
            )
        finally:
            # Drain Taichi even when the velocity launch fails after pose has
            # begun writing persistent external storage.
            self._cuda_graph_synchronize_taichi_runtime()

    def _motion(self, joint: int, local: int):
        import torch
        # Joint type is immutable topology; never convert a CUDA scalar to a
        # host int inside a captured or steady-state physics path.
        typ = self._compiled_joint_type_host[joint]; axis = self._xaxis[:, joint]; pivot = self._xanchor[:, joint]
        rot = torch.zeros((self.num_envs, 3), device=self.device); lin = torch.zeros_like(rot)
        if typ == self.JOINT_HINGE:
            rot = axis; lin = torch.cross(pivot, axis, dim=-1)
        elif typ == self.JOINT_SLIDE:
            lin = axis
        elif typ in (self.JOINT_BALL, self.JOINT_FREE):
            component = local if local < 3 else local - 3
            basis = self._basis_vectors[component].expand(self.num_envs, 3)
            if typ == self.JOINT_FREE and local < 3:
                lin = basis
            else:
                rot = basis; lin = torch.cross(pivot, basis, dim=-1)
        elif typ == self.JOINT_UNIVERSAL:
            rot = self._univ_axis0[:, joint] if local == 0 else self._univ_axis1[:, joint]
            lin = torch.cross(pivot, rot, dim=-1)
        return rot, lin

    def _refresh_dynamics(self):
        import torch
        with torch.no_grad():
            profile = self._profile_collector
            if profile is not None:
                profile.begin("dense_inertia_crb")
            try:
                body_quat = _quat_mul(
                    self._body_xquat,
                    self._v("body_iquat").unsqueeze(0).expand(self.num_envs, -1, -1),
                )
                inertia_rot = _quat_to_matrix(body_quat)
                body_inertia = (
                    self._world_body_inertia.unsqueeze(2)
                    if self._world_randomization_enabled
                    else self._v("body_inertia").unsqueeze(0).unsqueeze(2)
                )
                inertia_world = torch.matmul(
                    inertia_rot * body_inertia,
                    inertia_rot.transpose(-1, -2),
                )
                self._body_inertia_world.copy_(inertia_world)

                body_com = self._body_xpos + torch.matmul(
                    self._body_xmat,
                    self._v("body_ipos").unsqueeze(0).unsqueeze(-1),
                ).squeeze(-1)
                body_mass = (
                    self._world_body_mass
                    if self._world_randomization_enabled
                    else self._v("body_mass").unsqueeze(0)
                )
                eye = self._eye3.view(1, 1, 3, 3)
                com_outer = body_com[..., :, None] * body_com[..., None, :]
                crb = inertia_world + body_mass[..., None, None] * (
                    torch.sum(body_com * body_com, dim=-1)[..., None, None] * eye
                    - com_outer
                )
                self._crb_H.copy_(crb)
                self._crb_mcom.copy_(body_mass[..., None] * body_com)
                self._crb_m.copy_(body_mass.expand(self.num_envs, -1))
                for body, p in self._compiled_reverse_bodies:
                    if p >= 0:
                        self._crb_H[:, p] += self._crb_H[:, body]
                        self._crb_mcom[:, p] += self._crb_mcom[:, body]
                        self._crb_m[:, p] += self._crb_m[:, body]
            finally:
                if profile is not None:
                    profile.end("dense_inertia_crb")

            if profile is not None:
                profile.begin("dense_mass_matrix")
            try:
                self._qM.zero_()
                motion = self._contact_dof_motion_vectors() if self.n_dof else None
                if motion is not None:
                    motion_rot, motion_lin = motion
                    for r, (_, jr, _, body, _) in enumerate(self._compiled_dof_routes):
                        rr = motion_rot[:, r]
                        rl = motion_lin[:, r]
                        force_r = torch.bmm(
                            self._crb_H[:, body], rr[..., None]
                        ).squeeze(-1) + torch.cross(
                            self._crb_mcom[:, body], rl, dim=-1
                        )
                        force_l = -torch.cross(
                            self._crb_mcom[:, body], rr, dim=-1
                        ) + self._crb_m[:, body, None] * rl
                        values = torch.sum(
                            motion_rot * force_r[:, None, :], dim=-1
                        ) + torch.sum(
                            motion_lin * force_l[:, None, :], dim=-1
                        )
                        columns = self._support_dof_indices[body]
                        if columns.numel():
                            selected = values.index_select(1, columns)
                            self._qM[:, r, :].index_copy_(1, columns, selected)
                            self._qM[:, :, r].index_copy_(1, columns, selected)
                        self._qM[:, r, r] += self._v("jnt_armature")[jr]
                if self.n_dof:
                    self._qM[:, :self.n_dof, :self.n_dof] += 1.0e-7 * self._eye_dof[:self.n_dof, :self.n_dof]
            finally:
                if profile is not None:
                    profile.end("dense_mass_matrix")

            if profile is not None:
                profile.begin("dense_rne_bias")
            try:
                self._compute_rne_bias(motion=motion, inertia_world=inertia_world)
            finally:
                if profile is not None:
                    profile.end("dense_rne_bias")
            return motion

    def _compute_rne_bias(self, *, motion=None, inertia_world):
        import torch
        gravity = self._v("gravity").expand(self.num_envs, 3)
        self._rne_alin.zero_(); self._rne_aang.zero_(); self._rne_fsp.zero_(); self._rne_tsp.zero_()
        for body, p, joints, _ in self._compiled_body_routes:
            if p < 0:
                alin = -gravity; aang = torch.zeros_like(alin)
            else:
                pa = self._body_angular_vel[:, p]; pp = self._body_xpos[:, p]; pl = self._body_linear_vel[:, p]
                parent_acc = self._rne_alin[:, p]; parent_ang_acc = self._rne_aang[:, p]
                alin = parent_acc.clone(); aang = parent_ang_acc.clone()
                if joints:
                    j, typ, _, d, _ = joints[0]; axis = self._xaxis[:, j]; pivot = self._xanchor[:, j]
                    if typ in (self.JOINT_HINGE, self.JOINT_BALL, self.JOINT_UNIVERSAL):
                        rel = self._body_angular_vel[:, body] - pa
                        aang = aang + torch.cross(pa, rel, dim=-1)
                        pivot_acc = parent_acc + torch.cross(parent_ang_acc, pivot - pp, dim=-1) + torch.cross(pa, torch.cross(pa, pivot - pp, dim=-1), dim=-1)
                        r = self._body_xpos[:, body] - pivot
                        alin = pivot_acc + torch.cross(aang, r, dim=-1) + torch.cross(self._body_angular_vel[:, body], torch.cross(self._body_angular_vel[:, body], r, dim=-1), dim=-1)
                    elif typ == self.JOINT_SLIDE:
                        qd = self._qvel[:, d]
                        delta = self._body_xpos[:, body] - pp
                        alin = parent_acc + torch.cross(parent_ang_acc, delta, dim=-1) + torch.cross(pa, torch.cross(pa, delta, dim=-1), dim=-1) + 2.0 * torch.cross(pa, qd[:, None] * axis, dim=-1)
            self._rne_alin[:, body] = alin; self._rne_aang[:, body] = aang
        self._compute_rne_body_wrenches(inertia_world=inertia_world)
        for body, p in self._compiled_reverse_bodies:
            if p >= 0:
                self._rne_fsp[:, p] += self._rne_fsp[:, body]; self._rne_tsp[:, p] += self._rne_tsp[:, body]
        if motion is None:
            for d, j, sub, b, _ in self._compiled_dof_routes:
                sr, sl = self._motion(j, sub)
                self._qfrc_bias[:, d] = torch.sum(sr * self._rne_tsp[:, b], -1) + torch.sum(sl * self._rne_fsp[:, b], -1)
        elif self.n_dof:
            motion_rot, motion_lin = motion
            body_torque = self._rne_tsp.index_select(1, self._dof_body_indices)
            body_force = self._rne_fsp.index_select(1, self._dof_body_indices)
            self._qfrc_bias[:, :self.n_dof] = (
                torch.sum(motion_rot * body_torque, dim=-1)
                + torch.sum(motion_lin * body_force, dim=-1)
            )

    def _compute_rne_body_wrenches(self, *, inertia_world):
        import torch

        offset = (
            self._body_xmat @ self._v("body_ipos")[None, :, :, None]
        ).squeeze(-1)
        center = self._body_xpos + offset
        omega = self._body_angular_vel
        center_acc = (
            self._rne_alin
            + torch.cross(self._rne_aang, offset, dim=-1)
            + torch.cross(omega, torch.cross(omega, offset, dim=-1), dim=-1)
        )
        body_mass = (
            self._world_body_mass
            if getattr(self, "_world_randomization_enabled", False)
            else self._v("body_mass").unsqueeze(0)
        )
        force = body_mass[..., None] * center_acc
        inertia_omega = (inertia_world @ omega[..., None]).squeeze(-1)
        torque = (
            (inertia_world @ self._rne_aang[..., None]).squeeze(-1)
            + torch.cross(omega, inertia_omega, dim=-1)
            + torch.cross(center, force, dim=-1)
        )
        self._rne_fsp.copy_(force)
        self._rne_tsp.copy_(torque)

    def _clear_contact_workspace(self, mask=None):
        """Clear contact rows for all worlds or for a reset subset."""
        import torch
        if not self.contact_enabled:
            return
        if mask is None:
            self._contact_active.zero_()
            self._contact_body.fill_(-1)
            self._contact_geom.fill_(-1)
            self._contact_point.zero_()
            self._contact_normal.zero_()
            self._contact_distance.fill_(1.0e6)
            self._contact_normal_lambda.zero_()
            self._contact_tangent_lambda.zero_()
            self._contact_count.zero_()
            self._contact_summary_active.zero_()
            self._contact_summary_distance.zero_()
            self._contact_jacobian.zero_()
            self._contact_friction.zero_()
            return
        else:
            selected = mask.to(device=self.device, dtype=torch.bool)
        row = selected[:, None]
        row3 = selected[:, None, None]
        self._contact_active.masked_fill_(row, False)
        self._contact_body.masked_fill_(row, -1)
        self._contact_geom.masked_fill_(row, -1)
        self._contact_point.masked_fill_(row3, 0.0)
        self._contact_normal.masked_fill_(row3, 0.0)
        self._contact_distance.masked_fill_(row, 1.0e6)
        self._contact_normal_lambda.masked_fill_(row, 0.0)
        self._contact_tangent_lambda.masked_fill_(row3, 0.0)
        self._contact_count.masked_fill_(row, 0)
        self._contact_summary_active.masked_fill_(row, False)
        self._contact_summary_distance.masked_fill_(row, 0.0)
        self._contact_jacobian.masked_fill_(row3, 0.0)
        self._contact_friction.masked_fill_(row, 0.0)

    def _contact_support_candidates(self):
        """Generate local ground-plane candidates for analytic template geoms."""
        import torch
        if not self.contact_enabled:
            return
        self._clear_contact_workspace()
        if not self._ground_contact_geom_ids:
            return
        geom_size = self._v("geom_size").index_select(0, self._contact_slot_geom_indices)
        geom_friction = self._v("geom_friction").index_select(0, self._contact_slot_geom_indices)
        if geom_friction.ndim == 2:
            geom_friction = geom_friction[:, 0]
        center = self._geom_xpos.index_select(1, self._contact_slot_geom_indices)
        rot = self._geom_xmat.index_select(1, self._contact_slot_geom_indices)
        self._contact_normal[:, :, 2].fill_(1.0)
        for shape in (0, 1, 2, 3, 4):
            slot_indices = self._contact_shape_slot_indices[shape]
            if slot_indices.numel() == 0:
                continue
            group_center = center.index_select(1, slot_indices)
            group_rot = rot.index_select(1, slot_indices)
            group_size = geom_size.index_select(0, slot_indices)
            candidate_id = self._contact_slot_candidate_ids.index_select(0, slot_indices)
            if shape == 1:  # sphere
                radius = group_size[:, 0]
                point = group_center.clone()
                point[:, :, 0] -= radius[None, :]
                distance = point[:, :, 2] - self._contact_ground_height
            elif shape == 2:  # capsule, local z axis
                axis = group_rot[:, :, :, 2]
                sign = torch.where(candidate_id == 0, 1.0, -1.0).to(dtype=group_center.dtype)
                endpoint = group_center + sign[None, :, None] * group_size[None, :, 1, None] * axis
                point = endpoint.clone()
                point[:, :, 0] -= group_size[None, :, 0]
                distance = endpoint[:, :, 2] - group_size[None, :, 0] - self._contact_ground_height
            elif shape == 3:  # cylinder: lowest rim point at each cap
                axis = group_rot[:, :, :, 2]
                down = torch.zeros_like(axis)
                down[:, :, 2] = -1.0
                in_plane = down - axis * torch.sum(axis * down, dim=-1, keepdim=True)
                norm = torch.linalg.vector_norm(in_plane, dim=-1, keepdim=True)
                rim = torch.where(
                    norm > 1.0e-8,
                    in_plane / torch.clamp(norm, min=1.0e-8) * group_size[None, :, 0, None],
                    torch.zeros_like(in_plane),
                )
                sign = torch.where(candidate_id == 0, 1.0, -1.0).to(dtype=group_center.dtype)
                point = group_center + sign[None, :, None] * group_size[None, :, 1, None] * axis + rim
                distance = point[:, :, 2] - self._contact_ground_height
            elif shape == 0:  # box: all corners, retaining the lower manifold
                signs = torch.stack((
                    torch.where((candidate_id & 1) != 0, 1.0, -1.0),
                    torch.where((candidate_id & 2) != 0, 1.0, -1.0),
                    torch.where((candidate_id & 4) != 0, 1.0, -1.0),
                ), dim=-1).to(dtype=group_center.dtype)
                local = signs[None, :, :] * group_size[None, :, :]
                point = group_center + torch.matmul(group_rot, local.unsqueeze(-1)).squeeze(-1)
                distance = point[:, :, 2] - self._contact_ground_height
            else:  # convex proxy fallback (compiler supplies a radius)
                radius = torch.clamp(group_size[:, 0], min=1.0e-6)
                point = group_center.clone()
                point[:, :, 0] -= radius[None, :]
                distance = point[:, :, 2] - self._contact_ground_height
            active = distance <= self._contact_margin
            body_ids = self._contact_slot_body_indices.index_select(0, slot_indices).expand(self.num_envs, -1)
            geom_ids = self._contact_slot_geom_indices.index_select(0, slot_indices).expand(self.num_envs, -1)
            self._contact_active.index_copy_(1, slot_indices, active)
            self._contact_body.index_copy_(1, slot_indices, torch.where(active, body_ids, torch.full_like(body_ids, -1)))
            self._contact_geom.index_copy_(1, slot_indices, torch.where(active, geom_ids, torch.full_like(geom_ids, -1)))
            self._contact_point.index_copy_(1, slot_indices, point)
            self._contact_distance.index_copy_(1, slot_indices, distance)
            friction = torch.clamp(
                geom_friction.index_select(0, slot_indices), min=0.0
            ).expand(self.num_envs, -1)
            if self._world_randomization_enabled:
                friction = friction * self._world_friction_mu[:, None]
            self._contact_friction.index_copy_(1, slot_indices, friction)
        # Public task diagnostics are body-local summaries, not global row IDs.
        for body in range(self.n_bodies):
            mask = self._contact_active & (self._contact_body == body)
            self._contact_count[:, body] = mask.sum(dim=-1).to(torch.int32)
            self._contact_summary_active[:, body] = self._contact_count[:, body] > 0
            distances = torch.where(mask, self._contact_distance, torch.full_like(self._contact_distance, 1.0e6))
            self._contact_summary_distance[:, body] = distances.min(dim=-1).values

    def _contact_jacobian_for_axis(self, axis: Any):
        """Build a generalized point-velocity Jacobian for one row axis."""
        # `_motion` stores spatial linear motion at the world origin
        # (lin = pivot × axis), so the point Jacobian is `lin + w × p`.
        # Using `p - body_xpos` here would double-count the pivot for free
        # and hinge joints and produces a wrong contact torque.  The static
        # slot gather below preserves that convention without a Python
        # geom/slot/DOF sweep.
        return self._contact_jacobians_for_axes(axis[:, None, :, :])[:, 0]

    def _next_contact_response_backend(self) -> str:
        """Return the fixed next response route without device readback."""

        if getattr(self, "_contact_response_failed_closed", False) or getattr(
            self, "_contact_topology_failed_closed", False
        ):
            return "failed_closed"
        if self._contact_response_backend_selected in {
            _CONTACT_RESPONSE_TOPOLOGY_P1_BACKEND,
            _CONTACT_RESPONSE_TOPOLOGY_P12_BACKEND,
        }:
            return self._contact_response_backend_selected
        if (
            self._contact_response_backend_selected
            != _CONTACT_RESPONSE_TRITON_BACKEND
            or self._contact_response_triton_disabled
            or not self._contact_pgs_fused_qualified
        ):
            return _CONTACT_RESPONSE_TORCH_BACKEND
        return _CONTACT_RESPONSE_TRITON_BACKEND

    def _contact_response_fixed_tensor_pointers(self) -> dict[str, int]:
        """Return diagnostic-only identities for graph-owned response storage."""

        pointers = {
            f"contact.{name}": int(getattr(self, name).data_ptr())
            for name in (
                "_contact_response_factor",
                "_contact_response_factor_info",
                "_contact_mass_response",
                "_contact_mass_diagonal",
                "_contact_pgs_active_slots",
                "_contact_pgs_active_count",
            )
        }
        if self._contact_topology_factor is not None:
            pointers.update(
                {
                    "contact._contact_topology_factor": int(
                        self._contact_topology_factor.data_ptr()
                    ),
                    "contact._contact_topology_root_factor": int(
                        self._contact_topology_root_factor.data_ptr()
                    ),
                    "contact._contact_topology_child_info": int(
                        self._contact_topology_child_info.data_ptr()
                    ),
                    "contact._contact_topology_root_info": int(
                        self._contact_topology_root_info.data_ptr()
                    ),
                }
            )
        return pointers

    def _contact_response_backend_summary(self) -> dict[str, Any]:
        """Expose qualification, layout, and graph-storage provenance."""

        disabled = not self.contact_enabled
        return {
            "contact_response_backend_requested": getattr(
                self, "_contact_response_requested_backend", _CONTACT_RESPONSE_TRITON_BACKEND
            ),
            "contact_response_backend_selected": (
                "disabled_explicitly"
                if disabled
                else self._contact_response_backend_selected
            ),
            "contact_response_backend_effective": (
                "disabled_explicitly"
                if disabled
                else self._contact_response_backend_effective
            ),
            "contact_response_backend_next": (
                "disabled_explicitly"
                if disabled
                else self._next_contact_response_backend()
            ),
            "contact_response_triton_attempted": (
                getattr(self, "_contact_response_triton_attempted", False)
            ),
            "contact_response_triton_qualified": (
                getattr(self, "_contact_response_triton_qualified", False)
            ),
            "contact_response_failed_closed": getattr(
                self, "_contact_response_failed_closed", False
            ),
            "contact_response_fallback_reason": (
                getattr(self, "_contact_response_fallback_reason", None)
            ),
            "contact_response_qualification_source": (
                "disabled_explicitly"
                if disabled
                else "topology_child_schur_qualification"
                if self._contact_response_backend_selected
                in {
                    _CONTACT_RESPONSE_TOPOLOGY_P1_BACKEND,
                    _CONTACT_RESPONSE_TOPOLOGY_P12_BACKEND,
                }
                else "contact_pgs_fused_qualified"
            ),
            "contact_response_rhs_policy": (
                "disabled_explicitly"
                if disabled
                else "runtime_active_count_active_slots_only_v1"
            ),
            "contact_response_inactive_output_policy": (
                "disabled_explicitly"
                if disabled
                else "prezero_fixed_output_v1"
            ),
            "contact_response_fixed_storage_policy": (
                "disabled_explicitly"
                if disabled
                else "constructor_owned_graph_stable_v1"
            ),
            "contact_response_layout": (
                "disabled_explicitly"
                if disabled
                else {
                    "jacobian": "world_axis_slot_dof",
                    "response": "axis_world_dof_slot",
                    "diagonal": "axis_world_slot",
                }
            ),
            "contact_response_block_d": "disabled_explicitly" if disabled else 32,
            "contact_response_num_warps": (
                "disabled_explicitly" if disabled else 1
            ),
            "topology_child_schur": {
                "enabled": getattr(self, "_contact_topology_child_schur_enabled", False),
                "qualified": getattr(self, "_contact_topology_qualified", False),
                "root_factor_6x6": getattr(self, "_contact_root_factor_6x6_enabled", False),
                "capability_reasons": list(
                    getattr(self, "_contact_topology_schur_capability_reasons", ())
                ),
                "failed_closed": getattr(self, "_contact_topology_failed_closed", False),
                "error": getattr(self, "_contact_topology_error", None),
                "factor_layout": (
                    "reverse_child_unit_upper_ldlt_root6_v1"
                    if getattr(self, "_contact_topology_child_schur_enabled", False)
                    else "disabled_explicitly"
                ),
                "response_policy": (
                    "active_slots_only_v1"
                    if getattr(self, "_contact_topology_child_schur_enabled", False)
                    else "disabled_explicitly"
                ),
            },
        }

    def _contact_response_solve_topology_active(
        self,
        *,
        mass,
        jacobian_axes,
        active,
        world_active,
    ) -> bool:
        """Run P1/P12's fixed-topology factor and active-slot response.

        Unlike the historical articulated response pipeline, this branch
        consumes the fixed runtime's active-slot Jacobian/output layout and
        leaves PGS, autoreset and CUDA Graph ownership unchanged.
        """

        import torch

        if not self._contact_topology_child_schur_enabled:
            return False
        if _triton is None:
            raise RuntimeError("fixed-topology contact Schur requires Triton")
        if self._contact_topology_failed_closed:
            raise RuntimeError("fixed-topology contact Schur is failed closed")
        factor = self._contact_topology_factor
        root_factor = self._contact_topology_root_factor
        child_info = self._contact_topology_child_info
        root_info = self._contact_topology_root_info
        if (
            factor is None
            or root_factor is None
            or child_info is None
            or root_info is None
        ):
            raise RuntimeError("fixed-topology contact Schur workspace is missing")

        qualification = not self._contact_topology_qualified
        self._contact_mass_response.zero_()
        self._contact_mass_diagonal.zero_()
        block_s = 1
        while block_s < self._contact_slots:
            block_s *= 2
        try:
            _contact_topology_child_schur_factor_kernel[(self.num_envs,)](
                mass,
                factor,
                child_info,
                DOFS=self.n_dof,
                ROOT_DOFS=6,
                BLOCK_D=32,
                num_warps=1,
            )
            if self._contact_root_factor_6x6_enabled:
                _contact_topology_root_factor_kernel[(self.num_envs,)](
                    factor,
                    root_factor,
                    root_info,
                    DOFS=self.n_dof,
                    ROOT_DOFS=6,
                    BLOCK_ROOT=8,
                    num_warps=1,
                )
            else:
                torch.linalg.cholesky_ex(
                    factor[:, :6, :6],
                    check_errors=False,
                    out=(root_factor, root_info),
                )
            factorization_ok = torch.logical_and(
                child_info == 0,
                root_info == 0,
            ).all()
            if qualification:
                if not bool(factorization_ok.item()):
                    raise RuntimeError("fixed-topology contact Schur factorization failed")
            else:
                torch._assert_async(
                    factorization_ok,
                    "fixed-topology contact Schur factorization failed",
                )
            _ground_contact_active_slot_prepare_kernel[(self.num_envs,)](
                active,
                world_active,
                self._contact_normal_lambda,
                self._contact_tangent_lambda,
                self._contact_friction,
                self._contact_pgs_active_slots,
                self._contact_pgs_active_count,
                SLOTS=self._contact_slots,
                BLOCK_S=block_s,
                num_warps=1,
            )
            _ground_contact_response_topology_active_kernel[(self.num_envs,)](
                factor,
                root_factor,
                jacobian_axes,
                self._contact_pgs_active_slots,
                self._contact_pgs_active_count,
                self._contact_mass_response,
                self._contact_mass_diagonal,
                BATCH=self.num_envs,
                SLOTS=self._contact_slots,
                DOFS=self.n_dof,
                ROOT_DOFS=6,
                BLOCK_D=32,
                num_warps=1,
            )
            if qualification:
                _synchronize_contact_pgs_cuda_stream(self.device)
        except Exception as error:
            self._contact_topology_failed_closed = True
            self._contact_topology_error = _sanitized_contact_pgs_failure(
                "fixed_topology_child_schur", error
            )
            self._contact_response_backend_effective = "failed_closed"
            raise RuntimeError(
                "fixed-topology contact Schur candidate failed closed: "
                f"{self._contact_topology_error}"
            ) from error
        self._contact_topology_qualified = True
        self._contact_response_backend_effective = (
            self._contact_response_backend_selected
        )
        return True

    def _contact_response_solve_triton_active(
        self,
        *,
        mass,
        jacobian_axes,
        active,
        world_active,
    ) -> bool:
        """Attempt the fixed-storage active RHS solve.

        Only the first response qualification may synchronize and switch to
        the torch route.  A qualified launch is the graph/replay contract and
        therefore fails closed instead of making a host-side fallback choice.
        """

        import torch

        route = self._next_contact_response_backend()
        if route == "failed_closed":
            raise RuntimeError("contact response backend is failed closed")
        if route != _CONTACT_RESPONSE_TRITON_BACKEND or _triton is None:
            return False

        qualification = not self._contact_response_triton_qualified
        snapshot = None
        if qualification:
            snapshot = (
                self._contact_normal_lambda.clone(),
                self._contact_tangent_lambda.clone(),
                self._contact_pgs_active_slots.clone(),
                self._contact_pgs_active_count.clone(),
            )
        self._contact_response_triton_attempted = True
        self._contact_mass_response.zero_()
        self._contact_mass_diagonal.zero_()
        block_s = 1
        while block_s < self._contact_slots:
            block_s *= 2
        try:
            torch.linalg.cholesky_ex(
                mass,
                check_errors=False,
                out=(
                    self._contact_response_factor,
                    self._contact_response_factor_info,
                ),
            )
            factorization_ok = torch.all(self._contact_response_factor_info == 0)
            if qualification:
                # Qualification already owns the one allowed stream sync.  Read
                # info on the host here so a bad factor raises normally and the
                # CUDA context remains usable for state restore + torch fallback.
                if not bool(factorization_ok.item()):
                    raise RuntimeError(
                        "contact response Cholesky factorization failed"
                    )
            else:
                # Qualified execution and graph replay cannot make a host-side
                # route decision; a bad factor therefore fails closed on-device.
                torch._assert_async(
                    factorization_ok,
                    "contact response Cholesky factorization failed",
                )
            _ground_contact_active_slot_prepare_kernel[(self.num_envs,)](
                active,
                world_active,
                self._contact_normal_lambda,
                self._contact_tangent_lambda,
                self._contact_friction,
                self._contact_pgs_active_slots,
                self._contact_pgs_active_count,
                SLOTS=self._contact_slots,
                BLOCK_S=block_s,
                num_warps=1,
            )
            _ground_contact_response_active_kernel[(self.num_envs,)](
                self._contact_response_factor,
                jacobian_axes,
                self._contact_pgs_active_slots,
                self._contact_pgs_active_count,
                self._contact_mass_response,
                self._contact_mass_diagonal,
                BATCH=self.num_envs,
                SLOTS=self._contact_slots,
                DOFS=self.n_dof,
                BLOCK_D=32,
                num_warps=1,
            )
            if qualification:
                _synchronize_contact_pgs_cuda_stream(self.device)
        except Exception as error:
            reason = _sanitized_contact_pgs_failure(
                "triton_active_contact_response_launch",
                error,
            )
            self._contact_response_fallback_reason = reason
            if not qualification:
                self._contact_response_failed_closed = True
                self._contact_response_backend_effective = "failed_closed"
                raise
            try:
                (
                    normal_snapshot,
                    tangent_snapshot,
                    active_slots_snapshot,
                    active_count_snapshot,
                ) = snapshot
                self._contact_normal_lambda.copy_(normal_snapshot)
                self._contact_tangent_lambda.copy_(tangent_snapshot)
                self._contact_pgs_active_slots.copy_(active_slots_snapshot)
                self._contact_pgs_active_count.copy_(active_count_snapshot)
            except Exception as restore_error:
                self._contact_response_failed_closed = True
                self._contact_response_backend_effective = "failed_closed"
                self._contact_response_fallback_reason += ";" + (
                    _sanitized_contact_pgs_failure(
                        "triton_active_contact_response_restore",
                        restore_error,
                    )
                )
                raise
            self._contact_response_triton_disabled = True
            self._contact_response_backend_effective = (
                _CONTACT_RESPONSE_TORCH_BACKEND
            )
            return False
        self._contact_response_triton_qualified = True
        self._contact_response_backend_effective = _CONTACT_RESPONSE_TRITON_BACKEND
        return True

    def _qualify_contact_response_before_cuda_graph(self) -> None:
        """Complete response qualification before entering graph capture."""

        if (
            self._contact_response_backend_selected
            in {
                _CONTACT_RESPONSE_TOPOLOGY_P1_BACKEND,
                _CONTACT_RESPONSE_TOPOLOGY_P12_BACKEND,
            }
            and not self._contact_topology_qualified
        ):
            self._prepare_ground_contact_response()
            return
        if (
            self._contact_response_backend_selected
            == _CONTACT_RESPONSE_TRITON_BACKEND
            and self._contact_pgs_fused_qualified
            and not self._contact_response_triton_qualified
            and not self._contact_response_triton_disabled
        ):
            self._prepare_ground_contact_response()

    def _contact_pgs_sweep_triton_fused(
        self,
        *,
        jacobian_axes,
        response_axes,
        diagonal_axes,
        bias,
        active,
        world_active,
        normal_lambda,
        tangent_lambda,
        friction,
    ) -> bool:
        """Fuse normal/x/y ordered sweeps when the optional Triton path is safe."""
        if (
            self.device.type != "cuda"
            or _triton is None
            or self._contact_pgs_fused_disabled
            or self.n_dof == 0
            or self.n_dof > 256
        ):
            return False
        if self._contact_iterations < 1:
            self._contact_pgs_fused_disabled = True
            self._contact_pgs_fallback_reason = (
                "specialization:contact_iterations_must_be_positive"
            )
            self._contact_pgs_backend_effective = (
                "triton_ordered_world_serial_v1"
                if not self._contact_triton_disabled
                else "eager_fused_axis_world_serial_v1"
            )
            return False
        launch_config = _contact_pgs_fused_launch_config(self.n_dof)
        block_d = launch_config["contact_pgs_fused_block_d"]
        block_s = 1
        while block_s < self._contact_slots:
            block_s *= 2
        qualification_snapshot = None
        if not self._contact_pgs_fused_qualified:
            qualification_snapshot = (
                self._qvel[:, :self.n_dof].clone(),
                normal_lambda.clone(),
                tangent_lambda.clone(),
                self._contact_pgs_active_slots.clone(),
                self._contact_pgs_active_count.clone(),
            )
        self._contact_pgs_fused_attempted = True
        failure_stage = "triton_active_slot_prepare_launch"
        try:
            _ground_contact_active_slot_prepare_kernel[(self.num_envs,)](
                active.contiguous(),
                world_active,
                normal_lambda.contiguous(),
                tangent_lambda,
                friction.contiguous(),
                self._contact_pgs_active_slots,
                self._contact_pgs_active_count,
                SLOTS=self._contact_slots,
                BLOCK_S=block_s,
                num_warps=1,
            )
            failure_stage = "triton_fused_launch"
            _ground_contact_pgs_fused_kernel[(self.num_envs,)](
                self._qvel[:, :self.n_dof],
                jacobian_axes.contiguous(),
                response_axes.contiguous(),
                diagonal_axes.contiguous(),
                bias.contiguous(),
                active.contiguous(),
                world_active,
                normal_lambda.contiguous(),
                tangent_lambda,
                friction.contiguous(),
                self._contact_pgs_active_slots,
                self._contact_pgs_active_count,
                BATCH=self.num_envs,
                SLOTS=self._contact_slots,
                DOFS=self.n_dof,
                ITERATIONS=self._contact_iterations,
                BLOCK_D=block_d,
                num_warps=launch_config["contact_pgs_fused_num_warps"],
            )
            if qualification_snapshot is not None:
                _synchronize_contact_pgs_cuda_stream(self.device)
        except Exception as error:
            self._contact_pgs_fused_disabled = True
            self._contact_pgs_fallback_reason = _sanitized_contact_pgs_failure(
                failure_stage,
                error,
            )
            if self._contact_pgs_fused_qualified:
                self._contact_pgs_failed_closed = True
                self._contact_pgs_backend_effective = "failed_closed"
                raise
            try:
                (
                    qvel_snapshot,
                    normal_snapshot,
                    tangent_snapshot,
                    active_slots_snapshot,
                    active_count_snapshot,
                ) = qualification_snapshot
                self._qvel[:, :self.n_dof].copy_(qvel_snapshot)
                normal_lambda.copy_(normal_snapshot)
                tangent_lambda.copy_(tangent_snapshot)
                self._contact_pgs_active_slots.copy_(active_slots_snapshot)
                self._contact_pgs_active_count.copy_(active_count_snapshot)
            except Exception as restore_error:
                self._contact_pgs_failed_closed = True
                self._contact_pgs_backend_effective = "failed_closed"
                self._contact_pgs_fallback_reason += ";" + (
                    _sanitized_contact_pgs_failure(
                        "triton_fused_restore",
                        restore_error,
                    )
                )
                raise
            # Only an unqualified specialization can restore its complete
            # write set and safely continue into the semantic fallback.
            self._contact_pgs_backend_effective = (
                "triton_ordered_world_serial_v1"
                if not self._contact_triton_disabled
                else "eager_fused_axis_world_serial_v1"
            )
            return False
        self._contact_pgs_backend_effective = (
            "triton_fused_axis_world_serial_v2"
        )
        self._contact_pgs_fused_qualified = True
        return True

    def _next_contact_pgs_backend(self) -> str:
        """Return the next route without overwriting last actual execution."""

        if self._contact_pgs_failed_closed:
            effective = "failed_closed"
        elif not self.contact_enabled:
            effective = "disabled_explicitly"
        elif self.n_dof == 0:
            effective = "no_op_no_dofs"
        elif self.device.type != "cuda":
            effective = "eager_ordered_slot_sweep_v1"
        elif _triton is None or self._contact_triton_disabled:
            effective = "eager_fused_axis_world_serial_v1"
        elif self.n_dof > 256:
            effective = "eager_ordered_slot_sweep_v1"
        elif self._contact_pgs_fused_disabled:
            effective = "triton_ordered_world_serial_v1"
        else:
            effective = "triton_fused_axis_world_serial_v2"
        return effective

    def _contact_pgs_backend_summary(self) -> dict[str, Any]:
        """Report last actual and next-route PGS state without mutation."""

        effective = self._contact_pgs_backend_effective
        return {
            "contact_pgs_backend_selected": self._contact_pgs_backend_selected,
            "contact_pgs_backend_effective": effective,
            "contact_pgs_backend_next": self._next_contact_pgs_backend(),
            "contact_pgs_fused_attempted": self._contact_pgs_fused_attempted,
            "contact_pgs_fused_qualified": self._contact_pgs_fused_qualified,
            "contact_pgs_inactive_row_memory_policy": (
                "masked_jacobian_response_v1"
            ),
            "contact_pgs_active_slot_policy": (
                "world_local_ascending_compaction_v1"
            ),
            "contact_pgs_active_slot_workspace_bytes": (
                4 * self.num_envs * self._contact_slots
                + 4 * self.num_envs
            ),
            **_contact_pgs_fused_launch_config(self.n_dof),
            "contact_pgs_failed_closed": self._contact_pgs_failed_closed,
            "contact_pgs_fallback_reason": self._contact_pgs_fallback_reason,
            "contact_pgs_bootstrap": _contact_pgs_module_provenance(),
            "contact_pgs_triton_version": _CONTACT_PGS_BOOTSTRAP.get(
                "triton_version"
            ),
            "contact_pgs_sweep": effective,
            "contact_pgs_row_order": (
                "ascending_local_slot_gauss_seidel"
                if self.contact_enabled and self.n_dof > 0
                else "disabled_no_dofs"
                if self.contact_enabled
                else "disabled_explicitly"
            ),
            "contact_pgs_iterations": (
                int(self._contact_iterations)
                if self.contact_enabled and self.n_dof > 0
                else 0
            ),
        }

    def _contact_pgs_sweep_eager_fused(
        self,
        *,
        jacobian_axes,
        response_axes,
        diagonal_axes,
        bias,
        active,
        world_active,
        normal_lambda,
        tangent_lambda,
        friction,
    ) -> None:
        """Ordered eager fallback with one persistent contact-dtype qvel view."""
        import torch

        self._contact_pgs_backend_effective = "eager_fused_axis_world_serial_v1"
        contact_dtype = self._contact_mass_response.dtype
        # Keep the public qvel update boundary in f32, matching the original
        # ordered eager path and the Triton kernel.  Reuse one contact-dtype
        # read workspace so the row loop does not allocate a new cast tensor.
        qvel = self._qvel[:, :self.n_dof]
        qvel_contact = qvel.to(dtype=contact_dtype)
        active_rows = active & world_active[:, None]
        for axis in range(3):
            jacobian = jacobian_axes[axis]
            response = response_axes[axis]
            diagonal = diagonal_axes[axis]
            for _ in range(self._contact_iterations):
                for slot in range(self._contact_slots):
                    mask = active_rows[:, slot]
                    row_velocity = torch.sum(
                        jacobian[:, slot, :] * qvel_contact,
                        dim=-1,
                    )
                    if axis == 0:
                        old = normal_lambda[:, slot]
                        delta = torch.where(
                            mask,
                            (bias[:, slot] - row_velocity) / diagonal[:, slot],
                            torch.zeros_like(row_velocity),
                        )
                        updated = torch.clamp(
                            old.to(dtype=contact_dtype) + delta,
                            min=0.0,
                        )
                    else:
                        old = tangent_lambda[:, slot, axis - 1]
                        delta = torch.where(
                            mask,
                            -row_velocity / diagonal[:, slot],
                            torch.zeros_like(row_velocity),
                        )
                        cap = (
                            friction[:, slot]
                            * normal_lambda[:, slot]
                        ).to(dtype=contact_dtype)
                        updated = torch.clamp(
                            old.to(dtype=contact_dtype) + delta,
                            min=-cap,
                            max=cap,
                        )
                    delta = updated - old.to(dtype=contact_dtype)
                    if axis == 0:
                        normal_lambda[:, slot] = updated.to(
                            dtype=normal_lambda.dtype
                        )
                    else:
                        tangent_lambda[:, slot, axis - 1] = updated.to(
                            dtype=tangent_lambda.dtype
                        )
                    qvel.add_(
                        (response[:, :, slot] * delta[:, None]).to(
                            dtype=qvel.dtype
                        )
                    )
                    qvel_contact.copy_(qvel)

    def _contact_pgs_sweep_triton(
        self,
        *,
        jacobian,
        response,
        diagonal,
        bias,
        active,
        world_active,
        lambdas,
        friction,
        normal_lambda,
        mode: int,
    ) -> bool:
        """Run a generic ordered CUDA sweep when optional Triton is usable."""
        if (
            self.device.type != "cuda"
            or _triton is None
            or self._contact_triton_disabled
        ):
            return False
        block_d = 1
        while block_d < self.n_dof:
            block_d *= 2
        if block_d > 256:
            return False
        qvel_snapshot = self._qvel[:, :self.n_dof].clone()
        lambda_snapshot = lambdas.clone()
        try:
            _ground_contact_pgs_kernel[(self.num_envs,)](
                self._qvel[:, :self.n_dof],
                jacobian.contiguous(),
                response.contiguous(),
                diagonal.contiguous(),
                bias.contiguous(),
                active,
                world_active,
                lambdas,
                friction,
                normal_lambda,
                SLOTS=self._contact_slots,
                DOFS=self.n_dof,
                ITERATIONS=self._contact_iterations,
                MODE=int(mode),
                BLOCK_D=block_d,
                LAMBDA_BATCH_STRIDE=int(lambdas.stride(0)),
                LAMBDA_SLOT_STRIDE=int(lambdas.stride(1)),
                num_warps=4,
            )
            _synchronize_contact_pgs_cuda_stream(self.device)
        except Exception as error:
            self._contact_triton_disabled = True
            reason = _sanitized_contact_pgs_failure(
                "triton_generic_launch",
                error,
            )
            if self._contact_pgs_fallback_reason:
                reason = f"{self._contact_pgs_fallback_reason};{reason}"
            self._contact_pgs_fallback_reason = reason
            try:
                self._qvel[:, :self.n_dof].copy_(qvel_snapshot)
                lambdas.copy_(lambda_snapshot)
            except Exception as restore_error:
                self._contact_pgs_failed_closed = True
                self._contact_pgs_backend_effective = "failed_closed"
                self._contact_pgs_fallback_reason += ";" + (
                    _sanitized_contact_pgs_failure(
                        "triton_generic_restore",
                        restore_error,
                    )
                )
                raise
            self._contact_pgs_backend_effective = (
                "eager_ordered_slot_sweep_v1"
            )
            return False
        self._contact_pgs_backend_effective = "triton_ordered_world_serial_v1"
        return True

    def _prepare_ground_contact_response(self, *, motion=None):
        """Prepare fixed contact rows before the replayable PGS segment."""

        import torch

        if not self.contact_enabled or self.n_dof == 0:
            return
        profile = self._profile_collector
        if profile is not None:
            profile.begin("contact_candidate")
        try:
            self._contact_support_candidates()
        finally:
            if profile is not None:
                profile.end("contact_candidate")
        active_tensor = getattr(self, "_contact_active", None)
        world_active = getattr(self, "_contact_world_active", None)
        if world_active is None or active_tensor is None:
            world_active = torch.ones(
                (self.num_envs,),
                dtype=torch.bool,
                device=getattr(active_tensor, "device", self._contact_mass_response.device),
            )
        else:
            world_active.copy_(active_tensor.any(dim=1))
        if profile is not None:
            profile.begin("contact_mass_response")
        try:
            if profile is not None:
                profile.begin("contact_motion_jacobian")
            try:
                normal = self._contact_normal
                axes = self._contact_axes
                axes[:, 0].copy_(normal)
                axes[:, 1].copy_(self._basis_vectors[0].expand(self.num_envs, self._contact_slots, 3))
                axes[:, 2].copy_(self._basis_vectors[1].expand(self.num_envs, self._contact_slots, 3))
                contact_jacobians = self._contact_jacobians_for_axes(
                    axes,
                    motion=motion,
                )
                self._contact_jacobian.copy_(contact_jacobians[:, 0])
            finally:
                if profile is not None:
                    profile.end("contact_motion_jacobian")

            if profile is not None:
                profile.begin("contact_precision_rhs_pack")
            try:
                M = self._qM[:, :self.n_dof, :self.n_dof]
                # Eager mode keeps the established shared factorization.  Complete
                # contact Graph scopes switch only the factorization/solve
                # implementation to the capture-safe equivalent below.
                use_capture_safe_factorization = (
                    self._cuda_graph_enabled
                    and self._cuda_graph_capture_scope()
                    in {"contact_full_v4", "contact_core_full_v5"}
                )
                contact_dtype = self._contact_mass_response.dtype
                M_contact = M.to(dtype=contact_dtype)
                contact_jacobians_contact = contact_jacobians.to(dtype=contact_dtype)
            finally:
                if profile is not None:
                    profile.end("contact_precision_rhs_pack")

            used_active_response = False
            selected_response_backend = getattr(
                self,
                "_contact_response_backend_selected",
                _CONTACT_RESPONSE_TORCH_BACKEND,
            )
            if selected_response_backend in {
                _CONTACT_RESPONSE_TOPOLOGY_P1_BACKEND,
                _CONTACT_RESPONSE_TOPOLOGY_P12_BACKEND,
            }:
                used_active_response = self._contact_response_solve_topology_active(
                    mass=M_contact,
                    jacobian_axes=contact_jacobians_contact,
                    active=self._contact_active,
                    world_active=world_active,
                )
            elif selected_response_backend == _CONTACT_RESPONSE_TRITON_BACKEND:
                used_active_response = self._contact_response_solve_triton_active(
                    mass=M_contact,
                    jacobian_axes=contact_jacobians_contact,
                    active=self._contact_active,
                    world_active=world_active,
                )

            if not used_active_response:
                self._contact_response_backend_effective = (
                    _CONTACT_RESPONSE_TORCH_BACKEND
                )
                response_rhs = contact_jacobians_contact.permute(
                    0, 3, 1, 2
                ).reshape(
                    self.num_envs,
                    self.n_dof,
                    3 * self._contact_slots,
                )

                if use_capture_safe_factorization:
                    solved_rhs = _capture_safe_cholesky_solve(
                        M_contact, response_rhs
                    )
                else:
                    if profile is not None:
                        profile.begin("contact_factorization")
                    try:
                        contact_factor = torch.linalg.cholesky(M_contact)
                    finally:
                        if profile is not None:
                            profile.end("contact_factorization")

                    if profile is not None:
                        profile.begin("contact_linear_solve")
                    try:
                        solved_rhs = torch.cholesky_solve(
                            response_rhs, contact_factor
                        )
                    finally:
                        if profile is not None:
                            profile.end("contact_linear_solve")

            if profile is not None:
                profile.begin("contact_response_finalize")
            try:
                if not used_active_response:
                    response_batched = solved_rhs.reshape(
                        self.num_envs,
                        self.n_dof,
                        3,
                        self._contact_slots,
                    )
                    self._contact_mass_response.copy_(
                        response_batched.permute(2, 0, 1, 3)
                    )
                    diagonal_batched = torch.sum(
                        contact_jacobians_contact
                        * response_batched.permute(0, 2, 3, 1),
                        dim=-1,
                    ).clamp_min(1.0e-8)
                    self._contact_mass_diagonal.copy_(
                        diagonal_batched.permute(1, 0, 2)
                    )
                dt = max(self.physics_dt, 1.0e-9)
                penetration = torch.clamp(-self._contact_distance, min=0.0)
                bias = torch.clamp(
                    self._contact_bias_relaxation
                    * (penetration - self._contact_margin)
                    / dt,
                    min=0.0,
                    max=self._contact_bias_max_velocity,
                )
                self._contact_bias.copy_(bias.to(dtype=contact_dtype))
                self._contact_jacobian_axes.copy_(contact_jacobians_contact.permute(1, 0, 2, 3))
                self._contact_normal_lambda.zero_()
            finally:
                if profile is not None:
                    profile.end("contact_response_finalize")
        finally:
            if profile is not None:
                profile.end("contact_mass_response")

    def _run_ground_contact_pgs(self):
        """Run the fixed row-order PGS tail using prepared persistent fields."""

        import torch

        self._contact_pgs_backend_effective = self._next_contact_pgs_backend()
        if not self.contact_enabled or self.n_dof == 0:
            return
        if self._contact_pgs_failed_closed:
            raise RuntimeError("contact PGS backend is failed closed")
        contact_dtype = self._contact_mass_response.dtype
        jacobian_axes = self._contact_jacobian_axes
        response_axes = self._contact_mass_response
        diagonal_axes = self._contact_mass_diagonal
        bias = self._contact_bias
        if self.device.type == "cuda":
            fused_swept = self._contact_pgs_sweep_triton_fused(
                jacobian_axes=jacobian_axes,
                response_axes=response_axes,
                diagonal_axes=diagonal_axes,
                bias=bias,
                active=self._contact_active,
                world_active=self._contact_world_active,
                normal_lambda=self._contact_normal_lambda,
                tangent_lambda=self._contact_tangent_lambda,
                friction=self._contact_friction,
            )
            if fused_swept:
                return
            if _triton is None or self._contact_triton_disabled:
                self._contact_pgs_sweep_eager_fused(
                    jacobian_axes=jacobian_axes,
                    response_axes=response_axes,
                    diagonal_axes=diagonal_axes,
                    bias=bias,
                    active=self._contact_active,
                    world_active=self._contact_world_active,
                    normal_lambda=self._contact_normal_lambda,
                    tangent_lambda=self._contact_tangent_lambda,
                    friction=self._contact_friction,
                )
                return
        Jn_contact = jacobian_axes[0]
        MinvJt = response_axes[0]
        diag = diagonal_axes[0]
        active_rows = self._contact_active
        normal_swept = self._contact_pgs_sweep_triton(
            jacobian=Jn_contact,
            response=MinvJt,
            diagonal=diag,
            bias=bias,
            active=self._contact_active,
            world_active=self._contact_world_active,
            lambdas=self._contact_normal_lambda,
            friction=self._contact_friction,
            normal_lambda=self._contact_normal_lambda,
            mode=0,
        )
        if not normal_swept:
            for _ in range(self._contact_iterations):
                for slot in range(self._contact_slots):
                    mask = active_rows[:, slot]
                    row_v = torch.sum(
                        Jn_contact[:, slot, :] * self._qvel[:, :self.n_dof].to(dtype=contact_dtype),
                        dim=-1,
                    )
                    delta = torch.where(
                        mask,
                        (bias[:, slot] - row_v) / diag[:, slot],
                        torch.zeros_like(row_v),
                    )
                    old = self._contact_normal_lambda[:, slot]
                    new = torch.clamp(old.to(dtype=contact_dtype) + delta, min=0.0)
                    delta = new - old.to(dtype=contact_dtype)
                    self._contact_normal_lambda[:, slot] = new.to(dtype=self._contact_normal_lambda.dtype)
                    self._qvel[:, :self.n_dof] += (MinvJt[:, :, slot] * delta[:, None]).to(dtype=self._qvel.dtype)
        for tangent_id in range(2):
            Jt_contact = jacobian_axes[tangent_id + 1]
            MinvJtt = response_axes[tangent_id + 1]
            diag_t = diagonal_axes[tangent_id + 1]
            tangent_swept = self._contact_pgs_sweep_triton(
                jacobian=Jt_contact,
                response=MinvJtt,
                diagonal=diag_t,
                bias=torch.zeros_like(diag_t),
                active=self._contact_active,
                world_active=self._contact_world_active,
                lambdas=self._contact_tangent_lambda[:, :, tangent_id],
                friction=self._contact_friction,
                normal_lambda=self._contact_normal_lambda,
                mode=1,
            )
            if not tangent_swept:
                for _ in range(self._contact_iterations):
                    for slot in range(self._contact_slots):
                        mask = active_rows[:, slot]
                        row_v = torch.sum(
                            Jt_contact[:, slot, :] * self._qvel[:, :self.n_dof].to(dtype=contact_dtype),
                            dim=-1,
                        )
                        delta = torch.where(
                            mask,
                            -row_v / diag_t[:, slot],
                            torch.zeros_like(row_v),
                        )
                        old = self._contact_tangent_lambda[:, slot, tangent_id]
                        cap = (
                            self._contact_friction[:, slot]
                            * self._contact_normal_lambda[:, slot]
                        ).to(dtype=contact_dtype)
                        new = torch.clamp(old.to(dtype=contact_dtype) + delta, min=-cap, max=cap)
                        delta = new - old.to(dtype=contact_dtype)
                        self._contact_tangent_lambda[:, slot, tangent_id] = new.to(dtype=self._contact_tangent_lambda.dtype)
                        self._qvel[:, :self.n_dof] += (MinvJtt[:, :, slot] * delta[:, None]).to(dtype=self._qvel.dtype)

    def _solve_ground_contacts(self, *, motion=None):
        """Prepare and solve fixed local ground rows in eager mode."""

        if not self.contact_enabled or self.n_dof == 0:
            return
        profile = self._profile_collector
        self._prepare_ground_contact_response(motion=motion)
        if profile is not None:
            profile.begin("row_pgs_response")
            profile.begin("row_pgs")
        try:
            self._run_ground_contact_pgs()
        finally:
            if profile is not None:
                profile.end("row_pgs")
                profile.end("row_pgs_response")

    def _step_one(self):
        import torch
        with torch.no_grad():
            profile = self._profile_collector
            if not self._kinematics_valid:
                if profile is not None:
                    profile.begin("geom_fk")
                    profile.begin("fk_geom_transform")
                try:
                    self._refresh_kinematics()
                finally:
                    if profile is not None:
                        profile.end("fk_geom_transform")
                        profile.end("geom_fk")
            self._step_one_core()
            if profile is not None:
                profile.begin("geom_fk")
                profile.begin("fk_geom_transform")
            try:
                self._refresh_kinematics()
            finally:
                if profile is not None:
                    profile.end("fk_geom_transform")
                    profile.end("geom_fk")

    def _step_one_core(self, *, solve_contact: bool = True, integrate: bool = True):
        """Run dynamics/contact preparation and optionally the replayable tail."""

        import torch

        profile = self._profile_collector
        if profile is not None:
            profile.begin("dynamics")
            profile.begin("dense_dynamics")
        try:
            motion = self._refresh_dynamics()
            if profile is not None:
                profile.begin("dense_passive_actuation")
            try:
                passive = self._passive_force
                passive.zero_()
                for j, _, _, typ, q, d, count in self._compiled_joint_routes:
                    if typ in (self.JOINT_HINGE, self.JOINT_SLIDE):
                        passive[:, d] = -self._v("jnt_stiffness")[j] * (self._qpos[:, q] - self._v("jnt_ref")[j]) - self._v("jnt_damping")[j] * self._qvel[:, d]
                    elif typ in (self.JOINT_BALL, self.JOINT_UNIVERSAL):
                        passive[:, d:d + count] = -self._v("jnt_damping")[j] * self._qvel[:, d:d + count]
                for a, routes in enumerate(self._compiled_actuator_routes):
                    for d, coefficient in routes:
                        if 0 <= d < self.n_dof:
                            passive[:, d] += coefficient * self._ctrl[:, a]
            finally:
                if profile is not None:
                    profile.end("dense_passive_actuation")

            if profile is not None:
                profile.begin("dense_qacc_solve")
            try:
                if self.n_dof:
                    rhs = (passive - self._qfrc_bias)[:, :self.n_dof, None]
                    if (
                        self._cuda_graph_enabled
                        and self._cuda_graph_capture_scope()
                        in {"core_v2", "contact_full_v4", "contact_core_full_v5"}
                    ):
                        self._qacc[:, :self.n_dof] = _capture_safe_cholesky_solve(
                            self._qM[:, :self.n_dof, :self.n_dof], rhs
                        ).squeeze(-1)
                    else:
                        self._qacc[:, :self.n_dof] = torch.linalg.solve(
                            self._qM[:, :self.n_dof, :self.n_dof], rhs
                        ).squeeze(-1)
            finally:
                if profile is not None:
                    profile.end("dense_qacc_solve")

            if profile is not None:
                profile.begin("dense_velocity_update")
            try:
                if self.n_dof:
                    self._qvel += self.physics_dt * self._qacc
            finally:
                if profile is not None:
                    profile.end("dense_velocity_update")
        finally:
            if profile is not None:
                profile.end("dense_dynamics")
                profile.end("dynamics")
        if self.n_dof:
            if self.contact_enabled:
                # Ground rows are resolved after unconstrained acceleration
                # and before qpos integration, matching the local
                # RigidSolver free-body route.
                if (
                    self._cuda_graph_enabled
                    and self._cuda_graph_capture_scope() == "contact_core_v3"
                ):
                    self._prepare_ground_contact_response(motion=motion)
                    if solve_contact:
                        self._run_ground_contact_pgs()
                else:
                    self._solve_ground_contacts(motion=motion)
        if integrate:
            self._step_one_integration()

    def _step_one_integration(self):
        """Integrate one prepared substep; this tail is graph-capture safe."""

        if not self.n_dof:
            return
        profile = self._profile_collector
        if profile is not None:
            profile.begin("integration")
        try:
            for j, _, _, typ, q, d, count in self._compiled_joint_routes:
                if typ in (self.JOINT_HINGE, self.JOINT_SLIDE, self.JOINT_UNIVERSAL):
                    self._qpos[:, q:q + count] += self.physics_dt * self._qvel[:, d:d + count]
                elif typ == self.JOINT_BALL:
                    self._qpos[:, q:q + 4] = _quat_integrate(
                        self._qpos[:, q:q + 4],
                        self._qvel[:, d:d + 3],
                        self.physics_dt,
                    )
                elif typ == self.JOINT_FREE:
                    self._qpos[:, q:q + 3] += self.physics_dt * self._qvel[:, d:d + 3]
                    self._qpos[:, q + 3:q + 7] = _quat_integrate(
                        self._qpos[:, q + 3:q + 7],
                        self._qvel[:, d + 3:d + 6],
                        self.physics_dt,
                    )
        finally:
            if profile is not None:
                profile.end("integration")

    def _reset_world_randomization_defaults(self, selected) -> None:
        """Restore selected worlds without mutating the shared model."""

        import torch

        if not self._world_randomization_enabled:
            return
        selected = selected.to(device=self.device, dtype=torch.bool)
        self._world_friction_mu[selected] = 1.0
        self._world_base_mass_delta[selected] = 0.0
        self._world_body_mass[selected] = self._v("body_mass")
        self._world_body_inertia[selected] = self._v("body_inertia")
        self._world_push_event_steps[selected] = -1
        self._world_push_velocity_xy[selected] = 0.0
        self._world_push_cursor[selected] = 0
        self._world_push_on_reset_boundary[selected] = False

    def apply_world_randomization(
        self,
        *,
        payload: WorldRandomizationBatch,
        mask: np.ndarray,
    ) -> None:
        """Install fixed-shape reset-boundary parameters for selected worlds."""

        import torch

        if not self._world_randomization_enabled:
            raise RuntimeError(
                "world randomization is disabled by this task's static runtime YAML"
            )
        if not isinstance(payload, WorldRandomizationBatch):
            raise TypeError(
                "static fused randomization payload must be WorldRandomizationBatch"
            )
        # Reset samplers may hand us a read-only boolean view.  The tensor is
        # retained by the device-side reset path, so do not let
        # ``torch.as_tensor`` alias a non-writable NumPy buffer.
        selected_mask = np.array(mask, dtype=np.bool_, copy=True)
        if selected_mask.shape != (self.num_envs,):
            raise ValueError(
                f"world randomization mask must have shape ({self.num_envs},)"
            )
        expected = np.flatnonzero(selected_mask).astype(np.int64, copy=False)
        if not np.array_equal(expected, payload.world_indices):
            raise ValueError("world randomization world_indices must match reset mask")
        if payload.event_capacity > self._world_push_capacity:
            raise ValueError(
                f"push schedule capacity {payload.event_capacity} exceeds static capacity "
                f"{self._world_push_capacity}"
            )

        world_ids = torch.as_tensor(
            np.array(payload.world_indices, copy=True),
            dtype=torch.int64,
            device=self.device,
        )
        selected_device = torch.as_tensor(
            selected_mask, dtype=torch.bool, device=self.device
        )
        if payload.lifetime == "episode":
            self._reset_world_randomization_defaults(selected_device)
        initialized = self._world_randomization_initialized.index_select(0, world_ids)
        if payload.lifetime == "construction":
            write_local = ~initialized
            write_world_ids = world_ids[write_local]
        else:
            write_local = torch.ones_like(initialized, dtype=torch.bool)
            write_world_ids = world_ids

        if payload.friction_mu is not None and write_world_ids.numel():
            values = torch.as_tensor(
                np.array(payload.friction_mu, copy=True),
                dtype=torch.float32,
                device=self.device,
            )
            self._world_friction_mu[write_world_ids] = values[write_local]
        if payload.base_mass_delta_kg is not None and write_world_ids.numel():
            values = torch.as_tensor(
                np.array(payload.base_mass_delta_kg, copy=True),
                dtype=torch.float32,
                device=self.device,
            )
            delta = values[write_local]
            base_index = self._base_body_index()
            base_mass = float(self._v("body_mass")[base_index].item())
            effective = base_mass + delta
            if bool(torch.any(effective <= 1.0e-6)):
                raise ValueError("world randomization produced a non-positive base mass")
            self._world_base_mass_delta[write_world_ids] = delta
            self._world_body_mass[write_world_ids] = self._v("body_mass")
            self._world_body_mass[write_world_ids, base_index] = effective
            self._world_body_inertia[write_world_ids] = self._v("body_inertia")
            if payload.inertia_policy == "scale_inertia_with_mass":
                ratio = (effective / base_mass).reshape(-1, 1)
                self._world_body_inertia[write_world_ids, base_index] = (
                    self._v("body_inertia")[base_index].reshape(1, 3) * ratio
                )
            elif payload.inertia_policy != "reference_mass_only":
                raise ValueError(
                    f"unsupported randomization inertia policy {payload.inertia_policy!r}"
                )
        if (
            payload.push_event_steps is not None
            and payload.push_velocity_xy is not None
            and write_world_ids.numel()
        ):
            steps = torch.as_tensor(
                np.array(payload.push_event_steps, copy=True),
                dtype=torch.int32,
                device=self.device,
            )
            velocity = torch.as_tensor(
                np.array(payload.push_velocity_xy, copy=True),
                dtype=torch.float32,
                device=self.device,
            )
            self._world_push_event_steps[write_world_ids] = -1
            self._world_push_velocity_xy[write_world_ids] = 0.0
            self._world_push_event_steps[
                write_world_ids, : payload.event_capacity
            ] = steps[write_local]
            self._world_push_velocity_xy[
                write_world_ids, : payload.event_capacity
            ] = velocity[write_local]
            self._world_push_on_reset_boundary[write_world_ids] = bool(
                payload.push_on_reset_boundary
            )
        self._world_randomization_initialized[world_ids] = True
        self._world_randomization_summary = {
            "configured": True,
            "enabled": True,
            "schema_id": payload.schema_id,
            "reference_profile": payload.reference_profile,
            "lifetime": payload.lifetime,
            "inertia_policy": payload.inertia_policy,
            "selected_count": payload.selected_count,
            "event_capacity": payload.event_capacity,
        }

    def _base_body_index(self) -> int:
        """Return the compiled root body used by mass randomization."""

        parent = self._model.get("body_parentid")
        if parent is not None:
            roots = [
                index
                for index, value in enumerate(parent.detach().cpu().tolist())
                if int(value) < 0
            ]
            if roots:
                return int(roots[0])
        return 0

    def reset_world_randomization(self, mask: np.ndarray) -> None:
        """Reset selected episode clocks and apply an optional step-zero push."""

        import torch

        if not self._world_randomization_enabled:
            return
        selected = torch.as_tensor(mask, dtype=torch.bool, device=self.device)
        if tuple(selected.shape) != (self.num_envs,):
            raise ValueError(
                f"world randomization reset mask must have shape ({self.num_envs},)"
            )
        self._world_episode_step[selected] = 0
        self._world_push_cursor[selected] = 0
        if bool(torch.any(self._world_push_on_reset_boundary & selected)):
            self._apply_reset_boundary_push(selected)

    def _apply_reset_boundary_push(self, selected) -> None:
        import torch

        if self._root_linear_dof_indices.numel() < 2:
            return
        cursor = torch.clamp(
            self._world_push_cursor,
            min=0,
            max=self._world_push_capacity - 1,
        )
        steps = self._world_push_event_steps.gather(1, cursor[:, None]).squeeze(1)
        active = selected & self._world_push_on_reset_boundary & (steps == 0)
        velocity = self._world_push_velocity_xy.gather(
            1, cursor[:, None, None].expand(-1, 1, 2)
        ).squeeze(1)
        root = self._root_linear_dof_indices[:2]
        self._qvel[:, root] = torch.where(
            active[:, None], velocity, self._qvel[:, root]
        )
        self._world_push_cursor.add_(active.to(dtype=torch.int32))

    def _advance_world_randomization_schedule(self) -> None:
        """Apply scheduled pushes once per public control tick."""

        import torch

        if not self._world_randomization_enabled:
            return
        self._world_episode_step.add_(1)
        if self._root_linear_dof_indices.numel() < 2:
            return
        cursor = torch.clamp(
            self._world_push_cursor,
            min=0,
            max=self._world_push_capacity - 1,
        )
        steps = self._world_push_event_steps.gather(1, cursor[:, None]).squeeze(1)
        active = steps == self._world_episode_step
        velocity = self._world_push_velocity_xy.gather(
            1, cursor[:, None, None].expand(-1, 1, 2)
        ).squeeze(1)
        root = self._root_linear_dof_indices[:2]
        self._qvel[:, root] = torch.where(
            active[:, None], velocity, self._qvel[:, root]
        )
        self._world_push_cursor.add_(active.to(dtype=torch.int32))

    def step(self, substeps: int) -> None:
        if int(substeps) != self.control_substeps:
            raise ValueError(f"static fused control_substeps={self.control_substeps}, got {substeps}")
        self._advance_world_randomization_schedule()
        self._run_cuda_graph_or_eager()

    def write_state(self, state: Mapping[str, np.ndarray]) -> None:
        import torch
        self._invalidate_cuda_graph("host_state_write")
        for name, field in (("qpos", self._qpos), ("qvel", self._qvel), ("qacc", self._qacc), ("ctrl", self._ctrl), ("act", self._act)):
            value = np.asarray(state[name], dtype=np.float32)
            if tuple(value.shape) != tuple(field.shape):
                raise ValueError(f"static fused state {name!r} must have shape {tuple(field.shape)}")
            field.copy_(torch.as_tensor(value, dtype=torch.float32, device=self.device))
        self._kinematics_valid = False

    def write_ctrl(self, ctrl: np.ndarray) -> None:
        import torch
        value = np.asarray(ctrl, dtype=np.float32)
        if value.shape != tuple(self._ctrl.shape):
            raise ValueError(f"static fused control must have shape {tuple(self._ctrl.shape)}")
        self._ctrl.copy_(torch.as_tensor(value, dtype=torch.float32, device=self.device))

    def _state_fields(self):
        return self._device_fields

    def read_state(self) -> dict[str, np.ndarray]:
        return {name: value.detach().cpu().numpy().copy() for name, value in self._state_fields().items()}

    def read_device_state(self, names: tuple[str, ...]) -> DeviceBatchState:
        fields = self._state_fields(); unknown = sorted(set(names) - self._device_state_field_set)
        if unknown:
            raise KeyError(f"unknown static fused state fields: {unknown}")
        return DeviceBatchState(arrays={name: fields[name] for name in names}, device=str(self.device), num_envs=self.num_envs)

    def step_device(self, control: Any) -> DeviceBatchState:
        if tuple(getattr(control, "shape", ())) != tuple(self._ctrl.shape) or str(getattr(control, "device", "")) != str(self.device):
            raise RuntimeError(f"static fused device control must be {tuple(self._ctrl.shape)} on {self.device}")
        self._ctrl.copy_(control)
        self._advance_world_randomization_schedule()
        self._run_cuda_graph_or_eager()
        return self.read_device_state(self._device_state_field_names)

    def reset_device(
        self,
        state: Mapping[str, Any],
        mask: Any,
        *,
        selection: DeviceResetSelection | None = None,
    ) -> DeviceBatchState:
        import torch
        try:
            if isinstance(mask, torch.Tensor):
                if str(mask.device) != str(self.device):
                    raise RuntimeError(
                        "static fused reset mask must be on runtime device"
                    )
                selected = mask.to(dtype=torch.bool)
            elif self.device.type == "cpu":
                # Retain the public CPU contract accepted before CUDA-Graph
                # preservation: NumPy/list masks are normalized locally.
                selected = torch.as_tensor(
                    mask,
                    dtype=torch.bool,
                    device=self.device,
                )
            else:
                raise RuntimeError(
                    "static fused CUDA reset mask must be a tensor on runtime device"
                )
            if tuple(selected.shape) != (self.num_envs,):
                raise ValueError(
                    f"static fused reset mask must have shape ({self.num_envs},)"
                )
            if not isinstance(state, Mapping):
                raise TypeError("static fused reset state must be a mapping")
            selected_slots = None
            if selection is not None:
                StaticTemplateFusedArticulated.validate_device_reset_selection(
                    self,
                    mask,
                    selection,
                )
                selected_count = selection.selected_count
                selected_slots = selection.selected_slots
            else:
                selected_count = int(selected.sum().item())

            # Complete validation before the first state mutation.  Besides
            # clearer failures, this prevents a malformed later field from
            # leaving an earlier valid field partially reset.
            updates = []
            for name, field in (
                ("qpos", self._qpos),
                ("qvel", self._qvel),
                ("qacc", self._qacc),
                ("ctrl", self._ctrl),
                ("act", self._act),
            ):
                if name not in state:
                    continue
                value = state[name]
                value_shape = tuple(getattr(value, "shape", ()))
                field_shape = tuple(field.shape)
                if str(getattr(value, "device", "")) != str(self.device):
                    raise RuntimeError(
                        f"static fused reset field {name!r} must be on runtime device"
                    )
                if value_shape == field_shape:
                    selected_value = value[selected]
                elif value_shape == (selected_count, *field_shape[1:]):
                    selected_value = value
                else:
                    raise RuntimeError(
                        f"static fused reset field {name!r} must be full shape {field_shape} "
                        f"or selected shape {(selected_count, *field_shape[1:])}"
                    )
                updates.append((field, selected_value))

            for field, selected_value in updates:
                field[selected] = selected_value
            if selected_count == 0:
                return self.read_device_state(self._device_state_field_names)

            if self.kinematics_backend == "taichi":
                cache_was_valid = bool(self._kinematics_valid)
                self._refresh_kinematics_taichi_selected(
                    selected,
                    selected_count,
                    selected_slots=selected_slots,
                    force_full=not cache_was_valid,
                )
                if not cache_was_valid:
                    self._kinematics_valid = True
            else:
                self._refresh_kinematics()
            if self.contact_enabled:
                self._clear_contact_workspace(selected)
            reset_randomization = getattr(self, "reset_world_randomization", None)
            if callable(reset_randomization):
                reset_randomization(selected)
            return self.read_device_state(self._device_state_field_names)
        except Exception:
            # A partial reset cannot safely retain a captured replay.  This
            # also covers validation failures so callers get one fail-closed
            # lifecycle state for every unsuccessful device reset.
            self._invalidate_cuda_graph("device_reset_failed")
            raise

    def validate_device_reset_selection(
        self,
        mask: Any,
        selection: DeviceResetSelection,
    ) -> None:
        try:
            validate_reset_selection_contract(
                selection,
                mask=mask,
                num_envs=self.num_envs,
                device=str(self.device),
                require_data_pointer=True,
            )
        except Exception:
            self._invalidate_cuda_graph("device_reset_failed")
            raise

    def refresh(self) -> None:
        self._invalidate_cuda_graph("kinematics_refresh")
        self._refresh_kinematics()

    def prewarm(self) -> None:
        self._invalidate_cuda_graph("prewarm")
        self._refresh_kinematics(); self._refresh_dynamics()

    def reset_workspace(self, mask: np.ndarray) -> None:
        self._invalidate_cuda_graph("workspace_reset")
        if self.contact_enabled:
            import torch
            self._clear_contact_workspace(torch.as_tensor(mask, dtype=torch.bool, device=self.device))

    def execution_plan_facts(self) -> Mapping[str, Any]:
        """Publish provider-owned execution and contact layout facts."""

        return {
            "max_contact_pairs_per_world": 0,
            "max_constraint_rows_per_world": 0,
            "contact_workspace_slots_per_world": int(
                self._contact_slots if self.contact_enabled else 0
            ),
            "fused_kernel": True,
            "execution_route": "fused_world_local",
        }

    def render_state_source(self) -> tuple[object, str]:
        """Return the fused provider's batched render state port."""

        return self, "batched"

    def close(self) -> None:
        self._invalidate_cuda_graph("runtime_closed")
        self._close_taichi_external_views()

    def resource_summary(self) -> dict[str, Any]:
        effective_contact_dtype = str(self._contact_mass_response.dtype).removeprefix(
            "torch."
        )
        effective_contact_precision = {
            "float32": "f32",
            "float64": "f64",
        }[effective_contact_dtype]
        scalar = self.n_qpos + 2 * self.n_dof + 2 * self.n_actuators
        state = 4 * self.num_envs * (scalar + 13 * self.n_bodies + 7 * self.n_geoms + 7 * self.n_sites)
        dynamics = 4 * self.num_envs * (self.n_dof * self.n_dof * 2 + 9 * self.n_bodies + self.n_dof)
        contact_fields = (
            self._contact_active, self._contact_body, self._contact_geom,
            self._contact_point, self._contact_normal, self._contact_distance,
            self._contact_normal_lambda, self._contact_tangent_lambda,
            self._contact_count, self._contact_summary_active,
            self._contact_summary_distance, self._contact_jacobian,
            self._contact_friction,
        ) if self.contact_enabled else ()
        contact_per_world = int(sum(field.numel() * field.element_size() for field in contact_fields) // max(1, self.num_envs))
        persistent_workspace_fields = (
            self._body_xmat,
            self._body_inertia_world,
            self._geom_xmat,
            self._contact_axes,
            self._contact_jacobians,
            self._contact_jacobian_axes,
            self._contact_mass_response,
            self._contact_mass_diagonal,
            self._contact_response_factor,
            self._contact_response_factor_info,
            self._contact_bias,
            self._contact_motion_rot,
            self._contact_motion_lin,
            self._passive_force,
        )
        if self._contact_topology_factor is not None:
            persistent_workspace_fields = (
                *persistent_workspace_fields,
                self._contact_topology_factor,
                self._contact_topology_root_factor,
                self._contact_topology_child_info,
                self._contact_topology_root_info,
            )
        if self._world_randomization_enabled:
            persistent_workspace_fields = (
                *persistent_workspace_fields,
                self._world_friction_mu,
                self._world_base_mass_delta,
                self._world_body_mass,
                self._world_body_inertia,
                self._world_push_event_steps,
                self._world_push_velocity_xy,
                self._world_push_cursor,
                self._world_episode_step,
                self._world_randomization_initialized,
                self._world_push_on_reset_boundary,
            )
        persistent_workspace_per_world = int(
            sum(field.numel() * field.element_size() for field in persistent_workspace_fields)
            // max(1, self.num_envs)
        )
        dynamics += contact_per_world * self.num_envs
        dynamics += persistent_workspace_per_world * self.num_envs
        shared = int(sum(value.numel() * value.element_size() for value in self._model.values()))
        shared += int(self._eye3.numel() * self._eye3.element_size())
        shared += int(self._eye_dof.numel() * self._eye_dof.element_size())
        if self.contact_enabled:
            shared += int(sum(
                value.numel() * value.element_size()
                for value in (
                    self._contact_slot_dof_indices,
                    self._contact_slot_dof_mask,
                    self._contact_pair_slots,
                    self._contact_pair_dofs,
                )
            ))
        pgs_backend_summary = self._contact_pgs_backend_summary()
        response_backend_summary = self._contact_response_backend_summary()
        randomization_available = bool(self._world_randomization_enabled)
        graph_available = self.device.type == "cuda"
        return {
            "execution": "fused_world_local",
            "implementation_status": (
                "fused_taichi_fk_torch_solver"
                if self.kinematics_backend == "taichi"
                else "fused_torch_kernel"
            ),
            "solver_count": 1,
            "num_envs": self.num_envs,
            "backend": self.backend,
            "exact_batch": True,
            "workspace_addressing": "(world_id, local_id)",
            "global_id_policy": "forbidden",
            "compiled_traversal": "static_topology_routes_v1",
            "dense_rne_body_wrench": self._DENSE_RNE_BODY_WRENCH_PROVENANCE,
            "compiled_traversal_digest": self._compiled_traversal_digest,
            "compiled_traversal_routes": {
                "body": len(self._compiled_body_routes),
                "joint": len(self._compiled_joint_routes),
                "dof": len(self._compiled_dof_routes),
                "geom": len(self._compiled_geom_bodies),
                "site": len(self._compiled_site_bodies),
                "actuator": len(self._compiled_actuator_routes),
            },
            "shared_template_bytes": shared,
            "per_world_state_bytes": state // self.num_envs,
            "per_world_workspace_bytes": dynamics // self.num_envs,
            "persistent_workspace_bytes_per_world": persistent_workspace_per_world,
            "persistent_workspace_fields": [
                "body_xmat",
                "body_inertia_world",
                "geom_xmat",
                "contact_axes",
                "contact_jacobians",
                "contact_jacobian_axes",
                "contact_mass_response",
                "contact_mass_diagonal",
                "contact_response_factor",
                "contact_response_factor_info",
                "contact_bias",
                "contact_motion_rot",
                "contact_motion_lin",
                "passive_force",
                *(
                    [
                        "contact_topology_factor",
                        "contact_topology_root_factor",
                        "contact_topology_child_info",
                        "contact_topology_root_info",
                    ]
                    if self._contact_topology_factor is not None
                    else []
                ),
            ],
            "contact_workspace_bytes_per_world": contact_per_world,
            "total_payload_bytes": shared + state + dynamics,
            "contact_profile": "local_ground_rows" if self.contact_enabled else "disabled_explicitly",
            "contact_enabled": self.contact_enabled,
            "contact_workspace_slots_per_world": self._contact_slots if self.contact_enabled else 0,
            "contact_candidate_geoms": len(self._ground_contact_geom_ids) if self.contact_enabled else 0,
            "contact_layout": "compact_eligible_geom_slots_v1" if self.contact_enabled else "disabled_explicitly",
            "contact_jacobian_layout": "sparse_static_slot_dof_pairs_v1" if self.contact_enabled else "disabled_explicitly",
            **pgs_backend_summary,
            **response_backend_summary,
            "dynamics_factorization": (
                "qacc_fixed_batched_cholesky_capture_safe_v3"
                if (
                    self._cuda_graph_enabled
                    and self._cuda_graph_capture_scope()
                    in {"core_v2", "contact_full_v4", "contact_core_full_v5"}
                )
                else "qacc_linalg_solve_parity_guard_v1"
                if self.n_dof
                else "disabled_explicitly"
            ),
            "cuda_graph_dynamics_factorization": (
                "qacc_fixed_batched_cholesky_capture_safe_v3"
                if (
                    self._cuda_graph_enabled
                    and self._cuda_graph_capture_scope()
                    in {"core_v2", "contact_full_v4", "contact_core_full_v5"}
                    and self.n_dof
                )
                else "disabled_explicitly"
            ),
            "contact_factorization": (
                "per_substep_f32_fixed_topology_child_schur_root6x6_v1"
                if (
                    self.contact_enabled
                    and self._next_contact_response_backend()
                    == _CONTACT_RESPONSE_TOPOLOGY_P12_BACKEND
                )
                else "per_substep_f32_fixed_topology_child_schur_root_torch_v1"
                if (
                    self.contact_enabled
                    and self._next_contact_response_backend()
                    == _CONTACT_RESPONSE_TOPOLOGY_P1_BACKEND
                )
                else
                "per_substep_f32_fixed_cholesky_ex_active_slot_triton_v1"
                if (
                    self.contact_enabled
                    and self._next_contact_response_backend()
                    == _CONTACT_RESPONSE_TRITON_BACKEND
                )
                else
                f"per_substep_{effective_contact_precision}_fixed_cholesky_capture_safe_v2"
                if (
                    self.contact_enabled
                    and self.device.type == "cuda"
                    and self._cuda_graph_enabled
                    and self._cuda_graph_capture_scope()
                    in {"contact_full_v4", "contact_core_full_v5"}
                )
                else f"per_substep_{effective_contact_precision}_shared_cholesky_v1"
                if self.contact_enabled
                else "disabled_explicitly"
            ),
            "contact_workspace_reset": "in_place_masked_fill_v1" if self.contact_enabled else "disabled_explicitly",
            "world_randomization": {
                **self._world_randomization_summary,
                "capabilities": {
                    "friction": self._world_randomization_enabled,
                    "push_schedule": self._world_randomization_enabled,
                    "base_mass": self._world_randomization_enabled,
                    "inertia_policy": (
                        ["reference_mass_only", "scale_inertia_with_mass"]
                        if self._world_randomization_enabled
                        else []
                    ),
                },
                "push_event_capacity": (
                    self._world_push_capacity
                    if self._world_randomization_enabled
                    else 0
                ),
                "root_linear_dof_indices": self._root_linear_dof_indices.detach()
                .cpu()
                .tolist(),
                "base_body_index": (
                    self._base_body_index()
                    if self._world_randomization_enabled
                    else None
                ),
                "step_unit": "public_control_tick",
                "hot_path_host_sync": False,
            },
            "capabilities": {
                "reset": {
                    "host": True,
                    "masked": True,
                    "partial_state": True,
                    "post_reset_readable": True,
                },
                "randomization": {
                    "available": randomization_available,
                    "friction": randomization_available,
                    "base_mass": randomization_available,
                    "inertia_policy": (
                        ["reference_mass_only", "scale_inertia_with_mass"]
                        if randomization_available
                        else []
                    ),
                    "push_schedule": randomization_available,
                    "selected_worlds": randomization_available,
                    "episode_lifetime": randomization_available,
                },
                "device": {
                    "read": True,
                    "step": True,
                    "reset": True,
                    "selection_validation": True,
                },
                "contact": {
                    "ground": self.contact_enabled,
                    "contact_state": self.contact_enabled,
                },
                "graph": {
                    "cuda_graph": graph_available,
                    "enabled": bool(self._cuda_graph_enabled),
                },
                "render": {
                    "source": True,
                    "mode": "batched",
                },
            },
            "kinematics_backend": self.kinematics_backend,
            "contact_precision_requested": self.contact_precision,
            "contact_precision_effective": effective_contact_precision,
            "contact_precision_policy": "cuda_selectable_cpu_f32_reference_v1",
            "geometry_transform_layout": (
                "taichi_fixed_topology_v1"
                if self.kinematics_backend == "taichi"
                else "batched_body_gather_v1"
            ),
            "contact_candidate_layout": "batched_shape_slot_candidates_v1" if self.contact_enabled else "disabled_explicitly",
            "optional_contact_state_fields": ["ground_contact_geom"] if self.contact_enabled else [],
            "contact_solve_intermediate_dtype": effective_contact_dtype,
            "device_transition": {"available": True, "field_device": str(self.device), "zero_copy_substeps": True},
            "runtime_boundary": self.runtime_boundary_snapshot(),
            "cuda_graph": self._cuda_graph_resource_summary(),
        }


def torch_bmm_vec(matrix, vector):
    """Batched matrix-vector product accepting a shared local vector."""
    import torch
    if vector.ndim == 1:
        vector = vector.expand(matrix.shape[0], vector.shape[0])
    return torch.bmm(matrix, vector.unsqueeze(-1)).squeeze(-1)


__all__ = ["StaticTemplateFusedArticulated"]
