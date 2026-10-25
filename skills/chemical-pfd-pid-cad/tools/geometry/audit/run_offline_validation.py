"""Run public synthetic tests; optional router uses an explicit local runtime.

Never calls a model, AutoCAD, semantic index or network installer.
"""
from pathlib import Path
import argparse,subprocess,sys,os,json,re,importlib.metadata,hashlib

def main():
    root=Path(__file__).resolve().parents[1]
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--runtime',type=Path);ap.add_argument('--node',type=Path);ap.add_argument('--out',type=Path,default=root/'validation-output');args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True);env=os.environ.copy();env.update(PYTHONPATH=str(root/'python'),PYTHONDONTWRITEBYTECODE='1')
    env.pop('PFD_TEST_RUNTIME',None)
    if args.runtime:env['PFD_TEST_RUNTIME']=str(args.runtime.resolve())
    if args.node:env['PFD_NODE']=str(args.node.resolve())
    command=[sys.executable,'-X','utf8','-m','unittest','discover','-s',str(root/'tests'),'-v']
    process=subprocess.run(command,capture_output=True,encoding='utf8',env=env);log=process.stdout+process.stderr;(args.out/'unittest.log').write_text(log,'utf8')
    count=re.search(r'Ran (\d+) tests?',log);skips=len(re.findall(r'\.\.\. skipped ',log))
    report={'passed':process.returncode==0,'tests_discovered':int(count.group(1)) if count else None,'skipped':skips,'python':sys.version.split()[0],'dependencies':{n:importlib.metadata.version(n) for n in ('shapely','ezdxf')},'real_optional_libavoid_invoked':bool(args.runtime),'runtime_adapter_sha256':hashlib.sha256((args.runtime/'route.mjs').read_bytes()).hexdigest() if args.runtime else None,'candidate_adapter_sha256':hashlib.sha256((root/'python/pfd_runtime/route.mjs').read_bytes()).hexdigest(),'cad_executed':False,'model_or_semantic_query_executed':False,'network_installer_executed':False,'fresh_dependency_install_tested':False}
    (args.out/'validation-result.json').write_text(json.dumps(report,indent=2),'utf8');print(json.dumps(report,indent=2))
    if process.returncode:print(log)
    return process.returncode

if __name__=='__main__':raise SystemExit(main())
