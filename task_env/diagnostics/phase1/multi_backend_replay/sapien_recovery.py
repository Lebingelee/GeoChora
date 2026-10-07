"""P1.8 representation-aware prerequisite; approved P1.3 evaluator unchanged."""
import argparse
import hashlib
import json
from pathlib import Path
from .sapien_probe import SapienProbe
from ..conformance.lock import verify
from ..conformance.evaluate import evaluate
from ....runtime.sessions.representation import calibrate_timestep


def run(oracle, probe, output):
    output=Path(output)
    if output.exists():raise FileExistsError('recovery Evidence collision')
    spec=verify(oracle)[0]['probes'][probe]
    adapter=SapienProbe(spec)
    try:
        gate=calibrate_timestep(adapter.scene,spec['recipe']['timebase']['physics_dt'])
        facts=adapter.facts();series=[adapter.read()]
        for _ in range(spec['recipe']['timebase']['steps']):adapter.step();series.append(adapter.read())
        strict=evaluate(spec,series,facts)
        physical=all(v for k,v in strict['checks'].items() if k!='native_dt')
        report={'provider':'sapien','probe':probe,'fixture_hash':spec['fixture_hash'],
            'oracle_sha256':hashlib.sha256(Path(oracle).read_bytes()).hexdigest(),
            'representation_gate':gate,'strict_p1_3_evaluation':strict,'physical_geometric_checks_pass':physical,
            'status':'pass' if gate['pass'] and physical else 'fail','facts':facts,'series':series}
    finally:
        adapter.close();verify(oracle)
    report['closed']=True;output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--oracle',required=True);p.add_argument('--probe',required=True)
    p.add_argument('--output',required=True);a=p.parse_args();r=run(a.oracle,a.probe,a.output)
    print(a.probe,r['status'],r['representation_gate']);raise SystemExit(0 if r['status']=='pass' else 1)
