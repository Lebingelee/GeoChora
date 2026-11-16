"""Render a construction ledger as a Markdown summary for people.

Loads the ledger through ``construction_ledger.load`` (so every hash is
revalidated) and writes: state and remaining budget; one section per round with
its spec change, the finding the revision cited, the reason, and each report's
result; and the recorded issues with their resolution status.

Read-only and derived. The ledger and its hashed evidence remain the record;
this file is not evidence and must not be cited in a revision or Judge package.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import construction_ledger
from harness_spec_schema import CheckReport


def _short(value):
    return '—' if not value else str(value)[:12]


def _text(value):
    """Ledger strings are untrusted here: keep them on one line and inert as Markdown/HTML."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = ' '.join(text.split()).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'([\\`*_\[\]#|~])', r'\\\1', text)


def _code(value):
    """Inline code span; a backtick or line break would end the span early."""
    return '`' + ' '.join(str(value).replace('`', "'").split()) + '`'


def _report_line(ref):
    report = CheckReport.from_dict(construction_ledger.read_ref(ref))
    line = f'- {_code(report.tool)}: **{report.status}**, {len(report.findings)} finding(s)'
    totals = report.details.get('totals')
    if report.tool == 'feasibility_probe' and isinstance(totals, dict):
        line += ' — ' + ', '.join(f'{_text(key)} {_text(totals[key])}' for key in totals)
    return line, report


def _revision_lines(revision):
    if not revision:
        return ['Initial candidate.']
    if revision.get('kind') == 'owner_repair':
        receipt = construction_ledger.read_ref(revision['repair_receipt'])
        lines = [f"Owner-repair continuation of round {_text(revision.get('parent_round'))} "
                 f"(receipt `{_short(revision['repair_receipt']['sha256'])}`, "
                 f"repair commit `{_short(receipt.get('repair_commit'))}`).",
                 f"Reason: {_text(receipt.get('reason'))}"]
        if receipt.get('asset_change') is not None:
            lines.append(f"Asset change: {_text(receipt['asset_change'])}")
        return lines
    lines = []
    cited = revision.get('report')
    if cited is not None:
        finding = CheckReport.from_dict(construction_ledger.read_ref(cited)).findings[revision['finding_index']]
        lines.append(f"Cites finding {revision['finding_index']} of report `{_short(cited['sha256'])}`: "
                     f"{_code(finding.check)} ({finding.category}, {finding.locality}).")
    lines.append(f"Reason: {_text(revision.get('reason'))}")
    if revision.get('diagnostics'):
        lines.append(f"Diagnostic probes cited: {len(revision['diagnostics'])}.")
    if revision.get('diff'):
        lines += ['', '| Spec field | Before | After |', '|---|---|---|']
        lines += [f"| {_code(row['path'])} | {_text(row['before'])} | {_text(row['after'])} |" for row in revision['diff']]
    return lines


def render(ledger):
    value = construction_ledger.load(ledger)
    rounds = value['rounds']
    unresolved = construction_ledger.unresolved_issue_indices(value)
    lines = [
        f"# Construction ledger: {_code(value['task_id'])}", '',
        '> Derived, read-only view. The ledger and its hashed evidence are the record; do not cite this file.', '',
        f"- State: **{value['state']}**" + (f" (stop reason: {_code(value['stop_reason'])})" if value.get('stop_reason') else ''),
        f"- Rounds used: {len(rounds)} of {value['max_rounds']}",
        f"- Provider: {_text(value['provider'])}",
        f"- Issues: {len(value['open_issues'])} recorded, {len(unresolved)} without a recorded resolution",
        f"- Human Judge decision: {_text(value.get('judge_decision') or 'none')}", '',
    ]
    issue_round = {}
    for round_ in rounds:
        context = round_.get('context') or {}
        lines += [f"## Round {round_['number']}: {round_['status']}", '',
                  f"Spec `{_short(round_['spec_sha256'])}`, Core `{_short(context.get('core_commit', value['core_commit']))}`, "
                  f"artifact `{_short(round_.get('artifact_hash'))}`.", '']
        lines += _revision_lines(round_.get('revision')) + ['']
        if not round_.get('reports'):
            lines += ['No reports registered yet.', '']
            continue
        for ref in round_['reports']:
            line, report = _report_line(ref)
            lines.append(line)
            for index, finding in enumerate(report.findings):
                lines.append(f'  - [{index}] {_code(finding.check)} ({finding.category}, {finding.locality})'
                             + (f' at {_code(finding.spec_path)}' if finding.spec_path else ''))
            for index, issue in enumerate(value['open_issues']):
                if issue['report'] == ref:
                    issue_round[index] = round_['number']
        lines.append('')
    lines += ['## Issues', '']
    if not value['open_issues']:
        lines.append('None recorded.')
    else:
        events = {event['issue_index']: event for event in value.get('issue_events', [])}
        lines += ['| # | Round | Check | Category | Locality | Resolution |', '|---|---|---|---|---|---|']
        for index, issue in enumerate(value['open_issues']):
            finding = CheckReport.from_dict(construction_ledger.read_ref(issue['report'])).findings[issue['finding_index']]
            event = events.get(index)
            status = 'none recorded' if event is None else f"{event['disposition']} by {event['owner']} (owner claim)"
            lines.append(f"| {index} | {issue_round.get(index, '—')} | {_code(finding.check).replace('|', '/')} | {finding.category} | "
                         f"{finding.locality} | {status} |")
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--output', type=Path, help='new Markdown file; printed to stdout when omitted')
    args = parser.parse_args(argv)
    try:
        text = render(args.ledger)
        if args.output is None:
            print(text, end='')
        else:
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(text)
            print(json.dumps({'status': 'written', 'output': str(args.output)}))
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(json.dumps({'status': 'error', 'error': f'{type(error).__name__}: {error}'}))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
