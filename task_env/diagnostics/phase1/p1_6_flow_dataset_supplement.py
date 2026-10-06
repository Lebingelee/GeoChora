"""Bounded success-conditioned expert corpus supplement; no full-training route."""
import argparse
import json
import shutil
from pathlib import Path
from .flow_preparation.supplement import verify_prior, freeze, collect, finalize, verify_preserved
from .flow_preparation.prepare import run, write


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('workspace/qualification/phase1/p1_6_flow_preparation'))
    parser.add_argument('--stage',choices=['collection','checks','smoke'],required=True)
    args=parser.parse_args();root=args.root
    if args.stage=='collection':
        spec,lock,original=verify_prior(root)
        freeze(root,spec,lock)
        additions=collect(root,original)
        manifest=finalize(root,original,additions)
        print('ready_for_remote_review' if manifest['full_training_authorized'] else 'partial_with_localized_failure:expert_dataset_feasibility')
    elif args.stage=='checks':
        from .flow_preparation.supplement_checks import run as checks
        print(checks(root))
    else:
        work=root/'supplement/selected_preparation'
        if work.exists():raise FileExistsError('selected corpus smoke already started; no automatic retry')
        work.mkdir(parents=True)
        regression=work/'regression/preparation_checks';regression.mkdir(parents=True)
        shutil.copyfile(root/'supplement/regression/flow_checks/report.json',regression/'report.json')
        result=run(work,manifest_path=root/'training_dataset_manifest_v1.json')
        if not verify_preserved(root):raise ValueError('prior Evidence changed')
        write(work/'report.json',result)
        shutil.copyfile(work/'dataset_report.json',root/'selected_dataset_report.json')
        shutil.move(str(work/'cuda_smoke'),str(root/'selected_cuda_smoke'))
        shutil.move(str(work/'cpu_smoke'),str(root/'selected_cpu_smoke'))
        print(result['status'])


if __name__=='__main__':main()
