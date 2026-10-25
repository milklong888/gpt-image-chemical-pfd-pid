"""True source-producer/consumer roundtrip; original synthetic ZIP, no PDF/OCR/model/CAD."""
from pathlib import Path
import tempfile,zipfile,subprocess,sys,os,json,shutil,hashlib
sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[1];checks=[];steps=[]
with tempfile.TemporaryDirectory(prefix='zip-roundtrip-',dir=Path(__file__).parent)as tmp:
 root=Path(tmp)/'data';root.mkdir();archive=Path(tmp)/'original-synthetic.zip'
 with zipfile.ZipFile(archive,'w')as z:
  z.writestr('PFD pump.txt','Original synthetic unit-test note DEMO-P202-1. No engineering values.')
  z.writestr('alias/PFD pump.txt','Original synthetic unit-test note DEMO-P202-1. No engineering values.')
  z.writestr('unlabeled.dat',b'original synthetic unclassified fixture')
 zip_before=hashlib.sha256(archive.read_bytes()).hexdigest();env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',CHEM_KNOWLEDGE_DATA=str(root),CHEM_KNOWLEDGE_ASSETS=str(BASE/'assets'))
 def run(label,script,*args):
  p=subprocess.run([sys.executable,'-X','utf8',str(BASE/script),*map(str,args)],capture_output=True,text=True,encoding='utf-8',env=env)
  stdout=p.stdout.strip();stderr=p.stderr.strip()
  try:
   summary=json.loads(stdout)
   if 'out'in summary:summary['out']='<synthetic-registry>'
   stdout=json.dumps(summary,ensure_ascii=False)
  except ValueError:pass
  for prefix in [str(Path(sys.prefix)),str(Path(sys.prefix)).replace('\\','/'),str(Path(sys.executable).parent)]:
   stderr=stderr.replace(prefix,'<test-python-environment>')
  steps.append({'step':label,'script':script,'returncode':p.returncode,'stdout':stdout,'stderr':stderr})
  assert p.returncode==0,(label,p.stdout,p.stderr)
 run('ingest actual ZIP','engine/registry/ingest_archives.py','--archives',archive,'--out',root/'registry')
 run('classify actual registry','engine/registry/classify_sources.py','--out',root/'registry')
 registry=json.loads((root/'registry/sources.json').read_text('utf-8'));classified=json.loads((root/'registry/source-classification.json').read_text('utf-8'));rows=classified['sources'];assert len(registry['sources'])==2 and len(rows)==2
 known=next(x for x in rows if any('PFD pump' in a for a in x['aliases']));unknown=next(x for x in rows if x is not known)
 assert all('classification_candidates'in x and 'module_candidates'in x for x in rows);assert 'pfd'in {v['category']for v in known['classification_candidates']};assert 'pump_compressor'in {v['module']for v in known['module_candidates']};assert unknown['classification_candidates']==[{'category':'unknown','keywords':[]}]and unknown['module_candidates']==[];assert classified['approval']=='candidate only; not validated or mandatory';checks.append('Actual classifier canonical producer fields and candidate approval semantics preserved')
 assert sum(len(x['original_aliases'])for x in registry['sources'])==3;checks.append('Three ZIP members deduplicate to two immutable content sources, aliases retained')
 def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v),encoding='utf-8')
 write(root/'review/version-evidence.json',{'standards':[],'web_evidence':[]});write(root/'curated/requirements.json',[]);(root/'schema').mkdir();shutil.copy2(BASE/'schema/drawing_knowledge.linkml.yaml',root/'schema/drawing_knowledge.linkml.yaml')
 run('assemble actual produced classification','engine/knowledge.py','--data',root,'assemble')
 run('validate actual assembly LinkML','engine/knowledge.py','--data',root,'validate')
 kb=json.loads((root/'corpus/knowledge.json').read_text('utf-8'));byid={n['id']:n for n in kb['nodes']};assert byid[known['source_id']]['modules']==['pump_compressor'];assert byid[unknown['source_id']]['modules']==[]and byid[unknown['source_id']]['drawing_kinds']==['unknown'];assert byid[unknown['source_id']]['status']=='unknown'and byid[known['source_id']]['valid_for_release']is False;checks.append('Unknown input remains unknown/no equipment module; no engineering category forced')
 assert hashlib.sha256(archive.read_bytes()).hexdigest()==zip_before
 for s in registry['sources']:assert hashlib.sha256(Path(s['path']).read_bytes()).hexdigest()==s['sha256']
 checks.append('Original ZIP and all retained source bytes unchanged through whole chain')
# Summaries are kept; original fixture files are removed by TemporaryDirectory.
report={'passed':True,'checks':checks,'steps':steps,'mocked_steps':0,'synthetic_ZIP_members':3,'unique_content_sources':2,'PDFs':0,'OCR_runs':0,'model_runs':0,'CAD_runs':0,'code_SHA256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [BASE/'engine/registry/ingest_archives.py',BASE/'engine/registry/classify_sources.py',BASE/'engine/knowledge.py']}};(BASE/'roundtrip-test-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print('PASS actual ZIP ingest -> classify -> assemble -> validate')
