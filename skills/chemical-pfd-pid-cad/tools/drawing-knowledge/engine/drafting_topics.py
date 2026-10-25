"""Deterministic drafting lookup hints, never retrieval or compliance evidence."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
TOPICS_PATH = ROOT / 'drafting-topics.json'
DRAWING_KINDS = {'pfd', 'pid', 'equipment_condition', 'layout'}
MODULES = {'common', 'tower', 'heat_exchanger', 'reactor', 'vessel',
           'pump_compressor', 'piping', 'instrumentation'}
FIELDS = {'id', 'aliases', 'drawing_kinds', 'default_for', 'modules',
          'query_prompt', 'lookup_before', 'check_after', 'source_leads',
          'review_boundary'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _catalog():
    catalog = json.loads(TOPICS_PATH.read_text('utf8'))
    if catalog.get('schema') != 'drafting-topics/v1':
        raise ValueError('INVALID_DRAFTING_TOPICS_SCHEMA')
    rows = catalog.get('topics')
    if not isinstance(rows, list) or not rows:
        raise ValueError('INVALID_DRAFTING_TOPICS_CATALOG')
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError('INVALID_DRAFTING_TOPIC_FIELDS')
        if not isinstance(row['id'], str) or not row['id'] or row['id'] in ids:
            raise ValueError('DUPLICATE_OR_INVALID_DRAFTING_TOPIC')
        ids.add(row['id'])
        for field in ('aliases', 'drawing_kinds', 'default_for', 'modules',
                      'lookup_before', 'check_after'):
            if not isinstance(row[field], list) or any(not isinstance(x, str) or not x for x in row[field]):
                raise ValueError('INVALID_DRAFTING_TOPIC_LIST: ' + field)
        if not set(row['drawing_kinds']) <= DRAWING_KINDS or not set(row['default_for']) <= set(row['drawing_kinds']):
            raise ValueError('INVALID_DRAFTING_TOPIC_DRAWINGS')
        if not set(row['modules']) <= MODULES:
            raise ValueError('INVALID_DRAFTING_TOPIC_MODULES')
        for field in ('query_prompt', 'review_boundary'):
            if not isinstance(row[field], str) or not row[field]:
                raise ValueError('INVALID_DRAFTING_TOPIC_TEXT: ' + field)
        if not isinstance(row['source_leads'], list) or any(
            not isinstance(x, dict) or not x.get('locator') or not x.get('status')
            for x in row['source_leads']
        ):
            raise ValueError('INVALID_DRAFTING_SOURCE_LEADS')
    return catalog


def _alias_matches(question, alias):
    # ASCII word boundaries prevent "dimensionless"/"prereflux" matching.
    pattern = re.escape(alias.casefold())
    if alias[0].isascii() and alias[0].isalnum():
        pattern = r'(?<![a-z0-9_])' + pattern
    if alias[-1].isascii() and alias[-1].isalnum():
        pattern += r'(?![a-z0-9_])'
    return re.search(pattern, question.casefold()) is not None


def drafting_lookup(question, drawing, topics=None):
    """Select defaults plus literal aliases plus explicit IDs. No engineering inference.

    Modules are lookup guidance only and never change physical module scope.
    Unmatched text makes no completeness or non-applicability assertion.
    """
    if drawing not in DRAWING_KINDS:
        raise ValueError('UNKNOWN_DRAWING_KIND')
    if not isinstance(question, str):
        raise ValueError('INVALID_DRAFTING_QUESTION')
    if topics is None:
        topics = []
    if not isinstance(topics, (list, tuple)) or any(not isinstance(x, str) or not x for x in topics):
        raise ValueError('INVALID_EXPLICIT_DRAFTING_TOPICS')
    explicit = sorted(set(topics))
    catalog = _catalog()
    byid = {row['id']: row for row in catalog['topics']}
    unknown = set(explicit) - set(byid)
    if unknown:
        raise ValueError('UNKNOWN_DRAFTING_TOPICS: ' + ', '.join(sorted(unknown)))
    wrong = [topic for topic in explicit if drawing not in byid[topic]['drawing_kinds']]
    if wrong:
        raise ValueError('DRAFTING_TOPIC_DRAWING_MISMATCH: ' + ', '.join(wrong))
    selected = []
    for row in catalog['topics']:
        if drawing not in row['drawing_kinds']:
            continue
        aliases = sorted(alias for alias in row['aliases'] if _alias_matches(question, alias))
        reasons = []
        if drawing in row['default_for']:
            reasons.append('drawing_default')
        if aliases:
            reasons.append('question_alias')
        if row['id'] in explicit:
            reasons.append('explicit_topic')
        if reasons:
            selected.append(dict(row, selected_by=reasons, matched_aliases=aliases,
                                 needs_actual_query=True))
    return {
        'schema': 'drafting-lookup/v1',
        'catalog_schema': catalog['schema'],
        'question': question,
        'drawing_kind': drawing,
        'explicit_topics': explicit,
        'topics_sha256': sha(TOPICS_PATH),
        'helper_sha256': sha(__file__),
        'topics': sorted(selected, key=lambda row: row['id']),
        'needs_actual_query': True,
        'status': 'lookup_hints_only',
        'boundary': 'Candidate questions and source locators only. No actual query, source-body reading, project applicability, engineering-object addition, or standard-compliance approval is established. Unmatched aliases do not prove completeness.',
    }


def verify_drafting_lookup(lookup, question, drawing, topics=None):
    """Exact recomputation binds hints, explicit IDs, config and helper bytes.

    Existing receipts without this field must be reissued by packet.
    """
    if not isinstance(lookup, dict):
        raise ValueError('DRAFTING_LOOKUP_REQUIRED: reissue the knowledge packet.')
    if topics is not None:
        requested = drafting_lookup(question, drawing, topics)['explicit_topics']
        if lookup.get('explicit_topics') != requested:
            raise ValueError('DRAFTING_TOPIC_SCOPE_MISMATCH')
    expected = drafting_lookup(question, drawing, lookup.get('explicit_topics'))
    # JSON identity distinguishes true from 1 (Python object equality does not).
    if json.dumps(lookup, ensure_ascii=False, sort_keys=True) != json.dumps(expected, ensure_ascii=False, sort_keys=True):
        raise ValueError('DRAFTING_LOOKUP_CHANGED_OR_STALE: reissue the knowledge packet.')
    return expected
