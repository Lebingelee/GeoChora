"""Finite JSON, source pointers and frozen request/dispatch validation.

The legacy exception and receipt names are retained for existing source-review
callers. This module has no specification compiler, vocabulary or model SDK.
"""
from collections.abc import Mapping
import hashlib
import json
import re

_DISPATCH = "terminal-spec-model-dispatch/0.1"


class InvalidGenerationProtocol(ValueError):
    """Malformed or inconsistent generation/review provenance; no admission."""

def _json(value):
    try:
        copied = json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":"), allow_nan=False))
        if copied != value:
            raise ValueError("non-JSON keys or values")
        return copied
    except (TypeError, ValueError) as error:
        raise InvalidGenerationProtocol("finite JSON documents required") from error

def _keys(value, names, label):
    if not isinstance(value, Mapping) or set(value) != set(names):
        raise InvalidGenerationProtocol(label + " has missing or unknown fields")

def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise InvalidGenerationProtocol(label + " must be nonempty text")

def _profile(value):
    _keys(value, ("name", "reasoning_effort"), "model profile")
    for name in value:
        _text(value[name], "model " + name)
    return _json(value)

def _seal(document):
    return {**document, "request_sha256": _digest(document)}

def _dispatch(receipt, request, response):
    receipt = _json(receipt)
    _keys(receipt, ("schema_version", "dispatch_id", "context_id", "model_profile",
                    "request_sha256", "response_sha256"), "caller dispatch receipt")
    for name in ("dispatch_id", "context_id"):
        _text(receipt[name], name)
    if (receipt["schema_version"] != _DISPATCH or receipt["model_profile"] != request["model_profile"]
            or receipt["request_sha256"] != request["request_sha256"]
            or receipt["response_sha256"] != _digest(response)):
        raise InvalidGenerationProtocol("caller dispatch differs from requested model or exact request/response")
    return receipt

class InvalidTerminalSpec(ValueError):
    """The specification or its source/meaning references are invalid."""

def _digest(value):
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise InvalidTerminalSpec("canonical JSON data required") from error
    return hashlib.sha256(raw).hexdigest()

def _pointer(source, path):
    if not isinstance(path, str) or not path.startswith("/"):
        raise InvalidTerminalSpec("source basis must be a JSON pointer")
    current = source
    try:
        for token in path.split("/")[1:]:
            if re.search(r"~(?:[^01]|$)", token):
                raise ValueError("invalid JSON pointer escape")
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(current, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", token):
                    raise ValueError("invalid array index")
                current = current[int(token)]
            else:
                current = current[token]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise InvalidTerminalSpec(f"missing source pointer: {path}") from error
    return current

def _hash(value, name):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise InvalidGenerationProtocol(name + " requires a canonical SHA-256")
