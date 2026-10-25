"""Source-bound candidate content adapter; LlamaIndex/LinkML remain the backend."""
from pathlib import Path
import hashlib,json

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def manifest_path(root):return root/'review/additional-content/manifest.json'

def manifest_sha(root):
    p=manifest_path(root)
    if not p.exists():return None
    before=sha(p);data=json.loads(p.read_text('utf8'));expected_by_path={}
    for c in data['records']:
        payload=Path(c['payload_path']).resolve();expected=c['payload_sha256']
        if payload in expected_by_path and expected_by_path[payload]!=expected:
            raise ValueError('ADDITIONAL_PAYLOAD_SHA_CONFLICT: '+str(payload))
        expected_by_path[payload]=expected
    for payload,expected in expected_by_path.items():
        if sha(payload)!=expected:raise ValueError('ADDITIONAL_PAYLOAD_CHANGED: '+str(payload))
    if sha(p)!=before:raise ValueError('ADDITIONAL_MANIFEST_CHANGED_DURING_VERIFICATION')
    return before

def assemble_additional(root,byid,node,relation,module_matches):
    p=manifest_path(root)
    if not p.exists():return [],[]
    data=json.loads(p.read_text('utf8'));nodes=[];rels=[];verified={};seen=set()
    for c in data['records']:
        sid=c['source_id'];s=byid[sid]
        if c['source_sha256']!=s['sha256']:raise ValueError('ADDITIONAL_SOURCE_SHA_MISMATCH: '+sid)
        if c.get('status')!='extracted_candidate':raise ValueError('ADDITIONAL_CANDIDATE_STATUS_REQUIRED')
        payload=str(Path(c['payload_path']).resolve());expected=c['payload_sha256']
        if payload not in verified:verified[payload]=sha(payload)
        if verified[payload]!=expected:raise ValueError('ADDITIONAL_PAYLOAD_CHANGED: '+payload)
        pages=c.get('physical_pages',[])
        if pages and s['extension']!='.pdf':raise ValueError('NONPDF_PHYSICAL_PAGE_NOT_ALLOWED')
        if any(not isinstance(x,int) or x<1 or x>(s.get('pdf_page_count') or 0) for x in pages):raise ValueError('ADDITIONAL_PAGE_OUTSIDE_SOURCE')
        if not c.get('text','').strip():continue
        nid='additional:'+sid[4:]+':'+hashlib.sha256(json.dumps(c,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:20]
        if nid in seen:continue
        seen.add(nid)
        mods=sorted(set(c.get('modules',[])+module_matches(c['text']+' '+c['label'])))
        text='提取候选；不得直接采用为项目数值或标准。方法：'+c['method']+'\n位置：'+json.dumps(c.get('locator',{}),ensure_ascii=False)+'\n'+c['text']
        n=node(nid,'CasePattern',c['label'],source_id=sid,source_sha256=s['sha256'],source_path=s['path'],text=text,modules=mods,drawing_kinds=c.get('drawing_kinds',[]),payload_path=str(p),physical_pages=pages,evidence_ids=[sid])
        nodes.append(n);rels.append(relation(nid,'part_of',sid))
        for page in pages:rels.append(relation(nid,'part_of','page:'+sid+':'+str(page)))
        for m in mods:rels.append(relation(nid,'candidate_for','module:'+m))
    return nodes,rels
