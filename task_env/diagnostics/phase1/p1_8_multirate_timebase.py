"""Isolated P1.8-D worker: unchanged expert or within-profile D0/D1/D2."""
import argparse
import json
from pathlib import Path
from .multirate.expert import run as expert
from .multirate.replay import d0,run


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--profile',choices=['TB-500','TB-100','TB-50'],required=True);p.add_argument('--seed',type=int,choices=[31,73],required=True)
    p.add_argument('--route',choices=['expert','D0','D1','D2'],required=True);p.add_argument('--provider',choices=['geophys','mujoco','sapien','genesis'],default='geophys')
    a=p.parse_args()
    if a.route=='expert':
        if a.provider!='geophys':raise ValueError('Gate E source provider must be GeoPhys')
        report=expert(a.root,a.profile,a.seed);passed=report['success']
    elif a.route=='D0':report=d0(a.root,a.profile,a.seed);passed=report['pass']
    else:report=run(a.root,a.profile,a.seed,a.provider,a.route);passed=report['execution_valid'] and report['task_valid']
    print(json.dumps(report),flush=True);return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
