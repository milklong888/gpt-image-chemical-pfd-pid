"""Explicit portable locations; never discover or load a user's private library."""
from pathlib import Path
import os,json
HERE=Path(__file__).resolve().parent
CONFIG=Path(os.environ.get('CHEM_KNOWLEDGE_CONFIG',HERE/'runtime.json'))
def configuration():
    return json.loads(CONFIG.read_text('utf-8')) if CONFIG.is_file() else {}
def location(key,environment,default):
    value=os.environ.get(environment,configuration().get(key,str(default)))
    p=Path(value).expanduser()
    return (p if p.is_absolute() else CONFIG.parent/p).resolve()
def data_root():return location('data_root','CHEM_KNOWLEDGE_DATA',HERE.parent/'data')
def asset_root():return location('asset_root','CHEM_KNOWLEDGE_ASSETS',HERE.parent/'assets')
