"""Associate one closed recording, independent readback, and same-run report.

This is an offline identity check, not a simulator or a Solution evaluator.
The caller remains the owner of its completion report. Missing completion in
the recording is reported as missing, not filled from the caller report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def caller_report(path: Path, recording: Path) -> dict:
    matches = []
    for line in path.read_text(errors='replace').splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and str(recording) in (
                value.get('output'), value.get('recording_path')):
            matches.append(value)
    require(len(matches) == 1, 'expected one caller report for this recording')
    return matches[0]


def associate(recording: Path, readback: Path, log: Path, supervisor: Path) -> dict:
    recording, readback, log, supervisor = (
        Path(p).resolve(strict=True) for p in (recording, readback, log, supervisor)
    )
    evidence = json.loads(readback.read_text())
    receipt = json.loads(supervisor.read_text())
    report = caller_report(log, recording)
    actual_hash = sha256(recording)
    require(evidence.get('status') == 'PASS' and evidence.get('sha256') == actual_hash,
            'independent readback does not match the closed recording')
    require(evidence.get('bytes') == recording.stat().st_size, 'readback byte count differs')
    require(Path(evidence['path']).resolve() == recording, 'readback path differs')
    require(receipt.get('recording_exists') is True, 'supervisor did not find recording')
    argv = receipt['argv']
    output_flags = [flag for flag in ('--output', '--recording') if flag in argv]
    require(len(output_flags) == 1 and argv.count(output_flags[0]) == 1 and
            argv[argv.index(output_flags[0]) + 1] == str(recording),
            'supervisor command does not identify this recording')
    require(argv.count('--seed') == 1 and argv.count('--provider') == 1 and
            int(argv[argv.index('--seed') + 1]) == report['seed'] and
            argv[argv.index('--provider') + 1] == report['provider'],
            'supervisor command and caller seed/provider differ')
    episode = report['episode']
    transitions = evidence['transitions']
    require(evidence['boundaries'] == transitions + 1 == episode['transitions'] + 1,
            'caller and readback transition counts differ')
    require(evidence['task_success_final_recomputed'] == episode['task_success'],
            'caller and independent task predicate differ')
    schema = evidence['schema']
    completion_in_record = None
    completion_in_record_status = 'NOT_CHECKED'
    episode_id = None
    if schema == 'task-env-h5/v3':
        from task_env.recorders import load_structured_control_records_h5

        data = load_structured_control_records_h5(recording)
        outcome = data['outcome']
        profile = data['env_meta']['reference_profile']
        finish = report['recording_finalize']
        episode_id = outcome.episode_id
        require(finish['outcome']['episode_id'] == episode_id,
                'caller and recording episode identities differ')
        require(data['transition_count'] == transitions and
                data['observation_count'] == evidence['boundaries'], 'v3 counts differ')
        require(report['provider'] == profile['provider'] and
                report['controller_identity'] == profile['controller_identity'] and
                report['solution_identity'] == profile['solution_identity'] and
                report['provider_materialization_id'] == profile['materialization_identity'],
                'caller and recording provider/controller/Solution identities differ')
        require(profile['requested_reset_sample']['task_seed'] == report['seed'] and
                report['identity']['task_artifact_sha256'] == profile['task_artifact_identity_hash'] and
                report['recording']['sha256'] == actual_hash,
                'v3 reset seed, task identity, or reported recording hash differs')
        require(outcome.task_success == episode['task_success'] and
                outcome.truncated == episode['truncated'], 'v3 outcome differs')
        completion_in_record = outcome.solution_completed
        completion_in_record_status = 'ABSENT' if completion_in_record is None else 'PRESENT'
    else:
        saved = report['recording']
        require(saved['transitions'] == transitions and saved['boundaries'] == evidence['boundaries'],
                'caller recording counts differ')
        require(saved['controller_identity'] == evidence['controller_identity'] and
                saved['expert_identity'] == evidence['solution_identity'] and
                report['provider'] == evidence['provider'], 'caller and readback identities differ')
        require(saved['task_artifact_sha256'] == report['identity']['task_artifact_sha256'] and
                saved['source_revision'] == evidence['source_revision'],
                'caller task or recorded source revision differs')
    return {
        'status': 'PASS', 'recording': str(recording), 'recording_sha256': actual_hash,
        'independent_readback_sha256': sha256(readback), 'caller_log_sha256': sha256(log),
        'supervisor_receipt_sha256': sha256(supervisor), 'episode_id': episode_id,
        'association_code_sha256': sha256(Path(__file__).resolve()),
        'schema': schema, 'transitions': transitions, 'boundaries': evidence['boundaries'],
        'argv': argv, 'seed': report['seed'], 'provider': report['provider'],
        'task_success_recomputed': evidence['task_success_final_recomputed'],
        'completion_in_record': completion_in_record,
        'completion_in_record_status': completion_in_record_status,
        'solution_done_from_caller': episode['solution_done'],
        'solution_failed_from_caller': episode['solution_failed'],
        'completion_eligible_from_caller': episode['completion_eligible'],
        'close_succeeded_from_caller': report['close_succeeded'],
        'process_exit': receipt['exit_code'],
        'limitations': ('Association is not a physical run, independent Solution execution, '
                        'or proof of SDK log completion. Caller completion and close remain '
                        'same-run caller facts; no absent H5 field is reconstructed.'),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('recording', 'readback', 'log', 'supervisor'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(associate(args.recording, args.readback, args.log, args.supervisor),
                     ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
