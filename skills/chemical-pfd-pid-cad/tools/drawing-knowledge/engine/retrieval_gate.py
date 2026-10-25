"""Fail before CAD output if the knowledge receipt is absent, stale, or for another scope."""
from pathlib import Path
import hashlib,json,uuid
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def check_literal_engine(retrieval,knowledge_path):
    """Bind helper bytes without importing retrieval/framework/model code."""
    helper=Path(knowledge_path).with_name('literal_candidates.py')
    expected=retrieval.get('literal_engine_sha256')
    if not expected:raise ValueError('LITERAL_ENGINE_HASH_REQUIRED')
    if not helper.is_file() or expected!=sha(helper):raise ValueError('LITERAL_ENGINE_CHANGED')

def check_receipt(receipt_path, data_root, drawing, required_modules=(), topics=None):
    path=Path(receipt_path) if receipt_path else None
    if path is None or not path.is_file():raise ValueError('RETRIEVAL_REQUIRED: create a source-bound knowledge packet before generating CAD.')
    packet=json.loads(path.read_text('utf8'));actual=packet.pop('receipt_sha256',None)
    if actual!=digest(packet):raise ValueError('RECEIPT_CHANGED: receipt contents no longer match their digest.')
    packet['receipt_sha256']=actual
    execution_id=packet.get('execution_id')
    try:
        execution_uuid=uuid.UUID(execution_id) if isinstance(execution_id,str) else None
        if execution_uuid is None or execution_uuid.version!=4 or str(execution_uuid)!=execution_id:raise ValueError()
    except (ValueError,AttributeError):raise ValueError('PACKET_EXECUTION_ID_REQUIRED: reissue the knowledge packet with a valid UUID4 execution_id.') from None
    if packet.get('drawing_kind')!=drawing:raise ValueError('DRAWING_KIND_MISMATCH')
    from drafting_topics import verify_drafting_lookup
    verify_drafting_lookup(packet.get('drafting_lookup'),packet.get('question'),drawing,topics)
    data=Path(data_root);manifest=json.loads((data/'indexes/current.json').read_text('utf8'))
    import knowledge
    from knowledge import check_generation,document_context,module_source_context,expand_modules
    check_generation(data)
    if packet.get('corpus_sha256')!=manifest['corpus_sha256'] or manifest['corpus_sha256']!=sha(data/'corpus/knowledge.json'):raise ValueError('STALE_KNOWLEDGE_RECEIPT')
    retrieval=packet.get('retrieval',{})
    if retrieval.get('query_engine_sha256')!=sha(knowledge.__file__):raise ValueError('RETRIEVAL_ENGINE_CHANGED')
    check_literal_engine(retrieval,knowledge.__file__)
    if packet.get('question')!=retrieval.get('question') or packet.get('corpus_sha256')!=retrieval.get('corpus_sha256'):raise ValueError('RETRIEVAL_SCOPE_MISMATCH')
    audit_path=data/'evaluations/retrieval-calls.jsonl'
    execution_digest=digest(retrieval)
    executed=False
    if audit_path.is_file():
        for line in audit_path.read_text('utf8').splitlines():
            row=json.loads(line)
            if row.get('result_sha256')==execution_digest and row.get('question')==retrieval.get('question') and row.get('corpus_sha256')==manifest['corpus_sha256']:executed=True;break
    if not executed:raise ValueError('NO_RETRIEVAL_EXECUTION_RECORD')
    dependencies={'source_registry_sha256':data/'registry/sources.json','schema_sha256':data/'schema/drawing_knowledge.linkml.yaml','curated_sha256':data/'curated/requirements.json','version_evidence_sha256':data/'review/version-evidence.json','catalog_sha256':knowledge.SKILL/'tools/equipment-knowledge/catalog.json'}
    for key,dependency in dependencies.items():
        if not dependency.is_file() or manifest.get(key)!=sha(dependency):raise ValueError('STALE_KNOWLEDGE_DEPENDENCY: '+key)
    if not set(required_modules)<=set(packet.get('loaded_modules',[])):raise ValueError('MISSING_RELEVANT_MODULES')
    if not packet.get('requirements') or not packet.get('retrieval',{}).get('results'):raise ValueError('EMPTY_RETRIEVAL_RECEIPT')
    kb=json.loads((data/'corpus/knowledge.json').read_text('utf8'));lookup={n['id']:n for n in kb['nodes']}
    modules=expand_modules(drawing,packet.get('requested_equipment',[]),packet.get('stated_components',[]))
    if sorted(modules)!=packet.get('loaded_modules'):raise ValueError('FALSE_MODULE_SCOPE')
    cards=[n for n in kb['nodes'] if n['kind']=='Requirement' and set(n.get('modules',[]))&modules and (not n.get('drawing_kinds') or drawing in n['drawing_kinds'])]
    cases=[n for n in kb['nodes'] if n['kind']=='CasePattern' and n['status']=='reviewed_case' and set(n.get('modules',[]))&modules and (not n.get('drawing_kinds') or drawing in n['drawing_kinds'])]
    expected={'requirements':[n for n in cards if n['status']=='workflow_policy'],'historical_requirements_pending_adoption':[n for n in cards if n['status']!='workflow_policy'],'case_patterns':cases}
    expected['pinned_evidence']=[lookup[e] for e in sorted({e for n in cards+cases for e in n.get('evidence_ids',[])})]
    module_context=module_source_context(kb,cards,cases,expected['pinned_evidence'])
    for group,rows in module_context.items():
        if packet.get(group)!=rows:raise ValueError('INCOMPLETE_OR_UNBOUND_MODULE_CONTEXT: '+group)
    for group,rows in expected.items():
        actual_rows=packet.get(group,[])
        if len(actual_rows)!=len({r['id'] for r in actual_rows}) or {r['id'] for r in actual_rows}!={r['id'] for r in rows}:raise ValueError('INCOMPLETE_OR_DUPLICATE_MODULE_CARDS: '+group)
    if packet.get('engineering_release_eligible') is not False or packet.get('imagegen_allowed_for_review') is not True:raise ValueError('INVALID_REVIEW_STATUS')
    for group in ['requirements','historical_requirements_pending_adoption','case_patterns','pinned_evidence']:
        for row in packet.get(group,[]):
            if row.get('id') not in lookup or row!=lookup[row['id']]:raise ValueError('UNBOUND_KNOWLEDGE_CARD: '+str(row.get('id')))
    for row in packet['retrieval']['results']:
        item={k:v for k,v in row.items() if k!='score'}
        if item.get('id') not in lookup or item!=lookup[item['id']]:raise ValueError('UNBOUND_RETRIEVAL_RESULT')
    hits=packet['retrieval']['results']
    if len(hits)!=len({r['id'] for r in hits}):raise ValueError('DUPLICATE_RETRIEVAL_RESULT')
    context=[lookup[e] for e in sorted({e for n in hits for e in n.get('evidence_ids',[])})]
    if packet['retrieval'].get('context_evidence')!=context:raise ValueError('UNBOUND_CONTEXT_EVIDENCE')
    if packet['retrieval'].get('document_context')!=document_context(kb,hits,context):raise ValueError('UNBOUND_DOCUMENT_CONTEXT')
    for group in ['source_page_context','version_context']:
        for row in retrieval.get(group,[]):
            if row.get('id') not in lookup or row!=lookup[row['id']]:raise ValueError('UNBOUND_'+group.upper())
    rels={(r['subject'],r['predicate'],r['object'],r['status']) for r in kb['relations']}
    if any((r['subject'],r['predicate'],r['object'],r['status']) not in rels for r in packet['retrieval'].get('graph_context',[])):raise ValueError('UNBOUND_GRAPH_CONTEXT')
    for e in packet.get('pinned_evidence',[])+hits+context+retrieval['document_context']+retrieval.get('source_page_context',[])+retrieval.get('version_context',[])+[n for rows in module_context.values() for n in rows]:
        if e.get('source_path'):
            p=Path(e['source_path'])
            if not p.is_file() or sha(p)!=e.get('source_sha256'):raise ValueError('SOURCE_CHANGED: '+e.get('id',''))
    packet_audit=data/'evaluations/packet-calls.jsonl'
    expected_execution=knowledge.packet_execution_record(packet)
    packet_executed=False
    if packet_audit.is_file():
        try:
            for line in packet_audit.read_text('utf8').splitlines():
                if line.strip() and json.loads(line)==expected_execution:packet_executed=True;break
        except (ValueError,UnicodeError):raise ValueError('INVALID_PACKET_EXECUTION_LOG: reissue the knowledge packet.') from None
    if not packet_executed:raise ValueError('NO_PACKET_EXECUTION_RECORD: reissue the knowledge packet; recomputing a receipt digest cannot replace packet generation.')
    return {'ok':True,'receipt_path':str(path.resolve()),'receipt_sha256':sha(path),'corpus_sha256':manifest['corpus_sha256'],'drawing_kind':drawing,'loaded_modules':packet['loaded_modules'],'engineering_release_eligible':False}
