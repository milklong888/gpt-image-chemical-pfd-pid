"""Literal engineering-ID candidate preservation; no model, approval or index writes."""
import re
from llama_index.core.schema import NodeWithScore
_ID=re.compile(r'(?<![A-Za-z0-9_./-])[A-Za-z0-9]+(?:[-_./][A-Za-z0-9]+)*(?![A-Za-z0-9_./-])')
def identifiers(question):
    return sorted({m.group(0).casefold() for m in _ID.finditer(question) if re.search(r'[A-Za-z]',m.group(0)) and re.search(r'[0-9]',m.group(0))})
def preserve_literals(question,hits,lookup,docstore,source_id=None,standard=None,limit=10):
    terms=identifiers(question)
    info={'identifiers':terms,'matched_nodes':0,'literal_nodes_outside_limit':0,'applied':False,'scope':'Indexed canonical content only; source/standard hard filters; original evidence remains unreviewed.'}
    if not terms:return hits,{},info
    patterns={t:re.compile(r'(?<![A-Za-z0-9_./-])'+re.escape(t)+r'(?![A-Za-z0-9_./-])',re.I) for t in terms}
    matches={};literal=[];old={h.node.node_id:h for h in hits}
    excluded={'Source','StandardVersion','Module','DrawingKind','Port','Check'}
    for nid,n in lookup.items():
        if n.get('kind') in excluded or not n.get('text') or nid==n.get('source_id'):continue
        if source_id and n.get('source_id')!=source_id:continue
        if standard and n.get('standard_id')!=standard:continue
        matched=[t for t,p in patterns.items() if p.search(n['text'])]
        if not matched or not docstore.document_exists(nid):continue
        canonical=docstore.get_node(nid)
        matched=[t for t in matched if patterns[t].search(canonical.text)]
        if not matched:continue
        matches[nid]={'identifiers':matched,'match_count':len(matched),'basis':'Full engineering identifier with ASCII identifier boundaries in original content and indexed canonical text; label/source registration excluded.','original_status':n.get('status'),'engineering_approval':False}
        literal.append(old.get(nid) or NodeWithScore(node=canonical,score=0.0))
    literal.sort(key=lambda h:(-matches[h.node.node_id]['match_count'],h.node.node_id))
    ordered=[];seen=set()
    for h in literal+hits:
        if h.node.node_id not in seen:ordered.append(h);seen.add(h.node.node_id)
    info.update(matched_nodes=len(literal),literal_nodes_outside_limit=max(0,len(literal)-limit),applied=bool(literal),ranking='Distinct full identifiers matched descending, then canonical node_id ascending; hybrid order retained after literal candidates; original limit unchanged.')
    return ordered,matches,info
