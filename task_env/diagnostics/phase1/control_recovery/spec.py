"""Independent R1 evaluation; prior locked inputs remain immutable."""
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib, json
from pathlib import Path
import yaml
from ..control.spec import context, free_space_source, verify as verify_old, identities
from ....controllers.canonical import ProductionCanonicalPandaController

OLD = Path('workspace/qualification/phase1/p1_5_expert/control_oracle.yaml')


def specification():
    old, old_lock = verify_old(OLD)
    artifact, source, model, _ = context()
    controller = ProductionCanonicalPandaController.from_source(artifact, source)
    cfg = source.config.robot.gripper
    dt = Decimal(str(artifact.timebase.control_dt))
    opening = Decimal(str(source.config.action.gripper_opening_range_m))
    ceil = lambda value: int(value.to_integral_value(rounding=ROUND_CEILING))
    rate = ceil(opening / Decimal(str(cfg.opening_step_m)))
    force = ceil(opening / Decimal(str(cfg.force_adjust_step_m)))
    margin = ceil(Decimal('0.2') / dt)
    hold = Decimal('1.0') / dt
    if hold != hold.to_integral_value():
        raise ValueError('settling duration is not an integral number of control boundaries')
    return {'schema': 'p1_5-r1-prerequisite-oracle-v0',
        'old_oracle_sha256': old_lock['sha256'], 'artifact_hash': artifact.identity_hash,
        'source_sha256': model.source_sha256,
        'free_space_source_sha256': hashlib.sha256(free_space_source(source).scene_source.xml.encode()).hexdigest(),
        'controller_identity': controller.identity, 'gripper_profile': asdict(cfg),
        'action_physical_parameters': {'opening_range_m': float(opening),
            'stiffness_N_per_m': source.config.action.gripper_position_stiffness_N_per_m},
        'control_dt': float(dt), 'control_substeps': artifact.timebase.control_substeps,
        'samples': old['samples'], 'C1_A': old['C1_A'], 'C1_B': old['C1_B'],
        'C1_B_goal_world': old['C1_B_goal_world'], 'bounds': old['bounds'],
        'gripper': {'open_ticks': rate + margin, 'close_ticks': max(rate, force) + margin,
            'reopen_ticks': rate + margin, 'rate_ticks': rate, 'force_adjust_ticks': force,
            'dynamics_margin_s': .2, 'dynamics_margin_ticks': margin,
            'rationale': 'Full range/rate increment and full range/force adjustment increment, whichever longer, plus common 0.2 second dynamics margin. No provider-fitted horizon.'},
        'C1_B_evaluation': {'version': 'moving40_then_settled_r1', 'movement_ticks': len(old['C1_B']),
            'hold_duration_s': 1., 'hold_ticks': int(hold),
            'rationale': 'One round second of unchanged final complete target after the unchanged archival movement; explicit settled tracking rather than moving-end transient error.'},
        'C2': 'not_scheduled_in_R1', 'qualification_claim': False}


def prepare(root):
    root = Path(root)
    path = root / 'control_oracle_r1.yaml'
    lock_path = root / 'control_oracle_r1_lock.json'
    if path.exists() or lock_path.exists():
        raise ValueError('Evidence collision; preserve existing lock')
    spec = specification()
    path.write_text(yaml.safe_dump(json.loads(json.dumps(spec)), sort_keys=False))
    lock = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'timestamp': datetime.now(timezone.utc).isoformat(), 'provenance': identities()}
    lock_path.write_text(json.dumps(lock, indent=2) + '\n')
    return lock


def verify(path):
    path = Path(path)
    lock = json.loads((path.parent / 'control_oracle_r1_lock.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != lock['sha256']:
        raise ValueError('R1 oracle lock changed')
    spec = yaml.safe_load(path.read_text())
    if spec != json.loads(json.dumps(specification())):
        raise ValueError('R1 evaluation inputs changed after lock')
    return spec, lock
