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
import struct
from pathlib import Path
from typing import Any
import zipfile


INIT_SHA256 = "cbbc73792ce546c9bec181fd328a411d3183074840b282671dee481511381d0a"
ROWS = 50
WIDTH = 92
ROW_BYTES = WIDTH * 8
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
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

    def row(self, index: int) -> tuple[float, ...]:
        if type(index) is not int or not 0 <= index < ROWS:
            raise ValueError("initial-state row index must be in [0, 49]")
        start = index * WIDTH
        return self.values[start:start + WIDTH]


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


def _require_archive(data: bytes) -> bytes:
    if hashlib.sha256(data).hexdigest() != INIT_SHA256:
        raise ValueError("pruned_init bytes do not match the pinned input SHA256")
    return _read_archive_payload(data)


def _tokenize_fixed_array(payload: bytes) -> bytes:
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
    if ops[0][1] != 2 or ops[23][1] != 1 or ops[24][1] != ROWS or ops[25][1] != WIDTH:
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

    raw_candidates = [arg for op, arg, _ in ops if op.name == "BINUNICODE" and isinstance(arg, str)
                      and len(arg) == ROWS * ROW_BYTES]
    if len(raw_candidates) != 1:
        raise ValueError("pruned_init must contain exactly one fixed-size raw array string")
    try:
        raw = raw_candidates[0].encode("latin1", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("pruned_init raw array string is not a latin1 byte encoding") from exc
    if len(raw) != ROWS * ROW_BYTES:
        raise ValueError("pruned_init raw array byte length differs from its shape")
    return raw


def decode_pruned_init_bytes(data: bytes) -> DecodedInitV1:
    """Read the pinned (50, 92) float64 array without executing pickle code."""
    archive_sha = hashlib.sha256(data).hexdigest() if isinstance(data, bytes) else ""
    payload = _require_archive(data)
    raw = _tokenize_fixed_array(payload)
    values = tuple(value[0] for value in struct.iter_unpack("<d", raw))
    if len(values) != ROWS * WIDTH or any(not math.isfinite(value) for value in values):
        raise ValueError("pruned_init values must be exactly 50×92 finite float64 numbers")
    row_hashes = tuple(
        hashlib.sha256(raw[index * ROW_BYTES:(index + 1) * ROW_BYTES]).hexdigest()
        for index in range(ROWS)
    )
    return DecodedInitV1(
        source_sha256=archive_sha,
        raw_array_sha256=hashlib.sha256(raw).hexdigest(),
        values=values,
        raw_bytes=raw,
        row_sha256=row_hashes,
    )


def read_pruned_init(path: Path) -> DecodedInitV1:
    """Read and validate the exact frozen `.pruned_init` file."""
    return decode_pruned_init_bytes(Path(path).read_bytes())


def init_layout_v1() -> dict[str, Any]:
    """Return the source-derived expected name layout; not compiled-model proof."""
    robot = [*(f"joint{i}" for i in range(1, 8)), "finger_joint1", "finger_joint2"]
    objects = (
        "akita_black_bowl_1", "akita_black_bowl_2", "cookies_1",
        "glazed_rim_porcelain_ramekin_1", "plate_1",
    )
    qpos = list(robot)
    qvel = list(robot)
    for name in objects:
        qpos.extend(f"{name}.free[{i}]" for i in range(7))
        qvel.extend(f"{name}.free[{i}]" for i in range(6))
    qpos.extend((
        "wooden_cabinet_1.top_level", "wooden_cabinet_1.middle_level",
        "wooden_cabinet_1.bottom_level", "flat_stove_1.button",
    ))
    qvel.extend((
        "wooden_cabinet_1.top_level", "wooden_cabinet_1.middle_level",
        "wooden_cabinet_1.bottom_level", "flat_stove_1.button",
    ))
    if (len(qpos), len(qvel)) != (48, 43):
        raise AssertionError("internal LIBERO state layout arithmetic changed")
    return {
        "schema_version": "libero-pruned-init-name-layout-v1",
        "source_order": ["mounted_panda", *objects, "wooden_cabinet_1", "flat_stove_1"],
        "qpos_names": qpos,
        "qvel_names": qvel,
        "time_index": 0,
        "qpos_slice": [1, 49],
        "qvel_slice": [49, 92],
        "expected_nq": 48,
        "expected_nv": 43,
        "expected_na": 0,
        "fixture_body_pose_fields_in_flattened_state": False,
        "compiled_model_verification": "REQUIRED_BEFORE_NATIVE",
        "status": "SOURCE_DERIVED_LAYOUT; FIXTURE_POSES_MISSING_FROM_INIT_ROWS",
    }


__all__ = [
    "DecodedInitV1", "INIT_SHA256", "decode_pruned_init_bytes",
    "init_layout_v1", "read_pruned_init",
]
