#!/usr/bin/env python3
"""Check Skill structure, local Markdown references and explicit root source paths.

This is a static drift detector; it cannot establish runtime capability or qualification.
Run from a repository checkout with PyYAML available in the dependency environment.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import yaml


def check(skill, root):
    errors = []
    entry = skill / 'SKILL.md'
    text = entry.read_text()
    parts = text.split('---', 2)
    if len(parts) != 3 or parts[0].strip():
        return ['SKILL.md must begin with YAML frontmatter']
    meta = yaml.safe_load(parts[1])
    if not isinstance(meta, dict):
        return ['frontmatter must be a mapping']
    name = meta.get('name', '')
    if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9-]{1,64}', name) or name != skill.name:
        errors.append('invalid name or folder mismatch')
    if not isinstance(meta.get('description'), str) or not meta['description'].strip():
        errors.append('missing description')
    for path in skill.rglob('*.md'):
        body = path.read_text()
        for link in re.findall(r'\]\(([^)]+)\)', body):
            target = link.split('#', 1)[0]
            if target and '://' not in target and not (path.parent / target).exists():
                errors.append(f'{path.relative_to(root)}: missing link {target}')
        for target in re.findall(r'`((?:task_env|docs|examples|\.agents)/[^`\s]+)`', body):
            if not (root / target).exists():
                errors.append(f'{path.relative_to(root)}: missing source path {target}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill', type=Path)
    args = parser.parse_args()
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
    errors = check(args.skill.resolve(), root)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f'PASS {args.skill.name}: metadata, local links, explicit source paths (static only)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
