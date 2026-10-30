"""Static source-family audit for the F05 Menagerie Panda route.

The tool parses MJCF as XML and composes USD through the existing Core loader.
It never imports a physics engine. Its default entry point supervises a child
with resource sampling and an early engine/process tripwire.
"""
from __future__ import annotations

import argparse
import builtins
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import re
import signal
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
    if list(source_names) != list(mapped_names):
        raise ValueError("joint mapping order differs from source order")
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
        if mapped.get("components") != row.get("components"):
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


def parse_mjcf_bytes(raw, source_name="panda.xml"):
    """Resolve declared XML defaults, while leaving unknown inheritance explicit."""
    if not isinstance(raw, bytes):
        raise TypeError("MJCF must be bytes")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError("MJCF XML parse failed: " + str(error)) from error
    if root.tag != "mujoco":
        raise ValueError("MJCF root element must be mujoco")
    compiler = root.find("compiler")
    compiler_attrs = dict(compiler.attrib) if compiler is not None else {}
    angle = compiler_attrs.get("angle", "radian")
    if angle not in {"radian", "degree"}:
        raise ValueError("unknown compiler angle unit: " + angle)

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

    def complete_tree(node):
        return {
            "tag": node.tag,
            "attributes": dict(sorted((str(k), str(v)) for k, v in node.attrib.items())),
            "text": node.text.strip() if node.text and node.text.strip() else None,
            "children": [complete_tree(child) for child in list(node)],
        }

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
                "ref": _numeric((effective or {}).get("ref")),
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
            actuators.append({
                "name": elem.attrib.get("name", "<unnamed>"), "kind": elem.tag,
                "locator": source_name + ":/mujoco/actuator/" + elem.tag,
                "class": cls, "resolution_status": status, "authored": dict(elem.attrib),
                "effective": effective, "target_kind": target_kind,
                "target": effective.get(target_kind) if target_kind else None,
                "ctrlrange": _numeric(effective.get("ctrlrange")),
                "forcerange": _numeric(effective.get("forcerange")),
                "kp": _numeric(effective.get("kp")), "kv": _numeric(effective.get("kv")),
                "gainprm": _numeric(effective.get("gainprm")),
                "biasprm": _numeric(effective.get("biasprm")),
                "gear": _numeric(effective.get("gear")),
                "ctrllimited": effective.get("ctrllimited"), "forcelimited": effective.get("forcelimited"),
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
        "complete_xml_tree": complete_tree(root),
        "compiler": compiler_attrs,
        "defaults": defaults,
        "bodies": bodies, "joints": joints, "sites": sites, "geoms": geoms,
        "equalities": equalities, "tendons": tendons, "actuators": actuators,
        "meshes": meshes, "keyframes": keyframes,
        "option": dict(root.find("option").attrib) if root.find("option") is not None else None,
        "limitations": [
            "XML-only inspection; no MuJoCo compile/load/forward/step.",
            "MJCF include expansion is not executed; include node is preserved and its target remains unexpanded/unknown.",
            "Unresolved default classes and omitted semantics remain unknown rather than zero.",
        ],
    }


def inspect_usd_stage(loaded, snapshot_root):
    """Enumerate the composed authored USD through pxr after Core admission."""
    from pxr import Usd, UsdGeom

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
        prims.append({
            "path": str(prim.GetPath()),
            "name": prim.GetName(),
            "type": prim.GetTypeName(),
            "active": bool(prim.IsActive()),
            "instance": bool(prim.IsInstance()),
            "applied_schemas": list(prim.GetAppliedSchemas()),
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


def negative_cases():
    cases = []

    def attempt(case_id, mutate, checker):
        sample = mutate()
        try:
            checker(sample)
        except (ValueError, TypeError, KeyError) as error:
            cases.append({"id": case_id, "status": "REJECTED", "inner_gate": type(error).__name__, "detail": str(error)})
        else:
            cases.append({"id": case_id, "status": "ACCEPTED_UNEXPECTEDLY", "detail": "validator accepted mutated sample"})

    attempt("missing_mesh", lambda: (["arm.obj"], []), lambda pair: validate_mesh_closure(*pair))
    attempt("wrong_sha", lambda: ("0" * 64, _sha(b"right")), lambda pair: verify_sha(*pair, "negative mesh"))
    attempt("wrong_revision", lambda: ("source-r1", "source-r2"), lambda pair: validate_revision(*pair))
    attempt("frame_COM_mismatch", lambda: (
        {"entity": "panda_link", "frame": "link", "com_frame": "inertial"},
        {"entity": "panda_link", "frame": "link", "com_frame": "body"},
    ), lambda pair: validate_frame_binding(*pair))
    attempt("degree_radian_error", lambda: ("degree", "radian"), lambda pair: validate_unit_identity(*pair))
    attempt("joint_order_permutation", lambda: (["j1", "j2", "j3"], ["j2", "j1", "j3"]), lambda pair: validate_ordered_mapping(*pair))
    attempt("lost_equality_mimic", lambda: (
        [{"name": "finger_mimic", "joint1": "finger_joint1", "joint2": "finger_joint2", "polycoef": [0.0, 1.0]}],
        [],
    ), lambda pair: validate_equality_mapping(*pair))
    attempt("lost_tendon_transmission", lambda: (
        [{"name": "hand_tendon", "components": [{"kind": "joint", "joint": "finger_joint1", "coef": [1.0]}]}],
        [],
    ), lambda pair: validate_tendon_mapping(*pair))
    attempt("drive_gain_force_semantic_drift", lambda: (
        {"mode": "position", "unit": "radian", "stiffness": 50.0, "damping": 2.0, "force_limit": 87.0},
        {"mode": "position", "unit": "radian", "stiffness": 40.0, "damping": 2.0, "force_limit": 87.0},
    ), lambda pair: validate_drive_law(*pair))
    attempt("forged_upstream_or_native_consumption", lambda: {
        "claim": "UPSTREAM_VERIFIED_NATIVE_CONSUMPTION",
        "evidence_kind": "unbound-report-text",
        "source_identity_sha256": None,
        "consumer_commit": None,
    }, lambda sample: validate_claim_binding(sample))
    return cases


def validate_claim_binding(claim):
    if claim.get("claim") in {"UPSTREAM_VERIFIED_NATIVE_CONSUMPTION", "NATIVE_CONSUMPTION"}:
        for field in ("source_identity_sha256", "consumer_commit", "evidence_ref"):
            if not claim.get(field):
                raise ValueError("consumption claim lacks bound " + field)
        if claim.get("evidence_kind") not in {"native_run_receipt", "qualification_record"}:
            raise ValueError("consumption claim evidence kind is not native")
    return True


def verify_negative_suite(rows):
    required = {
        "missing_mesh", "wrong_sha", "wrong_revision", "frame_COM_mismatch",
        "degree_radian_error", "joint_order_permutation", "lost_equality_mimic",
        "lost_tendon_transmission", "drive_gain_force_semantic_drift",
        "forged_upstream_or_native_consumption",
    }
    by_id = {row["id"]: row for row in rows}
    missing = required - set(by_id)
    bad = [key for key in required if by_id.get(key, {}).get("status") != "REJECTED"]
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
    attrs = set()
    relations = set()
    for prim in prims:
        schemas.update(prim["applied_schemas"])
        attrs.update(item["name"] for item in prim["attributes"])
        relations.update(item["name"] for item in prim["relationships"])
    return {
        "prim_names": sorted(names),
        "prim_paths": sorted(paths),
        "applied_schemas": sorted(schemas),
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
        ("equality_mimic", len(mjcf["equalities"]) > 0, ("mimic" in attr_text or "mimic" in schema_text or "mimic" in relationship_text), "BLOCKED_BY_FEATURE"),
        ("tendon_transmission", len(mjcf["tendons"]) > 0 or any(row.get("target_kind") == "tendon" for row in mjcf["actuators"]), ("tendon" in attr_text or "tendon" in schema_text or "tendon" in relationship_text or "tendon" in prim_type_text), "BLOCKED_BY_FEATURE"),
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
            "disposition": "unknown" if source_present else "unsupported",
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
        "source_provenance_status": source_provenance,
        "features": coverage,
        "normalization_policy": {
            "translation": "meters; USD stage units recorded separately and compared only after explicit conversion",
            "angles": "MJCF compiler angle normalized to radians for hinge/ball; original unit retained",
            "quaternion": "source quaternion order remains explicitly wxyz; USD authored representation retained",
            "joint_order": "identity and traversal order retained; no inferred permutation accepted",
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
            item["ordered_identity_match"] = item["source_order"] == usd_joint_stage_order
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


def _analytic_drive_checks(mjcf):
    checks = []
    states = [
        {"q": 0.217, "dq": -0.13, "ctrl": 0.481},
        {"q": -0.341, "dq": 0.27, "ctrl": 0.119},
    ]
    for actuator in mjcf["actuators"]:
        gain = actuator.get("gainprm")
        bias = actuator.get("biasprm")
        if not gain or len(gain) < 1 or not bias or len(bias) < 3:
            checks.append({
                "actuator": actuator["name"], "locator": actuator["locator"],
                "status": "UNKNOWN", "reason": "effective gain and affine bias law were not explicitly resolved",
            })
            continue
        samples = []
        force_range = actuator.get("forcerange")
        for state in states:
            force = float(gain[0]) * state["ctrl"] + float(bias[0]) + float(bias[1]) * state["q"] + float(bias[2]) * state["dq"]
            samples.append({
                **state,
                "raw_analytic_actuator_force": force,
                "inside_declared_force_range": force_range is None or force_range[0] <= force <= force_range[1],
                "formula": "gainprm[0]*ctrl + biasprm[0] + biasprm[1]*q + biasprm[2]*dq",
                "clamped": False,
            })
        checks.append({
            "actuator": actuator["name"], "target": actuator["target"],
            "locator": actuator["locator"], "status": "ANALYTIC_SOURCE_LAW_ONLY",
            "kind": actuator["kind"], "target_kind": actuator["target_kind"],
            "gainprm": gain, "biasprm": bias, "force_range": force_range,
            "control_range": actuator.get("ctrlrange"),
            "samples": samples,
            "not_a_simulation": True,
        })
    return checks


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
                "stage_traversal_order_matches": feature.get("ordered_identity_match"),
                "interpretation": "Exact names are present, but authored USD traversal order is reversed; no joint order mapping is inferred.",
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
            feature["disposition"] = "converted_verified" if exact else "unknown"
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


def _build_next_patch_plan(source, usd, coverage, source_info):
    blocked = [
        row["feature"] for row in coverage["features"]
        if row["source_present"] and row["status"] != "SEMANTICALLY_EQUIVALENT"
    ]
    return {
        "schema_version": "f05-next-patch-plan-v1",
        "readiness_gate": "BLOCKED_BY_FEATURE" if blocked else "READY_FOR_S1_CONTRACT_REVIEW",
        "blocked_features": blocked,
        "sequencing": [
            {
                "stage": "P1 owned static source contract",
                "owner": "task_env/assembly/usd_delivery.py",
                "methods": ["load_usd_asset_delivery", "LoadedUsdDeliveryV1 inspection surface"],
                "decision": "Do not expand Core asset contract yet; retain exact byte/provenance boundary and put family audit schema in the diagnostic owner.",
                "consumer": "task_env/diagnostics/tasks/f05_source_family_audit.py",
                "test": "task_env/diagnostics/tasks/test_phase_ii_f05_source_family_audit.py",
                "feasibility": "HIGH for static contract; no provider-private runtime inspection",
            },
            {
                "stage": "P2 normalized source mapping at existing GeoPhys adapter",
                "owner": "task_env/runtime/sessions/geophys_source.py",
                "methods": ["inspect_usd_position_drive_model", "compile_geophys_usd_position_drive_receipt"],
                "fields": ["joint identity/order", "body and COM frame binding", "position-drive kp/kv", "force/position limits"],
                "consumer": "task_env/tasks/position_candidate/builder.py",
                "test": "task_env/diagnostics/tasks/test_phase_ii_f04_core_adapter_s1.py and the F05 diagnostic regression",
                "feasibility": "MEDIUM; source family equality/tendon cannot be inferred from current position-drive receipt",
            },
            {
                "stage": "P3 tendon and mimic semantics",
                "owner": "task_env/runtime/sessions/leaf_control.py",
                "methods": ["LeafNativeTendonMappingV1", "LeafNativeActuatorMappingV1"],
                "fields": ["equality constraint identity and polynomial", "tendon component path and transmission ratio", "actuator target kind"],
                "consumer": "task_env/tasks/position_candidate/attached_leaf_candidate.py",
                "test": "task_env/diagnostics/tasks/test_phase_ii_01_r03c_attached_leaf.py",
                "feasibility": "MEDIUM; existing native tendon mapping is reusable after the static loss is represented explicitly",
            },
            {
                "stage": "P4 environment and task validity",
                "owner": "task_env/tasks/reference_env.py",
                "methods": ["SelectedReferenceEnv lifecycle hooks and task predicate route"],
                "fields": ["free-body/support/contact scene", "raw task predicate versus lifecycle-valid success"],
                "consumer": "Phase F07 candidate only after separate authorization",
                "test": "candidate-specific lifecycle/replay qualification tests",
                "feasibility": "DEFERRED; F06/F07/native work not authorized in this package",
            },
        ],
        "stop_conditions": [
            "Do not advance on inventory PASS when equality/mimic, tendon transmission, or drive/gain/force semantics remain unresolved.",
            "S1 requires Sol review of this static report and an explicit next package.",
            "No native, renderer, GPU, conversion, asset edit, production implementation, or qualification is authorized here.",
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
    mjcf = parse_mjcf_bytes(source_bytes["panda.xml"], "panda.xml")

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
    joint_coverage = next(row for row in coverage["features"] if row["feature"] == "joint_identity")
    missing_features = [
        row["feature"] for row in coverage["features"]
        if row["source_present"] and row["status"] != "SEMANTICALLY_EQUIVALENT"
    ]
    readiness = "BLOCKED_BY_FEATURE" if missing_features else "READY_FOR_S1_CONTRACT_REVIEW"
    negative = negative_cases()
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
            "compiler_angle": mjcf["compiler"].get("angle", "radian"),
            "unexpanded_include_semantics": "UNKNOWN; XML include is not executed",
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
    equivalence = {
        "schema_version": "f05-equivalence-checks-v1",
        "status": readiness,
        "inventory_status": "PASS",
        "equivalence_claim": False,
        "blocked_by_feature": missing_features,
        "normalization": coverage["normalization_policy"],
        "feature_rows": coverage["features"],
        "identity_intersection": {
            "source_joint_order": [item["name"] for item in mjcf["joints"]],
            "usd_exact_name_joint_intersection": coverage["matched_joint_names"],
            "usd_joint_stage_order": joint_coverage["usd_exact_name_stage_order"],
            "ordered_identity_match": joint_coverage["ordered_identity_match"],
            "source_body_order": [item["name"] for item in mjcf["bodies"]],
            "usd_exact_name_body_intersection": coverage["matched_body_names"],
        },
        "analytic_drive_law_checks": _analytic_drive_checks(mjcf),
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
    _strict_write(out / "equivalence_checks.json", equivalence)
    _strict_write(out / "compatibility_matrix.json", compatibility)
    _strict_write(out / "next_patch_plan.json", next_plan)
    _strict_write(out / "evidence_reuse_matrix.json", evidence_reuse)
    _strict_write(out / "negative_results.json", {
        "schema_version": "f05-negative-results-v1",
        "status": "PASS" if all(row["status"] == "REJECTED" for row in negative) else "FAIL",
        "required_count": 10, "executed_count": len(negative), "cases": negative,
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
        "inventory_status": "PASS",
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
        "inventory_status": "PASS",
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
