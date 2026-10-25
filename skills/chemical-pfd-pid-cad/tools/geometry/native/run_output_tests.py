"""Compile/run the exact output helper without any CAD references or startup."""
from pathlib import Path
import argparse,subprocess,json,hashlib,re,datetime
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
O=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--csc',type=Path,required=True);p.add_argument('--dotnet',type=Path,required=True);p.add_argument('--references-from-rsp',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert not a.out.exists();a.out.mkdir(parents=True)
refs=[line for line in a.references_from_rsp.read_text('utf8').splitlines() if line.startswith('/reference:')]
assert refs and all('Microsoft.NETCore.App' in line and not any(x in line.lower() for x in ('autocad','acdbmgd','accoremgd','acmgd')) for line in refs)
dll=a.out.resolve()/'OwnedNativeAuditOutputTest.dll'
sources=[O/x for x in ('OwnedNativeAuditOutputTest.cs','OwnedNativeAuditOutput.cs','NativeWriteGuard.cs')]
rsp=a.out/'compile.rsp';rsp.write_text('\n'.join(['/nologo','/nostdlib+','/target:exe','/codepage:65001','/utf8output','/out:"'+str(dll)+'"']+refs+['"'+str(x)+'"' for x in sources]),'utf8')
compile=subprocess.run([str(a.csc),'/noconfig','@'+str(rsp.resolve())],capture_output=True,encoding='utf8',errors='replace');(a.out/'compiler.log').write_text(compile.stdout+compile.stderr,'utf8')
report={'compiled':compile.returncode==0,'compiler_returncode':compile.returncode,'sources':{x.name:sha(x) for x in sources},'CAD_references':0,'cad_executed':False,'native_AutoCAD_command_executed':False,'platform':'Windows/.NET8; exclusive CreateDirectoryW used, no Autodesk dependency'}
if compile.returncode==0:
 dll.with_suffix('.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net8.0','framework':{'name':'Microsoft.NETCore.App','version':'8.0.0'},'rollForward':'LatestPatch'}}),'utf8')
 test=subprocess.run([str(a.dotnet),str(dll),str((a.out/'fixtures').resolve())],capture_output=True,encoding='utf8',errors='replace');(a.out/'tests.log').write_text(test.stdout+test.stderr,'utf8')
 cases=re.findall(r'^PASS (.+)$',test.stdout,re.M)
 report.update(test_returncode=test.returncode,passed_cases=cases,actual_case_count=len(cases),passed=test.returncode==0 and 'OWNED_NATIVE_OUTPUT_PASS=13' in test.stdout and len(cases)==13,dll_sha256=sha(dll))
else:report['passed']=False
(a.out/'test-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(0 if report['passed'] else 1)
