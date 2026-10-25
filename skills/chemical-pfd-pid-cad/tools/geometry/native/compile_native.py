"""Compile optional source against caller-owned installed .NET/AutoCAD files.

This invokes only the compiler, never AutoCAD. No SDK/runtime binaries are copied.
"""
from pathlib import Path
import argparse,struct,subprocess,json,hashlib

def managed(path):
    try:
        data=path.read_bytes();pe=struct.unpack_from('<I',data,0x3c)[0]
        if data[pe:pe+4]!=b'PE\0\0':return False
        opt=pe+24;magic=struct.unpack_from('<H',data,opt)[0]
        directories=opt+(96 if magic==0x10b else 112 if magic==0x20b else 0)
        return bool(struct.unpack_from('<II',data,directories+14*8)[0])
    except (OSError,struct.error):return False

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('csc','runtime-dir','out'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--desktop-runtime-dir',type=Path);ap.add_argument('--autocad-dir',type=Path)
    ap.add_argument('--guard-only',action='store_true',help='Compile/run only the pure .NET path-guard tests; no AutoCAD references')
    ap.add_argument('--dotnet',type=Path)
    args=ap.parse_args();source=Path(__file__).resolve().parent;args.out.mkdir(parents=True,exist_ok=True)
    refs=[p.resolve() for p in args.runtime_dir.glob('*.dll') if p.name!='WindowsBase.dll' and managed(p)]
    if not args.guard_only:
        if not args.autocad_dir or not args.desktop_runtime_dir:ap.error('AutoCAD and Desktop runtime directories required for optional native audit compilation')
        refs.append((args.desktop_runtime_dir/'WindowsBase.dll').resolve())
        refs.extend((args.autocad_dir/name).resolve() for name in ('acdbmgd.dll','accoremgd.dll','acmgd.dll'))
    elif not args.dotnet:ap.error('--dotnet required to run pure guard tests')
    if not all(p.exists() for p in refs):raise SystemExit('Explicit dependency missing')
    names=('NativeWriteGuardTest.cs','NativeWriteGuard.cs') if args.guard_only else ('NativeAudit.cs','NativeWriteGuard.cs','OwnedNativeAuditOutput.cs')
    dll=args.out.resolve()/('NativeWriteGuardTest.dll' if args.guard_only else 'PortableNativeAudit.dll');rsp=args.out.resolve()/'compile.rsp'
    lines=['/nologo','/nostdlib+','/target:'+('exe' if args.guard_only else 'library'),'/codepage:65001','/utf8output','/out:"'+str(dll)+'"']
    lines+=['/reference:"'+str(p)+'"' for p in refs]
    lines+=['"'+str(source/name)+'"' for name in names]
    rsp.write_text('\n'.join(lines),'utf8')
    result=subprocess.run([str(args.csc),'/noconfig','@'+str(rsp)],capture_output=True,encoding='utf8',errors='replace')
    (args.out/'compiler.log').write_text(result.stdout+result.stderr,'utf8')
    report={'compiled':result.returncode==0,'compiler_exit_code':result.returncode,'cad_executed':False,'dependency_binaries_copied':False,'source_sha256':{name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in names},'dll_sha256':hashlib.sha256(dll.read_bytes()).hexdigest() if result.returncode==0 else None}
    if args.guard_only and result.returncode==0:
        dll.with_suffix('.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net8.0','framework':{'name':'Microsoft.NETCore.App','version':'8.0.0'},'rollForward':'LatestPatch'}}),'utf8')
        guard=subprocess.run([str(args.dotnet),str(dll)],capture_output=True,encoding='utf8',errors='replace')
        (args.out/'guard-tests.log').write_text(guard.stdout+guard.stderr,'utf8');report.update(pure_guard_exit_code=guard.returncode,pure_guard_pass='PURE_PATH_GUARD_PASS=7' in guard.stdout)
        if guard.returncode or not report['pure_guard_pass']:result.returncode=1
    (args.out/'compile-result.json').write_text(json.dumps(report,indent=2),'utf8');print(json.dumps(report,indent=2));return result.returncode

if __name__=='__main__':raise SystemExit(main())
