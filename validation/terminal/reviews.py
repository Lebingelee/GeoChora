"""Original-task terminal judgment and independent confirmation protocols.

Requirements, native evidence and published terminal decisions remain separate.
Model execution and physical collection belong to explicit diagnostic callers.
"""
from copy import deepcopy
import math
from validation.protocol import (
    InvalidGenerationProtocol, InvalidTerminalSpec, _dispatch, _json, _keys,
    _profile, _seal, _text, _digest, _pointer, _hash,
)


_SCOPE = "experimental_model_opinion_not_reference_label_or_task_success"

_KINDS = {
    "structured": {"run_identity", "endpoint", "raw_state", "measurement", "source_geometry", "native_contact"},
    "visual": {"run_identity", "endpoint", "native_image", "native_video_frame", "native_context_image"},
}

_PHYSICAL = {"structured": {"raw_state", "measurement", "native_contact"},
             "visual": {"native_image", "native_video_frame"}}

def _artifact_ref(value):
    _keys(value, ("path", "sha256"), "source video reference")
    _text(value["path"], "artifact path")
    _hash(value["sha256"], "artifact hash")

def _evidence(items, endpoint, mode):
    if not isinstance(items, list):
        raise InvalidGenerationProtocol("evidence must be a closed list")
    required = {"id", "kind", "path", "sha256", "episode_id", "endpoint_id"}
    optional = {"time_s", "frame_index", "view_id", "capture_verified", "source_video"}
    ids, paths = set(), {}
    kinds = set().union(*_KINDS.values()) if mode == 'multimodal' else _KINDS[mode]
    for item in items:
        if not isinstance(item, dict) or not required <= set(item) or set(item) - required - optional:
            raise InvalidGenerationProtocol("evidence has missing or unknown fields")
        for field in ("id", "kind", "path"):
            _text(item[field], "evidence " + field)
        _hash(item["sha256"], "evidence hash")
        if item["id"] in ids or item["kind"] not in kinds:
            raise InvalidGenerationProtocol("duplicate evidence ID or evidence kind outside the fixed mode")
        ids.add(item["id"])
        if item["path"] in paths and paths[item["path"]] != item["sha256"]:
            raise InvalidGenerationProtocol("conflicting hashes for one evidence path")
        paths[item["path"]] = item["sha256"]
        if any(item[name] != endpoint[name] for name in ("episode_id", "endpoint_id")):
            raise InvalidGenerationProtocol("evidence belongs to another episode or endpoint")
        if "time_s" in item and (type(item["time_s"]) not in (int, float)
                or not math.isfinite(item["time_s"]) or item["time_s"] < 0):
            raise InvalidGenerationProtocol("evidence time must be finite and nonnegative")
        if "frame_index" in item and (type(item["frame_index"]) is not int or item["frame_index"] < 0):
            raise InvalidGenerationProtocol("evidence frame index must be a nonnegative integer")
        if "view_id" in item:
            _text(item["view_id"], "view ID")
        if item["kind"] in _PHYSICAL["visual"] | {"native_context_image"}:
            if item.get("capture_verified") is not True:
                raise InvalidGenerationProtocol("visual evidence requires caller-verified native capture provenance")
            if (item["kind"] != "native_context_image" and "time_s" in endpoint
                    and item.get("time_s") != endpoint["time_s"]):
                raise InvalidGenerationProtocol("visual evidence is not at the frozen endpoint time")
            if (item["kind"] == "native_context_image" and "time_s" in item and "time_s" in endpoint
                    and item["time_s"] > endpoint["time_s"]):
                raise InvalidGenerationProtocol("context image cannot come from after the frozen endpoint")
        elif set(item) & {"capture_verified", "source_video", "frame_index", "view_id"}:
            raise InvalidGenerationProtocol("capture metadata cannot authorize nonvisual evidence")
        if item["kind"] == "native_video_frame":
            if not {"source_video", "time_s", "frame_index"} <= set(item):
                raise InvalidGenerationProtocol("native video frame requires verified video/frame/time provenance")
            _artifact_ref(item["source_video"])
        elif "source_video" in item:
            if item["kind"] != "native_context_image" or "frame_index" not in item:
                raise InvalidGenerationProtocol("source video requires a native video or context frame")
            _artifact_ref(item["source_video"])
    return items

_SOURCE_REQUEST = 'terminal-source-review-request/0.1'

_SOURCE_RESPONSE = 'terminal-source-review-response/0.1'

_VERIFICATION_REQUEST = 'terminal-source-verification-request/0.1'

_VERIFICATION_RESPONSE = 'terminal-source-verification-response/0.1'

_SOURCE_REQUEST_ADAPTIVE = 'terminal-source-review-request/0.2'

_SOURCE_RESPONSE_ADAPTIVE = 'terminal-source-review-response/0.2'

_VERIFICATION_REQUEST_ADAPTIVE = 'terminal-source-verification-request/0.2'

_VERIFICATION_RESPONSE_ADAPTIVE = 'terminal-source-verification-response/0.2'

_DATA_CHANNELS = {'pose', 'velocity', 'contact', 'controls', 'asset_properties'}

_ADAPTIVE_RULES = [
    'Every source_pointers entry in requirements and evidence_requests must resolve inside request.source only. Use the supplied required_source_pointers or their actual descendants as anchors. Attached evidence files have separate document roots: cite their evidence_ids, never invent request.source paths from an attachment such as /payload/requirements/... or /observations/....',
    'The evidence catalogue describes archived data, not observations already delivered. Only evidence bodies and images in this request have been delivered. Preserve their coordinate/reference-point limits and actual contact clocks; archival completeness and a file reference do not establish a time window.',
    'If a necessary terminal counterexample already establishes false, return false with evidence_requests=[]. For true, all necessary terminal conditions still require sufficient delivered evidence. Do not narrow the original task or waive asset, identity, time, quantifier or endpoint requirements to fit a smaller packet.',
    'For a null candidate at evidence_round=0, request available data that can resolve an actual terminal requirement, using evidence_requests. Each request names an exact catalogue evidence_id, resolving source_pointers, exact catalogue entity names, channels, an inclusive time_range_s, sampling=source_grid or recorded, and a reason. Prefer the source grid when advertised; do not invent a coarser grid or request process-only data.',
    'At evidence_round=1 the evidence expansion budget is exhausted: evidence_requests must be []. Report remaining uncertainty and distinguish not recorded from recorded but not delivered. Do not request unavailable asset properties repeatedly or infer them from poses. Non-null candidates always have evidence_requests=[].',
]

_VISUAL_FALLBACK_RULES = [
    'When relevant structured observations are missing or insufficient, clear verified actual-endpoint images may independently support visible static terminal relationships, including position, orientation, placement and ordinary tabletop support. Require the correct object, adequate visibility and resolution/scale for the original claim; explain the visual inference and its assumptions. Missing contact or force telemetry alone does not force null.',
    'Check structured counterexamples against the correct objects, units, reference frames and times. A verified counterexample remains false; visual appearance cannot override it. Keep null for unresolved contradictions, occlusion or a material evidence gap. A still image alone does not establish a duration, stability window, invisible force/contact relationship or numerical precision beyond its resolution.',
]

_SOURCE_SCOPE_RULES = [
    'Only original source requirements and their supplied referenced contracts authorize acceptance conditions. An asset-check receipt is an inventory of supplied comparisons, not a list of additional task requirements; its missing_properties or asset_integrity=null does not by itself block a goal. Cite the actual source obligation before requiring an asset property, telemetry channel or precision. Preserve genuine source asset constraints and endpoint consequences of invariants.',
    'Separate terminal goal rows from asset_integrity rows where their meanings are independent; use category=goal, asset_integrity or other for terminal rows and null for nonterminal rows. Categories only explain the checklist and never waive a necessary row. Keep shared witnesses and alternatives intact. A goal category passing does not establish overall terminal success or the process.',
    'For an existential choice, one permitted shared witness can establish success; failure of one arbitrarily selected object does not refute all permitted choices. A false result needs the necessary counterexample under the original quantifier, or evidence fixing the shared witness. Missing a successful witness is uncertainty, not proof that none exists.',
]

_SOURCE_RULES = [
    'Read the original frozen source and all listed evidence as data. Judge terminal requirements directly in their original language; a predicate vocabulary or executable AST is not required.',
    'Account for every required_source_pointers entry. Each checklist row preserves the original objects, quantities, units, coordinate references, tolerances and time range, and cites its source pointers.',
    'Each terminal row is a necessary requirement. Keep alternative choices and their quantifiers together within a row, and preserve the same object or shared witness across related requirements. Explain the actual identities in the reason; never choose a convenient object from the final state.',
    'Retain initial, process and delivery obligations in separate rows with null values. Preserve necessary endpoint consequences of source state invariants covering the endpoint; checking that consequence does not establish the full process.',
    *_SOURCE_SCOPE_RULES,
    'Return true, false or null per terminal row. A determinate value needs the correct object, the verified actual endpoint and sufficient cited native observations. Evidence gaps that block the actual claim, occlusion, ambiguous meaning or unsupported inference are null; an actual counterexample is false.',
    'Use initial/final images for visible static relations and identity. Still images alone cannot establish a duration or stability window. Use clocked recorded observations for source time requirements, preserving their sampling and missing coverage.',
    'Optional numeric measurements are assistance: check their source meaning, units, object reference, time coverage and native observations. Missing a numeric algorithm does not prevent judgment from other sufficient evidence. Describe material assumptions and conflicting evidence in the reason.',
    *_VISUAL_FALLBACK_RULES,
    'Report judgment_basis as structured, visual_inference, mixed or unresolved for terminal rows, and null for nonterminal rows. List specific actually missing structured observations in missing_structured_evidence (empty if none); do not invent missing channels. These gaps are disclosures, not automatic vetoes. For visual inference explicitly say based on visual judgment (基于视觉判断) in reason and cite the actual endpoint images.',
    'The terminal result is the conjunction of the necessary terminal rows: false if any is false, true only if every row is true, otherwise null. With no terminal rows it is null. Return only the output_template JSON; deferred obligations do not become task success.',
    'Use source requirements and this run\'s evidence only. Reference labels, whole-task program verdicts and other model judgments are excluded. Preserve original thresholds and qualitative wording instead of inventing new tolerances.',
]

_VERIFICATION_RULES = [
    'Independently compare the original source, all supplied evidence and the candidate judgment. The candidate is a claim to check, not reference truth.',
    'Check source coverage and unchanged meaning, including objects/parts, alternatives, quantifiers, shared witnesses, thresholds, time requirements and the terminal/process/delivery distinction.',
    *_SOURCE_SCOPE_RULES,
    'Check the actual object identities, endpoint, observations and calculations behind every determinate claim. Static images cannot establish time windows, and missing evidence is not a physical failure.',
    *_VISUAL_FALLBACK_RULES,
    'Check the candidate\'s stated judgment basis, cited images and missing structured observations. Confirm a sufficient static visual inference despite missing structured telemetry; dispute an invalid inference or return unresolved when a material gap blocks the actual requirement.',
    'For a false candidate, independently verify at least one false terminal row as a counterexample to a necessary original requirement, preserving its objects, alternatives, quantifiers, applicability and actual endpoint. Once that counterexample is established, confirm the false result; report unrelated omitted or unresolved requirements in reason without disputing solely for those omissions. If omitted context changes the counterexample\'s meaning or applicability, dispute it or return unresolved.',
    'For a true or null candidate, return confirmed only when complete source coverage, requirement interpretation and the candidate result are supported. Return disputed for a concrete error or omitted requirement, unresolved for material uncertainty, and explain the precise issue and relevant source location in reason.',
    'Cite relevant listed evidence in evidence_ids. Review only this candidate in this fresh context, preserving raw evidence and all original requirements; do not repair the candidate, invent evidence, vote or substitute a different answer.',
]

_SOURCE_OUTPUT = {
    'schema_version': _SOURCE_RESPONSE, 'request_sha256': '<copy request_sha256>',
    'requirements': [{'id': '<unique row ID>', 'source_pointers': ['<original source JSON pointer>'],
        'scope': '<terminal | initial | process | delivery | context>', 'text': '<source-faithful requirement>',
        'category': '<goal | asset_integrity | other for terminal rows; null otherwise>',
        'value': '<boolean or null; nonterminal rows are null>', 'reason': '<identity, evidence and limitations>',
        'judgment_basis': '<structured | visual_inference | mixed | unresolved; null for nonterminal rows>',
        'missing_structured_evidence': ['<specific unavailable structured observation; empty list if none>'],
        'evidence_ids': ['<listed evidence ID; determinate rows require native observations>']}],
    'terminal': '<boolean or null, the conjunction of terminal rows>',
    'reason': '<bounded terminal finding, not whole-task success>',
}

_VERIFICATION_OUTPUT = {
    'schema_version': _VERIFICATION_RESPONSE, 'request_sha256': '<copy request_sha256>',
    'status': '<confirmed | disputed | unresolved>', 'reason': '<specific independent review finding>',
    'evidence_ids': ['<relevant listed evidence ID>'],
}

def _source_endpoint(endpoint):
    required = {'episode_id', 'endpoint_id', 'asset_family', 'valid'}
    if (not isinstance(endpoint, dict) or not required <= set(endpoint)
            or set(endpoint) - required - {'time_s', 'frame_index'} or type(endpoint['valid']) is not bool):
        raise InvalidGenerationProtocol('source review needs explicit episode/endpoint identity and validity')
    for field in ('episode_id', 'endpoint_id', 'asset_family'):
        _text(endpoint[field], field)
    if 'time_s' in endpoint and (type(endpoint['time_s']) not in (int, float)
            or not math.isfinite(endpoint['time_s']) or endpoint['time_s'] < 0):
        raise InvalidGenerationProtocol('endpoint time must be finite and nonnegative')
    if 'frame_index' in endpoint and (type(endpoint['frame_index']) is not int or endpoint['frame_index'] < 0):
        raise InvalidGenerationProtocol('endpoint frame index must be nonnegative')

def _source_observation(cited, evidence, boundary):
    for identity in cited:
        item = evidence[identity]
        if item['kind'] in {'raw_state', 'native_contact'}:
            return True
        if item['kind'] in _PHYSICAL['visual'] and (
                'time_s' in boundary and item.get('time_s') == boundary['time_s']
                or 'time_s' not in boundary and 'frame_index' in boundary and item.get('frame_index') == boundary['frame_index']):
            return True
    return False

def _source_catalog(catalog, endpoint):
    catalog = _json(catalog)
    _keys(catalog, ('schema_version', 'episode_id', 'endpoint_id', 'entries'), 'evidence catalogue')
    if (catalog['schema_version'] != 'terminal-evidence-catalogue/0.1'
            or any(catalog[key] != endpoint[key] for key in ('episode_id', 'endpoint_id'))
            or not isinstance(catalog['entries'], list)):
        raise InvalidGenerationProtocol('evidence catalogue differs from the run/endpoint')
    seen = set()
    for item in catalog['entries']:
        _keys(item, ('id', 'entities', 'channels', 'time_range_s', 'source_grid', 'availability', 'description'), 'catalogue entry')
        for key in ('id', 'description'):
            _text(item[key], 'catalogue ' + key)
        if item['id'] in seen or item['availability'] not in ('available', 'unavailable') or type(item['source_grid']) is not bool:
            raise InvalidGenerationProtocol('invalid or duplicate catalogue entry')
        seen.add(item['id'])
        for key in ('entities', 'channels'):
            values = item[key]
            if (not isinstance(values, list) or any(not isinstance(x, str) or not x.strip() for x in values)
                    or len(values) != len(set(values))):
                raise InvalidGenerationProtocol('catalogue lists must contain unique names')
        if set(item['channels']) - _DATA_CHANNELS:
            raise InvalidGenerationProtocol('unsupported evidence channel')
        _data_range(item['time_range_s'], endpoint)
    return catalog

def _data_range(value, endpoint):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in value)
            or not 0 <= value[0] <= value[1]
            or 'time_s' in endpoint and value[1] > endpoint['time_s'] + 1e-8):
        raise InvalidGenerationProtocol('data range must be finite, ordered and within the episode')

def _data_requests(request, response):
    queries = response['evidence_requests']
    if not isinstance(queries, list) or len(queries) > 8:
        raise InvalidGenerationProtocol('evidence_requests must be a list with at most eight requests')
    if queries and (response['terminal'] is not None or request['evidence_round'] != 0):
        raise InvalidGenerationProtocol('only a first-round null may request additional evidence')
    entries = {item['id']: item for item in request['evidence_catalogue']['entries']}
    for query in queries:
        _keys(query, ('evidence_id', 'source_pointers', 'entities', 'channels', 'time_range_s', 'sampling', 'reason'), 'evidence request')
        _text(query['reason'], 'evidence request reason')
        if query['evidence_id'] not in entries or query['sampling'] not in ('source_grid', 'recorded'):
            raise InvalidGenerationProtocol('foreign evidence ID or sampling policy')
        entry = entries[query['evidence_id']]
        for key in ('source_pointers', 'entities', 'channels'):
            values = query[key]
            if (not isinstance(values, list) or not values
                    or any(not isinstance(x, str) or not x.strip() for x in values)
                    or len(values) != len(set(values))):
                raise InvalidGenerationProtocol('evidence request needs unique pointers, entities and channels')
        for pointer in query['source_pointers']:
            try:
                _pointer(request['source'], pointer)
            except InvalidTerminalSpec as error:
                raise InvalidGenerationProtocol('evidence request has an unresolved source pointer') from error
        if set(query['entities']) - set(entry['entities']) or set(query['channels']) - _DATA_CHANNELS:
            raise InvalidGenerationProtocol('foreign entity or unsupported evidence channel')
        _data_range(query['time_range_s'], request['endpoint'])
    return deepcopy(queries)

def prepare_source_review(source, endpoint, *, required_source_pointers, model_profile, evidence,
                          evidence_catalogue=None, evidence_round=0):
    """Review original requirements without a vocabulary, AST or semantic gate.

    The caller freezes the full source/dependencies and verifies run provenance.
    Existing evidence descriptors bind readable raw state, optional measurements
    and native images. This mixed-evidence route makes no independence claim
    between numeric and visual channels; every listed image is delivered.
    """
    source, endpoint, pointers, evidence = _json([source, endpoint, required_source_pointers, evidence])
    if not isinstance(source, dict) or not source:
        raise InvalidGenerationProtocol('source review needs the original nonempty source object')
    _source_endpoint(endpoint)
    if (not isinstance(pointers, list) or not pointers or any(not isinstance(p, str) for p in pointers)
            or len(set(pointers)) != len(pointers)):
        raise InvalidGenerationProtocol('required source pointers must be nonempty and unique')
    for pointer in pointers:
        _pointer(source, pointer)
    adaptive = evidence_catalogue is not None
    if type(evidence_round) is not int or evidence_round not in (0, 1) or evidence_round and not adaptive:
        raise InvalidGenerationProtocol('evidence round must be zero or one with a catalogue')
    output = deepcopy(_SOURCE_OUTPUT)
    extra = {}
    if adaptive:
        output.update(schema_version=_SOURCE_RESPONSE_ADAPTIVE, evidence_requests=[])
        extra = {'evidence_catalogue': _source_catalog(evidence_catalogue, endpoint), 'evidence_round': evidence_round}
        output['evidence_requests'] = [{'evidence_id': '<exact catalogue ID; omit requests if none needed>',
            'source_pointers': ['<source JSON pointer>'], 'entities': ['<exact catalogue entity>'],
            'channels': ['pose'], 'time_range_s': ['<start seconds>', '<end seconds>'],
            'sampling': '<source_grid | recorded>', 'reason': '<why this resolves a terminal condition>'}]
    return _seal({'schema_version': _SOURCE_REQUEST_ADAPTIVE if adaptive else _SOURCE_REQUEST, 'source': source, 'endpoint': endpoint,
        'required_source_pointers': pointers, 'model_profile': _profile(model_profile),
        'evidence': _evidence(evidence, endpoint, 'multimodal'), 'mode': 'multimodal',
        'rules': list(_SOURCE_RULES) + (_ADAPTIVE_RULES if adaptive else []), 'output_template': output, 'scope': _SCOPE, **extra})

def _prepared_source(request):
    request = _json(request)
    if not isinstance(request, dict):
        raise InvalidGenerationProtocol('source review request must be an object')
    version = request.get('schema_version')
    try:
        if version in (_SOURCE_REQUEST, _SOURCE_REQUEST_ADAPTIVE):
            expected = prepare_source_review(request['source'], request['endpoint'],
                required_source_pointers=request['required_source_pointers'],
                model_profile=request['model_profile'], evidence=request['evidence'],
                evidence_catalogue=request.get('evidence_catalogue'), evidence_round=request.get('evidence_round', 0))
        elif version in (_VERIFICATION_REQUEST, _VERIFICATION_REQUEST_ADAPTIVE):
            expected = prepare_source_verification(request['judgment_request'], request['judgment_response'],
                judgment_dispatch=request['judgment_dispatch'], model_profile=request['model_profile'])
        else:
            raise InvalidGenerationProtocol('unsupported source review request')
    except KeyError as error:
        raise InvalidGenerationProtocol('source request has missing fields') from error
    if request != expected:
        raise InvalidGenerationProtocol('source request differs from its frozen source, evidence or rules')
    return request

def _requirement_summary(rows):
    """Explain admitted candidate rows without promoting them to verified facts."""
    categories = {}
    for category in ('goal', 'asset_integrity', 'other', 'unclassified'):
        selected = [row for row in rows if row['scope'] == 'terminal'
                    and row.get('category', 'unclassified') == category]
        values = [row['value'] for row in selected]
        categories[category] = {
            'candidate_value': False if False in values else True if values and all(v is True for v in values) else None,
            'requirement_ids': [row['id'] for row in selected],
            'unknown_ids': [row['id'] for row in selected if row['value'] is None],
            'false_ids': [row['id'] for row in selected if row['value'] is False]}
    return {'schema_version': 'terminal-requirement-summary/0.1',
        'authority': 'candidate_checklist_not_independent_verification', 'terminal_categories': categories,
        'deferred': {scope: [row['id'] for row in rows if row['scope'] == scope]
                     for scope in ('initial', 'process', 'delivery', 'context')}}

def admit_source_review(request, response, *, dispatch):
    """Validate a candidate; only a separate verification can release a result.

    Protocol validation checks binding, citations, coverage and top-level
    conjunction. Requirement semantics, identity interpretation and physical
    sufficiency remain model claims and require independent verification.
    """
    request = _prepared_source(request)
    if request['schema_version'] not in (_SOURCE_REQUEST, _SOURCE_REQUEST_ADAPTIVE):
        raise InvalidGenerationProtocol('expected a source judgment request')
    response = _json(response)
    adaptive = request['schema_version'] == _SOURCE_REQUEST_ADAPTIVE
    _keys(response, ('schema_version', 'request_sha256', 'requirements', 'terminal', 'reason')
          + (('evidence_requests',) if adaptive else ()), 'source judgment')
    if response['schema_version'] != (_SOURCE_RESPONSE_ADAPTIVE if adaptive else _SOURCE_RESPONSE) or response['request_sha256'] != request['request_sha256']:
        raise InvalidGenerationProtocol('source judgment request/version mismatch')
    caller = _dispatch(dispatch, request, response)
    _text(response['reason'], 'terminal reason')
    if not isinstance(response['requirements'], list):
        raise InvalidGenerationProtocol('requirements must be a checklist')
    evidence = {item['id']: item for item in request['evidence']}
    ids, covered, values = set(), set(), []
    for row in response['requirements']:
        # Legacy rows omit both reporting fields; a partial report is malformed.
        reporting = ('judgment_basis', 'missing_structured_evidence')
        reporting = reporting if isinstance(row, dict) and any(field in row for field in reporting) else ()
        categorizing = ('category',) if isinstance(row, dict) and 'category' in row else ()
        _keys(row, ('id', 'source_pointers', 'scope', 'text', 'value', 'reason', 'evidence_ids') + reporting + categorizing, 'requirement row')
        for field in ('id', 'text', 'reason'):
            _text(row[field], 'requirement ' + field)
        if row['id'] in ids or row['scope'] not in ('terminal', 'initial', 'process', 'delivery', 'context'):
            raise InvalidGenerationProtocol('duplicate requirement or unknown scope')
        if categorizing and ((row['scope'] == 'terminal' and row['category'] not in ('goal', 'asset_integrity', 'other'))
                             or (row['scope'] != 'terminal' and row['category'] is not None)):
            raise InvalidGenerationProtocol('invalid requirement category for scope')
        ids.add(row['id'])
        pointers = row['source_pointers']
        if (not isinstance(pointers, list) or not pointers or any(not isinstance(p, str) for p in pointers)
                or len(set(pointers)) != len(pointers)):
            raise InvalidGenerationProtocol('requirement needs unique source pointers')
        for pointer in pointers:
            _pointer(request['source'], pointer)
        covered.update(pointers)
        if type(row['value']) not in (bool, type(None)) or row['scope'] != 'terminal' and row['value'] is not None:
            raise InvalidGenerationProtocol('only terminal rows can have boolean values')
        if reporting:
            basis, missing = row['judgment_basis'], row['missing_structured_evidence']
            if (row['scope'] == 'terminal' and (not isinstance(basis, str)
                    or basis not in ('structured', 'visual_inference', 'mixed', 'unresolved'))
                    or row['scope'] != 'terminal' and basis is not None
                    or row['value'] is not None and basis == 'unresolved'):
                raise InvalidGenerationProtocol('invalid judgment basis for requirement scope/value')
            if (not isinstance(missing, list)
                    or any(not isinstance(item, str) or not item.strip() for item in missing)
                    or len(set(missing)) != len(missing)):
                raise InvalidGenerationProtocol('missing structured evidence must be unique nonempty descriptions')
        cited = _citations(row['evidence_ids'], evidence, required=row['value'] is not None)
        if row['value'] is not None:
            if not request['endpoint']['valid']:
                raise InvalidGenerationProtocol('determinate judgment needs a verified actual endpoint')
            if not _source_observation(cited, evidence, request['endpoint']):
                raise InvalidGenerationProtocol('determinate judgment must cite native endpoint observations, not only auxiliary measurements or context')
            if reporting:
                images = [identity for identity in cited if evidence[identity]['kind'] in _PHYSICAL['visual']]
                if basis in ('visual_inference', 'mixed') and not _source_observation(images, evidence, request['endpoint']):
                    raise InvalidGenerationProtocol('visual judgment basis must cite aligned actual-endpoint images')
                kinds = {'raw_state', 'native_contact'} if basis == 'structured' else _PHYSICAL['structured']
                if basis in ('structured', 'mixed') and not any(evidence[identity]['kind'] in kinds for identity in cited):
                    raise InvalidGenerationProtocol('structured or mixed judgment basis lacks corresponding observations')
        if row['scope'] == 'terminal':
            values.append(row['value'])
    # A required source field can be located more precisely by a descendant.
    # This is structural coverage only; semantic completeness is independently reviewed.
    if any(not any(pointer == required or pointer.startswith(required + '/') for pointer in covered)
           for required in request['required_source_pointers']):
        raise InvalidGenerationProtocol('source judgment omitted required source coverage')
    terminal = False if False in values else True if values and all(value is True for value in values) else None
    if type(response['terminal']) not in (bool, type(None)) or response['terminal'] is not terminal:
        raise InvalidGenerationProtocol('terminal value disagrees with the necessary requirement rows')
    queries = _data_requests(request, response) if adaptive else None
    return {'protocol_status': 'valid', 'candidate_terminal': terminal, 'terminal': None,
        'reason': 'independent_review_required', 'requirements': deepcopy(response['requirements']),
        'requirement_summary': _requirement_summary(response['requirements']),
        'dispatch': caller, 'request_sha256': request['request_sha256'], 'response_sha256': _digest(response),
        'endpoint': deepcopy(request['endpoint']), 'process': 'not_evaluated', 'task_success': None, 'scope': _SCOPE,
        **({'evidence_requests': queries} if adaptive else {})}

def prepare_source_verification(judgment_request, judgment_response, *, judgment_dispatch, model_profile,
                                review_unknown=True):
    """Prepare independent review, or None for a valid null when explicitly skipped.

    The default preserves explicit/legacy diagnostic review. Normal paired runs
    pass review_unknown=False; invalid candidates still raise before any skip.
    """
    if type(review_unknown) is not bool:
        raise InvalidGenerationProtocol('review_unknown must be boolean')
    candidate = admit_source_review(judgment_request, judgment_response, dispatch=judgment_dispatch)
    profile = _profile(model_profile)
    if candidate['candidate_terminal'] is None and not review_unknown:
        return None
    request = _json(judgment_request)
    adaptive = request['schema_version'] == _SOURCE_REQUEST_ADAPTIVE
    output = deepcopy(_VERIFICATION_OUTPUT)
    if adaptive:
        output['schema_version'] = _VERIFICATION_RESPONSE_ADAPTIVE
    return _seal({'schema_version': _VERIFICATION_REQUEST_ADAPTIVE if adaptive else _VERIFICATION_REQUEST,
        'source': request['source'], 'endpoint': request['endpoint'], 'evidence': request['evidence'],
        'mode': 'multimodal', 'judgment_request': request, 'judgment_response': _json(judgment_response),
        'judgment_dispatch': candidate['dispatch'], 'model_profile': profile,
        'rules': list(_VERIFICATION_RULES) + (_ADAPTIVE_RULES[:2] if adaptive else []), 'output_template': output, 'scope': _SCOPE})

def admit_source_verification(request, response, *, dispatch):
    """Release the candidate only on independent confirmation; keep disputes unknown."""
    request = _prepared_source(request)
    if request['schema_version'] not in (_VERIFICATION_REQUEST, _VERIFICATION_REQUEST_ADAPTIVE):
        raise InvalidGenerationProtocol('expected a source verification request')
    response = _json(response)
    _keys(response, ('schema_version', 'request_sha256', 'status', 'reason', 'evidence_ids'), 'source verification')
    expected_version = (_VERIFICATION_RESPONSE_ADAPTIVE if request['schema_version'] == _VERIFICATION_REQUEST_ADAPTIVE else _VERIFICATION_RESPONSE)
    if (response['schema_version'] != expected_version or response['request_sha256'] != request['request_sha256']
            or response['status'] not in ('confirmed', 'disputed', 'unresolved')):
        raise InvalidGenerationProtocol('source verification has invalid binding or status')
    _text(response['reason'], 'independent review reason')
    evidence = {item['id']: item for item in request['evidence']}
    candidate = admit_source_review(request['judgment_request'], request['judgment_response'],
                                    dispatch=request['judgment_dispatch'])
    confirming = response['status'] == 'confirmed' and candidate['candidate_terminal'] is not None
    cited = _citations(response['evidence_ids'], evidence, required=confirming)
    if confirming and not _source_observation(cited, evidence, request['endpoint']):
        raise InvalidGenerationProtocol('confirmation must cite native endpoint observations')
    reviewer = _dispatch(dispatch, request, response)
    judgment = request['judgment_dispatch']
    if reviewer['context_id'] == judgment['context_id'] or reviewer['dispatch_id'] == judgment['dispatch_id']:
        raise InvalidGenerationProtocol('source verification requires independent dispatch and context')
    return {**candidate, 'terminal': candidate['candidate_terminal'] if response['status'] == 'confirmed' else None,
        'reason': response['reason'], 'review_status': response['status'], 'judgment_dispatch': judgment,
        'dispatch': reviewer, 'request_sha256': request['request_sha256'], 'response_sha256': _digest(response)}

def _citations(value, evidence, *, required=False):
    if (not isinstance(value, list) or any(not isinstance(item, str) for item in value)
            or len(set(value)) != len(value) or any(item not in evidence for item in value)
            or required and not value):
        raise InvalidGenerationProtocol("citations must use unique IDs from the closed evidence list")
    return value
