"""Check goal coverage and explicitly labelled source endpoint examples."""
from dataclasses import replace
from pathlib import Path
import argparse
import hashlib
import json
from catalog_query import core_context
from harness_spec_schema import CandidateSpec,CheckFinding,CheckReport
from harness_compiler import compile_candidate,CompilationRejected,evaluate_lift


def check_semantics(spec,catalog,examples_path,*,provider='mujoco'):
    from task_env.artifacts import CanonicalStateView,PoseWorld
    path=Path(examples_path).resolve()
    examples=json.loads(path.read_text())
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if examples.get('schema_version')!='harness-semantic-examples-v0' or type(examples.get('synthetic')) is not bool:
        raise ValueError('semantic examples schema and synthetic provenance required')
    compiled=compile_candidate(spec,catalog,provider=provider)
    findings=[];rows=[]
    evidence={'examples_ref':str(path),'examples_sha256':digest,'synthetic':examples['synthetic']}
    if examples['goal_predicate']!='lift_height':
        findings.append(CheckFinding('goal_coverage','semantic_mismatch','harness','template',spec.template,
            examples['goal_predicate'],evidence,'Provide a matching semantic template; do not map On/In to lift.'))
    else:
        if not examples.get('cases'):raise ValueError('at least one endpoint example required')
        expected_values=[]
        for case in examples['cases']:
            if type(case['expected_success']) is not bool:raise ValueError('expected_success must be bool')
            expected_values.append(case['expected_success'])
            joints={'panda-v1/finger_joint1':.02,'panda-v1/finger_joint2':.02}
            position=(.6,0.,float(case['cube_world_z_m']))
            state=CanonicalStateView('canonical-state-v0','SI_right_handed_z_up_wxyz',0,0.,joints,
                {key:0. for key in joints},{'cube-v1':PoseWorld(position,(1.,0.,0.,0.)),
                'panda-v1/ee':PoseWorld(position,(1.,0.,0.,0.))})
            actual=bool(evaluate_lift(state,compiled.artifact.semantics).success)
            rows.append({'name':case['name'],'actual':actual,'expected':case['expected_success'],
                'cube_world_z_m':case['cube_world_z_m']})
            if actual!=case['expected_success']:
                findings.append(CheckFinding('endpoint_success','semantic_mismatch','task_local','success_config.lift_height_m',
                    {'actual':actual,'threshold':spec.success_config['lift_height_m']},case['expected_success'],
                    {**evidence,'case':case['name'],'cube_world_z_m':case['cube_world_z_m']},
                    'Reconcile the declared threshold with the upstream goal and examples.'))
        if set(expected_values)!={False,True}:raise ValueError('both negative and positive examples required')
    return CheckReport(spec.spec_sha256(),compiled.artifact_hash,catalog['core_commit'],catalog['core_dirty'],
        'semantic_check','fail' if findings else 'pass',findings,
        details={**evidence,'provider':provider,'cases':rows,'scope':'Synthetic examples exercise the checker; not real LIBERO demo validation.' if examples['synthetic'] else 'Supplied endpoint examples only.'})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('core-repo','spec','catalog','examples','output'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--provider',default='mujoco')
    args=parser.parse_args();ctx=core_context(args.core_repo)
    spec=None
    try:
        spec=CandidateSpec.load(args.spec)
        catalog=json.loads(args.catalog.read_text())
        report=check_semantics(spec,catalog,args.examples,provider=args.provider)
    except CompilationRejected as error:report=replace(error.report,tool='semantic_check',details={'origin_tool':'harness_compiler'})
    except Exception as error:
        report=CheckReport(spec.spec_sha256() if spec else None,None,ctx['core_commit'],ctx['core_dirty'],'semantic_check','error',
            [CheckFinding('semantic_inputs','execution_fault','harness','',str(error),'valid and attributable examples',{})])
    report.save(args.output);print(report.to_json());return {'pass':0,'fail':1,'error':2}[report.status]

if __name__=='__main__':raise SystemExit(main())
