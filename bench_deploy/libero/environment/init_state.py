"""Safe reader for the one pinned LIBERO ``.pruned_init`` array format.

The input is a ZIP archive containing a protocol-2 NumPy ndarray pickle.  This
module never unpickles: ``pickletools`` is used only as a tokenizer and the
accepted opcode stream is matched against the exact frozen array encoding.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import math
import pickletools
import re
import struct
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

from bench_deploy.libero.artifacts.contracts import TASK_1, task_source_contract_v1
from bench_deploy.libero.objects.layout import (
    PILOT_FIXTURES, PILOT_FIXTURE_Z_OFFSET_M, PILOT_MOVABLES,
    PILOT_MOVABLE_OBJECT_CLASSES, PILOT_MOVABLE_Z_OFFSET_M,
    PILOT_TABLE_TOP_Z_M,
)


INIT_SHA256 = "cbbc73792ce546c9bec181fd328a411d3183074840b282671dee481511381d0a"
ROWS = 50
WIDTH = 92
ROW_BYTES = WIDTH * 8
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
PILOT_SOURCE_MANIFEST_SHA256 = "4ad168e4710f3153d0f1f470389a506df27588e4d5ce1eaec450289807d30a75"
PILOT_BDDL_SHA256 = "9b59eb1287802868ad9bc78d58e6d36d4ba31134e679cfdbdf4b0feb660c959b"
PILOT_RESET_SAMPLER_ID = "libero-bddl-normal-placement-v1"
PILOT_RESET_SAMPLER_VERSION = "libero-8f1084e3-robosuite-fbee5844-tabletop-table-region-v2"
PILOT_PANDA_ARM_RESET_NOISE_DRAWS = 7
PILOT_INIT_ORDER = (
    "sample_object_properties", "mj_step1", "sample_fixtures_and_objects",
    "restore_selected_init_row", "mj_forward",
)
_MEMBERS = {"archive/data.pkl", "archive/version"}
_GLOBAL_SYMBOLS = {
    "numpy.core.multiarray _reconstruct",
    "numpy ndarray",
    "_codecs encode",
    "numpy dtype",
}


@dataclass(frozen=True)
class DecodedInitV1:
    source_sha256: str
    raw_array_sha256: str
    values: tuple[float, ...]
    raw_bytes: bytes
    row_sha256: tuple[str, ...]
    row_count: int = ROWS
    width: int = WIDTH

    def row(self, index: int) -> tuple[float, ...]:
        if type(index) is not int or not 0 <= index < self.row_count:
            raise ValueError(f"initial-state row index must be in [0, {self.row_count - 1}]")
        start = index * self.width
        return self.values[start:start + self.width]


def _read_archive_payload(data: bytes) -> bytes:
    if type(data) is not bytes or len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("pruned_init archive must be bytes no larger than 2 MiB")
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != 2 or set(names) != _MEMBERS or len(set(names)) != 2:
                raise ValueError("pruned_init ZIP must contain only the two pinned members")
            if any(item.file_size > MAX_ARCHIVE_BYTES for item in infos):
                raise ValueError("pruned_init expanded member exceeds 2 MiB")
            if sum(item.file_size for item in infos) > MAX_ARCHIVE_BYTES:
                raise ValueError("pruned_init expanded archive exceeds 2 MiB")
            if archive.read("archive/version") != b"3\n":
                raise ValueError("unsupported pruned_init ZIP archive version")
            payload = archive.read("archive/data.pkl")
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError("pruned_init is not a valid bounded ZIP archive") from exc
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError("pruned_init pickle payload exceeds 2 MiB")
    return payload


def _require_archive(data: bytes, *, expected_sha256: str = INIT_SHA256) -> bytes:
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("pruned_init bytes do not match the pinned input SHA256 for this task")
    return _read_archive_payload(data)


def _tokenize_fixed_array(payload: bytes, *, expected_shape: tuple[int, int] = (ROWS, WIDTH)) -> bytes:
    if (type(expected_shape) is not tuple or len(expected_shape) != 2
            or any(type(value) is not int or value <= 0 for value in expected_shape)):
        raise ValueError("pruned_init expected shape must be a pair of positive integers")
    rows, width = expected_shape
    try:
        ops = list(pickletools.genops(payload))
    except Exception as exc:
        raise ValueError("pruned_init contains an invalid pickle token stream") from exc
    names = [op.name for op, _, _ in ops]
    globals_seen = {arg for op, arg, _ in ops if op.name == "GLOBAL"}
    if globals_seen != _GLOBAL_SYMBOLS or names.count("GLOBAL") != len(_GLOBAL_SYMBOLS):
        raise ValueError("pruned_init GLOBAL symbols differ from the fixed ndarray format")

    # Full opcode shape is frozen. REDUCE/BUILD are recognized as tokens only;
    # no callable, constructor, reducer or object's __setstate__ is executed.
    expected_names = (
        "PROTO GLOBAL BINPUT GLOBAL BINPUT BININT1 TUPLE1 BINPUT GLOBAL BINPUT "
        "BINUNICODE BINPUT BINUNICODE BINPUT TUPLE2 BINPUT REDUCE BINPUT TUPLE3 "
        "BINPUT REDUCE BINPUT MARK BININT1 BININT1 BININT1 TUPLE2 BINPUT GLOBAL "
        "BINPUT BINUNICODE BINPUT NEWFALSE NEWTRUE TUPLE3 BINPUT REDUCE BINPUT "
        "MARK BININT1 BINUNICODE BINPUT NONE NONE NONE BININT BININT BININT1 TUPLE "
        "BINPUT BUILD NEWFALSE BINGET BINUNICODE BINPUT BINGET TUPLE2 BINPUT REDUCE "
        "BINPUT TUPLE BINPUT BUILD STOP"
    ).split()
    if names != list(expected_names):
        raise ValueError("pruned_init opcode stream differs from the fixed ndarray format")
    if ops[0][1] != 2 or ops[23][1] != 1 or ops[24][1] != rows or ops[25][1] != width:
        raise ValueError("pruned_init protocol or array dimensions differ from the fixed input")
    if ops[30][1] != "f8" or ops[39][1] != 3 or ops[40][1] != "<":
        raise ValueError("pruned_init dtype is not little-endian float64")
    if ops[4][1] != 1 or ops[7][1] != 2 or ops[10][1] != "b" or ops[12][1] != "latin1":
        raise ValueError("pruned_init ndarray reconstruction metadata differs")
    if ops[42][1] is not None or ops[43][1] is not None or ops[44][1] is not None:
        raise ValueError("pruned_init dtype metadata differs from the fixed input")
    if ops[45][1] != -1 or ops[46][1] != -1 or ops[47][1] != 0:
        raise ValueError("pruned_init dtype metadata differs from the fixed input")
    if ops[52][1] != 3 or ops[55][1] != 5:
        raise ValueError("pruned_init pickle memo references differ from the fixed input")

    expected_bytes = rows * width * 8
    raw_candidates = [arg for op, arg, _ in ops if op.name == "BINUNICODE" and isinstance(arg, str)
                      and len(arg) == expected_bytes]
    if len(raw_candidates) != 1:
        raise ValueError("pruned_init must contain exactly one fixed-size raw array string")
    try:
        raw = raw_candidates[0].encode("latin1", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("pruned_init raw array string is not a latin1 byte encoding") from exc
    if len(raw) != expected_bytes:
        raise ValueError("pruned_init raw array byte length differs from its shape")
    return raw


def decode_pruned_init_bytes(data: bytes, *, task_uid: str = TASK_1) -> DecodedInitV1:
    """Read one exact required task array without executing pickle code.

    The task identity selects a frozen SHA-256 and shape.  Callers cannot pass
    arbitrary dimensions or a caller-supplied hash to broaden the decoder.
    """
    contract = task_source_contract_v1(task_uid)
    archive_sha = hashlib.sha256(data).hexdigest() if isinstance(data, bytes) else ""
    payload = _require_archive(data, expected_sha256=contract.init_sha256)
    raw = _tokenize_fixed_array(payload, expected_shape=contract.init_shape)
    values = tuple(value[0] for value in struct.iter_unpack("<d", raw))
    rows, width = contract.init_shape
    if len(values) != rows * width or any(not math.isfinite(value) for value in values):
        raise ValueError(f"pruned_init values must be exactly {rows}×{width} finite float64 numbers")
    row_bytes = width * 8
    row_hashes = tuple(
        hashlib.sha256(raw[index * row_bytes:(index + 1) * row_bytes]).hexdigest()
        for index in range(rows)
    )
    return DecodedInitV1(
        source_sha256=archive_sha,
        raw_array_sha256=hashlib.sha256(raw).hexdigest(),
        values=values,
        raw_bytes=raw,
        row_sha256=row_hashes,
        row_count=rows,
        width=width,
    )


def read_pruned_init(path: Path, *, task_uid: str = TASK_1) -> DecodedInitV1:
    """Read and validate one exact frozen `.pruned_init` file."""
    return decode_pruned_init_bytes(Path(path).read_bytes(), task_uid=task_uid)


def init_layout_v1(task_uid: str = TASK_1) -> dict[str, Any]:
    """Return the task's declared flat row layout; not compiled-model proof."""
    contract = task_source_contract_v1(task_uid)
    robot = [*(f"joint{i}" for i in range(1, 8)), "finger_joint1", "finger_joint2"]
    objects = contract.movable_instances
    qpos = list(robot)
    qvel = list(robot)
    for name in objects:
        qpos.extend(f"{name}.free[{i}]" for i in range(7))
        qvel.extend(f"{name}.free[{i}]" for i in range(6))
    qpos.extend(contract.fixture_joint_names)
    qvel.extend(contract.fixture_joint_names)
    rows, width = contract.init_shape
    qpos_end = 1 + len(qpos)
    if qpos_end + len(qvel) != width:
        raise ValueError("task source declaration and selected init row width disagree")
    layout = {
        "schema_version": (
            "libero-pruned-init-name-layout-v1" if task_uid == TASK_1
            else "libero-pruned-init-name-layout-v2"
        ),
        "task_uid": task_uid,
        "source_revision": "8f1084e3132a39270c3a13ebe37270a43ece2a01",
        "source_order": ["mounted_panda", *objects, "wooden_cabinet_1", "flat_stove_1"],
        "qpos_names": qpos,
        "qvel_names": qvel,
        "time_index": 0,
        "shape": [rows, width],
        "qpos_slice": [1, qpos_end],
        "qvel_slice": [qpos_end, width],
        "expected_nq": len(qpos),
        "expected_nv": len(qvel),
        "expected_na": 0,
        "fixture_body_pose_fields_in_flattened_state": False,
        "compiled_model_verification": "REQUIRED_BEFORE_NATIVE",
        "status": (
            "SOURCE_DERIVED_LAYOUT; FIXTURE_POSES_MISSING_FROM_INIT_ROWS"
            if task_uid == TASK_1 else "SOURCE_DECLARED_LAYOUT; FIXTURE_POSES_MISSING_FROM_INIT_ROWS"
        ),
    }
    # Preserve the already-consumed v1 projection byte-for-byte for the first
    # task.  The new fields are part of the v2 declaration only.
    if task_uid == TASK_1:
        for key in ("task_uid", "source_revision", "shape"):
            layout.pop(key)
    return layout


def _parse_sexpr(text: str):
    """Parse the fixed BDDL data syntax without importing BDDL or executing code."""
    tokens = re.findall(r"\(|\)|[^\s()]+", text)
    stack: list[list[Any]] = []
    root: list[Any] = []
    current = root
    for token in tokens:
        if token == "(":
            child: list[Any] = []
            current.append(child)
            stack.append(current)
            current = child
        elif token == ")":
            if not stack:
                raise ValueError("pinned BDDL has an unmatched closing parenthesis")
            current = stack.pop()
        else:
            current.append(token)
    if stack:
        raise ValueError("pinned BDDL has an unmatched opening parenthesis")
    return root


def _find_form(tree, head: str):
    pending = list(tree)
    found = []
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            if item and item[0] == head:
                found.append(item)
            pending.extend(item)
    if len(found) != 1:
        raise ValueError(f"pinned BDDL must contain one {head!r} form")
    return found[0]


def _task_regions_and_initial_state(install_root: Path, source_manifest: dict):
    manifest_path = Path(__file__).resolve().parents[3] / "asset/benchmarks/libero/source_manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != PILOT_SOURCE_MANIFEST_SHA256:
        raise ValueError("LIBERO source manifest differs from the frozen pilot identity")
    canonical_manifest = json_loads(manifest_bytes)
    if source_manifest != canonical_manifest:
        raise ValueError("provided LIBERO source manifest differs from the tracked frozen manifest")
    rows = {row.get("install_path"): row for row in source_manifest.get("files", ())}
    bddl_path = "upstream/libero/libero/libero/bddl_files/libero_spatial/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate.bddl"
    row = rows.get(bddl_path)
    if row is None or row.get("sha256") != PILOT_BDDL_SHA256:
        raise ValueError("frozen LIBERO BDDL is absent from its source manifest")
    root = Path(install_root).resolve(strict=True)
    target = root / bddl_path
    if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != PILOT_BDDL_SHA256:
        raise ValueError("installed LIBERO BDDL bytes differ from the frozen source")
    tree = _parse_sexpr(target.read_text(encoding="utf-8"))
    bddl = _find_form(tree, "define")
    regions_form = _find_form(bddl, ":regions")
    initial_form = _find_form(bddl, ":init")
    states = tuple(
        (str(item[0]).lower(), str(item[1]), str(item[2]))
        for item in initial_form[1:] if isinstance(item, list) and len(item) == 3
    )
    expected_states = tuple(
        ("on", name, f"main_table_{region}")
        for name, region, _ in (*PILOT_MOVABLES, *PILOT_FIXTURES)
    )
    if states != expected_states:
        raise ValueError("pinned LIBERO BDDL initial-state order or content changed")
    result = {}
    for region in regions_form[1:]:
        if not isinstance(region, list) or not region:
            continue
        name = str(region[0])
        target_form = next((entry for entry in region[1:] if isinstance(entry, list) and entry[:1] == [":target"]), None)
        ranges_form = next((entry for entry in region[1:] if isinstance(entry, list) and entry[:1] == [":ranges"]), None)
        yaw_form = next((entry for entry in region[1:] if isinstance(entry, list) and entry[:1] == [":yaw_rotation"]), None)
        if target_form is None or len(target_form) != 2 or ranges_form is None:
            continue
        ranges = tuple(tuple(float(value) for value in rectangle) for rectangle in ranges_form[1])
        yaw_ranges = ((0.0, 0.0),) if yaw_form is None else tuple(
            tuple(_bddl_number(value) for value in pair) for pair in yaw_form[1]
        )
        if (any(len(item) != 4 or any(not math.isfinite(value) for value in item) for item in ranges)
                or not yaw_ranges
                or any(len(item) != 2 or any(not math.isfinite(value) for value in item)
                       for item in yaw_ranges)):
            raise ValueError(f"pinned BDDL region {name!r} has an unsupported range shape")
        result[name] = {"target": str(target_form[1]), "ranges": ranges, "yaw_ranges": yaw_ranges}
    required_regions = {name for _, name, _ in (*PILOT_MOVABLES, *PILOT_FIXTURES)}
    if not required_regions <= set(result):
        raise ValueError("pinned BDDL does not cover every selected normal-reset region")
    if any(result[name]["target"] != "main_table" for _, name, _ in (*PILOT_MOVABLES, *PILOT_FIXTURES)):
        raise ValueError("pilot reset changed from table-region sampling to conditional placements")
    return result, states


def _bddl_number(value: str) -> float:
    if value.startswith("("):
        raise ValueError("nested BDDL yaw range is malformed")
    # LIBERO's BDDL parser evaluates a fixed Python math expression. This narrow
    # parser admits only the exact pi forms used by the selected source.
    if value == "pi":
        return math.pi
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\*pi(?:/([0-9]+(?:\.[0-9]+)?))?", value)
    if match:
        result = float(match.group(1)) * math.pi
        return result if match.group(2) is None else result / float(match.group(2))
    return float(value)


def json_loads(value: bytes):
    import json
    return json.loads(value)


def _object_placement_properties(install_root: Path, source_manifest: dict, source_path: str):
    rows = {row.get("install_path"): row for row in source_manifest.get("files", ())}
    row = rows.get(source_path)
    if row is None or not isinstance(row.get("sha256"), str):
        raise ValueError(f"pinned LIBERO object XML is missing from manifest: {source_path}")
    root = Path(install_root).resolve(strict=True)
    target = root / source_path
    if target.is_symlink():
        raise ValueError("LIBERO reset object XML may not be a symlink")
    payload = target.read_bytes()
    if hashlib.sha256(payload).hexdigest() != row["sha256"]:
        raise ValueError(f"installed object XML bytes differ from manifest: {source_path}")
    xml = ET.fromstring(payload)
    object_root = xml.find("./worldbody/body")
    if object_root is None:
        raise ValueError(f"pinned object XML has no unique worldbody root: {source_path}")
    sites = {site.get("name"): site.get("pos") for site in object_root.findall("site")}
    needed = {"bottom_site", "top_site", "horizontal_radius_site"}
    if set(sites) < needed:
        # The articulated sources name the main root rather than an anonymous body.
        sites = {site.get("name").removeprefix("main_"): site.get("pos") for site in object_root.findall("site")}
    if not needed <= set(sites):
        raise ValueError(f"pinned object XML omits the LIBERO placement sampler sites: {source_path}")
    bottom = tuple(float(value) for value in sites["bottom_site"].split())
    top = tuple(float(value) for value in sites["top_site"].split())
    radius_pos = tuple(float(value) for value in sites["horizontal_radius_site"].split())
    if len(bottom) != 3 or len(top) != 3 or len(radius_pos) != 3:
        raise ValueError("LIBERO placement sampler site coordinates have invalid dimensions")
    return {
        "asset_sha256": row["sha256"], "bottom_offset": bottom, "top_offset": top,
        "horizontal_radius": radius_pos[0],
    }


def _placement_draw(*, position, quaternion_wxyz, range_index, attempt, source_sampler,
                    region_bounds, sample_bounds, margin, z_offset, rotation_axis,
                    rotation_bounds, angle, object_class=None):
    x0, y0, x1, y1 = sample_bounds
    record = {
        "position": position, "quaternion_wxyz": quaternion_wxyz,
        "range_index": range_index, "attempt": attempt,
        "source_sampler": source_sampler,
        "region_ranges_m": list(region_bounds),
        "x_sample_bounds_m": [x0, x1], "y_sample_bounds_m": [y0, y1],
        "x_sample_interval_m": [min(x0, x1), max(x0, x1)],
        "y_sample_interval_m": [min(y0, y1), max(y0, y1)],
        "horizontal_radius_margin_m": margin, "z_offset_m": z_offset,
        "rotation_axis": rotation_axis, "rotation_range_rad": list(rotation_bounds),
        "rotation_angle_rad": angle,
    }
    if object_class is not None:
        record["object_class"] = object_class
    return record


def sample_libero_normal_reset_v1(
    *,
    init_bytes: bytes,
    install_root: Path,
    source_manifest: dict,
    task_artifact_hash: str,
    source_id: str,
    source_closure_digest: str,
    task_seed: int,
    init_row_index: int,
):
    """Return the pinned normal BDDL placement plus source-bound ResetSampleV1.

    This is a narrow pure-Python translation of LIBERO's fixed normal reset
    sampler. It uses a task-seeded RandomState and mirrors the upstream Panda
    ``Robot.reset`` RNG advance before placement sampling, then restores the
    selected safe-decoded .pruned_init row.
    """
    from task_env.artifacts import PoseWorld, ResetSampleV1

    if type(task_seed) is not int or task_seed < 0:
        raise ValueError("LIBERO normal reset requires a nonnegative integer task seed")
    if type(init_row_index) is not int or not 0 <= init_row_index < ROWS:
        raise ValueError("LIBERO init row must be in [0,49]")
    decoded = decode_pruned_init_bytes(init_bytes)
    regions, ordered_states = _task_regions_and_initial_state(install_root, source_manifest)
    source_parts = source_id.split(":") if isinstance(source_id, str) else []
    legacy_source_identity = (
        len(source_parts) == 2
        and source_parts[0] == "libero-spatial-pilot-v1"
        and bool(re.fullmatch(r"[0-9a-f]{64}", source_parts[1]))
    )
    profiled_source_identity = (
        len(source_parts) == 4
        and source_parts[0] == "libero-spatial-official-model-profile-v3"
        and all(re.fullmatch(r"[0-9a-f]{64}", value) for value in source_parts[1:])
    )
    if (not (legacy_source_identity or profiled_source_identity)
            or not isinstance(source_closure_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", source_closure_digest)):
        raise ValueError("LIBERO candidate source/closure identity is malformed")
    import numpy as np
    rng = np.random.RandomState(task_seed)
    # robosuite Robot.reset calls np.random.randn(len(init_qpos)) whenever
    # deterministic_reset=False. Panda has seven arm joints and this task
    # passes zero-magnitude Gaussian initialization noise, so the sampled
    # values do not perturb qpos but still advance the global placement RNG.
    # Preserve that stream position in the isolated deterministic candidate
    # RNG; the selected .pruned_init row later restores all robot qpos/qvel.
    rng.randn(PILOT_PANDA_ARM_RESET_NOISE_DRAWS)
    placed: dict[str, dict[str, Any]] = {}
    asset_properties: dict[str, dict[str, Any]] = {}
    draw_rows = []
    for object_name, region_name, source_path in PILOT_MOVABLES:
        properties = asset_properties.setdefault(
            source_path, _object_placement_properties(install_root, source_manifest, source_path),
        )
        region = regions[region_name]
        selected = None
        for attempt in range(5000):
            range_index = int(rng.randint(len(region["ranges"])))
            x0, y0, x1, y1 = region["ranges"][range_index]
            # The selected LIBERO problem registers TableRegionSampler, whose
            # defaults keep each movable's horizontal-radius boundary inside
            # its BDDL rectangle. Fixture samplers use different defaults.
            x0 += properties["horizontal_radius"]
            x1 -= properties["horizontal_radius"]
            y0 += properties["horizontal_radius"]
            y1 -= properties["horizontal_radius"]
            x = float(rng.uniform(low=x0, high=x1))
            y = float(rng.uniform(low=y0, high=y1))
            z = PILOT_MOVABLE_Z_OFFSET_M + PILOT_TABLE_TOP_Z_M - properties["bottom_offset"][2]
            overlaps = False
            for other in placed.values():
                distance = float(np.linalg.norm((x - other["position"][0], y - other["position"][1])))
                vertical = z - other["position"][2]
                if (distance <= properties["horizontal_radius"] + other["horizontal_radius"]
                        and vertical <= other["top_offset"][2] - properties["bottom_offset"][2]):
                    overlaps = True
                    break
            if overlaps:
                continue
            # GoogleScannedObject/HopeBaseObject use the same fixed x-axis
            # rotation. The upstream class sampler calls uniform even when the
            # endpoints coincide, so retain that RNG draw.
            angle = float(rng.uniform(low=math.pi / 2, high=math.pi / 2))
            quaternion = (math.cos(angle / 2), math.sin(angle / 2), 0.0, 0.0)
            radius = properties["horizontal_radius"]
            selected = _placement_draw(
                position=(x, y, z), quaternion_wxyz=quaternion,
                range_index=range_index, attempt=attempt + 1,
                source_sampler="libero.envs.regions.workspace_region_sampler.TableRegionSampler",
                region_bounds=(x0 - radius, y0 - radius, x1 + radius, y1 + radius),
                sample_bounds=(x0, y0, x1, y1), margin=radius,
                z_offset=PILOT_MOVABLE_Z_OFFSET_M, rotation_axis="x",
                rotation_bounds=(math.pi / 2, math.pi / 2), angle=angle,
                object_class=PILOT_MOVABLE_OBJECT_CLASSES[object_name],
            )
            placed[object_name] = {
                **selected, "horizontal_radius": properties["horizontal_radius"],
                "top_offset": properties["top_offset"], "bottom_offset": properties["bottom_offset"],
            }
            break
        if selected is None:
            raise ValueError(f"LIBERO upstream sampler exhausted 5000 placements for {object_name}")
        draw_rows.append({"object": object_name, "region": region_name, **selected})

    fixture_poses = {}
    for fixture_name, region_name, source_path in PILOT_FIXTURES:
        properties = asset_properties.setdefault(
            source_path, _object_placement_properties(install_root, source_manifest, source_path),
        )
        region = regions[region_name]
        range_index = int(rng.randint(len(region["ranges"])))
        x0, y0, x1, y1 = region["ranges"][range_index]
        x = float(rng.uniform(low=x0, high=x1))
        y = float(rng.uniform(low=y0, high=y1))
        angle_low, angle_high = region["yaw_ranges"][min(range_index, len(region["yaw_ranges"]) - 1)]
        angle = float(rng.uniform(low=min(angle_low, angle_high), high=max(angle_low, angle_high)))
        z = PILOT_FIXTURE_Z_OFFSET_M + PILOT_TABLE_TOP_Z_M - properties["bottom_offset"][2]
        quaternion = (math.cos(angle / 2), 0.0, 0.0, math.sin(angle / 2))
        selected = _placement_draw(
            position=(x, y, z), quaternion_wxyz=quaternion,
            range_index=range_index, attempt=1,
            source_sampler="robosuite.utils.placement_samplers.MultiRegionRandomSampler",
            region_bounds=(x0, y0, x1, y1), sample_bounds=(x0, y0, x1, y1),
            margin=0.0, z_offset=PILOT_FIXTURE_Z_OFFSET_M, rotation_axis="z",
            rotation_bounds=(angle_low, angle_high), angle=angle,
        )
        draw_rows.append({"object": fixture_name, "region": region_name, **selected})
        fixture_poses[fixture_name] = PoseWorld(selected["position"], selected["quaternion_wxyz"])

    layout = init_layout_v1()
    row = decoded.row(init_row_index)
    qpos_names, qvel_names = layout["qpos_names"], layout["qvel_names"]
    qpos_by_name = dict(zip(qpos_names, row[layout["qpos_slice"][0]:layout["qpos_slice"][1]], strict=True))
    qvel_by_name = dict(zip(qvel_names, row[layout["qvel_slice"][0]:layout["qvel_slice"][1]], strict=True))
    joint_names = (
        *(f"joint{index}" for index in range(1, 8)), "finger_joint1", "finger_joint2",
        "wooden_cabinet_1.top_level", "wooden_cabinet_1.middle_level",
        "wooden_cabinet_1.bottom_level", "flat_stove_1.button",
    )
    object_names = tuple(name for name, _, _ in PILOT_MOVABLES)
    joint_position = {name: float(qpos_by_name[name]) for name in joint_names}
    joint_velocity = {name: float(qvel_by_name[name]) for name in joint_names}
    poses_world = {}
    free_velocity = {}
    for name in object_names:
        base = f"{name}.free"
        coords = tuple(float(qpos_by_name[f"{base}[{index}]"]) for index in range(7))
        poses_world[name] = PoseWorld(coords[:3], coords[3:])
        free_velocity[name] = tuple(float(qvel_by_name[f"{base}[{index}]"]) for index in range(6))
    sample = ResetSampleV1.create(
        schema_version="reset-sample-v1", task_artifact_hash=task_artifact_hash,
        source_id=source_id, source_closure_digest=source_closure_digest,
        sampler_id=PILOT_RESET_SAMPLER_ID, sampler_version=PILOT_RESET_SAMPLER_VERSION,
        task_seed=task_seed, init_row_index=init_row_index,
        init_row_sha256=decoded.row_sha256[init_row_index], joint_position=joint_position,
        joint_velocity=joint_velocity,
        sampled_poses_world={name: PoseWorld(placed[name]["position"], placed[name]["quaternion_wxyz"])
                             for name in object_names},
        poses_world=poses_world, free_joint_velocity=free_velocity,
        free_joint_velocity_frame="mujoco_world_linear_local_angular_v1",
        fixture_pose_world=fixture_poses,
        simulation_time_s=float(row[0]), velocity_policy="named_qvel_and_free_joint_qvel_v1",
        control_policy="named_torque_and_finger_position_by_source_v1",
        initialization_order=PILOT_INIT_ORDER, settle_steps=0,
    )
    receipt = {
        "schema_version": "libero-normal-reset-realization-v2",
        "task_seed": task_seed, "init_row_index": init_row_index,
        "init_row_sha256": decoded.row_sha256[init_row_index],
        "reset_sample_id": sample.sample_id,
        "reset_sample_v1": sample.to_mapping(),
        "source_manifest_sha256": PILOT_SOURCE_MANIFEST_SHA256,
        "bddl_sha256": PILOT_BDDL_SHA256, "ordered_initial_states": [list(item) for item in ordered_states],
        "sampler_id": PILOT_RESET_SAMPLER_ID, "sampler_version": PILOT_RESET_SAMPLER_VERSION,
        "rng": {
            "generator": "numpy.random.RandomState / legacy np.random.seed compatible MT19937",
            "seed": task_seed,
            "upstream_preplacement_draw_count": PILOT_PANDA_ARM_RESET_NOISE_DRAWS,
        },
        "placements_before_pruned_init_restore": draw_rows,
        "asset_placement_geometry": {
            path: {
                "asset_sha256": value["asset_sha256"],
                "bottom_offset_m": list(value["bottom_offset"]),
                "top_offset_m": list(value["top_offset"]),
                "horizontal_radius_m": value["horizontal_radius"],
            }
            for path, value in asset_properties.items()
        },
    }
    return sample, receipt


__all__ = [
    "DecodedInitV1", "INIT_SHA256", "decode_pruned_init_bytes",
    "init_layout_v1", "read_pruned_init", "sample_libero_normal_reset_v1",
]
