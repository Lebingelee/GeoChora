"""Reversible, readable JSON presentation for opt-in terminal model inputs.

This changes representation only: no task rules, rounding, resampling or loss of
missing values. Original files and hashes remain the evidence authority.
"""
from copy import deepcopy
import json


ENCODING = 'lossless-json/0.1'
_TAGS = {'$literal', '$constant', '$records', '$arrays'}
_GUIDE = (
    'Lossless JSON presentation (not new measurements). Decode recursively: '
    '$constant={count,value} repeats the decoded value count times; '
    '$records={count,columns} reconstructs count row objects by taking each decoded column[i]; '
    '$arrays={count,columns} reconstructs count row arrays by taking each decoded column[i] in order; '
    '$literal holds an ordinary object whose keys are literal and values are recursively decoded. '
    'Other objects/arrays are ordinary JSON. Preserve all nulls, values and row order.\n'
)


def _text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _encode(value):
    if isinstance(value, dict):
        result = {key: _encode(item) for key, item in value.items()}
        return {'$literal': result} if _TAGS.intersection(value) else result
    if not isinstance(value, list):
        return value
    ordinary = [_encode(item) for item in value]
    if len(value) < 2:
        return ordinary
    candidates = [ordinary]
    if all(_text(item) == _text(value[0]) for item in value[1:]):
        candidates.append({'$constant': {'count': len(value), 'value': ordinary[0]}})
    if all(isinstance(item, dict) and item.keys() == value[0].keys() for item in value):
        candidates.append({'$records': {'count': len(value), 'columns': {
            key: _encode([row[key] for row in value]) for key in value[0]}}})
    if (all(isinstance(item, list) for item in value)
            and value[0] and all(len(item) == len(value[0]) for item in value)):
        candidates.append({'$arrays': {'count': len(value), 'columns': [
            _encode([row[i] for row in value]) for i in range(len(value[0]))]}})
    return min(candidates, key=lambda item: len(_text(item)))


def decode(value):
    """Expand this module's tagged presentation; useful for independent audits."""
    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    if '$literal' in value:
        return {key: decode(item) for key, item in value['$literal'].items()}
    if '$constant' in value:
        item = value['$constant']
        return [deepcopy(decode(item['value'])) for _ in range(item['count'])]
    for tag in ('$records', '$arrays'):
        if tag in value:
            item = value[tag]
            columns = item['columns']
            if tag == '$records':
                columns = {key: decode(column) for key, column in columns.items()}
                return [{key: column[i] for key, column in columns.items()} for i in range(item['count'])]
            columns = [decode(column) for column in columns]
            return [[column[i] for column in columns] for i in range(item['count'])]
    return {key: decode(item) for key, item in value.items()}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def present(body):
    """Use tagged JSON only when shorter, with an exact typed round-trip check.

    Non-JSON, duplicate-key and non-finite documents keep their original text.
    Nothing attempts to decode or execute XML, code or binary evidence.
    """
    try:
        value = json.loads(body, object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        encoded = _encode(value)
        if _text(decode(encoded)) != _text(value):
            raise RuntimeError('lossless evidence presentation failed round-trip validation')
        packed = _GUIDE + _text(encoded)
        return packed if len(packed) < len(body) else body
    except (ValueError, RecursionError):
        return body
