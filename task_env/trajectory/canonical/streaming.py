"""Bounded-buffer I/O for the existing canonical execution H5 schema.

The JSON bytes are identical to json.dumps(sort_keys=True, separators=(',',
':'), allow_nan=False). No observations, controls or owner fields are dropped.
The legacy full-object reader remains available in execution.load.
"""

from __future__ import annotations

import hashlib
import json
import os
import codecs
from pathlib import Path
from time import perf_counter

import numpy as np

BUFFER_BYTES = 1024 * 1024
VERIFICATION_VERSION = "canonical-json-streaming-byte-roundtrip-v1"


class _ObjectFragments:
    def __init__(self, mapping):
        self.mapping = mapping


class _RawFragment:
    def __init__(self, encoded):
        self.encoded = encoded


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _fragment_parts(value):
    if isinstance(value, _RawFragment):
        yield value.encoded
    elif isinstance(value, _ObjectFragments):
        yield b"{"
        for index, key in enumerate(sorted(value.mapping)):
            if index:
                yield b","
            yield _json_bytes(key) + b":"
            yield from _fragment_parts(value.mapping[key])
        yield b"}"
    else:
        yield _json_bytes(value)


def snapshot_digest(snapshot, encoded_blobs):
    """Hash exactly the historically expanded owner mapping, without deep copies.

    Blob bytes are validated once per validate() call. References are resolved
    only in the owner-field positions expanded by execution.expand_snapshot.
    No persistent cache is retained across mutations of caller-owned mappings.
    """
    owners = {}
    for name, owner in snapshot["owners"].items():
        fields = {}
        for field, entry in owner["fields"].items():
            value = entry["value"]
            if isinstance(value, dict) and value.get("kind") == "content-ref":
                fields[field] = _ObjectFragments({
                    **entry, "value": _RawFragment(encoded_blobs[value["sha256"]])})
            else:
                fields[field] = entry
        owners[name] = _ObjectFragments({**owner, "fields": _ObjectFragments(fields)})
    root = {key: value for key, value in snapshot.items() if key != "integrity_hash"}
    root["owners"] = _ObjectFragments(owners)
    hashed = hashlib.sha256()
    for part in _fragment_parts(_ObjectFragments(root)):
        hashed.update(part)
    return hashed.hexdigest()


def logical_segments(value):
    """Encode individual records in C without allocating the whole episode."""
    yield b"{"
    for index, key in enumerate(sorted(value)):
        if index:
            yield b","
        yield _json_bytes(key) + b":"
        item = value[key]
        if key in {"boundaries", "transitions"}:
            yield b"["
            for record_index, record in enumerate(item):
                if record_index:
                    yield b","
                yield _json_bytes(record)
            yield b"]"
        elif key == "blobs":
            yield b"{"
            for blob_index, name in enumerate(sorted(item)):
                if blob_index:
                    yield b","
                yield _json_bytes(name) + b":"
                yield _json_bytes(item[name])
            yield b"}"
        else:
            yield _json_bytes(item)
    yield b"}"


def logical_chunks(value, chunk_bytes=BUFFER_BYTES):
    if type(chunk_bytes) is not int or chunk_bytes <= 0:
        raise ValueError("positive integer I/O chunk size required")
    buffer = bytearray()
    for segment in logical_segments(value):
        view = memoryview(segment)
        offset = 0
        while offset < len(view):
            count = min(chunk_bytes - len(buffer), len(view) - offset)
            buffer.extend(view[offset:offset + count])
            offset += count
            if len(buffer) == chunk_bytes:
                yield bytes(buffer)
                buffer.clear()
    if buffer:
        yield bytes(buffer)


def save_streaming(path, value, *, chunk_bytes=BUFFER_BYTES):
    """Validate and atomically save the old schema with bounded encoding buffers."""
    import h5py
    from .execution import FILE_SCHEMA, LEGACY_FILE_SCHEMA, SCHEMA, validate

    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if path.exists() or temporary.exists():
        raise FileExistsError("no overwrite")
    started = perf_counter()
    validate(value)
    validated = perf_counter()
    logical_hash = hashlib.sha256()
    count = 0
    try:
        with h5py.File(temporary, "x") as handle:
            handle.attrs["schema"] = FILE_SCHEMA if value["schema"] == SCHEMA else LEGACY_FILE_SCHEMA
            dataset = handle.create_dataset(
                "logical_json_utf8", shape=(0,), maxshape=(None,), dtype=np.uint8,
                chunks=(chunk_bytes,), compression="gzip", compression_opts=4,
            )
            for chunk in logical_chunks(value, chunk_bytes):
                logical_hash.update(chunk)
                dataset.resize((count + len(chunk),))
                dataset[count:count + len(chunk)] = np.frombuffer(chunk, dtype=np.uint8)
                count += len(chunk)
            handle.attrs["logical_hash"] = logical_hash.hexdigest()
            handle.create_dataset("control_step", data=np.arange(len(value["boundaries"]), dtype=np.int64))
            handle.create_dataset("native_step_index", data=np.asarray(
                [boundary["native_step_index"] for boundary in value["boundaries"]], dtype=np.int64))
        os.replace(temporary, path)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise
    return {"path": str(path), "logical_hash": logical_hash.hexdigest(),
            "logical_bytes": count, "source_validation_s": validated - started,
            "encode_compress_write_s": perf_counter() - validated,
            "chunk_bytes": chunk_bytes}


def verify_roundtrip(path, value, *, chunk_bytes=BUFFER_BYTES):
    """Compare every stored JSON byte to the original mapping's canonical encoding.

    Source semantics are validated by save_streaming. This independently reads
    the persisted bytes, checks their hash and numeric projections, and avoids
    deserializing a second episode. It does not replace a live D0/D1/D2 check.
    """
    import h5py
    from .execution import FILE_SCHEMA, LEGACY_FILE_SCHEMA, SCHEMA

    started = perf_counter()
    digest = hashlib.sha256()
    count = 0
    with h5py.File(path, "r") as handle:
        _check_container(handle)
        expected_schema = FILE_SCHEMA if value["schema"] == SCHEMA else LEGACY_FILE_SCHEMA
        if handle.attrs["schema"] != expected_schema:
            raise ValueError("H5/logical version mismatch")
        dataset = handle["logical_json_utf8"]
        for expected in logical_chunks(value, chunk_bytes):
            if count + len(expected) > dataset.size:
                raise ValueError(f"truncated logical payload at byte {count}")
            actual = dataset[count:count + len(expected)].tobytes()
            if actual != expected:
                mismatch = next(i for i, (a, b) in enumerate(zip(actual, expected)) if a != b)
                raise ValueError(f"logical byte divergence at byte {count + mismatch}")
            digest.update(actual)
            count += len(actual)
        if count != dataset.size:
            raise ValueError("extra logical payload bytes")
        if digest.hexdigest() != handle.attrs["logical_hash"]:
            raise ValueError("logical hash")
        _check_projections(handle, value)
    return {"version": VERIFICATION_VERSION, "logical_hash": digest.hexdigest(),
            "logical_bytes": count, "byte_exact": True,
            "read_compare_hash_s": perf_counter() - started,
            "legacy_full_object_load_executed": False, "chunk_bytes": chunk_bytes}


def verify_payload_integrity(path, *, chunk_bytes=BUFFER_BYTES):
    """Read-only whole-payload integrity check for an archived/interrupted file.

    This deliberately reports no semantic/FULL verdict without source data.
    """
    import h5py
    started = perf_counter()
    digest = hashlib.sha256()
    with h5py.File(path, "r") as handle:
        _check_container(handle)
        dataset = handle["logical_json_utf8"]
        for offset in range(0, dataset.size, chunk_bytes):
            digest.update(dataset[offset:offset + chunk_bytes].tobytes())
        if digest.hexdigest() != handle.attrs["logical_hash"]:
            raise ValueError("logical hash")
        boundaries = len(handle["control_step"])
        if not np.array_equal(handle["control_step"][:], np.arange(boundaries, dtype=np.int64)):
            raise ValueError("control_step projection")
        native = handle["native_step_index"][:]
        if len(native) != boundaries or not boundaries or native[0] != 0 or (
                boundaries > 1 and (native[1] <= 0 or not np.array_equal(
                    native, np.arange(boundaries, dtype=np.int64) * native[1]))):
            raise ValueError("native_step_index projection")
        result = {"logical_hash": digest.hexdigest(), "logical_bytes": int(dataset.size),
                  "boundaries": boundaries, "payload_integrity": "PASS",
                  "semantic_validation": "NOT_RUN", "full_expert_status": "UNKNOWN"}
    result["read_hash_s"] = perf_counter() - started
    return result


def _check_container(handle):
    from .execution import FILE_SCHEMA, LEGACY_FILE_SCHEMA
    if set(handle) != {"logical_json_utf8", "control_step", "native_step_index"} or (
            handle.attrs.get("schema") not in (FILE_SCHEMA, LEGACY_FILE_SCHEMA)):
        raise ValueError("H5 execution schema")
    for name in ("control_step", "native_step_index"):
        if handle[name].ndim != 1 or handle[name].dtype != np.dtype(np.int64):
            raise ValueError("numeric projection dtype/shape")
    if handle["logical_json_utf8"].ndim != 1 or handle["logical_json_utf8"].dtype != np.dtype(np.uint8):
        raise ValueError("logical payload dtype/shape")


def _check_projections(handle, value):
    for name, expected in (
            ("control_step", np.arange(len(value["boundaries"]), dtype=np.int64)),
            ("native_step_index", np.asarray([b["native_step_index"] for b in value["boundaries"]], dtype=np.int64))):
        if not np.array_equal(handle[name][:], expected):
            raise ValueError("numeric projection")


class _JsonCursor:
    """Incrementally decode top-level episode records, including split UTF-8."""
    def __init__(self, dataset, chunk_bytes):
        self.dataset = dataset
        self.chunk_bytes = chunk_bytes
        self.offset = 0
        self.buffer = ""
        self.position = 0
        self.eof = False
        self.utf8 = codecs.getincrementaldecoder("utf-8")()
        self.decoder = json.JSONDecoder()

    def fill(self):
        self.buffer = self.buffer[self.position:]
        self.position = 0
        end = min(self.offset + self.chunk_bytes, self.dataset.size)
        raw = self.dataset[self.offset:end].tobytes()
        self.offset = end
        self.eof = end == self.dataset.size
        self.buffer += self.utf8.decode(raw, final=self.eof)

    def peek(self):
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position].isspace():
                self.position += 1
            if self.position < len(self.buffer):
                return self.buffer[self.position]
            if self.eof:
                return ""
            self.fill()

    def take(self, token):
        if self.peek() != token:
            raise ValueError(f"logical JSON expected {token!r}")
        self.position += 1

    def value(self):
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
                # A numeric token may end on a read boundary or before a split
                # exponent. Wait for its delimiter rather than accepting 1e as 1.
                if end == len(self.buffer) and not self.eof:
                    self.fill()
                    continue
                if end < len(self.buffer) and self.buffer[end] not in " \r\n\t,:]}":
                    if self.eof:
                        raise ValueError("invalid logical JSON value delimiter")
                    self.fill()
                    continue
                self.position = end
                return value
            except json.JSONDecodeError:
                if self.eof:
                    raise
                self.fill()

    def array(self):
        self.take("[")
        items = []
        if self.peek() != "]":
            while True:
                items.append(self.value())
                if self.peek() == "]":
                    break
                self.take(",")
        self.take("]")
        return items

    def blobs(self):
        self.take("{")
        result = {}
        if self.peek() != "}":
            while True:
                key = self.value()
                if not isinstance(key, str):
                    raise ValueError("JSON object key must be a string")
                self.take(":")
                result[key] = self.value()
                if self.peek() == "}":
                    break
                self.take(",")
        self.take("}")
        return result

    def episode(self):
        self.take("{")
        result = {}
        if self.peek() != "}":
            while True:
                key = self.value()
                if not isinstance(key, str):
                    raise ValueError("JSON object key must be a string")
                self.take(":")
                if key in {"boundaries", "transitions"}:
                    result[key] = self.array()
                elif key == "blobs":
                    result[key] = self.blobs()
                else:
                    result[key] = self.value()
                if self.peek() == "}":
                    break
                self.take(",")
        self.take("}")
        if self.peek():
            raise ValueError("extra logical JSON data")
        return result


def load_streaming(path, *, chunk_bytes=BUFFER_BYTES, profile=None):
    """Same validated mapping as load(), without whole-payload temporary copies.

    The final Python mapping is still resident: this is a bounded-buffer reader,
    not a lazy replay API. All semantic predicates and numeric projections remain
    checked, and the canonical logical hash is recomputed from every record.
    """
    import h5py
    from .execution import FILE_SCHEMA, LEGACY_FILE_SCHEMA, SCHEMA, validate
    if type(chunk_bytes) is not int or chunk_bytes <= 0:
        raise ValueError("positive integer I/O chunk size required")
    started = perf_counter()
    with h5py.File(path, "r") as handle:
        _check_container(handle)
        value = _JsonCursor(handle["logical_json_utf8"], chunk_bytes).episode()
        expected_schema = FILE_SCHEMA if value["schema"] == SCHEMA else LEGACY_FILE_SCHEMA
        if handle.attrs["schema"] != expected_schema:
            raise ValueError("H5/logical version mismatch")
        expected_hash = handle.attrs["logical_hash"]
        _check_projections(handle, value)
    parsed = perf_counter()
    validate(value)
    validated = perf_counter()
    hashed = hashlib.sha256()
    for chunk in logical_chunks(value, chunk_bytes):
        hashed.update(chunk)
    if hashed.hexdigest() != expected_hash:
        raise ValueError("logical hash")
    if profile is not None:
        profile.update(parse_s=parsed - started, semantic_validation_s=validated - parsed,
                       logical_hash_s=perf_counter() - validated,
                       total_s=perf_counter() - started, chunk_bytes=chunk_bytes)
    return value
