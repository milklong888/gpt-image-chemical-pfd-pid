"""Portable explicit-file entry for the independently scoped geometry modules."""
import argparse,json
from pathlib import Path
from pfd_guard import validate_scene,GuardError

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=['validate','route'])
    ap.add_argument('input',type=Path)
    ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--runtime',type=Path,help='Optional directory containing route.mjs and installed libavoid-js')
    args=ap.parse_args();payload=json.loads(args.input.read_text('utf8'))
    if args.mode=='route' and args.runtime is None:ap.error('route requires explicit --runtime containing the reviewed route.mjs and separately installed libavoid-js')
    scene=payload.get('scene',payload)
    try:
        if args.mode=='route':
            from pfd_router import route_scene
            scene=route_scene(scene,payload['connections'],runtime=args.runtime)
        result={'ok':True,'geometry':validate_scene(scene),'scene':scene,
                'scope':'Geometry feasibility only; no process topology, symbols, standards compliance or native DWG acceptance is inferred.'}
    except (GuardError,KeyError,ValueError,RuntimeError) as error:
        result={'ok':False,'error':error.to_dict() if isinstance(error,GuardError) else {'type':type(error).__name__,'message':str(error)}}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    return 0 if result['ok'] else 1

if __name__=='__main__':raise SystemExit(main())
