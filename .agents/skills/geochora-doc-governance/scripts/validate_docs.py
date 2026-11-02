#!/usr/bin/env python3
"""Validate current versioned docs or the explicitly frozen v1.1 consolidation baseline.

Current mode checks active Markdown links/anchors, JSON, versioned structure, the
per-file migration manifest, and stale documentation paths in maintained callers.
Historical mode checks the old inventory against its exact source, the frozen tag
objects and selected preserved evidence, plus the old doc-count/scope limits on
the retained v1.1.0 branch. Historical links are reported separately because
their source-relative paths may no longer exist in the current tree.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import posixpath
import re
import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import unquote


MIGRATION_PATH = "docs/module/task_env/v2.1.0/maintenance/migrations/document-migration-manifest.json"
INVENTORY_PATH = "docs/module/task_env/v1.1.0/maintenance/recovery/consolidation-inventory.json"
CURRENT_REQUIRED = [
    "docs/README.md",
    "docs/module/task_env/README.md",
    "docs/module/task_env/v2.1.0/README.md",
    "docs/module/task_env/v2.1.0/api/public-api.md",
    "docs/module/task_env/v2.1.0/api/configuration.md",
    "docs/module/task_env/v2.1.0/api/migration.md",
    "docs/module/task_env/v2.1.0/contracts/task-artifact.md",
    "docs/module/task_env/v2.1.0/contracts/runtime-and-providers.md",
    "docs/module/task_env/v2.1.0/contracts/recording-and-learning.md",
    "docs/module/task_env/v2.1.0/contracts/qualification.md",
    "docs/module/task_env/v2.1.0/guides/installation.md",
    "docs/module/task_env/v2.1.0/guides/quickstart.md",
    "docs/module/task_env/v2.1.0/guides/task-authoring.md",
    "docs/module/task_env/v2.1.0/capabilities/README.md",
    "docs/module/task_env/v2.1.0/capabilities/capability-matrix.json",
]
RELEASE_KIT = (
    "README.md",
    "CHANGELOG.md",
    "migration.md",
    "installation.md",
    "capabilities.md",
    "known-limitations.md",
    "third-party-assets.md",
    "release-manifest.json",
)
EXACT_POLICIES = {
    "PRESERVE_FROZEN_BODY_ORIGINALS",
    "PRESERVE_JSON_PROVENANCE",
    "RETAIN_RELEASE_BYTES",
}
NAVIGATION_POLICIES = {
    "FROZEN_FACTS_NAVIGATION_ONLY",
    "RETAIN_RELEASE_FACTS_NAVIGATION_ONLY",
}


def git(*args: str, text: bool = True) -> str | bytes:
    result = subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL)
    return result.decode("utf-8", errors="replace") if text else result


def show(ref: str, path: str) -> bytes:
    return git("show", f"{ref}:{path}", text=False)  # type: ignore[return-value]


def body(text: str) -> str:
    return re.sub(r"(?ms)^\s*(```|~~~).*?^\s*\1[^\n]*$", "", text)


def anchors(text: str) -> set[str]:
    counts: dict[str, int] = {}
    result = set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', text))
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", body(text), re.M):
        heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading).lower()
        slug = "".join(
            char
            for char in heading
            if char in "-_ " or unicodedata.category(char)[0] in "LN"
        ).replace(" ", "-")
        occurrence = counts.get(slug, 0)
        result.add(slug + (f"-{occurrence}" if occurrence else ""))
        counts[slug] = occurrence + 1
    return result


def repo_files(root: Path) -> list[str]:
    tracked = git("ls-files", "-z", text=False).decode().split("\0")
    untracked = git("ls-files", "--others", "--exclude-standard", "-z", text=False).decode().split("\0")
    return sorted({path for path in tracked + untracked if path and (root / path).is_file()})


def load_json(path: Path, errors: list[str]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            errors.append(f"{path}: top-level JSON value must be an object")
            return {}
        return value
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        errors.append(f"{path}: JSON {exc}")
        return {}


def migration_context(root: Path, errors: list[str]) -> tuple[dict, dict[str, dict]]:
    manifest = load_json(root / MIGRATION_PATH, errors)
    entries = manifest.get("entries", [])
    if not isinstance(entries, list):
        errors.append(f"{MIGRATION_PATH}: entries must be an array")
        return manifest, {}
    by_new: dict[str, dict] = {}
    old_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"{MIGRATION_PATH}: malformed entry")
            continue
        old_path, new_path = entry.get("old_path"), entry.get("new_path")
        if not isinstance(old_path, str) or not isinstance(new_path, str):
            errors.append(f"{MIGRATION_PATH}: entry lacks old_path/new_path")
            continue
        if new_path in by_new:
            errors.append(f"{MIGRATION_PATH}: duplicate new_path {new_path}")
        by_new[new_path] = entry
        old_paths.add(old_path)
        operation = entry.get("operation")
        source_ref = entry.get("source_ref")
        try:
            source = show(source_ref, old_path)
        except (subprocess.CalledProcessError, TypeError):
            errors.append(f"{MIGRATION_PATH}: source missing at {source_ref}:{old_path}")
            continue
        destination = root / new_path
        if operation not in {"MOVE", "MOVE_AFTER_DEVELOP_MERGE", "COPY_FROM_TAG", "RETAIN", "REFRESH", "REWRITE_VERSION_INDEX"}:
            errors.append(f"{MIGRATION_PATH}: unknown operation {operation!r} for {old_path}")
            continue
        if not destination.is_file():
            errors.append(f"{MIGRATION_PATH}: missing destination {new_path}")
            continue
        policy = entry.get("content_policy")
        if operation == "COPY_FROM_TAG" or policy in EXACT_POLICIES:
            if destination.read_bytes() != source:
                errors.append(f"{MIGRATION_PATH}: frozen bytes changed for {new_path}")
        elif policy in NAVIGATION_POLICIES and destination.suffix == ".md":
            old = re.sub(rb"(\]\()([^)]*)(\))", rb"\1<LINK>\3", source)
            new = re.sub(rb"(\]\()([^)]*)(\))", rb"\1<LINK>\3", destination.read_bytes())
            if old != new:
                errors.append(f"{MIGRATION_PATH}: non-navigation content changed for {new_path}")
    if len(entries) != 130:
        errors.append(f"{MIGRATION_PATH}: expected 130 mapped entries, found {len(entries)}")
    additions = manifest.get("additions", [])
    if len(additions) != 35:
        errors.append(f"{MIGRATION_PATH}: expected 35 additions, found {len(additions)}")
    for addition in additions:
        path = addition.get("new_path") if isinstance(addition, dict) else None
        if not path or not (root / path).is_file():
            errors.append(f"{MIGRATION_PATH}: missing added document {path!r}")
    manifest["_old_paths"] = old_paths
    manifest["_by_old"] = {
        entry["old_path"]: entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("old_path"), str)
    }
    return manifest, by_new


def check_protected_inputs(root: Path, manifest: dict, errors: list[str]) -> list[str]:
    protected = []
    primary = manifest.get("protected_local_input", {})
    if isinstance(primary, dict) and primary.get("path"):
        protected.append(primary)
    additional = manifest.get("additional_local_inputs", [])
    if isinstance(additional, list):
        protected.extend(item for item in additional if isinstance(item, dict))
    for item in protected:
        path = root / str(item.get("path", ""))
        expected = item.get("sha256")
        if not expected:
            errors.append(f"protected input has no recorded hash: {item.get('path')}")
            continue
        if not path.is_file():
            errors.append(f"protected local input missing: {item.get('path')}")
            continue
        data = path.read_bytes()
        if len(data) != item.get("bytes") or hashlib.sha256(data).hexdigest() != expected:
            errors.append(f"protected local input changed: {item.get('path')}")
    return [str(item.get("path")) for item in protected]


def parse_link_target(raw: str) -> tuple[str, str]:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(None, 1)[0] if target else ""
    target = unquote(target)
    target, _, anchor = target.partition("#")
    target = target.split("?", 1)[0]
    target = re.sub(r":\d+$", "", target)
    return target, unquote(anchor)


def source_link_exists(ref: str, source_path: str, rel: str, anchor: str) -> bool:
    if not rel:
        try:
            data = show(ref, source_path).decode("utf-8")
        except (subprocess.CalledProcessError, UnicodeDecodeError):
            return False
    else:
        target_path = posixpath.normpath(posixpath.join(posixpath.dirname(source_path), rel))
        try:
            data = show(ref, target_path).decode("utf-8")
        except (subprocess.CalledProcessError, UnicodeDecodeError):
            return False
    return not anchor or anchor in anchors(data)


def is_historical_path(path: str, entry: dict | None) -> bool:
    if any(part in path.split("/") for part in ("history", "originals", "recovery")):
        return True
    if path.startswith((
        "docs/releases/v1.0/",
        "docs/releases/v1.1/",
        "docs/module/task_env/v1.0.0/",
        "docs/module/task_env/v1.1.0/",
        "docs/module/task_env/v2.0.0/",
    )):
        return True
    return bool(entry and str(entry.get("source_ref", "")).startswith("refs/tags/"))


def check_markdown_links(root: Path, files: list[str], by_new: dict[str, dict], errors: list[str]) -> dict:
    historical_issues: list[str] = []
    external_count = 0
    untracked_evidence_refs: list[str] = []
    historical_issue_count = 0
    untracked_evidence_count = 0

    def report_historical(message: str) -> None:
        nonlocal historical_issue_count
        historical_issue_count += 1
        if len(historical_issues) < 50:
            historical_issues.append(message)

    def report_untracked(message: str) -> None:
        nonlocal untracked_evidence_count
        untracked_evidence_count += 1
        if len(untracked_evidence_refs) < 30:
            untracked_evidence_refs.append(message)
    for name in files:
        path = root / name
        if path.suffix.lower() != ".md" or name == "docs/maintenance/20261030_runtime_route_diagnostic_handoff.md":
            continue
        try:
            text = body(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        entry = by_new.get(name)
        historical = is_historical_path(name, entry)
        for raw in re.findall(r"\]\(([^)\n]+)\)", text):
            rel, anchor = parse_link_target(raw)
            if rel.startswith(("mailto:", "data:")):
                continue
            if "/workspace/" in ("/" + rel.lstrip("/")):
                report_untracked(f"{name}: ignored local evidence reference {raw}")
                continue
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", rel):
                external_count += 1
                match = re.match(
                    r"https://github\.com/[^/]+/[^/]+/(?:blob|tree)/(v1\.[01]\.0|v2\.0\.0)/([^#]+)$",
                    rel,
                )
                if match:
                    ref, frozen_path = match.groups()
                    try:
                        frozen = show(f"refs/tags/{ref}", frozen_path)
                        if anchor and frozen_path.endswith(".md") and anchor not in anchors(frozen.decode("utf-8")):
                            message = f"{name}: frozen anchor missing {raw}"
                            report_historical(message) if historical else errors.append(message)
                    except (subprocess.CalledProcessError, UnicodeDecodeError):
                        message = f"{name}: frozen target missing {raw}"
                        report_historical(message) if historical else errors.append(message)
                continue
            destination = (path.parent / rel).resolve() if rel else path.resolve()
            try:
                destination.relative_to(root.resolve())
                inside_root = True
            except ValueError:
                inside_root = False
            valid = inside_root and destination.exists()
            if valid and anchor and destination.suffix.lower() == ".md":
                try:
                    valid = anchor in anchors(destination.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError):
                    valid = False
            if valid:
                continue
            if historical and entry:
                ref = entry.get("source_ref")
                old_path = entry.get("old_path")
                if isinstance(ref, str) and isinstance(old_path, str) and source_link_exists(ref, old_path, rel, anchor):
                    continue
                report_historical(f"{name}: source-relative link unresolved: {raw}")
            elif historical:
                report_historical(f"{name}: historical link unresolved: {raw}")
            else:
                errors.append(f"{name}: missing target/anchor {raw}")
    return {
        "external_links_seen": external_count,
        "historical_link_issue_count": historical_issue_count,
        "historical_link_issues": historical_issues,
        "ignored_workspace_reference_count": untracked_evidence_count,
        "ignored_workspace_reference_examples": untracked_evidence_refs,
    }


def current_paths(root: Path, files: list[str], manifest: dict, errors: list[str]) -> dict:
    for name in CURRENT_REQUIRED:
        if not (root / name).is_file():
            errors.append(f"missing required current document: {name}")
    for version in ("v2.0.0", "v2.1.0"):
        for item in RELEASE_KIT:
            name = f"docs/releases/{version}/{item}"
            if not (root / name).is_file():
                errors.append(f"missing {version} release material: {name}")
    for name in (
        "docs/module/task_harness/README.md",
        "docs/module/asset_harness/README.md",
        "docs/module/policy_harness/README.md",
    ):
        if not (root / name).is_file():
            errors.append(f"missing harness module entry: {name}")

    for name in files:
        if name.endswith(".json") and (name.startswith("docs/") or name.startswith(".agents/skills/")):
            load_json(root / name, errors)

    obsolete = {
        old for old in manifest.get("_old_paths", set())
        if old != manifest.get("_by_old", {}).get(old, {}).get("new_path")
    }
    issues = []
    for name in files:
        if name.endswith(".md"):
            if not (
                name in {"README.md", "AGENTS.md", "task_env/README.md"}
                or name.startswith(("docs/", ".agents/skills/", "examples/", "task_env/", "bench_deploy/"))
            ):
                continue
            if is_historical_path(name, None) or "/migrations/" in name or name == "docs/maintenance/20261030_runtime_route_diagnostic_handoff.md":
                continue
            text = body((root / name).read_text(encoding="utf-8", errors="replace"))
            for old in obsolete:
                if re.search(r"(?<![A-Za-z0-9_./-])" + re.escape(old) + r"(?![A-Za-z0-9_./-])", text):
                    issues.append(f"{name}: stale path reference {old}")
        elif name.endswith(".py") and name.startswith(("task_env/", ".agents/skills/", "examples/", "bench_deploy/", "scripts/")):
            if name == ".agents/skills/geochora-doc-governance/scripts/validate_docs.py":
                continue
            try:
                tree = ast.parse((root / name).read_text(encoding="utf-8"), filename=name)
            except (OSError, SyntaxError, UnicodeDecodeError) as exc:
                errors.append(f"{name}: Python parse failed during path scan: {exc}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for old in obsolete:
                        if old in node.value:
                            issues.append(f"{name}:{node.lineno}: stale path reference {old}")
    errors.extend(issues)
    return {"stale_path_references": issues}


def check_current(root: Path, errors: list[str]) -> dict:
    files = repo_files(root)
    manifest, by_new = migration_context(root, errors)
    protected_inputs = check_protected_inputs(root, manifest, errors)
    structure = current_paths(root, files, manifest, errors)
    links = check_markdown_links(root, files, by_new, errors)
    counts = {
        "markdown": sum(name.endswith(".md") for name in files if name.startswith("docs/")),
        "docs_json": sum(name.endswith(".json") for name in files if name.startswith("docs/")),
        "task_env_docs": sum(name.startswith("docs/module/task_env/") for name in files),
    }
    return {
        "counts": counts,
        "migration_entries": len(manifest.get("entries", [])),
        "additions": len(manifest.get("additions", [])),
        "protected_inputs_checked": protected_inputs,
        **structure,
        **links,
        "scope": "current root-owned Markdown/JSON and maintained Python references; ignored workspace, submodules and protected untracked handoff excluded",
    }


def check_historical(root: Path, errors: list[str], historical_issues: list[str]) -> dict:
    manifest_errors: list[str] = []
    migration, _ = migration_context(root, manifest_errors)
    check_protected_inputs(root, migration, manifest_errors)
    errors.extend(manifest_errors)
    old_map = migration.get("_by_old", {})
    inventory_path = root / INVENTORY_PATH
    inventory = load_json(inventory_path, errors)
    baseline = inventory.get("baseline", {})
    source_commit = baseline.get("commit")
    inventory_row = old_map.get("docs/maintenance/consolidation-inventory.json")
    if not inventory_row or inventory_row.get("new_path") != INVENTORY_PATH:
        errors.append("historical inventory destination is not resolved by the current migration manifest")
    elif source_commit:
        try:
            original_inventory = show(inventory_row["source_ref"], inventory_row["old_path"])
            if inventory_path.read_bytes() != original_inventory:
                errors.append("moved consolidation inventory bytes differ from its recorded source")
        except (OSError, subprocess.CalledProcessError, KeyError):
            errors.append("cannot verify original consolidation inventory source")

    expected_tags = baseline.get("tag_objects", {})
    for name, expected in expected_tags.items():
        try:
            actual = git("rev-parse", f"refs/tags/{name}").strip()
            if actual != expected:
                errors.append(f"frozen annotated tag object changed: {name}")
        except subprocess.CalledProcessError:
            errors.append(f"frozen tag missing: {name}")
    if source_commit:
        try:
            actual = git("rev-parse", "refs/tags/v1.1.0^{}").strip()
            if actual != source_commit:
                errors.append("v1.1.0 annotated tag source differs from consolidation inventory baseline")
        except subprocess.CalledProcessError:
            errors.append("cannot resolve frozen v1.1.0 tag source")

    historical_ref = "refs/heads/v1.1.0"
    counts = {}
    try:
        names = git("ls-tree", "-r", "--name-only", "-z", historical_ref, "docs", text=False).decode().split("\0")
        paths = [name for name in names if name]
        task_paths = [name for name in paths if name.startswith("docs/module/task_env/")]
        counts = {"docs": len(paths), "task_env": len(task_paths)}
        limits = baseline.get("limits", {})
        if counts["docs"] > limits.get("docs", 0) or counts["task_env"] > limits.get("task_env", 0):
            errors.append(f"historical v1.1.0 count limit exceeded: {counts}, limits={limits}")
        if source_commit:
            changed = git("diff", "--name-only", "-z", source_commit, historical_ref, text=False).decode().split("\0")
            non_docs = [
                name for name in changed if name and not (
                    name.endswith(".md") or name.startswith(("docs/", ".agents/skills/"))
                )
            ]
            if non_docs:
                errors.append(f"historical doc-only baseline has non-document changes: {non_docs[:12]}")
    except subprocess.CalledProcessError:
        errors.append(f"required historical ref missing: {historical_ref}")

    evidence_checked = 0
    records = inventory.get("records", [])
    for record in records:
        if not isinstance(record, dict) or record.get("proposed_disposition") != "PRESERVE_MACHINE_EVIDENCE":
            continue
        original = record.get("original_path")
        row = old_map.get(original, {})
        destination = row.get("new_path", original)
        expected_hash = record.get("sha256")
        try:
            frozen = show("refs/tags/v1.1.0", original)
            if hashlib.sha256(frozen).hexdigest() != expected_hash:
                errors.append(f"recorded frozen evidence hash mismatch in tag: {original}")
            current = root / destination
            if not current.is_file() or hashlib.sha256(current.read_bytes()).hexdigest() != expected_hash:
                errors.append(f"preserved evidence bytes mismatch: {destination}")
            evidence_checked += 1
        except (OSError, subprocess.CalledProcessError, TypeError):
            errors.append(f"cannot verify preserved evidence: {original}")
    history = {
        "inventory_records": len(records),
        "preserved_evidence_checked": evidence_checked,
        "historical_ref": historical_ref,
        "historical_counts": counts,
        "frozen_tag_objects": expected_tags,
        "scope": "exact v1.1 inventory source, annotated refs, selected preserved machine evidence, and the historical doc-only/count boundary",
    }
    if not isinstance(historical_issues, list):
        historical_issues[:] = []
    return history


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("current", "historical"), default="current")
    parser.add_argument("--inventory", default=INVENTORY_PATH)
    parser.add_argument("--migration-manifest", default=MIGRATION_PATH)
    args = parser.parse_args()
    root = Path(git("rev-parse", "--show-toplevel").strip())
    errors: list[str] = []
    historical_issues: list[str] = []
    if args.inventory != INVENTORY_PATH or args.migration_manifest != MIGRATION_PATH:
        errors.append("custom inventory/manifest paths are unsupported; use the versioned canonical paths")
    if args.mode == "current":
        result = check_current(root, errors)
    else:
        result = check_historical(root, errors, historical_issues)
        result["historical_link_issues"] = historical_issues
    print(json.dumps(
        {"mode": args.mode, "errors": errors, "result": result},
        ensure_ascii=False,
        indent=2,
    ))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
