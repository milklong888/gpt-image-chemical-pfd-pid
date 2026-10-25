from pathlib import Path
import sys,tempfile,os,json,copy,hashlib,ast,importlib.util
sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(BASE/'engine'),str(BASE/'examples')]
from create_demo import create
results=[]
def reject(fn,contains):
 try:fn()
 except (ValueError,AssertionError)as e:
  assert contains in str(e),(contains,str(e));return
 raise AssertionError('Expected refusal: '+contains)
with tempfile.TemporaryDirectory(prefix='synthetic-',dir=Path(__file__).parent)as tmp:
 demo=create(Path(tmp)/'data');root=demo['root'];os.environ['CHEM_KNOWLEDGE_DATA']=str(root)
 import knowledge as k,source_context as sc,retrieval_gate as gate
 from additional_content import manifest_sha
 kb=k.assemble(root);k.validate_schema(root);lookup={n['id']:n for n in kb['nodes']};content=next(n for n in kb['nodes']if n['id'].startswith('additional:'))
 manifest={'generation':str(root/'indexes/synthetic-gate-test-NOT-A-REAL-INDEX'),'corpus_sha256':k.sha(root/'corpus/knowledge.json'),'source_registry_sha256':k.sha(root/'registry/sources.json'),'schema_sha256':k.sha(root/'schema/drawing_knowledge.linkml.yaml'),'curated_sha256':k.sha(root/'curated/requirements.json'),'version_evidence_sha256':k.sha(root/'review/version-evidence.json'),'catalog_sha256':k.sha(k.SKILL/'tools/equipment-knowledge/catalog.json'),'additional_content_sha256':manifest_sha(root),'support_review_sha256':None,'model':k.model_config(root),'synthetic_test_only':True};k.write(root/'indexes/current.json',manifest)
 original=k.read(root/'registry/sources.json')['sources'][0];sc.source_identity(original);saved=demo['source_path'].read_bytes();demo['source_path'].write_bytes(saved+b' altered');reject(lambda:sc.source_identity(original),'SOURCE_CHANGED');demo['source_path'].write_bytes(saved);results.append('Original synthetic source SHA tamper rejected')
 def emit_query(mutate=False):
  def fake_query(data,question,*args,**kwargs):
   row=dict(content,score=0.0)
   if mutate:row['text']='forged replacement'
   r={'question':question,'filters':{'source_id':None,'standard_id':None},'results':[row],'context_evidence':[lookup[demo['source_id']]],'document_context':[],'source_page_context':[],'version_context':[],'graph_context':[],'index_generation':manifest['generation'],'corpus_sha256':manifest['corpus_sha256'],'query_engine_sha256':k.sha(k.__file__),'literal_engine_sha256':k.sha(BASE/'engine/literal_candidates.py'),'literal_match_channel':{'matches':{}},'synthetic_test_only':True}
   (root/'evaluations').mkdir(exist_ok=True)
   with(root/'evaluations/retrieval-calls.jsonl').open('a',encoding='utf-8')as f:f.write(json.dumps({'result_sha256':k.digest(r),'question':question,'corpus_sha256':manifest['corpus_sha256']})+'\n')
   return r
  k.query=fake_query
  return k.packet(root,'DEMO-V101-1 synthetic test','pfd',[],[])
 packet=emit_query();path=root/'packet.json';k.write(path,packet);proof=gate.check_receipt(path,root,'pfd',{'common'});assert proof['ok'];results.append('Actual receipt gate accepts synthetic bound packet; retrieval mocked, no index/model')
 altered=copy.deepcopy(packet);altered['retrieval']['results'][0]['id']='forged-id';k.write(root/'tampered.json',altered);reject(lambda:gate.check_receipt(root/'tampered.json',root,'pfd',{'common'}),'RECEIPT_CHANGED');results.append('Packet result ID tamper rejected')
 forged=emit_query(True);k.write(root/'forged.json',forged);reject(lambda:gate.check_receipt(root/'forged.json',root,'pfd',{'common'}),'UNBOUND_RETRIEVAL_RESULT');results.append('Even synthetic re-digested/execution-recorded result content differs from corpus and is rejected')
 reject(lambda:gate.check_literal_engine({},BASE/'engine/knowledge.py'),'LITERAL_ENGINE_HASH_REQUIRED');reject(lambda:gate.check_literal_engine({'literal_engine_sha256':'0'*64},BASE/'engine/knowledge.py'),'LITERAL_ENGINE_CHANGED');results.append('Missing/changed literal helper hash rejected')
 from llama_index.core.schema import TextNode,NodeWithScore
 from llama_index.core.storage.docstore import SimpleDocumentStore
 from literal_candidates import preserve_literals
 store=SimpleDocumentStore();node=TextNode(id_=content['id'],text=content['text']);store.add_documents([node]);hits,matched,info=preserve_literals('DEMO-V101-1',[],lookup,store,demo['source_id']);assert hits and hits[0].node.node_id==content['id'];assert preserve_literals('DEMO-V101-10',[],lookup,store,demo['source_id'])[0]==[];assert preserve_literals('DEMO-V101-1',[],lookup,store,'different-source')[0]==[];results.append('Synthetic full identifier exact boundary/source filtering verified')
 from registry.ingest_archives import validate_member_path
 assert validate_member_path('../outside.txt')is not None;results.append('ZIP traversal refused by original ingest path checker')
for p in BASE.rglob('*.py'):ast.parse(p.read_text('utf-8-sig'))
report={'passed':True,'checks':results,'actual_semantic_queries':0,'actual_embedding_builds':0,'actual_CAD_runs':0,'docling_OCR_run':False,'scope':'Original synthetic data, real assembly/LinkML schema/gate/literal source checks; retrieval result generation mocked and explicitly synthetic. No production files read by tests.'};(BASE/'test-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
