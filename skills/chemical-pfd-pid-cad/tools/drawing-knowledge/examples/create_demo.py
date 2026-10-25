"""Create a tiny ORIGINAL SYNTHETIC source-bound demo; not engineering data."""
from pathlib import Path
import json,hashlib,shutil,argparse
BASE=Path(__file__).resolve().parent.parent
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def create(root):
    root=Path(root).resolve()
    if root.exists():raise ValueError('DEMO_OUTPUT_EXISTS')
    root.mkdir(parents=True)
    source=root/'registry/originals/synthetic.txt';source.parent.mkdir(parents=True);source.write_text('ORIGINAL SYNTHETIC TEST ONLY. DEMO-V101-1 is an invented identifier. No equipment values or design claims.',encoding='utf-8')
    h=hashlib.sha256(source.read_bytes()).hexdigest();sid='src-'+h[:16]
    write(root/'registry/sources.json',{'sources':[{'source_id':sid,'sha256':h,'path':str(source),'extension':'.txt','original_aliases':[{'zip_path':'synthetic-only.zip','member_name':'synthetic.txt'}],'pdf_page_count':None}]})
    write(root/'registry/source-classification.json',{'sources':[{'source_id':sid,'module_candidates':[{'module':'common'}],'classification_candidates':[]}]})
    write(root/'review/version-evidence.json',{'standards':[],'web_evidence':[]})
    write(root/'curated/requirements.json',[{'id':'policy:synthetic-review','kind':'Requirement','label':'Synthetic review-only demonstration','status':'workflow_policy','valid_for_release':False,'text':'This synthetic example demonstrates evidence binding; it provides no engineering requirements.','modules':['common'],'drawing_kinds':['pfd'],'evidence_ids':[sid]}])
    write(root/'review/additional-content/manifest.json',{'records':[{'source_id':sid,'source_sha256':h,'payload_path':str(source),'payload_sha256':h,'status':'extracted_candidate','text':source.read_text('utf-8'),'label':'Synthetic test observation','method':'Original authored plain-text fixture','modules':['common'],'drawing_kinds':['pfd'],'locator':{'type':'synthetic_document'}}]})
    (root/'schema').mkdir();shutil.copy2(BASE/'schema/drawing_knowledge.linkml.yaml',root/'schema/drawing_knowledge.linkml.yaml')
    # This stub is for no-model gate tests ONLY, never a usable embedding config.
    write(root/'models/model.json',{'repo':'SYNTHETIC-NO-MODEL-TEST-STUB','local_path':'models/NOT-A-MODEL','files':{},'dimension':0,'query_instruction':''})
    return {'root':root,'source_path':source,'source_id':sid,'source_sha256':h}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();v=create(a.out);print('Created synthetic demo; no index/model or engineering data.')
