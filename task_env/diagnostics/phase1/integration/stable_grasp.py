"""Independent opt-in 10N G0 entry; no imports from generated Evidence."""
import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from ..nutassembly_r5_architecture import tracking_worker as worker
from ....controllers.canonical.production_r3 import ProductionCanonicalPandaControllerR3
from ....controllers.canonical.gripper_execution import EqualRateGripperServo
from ....tasks.nut_assembly import stable_grasp_candidate

PROFILE = Path('task_env/tasks/nut_assembly/profiles/nutassembly-nominal-v2.json')
DYNAMIC = Path('task_env/tasks/nut_assembly/profiles/r5-controller-planner-reference.yaml')

class ExecutionController:
    def __init__(self, hold, rate, dt):
        self.hold = hold
        self.inner = EqualRateGripperServo(hold.controller, rate, dt)
    def __getattr__(self, name):
        return getattr(self.hold, name)
    def compute(self, *args):
        return self.hold.compute(*args)
    def inner_gripper_step(self, *args):
        return self.inner.inner_gripper_step(*args)


def context(hz, *, reference=False, skip_absolute_height_gate=False):
    if reference:
        raise ValueError('stable_grasp_reference was retired; restore v1.0.0 to replay that historical route')
    value = worker._context('NA-TB'+str(hz), PROFILE, DYNAMIC)
    source = value['source']
    source = replace(source, config=replace(source.config, robot=replace(source.config.robot,
        gripper=replace(source.config.robot.gripper, force_limit_N=10.))))
    value['source'] = source
    controller = ProductionCanonicalPandaControllerR3.from_source(value['artifact'], source, profile=value['dynamic_profile'])
    config = replace(value['solution_config'], grasp_offset=(0.,0.,.044895))
    module = stable_grasp_candidate
    holder = module.StableArmTargetHold(controller)
    solution_type = module.NutAssemblyStableGraspCandidate
    if skip_absolute_height_gate:
        from .height_gate_ablation import StableGraspWithoutHeightGate
        solution_type = StableGraspWithoutHeightGate
    solution = solution_type(config=config,
        control_dt=value['artifact'].timebase.control_dt, arm_hold=holder)
    # Match frozen reference identity recipe, intentionally distinct on extraction.
    controller.identity = hashlib.sha256(json.dumps({'R3_identity':controller.identity,
        'candidate_solution':solution.identity, 'force_limit_N':10.,
        'hold_wrapper_source':hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()},sort_keys=True).encode()).hexdigest()
    execution = ExecutionController(holder, hz, value['artifact'].timebase.control_dt)
    value.update(controller=execution,controller_identity=controller.identity,solution=solution,
        solution_config=config,solution_identity=solution.identity)
    value['recipe_identity'] = hashlib.sha256(json.dumps({'base_recipe':value['recipe_identity'],
        'candidate':solution.identity,'force':10.},sort_keys=True).encode()).hexdigest()
    return value


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--rate',type=int,choices=[500,100,50],required=True)
    p.add_argument('--provider',choices=['mujoco','geophys'],default='mujoco')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reference',action='store_true')
    p.add_argument('--skip-absolute-height-gate',action='store_true',
        help='Diagnostic only: keep measured stability, remove absolute expected-Z gate')
    args=p.parse_args()
    if args.reference:
        p.error('stable_grasp_reference was retired; restore v1.0.0 to replay that historical route')
    args.output.mkdir(parents=True,exist_ok=False)
    value=context(args.rate,reference=args.reference,
        skip_absolute_height_gate=args.skip_absolute_height_gate)
    worker.CLOSE_TIME_LIMIT_S=1.5
    report=worker.run_loaded(value,args.provider,args.output,'G0')
    report.update(force_limit_N=10.,fallback_enabled=False,forced_lift=False,
        solution_events=value['solution'].events,postclose_hold_s=.1,
        outer_rate_hz=args.rate,gripper_rate_hz=args.rate,reference=args.reference,
        development_candidate_only=True,full_task_qualified=False)
    report['absolute_height_gate_enabled'] = not args.skip_absolute_height_gate
    worker._write(args.output/'report.json',report)
    print(json.dumps({k:report.get(k) for k in ['pass','close_authorization','verify_lift_pass',
        'max_capture_position_drift_m','max_capture_rotation_drift_rad','failure_boundary','error']}),flush=True)
    if not report['pass']:raise SystemExit(1)

if __name__=='__main__':main()
