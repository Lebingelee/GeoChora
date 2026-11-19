"""Generic BDDL -> goal converter (format-generic; covers LIBERO- and BEHAVIOR-style BDDL).

Translates notation only, never meaning. The caller supplies the vocabulary version whose
predicate semantics apply (e.g. ``"libero-predicates/<rev>"``); this module knows no predicate list.

Output goal node grammar (``docs/module/validation/contracts.md#goal-evaluator``)::

    node := {"all": [node, ...]} | {"any": [node, ...]} | {"not": node}
          | {"pred": name, "args": [obj, ...]}

Parsing rules
-------------
* S-expressions; ``;`` starts a comment to end of line; ``"..."`` is one string token.
* Keywords are case-insensitive: ``define``, ``problem``, section names (``:goal``, ``:Goal``),
  connectives ``and/or/not`` (``And``, ``AND`` ...), quantifier/unsupported keywords.
* Predicate names are kept exactly as written by default (``predicate_case="preserve"``).
  The only alternative rule is ``predicate_case="lower"`` (ASCII lower-casing of the predicate name,
  matching e.g. LIBERO's own ``name.lower()`` lookup). Allowlist matching is exact on the
  name *after* this rule is applied.
* Object / fixture names and argument tokens are kept verbatim (never case-normalised).
* Sections: ``:domain``, ``:requirements``, ``:language``, ``:regions`` (recorded raw, not interpreted),
  ``:fixtures``, ``:objects``, ``:obj_of_interest``, ``:init``, ``:goal``. Any other section is an error.
  ``:goal`` is required and must appear once.

Supported goal constructs
-------------------------
``and`` -> ``all``, ``or`` -> ``any``, ``not`` (exactly one operand) -> ``not``, atoms
``(Pred a b ...)`` with symbol arguments -> ``{"pred", "args"}`` (zero-arity atoms allowed).

Unsupported (raise :class:`BDDLError` naming the construct; never skipped)
--------------------------------------------------------------------------
* Quantifiers ``exists``, ``forall`` and BEHAVIOR's ``forn``/``forpairs``/``fornpairs``: **rejected**.
  The goal grammar has no nested quantifier node; the evaluator's task-level ``bind`` is an
  existential with all-distinct, not-explicitly-named variables, which differs from BDDL scoping
  (quantifiers under ``not``/``or``, typed ranges over the object set, non-distinct bindings), so
  no mapping is clean in general. Expanding over :objects would change meaning silently.
* ``imply``, ``when``, ``either``, ``preference``.
* Numeric fluents/comparisons (``=``, ``<``, ``>``, ``<=``, ``>=``, ``+``, ``-``, ``*``, ``/``,
  ``increase``, ``decrease``, ``assign``, ``scale-up``, ``scale-down``), numeric literals,
  ``?variables`` (no binders are supported), nested lists as atom arguments, empty ``and``/``or``.

Optional ``allowlist``: ``{pred_name: arity | iterable of arities}``. A predicate not in it, or with
a wrong arity, raises :class:`BDDLError`.

Optional ``include_init``: ``(:init ...)`` is converted to a list of literal nodes (atoms or
``not`` of an atom), returned separately under ``"init"`` (useful to check a goal isn't already
satisfied initially). The allowlist applies to init literals too.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable, Mapping

CONVERTER_VERSION = 'bddl-goal-converter/1.0.0'
BASIS = 'native_converted'

_KNOWN_SECTIONS = (':domain', ':requirements', ':language', ':regions', ':fixtures', ':objects',
                   ':obj_of_interest', ':init', ':goal')
_QUANTIFIERS = {'exists', 'forall', 'forn', 'forpairs', 'fornpairs'}
_OTHER_UNSUPPORTED = {'imply', 'when', 'either', 'preference'}
_NUMERIC = {'=', '<', '>', '<=', '>=', '+', '-', '*', '/', 'increase', 'decrease', 'assign',
            'scale-up', 'scale-down'}
_NUMBER_RE = re.compile(r'^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$')


class BDDLError(ValueError):
    """Raised for malformed BDDL, unsupported constructs, allowlist violations or hash mismatch."""


class _Str(str):
    """A double-quoted string token (distinguished from a bare symbol)."""


# --------------------------------------------------------------------------- s-expressions
def _tokenize(text: str) -> list:
    tokens, i, n, line = [], 0, len(text), 1
    while i < n:
        c = text[i]
        if c == '\n':
            line += 1
            i += 1
        elif c.isspace():
            i += 1
        elif c == ';':
            while i < n and text[i] != '\n':
                i += 1
        elif c in '()':
            tokens.append((c, line))
            i += 1
        elif c == '"':
            j = text.find('"', i + 1)
            if j < 0:
                raise BDDLError(f'unterminated string literal at line {line}')
            tokens.append((_Str(text[i + 1:j]), line))
            line += text.count('\n', i, j)
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '();"':
                j += 1
            tokens.append((text[i:j], line))
            i = j
    return tokens


def parse_sexprs(text: str) -> list:
    """Parse text into a list of top-level s-expressions (nested Python lists of str tokens)."""
    stack: list = [[]]
    open_lines: list = []
    for tok, line in _tokenize(text):
        if tok == '(' and not isinstance(tok, _Str):
            stack.append([])
            open_lines.append(line)
        elif tok == ')' and not isinstance(tok, _Str):
            if len(stack) == 1:
                raise BDDLError(f"unbalanced ')' at line {line}")
            done = stack.pop()
            open_lines.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(tok)
    if len(stack) != 1:
        raise BDDLError(f"unbalanced '(' opened at line {open_lines[-1]}")
    return stack[0]


def _kw(tok) -> str | None:
    return tok.lower() if isinstance(tok, str) and not isinstance(tok, _Str) else None


def _render(expr) -> str:
    if isinstance(expr, list):
        return '(' + ' '.join(_render(e) for e in expr) + ')'
    return f'"{expr}"' if isinstance(expr, _Str) else str(expr)


# --------------------------------------------------------------------------- sections
def _typed_list(items: list, section: str) -> dict:
    """``a b - T c - U d`` -> {a: T, b: T, c: U, d: None}; order preserved, duplicates rejected."""
    out: dict = {}
    pending: list = []
    i = 0
    while i < len(items):
        tok = items[i]
        if isinstance(tok, list) or isinstance(tok, _Str):
            raise BDDLError(f'{section}: expected symbol, got {_render(tok)}')
        if tok == '-':
            if i + 1 >= len(items) or isinstance(items[i + 1], list) or not pending:
                raise BDDLError(f"{section}: dangling '-' type marker")
            typ = items[i + 1]
            if _kw(typ) == 'either':
                raise BDDLError(f'{section}: unsupported construct either')
            for name in pending:
                out[name] = typ
            pending = []
            i += 2
            continue
        if tok in out or tok in pending:
            raise BDDLError(f'{section}: duplicate name {tok}')
        pending.append(tok)
        i += 1
    for name in pending:
        out[name] = None
    return out


def _normalise_allowlist(allowlist) -> dict | None:
    if allowlist is None:
        return None
    norm = {}
    for name, ar in allowlist.items():
        arities = {ar} if isinstance(ar, int) else set(ar)
        if not arities or not all(isinstance(a, int) and a >= 0 for a in arities):
            raise BDDLError(f'allowlist: invalid arity spec for {name!r}: {ar!r}')
        norm[name] = frozenset(arities)
    return norm


class _Converter:
    def __init__(self, predicate_case: str, allowlist: dict | None):
        if predicate_case not in ('preserve', 'lower'):
            raise BDDLError(f"predicate_case must be 'preserve' or 'lower', got {predicate_case!r}")
        self.case = predicate_case
        self.allow = allowlist

    def atom(self, expr: list, where: str) -> dict:
        head = expr[0]
        if isinstance(head, list) or isinstance(head, _Str):
            raise BDDLError(f'{where}: predicate name must be a symbol: {_render(expr)}')
        if head.startswith('?'):
            raise BDDLError(f'{where}: variable in predicate position: {_render(expr)}')
        name = head.lower() if self.case == 'lower' else head
        args = []
        for a in expr[1:]:
            if isinstance(a, list):
                raise BDDLError(f'{where}: nested expression as argument (unsupported construct): {_render(expr)}')
            if isinstance(a, _Str):
                raise BDDLError(f'{where}: string literal argument (unsupported construct): {_render(expr)}')
            if a.startswith('?'):
                raise BDDLError(f'{where}: unbound variable {a} (quantifiers unsupported): {_render(expr)}')
            if _NUMBER_RE.match(a):
                raise BDDLError(f'{where}: numeric literal {a} (numeric fluents unsupported): {_render(expr)}')
            args.append(a)
        if self.allow is not None:
            if name not in self.allow:
                raise BDDLError(f'{where}: unknown predicate {name!r} (not in allowlist): {_render(expr)}')
            if len(args) not in self.allow[name]:
                raise BDDLError(f'{where}: predicate {name!r} has arity {len(args)}, allowed '
                                f'{sorted(self.allow[name])}: {_render(expr)}')
        return {'pred': name, 'args': args}

    def node(self, expr, where: str) -> dict:
        if not isinstance(expr, list):
            raise BDDLError(f'{where}: expected a parenthesised expression, got {_render(expr)}')
        if not expr:
            raise BDDLError(f'{where}: empty expression ()')
        kw = _kw(expr[0])
        if kw in ('and', 'or'):
            if len(expr) == 1:
                raise BDDLError(f'{where}: empty ({expr[0]}) is unsupported')
            return {'all' if kw == 'and' else 'any': [self.node(e, where) for e in expr[1:]]}
        if kw == 'not':
            if len(expr) != 2:
                raise BDDLError(f'{where}: (not ...) takes exactly one operand: {_render(expr)}')
            return {'not': self.node(expr[1], where)}
        if kw in _QUANTIFIERS:
            raise BDDLError(f'{where}: unsupported construct {kw} (quantifiers are not converted): {_render(expr)}')
        if kw in _OTHER_UNSUPPORTED:
            raise BDDLError(f'{where}: unsupported construct {kw}: {_render(expr)}')
        if kw in _NUMERIC:
            raise BDDLError(f'{where}: unsupported construct {kw} (numeric fluents): {_render(expr)}')
        return self.atom(expr, where)

    def literal(self, expr, where: str) -> dict:
        if isinstance(expr, list) and expr and _kw(expr[0]) == 'not':
            if len(expr) != 2 or not isinstance(expr[1], list) or not expr[1]:
                raise BDDLError(f'{where}: malformed (not ...): {_render(expr)}')
            inner = self.literal(expr[1], where)
            if 'not' in inner:
                raise BDDLError(f'{where}: nested not in init literal: {_render(expr)}')
            return {'not': inner}
        node = self.node(expr, where)
        if 'pred' not in node and 'not' not in node:
            raise BDDLError(f'{where}: init entries must be literals, got {_render(expr)}')
        return node


# --------------------------------------------------------------------------- public API
def convert_bddl_text(text: str | bytes, *, vocabulary: str, source_path: str | None = None,
                      expected_sha256: str | None = None, allowlist: Mapping[str, int | Iterable[int]] | None = None,
                      predicate_case: str = 'preserve', include_init: bool = False) -> dict:
    """Convert one BDDL problem to a goal document.

    Returns ``{"format": "bddl", "problem", "domain", "language", "objects", "fixtures",
    "obj_of_interest", "goal", "init" (list or None), "vocabulary", "basis": "native_converted",
    "provenance": {"source_path", "sha256", "converter"}}``. ``objects``/``fixtures`` map
    name -> type (``None`` if untyped), in source order. ``language`` is the raw tokens joined by
    single spaces (None if absent); ``regions`` are not interpreted.
    """
    if not isinstance(vocabulary, str) or not vocabulary.strip():
        raise BDDLError('vocabulary version must be a non-empty string supplied by the caller')
    raw = text.encode('utf-8') if isinstance(text, str) else bytes(text)
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and expected_sha256.lower() != sha:
        raise BDDLError(f'sha256 mismatch for {source_path or "<text>"}: expected {expected_sha256}, got {sha}')
    try:
        decoded = raw.decode('utf-8-sig')
    except UnicodeDecodeError as e:
        raise BDDLError(f'source is not valid UTF-8: {e}') from None

    top = parse_sexprs(decoded)
    if len(top) != 1 or not isinstance(top[0], list) or not top[0] or _kw(top[0][0]) != 'define':
        raise BDDLError('expected exactly one top-level (define ...) form')
    form = top[0]
    if len(form) < 2 or not isinstance(form[1], list) or len(form[1]) != 2 or _kw(form[1][0]) != 'problem' \
            or isinstance(form[1][1], list):
        raise BDDLError('expected (problem <name>) as the first element of define')
    problem = form[1][1]

    sections: dict = {}
    for sec in form[2:]:
        if not isinstance(sec, list) or not sec or _kw(sec[0]) is None or not _kw(sec[0]).startswith(':'):
            raise BDDLError(f'expected a (:section ...) form, got {_render(sec)}')
        key = _kw(sec[0])
        if key not in _KNOWN_SECTIONS:
            raise BDDLError(f'unsupported section {sec[0]}')
        if key in sections:
            raise BDDLError(f'duplicate section {sec[0]}')
        sections[key] = sec[1:]
    if ':goal' not in sections:
        raise BDDLError('missing (:goal ...) section')

    domain = None
    if ':domain' in sections:
        d = sections[':domain']
        if len(d) != 1 or isinstance(d[0], list):
            raise BDDLError('(:domain ...) must contain exactly one name')
        domain = d[0]
    language = ' '.join(str(t) for t in sections[':language']) if ':language' in sections else None
    if language is not None and any(isinstance(t, list) for t in sections[':language']):
        raise BDDLError('(:language ...) must not contain nested expressions')
    objects = _typed_list(sections.get(':objects', []), ':objects')
    fixtures = _typed_list(sections.get(':fixtures', []), ':fixtures')
    clash = sorted(set(objects) & set(fixtures))
    if clash:
        raise BDDLError(f'names declared both as object and fixture: {clash}')
    ooi = sections.get(':obj_of_interest', [])
    if any(isinstance(t, list) for t in ooi):
        raise BDDLError('(:obj_of_interest ...) must contain names only')

    conv = _Converter(predicate_case, _normalise_allowlist(allowlist))
    g = sections[':goal']
    if len(g) != 1:
        raise BDDLError(f'(:goal ...) must contain exactly one expression, got {len(g)}')
    goal = conv.node(g[0], ':goal')
    init = [conv.literal(e, ':init') for e in sections.get(':init', [])] if include_init else None

    return {
        'format': 'bddl',
        'problem': problem,
        'domain': domain,
        'language': language,
        'objects': objects,
        'fixtures': fixtures,
        'obj_of_interest': list(ooi),
        'goal': goal,
        'init': init,
        'vocabulary': vocabulary,
        'basis': BASIS,
        'provenance': {'source_path': source_path, 'sha256': sha, 'converter': CONVERTER_VERSION},
    }


def convert_bddl_file(path: str | Path, *, vocabulary: str, expected_sha256: str | None = None,
                      allowlist: Mapping[str, int | Iterable[int]] | None = None,
                      predicate_case: str = 'preserve', include_init: bool = False) -> dict:
    """Read ``path`` as bytes and convert (see :func:`convert_bddl_text`); ``source_path`` = posix path."""
    p = Path(path)
    return convert_bddl_text(p.read_bytes(), vocabulary=vocabulary, source_path=p.as_posix(),
                             expected_sha256=expected_sha256, allowlist=allowlist,
                             predicate_case=predicate_case, include_init=include_init)
