#!/usr/bin/env python3
"""Validate active repository docs and an exact tag-backed consolidation inventory.

Checks Markdown local targets/anchors, tag-backed immutable URLs, JSON, protected bytes,
file counts, frozen refs and documentation-only scope. Run at repo root after staging.
External consumers and runtime capabilities are outside this static check.
"""
from pathlib import Path
import ast
import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
from urllib.parse import unquote


def git(*args):
    return subprocess.check_output(['git', *args])


def body(text):
    return re.sub(r'(?ms)^\s*(```|~~~).*?^\s*\1[^\n]*$', '', text)


def anchors(text):
    counts, result = {}, set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', text))
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', body(text), re.M):
        heading = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', heading).lower()
        slug = ''.join(c for c in heading if c in '-_ ' or unicodedata.category(c)[0] in 'LN').replace(' ', '-')
        n = counts.get(slug, 0)
        result.add(slug + (f'-{n}' if n else ''))
        counts[slug] = n + 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', default='docs/maintenance/consolidation-inventory.json')
    args = parser.parse_args()
    root = Path(git('rev-parse', '--show-toplevel').decode().strip())
    files = git('ls-files', '-z').decode().strip('\0').split('\0')
    docs = [p for p in files if p.startswith('docs/') and (root / p).is_file()]
    task = [p for p in docs if p.startswith('docs/module/task_env/')]
    errors, urls = [], set()
    inv = json.loads((root / args.inventory).read_text())
    for name, tag in inv['baseline']['tag_objects'].items():
        if git('rev-parse', 'refs/tags/' + name).decode().strip() != tag:
            errors.append('frozen tag changed: ' + name)
    for record in inv['records']:
        original = record['original_path']
        frozen = git('show', 'refs/tags/v1.1.0:' + original)
        if hashlib.sha256(frozen).hexdigest() != record['sha256']:
            errors.append('immutable recovery mismatch: ' + original)
        if record['proposed_disposition'] == 'PRESERVE_MACHINE_EVIDENCE':
            path = root / original
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
                errors.append('protected data mismatch: ' + original)
        elif record['proposed_disposition'] == 'KEEP_CANONICAL':
            current = (root / original).read_bytes()
            if original in inv['reference_migration']['v1_0_navigation_only']:
                for old in ('phase1_followups.md', 'phase2_plan.md'):
                    frozen = frozen.replace(('](../../roadmap/' + old + ')').encode(),
                        ('](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/roadmap/' + old + ')').encode())
            if current != frozen:
                errors.append('v1.0 changed beyond navigation migration: ' + original)
        elif record['proposed_disposition'] == 'HISTORICAL_TAG_ONLY' and (root / original).exists():
            errors.append('historical file remains active: ' + original)
        destination = record['destination']
        if '://' not in destination and not (root / destination).is_file():
            errors.append('missing merge destination: ' + destination)
    for p in docs:
        if p.endswith('.json'):
            try:
                json.loads((root / p).read_text())
            except (ValueError, UnicodeDecodeError) as exc:
                errors.append(f'{p}: JSON {exc}')
    # Include every root-owned maintained Markdown page, not only the shortened docs tree.
    for name in files:
        path = root / name
        if not name.endswith('.md') or not path.is_file():
            continue
        text = body(path.read_text())
        for raw in re.findall(r'\]\(([^)\n]+)\)', text):
            target = raw.strip('<>')
            if '://' in target:
                urls.add(target)
                m = re.match(r'https://github.com/Lebingelee/GeoChora/(blob|tree)/(v1\.[01]\.0)/([^#]+)(?:#(.*))?$', target)
                if m:
                    kind, ref, rel, anchor = m.groups()
                    rel = unquote(rel)
                    try:
                        data = git('show', 'refs/tags/' + ref + ':' + rel)
                        if anchor and rel.endswith('.md') and unquote(anchor) not in anchors(data.decode()):
                            errors.append(f'{name}: frozen anchor missing {target}')
                    except subprocess.CalledProcessError:
                        errors.append(f'{name}: frozen target missing {target}')
                continue
            if target.startswith(('mailto:', 'data:')):
                continue
            rel, _, anchor = unquote(target).partition('#')
            rel = re.sub(r':\d+$', '', rel)
            dest = (path.parent / rel).resolve() if rel else path
            if not dest.exists():
                errors.append(f'{name}: missing {target}')
            elif anchor and dest.suffix == '.md' and anchor not in anchors(dest.read_text()):
                errors.append(f'{name}: anchor missing {target}')
    baseline_docs = {r['original_path'] for r in inv['records']}
    for name in files:
        path = root / name
        if not name.startswith('task_env/') or not name.endswith('.py') or not path.is_file():
            continue
        for node in ast.walk(ast.parse(path.read_text(), filename=name)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for ref in re.findall(r'docs/[A-Za-z0-9_./-]+\.(?:json|md)', node.value):
                    if ref in baseline_docs and not (root / ref).is_file():
                        errors.append(f'{name}:{node.lineno}: newly broken source documentation reference {ref}')
    counts = {'docs': len(docs), 'task_env': len(task), 'markdown': sum(p.endswith('.md') for p in docs),
              'task_env_markdown': sum(p.endswith('.md') for p in task),
              'machine_or_other': sum(not p.endswith('.md') for p in docs)}
    if counts['docs'] > inv['baseline']['limits']['docs'] or len(task) > inv['baseline']['limits']['task_env']:
        errors.append('count limit exceeded')
    # Runtime, tests, providers, Gitlinks and examples may not change in this doc-only project.
    for name in git('diff', '--name-only', '-z', inv['baseline']['commit']).decode().strip('\0').split('\0'):
        if not (name.endswith('.md') or name.startswith(('docs/', '.agents/skills/'))):
            errors.append('non-documentation change: ' + name)
    print(json.dumps({'counts': counts, 'immutable_urls_checked': len([u for u in urls if '/v1.1.0/' in u or '/v1.0.0/' in u]),
                      'errors': errors, 'scope': 'tracked root repository Markdown/JSON; immutable URLs verified against fetched annotated tags'}, ensure_ascii=False, indent=2))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
