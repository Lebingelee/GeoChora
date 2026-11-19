"""Prepare independent terminal review from an external task and evidence bundle.

Run from the repository root with PYTHONPATH=. and validation requirements.
No model is called by this command. Use validation.terminal.source_run run next.
"""
import argparse
import json
from pathlib import Path

from validation.inputs import load_task_source
from validation.terminal.reviews import prepare_source_review
from validation.terminal.source_run import prepare_source_run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', required=True, type=Path)
    parser.add_argument('--resource-root', type=Path)
    parser.add_argument('--evidence-bundle', required=True, type=Path)
    parser.add_argument('--artifact-root', required=True, type=Path)
    parser.add_argument('--judge-profile', required=True, type=Path)
    parser.add_argument('--verifier-profile', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--evidence-mode', choices=('full', 'adaptive', 'catalogued_full'), default='full')
    parser.add_argument('--max-text-characters', type=int,
                        help='explicit input text budget; oversized evidence is rejected without truncation')
    args = parser.parse_args(argv)
    source = load_task_source(args.task, resource_root=args.resource_root)
    bundle = json.loads(args.evidence_bundle.read_text(encoding='utf-8'))
    pointers = ['/task/prompt', '/task/truth/acceptance']
    pointers.extend('/dependencies/' + key for key in source['dependencies'])
    request = prepare_source_review(source, bundle['endpoint'], required_source_pointers=pointers,
        model_profile=json.loads(args.judge_profile.read_text(encoding='utf-8')), evidence=bundle['evidence'])
    result = prepare_source_run(request, args.artifact_root, args.output,
        verification_model_profile=json.loads(args.verifier_profile.read_text(encoding='utf-8')),
        evidence_mode=args.evidence_mode, max_text_characters=args.max_text_characters)
    print(json.dumps({'status': 'prepared_no_model_call', 'run': str(args.output / 'run.json'),
                      'identity': result['identity']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
