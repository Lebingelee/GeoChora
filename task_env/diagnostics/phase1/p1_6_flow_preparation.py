"""Flow preparation only: strict datasets, one CUDA update, CPU inference."""
from pathlib import Path
import argparse
import traceback
from .flow_preparation.prepare import run,write


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('workspace/qualification/phase1/p1_6_flow_preparation'))
    parser.add_argument("--output", type=Path, help="New report path for a preserved preparation attempt")
    args=parser.parse_args()
    output = args.output or args.root/"preparation_report.json"
    if output.exists():
        raise FileExistsError('refusing preparation Evidence collision')
    try:
        result=run(args.root)
    except Exception as error:
        boundary='canonical_flow_dataset'
        if (args.root/'dataset_report.json').exists():
            boundary='cuda_one_batch_smoke'
        if (args.root/'cuda_smoke/report.json').exists():
            boundary='smoke_checkpoint_or_cpu_inference'
        result={'status':'partial_with_localized_failure','first_boundary':boundary,
                'error':str(error),'traceback':traceback.format_exc(),
                'full_training_executed':False,'policy_rollout_executed':False}
    write(output,result)
    print(result['status'])
    if 'error' in result:
        raise SystemExit(1)


if __name__=='__main__':main()
