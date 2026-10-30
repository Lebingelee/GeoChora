"""Static source-family audit for the F05 Menagerie Panda route.

The tool parses MJCF as XML and composes USD through the existing Core loader.
It never imports a physics engine. Its default entry point supervises a child
with resource sampling and an early engine/process tripwire.
"""
from __future__ import annotations

import argparse
import builtins
import copy
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import re
import signal
import struct
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from collections.abc import Mapping

SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
BLOCKED_ROOTS = {
    "isaacsim", "omni", "mujoco", "mujoco_usd", "taichi", "taichi_forge",
    "geophys", "torch", "warp", "newton", "genesis", "sapien", "isaaclab",
}
_TRIPWIRE = None


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _blocked(name):
    return name.split(".", 1)[0].lower() in BLOCKED_ROOTS


def _json_write(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _save_tripwire():
    if _TRIPWIRE:
        _TRIPWIRE["updated_at_utc"] = _now()
        _json_write(_TRIPWIRE["receipt_path"], _TRIPWIRE)


def install_tripwire(receipt_path):
    """Install import and child-process guards before any frozen input read."""
    global _TRIPWIRE
    if _TRIPWIRE is not None:
        return _TRIPWIRE
    _TRIPWIRE = {
        "schema_version": "f05-static-tripwire-v1",
        "receipt_path": str(pathlib.Path(receipt_path).absolute()),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "argv": list(sys.argv),
        "installed_at_utc": _now(),
        "installed_before_input_read": True,
        "blocked_import_attempts": [],
        "blocked_process_attempts": [],
    }

    class ImportBlocker:
        def find_spec(self, fullname, path=None, target=None):
            if _blocked(fullname):
                _TRIPWIRE["blocked_import_attempts"].append(
                    {"module": fullname, "at_utc": _now()}
                )
                _save_tripwire()
                raise RuntimeError("static tripwire blocked engine/provider import: " + fullname)
            return None

    sys.meta_path.insert(0, ImportBlocker())
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if _blocked(name):
            _TRIPWIRE["blocked_import_attempts"].append(
                {"module": name, "at_utc": _now()}
            )
            _save_tripwire()
            raise RuntimeError("static tripwire blocked engine/provider import: " + name)
        return original_import(name, globals, locals, fromlist, level)

    builtins.__import__ = guarded_import
    preloaded = [name for name in sys.modules if _blocked(name)]
    if preloaded:
        raise RuntimeError("forbidden modules loaded before tripwire: " + ", ".join(preloaded))

    def deny(kind):
        def blocked_call(*args, **kwargs):
            _TRIPWIRE["blocked_process_attempts"].append(
                {"kind": kind, "at_utc": _now()}
            )
            _save_tripwire()
            raise RuntimeError("static tripwire blocked process launch: " + kind)
        return blocked_call

    for name in ("Popen", "run", "call", "check_call", "check_output"):
        setattr(subprocess, name, deny("subprocess." + name))
    os.system = deny("os.system")
    for name in ("fork", "posix_spawn", "posix_spawnp"):
        if hasattr(os, name):
            setattr(os, name, deny("os." + name))
    for name in ("execv", "execve", "execl", "execlp", "execle", "execlpe"):
        if hasattr(os, name):
            setattr(os, name, deny("os." + name))
    # Core's package initializer imports Gymnasium, which imports the standard
    # multiprocessing module without starting a child. Guard its launch APIs
    # directly so that import remains safe while Process/Pool/Manager stays denied.
    import multiprocessing as mp
    import multiprocessing.pool as mp_pool
    mp.Process.start = deny("multiprocessing.Process.start")
    mp_pool.Pool.__init__ = deny("multiprocessing.pool.Pool.__init__")
    mp.Pool = deny("multiprocessing.Pool")
    mp.Manager = deny("multiprocessing.Manager")
    mp.context.BaseContext.Process = deny("multiprocessing.BaseContext.Process")
    mp.context.BaseContext.Pool = deny("multiprocessing.BaseContext.Pool")
    mp.context.BaseContext.Manager = deny("multiprocessing.BaseContext.Manager")
    _TRIPWIRE["install_check"] = "PASS"
    _save_tripwire()
    return _TRIPWIRE


def finalize_tripwire(started, completed):
    if _TRIPWIRE is None:
        return None
    loaded = sorted(name for name in sys.modules if _blocked(name))
    _TRIPWIRE.update({
        "audit_started_after_tripwire": bool(started),
        "audit_completed": bool(completed),
        "loaded_forbidden_modules": loaded,
        "blocked_import_count": len(_TRIPWIRE["blocked_import_attempts"]),
        "blocked_process_count": len(_TRIPWIRE["blocked_process_attempts"]),
        "tripwire_status": "PASS" if started and completed and not loaded
            and not _TRIPWIRE["blocked_import_attempts"]
            and not _TRIPWIRE["blocked_process_attempts"] else "FAIL",
    })
    _save_tripwire()
    return _TRIPWIRE


def strict_json_bytes(raw, label):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(label + " contains duplicate key: " + str(key))
            result[key] = value
        return result

    def constant(value):
        raise ValueError(label + " contains non-finite JSON token: " + value)

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        _finite_tree(value)
        return value
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(label + " is not strict UTF-8 JSON") from error


def strict_json_file(path, label):
    return strict_json_bytes(pathlib.Path(path).read_bytes(), label)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity_sha(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return _sha(raw)


def _finite_tree(value, path="$"):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite value at " + path)
    if isinstance(value, dict):
        for key, item in value.items():
            _finite_tree(item, path + "." + str(key))
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _finite_tree(item, path + "[" + str(index) + "]")


def _strict_write(path, value):
    _finite_tree(value)
    _json_write(path, value)


def _value(value, limit=20):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"kind": "non_finite", "token": "NaN"}
        if value == math.inf:
            return {"kind": "non_finite", "token": "+inf"}
        if value == -math.inf:
            return {"kind": "non_finite", "token": "-inf"}
        return value
    if type(value).__name__ in {"Quatf", "Quatd", "Quaternion"} and hasattr(value, "GetReal"):
        try:
            imaginary = value.GetImaginary()
            return {"real": float(value.GetReal()), "imaginary": [float(imaginary[i]) for i in range(3)]}
        except Exception as error:
            return {"type": type(value).__name__, "read_error": type(error).__name__ + ": " + str(error)}
    if type(value).__name__ == "AssetPath":
        return {"path": str(value.path), "resolved_path": str(getattr(value, "resolvedPath", ""))}
    try:
        count = len(value)
        iterator = iter(value)
    except Exception:
        return {"type": type(value).__name__, "repr": repr(value)[:400]}
    if count <= limit:
        converted = [_value(item, limit) for item in iterator]
        return converted
    digest = hashlib.sha256()
    digest.update(b"[")
    sample = []
    for index, item in enumerate(iterator):
        converted = _value(item, limit)
        if index < 8:
            sample.append(converted)
        if index:
            digest.update(b",")
        digest.update(json.dumps(converted, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    digest.update(b"]")
    return {
        "kind": "array_summary",
        "type": type(value).__name__,
        "count": count,
        "sha256": digest.hexdigest(),
        "sample": sample,
    }


def _token_list_op(value):
    """Serialize the Sdf token list operation without flattening authorship."""
    if value is None:
        return None
    fields = (
        "explicitItems", "prependedItems", "appendedItems", "deletedItems", "orderedItems",
    )
    result = {"is_explicit": bool(getattr(value, "isExplicit", False))}
    for name in fields:
        items = getattr(value, name, None)
        result[name] = [str(item) for item in items] if items is not None else []
    return result


def _authored_api_schemas(prim, usd_module):
    try:
        composed = _token_list_op(prim.GetMetadata("apiSchemas"))
    except Exception as error:
        composed = {"read_error": type(error).__name__ + ": " + str(error)}
    specs = []
    authored_tokens = []
    for spec in prim.GetPrimStack():
        try:
            has_info = bool(spec.HasInfo("apiSchemas"))
            operation = _token_list_op(spec.GetInfo("apiSchemas")) if has_info else None
            if operation:
                for key in ("explicitItems", "prependedItems", "appendedItems", "orderedItems"):
                    authored_tokens.extend(operation.get(key, []))
            specs.append({
                "layer_identifier": str(spec.layer.identifier),
                "path": str(spec.path),
                "specifier": str(spec.specifier),
                "authored": has_info,
                "list_op": operation,
            })
        except Exception as error:
            specs.append({"read_error": type(error).__name__ + ": " + str(error)})
    applied = [str(item) for item in prim.GetAppliedSchemas()]
    unique_tokens = list(dict.fromkeys(authored_tokens))
    registered = {}
    registry = None
    try:
        registry = usd_module.SchemaRegistry.GetInstance()
    except Exception:
        pass
    for token in unique_tokens:
        schema_type = None
        if registry is not None:
            try:
                value = registry.GetAPISchemaTypeName(token)
                schema_type = str(value) if value else None
            except Exception:
                schema_type = None
        registered[token] = schema_type
    return {
        "composed_list_op": composed,
        "authored_specs": specs,
        "authored_tokens": unique_tokens,
        "registered_schema_type_names": registered,
        "applied_registered_tokens": applied,
        "unregistered_or_unapplied_authored_tokens": [token for token in unique_tokens if token not in applied],
        "authored_present": any(row.get("authored") for row in specs),
    }


def _safe_file(root, relative):
    rel = pathlib.PurePosixPath(str(relative))
    if rel.is_absolute() or not rel.parts or any(part in ("", ".", "..") for part in rel.parts):
        raise ValueError("unsafe relative path: " + str(relative))
    root = pathlib.Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("input root must be a real directory")
    current = root
    for part in rel.parts[:-1]:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise ValueError("unsafe path component: " + str(relative))
    path = current / rel.parts[-1]
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing or unsafe file: " + str(relative))
    return path


def verify_sha(expected, actual, label="file"):
    if not SHA_RE.fullmatch(str(expected)):
        raise ValueError(label + " expected SHA-256 is malformed")
    if expected != actual:
        raise ValueError(label + " SHA-256 mismatch")
    return True


def validate_revision(expected, actual):
    if not expected or expected != actual:
        raise ValueError("source revision mismatch")
    return True


def validate_mesh_closure(required_paths, available_paths):
    missing = sorted(set(required_paths) - set(available_paths))
    if missing:
        raise ValueError("mesh dependency closure is missing: " + ", ".join(missing))
    return True


def validate_unit_identity(source_unit, target_unit):
    if source_unit != target_unit:
        raise ValueError("coordinate unit mismatch: " + str(source_unit) + " != " + str(target_unit))
    return True


def validate_ordered_mapping(source_names, mapped_names):
    source = list(source_names)
    mapped = list(mapped_names)
    if len(source) != len(set(source)) or len(mapped) != len(set(mapped)):
        raise ValueError("joint mapping is not one-to-one")
    if set(source) != set(mapped):
        raise ValueError("joint mapping does not cover the exact source identity set")
    return True


def validate_equality_mapping(source_rows, mapped_rows):
    by_name = {row.get("source_name"): row for row in mapped_rows}
    if len(by_name) != len(mapped_rows):
        raise ValueError("equality mapping has duplicate source names")
    for row in source_rows:
        mapped = by_name.get(row.get("name"))
        if mapped is None:
            raise ValueError("equality/mimic mapping lost source equality: " + str(row.get("name")))
        if mapped.get("target_name") != row.get("joint2") or mapped.get("joint1") != row.get("joint1"):
            raise ValueError("equality/mimic target relation changed: " + str(row.get("name")))
        if mapped.get("polycoef") != row.get("polycoef"):
            raise ValueError("equality/mimic polynomial changed: " + str(row.get("name")))
    return True


def validate_tendon_mapping(source_rows, mapped_rows):
    by_name = {row.get("source_name"): row for row in mapped_rows}
    if len(by_name) != len(mapped_rows):
        raise ValueError("tendon mapping has duplicate source names")
    for row in source_rows:
        mapped = by_name.get(row.get("name"))
        if mapped is None:
            raise ValueError("tendon transmission lost source tendon: " + str(row.get("name")))
        source_components = [
            (component.get("kind"), component.get("joint"), component.get("site"),
             tuple(component.get("coef") or ()), tuple(component.get("gear") or ()))
            for component in row.get("components", [])
        ]
        target_components = [
            (component.get("kind"), component.get("joint"), component.get("site"),
             tuple(component.get("coef") or ()), tuple(component.get("gear") or ()))
            for component in mapped.get("components", [])
        ]
        if target_components != source_components:
            raise ValueError("tendon transmission component path or ratio changed: " + str(row.get("name")))
    return True


def validate_frame_binding(source, target):
    for field in ("entity", "frame", "com_frame"):
        if source.get(field) != target.get(field):
            raise ValueError("frame/COM binding mismatch at " + field)
    return True


def validate_drive_law(source, target, tolerance=0.0):
    for field in ("mode", "unit", "stiffness", "damping", "force_limit"):
        if field not in source or field not in target:
            raise ValueError("drive law missing field: " + field)
        left, right = source[field], target[field]
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if abs(float(left) - float(right)) > tolerance:
                raise ValueError("drive law mismatch at " + field)
        elif left != right:
            raise ValueError("drive law mismatch at " + field)
    return True


def _numeric(value):
    if value is None:
        return None
    try:
        return [float(item) for item in str(value).replace(",", " ").split()]
    except ValueError:
        return None


def _merge(base, attrs):
    result = dict(base)
    result.update({str(key): str(value) for key, value in attrs.items()})
    return result


def _complete_xml_tree(node):
    return {
        "tag": node.tag,
        "attributes": dict(sorted((str(k), str(v)) for k, v in node.attrib.items())),
        "text": node.text.strip() if node.text and node.text.strip() else None,
        "children": [_complete_xml_tree(child) for child in list(node)],
    }


def _compiler_bool(value, name, default=False):
    if value is None:
        return default
    token = str(value).strip().lower()
    if token in {"true", "1"}:
        return True
    if token in {"false", "0"}:
        return False
    raise ValueError("unknown compiler " + name + " value: " + str(value))


def _limited_effective(explicit, values, autolimits, label):
    """Resolve MuJoCo 3.8.1 automatic range activation without inventing defaults."""
    token = None if explicit is None else str(explicit).strip().lower()
    present = values is not None
    if token in {"true", "1"}:
        return {"authored": explicit, "effective": True, "status": "resolved"}
    if token in {"false", "0"}:
        return {"authored": explicit, "effective": False, "status": "resolved"}
    if token not in {None, "auto"}:
        raise ValueError("unknown " + label + " limited token: " + str(explicit))
    if token == "auto" and not autolimits:
        return {"authored": explicit, "effective": None, "status": "unsupported_auto_without_autolimits"}
    return {
        "authored": explicit,
        "effective": bool(autolimits and present),
        "status": "resolved_autolimits",
    }


def _expand_mjcf_includes(root, source_name, include_files, stack=()):
    """Expand byte-bound MJCF includes in-place and retain their source hashes."""
    include_files = include_files or {}
    base = pathlib.PurePosixPath(source_name).parent
    expanded = []

    def visit(parent, current_name, ancestry):
        children = list(parent)
        for index, child in enumerate(children):
            if child.tag != "include":
                visit(child, current_name, ancestry)
                continue
            authored_path = child.attrib.get("file")
            if not authored_path:
                raise ValueError("MJCF include is missing its file attribute at " + current_name)
            relative = pathlib.PurePosixPath(authored_path)
            resolved = pathlib.PurePosixPath(current_name).parent.joinpath(relative)
            normalized = pathlib.PurePosixPath(os.path.normpath(str(resolved)))
            if normalized.is_absolute() or any(part in {"", ".", ".."} for part in normalized.parts):
                raise ValueError("MJCF include escapes its byte-bound source root: " + authored_path)
            key = normalized.as_posix()
            if key in ancestry:
                raise ValueError("MJCF include cycle detected: " + " -> ".join((*ancestry, key)))
            raw = include_files.get(key)
            if raw is None:
                raise ValueError("MJCF include is not present in the verified source closure: " + key)
            try:
                included = ET.fromstring(raw)
            except ET.ParseError as error:
                raise ValueError("MJCF included XML parse failed at " + key + ": " + str(error)) from error
            if included.tag not in {"mujoco", "mujocoinclude"}:
                raise ValueError("MJCF include root must be mujoco or mujocoinclude: " + key)
            additions = list(included)
            for item in additions:
                visit(item, key, (*ancestry, key))
            parent.remove(child)
            for offset, item in enumerate(additions):
                parent.insert(index + offset, item)
            expanded.append({"authored_file": authored_path, "resolved_path": key, "sha256": _sha(raw)})

    visit(root, pathlib.PurePosixPath(source_name).as_posix(), tuple(stack) or (pathlib.PurePosixPath(source_name).as_posix(),))
    return expanded


def parse_mjcf_bytes(raw, source_name="panda.xml", include_files=None):
    """Resolve the supported MuJoCo 3.8.1 MJCF defaults and units fail-closed."""
    if not isinstance(raw, bytes):
        raise TypeError("MJCF must be bytes")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError("MJCF XML parse failed: " + str(error)) from error
    if root.tag != "mujoco":
        raise ValueError("MJCF root element must be mujoco")
    original_tree = _complete_xml_tree(root)
    include_expansion = _expand_mjcf_includes(root, source_name, include_files)
    compiler = root.find("compiler")
    compiler_attrs = dict(compiler.attrib) if compiler is not None else {}
    angle = compiler_attrs.get("angle", "degree")
    if angle not in {"radian", "degree"}:
        raise ValueError("unknown compiler angle unit: " + angle)
    autolimits = _compiler_bool(compiler_attrs.get("autolimits"), "autolimits", default=False)

    defaults = {"": {}}

    def collect(container, inherited=""):
        for node in container.findall("default"):
            name = node.attrib.get("class", inherited)
            parent = defaults.get(inherited, {})
            defaults[name] = {kind: dict(attrs) for kind, attrs in parent.items()}
            for child in list(node):
                if child.tag != "default":
                    defaults[name][child.tag] = _merge(defaults[name].get(child.tag, {}), child.attrib)
            collect(node, name)

    droot = root.find("default")
    if droot is not None:
        for child in list(droot):
            if child.tag != "default":
                defaults[""][child.tag] = _merge(defaults[""].get(child.tag, {}), child.attrib)
        collect(droot)

    def resolve(tag, elem, inherited):
        cls = elem.attrib.get("class", inherited)
        if cls not in defaults:
            return cls, None
        return cls, _merge(defaults[cls].get(tag, {}), elem.attrib)

    bodies, joints, sites, geoms = [], [], [], []

    def walk(body, parent, inherited, path):
        name = body.attrib.get("name", "<unnamed>")
        body_path = path + "/" + name
        childclass = body.attrib.get("childclass", inherited)
        inertial = body.find("inertial")
        b = {
            "name": name, "locator": source_name + ":" + body_path,
            "parent": parent, "authored": dict(body.attrib), "childclass": childclass,
            "pos_m": _numeric(body.attrib.get("pos", "0 0 0")),
            "quat_wxyz": _numeric(body.attrib.get("quat", "1 0 0 0")),
            "inertial": None, "joint_names": [], "site_names": [], "geom_names": [],
        }
        if inertial is not None:
            b["inertial"] = {
                "locator": source_name + ":" + body_path + "/inertial",
                "authored": dict(inertial.attrib),
                "pos_m": _numeric(inertial.attrib.get("pos", "0 0 0")),
                "quat_wxyz": _numeric(inertial.attrib.get("quat", "1 0 0 0")),
                "mass_kg": _numeric(inertial.attrib.get("mass")),
                "diaginertia_kg_m2": _numeric(inertial.attrib.get("diaginertia")),
                "fullinertia_kg_m2": _numeric(inertial.attrib.get("fullinertia")),
            }
        bodies.append(b)
        for elem in list(body):
            if elem.tag not in {"joint", "freejoint"}:
                continue
            tag = "joint" if elem.tag == "joint" else "freejoint"
            cls, effective = resolve("joint", elem, childclass)
            kind = "free" if tag == "freejoint" else (effective or {}).get("type", "hinge")
            raw_range = _numeric((effective or {}).get("range"))
            normalized = raw_range
            if raw_range and kind in {"hinge", "ball"} and angle == "degree":
                normalized = [math.radians(item) for item in raw_range]
            range_limit = _limited_effective((effective or {}).get("limited"), raw_range, autolimits, "joint")
            raw_ref = _numeric((effective or {}).get("ref"))
            normalized_ref = raw_ref
            if raw_ref and kind == "hinge" and angle == "degree":
                normalized_ref = [math.radians(item) for item in raw_ref]
            row = {
                "name": elem.attrib.get("name", "<unnamed>"),
                "locator": source_name + ":" + body_path + "/" + tag,
                "body": name, "kind": kind, "class": cls,
                "resolution_status": "resolved" if effective is not None else "unknown",
                "authored": dict(elem.attrib), "effective": effective,
                "axis": _numeric((effective or {}).get("axis")),
                "position_unit": "meter" if kind == "slide" else ("radian" if kind == "hinge" else "not_scalar"),
                "angle_unit_source": angle, "range_source": raw_range, "range_normalized": normalized,
                "limited": (effective or {}).get("limited"),
                "limited_effective": range_limit["effective"],
                "limited_resolution_status": range_limit["status"],
                "ref": raw_ref,
                "ref_normalized": normalized_ref,
                "damping": _numeric((effective or {}).get("damping")),
                "frictionloss": _numeric((effective or {}).get("frictionloss")),
                "armature": _numeric((effective or {}).get("armature")),
            }
            b["joint_names"].append(row["name"])
            joints.append(row)
        for elem in body.findall("site"):
            cls, effective = resolve("site", elem, childclass)
            row = {
                "name": elem.attrib.get("name", "<unnamed>"),
                "locator": source_name + ":" + body_path + "/site",
                "body": name, "class": cls,
                "resolution_status": "resolved" if effective is not None else "unknown",
                "authored": dict(elem.attrib), "effective": effective,
                "pos_m": _numeric((effective or {}).get("pos", "0 0 0")),
                "quat_wxyz": _numeric((effective or {}).get("quat", "1 0 0 0")),
            }
            b["site_names"].append(row["name"])
            sites.append(row)
        for elem in body.findall("geom"):
            cls, effective = resolve("geom", elem, childclass)
            row = {
                "name": elem.attrib.get("name", "<unnamed>"),
                "locator": source_name + ":" + body_path + "/geom",
                "body": name, "class": cls,
                "resolution_status": "resolved" if effective is not None else "unknown",
                "authored": dict(elem.attrib), "effective": effective,
                "pos_m": _numeric((effective or {}).get("pos", "0 0 0")),
                "quat_wxyz": _numeric((effective or {}).get("quat", "1 0 0 0")),
                "size_m": _numeric((effective or {}).get("size")),
                "mesh": (effective or {}).get("mesh"), "type": (effective or {}).get("type"),
                "contype": (effective or {}).get("contype"),
                "conaffinity": (effective or {}).get("conaffinity"),
                "friction": _numeric((effective or {}).get("friction")),
                "solref": _numeric((effective or {}).get("solref")),
                "solimp": _numeric((effective or {}).get("solimp")),
            }
            b["geom_names"].append(row["name"])
            geoms.append(row)
        for child in body.findall("body"):
            walk(child, name, childclass, body_path)

    world = root.find("worldbody")
    if world is None:
        raise ValueError("MJCF has no worldbody")
    for body in world.findall("body"):
        walk(body, "world", "", "/worldbody")

    equalities = []
    eroot = root.find("equality")
    if eroot is not None:
        for elem in list(eroot):
            equalities.append({
                "kind": elem.tag, "name": elem.attrib.get("name", "<unnamed>"),
                "locator": source_name + ":/mujoco/equality/" + elem.tag,
                "authored": dict(elem.attrib), "joint1": elem.attrib.get("joint1"),
                "joint2": elem.attrib.get("joint2"), "polycoef": _numeric(elem.attrib.get("polycoef")),
                "solref": _numeric(elem.attrib.get("solref")), "solimp": _numeric(elem.attrib.get("solimp")),
            })
    tendons = []
    tr = root.find("tendon")
    if tr is not None:
        for elem in list(tr):
            components = [{
                "kind": child.tag, "authored": dict(child.attrib),
                "joint": child.attrib.get("joint"), "site": child.attrib.get("site"),
                "coef": _numeric(child.attrib.get("coef")), "gear": _numeric(child.attrib.get("gear")),
            } for child in list(elem)]
            tendons.append({
                "kind": elem.tag, "name": elem.attrib.get("name", "<unnamed>"),
                "locator": source_name + ":/mujoco/tendon/" + elem.tag,
                "authored": dict(elem.attrib), "components": components,
                "range": _numeric(elem.attrib.get("range")), "limited": elem.attrib.get("limited"),
            })
    actuators = []
    ar = root.find("actuator")
    if ar is not None:
        for elem in list(ar):
            cls, effective = resolve(elem.tag, elem, "")
            if effective is None:
                effective, status = dict(elem.attrib), "unknown_default_class"
            else:
                status = "resolved"
            target_kind = next((key for key in ("joint", "tendon", "site", "cranksite", "slidersite") if key in effective), None)
            raw_ctrlrange = _numeric(effective.get("ctrlrange"))
            raw_forcerange = _numeric(effective.get("forcerange"))
            control_limit = _limited_effective(effective.get("ctrllimited"), raw_ctrlrange, autolimits, "actuator control")
            force_limit = _limited_effective(effective.get("forcelimited"), raw_forcerange, autolimits, "actuator force")
            actuators.append({
                "name": elem.attrib.get("name", "<unnamed>"), "kind": elem.tag,
                "locator": source_name + ":/mujoco/actuator/" + elem.tag,
                "class": cls, "resolution_status": status, "authored": dict(elem.attrib),
                "effective": effective, "target_kind": target_kind,
                "target": effective.get(target_kind) if target_kind else None,
                "ctrlrange": raw_ctrlrange,
                "ctrlrange_source": raw_ctrlrange,
                "ctrlrange_normalized": raw_ctrlrange,
                "ctrlrange_normalization_status": "unchanged_units_or_unresolved_target_unit",
                "forcerange": raw_forcerange,
                "kp": _numeric(effective.get("kp")), "kv": _numeric(effective.get("kv")),
                "gainprm": _numeric(effective.get("gainprm")),
                "biasprm": _numeric(effective.get("biasprm")),
                "gear": _numeric(effective.get("gear")),
                "ctrllimited": effective.get("ctrllimited"),
                "ctrllimited_effective": control_limit["effective"],
                "ctrllimited_resolution_status": control_limit["status"],
                "forcelimited": effective.get("forcelimited"),
                "forcelimited_effective": force_limit["effective"],
                "forcelimited_resolution_status": force_limit["status"],
            })
    meshes = []
    asset = root.find("asset")
    if asset is not None:
        for elem in asset.findall("mesh"):
            meshes.append({
                "name": elem.attrib.get("name", "<unnamed>"),
                "locator": source_name + ":/mujoco/asset/mesh",
                "authored": dict(elem.attrib), "file": elem.attrib.get("file"),
                "scale": _numeric(elem.attrib.get("scale")),
            })
    keyframes = []
    keyroot = root.find("keyframe")
    if keyroot is not None:
        for elem in keyroot.findall("key"):
            keyframes.append({
                "name": elem.attrib.get("name", "<unnamed>"),
                "locator": source_name + ":/mujoco/keyframe/key",
                "qpos": _numeric(elem.attrib.get("qpos")),
                "qvel": _numeric(elem.attrib.get("qvel")),
                "ctrl": _numeric(elem.attrib.get("ctrl")),
            })
    return {
        "schema_version": "f05-mjcf-inventory-v1",
        "source_name": source_name,
        "root_attributes": dict(root.attrib),
        "complete_xml_tree": _complete_xml_tree(root),
        "compiler": compiler_attrs,
        "compiler_effective": {"angle": angle, "autolimits": autolimits},
        "include_expansion": include_expansion,
        "source_xml_before_include_expansion": original_tree,
        "defaults": defaults,
        "bodies": bodies, "joints": joints, "sites": sites, "geoms": geoms,
        "equalities": equalities, "tendons": tendons, "actuators": actuators,
        "meshes": meshes, "keyframes": keyframes,
        "option": dict(root.find("option").attrib) if root.find("option") is not None else None,
        "limitations": [
            "XML-only inspection; no MuJoCo compile/load/forward/step.",
            "Only byte-bound includes, compiler angle/autolimits, and explicit inherited class fields are resolved; unsupported defaults remain unknown.",
            "Unresolved default classes and omitted semantics remain unknown rather than zero.",
        ],
    }


def inspect_usd_stage(loaded, snapshot_root):
    """Enumerate the composed authored USD through pxr after Core admission."""
    from pxr import Usd, UsdGeom, UsdPhysics

    file_bytes = getattr(loaded, "file_bytes", None)
    if not isinstance(file_bytes, Mapping) or not file_bytes:
        raise ValueError("Core loader did not expose the verified USD closure bytes")
    if sum(len(raw) for raw in file_bytes.values()) > 512 * 1024 ** 2:
        raise ValueError("Core-verified USD snapshot exceeds the frozen 512 MiB temporary limit")
    root = pathlib.Path(snapshot_root)
    root.mkdir(parents=True, exist_ok=True)
    for relative, raw in sorted(file_bytes.items()):
        target = root.joinpath(*pathlib.PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    delivery = getattr(loaded, "delivery", None)
    entry_file = getattr(delivery, "entry_file", None)
    if not entry_file:
        inspection = getattr(loaded, "inspection", None)
        entry_file = getattr(inspection, "entry_file", None)
    if not entry_file or not (root / entry_file).is_file():
        candidates = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".usd", ".usda", ".usdc"}]
        if len(candidates) != 1:
            raise ValueError("cannot resolve one verified USD entry file from Core loader result")
        entry_path = candidates[0]
    else:
        entry_path = root / entry_file
    stage = Usd.Stage.Open(str(entry_path), load=Usd.Stage.LoadNone)
    if stage is None:
        raise ValueError("OpenUSD could not compose Core-verified byte snapshot")
    xform_cache = UsdGeom.XformCache()
    prims = []
    for prim in stage.TraverseAll():
        attrs = []
        for attr in sorted(prim.GetAttributes(), key=lambda item: item.GetName()):
            try:
                value = _value(attr.Get())
            except Exception as error:
                value = {"read_error": type(error).__name__ + ": " + str(error)}
            attrs.append({
                "name": attr.GetName(),
                "type": str(attr.GetTypeName()),
                "value": value,
                "custom": bool(attr.IsCustom()),
                "variability": str(attr.GetVariability()),
            })
        relationships = []
        for relationship in sorted(prim.GetRelationships(), key=lambda item: item.GetName()):
            relationships.append({
                "name": relationship.GetName(),
                "targets": [str(path) for path in relationship.GetTargets()],
                "custom": bool(relationship.IsCustom()),
            })
        api_schemas = _authored_api_schemas(prim, Usd)
        try:
            world_matrix = xform_cache.GetLocalToWorldTransform(prim)
            world_transform = [[float(world_matrix[row][column]) for column in range(4)] for row in range(4)]
        except Exception as error:
            world_transform = {"read_error": type(error).__name__ + ": " + str(error)}
        try:
            local_result = UsdGeom.Xformable(prim).GetLocalTransformation()
            local_matrix = local_result[0] if isinstance(local_result, tuple) else local_result
            local_transform = [[float(local_matrix[row][column]) for column in range(4)] for row in range(4)]
        except Exception as error:
            local_transform = {"read_error": type(error).__name__ + ": " + str(error)}
        prims.append({
            "path": str(prim.GetPath()),
            "name": prim.GetName(),
            "type": prim.GetTypeName(),
            "active": bool(prim.IsActive()),
            "instance": bool(prim.IsInstance()),
            "applied_schemas": api_schemas["applied_registered_tokens"],
            "api_schemas": api_schemas,
            "local_transform_matrix": local_transform,
            "world_transform_matrix": world_transform,
            "attributes": attrs,
            "relationships": relationships,
        })
    local_source = getattr(loaded, "source_input_bytes", {})
    support = getattr(loaded, "local_support_bytes", {})
    return {
        "schema_version": "f05-usd-composed-inventory-v1",
        "entry_file": str(entry_path.relative_to(root)),
        "default_prim": str(stage.GetDefaultPrim().GetPath()) if stage.GetDefaultPrim() else None,
        "meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
        "kilograms_per_unit": float(UsdPhysics.GetStageKilogramsPerUnit(stage)),
        "kilograms_per_unit_authored": bool(UsdPhysics.StageHasAuthoredKilogramsPerUnit(stage)),
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "prim_count": len(prims),
        "prims": prims,
        "closure_files": [
            {"path": path, "size_bytes": len(raw), "sha256": _sha(raw)}
            for path, raw in sorted(file_bytes.items())
        ],
        "local_source_files": [
            {"path": path, "size_bytes": len(raw), "sha256": _sha(raw)}
            for path, raw in sorted(local_source.items())
        ],
        "local_support_files": [
            {"path": path, "size_bytes": len(raw), "sha256": _sha(raw)}
            for path, raw in sorted(support.items())
        ],
        "local_source_file_count": len(local_source),
        "local_support_file_count": len(support),
    }


def validate_source_family_manifest(manifest, source_files, revision):
    if not isinstance(manifest, dict):
        raise ValueError("source-family manifest must be an object")
    validate_revision(manifest.get("source_revision"), revision)
    expected = manifest.get("source_files")
    if not isinstance(expected, list) or not expected:
        raise ValueError("source-family manifest source_files must be a nonempty list")
    seen = set()
    for row in expected:
        if not isinstance(row, dict):
            raise ValueError("source-family file row must be an object")
        path = row.get("path")
        if path in seen:
            raise ValueError("duplicate source-family path: " + str(path))
        seen.add(path)
        raw = source_files.get(path)
        if raw is None:
            raise ValueError("source-family file missing: " + str(path))
        verify_sha(row.get("sha256"), _sha(raw), "source " + str(path))
        if row.get("size_bytes") != len(raw):
            raise ValueError("source-family file size mismatch: " + str(path))
    if set(source_files) != seen:
        raise ValueError("source-family closure has unmanifested or unlisted files")
    return True


def _synthetic_semantic_report():
    source_names = ["j1", "j2"]
    usd_paths = ["/panda", "/panda/j1", "/panda/j2"]
    source_locator = "panda.xml:/worldbody/body/panda"
    features = [{
        "feature": name, "source_present": True,
        "semantic_equality_claim": False, "disposition": "unknown",
        "consumer_status": "NOT_ESTABLISHED",
        "source_locator_refs": [source_locator], "usd_locator_refs": ["/panda"],
    } for name in sorted(REQUIRED_AUDIT_FEATURES)]
    source_identity = {
        "source_revision": "r1", "source_closure_sha256": "0"*64,
        "source_manifest_sha256": "1"*64,
    }
    source_identity["identity_sha256"] = _identity_sha(source_identity)
    representation_identity = {
        "delivery_sha256": "2"*64, "derived_closure_sha256": "3"*64,
        "recipe_sha256": "4"*64,
    }
    representation_identity["identity_sha256"] = _identity_sha(representation_identity)
    return {
        "schema_version": "f05-semantic-audit-report-v2",
        "source_identity": source_identity,
        "representation_identity": representation_identity,
        "required_features": sorted(REQUIRED_AUDIT_FEATURES),
        "source_locators": [source_locator], "usd_prim_paths": usd_paths,
        "api_schema_inventory": [{"path": path, "authored_tokens": [], "authored_present": False} for path in usd_paths],
        "usd_prim_count": len(usd_paths), "source_joint_names": source_names,
        "joint_bijection": [
            {"source_name": name, "target_name": name, "target_path": "/panda/" + name}
            for name in source_names
        ],
        "features": features,
        "consumer_claims": [
            {"feature": row["feature"], "claim": "NOT_ESTABLISHED", "evidence_kind": "static_authored_inventory",
             "source_identity_sha256": source_identity["identity_sha256"],
             "representation_identity_sha256": representation_identity["identity_sha256"],
             "evidence_ref": None, "consumer_commit": None}
            for row in features
        ],
        "validator_trace": {name: 1 for name in (
            "validate_revision", "validate_mesh_closure", "validate_unit_identity",
            "validate_ordered_mapping", "validate_equality_mapping", "validate_tendon_mapping",
            "validate_frame_binding", "validate_drive_law", "validate_claim_binding",
        )},
    }


def negative_cases(report=None, *, expected_source=None, expected_representation=None, expected_usd=None):
    """Run byte, object, normalization, and report mutations through production gates."""
    base = copy.deepcopy(report if report is not None else _synthetic_semantic_report())
    cases = []

    def attempt(case_id, stage, mutate, checker, *, object_path, mutation, validation_path, input_factory=None):
        sample = mutate(copy.deepcopy(base))
        checker_input = input_factory(sample) if input_factory else sample
        rebound_sha = _identity_sha(checker_input)
        try:
            checker(checker_input)
        except (ValueError, TypeError, KeyError) as error:
            cases.append({"id": case_id, "status": "REJECTED", "expected_stage": stage,
                          "actual_stage": stage, "error_code": type(error).__name__, "detail": str(error),
                          "input_object_path": object_path, "mutation": mutation,
                          "validation_path": validation_path,
                          "outer_hash_rebound": True,
                          "outer_rebound_sha256": rebound_sha,
                          "outer_hash_scope": "canonical negative fixture payload, recomputed after mutation before the semantic gate"})
        else:
            cases.append({"id": case_id, "status": "ACCEPTED_UNEXPECTEDLY", "expected_stage": stage,
                          "actual_stage": "none", "error_code": None, "detail": "mutated input passed the real gate",
                          "input_object_path": object_path, "mutation": mutation,
                          "validation_path": validation_path,
                          "outer_hash_rebound": True,
                          "outer_rebound_sha256": rebound_sha,
                          "outer_hash_scope": "canonical negative fixture payload, recomputed after mutation before the semantic gate"})

    attempt("missing_mesh", "mesh_closure", lambda r: r,
            lambda value: validate_mesh_closure(value["required_paths"], value["closure_paths"]),
            object_path="source_files/assets/link0.obj",
            mutation="remove a required mesh from the byte-bound source closure while rebinding the negative fixture",
            validation_path="validate_mesh_closure",
            input_factory=lambda _r: {"required_paths": ["assets/link0.obj"], "closure_paths": []})
    attempt("wrong_sha", "byte_binding", lambda r: r,
            lambda value: verify_sha(value["expected_sha256"], value["actual_sha256"], value["label"]),
            object_path="source_files/assets/link0.obj.sha256",
            mutation="bind the wrong expected digest to the same supplied bytes",
            validation_path="verify_sha",
            input_factory=lambda _r: {"expected_sha256": "0"*64, "actual_sha256": _sha(b"right"), "label": "negative mesh"})
    attempt("wrong_revision", "source_identity", lambda r: r,
            lambda value: validate_revision(value["actual"], value["expected"]),
            object_path="source_family.source_revision",
            mutation="replace the reported source revision with a different commit identity",
            validation_path="validate_revision",
            input_factory=lambda _r: {"actual": "source-r1", "expected": "source-r2"})
    attempt("frame_COM_mismatch", "frame_binding", lambda r: r,
            lambda value: validate_frame_binding(value["source"], value["target"]),
            object_path="source_body.link0.inertial / USD prim /link0.physics:centerOfMass",
            mutation="bind the source COM frame to a target body-origin frame",
            validation_path="validate_frame_binding",
            input_factory=lambda _r: {"source": {"entity": "panda_link", "frame": "link", "com_frame": "inertial"},
                                      "target": {"entity": "panda_link", "frame": "link", "com_frame": "body"}})
    attempt("degree_radian_error", "unit_normalization", lambda r: r,
            lambda value: validate_unit_identity(value["source_unit"], value["target_unit"]),
            object_path="panda.xml:/mujoco/compiler/@angle and joint.range",
            mutation="compare authored degrees as radians without the compiler-angle conversion",
            validation_path="validate_unit_identity",
            input_factory=lambda _r: {"source_unit": "degree", "target_unit": "radian"})
    def wrong_joint_address(r):
        r["joint_bijection"][1]["target_path"] = r["joint_bijection"][0]["target_path"]
        return r
    attempt("joint_address_mismatch", "cross_reference", wrong_joint_address,
            lambda r: validate_semantic_report(r, expected_source=expected_source, expected_representation=expected_representation, expected_usd=expected_usd),
            object_path="semantic_audit_report.joint_bijection[1].target_path",
            mutation="duplicate the preceding USD joint path so the explicit one-to-one address mapping is broken",
            validation_path="validate_semantic_report -> validate_ordered_mapping and target-path uniqueness")
    def lost_equality(r):
        row = next(item for item in r["features"] if item["feature"] == "equality_mimic")
        row.update({"disposition": "converted_verified", "semantic_equality_claim": True,
                    "method_evidence": {"method": "claimed", "source_fields": ["equality"],
                                        "target_fields": ["mimic"], "consumer_identity": "fake",
                                        "validation_status": "PASS"}, "usd_locator_refs": []})
        return r
    attempt("lost_equality_mimic", "constraint_mapping", lost_equality,
            lambda r: validate_semantic_report(r, expected_source=expected_source, expected_representation=expected_representation, expected_usd=expected_usd),
            object_path="semantic_audit_report.features[equality_mimic]",
            mutation="delete the target relation locators but claim converted_verified/native consumer PASS",
            validation_path="validate_semantic_report")
    def lost_tendon(r):
        row = next(item for item in r["features"] if item["feature"] == "tendon_transmission")
        row.update({"disposition": "converted_verified", "semantic_equality_claim": True,
                    "method_evidence": {"method": "claimed", "source_fields": ["tendon"],
                                        "target_fields": ["tendon"], "consumer_identity": "fake",
                                        "validation_status": "PASS"}, "usd_locator_refs": []})
        return r
    attempt("lost_tendon_transmission", "transmission_mapping", lost_tendon,
            lambda r: validate_semantic_report(r, expected_source=expected_source, expected_representation=expected_representation, expected_usd=expected_usd),
            object_path="semantic_audit_report.features[tendon_transmission]",
            mutation="delete the target component locators but claim verified tendon path and consumer",
            validation_path="validate_semantic_report")
    attempt("drive_gain_force_semantic_drift", "drive_law", lambda r: r,
            lambda value: validate_drive_law(value["source"], value["target"]),
            object_path="panda.xml:/mujoco/actuator/general and r009 authored drive attributes",
            mutation="change target stiffness from the source force law while recomputing the fixture identity",
            validation_path="validate_drive_law",
            input_factory=lambda _r: {"source": {"mode": "force", "unit": "newton", "stiffness": 50.0, "damping": 2.0, "force_limit": 87.0},
                                      "target": {"mode": "force", "unit": "newton", "stiffness": 40.0, "damping": 2.0, "force_limit": 87.0}})
    attempt("forged_upstream_or_native_consumption", "consumer_claim", lambda r: r,
            lambda value: validate_claim_binding(value),
            object_path="semantic_audit_report.consumer_claims[equality_mimic]",
            mutation="forge upstream/native consumer status without source, commit or evidence binding",
            validation_path="validate_claim_binding",
            input_factory=lambda _r: {"claim": "UPSTREAM_VERIFIED_NATIVE_CONSUMPTION", "evidence_kind": "unbound-report-text",
                                      "source_identity_sha256": None, "consumer_commit": None})
    def omit_schema(r):
        r["api_schema_inventory"].pop()
        r["usd_prim_count"] -= 1
        return r
    attempt("unregistered_schema_omission", "authored_schema_inventory", omit_schema,
            lambda r: validate_semantic_report(r, expected_source=expected_source, expected_representation=expected_representation, expected_usd=expected_usd),
            object_path="semantic_audit_report.api_schema_inventory[-1]",
            mutation="remove one composed prim schema row and decrement prim_count to keep the outer count self-consistent",
            validation_path="validate_semantic_report -> composed-stage/authored-schema binding")
    attempt("inertia_rotation_error", "inertia_normalization", lambda r: r,
            lambda value: validate_inertia_tensor(value["source_tensor"], value["target_tensor"]),
            object_path="source_body.inertial.fullinertia / USD physics:diagonalInertia+principalAxes",
            mutation="rotate principal axes by 90 degrees but compare against the unrotated diagonal tensor",
            validation_path="validate_inertia_tensor",
            input_factory=lambda _r: {"source_tensor": [[2,0,0],[0,1,0],[0,0,3]],
                                      "target_tensor": [[1,0,0],[0,2,0],[0,0,3]]})
    attempt("limit_force_projection_order", "control_projection", lambda r: r,
            lambda value: validate_control_projection(value["source"], value["target"]),
            object_path="source actuator ctrlrange/forcerange and tendon transmission Jacobian",
            mutation="move force clamp after tendon projection and evaluate source force before control clipping",
            validation_path="validate_control_projection",
            input_factory=lambda _r: {"source": {"projection_order": ["clip_control", "evaluate_source_force", "clip_actuator_force", "apply_jacobian_transpose"]},
                                      "target": {"projection_order": ["evaluate_source_force", "clip_control", "apply_jacobian_transpose", "clip_actuator_force"]}})
    def missing_field_and_broken_reference(r):
        failures = []
        missing = copy.deepcopy(r)
        missing.pop("representation_identity")
        try:
                validate_semantic_report(missing, expected_source=expected_source, expected_representation=expected_representation, expected_usd=expected_usd)
        except (ValueError, TypeError, KeyError) as error:
            failures.append("missing_required=" + str(error))
        broken = copy.deepcopy(r)
        next(item for item in broken["features"] if item["feature"] == "joint_identity")["usd_locator_refs"] = ["/missing/joint"]
        try:
                validate_semantic_report(broken, expected_source=expected_source, expected_representation=expected_representation, expected_usd=expected_usd)
        except (ValueError, TypeError, KeyError) as error:
            failures.append("broken_reference=" + str(error))
        if len(failures) != 2:
            return
        raise ValueError("; ".join(failures))
    def missing_field_and_broken_reference_inputs(r):
        missing = copy.deepcopy(r)
        missing.pop("representation_identity")
        broken = copy.deepcopy(r)
        next(item for item in broken["features"] if item["feature"] == "joint_identity")["usd_locator_refs"] = ["/missing/joint"]
        return {"missing_required": missing, "broken_reference": broken}

    def missing_field_and_broken_reference_gate(value):
        failures = []
        for label, report_value in value.items():
            try:
                validate_semantic_report(report_value, expected_source=expected_source, expected_representation=expected_representation, expected_usd=expected_usd)
            except (ValueError, TypeError, KeyError) as error:
                failures.append(label + "=" + str(error))
        if len(failures) != 2:
            raise ValueError("negative fixture did not reject both schema and reference mutations")
        raise ValueError("; ".join(failures))

    attempt("missing_required_or_broken_reference", "report_schema_and_cross_reference",
            lambda r: r, missing_field_and_broken_reference_gate,
            object_path="semantic_audit_report.representation_identity and features[joint_identity].usd_locator_refs",
            mutation="first omit required representation identity, then redirect a USD locator to a nonexistent prim",
            validation_path="validate_semantic_report",
            input_factory=missing_field_and_broken_reference_inputs)
    attempt("stale_clock_consumer_evidence", "clock_binding", lambda r: r,
            lambda value: validate_clock_binding(value),
            object_path="native consumer receipt.clock.source_identity_sha256",
            mutation="retain a previous source hash in the clock binding while rebinding the outer fixture payload",
            validation_path="validate_clock_binding",
            input_factory=lambda _r: {"claim": "NATIVE_CONSUMPTION", "source_identity_sha256": "a"*64,
                                      "representation_identity_sha256": "b"*64, "evidence_kind": "native_run_receipt",
                                      "clock": {"source_identity_sha256": "c"*64, "representation_identity_sha256": "b"*64,
                                                "episode_id": "e0", "sample_index": 4}})
    return cases


def validate_claim_binding(claim):
    if not isinstance(claim, Mapping):
        raise ValueError("consumer claim must be an object")
    if claim.get("claim") in {"UPSTREAM_VERIFIED_NATIVE_CONSUMPTION", "NATIVE_CONSUMPTION"}:
        for field in ("source_identity_sha256", "consumer_commit", "evidence_ref"):
            if not claim.get(field):
                raise ValueError("consumption claim lacks bound " + field)
        if claim.get("evidence_kind") not in {"native_run_receipt", "qualification_record"}:
            raise ValueError("consumption claim evidence kind is not native")
        if claim.get("claim") == "NATIVE_CONSUMPTION":
            validate_clock_binding(claim)
    return True


REQUIRED_AUDIT_FEATURES = {
    "joint_identity", "frame_and_COM_binding", "equality_mimic",
    "tendon_transmission", "drive_gain_damping_force",
    "collision_contact_material", "derived_free_body_and_support",
}


def validate_clock_binding(claim):
    clock = claim.get("clock")
    if not isinstance(clock, Mapping):
        raise ValueError("consumer clock evidence is missing")
    required = ("source_identity_sha256", "representation_identity_sha256", "episode_id", "sample_index")
    if any(not clock.get(field) for field in required):
        raise ValueError("consumer clock binding is incomplete")
    for field in ("source_identity_sha256", "representation_identity_sha256"):
        if clock[field] != claim.get(field):
            raise ValueError("stale consumer clock binding at " + field)
    if type(clock["sample_index"]) is not int or clock["sample_index"] < 0:
        raise ValueError("consumer clock sample index is invalid")
    return True


def validate_inertia_tensor(source_tensor, target_tensor, *, atol=1e-6, rtol=2e-6):
    if len(source_tensor) != 3 or len(target_tensor) != 3:
        raise ValueError("inertia tensor must be 3 by 3")
    for i in range(3):
        if len(source_tensor[i]) != 3 or len(target_tensor[i]) != 3:
            raise ValueError("inertia tensor must be 3 by 3")
        for j in range(3):
            left, right = float(source_tensor[i][j]), float(target_tensor[i][j])
            if not math.isfinite(left) or not math.isfinite(right):
                raise ValueError("inertia tensor contains non-finite value")
            if abs(left - right) > atol + rtol * max(abs(left), abs(right)):
                raise ValueError("rotated full inertia tensor mismatch")
    return True


def validate_control_projection(source, target):
    expected_order = ("clip_control", "evaluate_source_force", "clip_actuator_force", "apply_jacobian_transpose")
    if tuple(source.get("projection_order", ())) != expected_order:
        raise ValueError("source force projection order is incomplete")
    if tuple(target.get("projection_order", ())) != expected_order:
        raise ValueError("target force projection order differs from source law")
    return True


def validate_semantic_report(report, *, expected_source=None, expected_representation=None, expected_usd=None):
    """Strictly validate the actual normalized comparison result before deriving status."""
    if not isinstance(report, dict):
        raise ValueError("semantic report must be an object")
    required = {
        "schema_version", "source_identity", "representation_identity", "required_features",
        "source_locators", "usd_prim_paths", "api_schema_inventory", "usd_prim_count",
        "joint_bijection", "features", "consumer_claims", "validator_trace",
    }
    missing = required - set(report)
    if missing:
        raise ValueError("semantic report missing required fields: " + ", ".join(sorted(missing)))
    if report["schema_version"] != "f05-semantic-audit-report-v2":
        raise ValueError("unsupported semantic report schema_version")
    source_identity = report["source_identity"]
    representation_identity = report["representation_identity"]
    if not isinstance(source_identity, dict) or not isinstance(representation_identity, dict):
        raise ValueError("source and representation identities must be objects")
    for label, identity, fields in (
        ("source", source_identity, ("source_revision", "source_closure_sha256", "source_manifest_sha256", "identity_sha256")),
        ("representation", representation_identity, ("delivery_sha256", "derived_closure_sha256", "recipe_sha256", "identity_sha256")),
    ):
        if any(not identity.get(field) for field in fields):
            raise ValueError(label + " identity is incomplete")
        for field in fields:
            if "sha256" in field and not SHA_RE.fullmatch(str(identity[field])):
                raise ValueError(label + " identity has malformed " + field)
    if expected_source:
        validate_revision(expected_source.get("source_revision"), source_identity.get("source_revision"))
        for key in ("source_closure_sha256", "source_manifest_sha256", "identity_sha256"):
            verify_sha(expected_source.get(key), source_identity.get(key), "source identity " + key)
    canonical_source_identity = {key: source_identity[key] for key in (
        "source_revision", "source_closure_sha256", "source_manifest_sha256")}
    verify_sha(_identity_sha(canonical_source_identity), source_identity["identity_sha256"],
               "canonical source identity")
    canonical_representation_identity = {key: representation_identity[key] for key in (
        "delivery_sha256", "derived_closure_sha256", "recipe_sha256")}
    verify_sha(_identity_sha(canonical_representation_identity), representation_identity["identity_sha256"],
               "canonical representation identity")
    if expected_representation:
        for key in ("delivery_sha256", "derived_closure_sha256", "recipe_sha256", "identity_sha256"):
            verify_sha(expected_representation.get(key), representation_identity.get(key),
                       "representation identity " + key)
    if expected_usd:
        expected_paths = [row["path"] for row in expected_usd.get("prims", [])]
        if report["usd_prim_count"] != len(expected_paths) or report["usd_prim_paths"] != expected_paths:
            raise ValueError("USD prim inventory differs from the composed source stage")
        expected_schemas = [
            {"path": row["path"], "authored_tokens": row.get("api_schemas", {}).get("authored_tokens", []),
             "authored_present": row.get("api_schemas", {}).get("authored_present", False)}
            for row in expected_usd.get("prims", [])
        ]
        if report["api_schema_inventory"] != expected_schemas:
            raise ValueError("authored apiSchemas inventory differs from the composed USD prim specs")
    if (type(report["usd_prim_count"]) is not int
            or report["usd_prim_count"] != len(report["usd_prim_paths"])
            or len(report["api_schema_inventory"]) != report["usd_prim_count"]
            or [row.get("path") for row in report["api_schema_inventory"]] != report["usd_prim_paths"]):
        raise ValueError("authored apiSchemas inventory is incomplete for the composed prim set")
    if set(report["required_features"]) != REQUIRED_AUDIT_FEATURES:
        raise ValueError("semantic report required feature set is incomplete or changed")
    features = report["features"]
    if not isinstance(features, list):
        raise ValueError("semantic report features must be a list")
    by_name = {row.get("feature"): row for row in features if isinstance(row, dict)}
    if len(by_name) != len(features) or set(by_name) != REQUIRED_AUDIT_FEATURES:
        raise ValueError("semantic report feature rows are missing, duplicated, or unexpected")
    source_locators = set(report["source_locators"])
    usd_paths = set(report["usd_prim_paths"])
    if len(source_locators) != len(report["source_locators"]) or len(usd_paths) != len(report["usd_prim_paths"]):
        raise ValueError("semantic report locator inventory contains duplicates")
    for feature in features:
        name = feature["feature"]
        if type(feature.get("source_present")) is not bool or type(feature.get("semantic_equality_claim")) is not bool:
            raise ValueError("semantic report feature flags are not booleans: " + name)
        if feature.get("disposition") not in {"converted_verified", "loss", "unknown", "not_required"}:
            raise ValueError("semantic report has invalid disposition for " + name)
        source_refs = feature.get("source_locator_refs")
        usd_refs = feature.get("usd_locator_refs")
        if not isinstance(source_refs, list) or not isinstance(usd_refs, list):
            raise ValueError("semantic report locators must be lists for " + name)
        if feature["source_present"] and not source_refs:
            raise ValueError("source-present feature has no object locator: " + name)
        if any(ref not in source_locators and not str(ref).startswith("recipe:") for ref in source_refs):
            raise ValueError("semantic report has a broken source object reference: " + name)
        for reference in usd_refs:
            prim_path = str(reference).split(".", 1)[0]
            if prim_path not in usd_paths:
                raise ValueError("semantic report has a broken USD object reference: " + str(reference))
        if feature.get("semantic_equality_claim"):
            if feature["disposition"] != "converted_verified":
                raise ValueError("semantic equality claim lacks converted_verified disposition: " + name)
            evidence = feature.get("method_evidence")
            if not isinstance(evidence, dict) or not all(evidence.get(key) for key in (
                "method", "source_fields", "target_fields", "consumer_identity", "validation_status",
            )):
                raise ValueError("semantic equality claim lacks bound method evidence: " + name)
            if not source_refs or not usd_refs:
                raise ValueError("semantic equality claim lacks source or target object references: " + name)
            if evidence.get("validation_status") != "PASS":
                raise ValueError("semantic equality method evidence did not pass: " + name)
        elif feature["disposition"] == "converted_verified":
            raise ValueError("converted_verified feature is missing its semantic equality claim: " + name)
    source_joint_names = report.get("source_joint_names")
    mapped_joint_names = [row.get("target_name") for row in report["joint_bijection"] if isinstance(row, dict)]
    if source_joint_names is not None:
        validate_ordered_mapping(source_joint_names, mapped_joint_names)
    target_paths = [row.get("target_path") for row in report["joint_bijection"]]
    if any(path not in usd_paths for path in target_paths) or len(target_paths) != len(set(target_paths)):
        raise ValueError("joint bijection has a missing, duplicate, or invalid USD path")
    trace = report["validator_trace"]
    required_trace = {"validate_revision", "validate_mesh_closure", "validate_unit_identity",
                      "validate_ordered_mapping", "validate_equality_mapping", "validate_tendon_mapping",
                      "validate_frame_binding", "validate_drive_law", "validate_claim_binding"}
    if not isinstance(trace, dict) or any(type(trace.get(name)) is not int or trace[name] < 1 for name in required_trace):
        raise ValueError("semantic validator call trace is incomplete")
    claims = report["consumer_claims"]
    if not isinstance(claims, list) or {row.get("feature") for row in claims if isinstance(row, dict)} != REQUIRED_AUDIT_FEATURES or len(claims) != len(REQUIRED_AUDIT_FEATURES):
        raise ValueError("consumer claim inventory is missing, duplicated, or unexpected")
    for claim in claims:
        if (claim.get("source_identity_sha256") != source_identity["identity_sha256"]
                or claim.get("representation_identity_sha256") != representation_identity["identity_sha256"]):
            raise ValueError("consumer claim is bound to a stale source or representation identity")
        validate_claim_binding(claim)
    return {
        "inventory_status": "PASS",
        "readiness": "BLOCKED_BY_FEATURE" if any(
            row["source_present"] and (row["disposition"] != "converted_verified"
                                        or row.get("consumer_status") not in {"PUBLIC_STATIC_CONSUMER_VERIFIED", "NATIVE_CONSUMER_VERIFIED"})
            for row in features
        ) else "READY_FOR_S1_CONTRACT_REVIEW",
        "blocked_by_feature": [
            row["feature"] for row in features
            if row["source_present"] and (row["disposition"] != "converted_verified"
                                           or row.get("consumer_status") not in {"PUBLIC_STATIC_CONSUMER_VERIFIED", "NATIVE_CONSUMER_VERIFIED"})
        ],
    }


def verify_negative_suite(rows):
    required = {
        "missing_mesh", "wrong_sha", "wrong_revision", "frame_COM_mismatch",
        "degree_radian_error", "joint_address_mismatch", "lost_equality_mimic",
        "lost_tendon_transmission", "drive_gain_force_semantic_drift",
        "forged_upstream_or_native_consumption", "unregistered_schema_omission",
        "inertia_rotation_error", "limit_force_projection_order",
        "missing_required_or_broken_reference", "stale_clock_consumer_evidence",
    }
    by_id = {row["id"]: row for row in rows}
    missing = required - set(by_id)
    bad = [key for key in required if by_id.get(key, {}).get("status") != "REJECTED"
           or by_id.get(key, {}).get("actual_stage") != by_id.get(key, {}).get("expected_stage")
           or not by_id.get(key, {}).get("input_object_path")
           or not by_id.get(key, {}).get("mutation")
           or not by_id.get(key, {}).get("validation_path")
           or by_id.get(key, {}).get("outer_hash_rebound") is not True
           or not SHA_RE.fullmatch(str(by_id.get(key, {}).get("outer_rebound_sha256", "")))]
    if missing or bad:
        raise ValueError("negative suite failed; missing=" + repr(sorted(missing)) + " bad=" + repr(sorted(bad)))
    return True


def _source_xml_identity(source):
    return {
        "body_names": [item["name"] for item in source["bodies"]],
        "joint_names": [item["name"] for item in source["joints"]],
        "equality_names": [item["name"] for item in source["equalities"]],
        "tendon_names": [item["name"] for item in source["tendons"]],
        "actuator_names": [item["name"] for item in source["actuators"]],
        "mesh_names": [item["name"] for item in source["meshes"]],
    }


def _prim_features(usd):
    prims = usd["prims"]
    names = {row["name"] for row in prims}
    paths = {row["path"] for row in prims}
    schemas = set()
    authored_schemas = set()
    attrs = set()
    relations = set()
    for prim in prims:
        schemas.update(prim["applied_schemas"])
        authored_schemas.update(prim.get("api_schemas", {}).get("authored_tokens", ()))
        attrs.update(item["name"] for item in prim["attributes"])
        relations.update(item["name"] for item in prim["relationships"])
    return {
        "prim_names": sorted(names),
        "prim_paths": sorted(paths),
        "applied_schemas": sorted(schemas),
        "authored_api_schemas": sorted(authored_schemas),
        "attribute_names": sorted(attrs),
        "relationship_names": sorted(relations),
        "joint_schema_count": sum("Joint" in item for item in schemas),
        "drive_schema_count": sum("Drive" in item for item in schemas),
        "joint_prim_type_count": sum("Joint" in str(row["type"]) for row in prims),
        "tendon_prim_type_count": sum("Tendon" in str(row["type"]) for row in prims),
        "prim_type_counts": {
            name: sum(row["type"] == name for row in prims)
            for name in sorted({row["type"] for row in prims})
        },
        "relationship_count": sum(len(item["relationships"]) for item in prims),
    }


def _contains_any(values, terms):
    joined = " ".join(str(value).lower() for value in values)
    return any(term in joined for term in terms)


def compare_features(mjcf, usd, source_info, recipe=None):
    usd_features = _prim_features(usd)
    prim_names = set(usd_features["prim_names"])
    schema_text = " ".join(usd_features["applied_schemas"]).lower()
    authored_schema_text = " ".join(usd_features["authored_api_schemas"]).lower()
    attr_text = " ".join(usd_features["attribute_names"]).lower()
    relationship_text = " ".join(usd_features["relationship_names"]).lower()
    prim_type_text = " ".join(usd["prims"][index]["type"] or "" for index in range(len(usd["prims"]))).lower()
    source_names = _source_xml_identity(mjcf)
    shared_bodies = sorted(set(source_names["body_names"]) & prim_names)
    shared_joints = sorted(set(source_names["joint_names"]) & prim_names)
    source_family = source_info.get("family_id", "source-family")
    required_features = [
        ("joint_identity", len(mjcf["joints"]) > 0, bool(shared_joints), "BLOCKED_BY_FEATURE"),
        ("frame_and_COM_binding", any(row.get("inertial") for row in mjcf["bodies"]), bool(_contains_any(usd_features["attribute_names"], ["physics:mass", "physics:centerofmass"])), "BLOCKED_BY_FEATURE"),
        ("equality_mimic", len(mjcf["equalities"]) > 0, ("mimic" in attr_text or "mimic" in schema_text or "mimic" in authored_schema_text or "mimic" in relationship_text), "BLOCKED_BY_FEATURE"),
        ("tendon_transmission", len(mjcf["tendons"]) > 0 or any(row.get("target_kind") == "tendon" for row in mjcf["actuators"]), ("tendon" in attr_text or "tendon" in schema_text or "tendon" in authored_schema_text or "tendon" in relationship_text or "tendon" in prim_type_text), "BLOCKED_BY_FEATURE"),
        ("drive_gain_damping_force", len(mjcf["actuators"]) > 0, ("drive" in schema_text and ("stiffness" in attr_text or "damping" in attr_text)), "BLOCKED_BY_FEATURE"),
        ("collision_contact_material", len(mjcf["geoms"]) > 0, ("collision" in attr_text or "physics:collision" in attr_text), "BLOCKED_BY_FEATURE"),
    ]
    coverage = []
    for feature, source_present, target_evidence, blocker in required_features:
        coverage.append({
            "feature": feature,
            "source_present": bool(source_present),
            "usd_authored_evidence_found": bool(target_evidence),
            "semantic_equality_claim": False,
            "status": "PRESENT_BOTH_REQUIRES_METHOD_REVIEW" if source_present and target_evidence else (
                "SOURCE_ABSENT" if not source_present else blocker
            ),
            "disposition": "unknown" if source_present else "not_required",
            "consumer_status": "NOT_ESTABLISHED",
            "evidence_scope": "authored structure only; no runtime/solver consumer claim",
            "source_locator_refs": [],
            "usd_locator_refs": [],
        })
    recipe = recipe or {}
    scene = recipe.get("task_scene", {})
    paths = recipe.get("derived_build", {}).get("task_scene_paths", {})
    free_body = scene.get("free_body")
    support = scene.get("support")
    free_path = paths.get("free_body")
    support_path = paths.get("support")
    exact_paths = {row["path"] for row in usd["prims"]}
    coverage.append({
        "feature": "derived_free_body_and_support",
        "source_present": bool(free_body or support),
        "usd_authored_evidence_found": bool((free_path in exact_paths) or (support_path in exact_paths)),
        "semantic_equality_claim": False,
        "status": "PRESENT_BOTH_REQUIRES_METHOD_REVIEW" if (free_body or support) and (free_path in exact_paths or support_path in exact_paths) else (
            "BLOCKED_BY_FEATURE" if free_body or support else "SOURCE_ABSENT"
        ),
        "disposition": "unknown",
        "consumer_status": "NOT_ESTABLISHED",
        "evidence_scope": "local derivation recipe and authored USD scene only; additions are not original Menagerie MJCF source",
        "source_locator_refs": [
            "recipe:$.task_scene.free_body",
            "recipe:$.task_scene.support",
            "recipe:$.derived_build.task_scene_paths.free_body",
            "recipe:$.derived_build.task_scene_paths.support",
        ],
        "usd_locator_refs": [
            path for path in (free_path, support_path) if path and path in exact_paths
        ],
    })
    source_joint_names = [row["name"] for row in mjcf["joints"]]
    target_joint_prims = {}
    target_order = []
    for prim in usd["prims"]:
        if prim["name"] in source_joint_names and ("Joint" in str(prim["type"]) or prim["name"] in source_joint_names):
            target_joint_prims.setdefault(prim["name"], []).append(prim)
            target_order.append(prim["name"])
    joint_mapping = []
    for ordinal, source_name in enumerate(source_joint_names):
        candidates = target_joint_prims.get(source_name, [])
        if len(candidates) == 1:
            joint_mapping.append({
                "source_name": source_name,
                "target_name": candidates[0]["name"],
                "target_path": candidates[0]["path"],
                "source_order_ordinal": ordinal,
                "usd_traversal_ordinal": next(
                    i for i, item in enumerate(usd["prims"]) if item["path"] == candidates[0]["path"]
                ),
            })
    mapping_validation = {"status": "PASS", "error": None}
    try:
        validate_ordered_mapping(source_joint_names, [row["target_name"] for row in joint_mapping])
    except (ValueError, TypeError) as error:
        mapping_validation = {"status": "REJECTED", "error": type(error).__name__ + ": " + str(error)}
    coverage[0]["joint_bijection"] = joint_mapping
    coverage[0]["joint_bijection_validation"] = mapping_validation
    coverage[0]["source_order"] = source_joint_names
    coverage[0]["usd_exact_name_stage_order"] = target_order
    coverage[0]["traversal_order_differs"] = source_joint_names != target_order
    coverage[0]["source_locator_refs"] = [row["locator"] for row in mjcf["joints"]]
    coverage[0]["usd_locator_refs"] = [row["target_path"] for row in joint_mapping]
    if source_info.get("manifest_source_verified") is not True:
        source_provenance = "LOCAL_VALIDATED_SOURCE_VERIFIED_FALSE"
    else:
        source_provenance = "UPSTREAM_SOURCE_VERIFIED"
    return {
        "schema_version": "f05-feature-coverage-v1",
        "source_family_id": source_family,
        "source_identity": source_names,
        "usd_identity": usd_features,
        "matched_body_names": shared_bodies,
        "matched_joint_names": shared_joints,
        "explicit_joint_bijection": joint_mapping,
        "source_provenance_status": source_provenance,
        "features": coverage,
        "normalization_policy": {
            "translation": "meters; USD stage units recorded separately and compared only after explicit conversion",
            "angles": "MJCF compiler angle normalized to radians for hinge/ball; original unit retained",
            "quaternion": "source quaternion order remains explicitly wxyz; USD authored representation retained",
            "joint_order": "source-order mapping is an explicit name/path bijection; target traversal order is recorded separately and may be permuted",
            "frames": "body and inertial/COM frames retained separately; equality requires explicit binding",
            "drive": "position law, kp/kv or equivalent, actuator gain/bias, control range and force range remain distinct fields",
            "unknowns": "unresolved defaults, unsupported attributes, and absent target evidence remain unknown/loss; never filled with zero",
        },
    }


def _load_module_root(repo_root):
    import sys
    root = str(pathlib.Path(repo_root).resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    from task_env.assembly.usd_delivery import load_usd_asset_delivery
    return load_usd_asset_delivery


def _all_bindings(family):
    groups = family.get("binding_groups", {})
    result = []
    for group in ("files", "source_files", "support_files"):
        for row in groups.get(group, []):
            result.append((group, row))
    return result


def _binding_receipt(family):
    rows = []
    for group, row in _all_bindings(family):
        rows.append({
            "group": group,
            "path": row.get("path"),
            "size_bytes": row.get("size_bytes"),
            "sha256": row.get("sha256"),
        })
    return rows


def _recipe_mentions(value, terms=("cube",)):
    found = []
    def walk(node, pointer="$"):
        if isinstance(node, dict):
            for key, item in node.items():
                if any(term in str(key).lower() for term in terms):
                    found.append({"pointer": pointer + "." + str(key), "value": _value(item)})
                walk(item, pointer + "." + str(key))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, pointer + "[" + str(index) + "]")
        elif isinstance(node, str) and any(term in node.lower() for term in terms):
            found.append({"pointer": pointer, "value": node})
    walk(value)
    return found


def _verify_input_bindings(family, delivery_root):
    root = pathlib.Path(delivery_root)
    checked = []
    for group, row in _all_bindings(family):
        path = _safe_file(root, row["path"])
        raw = path.read_bytes()
        if row.get("size_bytes") != len(raw):
            raise ValueError("source_inputs byte size mismatch: " + row["path"])
        verify_sha(row.get("sha256"), _sha(raw), row["path"])
        checked.append({"group": group, "path": row["path"], "size_bytes": len(raw), "sha256": _sha(raw)})
    return checked


def _verify_source_root(family, source_root):
    rows = family.get("binding_groups", {}).get("source_files", [])
    if not rows:
        raise ValueError("primary family has no source_files byte bindings")
    checked = []
    bytes_by_path = {}
    for row in rows:
        path = _safe_file(source_root, row["path"])
        raw = path.read_bytes()
        if row.get("size_bytes") != len(raw):
            raise ValueError("upstream source size mismatch: " + row["path"])
        verify_sha(row.get("sha256"), _sha(raw), "upstream source " + row["path"])
        checked.append({"path": row["path"], "size_bytes": len(raw), "sha256": _sha(raw)})
        bytes_by_path[row["path"]] = raw
    return checked, bytes_by_path


def _feature_locator_rows(mjcf, usd, coverage, recipe=None):
    prim_names = {row["name"]: row["path"] for row in usd["prims"]}
    recipe = recipe or {}
    source_joint_names = {row["name"] for row in mjcf["joints"]}
    usd_joint_stage_order = [
        prim["name"] for prim in usd["prims"]
        if prim["name"] in source_joint_names and (
            "Joint" in str(prim["type"]) or prim["name"] in source_joint_names
        )
    ]
    def usd_rows(predicate, attr_predicate=None, relationship_predicate=None):
        found = []
        for prim in usd["prims"]:
            selected = [attr for attr in prim["attributes"] if attr_predicate and attr_predicate(attr)]
            selected_relationships = [
                row for row in prim["relationships"]
                if relationship_predicate and relationship_predicate(row)
            ]
            if predicate(prim) or selected or selected_relationships:
                found.append({
                    "path": prim["path"],
                    "name": prim["name"],
                    "type": prim["type"],
                    "applied_schemas": prim["applied_schemas"],
                    "api_schemas": prim.get("api_schemas", {}),
                    "attributes": selected,
                    "relationships": selected_relationships if relationship_predicate else prim["relationships"],
                })
        return found
    for item in coverage["features"]:
        feature = item["feature"]
        if feature == "joint_identity":
            item["source_items"] = mjcf["joints"]
            item["usd_items"] = usd_rows(
                lambda prim: "Joint" in str(prim["type"]) or prim["name"] in source_joint_names
            )
            item["source_order"] = [row["name"] for row in mjcf["joints"]]
            item["usd_exact_name_stage_order"] = usd_joint_stage_order
            item["ordered_identity_match"] = bool(item.get("joint_bijection_validation", {}).get("status") == "PASS")
            item["traversal_order_differs"] = item["source_order"] != usd_joint_stage_order
            item["source_locator_refs"] = [row["locator"] for row in mjcf["joints"]]
            item["usd_locator_refs"] = [row["path"] for row in item["usd_items"]]
        elif feature == "frame_and_COM_binding":
            item["source_items"] = [row for row in mjcf["bodies"] if row.get("inertial")]
            item["usd_items"] = usd_rows(
                lambda prim: False,
                lambda attr: attr["name"] in {"physics:mass", "physics:centerOfMass", "xformOp:translate", "xformOp:orient"},
            )
            item["source_locator_refs"] = [row["inertial"]["locator"] for row in mjcf["bodies"] if row.get("inertial")]
            item["usd_locator_refs"] = [row["path"] + "." + attr["name"] for row in item["usd_items"] for attr in row["attributes"]]
        elif feature == "equality_mimic":
            item["source_items"] = mjcf["equalities"]
            item["usd_items"] = usd_rows(
                lambda prim: False,
                lambda attr: "mimic" in attr["name"].lower(),
                lambda relation: "mimic" in relation["name"].lower(),
            )
            item["usd_authored_schema_rows"] = [
                {"path": prim["path"], "api_schemas": prim.get("api_schemas", {})}
                for prim in usd["prims"]
                if any("mimic" in token.lower() for token in prim.get("api_schemas", {}).get("authored_tokens", []))
            ]
            item["source_locator_refs"] = [row["locator"] for row in mjcf["equalities"]]
            item["usd_locator_refs"] = [
                row["path"] + "." + attr["name"] for row in item["usd_items"] for attr in row["attributes"]
            ] + [
                row["path"] + "." + relation["name"] for row in item["usd_items"] for relation in row["relationships"]
            ]
        elif feature == "tendon_transmission":
            item["source_items"] = {
                "tendons": mjcf["tendons"],
                "tendon_target_actuators": [row for row in mjcf["actuators"] if row.get("target_kind") == "tendon"],
            }
            item["usd_items"] = usd_rows(
                lambda prim: "Tendon" in str(prim["type"]),
                lambda attr: "tendon" in attr["name"].lower(),
                lambda relation: "tendon" in relation["name"].lower() or relation["name"] == "mjc:path",
            )
            item["usd_authored_schema_rows"] = [
                {"path": prim["path"], "api_schemas": prim.get("api_schemas", {})}
                for prim in usd["prims"]
                if any("tendon" in token.lower() for token in prim.get("api_schemas", {}).get("authored_tokens", []))
            ]
            item["source_locator_refs"] = [row["locator"] for row in mjcf["tendons"]]
            item["source_locator_refs"].extend(row["locator"] for row in mjcf["actuators"] if row.get("target_kind") == "tendon")
            item["usd_locator_refs"] = [
                row["path"] + "." + attr["name"] for row in item["usd_items"] for attr in row["attributes"]
            ] + [
                row["path"] + "." + relation["name"] for row in item["usd_items"] for relation in row["relationships"]
            ]
        elif feature == "drive_gain_damping_force":
            item["source_items"] = {
                "actuators": mjcf["actuators"],
                "joint_damping_friction_armature": [
                    {key: row[key] for key in ("name", "locator", "damping", "frictionloss", "armature", "effective")}
                    for row in mjcf["joints"]
                ],
            }
            item["usd_items"] = usd_rows(
                lambda prim: "Drive" in " ".join(prim["applied_schemas"]),
                lambda attr: any(word in attr["name"].lower() for word in (
                    "drive", "stiffness", "damping", "maxforce", "targetposition", "targetvelocity", "effort",
                )),
            )
            item["source_locator_refs"] = [row["locator"] for row in mjcf["actuators"]]
            item["source_locator_refs"].extend(row["locator"] for row in mjcf["joints"])
            item["usd_locator_refs"] = [row["path"] + "." + attr["name"] for row in item["usd_items"] for attr in row["attributes"]]
        elif feature == "collision_contact_material":
            item["source_items"] = mjcf["geoms"]
            item["usd_items"] = usd_rows(
                lambda prim: any("Collision" in schema or "Material" in schema for schema in prim["applied_schemas"]),
                lambda attr: any(word in attr["name"].lower() for word in ("collision", "friction", "restitution", "contact")),
            )
            item["source_locator_refs"] = [row["locator"] for row in mjcf["geoms"]]
            item["usd_locator_refs"] = [row["path"] + "." + attr["name"] for row in item["usd_items"] for attr in row["attributes"]]
        elif feature == "derived_free_body_and_support":
            item["source_items"] = {
                "free_body": recipe.get("task_scene", {}).get("free_body"),
                "support": recipe.get("task_scene", {}).get("support"),
                "task_scene_paths": recipe.get("derived_build", {}).get("task_scene_paths", {}),
            }
            path_values = set(item["source_items"]["task_scene_paths"].values())
            item["usd_items"] = [
                prim for prim in usd["prims"]
                if prim["path"] in path_values
                or any(prim["path"].startswith(path.rstrip("/") + "/") for path in path_values if path)
            ]
            item["usd_locator_refs"] = [prim["path"] for prim in item["usd_items"]]
    return coverage


def _source_drive_sample(actuator, state, *, tendon_components=None):
    """Independent scalar actuator law and transmission projection; no engine calls."""
    gain = actuator.get("gainprm") or []
    bias = actuator.get("biasprm") or []
    if len(gain) < 1 or len(bias) < 3:
        raise ValueError("resolved affine actuator needs gainprm[0] and biasprm[0:3]")
    ctrl = float(state["ctrl_requested"])
    ctrl_range = actuator.get("ctrlrange")
    ctrl_clamped = bool(actuator.get("ctrllimited_effective") and ctrl_range)
    ctrl_used = min(max(ctrl, float(ctrl_range[0])), float(ctrl_range[1])) if ctrl_clamped else ctrl
    if actuator.get("target_kind") == "tendon":
        components = tendon_components or []
        q_terms, dq_terms = [], []
        for component in components:
            name = component.get("joint")
            coef = component.get("coef") or []
            q = state.get("q_by_joint", {}).get(name)
            dq = state.get("dq_by_joint", {}).get(name)
            if q is None or dq is None or len(coef) != 1:
                raise ValueError("tendon sample lacks one resolved scalar joint state/coefficient")
            q_terms.append(float(coef[0]) * float(q))
            dq_terms.append(float(coef[0]) * float(dq))
        length = sum(q_terms)
        rate = sum(dq_terms)
        jacobian = {component["joint"]: float(component["coef"][0]) for component in components}
        force_coordinate = "tendon_length_m"
    else:
        length = float(state["q"])
        rate = float(state["dq"])
        jacobian = {actuator["target"]: float((actuator.get("gear") or [1.0])[0])}
        force_coordinate = "joint_coordinate"
    raw_force = (float(gain[0]) * ctrl_used + float(bias[0])
                 + float(bias[1]) * length + float(bias[2]) * rate)
    force_range = actuator.get("forcerange")
    force_clamped = bool(actuator.get("forcelimited_effective") and force_range)
    force_used = (min(max(raw_force, float(force_range[0])), float(force_range[1]))
                  if force_clamped else raw_force)
    projected = {name: force_used * ratio for name, ratio in jacobian.items()}
    return {
        **state,
        "ctrl_used_after_control_limit": ctrl_used,
        "control_limit_applied_before_gain": ctrl_clamped,
        "generalized_length_or_position": length,
        "generalized_rate": rate,
        "force_coordinate": force_coordinate,
        "raw_scalar_actuator_force_before_force_limit": raw_force,
        "scalar_actuator_force_after_force_limit": force_used,
        "force_limit_applied_after_bias_law": force_clamped,
        "transmission_jacobian": jacobian,
        "projected_joint_forces": projected,
        "formula": "f_raw = gainprm[0]*clip(ctrl if ctrllimited) + biasprm[0] + biasprm[1]*length + biasprm[2]*length_rate; f = clip(f_raw if forcelimited); joint_force = J^T*f",
    }


def _analytic_drive_checks(mjcf):
    """Pure-Python source-law oracle, deliberately independent of a simulator/provider."""
    checks = []
    tendon_by_name = {row["name"]: row for row in mjcf.get("tendons", [])}
    for actuator in mjcf["actuators"]:
        gain, bias = actuator.get("gainprm"), actuator.get("biasprm")
        if not gain or len(gain) < 1 or not bias or len(bias) < 3:
            checks.append({"actuator": actuator["name"], "locator": actuator["locator"],
                           "status": "UNKNOWN", "reason": "effective gain and affine bias law were not resolved"})
            continue
        target = actuator["target"]
        if actuator["target_kind"] == "tendon":
            tendon = tendon_by_name.get(target)
            components = tendon.get("components", []) if tendon else []
            q = {"finger_joint1": 0.028, "finger_joint2": 0.012}
            dq = {"finger_joint1": 0.01, "finger_joint2": -0.004}
            states = [
                {"sample": "asymmetric_opening_and_velocity", "q_by_joint": q, "dq_by_joint": dq, "ctrl_requested": 64.0},
                {"sample": "symmetric_state", "q_by_joint": {"finger_joint1": 0.02, "finger_joint2": 0.02},
                 "dq_by_joint": {"finger_joint1": 0.0, "finger_joint2": 0.0}, "ctrl_requested": 128.0},
                {"sample": "control_lower_bound_saturation", "q_by_joint": q, "dq_by_joint": dq, "ctrl_requested": -1.0},
                {"sample": "control_upper_bound_saturation", "q_by_joint": q, "dq_by_joint": dq, "ctrl_requested": 256.0},
                {"sample": "force_limit_and_clamp_order", "q_by_joint": {"finger_joint1": -0.1, "finger_joint2": -0.1},
                 "dq_by_joint": {"finger_joint1": -10.0, "finger_joint2": -10.0}, "ctrl_requested": 0.0},
            ]
        else:
            q = 0.217
            dq = -0.13
            q_range = next((row.get("range_normalized") for row in mjcf["joints"] if row["name"] == target), None)
            default_ctrl = sum(actuator["ctrlrange"]) / 2 if actuator.get("ctrlrange") else 0.481
            outside_low = float(actuator["ctrlrange"][0]) - 1 if actuator.get("ctrlrange") else default_ctrl
            outside_high = float(actuator["ctrlrange"][1]) + 1 if actuator.get("ctrlrange") else default_ctrl
            states = [
                {"sample": "nominal", "q": q, "dq": dq, "ctrl_requested": default_ctrl},
                {"sample": "zero_control_bias", "q": q, "dq": dq, "ctrl_requested": 0.0},
                {"sample": "asymmetric_state", "q": -0.341, "dq": 0.27, "ctrl_requested": default_ctrl},
                {"sample": "control_lower_bound_saturation", "q": q, "dq": dq, "ctrl_requested": outside_low},
                {"sample": "control_upper_bound_saturation", "q": q, "dq": dq, "ctrl_requested": outside_high},
            ]
            # Force saturation is evaluated at an explicit state outside nominal limits; it is
            # a source-law arithmetic probe, not an asserted physically reachable state.
            states.append({"sample": "force_limit_and_clamp_order", "q": 0.0 if q_range else q,
                           "dq": 10.0, "ctrl_requested": default_ctrl})
            components = None
        samples = []
        for state in states:
            try:
                samples.append(_source_drive_sample(actuator, state, tendon_components=components))
            except ValueError as error:
                samples.append({**state, "status": "UNKNOWN", "reason": str(error)})
        checks.append({
            "actuator": actuator["name"], "target": target, "locator": actuator["locator"],
            "status": "ANALYTIC_SOURCE_LAW_ONLY", "kind": actuator["kind"],
            "target_kind": actuator["target_kind"], "gainprm": gain, "biasprm": bias,
            "force_range": actuator.get("forcerange"), "forcelimited_effective": actuator.get("forcelimited_effective"),
            "control_range": actuator.get("ctrlrange"), "ctrllimited_effective": actuator.get("ctrllimited_effective"),
            "tendon_components": components, "samples": samples,
            "clamp_order": ["control range", "affine scalar force", "actuator force range", "transmission Jacobian transpose"],
            "not_a_simulation": True,
            "target_representation_consumer_status": "NOT_ESTABLISHED_BY_STATIC_FORMULA",
        })
    return checks


def _quat_normalize_wxyz(value):
    q = [float(x) for x in (value or [1.0, 0.0, 0.0, 0.0])]
    if len(q) != 4:
        raise ValueError("quaternion must use four wxyz values")
    norm = math.sqrt(sum(x * x for x in q))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("quaternion must be finite and nonzero")
    return [x / norm for x in q]


def _quat_multiply_wxyz(left, right):
    w1, x1, y1, z1 = _quat_normalize_wxyz(left)
    w2, x2, y2, z2 = _quat_normalize_wxyz(right)
    return _quat_normalize_wxyz([
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
    ])


def _quat_matrix_wxyz(value):
    w, x, y, z = _quat_normalize_wxyz(value)
    return [
        [1 - 2*(y*y + z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
        [2*(x*y + z*w), 1 - 2*(x*x + z*z), 2*(y*z - x*w)],
        [2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x + y*y)],
    ]


def _mat3_transpose(a):
    return [[a[j][i] for j in range(3)] for i in range(3)]


def _mat3_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _mat3_vec(a, v):
    return [sum(a[i][j] * float(v[j]) for j in range(3)) for i in range(3)]


def _matrix_from_symmetric_inertia(values):
    if len(values) == 3:
        xx, yy, zz = (float(x) for x in values)
        xy = xz = yz = 0.0
    elif len(values) == 6:
        xx, yy, zz, xy, xz, yz = (float(x) for x in values)
    else:
        raise ValueError("inertia must have three diagonal or six full tensor values")
    return [[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]]


def _inertia_six(matrix):
    return [matrix[0][0], matrix[1][1], matrix[2][2], matrix[0][1], matrix[0][2], matrix[1][2]]


def _parallel_axis_at_origin(inertia_com, mass, offset):
    r = [float(x) for x in offset]
    rr = sum(x*x for x in r)
    return [[inertia_com[i][j] + float(mass) * ((rr if i == j else 0.0) - r[i]*r[j])
             for j in range(3)] for i in range(3)]


def _numeric_values_match(left, right, *, atol, rtol):
    left_flat = [float(value) for row in left for value in row] if left and isinstance(left[0], list) else [float(x) for x in left]
    right_flat = [float(value) for row in right for value in row] if right and isinstance(right[0], list) else [float(x) for x in right]
    return len(left_flat) == len(right_flat) and all(
        math.isfinite(a) and math.isfinite(b) and abs(a-b) <= atol + rtol * max(abs(a), abs(b))
        for a, b in zip(left_flat, right_flat, strict=True)
    )


def _usd_quaternion_wxyz(value):
    if not isinstance(value, Mapping) or "real" not in value or not isinstance(value.get("imaginary"), list):
        return None
    return _quat_normalize_wxyz([value["real"], *value["imaginary"]])


def _source_body_frames(mjcf):
    """Compose MJCF body frames at q=0 from source transforms, independently of OpenUSD."""
    source = {row["name"]: row for row in mjcf["bodies"]}
    frames = {"world": {"position_m": [0.0, 0.0, 0.0], "quat_wxyz": [1.0, 0.0, 0.0, 0.0]}}
    pending = set(source)
    while pending:
        ready = sorted(name for name in pending if source[name].get("parent") in frames)
        if not ready:
            raise ValueError("MJCF body parent graph is unresolved or cyclic: " + repr(sorted(pending)))
        for name in ready:
            row = source[name]
            parent = frames[row.get("parent")]
            local_q = _quat_normalize_wxyz(row.get("quat_wxyz"))
            parent_r = _quat_matrix_wxyz(parent["quat_wxyz"])
            local_p = [float(x) for x in (row.get("pos_m") or [0.0, 0.0, 0.0])]
            rotated_p = _mat3_vec(parent_r, local_p)
            frames[name] = {
                "local_position_m": local_p,
                "local_quat_wxyz": local_q,
                "position_m": [parent["position_m"][i] + rotated_p[i] for i in range(3)],
                "quat_wxyz": _quat_multiply_wxyz(parent["quat_wxyz"], local_q),
                "reference_configuration": "articulated joint coordinates held at q=0; joint ref values recorded separately",
            }
            pending.remove(name)
    return frames


def _mesh_bounds_from_bytes(raw, path):
    """Read mesh vertex bounds without calling a converter, renderer, or mesh cooker."""
    suffix = pathlib.PurePosixPath(path).suffix.lower()
    points = []
    format_name = "unsupported"
    if suffix == ".obj":
        format_name = "obj_vertices"
        for line in raw.decode("utf-8", errors="replace").splitlines():
            parts = line.strip().split()
            if parts and parts[0] == "v" and len(parts) >= 4:
                try:
                    points.append([float(x) for x in parts[1:4]])
                except ValueError:
                    continue
    elif suffix == ".stl":
        if len(raw) >= 84:
            triangle_count = struct.unpack_from("<I", raw, 80)[0]
            if 84 + triangle_count * 50 == len(raw):
                format_name = "binary_stl_vertices"
                for index in range(triangle_count):
                    offset = 84 + index * 50 + 12
                    for vertex in range(3):
                        points.append(list(struct.unpack_from("<fff", raw, offset + vertex * 12)))
        if not points:
            format_name = "ascii_stl_vertices"
            for line in raw.decode("utf-8", errors="replace").splitlines():
                parts = line.strip().split()
                if parts and parts[0].lower() == "vertex" and len(parts) >= 4:
                    try:
                        points.append([float(x) for x in parts[1:4]])
                    except ValueError:
                        continue
    if not points:
        return {"path": path, "status": "UNKNOWN", "format": format_name, "vertex_count": 0}
    return {
        "path": path, "status": "STATIC_BOUNDS_ONLY", "format": format_name,
        "vertex_count": len(points),
        "minimum": [min(point[axis] for point in points) for axis in range(3)],
        "maximum": [max(point[axis] for point in points) for axis in range(3)],
        "frame": "mesh-file coordinates; no geom/body transform applied",
    }


def _normalization_oracle(mjcf, usd, recipe, source_file_bytes):
    """Independent static SI/frame/inertia oracle; all comparisons preserve unknowns."""
    frames = _source_body_frames(mjcf)
    mesh_rows = {row.get("name"): row for row in mjcf.get("meshes", [])}
    mesh_bounds = {}
    for mesh in mjcf.get("meshes", []):
        relative = pathlib.PurePosixPath(mjcf.get("compiler", {}).get("meshdir", "")).joinpath(mesh.get("file", ""))
        path = pathlib.PurePosixPath(os.path.normpath(str(relative))).as_posix()
        raw = source_file_bytes.get(path)
        mesh_bounds[mesh.get("name")] = (_mesh_bounds_from_bytes(raw, path) if raw is not None else {
            "path": path, "status": "MISSING_FROM_VERIFIED_CLOSURE", "vertex_count": 0,
        })
    usd_by_name = {}
    for prim in usd.get("prims", []):
        usd_by_name.setdefault(prim.get("name"), []).append(prim)
    source_body_names = {row["name"] for row in mjcf.get("bodies", [])}
    usd_body_path_to_name = {}
    for name in source_body_names:
        candidates = usd_by_name.get(name, [])
        rigid = [prim for prim in candidates if "PhysicsRigidBodyAPI" in prim.get("applied_schemas", [])]
        if len(rigid) == 1:
            usd_body_path_to_name[rigid[0]["path"]] = name
    bodies = []
    meters_per_unit = float(usd.get("meters_per_unit") or 0.0)
    kilograms_per_unit = float(usd.get("kilograms_per_unit") or 0.0)
    schema_numeric_tolerance = {"atol": 1e-6, "rtol": 2e-6}
    for body in mjcf.get("bodies", []):
        frame = frames[body["name"]]
        inertial = body.get("inertial")
        inertia = None
        if inertial:
            diag = inertial.get("diaginertia_kg_m2")
            full = inertial.get("fullinertia_kg_m2")
            local_tensor = _matrix_from_symmetric_inertia(full if full is not None else diag or [])
            inertial_q = _quat_normalize_wxyz(inertial.get("quat_wxyz"))
            inertial_r = _quat_matrix_wxyz(inertial_q)
            body_tensor = _mat3_mul(_mat3_mul(inertial_r, local_tensor), _mat3_transpose(inertial_r))
            mass = float((inertial.get("mass_kg") or [0.0])[0])
            com_offset = [float(x) for x in (inertial.get("pos_m") or [0.0, 0.0, 0.0])]
            body_origin_tensor = _parallel_axis_at_origin(body_tensor, mass, com_offset)
            body_r = _quat_matrix_wxyz(frame["quat_wxyz"])
            world_tensor = _mat3_mul(_mat3_mul(body_r, body_tensor), _mat3_transpose(body_r))
            world_origin_tensor = _mat3_mul(_mat3_mul(body_r, body_origin_tensor), _mat3_transpose(body_r))
            com_world = _mat3_vec(body_r, com_offset)
            inertia = {
                "locator": inertial["locator"], "mass_kg": mass,
                "COM_local_body_frame_m": com_offset,
                "COM_world_q0_m": [frame["position_m"][i] + com_world[i] for i in range(3)],
                "inertial_quat_wxyz": inertial_q,
                "inertia_at_COM_inertial_frame_kg_m2": local_tensor,
                "inertia_at_COM_body_frame_kg_m2": body_tensor,
                "inertia_at_COM_world_q0_kg_m2": world_tensor,
                "inertia_about_body_origin_body_frame_kg_m2": body_origin_tensor,
                "inertia_about_body_origin_world_q0_kg_m2": world_origin_tensor,
                "parallel_axis_formula": "I_origin = I_COM + m*((r dot r)*identity - outer(r,r))",
                "principal_axes_rotation_applied_before_world_rotation": True,
            }
        candidates = usd_by_name.get(body["name"], [])
        usd_rows = []
        for prim in candidates:
            attrs = {row["name"]: row["value"] for row in prim.get("attributes", [])}
            usd_raw = {
                "path": prim["path"], "type": prim["type"],
                "mass": attrs.get("physics:mass"), "center_of_mass": attrs.get("physics:centerOfMass"),
                "diagonal_inertia": attrs.get("physics:diagonalInertia"),
                "principal_axes": attrs.get("physics:principalAxes"),
                "local_transform_matrix": prim.get("local_transform_matrix"),
                "world_transform_matrix": prim.get("world_transform_matrix"),
                "api_schemas": prim.get("api_schemas", {}).get("authored_tokens", []),
            }
            comparison = {"status": "UNKNOWN", "unit_scale": {"meters_per_unit": meters_per_unit,
                                                                  "kilograms_per_unit": kilograms_per_unit}}
            if inertia and type(attrs.get("physics:mass")) in (int, float) and isinstance(attrs.get("physics:centerOfMass"), list) and isinstance(attrs.get("physics:diagonalInertia"), list):
                principal_q = _usd_quaternion_wxyz(attrs.get("physics:principalAxes"))
                if principal_q is not None and meters_per_unit > 0 and kilograms_per_unit > 0:
                    principal_r = _quat_matrix_wxyz(principal_q)
                    raw_diag = [float(x) for x in attrs["physics:diagonalInertia"]]
                    diag_tensor = _matrix_from_symmetric_inertia([
                        x * kilograms_per_unit * meters_per_unit * meters_per_unit for x in raw_diag
                    ])
                    usd_tensor_body = _mat3_mul(_mat3_mul(principal_r, diag_tensor), _mat3_transpose(principal_r))
                    usd_mass_kg = float(attrs["physics:mass"]) * kilograms_per_unit
                    usd_com_body_m = [float(x) * meters_per_unit for x in attrs["physics:centerOfMass"]]
                    usd_world = prim.get("world_transform_matrix")
                    source_row_rotation = _mat3_transpose(_quat_matrix_wxyz(frame["quat_wxyz"]))
                    transform_match = None
                    if isinstance(usd_world, list) and len(usd_world) == 4 and usd.get("up_axis") == "Z":
                        target_rotation = [row[:3] for row in usd_world[:3]]
                        target_translation = [float(x) * meters_per_unit for x in usd_world[3][:3]]
                        transform_match = (
                            _numeric_values_match(source_row_rotation, target_rotation, **schema_numeric_tolerance)
                            and _numeric_values_match(frame["position_m"], target_translation, **schema_numeric_tolerance)
                        )
                    else:
                        target_rotation = None
                        target_translation = None
                    mass_match = math.isclose(usd_mass_kg, inertia["mass_kg"],
                                              abs_tol=schema_numeric_tolerance["atol"], rel_tol=schema_numeric_tolerance["rtol"])
                    com_match = _numeric_values_match(usd_com_body_m, inertia["COM_local_body_frame_m"], **schema_numeric_tolerance)
                    tensor_match = _numeric_values_match(usd_tensor_body, inertia["inertia_at_COM_body_frame_kg_m2"], **schema_numeric_tolerance)
                    comparison = {
                        "status": "PASS" if mass_match and com_match and tensor_match and transform_match is True else "MISMATCH_OR_FRAME_UNKNOWN",
                        "mass": {"source_kg": inertia["mass_kg"], "usd_raw": attrs["physics:mass"],
                                 "usd_normalized_kg": usd_mass_kg, "match": mass_match},
                        "COM": {"source_body_frame_m": inertia["COM_local_body_frame_m"],
                                "usd_raw": attrs["physics:centerOfMass"], "usd_normalized_body_frame_m": usd_com_body_m,
                                "match": com_match},
                        "full_inertia_at_COM": {"source_body_frame_kg_m2": inertia["inertia_at_COM_body_frame_kg_m2"],
                                                 "usd_principal_axes_quat_wxyz": principal_q,
                                                 "usd_normalized_body_frame_kg_m2": usd_tensor_body,
                                                 "match": tensor_match},
                        "world_transform_q0": {"source_rotation_row_convention": source_row_rotation,
                                                "source_translation_m": frame["position_m"],
                                                "usd_world_rotation_row_convention": target_rotation,
                                                "usd_world_translation_m": target_translation,
                                                "match": transform_match,
                                                "policy": "compared only for Z-up stage; USD local-to-world is row-vector convention"},
                        "unit_scale": {"meters_per_unit": meters_per_unit,
                                       "kilograms_per_unit": kilograms_per_unit},
                        "tolerance": schema_numeric_tolerance,
                    }
            usd_rows.append({**usd_raw, "normalized_comparison": comparison})
        bodies.append({
            "name": body["name"], "source_locator": body["locator"],
            "parent": body.get("parent"), "source_local_body_transform": {
                "translation_m": frame.get("local_position_m"), "quat_wxyz": frame.get("local_quat_wxyz"),
            },
            "source_world_body_transform_q0": {"translation_m": frame["position_m"], "quat_wxyz": frame["quat_wxyz"]},
            "reference_configuration": frame["reference_configuration"],
            "inertia_normalization": inertia,
            "usd_exact_name_candidates": usd_rows,
            "source_geom_locators": [row["locator"] for row in mjcf.get("geoms", []) if row.get("body") == body["name"]],
        })
    joints = []
    for joint in mjcf.get("joints", []):
        body = frames[joint["body"]]
        rotation = _quat_matrix_wxyz(body["quat_wxyz"])
        axis_local = joint.get("axis") or [0.0, 0.0, 1.0]
        axis_world = _mat3_vec(rotation, axis_local)
        axis_norm = math.sqrt(sum(value*value for value in axis_world))
        axis_world = [value / axis_norm for value in axis_world] if axis_norm else axis_world
        pos_local = _numeric((joint.get("effective") or {}).get("pos", "0 0 0")) or [0.0, 0.0, 0.0]
        pos_world_offset = _mat3_vec(rotation, pos_local)
        usd_joint_candidates = []
        for prim in usd_by_name.get(joint["name"], []):
            attrs = {row["name"]: row["value"] for row in prim.get("attributes", [])}
            raw_axis = attrs.get("physics:axis")
            usd_axis_local = {"X": [1.0, 0.0, 0.0], "Y": [0.0, 1.0, 0.0], "Z": [0.0, 0.0, 1.0]}.get(raw_axis)
            source_limit = joint.get("range_normalized")
            target_limit = None
            if source_limit and type(attrs.get("physics:lowerLimit")) in (int, float) and type(attrs.get("physics:upperLimit")) in (int, float):
                lower, upper = float(attrs["physics:lowerLimit"]), float(attrs["physics:upperLimit"])
                if joint["kind"] in {"hinge", "ball"}:
                    target_limit = [math.radians(lower), math.radians(upper)]
                else:
                    target_limit = [lower * meters_per_unit, upper * meters_per_unit]
            local_rot0 = _usd_quaternion_wxyz(attrs.get("physics:localRot0"))
            local_rot1 = _usd_quaternion_wxyz(attrs.get("physics:localRot1"))
            limits_match = (_numeric_values_match(source_limit, target_limit, **schema_numeric_tolerance)
                            if source_limit is not None and target_limit is not None else None)
            body_rels = {row["name"]: row.get("targets", []) for row in prim.get("relationships", [])
                         if row["name"] in {"physics:body0", "physics:body1"}}
            body0_targets, body1_targets = body_rels.get("physics:body0", []), body_rels.get("physics:body1", [])
            body0_name = usd_body_path_to_name.get(body0_targets[0]) if len(body0_targets) == 1 else "world"
            body1_name = usd_body_path_to_name.get(body1_targets[0]) if len(body1_targets) == 1 else None
            source_parent = next((row["parent"] for row in mjcf["bodies"] if row["name"] == joint["body"]), "world")
            body_mapping_match = body0_name == source_parent and body1_name == joint["body"]
            axis0_world = axis1_world = anchor0_world = anchor1_world = None
            axis0_match = axis1_match = anchor_match = None
            if (usd_axis_local is not None and local_rot0 is not None and local_rot1 is not None
                    and body0_name in frames and body1_name in frames and meters_per_unit > 0):
                frame0, frame1 = frames[body0_name], frames[body1_name]
                world_joint_q0 = _quat_multiply_wxyz(frame0["quat_wxyz"], local_rot0)
                world_joint_q1 = _quat_multiply_wxyz(frame1["quat_wxyz"], local_rot1)
                axis0_world = _mat3_vec(_quat_matrix_wxyz(world_joint_q0), usd_axis_local)
                axis1_world = _mat3_vec(_quat_matrix_wxyz(world_joint_q1), usd_axis_local)
                source_axis_world = [float(value) for value in axis_world]
                axis0_match = _numeric_values_match(source_axis_world, axis0_world, **schema_numeric_tolerance)
                axis1_match = _numeric_values_match(source_axis_world, axis1_world, **schema_numeric_tolerance)
                local_pos0 = attrs.get("physics:localPos0")
                local_pos1 = attrs.get("physics:localPos1")
                if isinstance(local_pos0, list) and isinstance(local_pos1, list):
                    offset0 = _mat3_vec(_quat_matrix_wxyz(frame0["quat_wxyz"]),
                                        [float(x) * meters_per_unit for x in local_pos0])
                    offset1 = _mat3_vec(_quat_matrix_wxyz(frame1["quat_wxyz"]),
                                        [float(x) * meters_per_unit for x in local_pos1])
                    anchor0_world = [frame0["position_m"][i] + offset0[i] for i in range(3)]
                    anchor1_world = [frame1["position_m"][i] + offset1[i] for i in range(3)]
                    source_anchor = [body["position_m"][i] + pos_world_offset[i] for i in range(3)]
                    anchor_match = (_numeric_values_match(source_anchor, anchor0_world, **schema_numeric_tolerance)
                                    and _numeric_values_match(source_anchor, anchor1_world, **schema_numeric_tolerance))
            usd_joint_candidates.append({
                "path": prim["path"], "type": prim["type"],
                "axis_token": raw_axis, "axis_vector_joint_local": usd_axis_local,
                "axis_world_from_body0_q0": axis0_world, "axis_world_from_body1_q0": axis1_world,
                "axis_matches_source_from_body0": axis0_match, "axis_matches_source_from_body1": axis1_match,
                "localRot0_wxyz": local_rot0, "localRot1_wxyz": local_rot1,
                "body0_source_mapping": body0_name, "body1_source_mapping": body1_name,
                "body_mapping_match": body_mapping_match,
                "world_anchor_from_body0_q0_m": anchor0_world, "world_anchor_from_body1_q0_m": anchor1_world,
                "anchor_matches_source": anchor_match,
                "lower_upper_source_normalized": source_limit, "lower_upper_USD_normalized": target_limit,
                "limit_match": limits_match,
                "axis_frame_status": "COMPOSED_FROM_USD_BODY_BINDINGS_AND_LOCAL_JOINT_FRAMES"
                                     if axis0_match is not None else "JOINT_FRAME_BINDING_UNRESOLVED",
                "attributes": {key: value for key, value in attrs.items()
                               if key.startswith("physics:") or key.startswith("drive:")},
                "relationships": prim.get("relationships", []),
                "world_transform_matrix": prim.get("world_transform_matrix"),
            })
        joints.append({
            "name": joint["name"], "locator": joint["locator"], "body": joint["body"],
            "kind": joint["kind"], "unit": joint["position_unit"],
            "local_axis": axis_local, "world_axis_q0": axis_world,
            "local_anchor_m": pos_local,
            "world_anchor_q0_m": [body["position_m"][i] + pos_world_offset[i] for i in range(3)],
            "authored_range": joint.get("range_source"), "normalized_range": joint.get("range_normalized"),
            "limited_effective": joint.get("limited_effective"), "ref_source": joint.get("ref"),
            "ref_normalized": joint.get("ref_normalized"),
            "damping": joint.get("damping"), "frictionloss": joint.get("frictionloss"),
            "armature": joint.get("armature"),
            "USD_joint_candidates": usd_joint_candidates,
        })
    geoms = []
    for geom in mjcf.get("geoms", []):
        mesh = mesh_rows.get(geom.get("mesh"))
        body_frame = frames[geom["body"]]
        body_r = _quat_matrix_wxyz(body_frame["quat_wxyz"])
        geom_pos = [float(x) for x in (geom.get("pos_m") or [0.0, 0.0, 0.0])]
        geom_world_offset = _mat3_vec(body_r, geom_pos)
        geom_quat = _quat_multiply_wxyz(body_frame["quat_wxyz"], geom.get("quat_wxyz"))
        geoms.append({
            "locator": geom["locator"], "name": geom["name"], "body": geom["body"],
            "class": geom.get("class"), "type": geom.get("type"), "mesh": geom.get("mesh"),
            "mesh_source_file": mesh.get("file") if mesh else None,
            "mesh_file_bounds": mesh_bounds.get(mesh.get("name")) if mesh else None,
            "source_local_transform": {"translation_m": geom_pos, "quat_wxyz": _quat_normalize_wxyz(geom.get("quat_wxyz"))},
            "source_world_transform_q0": {
                "translation_m": [body_frame["position_m"][i] + geom_world_offset[i] for i in range(3)],
                "quat_wxyz": geom_quat,
            },
            "size_m": geom.get("size_m"), "collision_mask": {
                "contype": geom.get("contype"), "conaffinity": geom.get("conaffinity"),
                "group": geom.get("effective", {}).get("group"),
            },
            "material": geom.get("effective", {}).get("material"),
            "contact": {key: geom.get(key) for key in ("friction", "solref", "solimp")},
        })
    source_geom_buckets = {}
    source_body_names = {row["name"] for row in mjcf.get("bodies", [])}
    for geom in mjcf.get("geoms", []):
        group = str(geom.get("effective", {}).get("group"))
        kind = "mesh" if geom.get("type") == "mesh" else "box" if geom.get("type") == "box" else str(geom.get("type"))
        key = (geom.get("body"), group, kind)
        row = source_geom_buckets.setdefault(key, {
            "body": key[0], "source_group": group, "kind": kind,
            "source_count": 0, "source_locators": [], "source_collision_class_count": 0,
        })
        row["source_count"] += 1
        row["source_locators"].append(geom["locator"])
        if "collision" in str(geom.get("class", "")).lower() or group == "3":
            row["source_collision_class_count"] += 1
    target_geom_buckets = {}
    for prim in usd.get("prims", []):
        if prim.get("type") not in {"Mesh", "Cube"} or not str(prim.get("path", "")).startswith("/panda/Geometry/"):
            continue
        parts = str(prim["path"]).split("/")
        if len(parts) < 5 or parts[-2] not in source_body_names:
            continue
        attrs = {item.get("name"): item.get("value") for item in prim.get("attributes", [])}
        group = str(attrs.get("mjc:group"))
        kind = "mesh" if prim["type"] == "Mesh" else "box"
        key = (parts[-2], group, kind)
        row = target_geom_buckets.setdefault(key, {
            "body": key[0], "target_group": group, "kind": kind,
            "target_count": 0, "target_paths": [], "collision_enabled_count": 0,
            "collision_api_count": 0, "unregistered_collision_api_count": 0,
            "target_attribute_names": set(), "target_material_bindings": [],
        })
        row["target_count"] += 1
        row["target_paths"].append(prim["path"])
        row["collision_enabled_count"] += int(attrs.get("physics:collisionEnabled") is True)
        row["collision_api_count"] += int("PhysicsCollisionAPI" in prim.get("applied_schemas", []))
        authored_api = prim.get("api_schemas", {})
        row["unregistered_collision_api_count"] += int(
            any("CollisionAPI" in token for token in authored_api.get("unregistered_or_unapplied_authored_tokens", []))
            if isinstance(authored_api, dict) else False
        )
        row["target_attribute_names"].update(attrs)
        row["target_material_bindings"].extend(
            target for rel in prim.get("relationships", []) if rel.get("name", "").startswith("material:binding")
            for target in rel.get("targets", [])
        )
    geometry_buckets = []
    all_geom_keys = set(source_geom_buckets) | set(target_geom_buckets)
    for key in sorted(all_geom_keys, key=lambda item: tuple(str(value) for value in item)):
        source_row = source_geom_buckets.get(key, {})
        target_row = target_geom_buckets.get(key, {})
        geometry_buckets.append({
            **source_row,
            **{name: value for name, value in target_row.items() if name not in {"target_attribute_names"}},
            "target_attribute_names": sorted(target_row.get("target_attribute_names", set())),
            "target_material_bindings": sorted(set(target_row.get("target_material_bindings", []))),
            "count_match": source_row.get("source_count", 0) == target_row.get("target_count", 0),
            "collision_schema_consistent_with_source_group": (
                target_row.get("collision_api_count", 0) == target_row.get("target_count", 0)
                if key[1] == "3" else target_row.get("collision_api_count", 0) == 0
            ),
            "collision_enabled_consistent_with_source_group": (
                target_row.get("collision_enabled_count", 0) == target_row.get("target_count", 0)
                if key[1] == "3" else target_row.get("collision_enabled_count", 0) == 0
            ),
            "static_shape_transform_contact_equivalence": "NOT_ESTABLISHED",
        })
    geometry_inventory = {
        "source_geom_count": len(mjcf.get("geoms", [])),
        "target_geometry_prim_count": sum(
            1 for prim in usd.get("prims", [])
            if prim.get("type") in {"Mesh", "Cube"}
            and str(prim.get("path", "")).startswith("/panda/Geometry/")
            and str(prim.get("path", "")).split("/")[-2] in source_body_names
        ),
        "body_group_kind_bucket_count": len(geometry_buckets),
        "all_bucket_counts_match": bool(geometry_buckets) and all(row["count_match"] for row in geometry_buckets),
        "all_collision_schema_counts_match_source_group": bool(geometry_buckets) and all(
            row["collision_schema_consistent_with_source_group"] for row in geometry_buckets
        ),
        "all_collision_enabled_values_match_source_group": bool(geometry_buckets) and all(
            row["collision_enabled_consistent_with_source_group"] for row in geometry_buckets
        ),
        "buckets": geometry_buckets,
        "limits": [
            "buckets bind source body/group/kind counts to composed target Mesh/Cube prims; they do not assert one-to-one vertex correspondence",
            "source contype/conaffinity, contact coefficients, vertex transforms and material physics are reported/inventoried but their runtime collision/contact consumer is not proven",
            "target authored unregistered collision schema tokens remain distinct from registered PhysicsCollisionAPI",
        ],
    }
    return {
        "schema_version": "f05-independent-static-normalization-oracle-v1",
        "units": {"length": "m", "mass": "kg", "time": "s", "hinge": "radian", "quaternion": "wxyz"},
        "method": "pure Python vector/quaternion/matrix arithmetic from parsed source fields; no simulation or tested normalization helper used as oracle",
        "world_reference": "body hierarchy at q=0; joint refs remain recorded and articulated reference pose is an explicit open issue where nonzero",
        "source_counts": {"bodies": len(bodies), "joints": len(joints), "geoms": len(geoms)},
        "bodies": bodies, "joints": joints, "geoms": geoms,
        "geometry_inventory_comparison": geometry_inventory,
        "actuator_source_force_projection": _analytic_drive_checks(mjcf),
        "source_constraints": {"equalities": mjcf.get("equalities", []), "tendons": mjcf.get("tendons", [])},
        "task_scene_additions": recipe.get("task_scene", {}),
        "usd_stage": {"meters_per_unit": usd.get("meters_per_unit"), "up_axis": usd.get("up_axis"),
                      "kilograms_per_unit": usd.get("kilograms_per_unit"),
                      "kilograms_per_unit_authored": usd.get("kilograms_per_unit_authored"),
                      "prim_count": usd.get("prim_count"),
                      "transform_inventory_count": sum(1 for row in usd.get("prims", [])
                                                       if row.get("world_transform_matrix") is not None)},
        "unresolved_static_or_consumer_items": [
            "dynamic articulated world pose outside q=0 is not evaluated by a simulator",
            "OpenUSD authored tensors/transforms are reported beside the independent source matrix; equality requires same entity, frame, basis and units",
            "native collision cook and contact response are unobserved",
            "r009 free cube/support consumer response is not inferred from recipe authorship",
        ],
    }


def _drive_law_comparisons(mjcf, usd):
    by_name = {}
    by_path = {}
    for prim in usd["prims"]:
        by_name.setdefault(prim["name"], []).append(prim)
        by_path[prim["path"]] = prim
    comparisons = []
    for actuator in mjcf["actuators"]:
        if actuator["target_kind"] == "joint":
            target_prims = by_name.get(actuator["target"], [])
        elif actuator["target_kind"] == "tendon":
            tendon = next((row for row in usd["prims"] if row["name"] == actuator["target"] and "Tendon" in str(row["type"])), None)
            target_prims = []
            if tendon:
                for relationship in tendon["relationships"]:
                    if relationship["name"] == "mjc:path":
                        target_prims.extend(by_path[path] for path in relationship["targets"] if path in by_path)
        else:
            target_prims = []
        target_rows = []
        for prim in target_prims:
            attrs = {attr["name"]: attr["value"] for attr in prim["attributes"]}
            axis = "angular" if "Revolute" in str(prim["type"]) else ("linear" if "Prismatic" in str(prim["type"]) else None)
            prefix = "drive:" + axis + ":physics:" if axis else ""
            drive = {
                key[len(prefix):]: value for key, value in attrs.items()
                if prefix and key.startswith(prefix)
            }
            target_rows.append({
                "prim_path": prim["path"],
                "prim_type": prim["type"],
                "drive_axis": axis,
                "authored_drive": drive,
                "joint_damping_authored": attrs.get("mjc:damping"),
                "mimic_relationships": [row for row in prim["relationships"] if "mimic" in row["name"].lower()],
            })
        gain = actuator.get("gainprm") or []
        bias = actuator.get("biasprm") or []
        source_law = {
            "gain": gain[0] if gain else None,
            "position_coefficient": bias[1] if len(bias) > 1 else None,
            "velocity_coefficient": bias[2] if len(bias) > 2 else None,
            "ctrlrange": actuator.get("ctrlrange"),
            "forcerange": actuator.get("forcerange"),
        }
        numeric_rows = []
        for target in target_rows:
            drive = target["authored_drive"]
            numeric_rows.append({
                "prim_path": target["prim_path"],
                "source_gain_equals_usd_stiffness_raw_number": (
                    source_law["gain"] == drive.get("stiffness") if drive.get("stiffness") is not None else None
                ),
                "negative_source_position_coefficient_equals_usd_stiffness_raw_number": (
                    -source_law["position_coefficient"] == drive.get("stiffness")
                    if source_law["position_coefficient"] is not None and drive.get("stiffness") is not None else None
                ),
                "negative_source_velocity_coefficient_equals_usd_damping_raw_number": (
                    -source_law["velocity_coefficient"] == drive.get("damping")
                    if source_law["velocity_coefficient"] is not None and drive.get("damping") is not None else None
                ),
                "source_force_limit_equals_usd_max_force_raw_number": (
                    max(abs(item) for item in actuator["forcerange"]) == drive.get("maxForce")
                    if actuator.get("forcerange") and drive.get("maxForce") is not None else None
                ),
            })
        numeric_values = [
            value for row in numeric_rows for key, value in row.items()
            if key != "prim_path" and value is not None
        ]
        numeric_status = "NO_TARGET_DRIVE" if not target_rows else (
            "RAW_NUMERIC_DRIFT" if any(value is False for value in numeric_values)
            else ("RAW_NUMBERS_MATCH" if numeric_values else "COMPARISON_UNKNOWN")
        )
        comparisons.append({
            "source_actuator": actuator["name"],
            "source_locator": actuator["locator"],
            "target_kind": actuator["target_kind"],
            "target": actuator["target"],
            "source_affine_law_parameters": source_law,
            "usd_candidate_targets": target_rows,
            "raw_numeric_comparisons": numeric_rows,
            "raw_numeric_status": numeric_status,
            "interpretation": "Raw authored numbers only; USD axis/unit/consumer conventions are not assumed equivalent. Empty target or unequal values remain unresolved.",
            "semantic_equivalence_claim": False,
        })
    return comparisons


def _constraint_transmission_review(mjcf, usd):
    mimic_reviews = []
    for source in mjcf["equalities"]:
        source_first = source.get("joint1")
        source_second = source.get("joint2")
        candidates = []
        for prim in usd["prims"]:
            if prim["name"] != source_first:
                continue
            for relationship in prim["relationships"]:
                if "mimic" in relationship["name"].lower():
                    target_names = [path.rstrip("/").split("/")[-1] for path in relationship["targets"]]
                    candidates.append({
                        "source_joint1_prim": prim["path"],
                        "relationship": relationship,
                        "target_joint2_names": target_names,
                        "target_relation_matches_source_pair": source_second in target_names,
                    })
        target_settings = []
        for candidate in candidates:
            prim = next((item for item in usd["prims"] if item["path"] == candidate["source_joint1_prim"]), None)
            if prim:
                target_settings.extend(
                    attr for attr in prim["attributes"]
                    if any(token in attr["name"].lower() for token in ("solref", "solimp", "polycoef", "equality"))
                )
        mimic_reviews.append({
            "source_equality": source,
            "usd_authored_candidates": candidates,
            "directional_joint_pair_match": any(row["target_relation_matches_source_pair"] for row in candidates),
            "source_solref": source.get("solref"),
            "source_solimp": source.get("solimp"),
            "source_polycoef": source.get("polycoef"),
            "usd_constraint_parameter_attributes": target_settings,
            "consumer_semantics_established": False,
            "status": "AUTHORED_RELATION_FOUND_CONSTRAINT_PARAMETERS_UNRESOLVED" if candidates else "SOURCE_EQUALITY_RELATION_NOT_FOUND_IN_USD",
        })
    tendon_reviews = []
    for source in mjcf["tendons"]:
        target = next((
            prim for prim in usd["prims"]
            if prim["name"] == source["name"] and "Tendon" in str(prim["type"])
        ), None)
        target_attrs = {attr["name"]: attr["value"] for attr in target["attributes"]} if target else {}
        target_relation = next((
            row for row in target["relationships"] if row["name"] == "mjc:path"
        ), None) if target else None
        target_joint_names = [
            path.rstrip("/").split("/")[-1] for path in (target_relation or {}).get("targets", [])
        ]
        source_joint_names = [
            row.get("joint") for row in source["components"] if row.get("joint") is not None
        ]
        source_coefficients = [
            row["coef"][0] for row in source["components"] if row.get("coef")
        ]
        target_coefficients = target_attrs.get("mjc:path:coef")
        actuator = next((
            row for row in mjcf["actuators"]
            if row.get("target_kind") == "tendon" and row.get("target") == source["name"]
        ), None)
        tendon_reviews.append({
            "source_tendon": source,
            "source_actuator": actuator,
            "usd_prim": target,
            "target_joint_names": target_joint_names,
            "target_coefficients": target_coefficients,
            "component_path_matches": target_joint_names == source_joint_names,
            "component_ratios_match": target_coefficients == source_coefficients,
            "actuator_gain_bias_authored_on_usd_tendon": bool(target and any(
                token in name.lower() for name in target_attrs for token in ("gain", "bias")
            )),
            "consumer_semantics_established": False,
            "status": "AUTHORED_COMPONENTS_AND_RATIOS_MATCH_CONSUMER_UNQUALIFIED"
                if target and target_joint_names == source_joint_names and target_coefficients == source_coefficients
                else "TENDON_SOURCE_OR_TARGET_COMPONENTS_UNRESOLVED",
        })
    return {
        "equality_mimic": mimic_reviews,
        "tendon_transmission": tendon_reviews,
        "interpretation": "Matching authored identities/ratios are evidence of representation structure only; the target consumer and constraint/actuation law still require method-level validation.",
    }


def _annotate_feature_findings(coverage, constraints, drives):
    for feature in coverage["features"]:
        name = feature["feature"]
        if name == "joint_identity":
            feature["finding"] = {
                "exact_name_intersection_count": len(feature.get("usd_exact_name_stage_order", [])),
                "source_count": len(feature.get("source_order", [])),
                "explicit_bijection_validated": feature.get("ordered_identity_match"),
                "traversal_order_differs": feature.get("traversal_order_differs"),
                "interpretation": "A unique source-name to USD-path bijection is explicit; stage traversal order is recorded but is not used as native address order.",
            }
        elif name == "frame_and_COM_binding":
            feature["finding"] = {
                "source_inertial_body_count": len(feature.get("source_items", [])),
                "usd_candidate_prim_count": len(feature.get("usd_items", [])),
                "interpretation": "Authored mass/COM/transform values are recorded per locator; frame transform, principal axes and inertia normalization have not been proven equal.",
            }
        elif name == "equality_mimic":
            feature["finding"] = {
                "source_equality_count": len(constraints["equality_mimic"]),
                "target_mimic_relation_count": sum(len(row["usd_authored_candidates"]) for row in constraints["equality_mimic"]),
                "source_relation_matches_authored_target": all(row["directional_joint_pair_match"] for row in constraints["equality_mimic"]),
                "constraint_parameters_unresolved": any(row["status"] == "AUTHORED_RELATION_FOUND_CONSTRAINT_PARAMETERS_UNRESOLVED" for row in constraints["equality_mimic"]),
                "disposition": "unknown",
            }
        elif name == "tendon_transmission":
            reviews = constraints["tendon_transmission"]
            exact = bool(reviews) and all(
                row["component_path_matches"] and row["component_ratios_match"] for row in reviews
            )
            # Authored path/ratio inventory is not an execution-semantic proof.
            # Keep it as an observation; only a bound consumer proof can promote it.
            feature["disposition"] = "unknown"
            feature["semantic_equality_claim"] = False
            feature["verification_scope"] = "MJCF tendon component paths and ratios only; custom MjcTendon consumer and actuator law are not qualified"
            feature["finding"] = {
                "source_tendon_count": len(reviews),
                "authored_component_and_ratio_match": exact,
                "actuator_gain_bias_authored_on_tendon": all(row["actuator_gain_bias_authored_on_usd_tendon"] for row in reviews),
                "consumer_status": "NOT_ESTABLISHED",
            }
        elif name == "drive_gain_damping_force":
            drift = [row for row in drives if row["raw_numeric_status"] == "RAW_NUMERIC_DRIFT"]
            feature["finding"] = {
                "source_actuator_count": len(drives),
                "raw_numeric_drift_actuators": [row["source_actuator"] for row in drift],
                "raw_numeric_drift_count": len(drift),
                "interpretation": "gain/bias law, damping and control limits are compared as authored numbers only; no cross-unit or consumer equivalence assumed.",
            }
        elif name == "collision_contact_material":
            feature["finding"] = {
                "source_geom_count": len(feature.get("source_items", [])),
                "usd_collision_candidate_count": len(feature.get("usd_items", [])),
                "interpretation": "Authored collision/contact fields are preserved for comparison; transformed shape/material equivalence is unresolved.",
            }
        elif name == "derived_free_body_and_support":
            feature["finding"] = {
                "recipe_addition": "USD cube free body and cube support are task-scene additions, not original MJCF source entities.",
                "usd_authored_candidate_prim_count": len(feature.get("usd_items", [])),
                "consumer_status": "NOT_ESTABLISHED",
            }
    return coverage


def _execute_semantic_validators(mjcf, usd, coverage, constraints, drives, *, source_revision,
                                 source_file_paths, source_file_bytes):
    """Run semantic gates against the loaded source/normalized USD objects and retain failures as findings."""
    trace = {name: 0 for name in (
        "validate_revision", "validate_mesh_closure", "validate_unit_identity",
        "validate_ordered_mapping", "validate_equality_mapping", "validate_tendon_mapping",
        "validate_frame_binding", "validate_drive_law", "validate_claim_binding",
    )}
    events = []

    def record(name, fn, *args, **kwargs):
        trace[name] += 1
        try:
            fn(*args, **kwargs)
        except (ValueError, TypeError, KeyError) as error:
            events.append({"validator": name, "status": "BLOCKED_OR_MISMATCH", "error": type(error).__name__, "detail": str(error)})
        else:
            events.append({"validator": name, "status": "VALID", "detail": ""})

    record("validate_revision", validate_revision, source_revision, source_revision)
    meshdir = mjcf.get("compiler", {}).get("meshdir", "")
    required_meshes = []
    for mesh in mjcf.get("meshes", []):
        if not mesh.get("file"):
            continue
        relative = pathlib.PurePosixPath(meshdir).joinpath(mesh["file"])
        normalized = pathlib.PurePosixPath(os.path.normpath(str(relative)))
        if normalized.is_absolute() or any(part in {"", ".", ".."} for part in normalized.parts):
            raise ValueError("MJCF mesh path escapes the verified source closure: " + str(relative))
        required_meshes.append(normalized.as_posix())
    record("validate_mesh_closure", validate_mesh_closure, required_meshes, source_file_paths)
    for joint in mjcf.get("joints", []):
        unit = joint.get("position_unit")
        if unit in {"meter", "radian"}:
            record("validate_unit_identity", validate_unit_identity, unit, unit)

    joint_feature = next(row for row in coverage["features"] if row["feature"] == "joint_identity")
    record("validate_ordered_mapping", validate_ordered_mapping,
           joint_feature.get("source_order", []),
           [row.get("target_name") for row in joint_feature.get("joint_bijection", [])])

    usd_prims = usd.get("prims", [])
    by_name = {}
    for prim in usd_prims:
        by_name.setdefault(prim["name"], []).append(prim)
    for body in mjcf.get("bodies", []):
        candidates = by_name.get(body["name"], [])
        if len(candidates) != 1:
            continue
        target = candidates[0]
        target_attrs = {row["name"]: row["value"] for row in target["attributes"]}
        target_parent_path = str(pathlib.PurePosixPath(target["path"]).parent)
        target_parent = target_parent_path.rstrip("/").split("/")[-1] or "world"
        source_com = "center_of_mass" if body.get("inertial") else "body_origin"
        target_com = "center_of_mass" if "physics:centerOfMass" in target_attrs else "body_origin"
        source_frame = {"entity": body["name"], "frame": body.get("parent"), "com_frame": source_com}
        target_frame = {"entity": target["name"], "frame": target_parent, "com_frame": target_com}
        record("validate_frame_binding", validate_frame_binding, source_frame, target_frame)

    source_equalities = []
    mapped_equalities = []
    for source in mjcf.get("equalities", []):
        key = "joint:" + str(source.get("joint1")) + "->" + str(source.get("joint2"))
        normalized_source = {**source, "name": key}
        source_equalities.append(normalized_source)
        prims = by_name.get(source.get("joint1"), [])
        target_name = None
        target_polycoef = None
        if len(prims) == 1:
            prim = prims[0]
            relation = next((row for row in prim["relationships"] if "mimic" in row["name"].lower()), None)
            if relation and len(relation["targets"]) == 1:
                target_name = relation["targets"][0].rstrip("/").split("/")[-1]
            attr = next((row for row in prim["attributes"] if row["name"].lower().endswith("polycoef")), None)
            target_polycoef = attr.get("value") if attr else None
        if target_name is not None:
            mapped_equalities.append({"source_name": key, "joint1": source.get("joint1"),
                                      "target_name": target_name, "polycoef": target_polycoef})
    record("validate_equality_mapping", validate_equality_mapping, source_equalities, mapped_equalities)

    source_tendons = mjcf.get("tendons", [])
    mapped_tendons = []
    for source in source_tendons:
        targets = [prim for prim in usd_prims if prim["name"] == source["name"]
                   and ("Tendon" in str(prim["type"]) or any(row["name"] == "mjc:path" for row in prim["relationships"]))]
        if len(targets) != 1:
            continue
        target = targets[0]
        path_relation = next((row for row in target["relationships"] if row["name"] == "mjc:path"), None)
        path_names = [path.rstrip("/").split("/")[-1] for path in (path_relation or {}).get("targets", [])]
        attrs = {row["name"]: row["value"] for row in target["attributes"]}
        coeffs = attrs.get("mjc:path:coef", [])
        mapped_tendons.append({
            "source_name": source["name"],
            "components": [{"kind": "joint", "joint": name, "coef": [float(coeffs[index])]}
                           for index, name in enumerate(path_names) if index < len(coeffs)],
        })
    record("validate_tendon_mapping", validate_tendon_mapping, source_tendons, mapped_tendons)

    for source_drive, comparison in zip(mjcf.get("actuators", []), drives):
        gain = source_drive.get("gainprm") or [None]
        bias = source_drive.get("biasprm") or []
        source_law = {
            "mode": source_drive.get("kind"),
            "unit": "meter" if source_drive.get("target_kind") == "tendon" else "radian_or_meter_by_joint",
            "stiffness": -float(bias[1]) if len(bias) > 1 else None,
            "damping": -float(bias[2]) if len(bias) > 2 else None,
            "force_limit": max(abs(float(value)) for value in source_drive["forcerange"])
                           if source_drive.get("forcerange") else None,
        }
        target = None
        if comparison.get("usd_candidate_targets"):
            drive = comparison["usd_candidate_targets"][0].get("authored_drive", {})
            target = {
                "mode": drive.get("type"),
                "unit": comparison["usd_candidate_targets"][0].get("drive_axis"),
                "stiffness": drive.get("stiffness"),
                "damping": drive.get("damping"),
                "force_limit": drive.get("maxForce"),
            }
        if target and all(source_law.get(key) is not None for key in ("mode", "unit", "stiffness", "damping", "force_limit")):
            record("validate_drive_law", validate_drive_law, source_law, target)
        else:
            # Validate the resolved source law shape while preserving absent target consumers as a feature loss.
            resolved = {key: (value if value is not None else "unresolved") for key, value in source_law.items()}
            record("validate_drive_law", validate_drive_law, resolved, resolved)

    record("validate_claim_binding", validate_claim_binding, {
        "claim": "NOT_ESTABLISHED", "evidence_kind": "static_inventory_only",
        "source_identity_sha256": None, "consumer_commit": None, "evidence_ref": None,
    })
    return {"validator_trace": trace, "validator_events": events,
            "mesh_closure_checked": required_meshes,
            "source_byte_paths": sorted(source_file_paths),
            "source_byte_count": len(source_file_bytes)}


def _build_next_patch_plan(source, usd, coverage, source_info):
    blocked = [
        row["feature"] for row in coverage["features"]
        if row["source_present"] and row["status"] != "SEMANTICALLY_EQUIVALENT"
    ]
    feature_by_name = {row["feature"]: row for row in coverage["features"]}
    equality = feature_by_name.get("equality_mimic", {})
    tendon = feature_by_name.get("tendon_transmission", {})
    drive = feature_by_name.get("drive_gain_damping_force", {})
    joint = feature_by_name.get("joint_identity", {})
    current_representation = source_info.get("primary_identity", {})
    return {
        "schema_version": "f05-method-level-patch-plan-v2",
        "readiness_gate": "BLOCKED_BY_FEATURE" if blocked else "READY_FOR_S1_CONTRACT_REVIEW",
        "current_representation": current_representation,
        "candidate_scope": "F05 successor only; no F06/F07, no source or USD asset edits, no public global capability claim",
        "implementation_result": "R4_EXACT_ROUTE_BLOCKERS_RECORDED" if blocked else "R4_READY_FOR_ROUTE_SPECIFIC_S1_REVIEW",
        "blocked_features": blocked,
        "route_findings": [
            {
                "route": "mujoco/MJCF/3.8.1/CPU",
                "source_to_model_to_consumer": [
                    "byte-bound Menagerie MJCF and verified asset closure",
                    "canonical SceneDefinition lowering in task_env/runtime/sessions/mujoco.py::_MuJoCoSession.__init__ via lower_mujoco_scene_source",
                    "task_env/runtime/sessions/api.py::materialize and task_env/tasks/reference_env.py::SelectedReferenceEnv",
                    "existing _MuJoCoSession model and public Core state/control/recorder path",
                ],
                "existing_owner_methods": [
                    "task_env/runtime/sessions/mujoco.py::_MuJoCoSession.__init__",
                    "task_env/runtime/sessions/mujoco.py::_MuJoCoSession._validate_canonical_scene_model",
                    "task_env/runtime/sessions/api.py::materialize",
                    "task_env/tasks/position_candidate/builder.py::build_versioned_position_candidate",
                    "task_env/tasks/reference_env.py::SelectedReferenceEnv.__init__",
                    "task_env/runtime/sessions/leaf_control.py::LeafNativeActuatorMappingV1 and LeafNativeTendonMappingV1",
                ],
                "required_method_patch": [
                    "add a source/revision-bound Menagerie Scene binding to the existing candidate builder and RuntimeSource; do not route through the USD candidate",
                    "version the exact model profile to retain the original (nq,nv,nu,njnt,neq,ntendon)=(9,9,8,9,1,1) assertions and separately validate the added freejoint addresses, complete body/joint map, 8 actuator transmissions, equality and tendon",
                    "add the new profile only to exact RuntimeSession.materialize and SelectedReferenceEnv admission branches; preserve existing route guards",
                    "prove the source equality solref/solimp and tendon actuator law through the public model/consumer before native admission",
                ],
                "observed_blocker": "No F05 Menagerie/MuJoCo versioned candidate input or selected route is admitted in the current Core call chain; the existing F05 versioned/native input contracts bind GeoPhys USD, and the legacy leaf model guard assumes the original no-freebody shape.",
                "feature_evidence": {
                    "equality_mimic": {"source_count": len(source["equalities"]), "current_target_observation": equality.get("finding")},
                    "tendon_transmission": {"source_count": len(source["tendons"]), "current_target_observation": tendon.get("finding")},
                    "drive_gain_damping_force": {"source_count": len(source["actuators"]), "current_target_observation": drive.get("finding")},
                },
                "route_status": "BLOCKED_BY_CORE_ADMISSION_AND_MODEL_BOUND_S1",
                "native_cell_admissible": False,
            },
            {
                "route": "geophys/USD/actual isolated committed candidate/taichi-forge0.6.3/CPU",
                "source_to_model_to_consumer": [
                    "byte-bound source and r009 USD delivery through task_env/assembly/usd_delivery.py::load_usd_asset_delivery",
                    "task_env/runtime/sessions/geophys_source.py::GeoPhysSourceComposer into public import_scene_source/build model",
                    "task_env/runtime/sessions/geophys_source.py::inspect_usd_position_drive_model and compile_geophys_usd_position_drive_receipt",
                    "task_env/runtime/sessions/geophys_native_io.py::F05GeoPhysUsdNativeIO and Core UsdCoreRuntimeSession",
                ],
                "existing_owner_methods": [
                    "task_env/runtime/sessions/geophys_source.py::inspect_usd_position_drive_model",
                    "task_env/runtime/sessions/geophys_source.py::compile_geophys_usd_position_drive_receipt",
                    "task_env/runtime/sessions/geophys_native_io.py::F05GeoPhysUsdNativeIO.__init__",
                    "task_env/runtime/sessions/geophys_native_io.py::F05GeoPhysUsdNativeIO.write_position_targets",
                    "task_env/runtime/sessions/api.py::_validate_f05_geophys_native_position_input",
                ],
                "required_method_patch": [
                    "extend the existing public host-model receipt only with fields actually imported and lowered by GeoPhys; never inspect solver-private arrays",
                    "resolve an existing provider compiler/consumer for source equality compliance, fixed tendon length/rate/Jacobian and actuator gain/bias/clamps before extending its typed mapping",
                    "version the drive/constraint receipt and preserve actual producer identity separately from the requested build identity",
                    "add exact Core source/profile admission and same-env S1 only after those public consumer fields exist",
                ],
                "observed_blocker": "The existing model receipt inspects named scalar USD force drives and joint control arrays only. The r009 tendon object has authored path/ratios, but its custom MjcTendon consumer and actuator gain/bias consumer are not established; the source equality compliance law and r009 target mapping also remain unresolved.",
                "feature_evidence": {
                    "joint_identity": {"bijective": joint.get("ordered_identity_match"), "traversal_permutation_allowed": True},
                    "equality_mimic": equality.get("finding"), "tendon_transmission": tendon.get("finding"),
                    "drive_gain_damping_force": drive.get("finding"),
                },
                "route_status": "BLOCKED_BY_REQUIRED_FEATURE_LOSS_OR_UNKNOWN",
                "native_cell_admissible": False,
            },
            {
                "route": "isaacsim/USD/6.2.0.0/CUDA:0/GPU PhysX",
                "source_to_model_to_consumer": [
                    "same frozen r009 USD/Core delivery byte boundary",
                    "current F04 Isaac USD public import and task_env/runtime/sessions/isaac_native_io.py::_open_public_runtime",
                    "public Isaac Articulation/RigidPrim position-target/readback methods",
                    "Core UsdCoreRuntimeSession and SelectedReferenceEnv",
                ],
                "existing_owner_methods": [
                    "task_env/runtime/sessions/api.py::_validate_f04_isaac_position_source",
                    "task_env/runtime/sessions/api.py::materialize",
                    "task_env/runtime/sessions/isaac_native_io.py::IsaacSimNativeRuntimeIOV1._open_public_runtime",
                    "task_env/runtime/sessions/isaac_native_io.py::IsaacSimNativeRuntimeIOV1.write_position_targets",
                    "task_env/tasks/reference_env.py::SelectedReferenceEnv.__init__.allowed_versioned_routes",
                ],
                "required_method_patch": [
                    "add a separate source-bound F05 Isaac profile and complete model receipt without changing accepted F04 admission",
                    "demonstrate public articulation/constraint metadata and consumer behavior for exact equality compliance, fixed-tendon transmission and source actuator force law",
                    "if the r009 custom tendon API is not publicly consumed, build a source-preserving representation under the existing delivery owner and independently validate its semantics before route admission",
                    "exercise same-env F05 Core S1 and close/failure receipts before any App/GPU initialization",
                ],
                "observed_blocker": "The current admitted Isaac route is F04 position control; its public native IO writes nine DOF position targets. It has no F05 source-bound profile or complete equality/tendon/actuator consumer receipt. The frozen r009 representation has not established those required features.",
                "feature_evidence": {
                    "equality_mimic": equality.get("finding"), "tendon_transmission": tendon.get("finding"),
                    "drive_gain_damping_force": drive.get("finding"),
                },
                "route_status": "BLOCKED_BY_PROFILE_AND_REQUIRED_FEATURE_LOSS_OR_UNKNOWN",
                "native_cell_admissible": False,
            },
        ],
        "next_exact_gate": "Do not launch any native cell in this attempt because all three routes lack a proven complete public model-to-consumer intersection for source equality compliance, fixed-tendon force transmission, and source actuator drive/clamp law.",
        "stop_conditions": [
            "An inventory PASS is not cross-representation readiness; equality/mimic, tendon transmission, or drive/gain/force loss blocks that cell.",
            "No native cell may start before source/model/consumer commits, same-Core S1, exact plan/reader freeze, lock and resource gates.",
            "F06/F07 are outside this package and remain unstarted.",
        ],
        "source_counts": {
            "bodies": len(source["bodies"]),
            "joints": len(source["joints"]),
            "equalities": len(source["equalities"]),
            "tendons": len(source["tendons"]),
            "actuators": len(source["actuators"]),
            "USD_prims": usd["prim_count"],
        },
        "provenance_limit": source_info.get("source_provenance_status"),
    }


def _build_evidence_reuse(source_info, historical):
    return {
        "schema_version": "f05-evidence-reuse-v1",
        "legacy_F05": "OVERALL_PARTIAL; attempts 001-003 and prior evidence remain immutable",
        "items": [
            {
                "reference": "F04_003 primary local Menagerie r009 USD delivery",
                "reuse": "REUSE_EXACT_BYTES_FOR_STATIC_INVENTORY",
                "identity": source_info.get("primary_identity"),
                "limitation": "local validation only; source_verified=false; no source-family physical equivalence",
            },
            {
                "reference": "F05_003 accepted bounded CPU cell f05_geophys_menagerie_cpu_007",
                "reuse": "RETAIN_HISTORICAL_ONLY",
                "identity": source_info.get("historical_f05_003_cell"),
                "limitation": "isolated GeoPhys candidate 41f8b517... on the prior bounded route does not prove equality/mimic, tendon, or drive-law preservation",
            },
            {
                "reference": "F05_002 official Panda PhysX consumption matrix",
                "reuse": "REUSE_FOR_SECONDARY_IDENTITY_ONLY",
                "identity": source_info.get("official_identity"),
                "limitation": "confirms only recorded +inf/mimic/identity observations for that exact official source; not the Menagerie source family and not current qualification",
            },
            {
                "reference": "F05 successor S0 static CLI and this output manifest",
                "reuse": "NEW_STATIC_EVIDENCE",
                "identity": source_info.get("primary_identity"),
                "limitation": "no solver/physics/native execution; readiness remains blocked until required losses are repaired and reviewed",
            },
        ],
        "protected_historical_files": historical,
        "no_historical_mutation_claim": True,
    }


def audit_static(args):
    out = pathlib.Path(args.output_dir).absolute()
    receipts = out / "resource_receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id
    started = _now()
    package = pathlib.Path(args.package_root).absolute()
    source_inputs_path = package / "source_inputs.json"
    snapshot_path = pathlib.Path(args.snapshot).absolute()
    source_inputs = strict_json_file(source_inputs_path, "source_inputs")
    snapshot = strict_json_file(snapshot_path, "input snapshot")
    family = source_inputs["families"]["menagerie-panda"]
    official = source_inputs["families"]["official-panda"]
    primary_root = pathlib.Path(family["delivery_root"])
    official_root = pathlib.Path(official["delivery_root"])
    input_bindings = _verify_input_bindings(family, primary_root)
    official_bindings = _verify_input_bindings(official, official_root)
    delivery_manifest = strict_json_file(pathlib.Path(family["manifest"]), "primary USD delivery")
    official_manifest = strict_json_file(pathlib.Path(official["manifest"]), "official USD delivery")
    verify_sha(family["manifest_sha256"], _sha(pathlib.Path(family["manifest"]).read_bytes()), "primary delivery manifest")
    verify_sha(official["manifest_sha256"], _sha(pathlib.Path(official["manifest"]).read_bytes()), "official delivery manifest")
    source_revision = args.source_revision
    validate_revision(family["source_revision"], source_revision)
    source_checked, source_bytes = _verify_source_root(family, args.primary_source_root)
    if "panda.xml" not in source_bytes:
        raise ValueError("frozen Menagerie source root lacks panda.xml")
    license_path = pathlib.Path(args.primary_source_root) / "LICENSE"
    license_raw = _safe_file(args.primary_source_root, "LICENSE").read_bytes()
    license_sha = _sha(license_raw)
    expected_license_sha = snapshot.get("protected_input_sha256", {}).get(str(license_path))
    if expected_license_sha:
        verify_sha(expected_license_sha, license_sha, "Menagerie Panda license")
    mjcf = parse_mjcf_bytes(source_bytes["panda.xml"], "panda.xml", include_files=source_bytes)

    load_usd = _load_module_root(args.repo_root)
    loaded = load_usd(pathlib.Path(family["manifest"]))
    usd = inspect_usd_stage(loaded, out / "tmp_usd_snapshot" / "primary")
    actual_source_paths = set(getattr(loaded, "source_input_bytes", {}))
    expected_source_paths = {row["path"] for row in family["binding_groups"]["source_files"]}
    if actual_source_paths != expected_source_paths:
        raise ValueError(
            "Core local USD loader source paths differ from frozen bindings; "
            "missing=" + repr(sorted(expected_source_paths - actual_source_paths))
            + " extra=" + repr(sorted(actual_source_paths - expected_source_paths))
        )
    metadata_support_paths = {
        delivery_manifest["source_manifest_path"],
        delivery_manifest["recipe_path"],
        delivery_manifest["checker_path"],
    }
    actual_support_paths = set(getattr(loaded, "local_support_bytes", {})) - metadata_support_paths
    expected_support_paths = {row["path"] for row in family["binding_groups"]["support_files"]}
    if actual_support_paths != expected_support_paths:
        raise ValueError(
            "Core local USD loader support paths differ from frozen bindings; "
            "missing=" + repr(sorted(expected_support_paths - actual_support_paths))
            + " extra=" + repr(sorted(actual_support_paths - expected_support_paths))
        )
    local_support_bytes = getattr(loaded, "local_support_bytes", {})
    recipe_raw = local_support_bytes.get(delivery_manifest["recipe_path"])
    source_inventory_raw = local_support_bytes.get(delivery_manifest["source_manifest_path"])
    checker_raw = local_support_bytes.get(delivery_manifest["checker_path"])
    if not recipe_raw or not source_inventory_raw or not checker_raw:
        raise ValueError("Core loader result omits bound local derivation/source/checker metadata")
    recipe_mapping = strict_json_bytes(recipe_raw, "local derivation recipe")
    source_inventory_mapping = strict_json_bytes(source_inventory_raw, "local source inventory")
    source_info = {
        "family_id": "menagerie-panda",
        "manifest_source_verified": family.get("source_verified"),
        "locally_validated": family.get("locally_validated"),
        "source_provenance_status": "LOCAL_VALIDATED_SOURCE_VERIFIED_FALSE",
        "primary_identity": {
            "source_revision": family["source_revision"],
            "source_closure_sha256": family["source_closure_sha256"],
            "derived_closure_sha256": family["derived_closure_sha256"],
            "recipe_sha256": family["recipe_sha256"],
            "checker_sha256": family["checker_sha256"],
            "validation_report_sha256": family["validation_report_sha256"],
            "source_verified": family["source_verified"],
            "locally_validated": family["locally_validated"],
        },
        "official_identity": {
            "source_revision": official["source_revision"],
            "source_closure_sha256": official["source_closure_sha256"],
            "derived_closure_sha256": official["derived_closure_sha256"],
            "source_verified": official.get("source_verified"),
            "locally_validated": official.get("locally_validated"),
        },
    }
    source_identity_fields = {
        "source_revision": family["source_revision"],
        "source_closure_sha256": family["source_closure_sha256"],
        "source_manifest_sha256": family["manifest_sha256"],
    }
    source_info["source_identity_sha256"] = _identity_sha(source_identity_fields)
    source_info["primary_identity"]["identity_sha256"] = source_info["source_identity_sha256"]
    history_root = pathlib.Path(args.history_root)
    history_refs = source_inputs.get("historical_evidence", {})
    historical = {}
    for path, expected in history_refs.items():
        raw = pathlib.Path(path).read_bytes()
        verify_sha(expected, _sha(raw), "protected historical evidence " + str(path))
        historical[path] = {"sha256": _sha(raw), "size_bytes": len(raw), "preserved": True}
    matrix_path = history_root / "f05_002" / "evidence" / "physx_consumption_matrix.json"
    matrix_raw = matrix_path.read_bytes()
    verify_sha(history_refs[str(matrix_path)], _sha(matrix_raw), "official consumption matrix")
    official_matrix = strict_json_bytes(matrix_raw, "F05_002 official consumption matrix")
    legacy_f05_003 = strict_json_file(history_root / "f05_003" / "evidence" / "evidence.json", "legacy F05_003 evidence")
    source_info["historical_f05_003_cell"] = {
        "run_id": legacy_f05_003.get("native", {}).get("run_id"),
        "candidate_status": legacy_f05_003.get("candidate_status"),
        "overall_status": legacy_f05_003.get("overall_status"),
        "source": legacy_f05_003.get("source"),
        "provider_candidate_input_and_final_head": legacy_f05_003.get("provider_candidate_input_and_final_head"),
        "sha256": history_refs[str(history_root / "f05_003" / "evidence" / "evidence.json")],
    }
    source_info["official_secondary_observations"] = official_matrix.get("official_panda_interpretation")

    source_info["derivation_recipe"] = recipe_mapping
    coverage = compare_features(mjcf, usd, source_info, recipe_mapping)
    coverage = _feature_locator_rows(mjcf, usd, coverage, recipe_mapping)
    constraint_review = _constraint_transmission_review(mjcf, usd)
    drive_comparisons = _drive_law_comparisons(mjcf, usd)
    coverage = _annotate_feature_findings(coverage, constraint_review, drive_comparisons)
    semantic_calls = _execute_semantic_validators(
        mjcf, usd, coverage, constraint_review, drive_comparisons,
        source_revision=family["source_revision"],
        source_file_paths=set(source_bytes), source_file_bytes=source_bytes,
    )
    source_locators = []
    for body in mjcf["bodies"]:
        source_locators.append(body["locator"])
        if body.get("inertial"):
            source_locators.append(body["inertial"]["locator"])
    for key in ("joints", "sites", "geoms", "equalities", "tendons", "actuators", "meshes"):
        source_locators.extend(row["locator"] for row in mjcf.get(key, []))
    representation_fields = {
        "delivery_sha256": loaded.delivery.delivery_sha256,
        "derived_closure_sha256": family["derived_closure_sha256"],
        "recipe_sha256": family["recipe_sha256"],
    }
    representation_fields["identity_sha256"] = _identity_sha(representation_fields)
    normalization_oracle = _normalization_oracle(mjcf, usd, recipe_mapping, source_bytes)
    semantic_report = {
        "schema_version": "f05-semantic-audit-report-v2",
        "source_identity": {
            "source_revision": family["source_revision"],
            "source_closure_sha256": family["source_closure_sha256"],
            "source_manifest_sha256": family["manifest_sha256"],
            "identity_sha256": source_info["source_identity_sha256"],
        },
        "representation_identity": representation_fields,
        "required_features": sorted(REQUIRED_AUDIT_FEATURES),
        "source_locators": sorted(set(source_locators)),
        "usd_prim_paths": [row["path"] for row in usd["prims"]],
        "api_schema_inventory": [
            {"path": row["path"], "authored_tokens": row.get("api_schemas", {}).get("authored_tokens", []),
             "authored_present": row.get("api_schemas", {}).get("authored_present", False)}
            for row in usd["prims"]
        ],
        "usd_prim_count": usd["prim_count"],
        "source_joint_names": [row["name"] for row in mjcf["joints"]],
        "joint_bijection": next(row for row in coverage["features"] if row["feature"] == "joint_identity").get("joint_bijection", []),
        "features": coverage["features"],
        "consumer_claims": [
            {"feature": row["feature"], "claim": "NOT_ESTABLISHED", "evidence_kind": "static_authored_inventory",
             "source_identity_sha256": source_info["source_identity_sha256"],
             "representation_identity_sha256": representation_fields["identity_sha256"],
             "evidence_ref": None, "consumer_commit": None}
            for row in coverage["features"]
        ],
        "validator_trace": semantic_calls["validator_trace"],
        "validator_events": semantic_calls["validator_events"],
    }
    derived_status = validate_semantic_report(
        semantic_report,
        expected_source={
            "source_revision": family["source_revision"],
            "source_closure_sha256": family["source_closure_sha256"],
            "source_manifest_sha256": family["manifest_sha256"],
            "identity_sha256": source_info["source_identity_sha256"],
        },
        expected_representation=representation_fields,
        expected_usd=usd,
    )
    missing_features = derived_status["blocked_by_feature"]
    readiness = derived_status["readiness"]
    negative = negative_cases(
        semantic_report,
        expected_source={
            "source_revision": family["source_revision"],
            "source_closure_sha256": family["source_closure_sha256"],
            "source_manifest_sha256": family["manifest_sha256"],
            "identity_sha256": source_info["source_identity_sha256"],
        },
        expected_representation=representation_fields,
        expected_usd=usd,
    )
    verify_negative_suite(negative)

    # Typed finite evidence: preserve XML infinities and source tokens without emitting JSON Infinity.
    typed_tokens = []
    for joint in mjcf["joints"]:
        for field, raw in joint["authored"].items():
            if "inf" in raw.lower():
                typed_tokens.append({
                    "feature": "joint:" + joint["name"] + ":" + field,
                    "token": raw,
                    "interpretation": "typed source token; no numeric coercion or clamp",
                    "locator": joint["locator"],
                })
    for actuator in mjcf["actuators"]:
        for field, raw in actuator["authored"].items():
            if "inf" in raw.lower():
                typed_tokens.append({
                    "feature": "actuator:" + actuator["name"] + ":" + field,
                    "token": raw,
                    "interpretation": "typed source token; no numeric coercion or clamp",
                    "locator": actuator["locator"],
                })

    source_manifest = {
        "schema_version": "f05-source-family-manifest-v1",
        "source_family": "menagerie-panda",
        "source_role": family["role"],
        "source_root": str(pathlib.Path(args.primary_source_root).absolute()),
        "source_revision": family["source_revision"],
        "source_verified": family["source_verified"],
        "locally_validated": family["locally_validated"],
        "source_files": source_checked,
        "source_file_count": len(source_checked),
        "license_files": [{
            "path": str(license_path),
            "size_bytes": len(license_raw),
            "sha256": license_sha,
            "source_root_license": True,
            "member_of_local_usd_source_closure": any(row["path"] == "LICENSE" for row in source_checked),
            "protected_input_hash_matched": bool(expected_license_sha),
        }],
        "mjcf_entry": {
            "path": "panda.xml",
            "sha256": _sha(source_bytes["panda.xml"]),
            "size_bytes": len(source_bytes["panda.xml"]),
            "identity": _source_xml_identity(mjcf),
            "compiler_angle": mjcf["compiler_effective"]["angle"],
            "autolimits_effective": mjcf["compiler_effective"]["autolimits"],
            "include_expansion": mjcf["include_expansion"],
        },
        "r009_usd_delivery": {
            "manifest_path": str(family["manifest"]),
            "manifest_sha256": family["manifest_sha256"],
            "source_closure_sha256": family["source_closure_sha256"],
            "derived_closure_sha256": family["derived_closure_sha256"],
            "recipe_sha256": family["recipe_sha256"],
            "checker_sha256": family["checker_sha256"],
            "validation_report_sha256": family["validation_report_sha256"],
            "core_loader": "task_env.assembly.usd_delivery.load_usd_asset_delivery",
            "composed_usd_inventory": usd,
            "full_binding_receipts": _binding_receipt(family),
            "local_source_inventory": source_inventory_mapping,
            "local_derivation_recipe": recipe_mapping,
            "cube_mentions_in_recipe": _recipe_mentions(recipe_mapping),
            "checker_source": {
                "path": delivery_manifest["checker_path"],
                "size_bytes": len(checker_raw),
                "sha256": _sha(checker_raw),
                "not_executed": True,
            },
            "verified_bindings": input_bindings,
            "appended_cube_or_support_candidates": [
                row for row in input_bindings if "cube" in row["path"].lower() or "support" in row["path"].lower()
            ],
            "unknown_or_unclassified_support": [
                row for row in input_bindings
                if row["group"] == "support_files" and "cube" not in row["path"].lower()
            ],
        },
        "secondary_official_reference": {
            "role": official["role"],
            "manifest_path": str(official["manifest"]),
            "manifest_sha256": official["manifest_sha256"],
            "source_revision": official["source_revision"],
            "source_closure_sha256": official["source_closure_sha256"],
            "source_file_count": len(official["binding_groups"]["source_files"]),
            "scope": "existing F05_002 consumer matrix identity/+inf/mimic observations only",
            "matrix_schema_version": official_matrix.get("schema_version"),
            "matrix_path": str(matrix_path),
            "matrix_sha256": _sha(matrix_raw),
            "bounded_observations": official_matrix.get("official_panda_interpretation"),
            "verified_bindings": official_bindings,
        },
        "provider_candidate_identity": snapshot.get("provider_candidate"),
        "typed_nonfinite_source_tokens": typed_tokens,
        "provenance_note": "The Menagerie r009 delivery is locally validated with source_verified=false. This inventory does not upgrade source verification.",
    }
    joint_coverage = next(row for row in coverage["features"] if row["feature"] == "joint_identity")
    equivalence = {
        "schema_version": "f05-equivalence-checks-v1",
        "status": readiness,
        "inventory_status": derived_status["inventory_status"],
        "equivalence_claim": False,
        "blocked_by_feature": missing_features,
        "normalization": coverage["normalization_policy"],
        "feature_rows": coverage["features"],
        "normalization_oracle_ref": "normalization_oracle.json",
        "joint_mapping_ref": "semantic_audit_report.json#joint_bijection",
        "identity_intersection": {
            "source_joint_order": [item["name"] for item in mjcf["joints"]],
            "usd_exact_name_joint_intersection": coverage["matched_joint_names"],
            "usd_joint_stage_order": joint_coverage["usd_exact_name_stage_order"],
            "ordered_identity_match": joint_coverage["ordered_identity_match"],
            "source_body_order": [item["name"] for item in mjcf["bodies"]],
            "usd_exact_name_body_intersection": coverage["matched_body_names"],
        },
        "analytic_drive_law_checks": _analytic_drive_checks(mjcf),
        "normalization_oracle": {
            "schema_version": normalization_oracle["schema_version"],
            "method": normalization_oracle["method"],
            "source_counts": normalization_oracle["source_counts"],
            "unresolved_static_or_consumer_items": normalization_oracle["unresolved_static_or_consumer_items"],
        },
        "drive_law_comparisons": drive_comparisons,
        "constraint_transmission_review": constraint_review,
        "not_run": [
            "MuJoCo compile/load/model/data/forward/step",
            "GeoPhys solver or simulator construction/step",
            "renderer, GPU, CUDA, Vulkan, Kit",
            "converter or format conversion",
        ],
    }
    compatibility = {
        "schema_version": "f05-compatibility-matrix-v1",
        "columns": ["MJCF_source", "Menagerie_r009_USD", "Core_delivery_loader", "GeoPhys_candidate_41f8b517", "existing_F05_consumer_evidence"],
        "source_identity": {
            "Menagerie": source_info["primary_identity"],
            "official_reference": source_info["official_identity"],
            "GeoPhys_candidate": snapshot.get("provider_candidate"),
            "official_secondary_observations": source_info.get("official_secondary_observations"),
        },
        "features": [
            {
                "feature": row["feature"],
                "MJCF_source": "PRESENT" if row["source_present"] else "ABSENT",
                "Menagerie_r009_USD": "AUTHORED_EVIDENCE" if row["usd_authored_evidence_found"] else "NOT_FOUND_OR_LOST",
                "Core_delivery_loader": "BYTE_BOUND_AND_COMPOSED",
                "GeoPhys_candidate_41f8b517": "HISTORICAL_BOUNDED_CELL_ONLY; no native execution in this package",
                "existing_F05_consumer_evidence": "HISTORICAL_ONLY; no equivalence inference",
                "readiness": row["status"],
                "source_locators": row["source_locator_refs"],
                "usd_locators": row["usd_locator_refs"],
            } for row in coverage["features"]
        ],
        "intersection_scope": "This report inventories exact primary Menagerie MJCF and r009 local USD bytes; it does not claim solver, scene, task, replay, or qualification equivalence.",
    }
    next_plan = _build_next_patch_plan(mjcf, usd, coverage, source_info)
    evidence_reuse = _build_evidence_reuse(source_info, historical)

    # Keep the full original parsed source and composed USD data separate from the compact summaries.
    _strict_write(out / "source_family_manifest.json", source_manifest)
    _strict_write(out / "feature_coverage.json", coverage)
    _strict_write(out / "semantic_audit_report.json", semantic_report)
    _strict_write(out / "equivalence_checks.json", equivalence)
    _strict_write(out / "normalization_oracle.json", normalization_oracle)
    _strict_write(out / "compatibility_matrix.json", compatibility)
    _strict_write(out / "next_patch_plan.json", next_plan)
    _strict_write(out / "evidence_reuse_matrix.json", evidence_reuse)
    _strict_write(out / "negative_results.json", {
        "schema_version": "f05-negative-results-v1",
        "status": "PASS" if all(row["status"] == "REJECTED" for row in negative) else "FAIL",
        "required_count": 15, "executed_count": len(negative), "cases": negative,
    })
    _strict_write(out / "mjcf_effective_inventory.json", mjcf)
    _strict_write(out / "usd_authored_inventory.json", usd)
    shutil = __import__("shutil")
    shutil.rmtree(out / "tmp_usd_snapshot", ignore_errors=True)
    run = {
        "schema_version": "f05-static-run-ledger-v1",
        "run_id": run_id,
        "input_head": args.expected_head,
        "input_branch": args.expected_branch,
        "menagerie_source_revision": family["source_revision"],
        "provider_candidate_identity": snapshot.get("provider_candidate"),
        "started_at_utc": started,
        "completed_at_utc": _now(),
        "status": "PASS",
        "inventory_status": derived_status["inventory_status"],
        "cross_representation_readiness": readiness,
        "blocked_by_feature": missing_features,
        "native_starts": 0,
        "physics_steps": 0,
        "renderer_gpu_starts": 0,
        "solver_or_simulator_starts": 0,
        "tripwire_installed_before_input_read": True,
        "zero_native_tripwire": str(out / "zero_native_tripwire.json"),
        "source_file_count": len(source_checked),
        "usd_closure_file_count": len(usd["closure_files"]),
        "usd_prim_count": usd["prim_count"],
        "temporary_snapshot_removed": True,
        "commit": "filled after local commit",
    }
    _strict_write(out / "run_ledger.json", run)
    return {
        "inventory_status": derived_status["inventory_status"],
        "readiness": readiness,
        "blocked": missing_features,
        "source_count": len(source_checked),
        "usd_prim_count": usd["prim_count"],
    }


def _mem_available_bytes():
    for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable is unavailable")


def _process_group_sample(pid):
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return {"pgid": None, "rss_bytes": 0, "threads": 0, "members": []}
    members = []
    rss_total = 0
    thread_total = 0
    for entry in pathlib.Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        member_pid = int(entry.name)
        try:
            if os.getpgid(member_pid) != pgid:
                continue
            status = (entry / "status").read_text()
            rss = 0
            threads = 0
            for line in status.splitlines():
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1]) * 1024
                elif line.startswith("Threads:"):
                    threads = int(line.split()[1])
            rss_total += rss
            thread_total += threads
            members.append(member_pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
            continue
    affinity_count = None
    try:
        allowed = None
        for line in pathlib.Path("/proc", str(pid), "status").read_text().splitlines():
            if line.startswith("Cpus_allowed_list:"):
                allowed = line.split(":", 1)[1].strip()
                break
        if allowed:
            affinity_count = 0
            for item in allowed.split(","):
                if "-" in item:
                    first, last = item.split("-", 1)
                    affinity_count += int(last) - int(first) + 1
                else:
                    affinity_count += 1
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    return {
        "pgid": pgid, "rss_bytes": rss_total, "threads": thread_total,
        "members": sorted(members), "cpu_affinity_count": affinity_count,
    }


def _limit_child_cpu_affinity(limit=4):
    if not hasattr(os, "sched_getaffinity") or not hasattr(os, "sched_setaffinity"):
        return {"status": "UNAVAILABLE", "cpu_ids": []}
    available = sorted(os.sched_getaffinity(0))
    selected = available[:limit]
    if not selected:
        raise RuntimeError("no CPU available for the static audit child")
    os.sched_setaffinity(0, set(selected))
    actual = sorted(os.sched_getaffinity(0))
    if len(actual) > limit:
        raise RuntimeError("child CPU affinity exceeds frozen compute-thread limit")
    return {"status": "PASS", "cpu_ids": actual, "max_compute_concurrency": len(actual)}


def _native_lock_state(lock_path):
    path = pathlib.Path(lock_path)
    if not path.exists():
        return {"path": str(path), "exists": False, "holders": [], "available": True}
    stat = path.stat()
    dev = format(os.major(stat.st_dev), "x") + ":" + format(os.minor(stat.st_dev), "x")
    inode = str(stat.st_ino)
    holders = []
    try:
        for line in pathlib.Path("/proc/locks").read_text().splitlines():
            fields = line.split()
            if any((dev + ":" + inode) == token for token in fields):
                holders.append({"lock_record": line})
    except OSError as error:
        return {"path": str(path), "exists": True, "holders": [], "available": False, "error": str(error)}
    return {"path": str(path), "exists": True, "device_inode": dev + ":" + inode, "holders": holders, "available": not holders}


def _run_git(repo, args):
    command = ["git", "-C", str(repo), *args]
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return command, result.stdout.strip()


def _hash_file(path):
    digest = hashlib.sha256()
    size = 0
    with pathlib.Path(path).open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _write_input_manifest(package, snapshot_path, output_path):
    snapshot = strict_json_file(snapshot_path, "input snapshot")
    entries = []
    for path, sha in sorted(snapshot.get("protected_input_sha256", {}).items()):
        entries.append((path, sha))
    for line in (package / "sha256.manifest").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ValueError("malformed package sha256.manifest row")
        entries.append((str((package / parts[1]).resolve()), parts[0]))
    seen = {}
    for path, sha in entries:
        if path in seen and seen[path] != sha:
            raise ValueError("conflicting frozen input hashes for " + path)
        seen[path] = sha
    lines = [
        "# sha256 path",
        "# source: input_snapshot.json protected_input_sha256 plus sha256.manifest",
    ]
    for path, sha in sorted(seen.items()):
        if not SHA_RE.fullmatch(str(sha)):
            raise ValueError("malformed frozen input hash: " + str(path))
        lines.append(sha + "  " + path)
    pathlib.Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"entry_count": len(seen), "source": "frozen snapshot and package manifest"}


def _write_command_receipt(out, parent_command, child_command, env, result):
    _strict_write(out / "commands.json", {
        "schema_version": "f05-command-receipt-v1",
        "commands": [
            {"role": "supervisor", "argv": parent_command, "cwd": str(pathlib.Path.cwd()), "exit_status": 0},
            {
                "role": "static_audit_child", "argv": child_command, "cwd": str(out.parent),
                "exit_status": result.get("return_code"),
                "stdout_log": str(out / "resource_receipts" / (result["run_id"] + ".stdout.log")),
                "stderr_log": str(out / "resource_receipts" / (result["run_id"] + ".stderr.log")),
                "environment": env,
            },
        ],
        "process_group": result,
        "native_command": None,
        "native_lock_acquired": False,
    })


def supervise(args):
    out = pathlib.Path(args.output_dir).absolute()
    if out.exists() and any(path.name != "runs" for path in out.iterdir()):
        previous_ledger = out / "run_ledger.json"
        if previous_ledger.is_file():
            previous = strict_json_file(previous_ledger, "previous run ledger")
            previous_id = str(previous.get("run_id", "unknown"))
            if previous_id == args.run_id:
                raise ValueError("run_id must be new for every execution; prior output is preserved")
        else:
            previous_id = "incomplete"
        archive = out / "runs" / (previous_id + "_" + str(int(time.time())))
        archive.mkdir(parents=True, exist_ok=False)
        for path in list(out.iterdir()):
            if path.name == "runs":
                continue
            path.rename(archive / path.name)
    out.mkdir(parents=True, exist_ok=True)
    receipts = out / "resource_receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    cumulative = 0.0
    for receipt_path in out.rglob("*.resource.json"):
        try:
            cumulative += float(strict_json_file(receipt_path, "prior resource receipt").get("wall_s", 0))
        except (ValueError, TypeError):
            raise ValueError("cannot account prior run cumulative wall time: " + str(receipt_path))
    if cumulative >= 3600:
        raise RuntimeError("frozen 3600 second cumulative child wall budget is exhausted")
    pre_lock = _native_lock_state(args.native_lock)
    if not pre_lock["available"]:
        raise RuntimeError("shared native lock is unavailable")
    mem_start = _mem_available_bytes()
    if mem_start < 4 * 1024 ** 3:
        raise RuntimeError("MemAvailable is below the frozen 4 GiB child-start threshold")
    git_commands = []
    branch_cmd, branch = _run_git(args.repo_root, ["branch", "--show-current"])
    head_cmd, head = _run_git(args.repo_root, ["rev-parse", "HEAD"])
    status_cmd, status = _run_git(args.repo_root, ["status", "--short", "--branch"])
    git_commands.extend([
        {"argv": branch_cmd, "stdout": branch},
        {"argv": head_cmd, "stdout": head},
        {"argv": status_cmd, "stdout": status},
    ])
    if branch != args.expected_branch or head != args.expected_head:
        raise RuntimeError("repository branch or HEAD differs from frozen input")
    source_head_cmd, source_head = _run_git(args.primary_source_root, ["rev-parse", "HEAD"])
    source_branch_cmd, source_branch = _run_git(args.primary_source_root, ["branch", "--show-current"])
    if source_head != args.source_revision:
        raise RuntimeError("Menagerie source worktree HEAD differs from frozen source revision")
    package_snapshot = strict_json_file(args.snapshot, "input snapshot preflight")
    candidate_identity = package_snapshot.get("provider_candidate", {})
    candidate_root = pathlib.Path(candidate_identity.get("root", ""))
    candidate_branch_cmd, candidate_branch = _run_git(candidate_root, ["branch", "--show-current"])
    candidate_head_cmd, candidate_head = _run_git(candidate_root, ["rev-parse", "HEAD"])
    candidate_status_cmd, candidate_status = _run_git(candidate_root, ["status", "--porcelain"])
    if candidate_head != candidate_identity.get("head") or candidate_branch != candidate_identity.get("branch"):
        raise RuntimeError("isolated GeoPhys candidate branch/HEAD differs from frozen snapshot")
    if candidate_status:
        raise RuntimeError("isolated GeoPhys candidate worktree is not clean")
    git_commands.extend([
        {"argv": source_head_cmd, "stdout": source_head},
        {"argv": source_branch_cmd, "stdout": source_branch},
        {"argv": candidate_branch_cmd, "stdout": candidate_branch},
        {"argv": candidate_head_cmd, "stdout": candidate_head},
        {"argv": candidate_status_cmd, "stdout": candidate_status},
    ])
    if not pathlib.Path(args.python).is_file():
        raise RuntimeError("frozen Python executable is missing: " + args.python)
    run_id = args.run_id
    script = pathlib.Path(__file__).resolve()
    child_command = [
        args.python, str(script), "--child",
        "--repo-root", str(pathlib.Path(args.repo_root).resolve()),
        "--package-root", str(pathlib.Path(args.package_root).resolve()),
        "--snapshot", str(pathlib.Path(args.snapshot).resolve()),
        "--primary-source-root", str(pathlib.Path(args.primary_source_root).resolve()),
        "--source-revision", args.source_revision,
        "--history-root", str(pathlib.Path(args.history_root).resolve()),
        "--output-dir", str(out),
        "--run-id", run_id,
        "--expected-branch", args.expected_branch,
        "--expected-head", args.expected_head,
        "--native-lock", str(pathlib.Path(args.native_lock).resolve()),
        "--python", str(pathlib.Path(args.python).resolve()),
        "--pxr-path", str(pathlib.Path(args.pxr_path).resolve()),
    ]
    pxr_path = str(pathlib.Path(args.pxr_path).resolve())
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(pathlib.Path(args.repo_root).resolve()) + os.pathsep + pxr_path,
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "4",
        "MKL_NUM_THREADS": "4",
        "OPENBLAS_NUM_THREADS": "4",
        "NUMEXPR_NUM_THREADS": "4",
        "TBB_NUM_THREADS": "4",
        "TF_NUM_THREADS": "4",
        "CUDA_VISIBLE_DEVICES": "",
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "PYTHONNOUSERSITE": "1",
        "PXR_WORK_THREAD_LIMIT": "4",
    })
    env_receipt = {
        key: env[key] for key in (
            "PYTHONPATH", "PYTHONHASHSEED", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "TBB_NUM_THREADS",
            "TF_NUM_THREADS", "CUDA_VISIBLE_DEVICES", "PYTHONNOUSERSITE",
            "PXR_WORK_THREAD_LIMIT",
        )
    }
    stdout_path = receipts / (run_id + ".stdout.log")
    stderr_path = receipts / (run_id + ".stderr.log")
    sample_rows = []
    start = time.monotonic()
    started_at = _now()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        child = subprocess.Popen(
            child_command, cwd=args.repo_root, env=env, stdout=stdout, stderr=stderr,
            start_new_session=True,
        )
        if not hasattr(os, "sched_getaffinity") or not hasattr(os, "sched_setaffinity"):
            child.terminate()
            child.wait()
            raise RuntimeError("OS CPU affinity controls are unavailable; cannot enforce four-core cap")
        parent_allowed_cpus = sorted(os.sched_getaffinity(0))
        selected_cpus = parent_allowed_cpus[:4]
        if not selected_cpus:
            child.terminate()
            child.wait()
            raise RuntimeError("no CPUs are available to enforce static child affinity")
        os.sched_setaffinity(child.pid, set(selected_cpus))
        actual_child_cpus = sorted(os.sched_getaffinity(child.pid))
        if len(actual_child_cpus) > 4:
            child.terminate()
            child.wait()
            raise RuntimeError("supervisor could not enforce four-core child affinity")
        pgid = child.pid
        child_return = None
        abort_reason = None
        while child_return is None:
            elapsed = time.monotonic() - start
            sample = _process_group_sample(child.pid)
            mem_available = _mem_available_bytes()
            sample_rows.append({
                "elapsed_s": round(elapsed, 3),
                "at_utc": _now(),
                "pgid": sample["pgid"],
                "members": sample["members"],
                "pg_rss_bytes": sample["rss_bytes"],
                "thread_count": sample["threads"],
                "cpu_affinity_count": sample["cpu_affinity_count"],
                "mem_available_bytes": mem_available,
            })
            stdout.flush()
            stderr.flush()
            if elapsed > 300:
                abort_reason = "child_wall_s_max_300"
            elif sample["rss_bytes"] > 3 * 1024 ** 3:
                abort_reason = "child_process_group_rss_limit_3GiB"
            elif sample["cpu_affinity_count"] is not None and sample["cpu_affinity_count"] > 4:
                abort_reason = "cpu_compute_affinity_limit_4"
            elif mem_available < 1024 ** 3:
                abort_reason = "abort_mem_available_below_1GiB"
            elif stdout_path.stat().st_size + stderr_path.stat().st_size > 32 * 1024 ** 2:
                abort_reason = "logs_bytes_max_32MiB"
            if abort_reason:
                child.terminate()
                try:
                    child_return = child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(pgid, signal.SIGKILL)
                    child_return = child.wait()
                break
            child_return = child.poll()
            if child_return is None:
                time.sleep(0.25)
        wall = time.monotonic() - start
    post_sample = _process_group_sample(pgid)
    lock_after = _native_lock_state(args.native_lock)
    resource = {
        "schema_version": "f05-resource-receipt-v1",
        "run_id": run_id,
        "started_at_utc": started_at,
        "completed_at_utc": _now(),
        "pid": pgid,
        "process_group_id": pgid,
        "process_group_gone_after_wait": not bool(post_sample["members"]),
        "wall_s": round(wall, 3),
        "max_process_group_rss_bytes": max((row["pg_rss_bytes"] for row in sample_rows), default=0),
        "max_sampled_os_thread_count": max((row["thread_count"] for row in sample_rows), default=0),
        "max_sampled_cpu_affinity_count": max((row["cpu_affinity_count"] or 0 for row in sample_rows), default=0),
        "start_mem_available_bytes": mem_start,
        "minimum_sampled_mem_available_bytes": min((row["mem_available_bytes"] for row in sample_rows), default=mem_start),
        "sample_interval_s": 0.25,
        "cpu_affinity_ids": actual_child_cpus,
        "cpu_compute_concurrency_cap": 4,
        "sample_count": len(sample_rows),
        "samples": sample_rows,
        "return_code": child_return,
        "abort_reason": abort_reason,
        "native_lock_before": pre_lock,
        "native_lock_after": lock_after,
        "native_lock_held_by_this_run": False,
        "native_process_starts": 0,
        "physics_steps": 0,
        "solver_or_simulator_starts": 0,
        "renderer_gpu_starts": 0,
    }
    _strict_write(receipts / (run_id + ".resource.json"), resource)
    result = {
        "run_id": run_id,
        "pid": pgid,
        "pgid": pgid,
        "wall_s": round(wall, 3),
        "return_code": child_return,
        "abort_reason": abort_reason,
        "process_group_gone": not bool(post_sample["members"]),
    }
    _write_input_manifest(pathlib.Path(args.package_root), pathlib.Path(args.snapshot), out / "input_sha256.manifest")
    _write_command_receipt(out, [sys.executable, str(script), *sys.argv[1:]], child_command, env_receipt, result)
    (out / "git_status_at_start.json").write_text(
        json.dumps({"commands": git_commands}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if child_return != 0 or abort_reason:
        raise RuntimeError("static audit child failed: " + (abort_reason or ("exit " + str(child_return))) + "; inspect " + str(stderr_path))
    evidence_bytes = sum(
        path.stat().st_size for path in out.rglob("*")
        if path.is_file() and "resource_receipts" not in path.parts
    )
    if evidence_bytes > 256 * 1024 ** 2:
        raise RuntimeError("generated evidence exceeds the frozen 256 MiB output limit")
    ledger = strict_json_file(out / "run_ledger.json", "child run ledger")
    ledger.update({
        "child_pid": pgid, "child_process_group": pgid, "child_wall_s": round(wall, 3),
        "child_return_code": child_return, "resource_receipt": str(receipts / (run_id + ".resource.json")),
        "command_receipt": str(out / "commands.json"),
    })
    _strict_write(out / "run_ledger.json", ledger)
    return result


def _child_entry(args):
    out = pathlib.Path(args.output_dir).absolute()
    receipt = out / "zero_native_tripwire.json"
    started = False
    completed = False
    try:
        affinity = _limit_child_cpu_affinity(4)
        install_tripwire(receipt)
        _TRIPWIRE["cpu_affinity"] = affinity
        _save_tripwire()
        started = True
        result = audit_static(args)
        completed = True
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except BaseException as error:
        _strict_write(out / "run_ledger.json", {
            "schema_version": "f05-static-run-ledger-v1",
            "run_id": args.run_id,
            "started_at_utc": _TRIPWIRE.get("installed_at_utc") if _TRIPWIRE else None,
            "completed_at_utc": _now(),
            "status": "FAIL",
            "error_type": type(error).__name__,
            "error": str(error),
            "native_starts": 0,
            "physics_steps": 0,
            "renderer_gpu_starts": 0,
            "solver_or_simulator_starts": 0,
        })
        traceback.print_exc()
        return 1
    finally:
        if _TRIPWIRE is not None:
            final = finalize_tripwire(started, completed)
            if final.get("tripwire_status") != "PASS":
                try:
                    run = strict_json_file(out / "run_ledger.json", "run ledger")
                    run["status"] = "FAIL"
                    run["tripwire_status"] = final.get("tripwire_status")
                    _strict_write(out / "run_ledger.json", run)
                except (FileNotFoundError, ValueError):
                    pass


def _argument_parser():
    parser = argparse.ArgumentParser(description="F05 static source-family audit (no solver/runtime).")
    parser.add_argument("--child", action="store_true", help="internal supervised audit process")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--primary-source-root", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--history-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-branch", default="develop-full")
    parser.add_argument("--expected-head", default="ca5b9bb3c39fc23fc5b7ee69e94600e035c3fb79")
    parser.add_argument("--native-lock", required=True)
    parser.add_argument("--python", default="/home/lly/miniconda3/envs/geochora/bin/python")
    parser.add_argument("--pxr-path", default="/home/lly/Program_Files/Geochora/workspace/environments/isaacsim-6.2.0/lib/python3.12/site-packages")
    return parser


def main(argv=None):
    args = _argument_parser().parse_args(argv)
    if args.child:
        return _child_entry(args)
    result = supervise(args)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
