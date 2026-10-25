"""Preserve source primitives; compare native geometry after CAD roundtrip."""
import math
from pfd_guard import GuardError

def signature(entity):
    t=entity.dxftype();d=entity.dxf
    attributes={
      'LINE':['start','end'],'CIRCLE':['center','radius'],
      'ARC':['center','radius','start_angle','end_angle'],
      'ELLIPSE':['center','major_axis','ratio','start_param','end_param'],
      'SOLID':['vtx0','vtx1','vtx2','vtx3'],'TRACE':['vtx0','vtx1','vtx2','vtx3']}
    def plain(value):
        if isinstance(value,(str,int,float,bool)):return value
        return list(value)
    if t in attributes:return {'type':t,**{k:plain(getattr(d,k)) for k in attributes[t]}}
    if t=='LWPOLYLINE':return {'type':t,'points':[list(p) for p in entity.get_points()],'closed':entity.closed,'const_width':d.get('const_width',0)}
    if t=='SPLINE':return {'type':t,'degree':d.degree,'control_points':[list(p) for p in entity.control_points],
        'fit_points':[list(p) for p in entity.fit_points],'knots':list(entity.knots),'weights':list(entity.weights),'flags':d.flags}
    raise GuardError('unsupported_source_entity','source primitive requires explicit support: '+t)

def equal_geometry(a,b,tolerance):
    if isinstance(a,dict):return isinstance(b,dict) and set(a)==set(b) and all(equal_geometry(a[k],b[k],tolerance) for k in a)
    if isinstance(a,(list,tuple)):return isinstance(b,(list,tuple)) and len(a)==len(b) and all(equal_geometry(x,y,tolerance) for x,y in zip(a,b))
    if isinstance(a,(int,float)) and not isinstance(a,bool):return isinstance(b,(int,float)) and math.isfinite(a) and math.isfinite(b) and abs(a-b)<=tolerance
    return a==b
