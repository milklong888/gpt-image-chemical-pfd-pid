"""Read-only effective lineweight continuity check on APW_PFD-tagged DXF.

Checks model-space entity/layer/INSERT inheritance in hundredths of mm. A
registry LWDEFAULT must be supplied explicitly if DEFAULT occurs. Zero is a
device-dependent hairline, not a verified physical width. CTB/STB and viewport
plot overrides are outside this model-space entity-property audit.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import ezdxf
from ezdxf.math import Vec3
from ezdxf.lldxf.const import VALID_DXF_LINEWEIGHTS

TOL=1e-5

class WidthError(ValueError):
    def __init__(self,code,message,**details):
        self.code=code;self.details=details;super().__init__(message)
    def data(self):return {'code':self.code,'message':str(self),**self.details}

def metadata(entity):
    if not entity.has_xdata('APW_PFD'):return {}
    return dict(t.value.split('=',1) for t in entity.get_xdata('APW_PFD') if t.code==1000 and '=' in t.value)

def effective_layer(entity,parents=()):
    layer=entity.dxf.layer
    if layer=='0':
        for insert in parents:
            if insert.dxf.layer!='0':return insert.dxf.layer
    return layer

def effective_lineweight(doc,entity,parents=(),default_lineweight=None):
    """Resolve actual inheritance; parents are immediate INSERT first.

    Caller passes actual insertion context from walk(). A top-level ByBlock
    entity has no parent evidence and is deliberately rejected, not guessed.
    """
    trace=[]
    def positive(value,source):
        if isinstance(value,bool) or not isinstance(value,int) or value not in VALID_DXF_LINEWEIGHTS:
            raise WidthError('invalid_lineweight','not an allowed DXF lineweight',value=value,source=source)
        if value==0:raise WidthError('zero_lineweight','lineweight 0 is a device-dependent hairline, not a verified positive width',source=source)
        if value<0:raise WidthError('invalid_lineweight','observed default must be a positive physical lineweight, not another inheritance selector',value=value,source=source)
        return value
    def resolve(obj,chain):
        value=obj.dxf.get('lineweight',-1)
        trace.append({'entity':obj.dxf.handle,'raw':value,'layer':obj.dxf.layer})
        if value>=0:return positive(value,'entity '+str(obj.dxf.handle))
        if value==-2:
            if not chain:raise WidthError('unresolved_byblock','ByBlock has no INSERT context',handle=obj.dxf.handle)
            return resolve(chain[0],chain[1:])
        if value==-1:
            name=effective_layer(obj,chain)
            try:layer=doc.layers.get(name)
            except Exception as exc:raise WidthError('missing_layer','effective layer is missing',layer=name) from exc
            value=layer.dxf.get('lineweight',-3)
            trace.append({'layer':name,'raw':value})
            if value>=0:return positive(value,'layer '+name)
            if value!=-3:raise WidthError('invalid_layer_lineweight','layer cannot inherit ByLayer/ByBlock',layer=name,value=value)
        if value==-3:
            if default_lineweight is None:raise WidthError('unresolved_default','DEFAULT requires an explicitly observed LWDEFAULT value; it is stored in the CAD registry')
            trace.append({'observed_LWDEFAULT':default_lineweight})
            return positive(default_lineweight,'explicit observed LWDEFAULT')
        raise WidthError('invalid_lineweight','unknown lineweight selector',value=value)
    value=resolve(entity,tuple(parents))
    return {'hundredths_mm':value,'mm':value/100,'trace':trace}

def walk(doc):
    def visit(layout,parents=(),names=()):
        for entity in layout:
            if entity.dxftype()=='INSERT':
                name=entity.dxf.name
                if name in names:raise WidthError('cyclic_block','cyclic INSERT block reference',block=name)
                if entity.mcount>1:raise WidthError('unsupported_minsert','MINSERT needs explicit expansion before lineweight audit')
                yield from visit(doc.blocks[name],(entity,)+parents,names+(name,))
            else:yield entity,parents
    yield from visit(doc.modelspace())

def wcs(point,parents):
    p=Vec3(point)
    for parent in parents:p=parent.matrix44().transform(p)
    return list(p)

def endpoints(entity,parents):
    typ=entity.dxftype()
    if typ=='LINE':points=[entity.dxf.start,entity.dxf.end]
    elif typ=='LWPOLYLINE':
        if entity.closed:raise WidthError('closed_route','continuity needs an open path')
        if entity.dxf.get('const_width',0)!=0 or any(abs(p[2])+abs(p[3])>0 for p in entity.get_points()):
            raise WidthError('geometric_polyline_width','geometric polyline width can override appearance; lineweight alone is insufficient')
        points=list(entity.vertices_in_wcs())
        if len(points)<2:raise WidthError('short_route','route needs at least two vertices')
        points=[points[0],points[-1]]
    else:raise WidthError('unsupported_route_type','route/nozzle must be LINE or open LWPOLYLINE',type=typ)
    return [wcs(p,parents) for p in points]

def audit(dxf,default_lineweight=None):
    path=Path(dxf);doc=ezdxf.readfile(path)
    errors=[];routes=[];nozzles=[];ports=[];pairs=[]
    def error(code,message,**kw):errors.append({'code':code,'message':message,**kw})
    try:records=list(walk(doc))
    except WidthError as exc:records=[];errors.append(exc.data())
    for entity,parents in records:
        m=metadata(entity);role=m.get('role')
        if role not in ('material_route','nozzle','port'):continue
        address='/'.join([p.dxf.handle for p in reversed(parents)]+[entity.dxf.handle])
        record={'address':address,'handle':entity.dxf.handle,'meta':m,'layer':effective_layer(entity,parents)}
        if role=='port':
            if entity.dxftype()!='POINT':error('unsupported_port_type','port metadata must be POINT',address=address);continue
            record['point']=wcs(entity.dxf.location,parents);ports.append(record);continue
        try:
            record['points']=endpoints(entity,parents)
            record['lineweight']=effective_lineweight(doc,entity,parents,default_lineweight)
        except WidthError as exc:errors.append({**exc.data(),'address':address,'role':role,'meta':m});continue
        for obj,chain in [(entity,parents)]+[(p,parents[i+1:]) for i,p in enumerate(parents)]:
            layer=doc.layers.get(effective_layer(obj,chain))
            if layer.is_off() or layer.is_frozen() or not layer.dxf.get('plot',1) or obj.dxf.get('invisible',0):
                error('hidden_line','route/nozzle or its INSERT is hidden/nonplotting',address=address)
        (nozzles if role=='nozzle' else routes).append(record)
    for nozzle in nozzles:
        m=nozzle['meta'];sid=m.get('stream');unit=m.get('unit')
        if not sid or not unit:error('missing_nozzle_identity','nozzle requires unit and stream IDs',address=nozzle['address']);continue
        matches=[p for p in ports if p['meta'].get('unit')==unit and p['meta'].get('stream')==sid and any(math.dist(p['point'],q)<=TOL for q in nozzle['points'])]
        if len(matches)!=1:
            error('nozzle_port_ambiguity','one registered port must coincide with one nozzle endpoint',address=nozzle['address'],unit=unit,stream=sid,matches=len(matches));continue
        port=matches[0]
        attached=[(r,side) for r in routes if r['meta'].get('stream')==sid for side,q in zip(('source','target'),r['points']) if math.dist(port['point'],q)<=TOL]
        if len(attached)!=1:
            error('nozzle_route_ambiguity','one external route endpoint must match registered nozzle port',address=nozzle['address'],unit=unit,stream=sid,matches=len(attached));continue
        route,side=attached[0]
        pair={'unit':unit,'stream':sid,'point':port['point'],'route_side':side,
              'nozzle_handle':nozzle['handle'],'route_handle':route['handle'],'port_handle':port['handle'],
              'nozzle_address':nozzle['address'],'route_address':route['address'],
              'nozzle_lineweight':nozzle['lineweight'],'route_lineweight':route['lineweight']}
        pairs.append(pair)
        nw=nozzle['lineweight']['hundredths_mm'];rw=route['lineweight']['hundredths_mm']
        if nw!=rw:error('lineweight_discontinuity','nozzle and connected material route have different effective lineweights',
                        unit=unit,stream=sid,nozzle_handle=nozzle['handle'],route_handle=route['handle'],point=port['point'],
                        nozzle_mm=nw/100,route_mm=rw/100,relation='nozzle_thinner' if nw<rw else 'nozzle_thicker')
    raw_nozzles=sum(metadata(e).get('role')=='nozzle' for e,_ in records)
    if not raw_nozzles:error('no_nozzles','no explicitly tagged nozzles were available to verify')
    return {'schema':'pfd-lineweight-audit/v1','ok':not errors,'file':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'scope':'saved DXF model-space entity/layer/INSERT lineweight continuity; not CTB/STB or viewport plotting certification',
            'default_lineweight_source':'explicit caller-observed LWDEFAULT' if default_lineweight is not None else 'not supplied; unresolved DEFAULT rejected',
            'counts':{'material_routes':sum(metadata(e).get('role')=='material_route' for e,_ in records),'nozzles':raw_nozzles,'registered_ports':len(ports),'matched_nozzle_route_pairs':len(pairs),'errors':len(errors)},
            'errors':errors,'pairs':pairs}

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('dxf',type=Path);ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--default-lineweight',type=int,help='observed current CAD LWDEFAULT in hundredths of mm; never guess')
    args=ap.parse_args();result=audit(args.dxf,args.default_lineweight)
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:result[k] for k in ('ok','counts','errors')},ensure_ascii=False));raise SystemExit(0 if result['ok'] else 2)
