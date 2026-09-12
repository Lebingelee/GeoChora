"""Aggregate the measured Isaac/MuJoCo/GeoPhys Go2 contact-onset envelope.

Isaac Gym lives in the supplied Python-3.8 ``adamanip`` environment, while
MuJoCo and GeoPhys run in ``geophys``.  This report therefore consumes the
Isaac trace produced by ``task_env.diagnostics.go2.isaac_contact_oracle`` and reproduces the
MuJoCo/fused-GeoPhys traces locally.  It deliberately freezes the distinction
between a measured three-engine envelope and a claim of contact bitwise
parity.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from task_env.assembly import compile_task_scene
from task_env.environment.configuration import resolve_task_env_config
from task_env.runtime import make_batch_runtime
from task_env.diagnostics.go2.mujoco_oracle import DEFAULT_ANGLES, Go2MujocoOracle
from task_env.tasks.go2_walk.assets import Go2PlatformBoxSceneComposer
from task_env.tasks.go2_walk.task import Go2WalkEnv, _base_kinematics, _base_roll_pitch


from ...utils._paths import REPO_ROOT


def _host(value) -> np.ndarray:
    detach = getattr(value, "detach", None)
    if callable(detach):
        value = detach()
    cpu = getattr(value, "cpu", None)
    if callable(cpu):
        value = cpu()
    return np.asarray(value)


def _initial_state(compiled, *, root_z: float, batch: int) -> dict[str, np.ndarray]:
    initial = compiled.initial_state
    refs = compiled.references.agents["go2-v1"]
    state = {
        name: np.asarray(getattr(initial, name), dtype=np.float32)[None, :].copy()
        for name in ("qpos", "qvel", "qacc", "ctrl", "act")
    }
    state["qpos"][0, :7] = np.asarray((0.0, 0.0, root_z, 1.0, 0.0, 0.0, 0.0), dtype=np.float32)
    state["qpos"][0, refs.arm_qpos_ids] = DEFAULT_ANGLES
    state["qvel"].fill(0.0)
    return {name: np.repeat(value, int(batch), axis=0) for name, value in state.items()}


def _setup_mujoco(oracle: Go2MujocoOracle, state, refs) -> None:
    qpos = np.zeros(oracle.model.nq, dtype=np.float32)
    qvel = np.zeros(oracle.model.nv, dtype=np.float32)
    qpos[:7] = state["qpos"][0, :7]
    qpos[oracle.qpos_ids] = state["qpos"][0, refs.arm_qpos_ids]
    qvel[:6] = state["qvel"][0, :6]
    qvel[oracle.dof_ids] = state["qvel"][0, refs.arm_dof_ids]
    oracle.reset(qpos=qpos, qvel=qvel)


def _observation(qpos, qvel, refs, previous_action=None) -> np.ndarray:
    """Build the canonical blind 48-d observation from a wxyz state."""
    qpos = np.asarray(qpos, dtype=np.float32)
    qvel = np.asarray(qvel, dtype=np.float32)
    _, lin, ang, gravity = _base_kinematics(qpos, qvel, None, 0)
    action = np.zeros(12, dtype=np.float32) if previous_action is None else np.asarray(previous_action, dtype=np.float32)
    return np.concatenate((
        lin * 2.0,
        ang * 0.25,
        gravity,
        np.zeros(3, dtype=np.float32),
        qpos[refs.arm_qpos_ids] - DEFAULT_ANGLES,
        qvel[refs.arm_dof_ids] * 0.05,
        action,
    )).astype(np.float32)


def _root_state_from_isaac(row) -> tuple[np.ndarray, np.ndarray]:
    state = np.asarray(row["root_state_xyzw"], dtype=np.float32)[0]
    qpos = np.zeros(7, dtype=np.float32)
    qpos[:3] = state[:3]
    # Isaac Gym stores xyzw; the task/oracle contract stores wxyz.
    qpos[3:7] = state[[6, 3, 4, 5]]
    return qpos, state[7:13].copy()


def _contact_bodies_mujoco(
    oracle: Go2MujocoOracle,
    n_bodies: int,
    local_body_ids: dict[str, int] | None = None,
) -> tuple[np.ndarray, np.ndarray, bool]:
    ground = np.zeros(n_bodies, dtype=np.bool_)
    body = np.zeros(n_bodies, dtype=np.bool_)
    ground_id = int(oracle.model.geom("oracle_ground").id)
    support_contact = False
    for index in range(int(oracle.data.ncon)):
        contact = oracle.data.contact[index]
        geom_a, geom_b = int(contact.geom1), int(contact.geom2)
        if geom_a == ground_id or geom_b == ground_id:
            support_contact = True
            other = geom_b if geom_a == ground_id else geom_a
            raw_body_id = int(oracle.model.geom_bodyid[other])
            body_name = str(oracle.model.body(raw_body_id).name)
            body_id = int((local_body_ids or {}).get(body_name, raw_body_id))
            if 0 <= body_id < n_bodies:
                ground[body_id] = True
        else:
            raw_body_a = int(oracle.model.geom_bodyid[geom_a])
            raw_body_b = int(oracle.model.geom_bodyid[geom_b])
            body_a = int((local_body_ids or {}).get(str(oracle.model.body(raw_body_a).name), raw_body_a))
            body_b = int((local_body_ids or {}).get(str(oracle.model.body(raw_body_b).name), raw_body_b))
            if 0 <= body_a < n_bodies:
                body[body_a] = True
            if 0 <= body_b < n_bodies:
                body[body_b] = True
    return ground, body, support_contact


def _contact_geoms_mujoco(
    oracle: Go2MujocoOracle,
    geom_count: int,
    *,
    local_geom_ids: dict[str, int] | None = None,
) -> np.ndarray:
    """Return active MuJoCo geom identities for reward/contact semantics."""

    result = np.full(int(geom_count), -1, dtype=np.int32)
    ground_id = int(oracle.model.geom("oracle_ground").id)
    active: list[int] = []
    for index in range(int(oracle.data.ncon)):
        contact = oracle.data.contact[index]
        for geom_id in (int(contact.geom1), int(contact.geom2)):
            if geom_id == ground_id:
                continue
            raw_name = str(oracle.model.geom(geom_id).name)
            if local_geom_ids is not None and raw_name in local_geom_ids:
                active.append(int(local_geom_ids[raw_name]))
    if active:
        values = np.asarray(sorted(set(active)), dtype=np.int32)
        values = values[(values >= 0) & (values < int(geom_count))]
        result[: values.size] = values
    return result


def _geophys_row_contact_mask(runtime, body_count: int) -> np.ndarray:
    """Read exact-row body identity for the private platform diagnostic.

    The public summary is preferred after the generalized row report fix.  A
    solved-block fallback keeps old cached solver builds diagnosable without
    changing the public runtime contract.
    """

    mask = np.zeros(int(body_count), dtype=np.bool_)
    physics = getattr(runtime, "_physics", None)
    solvers = tuple(getattr(physics, "_solvers", ()) or ())
    if not solvers:
        return mask
    solver = solvers[0]
    # The public summary is the contract consumed by tasks.  Keep the solved
    # row-buffer fallback below for old/cached solver builds, but prefer the
    # post-FK summary produced by the generalized row report path.
    try:
        public_active = np.asarray(solver.body_contact_active.to_numpy(), dtype=np.bool_)
        public_count = np.asarray(solver.body_contact_count.to_numpy(), dtype=np.int32)
        width = min(int(body_count), len(public_active), len(public_count))
        if width > 0 and int(public_count[:width].sum()) > 0:
            mask[:width] = public_active[:width]
            return mask
    except AttributeError:
        pass
    try:
        block_count = int(np.asarray(solver.contact_block_count.to_numpy()))
        block_a = np.asarray(solver.contact_block_body_a.to_numpy())
        block_b = np.asarray(solver.contact_block_body_b.to_numpy())
        row_start = np.asarray(solver.contact_block_row_start.to_numpy())
        row_count = np.asarray(solver.contact_block_row_count.to_numpy())
        lambdas = np.asarray(solver.contact_row_lambda.to_numpy())
    except AttributeError:
        return mask
    for block_id in range(min(block_count, len(block_a))):
        start = int(row_start[block_id])
        count = int(row_count[block_id])
        if start < 0 or count <= 0 or start >= len(lambdas):
            continue
        if float(lambdas[start]) <= 1.0e-8:
            continue
        for body_id in (int(block_a[block_id]), int(block_b[block_id])):
            if 0 <= body_id < mask.size:
                mask[body_id] = True
    return mask


def _geophys_row_contact_geom_mask(runtime, geom_count: int) -> np.ndarray:
    """Read solved exact-row geom identities for the private platform probe."""

    result = np.full(int(geom_count), -1, dtype=np.int32)
    physics = getattr(runtime, "_physics", None)
    solvers = tuple(getattr(physics, "_solvers", ()) or ())
    if not solvers:
        return result
    solver = solvers[0]
    try:
        block_count = int(np.asarray(solver.contact_block_count.to_numpy()))
        geom_a = np.asarray(solver.contact_block_geom_a.to_numpy())
        geom_b = np.asarray(solver.contact_block_geom_b.to_numpy())
        row_start = np.asarray(solver.contact_block_row_start.to_numpy())
        row_count = np.asarray(solver.contact_block_row_count.to_numpy())
        lambdas = np.asarray(solver.contact_row_lambda.to_numpy())
    except AttributeError:
        return result
    active: list[int] = []
    for block_id in range(min(block_count, len(geom_a), len(geom_b))):
        start = int(row_start[block_id])
        count = int(row_count[block_id])
        if start < 0 or count <= 0 or start >= len(lambdas):
            continue
        if float(lambdas[start]) <= 1.0e-8:
            continue
        active.extend((int(geom_a[block_id]), int(geom_b[block_id])))
    if active:
        values = np.asarray(sorted(set(active)), dtype=np.int32)
        values = values[(values >= 0) & (values < int(geom_count))]
        result[: values.size] = values
    return result


def _evaluate_task(task, *, qpos, qvel, ground_contact, body_contact, contact_geom=None, previous_action, previous_vel):
    action = np.zeros(12, dtype=np.float32)
    _, lin, ang, gravity = _base_kinematics(qpos, qvel, None, task.base_body_id)
    torque = task._compute_torque(action, qpos, qvel)
    reward, terms = task._reward(
        lin, ang, gravity, torque, action, previous_action, qpos, qvel,
        np.zeros(3, dtype=np.float32), previous_vel, ground_contact, body_contact,
        contact_geom,
    )
    roll, pitch = _base_roll_pitch(qpos, None, task.base_body_id)
    fall = bool(abs(float(roll)) > 0.8 or abs(float(pitch)) > 1.0)
    base_contact = bool(task._body_contact(ground_contact, body_contact, task.base_body_id, ())[()])
    return float(np.asarray(reward)), {name: float(np.asarray(value)) for name, value in terms.items()}, fall or base_contact, False


def _run_geophys_and_mujoco(
    *,
    backend: str,
    root_z: float,
    steps: int,
    profile: str,
    rigid_solver_backend: str,
    platform_box: bool,
):
    base = resolve_task_env_config(Go2WalkEnv, None)
    config = replace(
        base,
        runtime=replace(
            base.runtime,
            backend=backend,
            prewarm=False,
            batch_physics_layout="static_template",
            static_template={
                "profile": str(profile),
                "kinematics_backend": "torch",
                "contact_precision": "f64",
                "cuda_graph": False,
            },
            # A platform-box probe must exercise the static-body contact route,
            # not the analytic plane route.  The canonical plane keeps the
            # existing ground-contact configuration.
            enable_ground_contact=not bool(platform_box),
            enable_domain_boundary_contact=False,
            rigid_solver_backend=str(rigid_solver_backend),
        ),
    )
    env = Go2WalkEnv(config=config, build_runtime=False)
    scene_composer = (
        Go2PlatformBoxSceneComposer()
        if platform_box
        else env.create_scene_composer()
    )
    compiled = compile_task_scene(
        composition=env.composition_spec,
        scene=env.scene,
        agents=env.agents,
        objects=env.objects,
        scene_composer=scene_composer,
    )
    refs = compiled.references.agents["go2-v1"]
    local_body_ids = {
        str(name): int(body_id)
        for name, body_id in dict(getattr(compiled.references.names, "bodies", {}) or {}).items()
    }
    task = env.create_task_definition(compiled)
    task._feet_air_time = np.zeros(4, dtype=np.float32)
    task._last_contacts = np.zeros(4, dtype=np.bool_)
    task_mujoco = env.create_task_definition(compiled)
    task_mujoco._feet_air_time = np.zeros(4, dtype=np.float32)
    task_mujoco._last_contacts = np.zeros(4, dtype=np.bool_)
    state1 = _initial_state(compiled, root_z=root_z, batch=1)
    # The static-body platform probe is intentionally a B=1 route check.  A
    # second exact RigidSolver roughly doubles the already large generalized
    # contact compilation footprint, while B>1 isolation is covered by the
    # canonical fused-ground smoke.  Keep the normal three-engine report at
    # B=2 and make the private platform diagnostic resource-bounded.
    isolation_batch = 1 if platform_box else 2
    state2 = _initial_state(compiled, root_z=root_z, batch=isolation_batch)
    runtime1 = make_batch_runtime(compiled_scene=compiled, resolved_config=config, num_envs=1, backend=backend)
    # Do not construct a second exact solver for the private platform probe;
    # it is a contact-route check and the canonical fused smoke owns B>1
    # isolation.  This also keeps the diagnostic below the local compiler
    # memory ceiling.
    runtime2 = None if platform_box else make_batch_runtime(
        compiled_scene=compiled,
        resolved_config=config,
        num_envs=isolation_batch,
        backend=backend,
    )
    oracle = Go2MujocoOracle(platform_box=platform_box)
    _setup_mujoco(oracle, state1, refs)
    mask1 = np.ones(1, dtype=np.bool_)
    mask2 = np.ones(isolation_batch, dtype=np.bool_)
    runtime1.reset(state=state1, mask=mask1)
    if runtime2 is not None:
        runtime2.reset(state=state2, mask=mask2)
    action1 = np.zeros_like(state1["ctrl"])
    action2 = np.zeros_like(state2["ctrl"])
    rows = []
    try:
        for tick in range(1, int(steps) + 1):
            one = runtime1.step(action1).state.arrays
            two = runtime2.step(action2).state.arrays if runtime2 is not None else one
            mujoco = oracle.step(np.zeros(12, dtype=np.float32))
            geo_qpos = _host(one["qpos"])[0]
            geo_qvel = _host(one["qvel"])[0]
            batch_qpos = _host(two["qpos"])[0]
            batch_qvel = _host(two["qvel"])[0]
            mujoco_native_qpos = np.asarray(mujoco["qpos"], dtype=np.float32)
            mujoco_native_qvel = np.asarray(mujoco["qvel"], dtype=np.float32)
            # MuJoCo's native qpos/qvel addresses are model-specific; convert
            # to the canonical compiled Go2 layout before task algebra and
            # observation comparison.
            mujoco_qpos = np.zeros(19, dtype=np.float32)
            mujoco_qvel = np.zeros(18, dtype=np.float32)
            mujoco_qpos[:7] = mujoco_native_qpos[:7]
            mujoco_qpos[refs.arm_qpos_ids] = mujoco_native_qpos[oracle.qpos_ids]
            mujoco_qvel[:6] = mujoco_native_qvel[:6]
            mujoco_qvel[refs.arm_dof_ids] = mujoco_native_qvel[oracle.dof_ids]
            active = _host(one.get("ground_contact_count", np.zeros((1, 1), dtype=np.int32)))[0]
            body_count = len(tuple(getattr(compiled.scene_model, "objects", ()) or ()))
            geo_ground = _host(one.get("ground_contact_active", np.zeros((1, body_count), dtype=np.bool_)))[0].astype(np.bool_)
            geo_body = _host(one.get("body_contact_active", np.zeros_like(geo_ground)))[0].astype(np.bool_)
            if platform_box:
                # Exact row-PGS static endpoints are read from the solved
                # local blocks for this diagnostic; this also preserves the
                # platform/calf identity needed by the reward comparison.
                geo_body = _geophys_row_contact_mask(runtime1, body_count)
                geo_contact_geom = _geophys_row_contact_geom_mask(
                    runtime1, int(compiled.scene_model.joint_data["n_geoms"])
                )
            else:
                geo_contact_geom = _host(one.get("ground_contact_geom"))[0] if "ground_contact_geom" in one else None
            mujoco_ground, mujoco_body, mujoco_support_contact = _contact_bodies_mujoco(
                oracle,
                body_count,
                local_body_ids=local_body_ids,
            )
            mujoco_contact_geom = _contact_geoms_mujoco(
                oracle,
                int(compiled.scene_model.joint_data["n_geoms"]),
                local_geom_ids=dict(compiled.references.names.geoms),
            )
            platform_body_id = -1
            if platform_box:
                names = dict(getattr(compiled.references.names, "bodies", {}) or {})
                platform_body_id = int(names.get("go2_support_platform", -1))
            geo_support_contact = bool(
                platform_box
                and 0 <= platform_body_id < geo_body.size
                and geo_body[platform_body_id]
            )
            geo_reward, geo_terms, geo_done, geo_timeout = _evaluate_task(
                task, qpos=geo_qpos, qvel=geo_qvel, ground_contact=geo_ground,
                body_contact=geo_body, previous_action=np.zeros(12, dtype=np.float32),
                contact_geom=geo_contact_geom,
                previous_vel=np.zeros(12, dtype=np.float32) if tick == 1 else prev_geo_vel,
            )
            mujoco_reward, mujoco_terms, mujoco_done, mujoco_timeout = _evaluate_task(
                task_mujoco, qpos=mujoco_qpos, qvel=mujoco_qvel, ground_contact=mujoco_ground,
                body_contact=mujoco_body, previous_action=np.zeros(12, dtype=np.float32),
                contact_geom=mujoco_contact_geom,
                previous_vel=np.zeros(12, dtype=np.float32) if tick == 1 else prev_mujoco_vel,
            )
            prev_geo_vel = geo_qvel[refs.arm_dof_ids].copy()
            prev_mujoco_vel = mujoco_qvel[refs.arm_dof_ids].copy()
            rows.append({
                "tick": tick,
                "geophys": {
                    "root_z": float(geo_qpos[2]),
                    "root_vz": float(geo_qvel[2]),
                    "contact_rows": int(np.asarray(active).sum()),
                    "body_contact_count": int(np.asarray(geo_body).sum()),
                    "contact_geom_count": int(np.count_nonzero(np.asarray(geo_contact_geom) >= 0)) if geo_contact_geom is not None else 0,
                    "support_contact": geo_support_contact,
                    "joint_qpos_max_abs": float(np.max(np.abs(geo_qpos[refs.arm_qpos_ids] - mujoco_qpos[refs.arm_qpos_ids]))),
                    "joint_qvel_max_abs": float(np.max(np.abs(geo_qvel[refs.arm_dof_ids] - mujoco_qvel[refs.arm_dof_ids]))),
                    "observation": _observation(geo_qpos, geo_qvel, refs).tolist(),
                    "reward": geo_reward,
                    "reward_terms": geo_terms,
                    "terminated": bool(geo_done),
                    "truncated": bool(geo_timeout),
                },
                "mujoco": {
                    "root_z": float(mujoco_qpos[2]),
                    "root_vz": float(mujoco_qvel[2]),
                    "contact_count": int(oracle.data.ncon),
                    "contact_geom_count": int(np.count_nonzero(np.asarray(mujoco_contact_geom) >= 0)),
                    "support_contact": bool(mujoco_support_contact),
                    "observation": _observation(mujoco_qpos, mujoco_qvel, refs).tolist(),
                    "reward": mujoco_reward,
                    "reward_terms": mujoco_terms,
                    "terminated": bool(mujoco_done),
                    "truncated": bool(mujoco_timeout),
                },
                "slot0_isolation": {
                    "qpos_max_abs": float(np.max(np.abs(geo_qpos - batch_qpos))) if isolation_batch > 1 else 0.0,
                    "qvel_max_abs": float(np.max(np.abs(geo_qvel - batch_qvel))) if isolation_batch > 1 else 0.0,
                },
            })
            rows[-1]["observation_max_abs_mujoco_geophys"] = float(np.max(np.abs(
                np.asarray(rows[-1]["mujoco"]["observation"]) - np.asarray(rows[-1]["geophys"]["observation"])
            )))
        return rows, runtime1.resource_summary(), (
            runtime2.resource_summary() if runtime2 is not None else runtime1.resource_summary()
        )
    finally:
        runtime1.close()
        if runtime2 is not None:
            runtime2.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isaac-json", type=Path, default=REPO_ROOT / "temp_outputs/task_env/go2_isaac_contact_oracle.json")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "temp_outputs/task_env/go2_three_contact_oracle_report.json")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--profile",
        choices=("articulated_ground_contact_v1", "articulated_fused_ground_contact_v1"),
        default="articulated_fused_ground_contact_v1",
        help="static-template execution profile; soft_efc uses the exact-B RigidSolver profile",
    )
    parser.add_argument(
        "--rigid-solver-backend",
        choices=("row_pgs", "soft_efc"),
        default="row_pgs",
        help="RigidSolver backend used by the exact-B reference profile",
    )
    parser.add_argument("--root-z", type=float, default=0.35)
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument(
        "--allow-contact-onset-mismatch",
        action="store_true",
        help="write a diagnostic report even when a backend has a different contact onset",
    )
    parser.add_argument(
        "--platform-box",
        action="store_true",
        help=(
            "use a private thin static-body box instead of the plane; this is an "
            "exact-RigidSolver body-contact diagnostic, not a fused-runtime capability"
        ),
    )
    args = parser.parse_args()
    if int(args.steps) < 1:
        parser.error("--steps must be positive")
    isaac = json.loads(args.isaac_json.read_text(encoding="utf-8"))
    if isaac.get("schema") != "task-env-go2-isaac-contact-oracle-v1":
        raise ValueError("Isaac artifact does not use the contact-oracle schema")
    if abs(float(isaac["config"]["root_z"]) - float(args.root_z)) > 1.0e-6:
        raise ValueError("Isaac artifact root_z does not match this report")
    if len(isaac.get("trace", ())) < int(args.steps) + 1:
        raise ValueError("Isaac artifact has fewer ticks than requested")
    rows, resource1, resource2 = _run_geophys_and_mujoco(
        backend=args.backend,
        root_z=float(args.root_z),
        steps=int(args.steps),
        profile=str(args.profile),
        rigid_solver_backend=str(args.rigid_solver_backend),
        platform_box=bool(args.platform_box),
    )
    combined = []
    isaac_rows = isaac["trace"]
    # The compiled canonical Go2 layout is validated by stage16 contract
    # smoke: free-root qpos[0:7], then 12 arm qpos; qvel[0:6], then 12 arm
    # dofs.  Keep this aggregation script independent of task construction.
    refs = SimpleNamespace(
        arm_qpos_ids=np.asarray((7, 11, 15, 8, 12, 16, 9, 13, 17, 10, 14, 18), dtype=np.int32),
        arm_dof_ids=np.asarray((6, 10, 14, 7, 11, 15, 8, 12, 16, 9, 13, 17), dtype=np.int32),
    )
    for row in rows:
        isaac_row = isaac_rows[int(row["tick"])]
        isaac_qpos_root, isaac_root_vel = _root_state_from_isaac(isaac_row)
        isaac_qpos = np.zeros(19, dtype=np.float32)
        isaac_qvel = np.zeros(18, dtype=np.float32)
        isaac_qpos[:7] = isaac_qpos_root
        isaac_qvel[:6] = isaac_root_vel
        isaac_qpos[refs.arm_qpos_ids] = np.asarray(isaac_row["dof_pos"], dtype=np.float32)[0]
        isaac_qvel[refs.arm_dof_ids] = np.asarray(isaac_row["dof_vel"], dtype=np.float32)[0]
        # The Isaac trace stores active body indices from the net contact force
        # tensor.  Map those indices to the same local body mask used by the
        # host task evaluator; no contact force magnitude is inferred here.
        isaac_ground = np.zeros(14, dtype=np.bool_)
        isaac_body = np.zeros(14, dtype=np.bool_)
        for body_id in isaac_row["contact"].get("active_body_indices", ()):
            if 0 <= int(body_id) < isaac_ground.size:
                isaac_ground[int(body_id)] = True
        # Isaac rewards/done are authoritative in the legacy artifact.  Its
        # observation is reconstructed only to make the layout/value report
        # explicit; reward terms are intentionally not reverse-engineered.
        row["isaac"] = {
            "root_z": float(isaac_row["root_z"]),
            "root_vz": float(isaac_row["root_vz"]),
            "contact_count": int(isaac_row["contact"]["active_body_count"]),
            "support_contact": bool(int(isaac_row["contact"]["active_body_count"]) > 0),
            "observation": _observation(isaac_qpos, isaac_qvel, refs).tolist(),
            "reward": float(np.asarray(isaac_row.get("reward", [0.0]))[0]),
            "terminated": bool(np.asarray(isaac_row.get("terminated_or_done", [False]))[0]),
            "truncated": bool(np.asarray(isaac_row.get("timeout", [False]))[0]),
        }
        row["pairwise_root_z_abs"] = {
            "isaac_mujoco": abs(row["isaac"]["root_z"] - row["mujoco"]["root_z"]),
            "isaac_geophys": abs(row["isaac"]["root_z"] - row["geophys"]["root_z"]),
            "mujoco_geophys": abs(row["mujoco"]["root_z"] - row["geophys"]["root_z"]),
        }
        row["pairwise_root_vz_abs"] = {
            "isaac_mujoco": abs(row["isaac"]["root_vz"] - row["mujoco"]["root_vz"]),
            "isaac_geophys": abs(row["isaac"]["root_vz"] - row["geophys"]["root_vz"]),
            "mujoco_geophys": abs(row["mujoco"]["root_vz"] - row["geophys"]["root_vz"]),
        }
        row["pairwise_observation_max_abs"] = {
            "isaac_mujoco": float(np.max(np.abs(
                np.asarray(row["isaac"]["observation"]) - np.asarray(row["mujoco"]["observation"])
            ))),
            "isaac_geophys": float(np.max(np.abs(
                np.asarray(row["isaac"]["observation"]) - np.asarray(row["geophys"]["observation"])
            ))),
            "mujoco_geophys": float(row["observation_max_abs_mujoco_geophys"]),
        }
        row["reward_abs_diff"] = {
            "isaac_mujoco": abs(row["isaac"]["reward"] - row["mujoco"]["reward"]),
            "isaac_geophys": abs(row["isaac"]["reward"] - row["geophys"]["reward"]),
            "mujoco_geophys": abs(row["mujoco"]["reward"] - row["geophys"]["reward"]),
        }
        row["done_flags"] = {
            name: {
                "terminated": bool(row[name]["terminated"]),
                "truncated": bool(row[name]["truncated"]),
            }
            for name in ("isaac", "mujoco", "geophys")
        }
        combined.append(row)
    if args.platform_box:
        # The platform is a static body in GeoPhys but a world geom in the
        # MuJoCo oracle.  Compare the explicit support-contact boolean rather
        # than GeoPhys's analytic-ground row count.
        onset = {
            name: next(
                (r["tick"] for r in combined if bool(r[name].get("support_contact", False))),
                None,
            )
            for name in ("isaac", "mujoco", "geophys")
        }
    else:
        onset = {
            name: next((r["tick"] for r in combined if int(r[name]["contact_count" if name != "geophys" else "contact_rows"]) > 0), None)
            for name in ("isaac", "mujoco", "geophys")
        }
    onset_matches = len(set(onset.values())) == 1
    if not onset_matches and not args.allow_contact_onset_mismatch:
        raise AssertionError(f"contact onset mismatch across engines: {onset}")
    if max(max(r["slot0_isolation"].values()) for r in combined) > 1.0e-6:
        raise AssertionError("GeoPhys B=1/B=2 slot-0 contact isolation failed")
    report = {
        "schema": "task-env-go2-three-contact-oracle-report-v1",
        "interpretation": "measured three-engine contact envelope; not bitwise contact parity",
        "isaac_artifact": str(args.isaac_json),
        "backend": args.backend,
        "root_z": float(args.root_z),
        "steps": int(args.steps),
        "contact_onset_tick": onset,
        "contact_onset_matches": onset_matches,
        "diagnostic_only": bool(args.allow_contact_onset_mismatch and not onset_matches),
        "geophys_profile": str(args.profile),
        "rigid_solver_backend": str(args.rigid_solver_backend),
        "platform_box": bool(args.platform_box),
        "isolation_batch": 1 if args.platform_box else 2,
        "reward_threshold": {
            "threshold": 0.01,
            "post_contact_ticks_gt_threshold": {
                name: [
                    int(row["tick"])
                    for row in combined
                    if onset[name] is not None
                    and int(row["tick"]) >= int(onset[name])
                    and float(row[name]["reward"]) > 0.01
                ]
                for name in ("isaac", "mujoco", "geophys")
            },
            "max_reward": {
                name: max(float(row[name]["reward"]) for row in combined)
                for name in ("isaac", "mujoco", "geophys")
            },
        },
        "resource_summary_b1": resource1,
        "resource_summary_b2": resource2,
        "rows": combined,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "contact_onset_tick": onset,
        "max_slot0_qpos": max(r["slot0_isolation"]["qpos_max_abs"] for r in combined),
        "max_slot0_qvel": max(r["slot0_isolation"]["qvel_max_abs"] for r in combined),
    }, indent=2))


if __name__ == "__main__":
    main()
