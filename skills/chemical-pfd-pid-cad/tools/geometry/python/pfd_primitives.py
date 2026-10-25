"""New bounded jump/arrow drawing primitives; no project figures or symbol data.

Only an explicit vertical route, one continuous horizontal under-line and
three tangent arcs are supported. This does not infer process connections,
discover all drawing obstacles, replace source drawings, or certify standards.
"""
import math
from dataclasses import dataclass
from ezdxf.path import make_path
from shapely.geometry import LineString,Point,Polygon,box
from shapely.ops import unary_union

EPS=1e-6

def _entity(doc,handle):
    e=doc.entitydb.get(handle)
    if e is None or not e.is_alive:raise ValueError('declared entity missing: '+handle)
    return e

@dataclass(frozen=True)
class Jump:
    center:tuple
    radius:float
    lower_y:float
    upper_y:float
    side:int=1

    def validate(self):
        values=(*self.center,self.radius,self.lower_y,self.upper_y)
        if len(self.center)!=2 or any(not math.isfinite(v) for v in values):raise ValueError('finite jump geometry required')
        if self.radius<=0 or self.side not in (-1,1):raise ValueError('positive radius and side -1/+1 required')
        if not self.lower_y<self.center[1]-2*self.radius<self.center[1]+2*self.radius<self.upper_y:raise ValueError('jump does not fit explicit vertical extent')

    def arcs(self):
        self.validate();x,y=self.center;r=self.radius
        result=[((x+r,y-2*r),90.,180.),((x+r,y),270.,90.),((x+r,y+2*r),180.,270.)]
        if self.side<0:result=[((2*x-c[0],c[1]),(180-b)%360,(180-a)%360) for c,a,b in result]
        return result

def _points(e):
    if e.dxftype()=='LINE':return [tuple(e.dxf.start)[:2],tuple(e.dxf.end)[:2]]
    return [(p.x,p.y) for p in make_path(e).flattening(.001)]

def _ends(e):
    return _points(e) if e.dxftype()=='LINE' else [tuple(e.start_point)[:2],tuple(e.end_point)[:2]]

def _style(e):
    return tuple(e.dxf.get(k,v) for k,v in [('layer','0'),('color',256),('true_color',None),('lineweight',-1),('linetype','BYLAYER'),('ltscale',1),('transparency',0)])

def add_jump(doc,spec,*,layer='PROCESS',lineweight=80,color=7):
    """Create a new route only. A caller owns any source replacement policy."""
    spec.validate()
    if lineweight<=0:raise ValueError('explicit positive DXF lineweight required')
    if layer not in doc.layers:doc.layers.new(layer,dxfattribs={'lineweight':lineweight,'color':color})
    attrs={'layer':layer,'color':color,'lineweight':lineweight};m=doc.modelspace();x,y=spec.center;r=spec.radius
    lines=[m.add_line((x,spec.lower_y),(x,y-2*r),dxfattribs=attrs),m.add_line((x,y+2*r),(x,spec.upper_y),dxfattribs=attrs)]
    arcs=[m.add_arc(c,r,a,b,dxfattribs=attrs) for c,a,b in spec.arcs()]
    return {'lines':[e.dxf.handle for e in lines],'arcs':[e.dxf.handle for e in arcs]}

def audit_jump(doc,spec,handles,under_handle,*,paper_mm_per_unit,equipment_polygons=(),label_boxes=(),arrow_polygons=(),protected_points=()):
    """Check actual saved primitives against explicit, limited caller context.

    Geometric crossing is expected. It is a declared logical nonconnection,
    never accepted as a T merely because the planar centerlines intersect.
    """
    if isinstance(paper_mm_per_unit,bool) or not math.isfinite(paper_mm_per_unit) or paper_mm_per_unit<=0:raise ValueError('explicit positive paper_mm_per_unit required for ink clearance')
    spec.validate();lines=[_entity(doc,h) for h in handles['lines']];arcs=[_entity(doc,h) for h in handles['arcs']]
    if len(lines)!=2 or len(arcs)!=3 or any(e.dxftype()!='LINE' for e in lines) or any(e.dxftype()!='ARC' for e in arcs):raise ValueError('exactly2 LINE and3 ARC are required')
    under=_entity(doc,under_handle);x,y=spec.center;r=spec.radius
    if under.dxftype()!='LINE' or abs(under.dxf.start.y-y)>EPS or abs(under.dxf.end.y-y)>EPS or not min(under.dxf.start.x,under.dxf.end.x)<x<max(under.dxf.start.x,under.dxf.end.x):raise ValueError('explicit continuous horizontal under-line required')
    for e,(c,a,b) in zip(arcs,spec.arcs()):
        if math.dist(tuple(e.dxf.center)[:2],c)>EPS or abs(e.dxf.radius-r)>EPS or abs((e.dxf.start_angle-a+180)%360-180)>EPS or abs((e.dxf.end_angle-b+180)%360-180)>EPS:raise ValueError('actual arc geometry/direction differs')
    wanted=[[(x,spec.lower_y),(x,y-2*r)],[(x,y+2*r),(x,spec.upper_y)]]
    if any(any(math.dist(a,b)>EPS for a,b in zip(_ends(e),ps)) for e,ps in zip(lines,wanted)):raise ValueError('bridge lead endpoint differs')
    route=lines+arcs
    if len({_style(e) for e in route})!=1 or lines[0].dxf.lineweight<=0:raise ValueError('bridge style/physical lineweight differs')
    def tangent(e,p):
        if e.dxftype()=='LINE':v=e.dxf.end-e.dxf.start;n=math.hypot(v.x,v.y);return (v.x/n,v.y/n)
        return (-(p[1]-e.dxf.center.y)/e.dxf.radius,(p[0]-e.dxf.center.x)/e.dxf.radius)
    for e in arcs:
        for p in _ends(e):
            mates=[f for f in route if f is not e and any(math.dist(p,q)<=EPS for q in _ends(f))]
            if len(mates)!=1 or abs(sum(a*b for a,b in zip(tangent(e,p),tangent(mates[0],p))))<1-EPS:raise ValueError('bridge is not uniquely continuous and tangent')
    curve=unary_union([LineString(_points(e)) for e in arcs]);stroke=curve.buffer(lines[0].dxf.lineweight/(200*paper_mm_per_unit))
    for p in protected_points:
        if abs(p[0]-x)<EPS and y-2*r-EPS<=p[1]<=y+2*r+EPS:raise ValueError('bridge consumes a protected branch/port/arrow contact')
    for polygon in [*equipment_polygons,*arrow_polygons]:
        if stroke.intersects(Polygon(polygon)):raise ValueError('bridge touches a declared body or arrow')
    for bounds in label_boxes:
        if stroke.intersects(box(*bounds)):raise ValueError('bridge touches a declared label')
    cross=curve.intersection(LineString(_points(under)))
    if cross.is_empty:raise ValueError('jump does not cross the declared under-route')
    for e in doc.modelspace():
        if e.dxftype()=='CIRCLE' and Point(tuple(e.dxf.center)[:2]).distance(cross)<EPS:raise ValueError('junction dot at declared nonconnection')
    return {'ok':True,'continuous_arcs':3,'logical_nonconnection':True,'scope':'Only supplied equipment/label/arrow/protected-point context checked; no global layout or native plotting claim.'}

def arrow_shape(e):
    """Explicit handles only; do not classify every SOLID as an arrow."""
    if e.dxftype()=='LWPOLYLINE':
        ps=list(e.get_points())
        if len(ps)!=2 or e.closed or e.dxf.get('const_width',0) or ps[0][4] or ps[1][4]:raise ValueError('only straight two-point tapered heads supported')
        w0,w1=ps[0][2:4]
        if min(w0,w1)!=0 or max(w0,w1)<=0:raise ValueError('one positive base width and a zero-width tip required')
        base,tip=(ps[0][:2],ps[1][:2]) if w0>w1 else (ps[1][:2],ps[0][:2]);w=max(w0,w1)/2
        dx,dy=tip[0]-base[0],tip[1]-base[1];n=math.hypot(dx,dy)
        if n<=EPS:raise ValueError('degenerate arrow')
        return Polygon([(base[0]-dy/n*w,base[1]+dx/n*w),(base[0]+dy/n*w,base[1]-dx/n*w),tip])
    if e.dxftype()=='SOLID':
        ps=[tuple(getattr(e.dxf,'vtx'+str(i)))[:2] for i in range(4)]
        if ps[2]!=ps[3] or Polygon(ps[:3]).area<=EPS:raise ValueError('explicit triangular SOLID required')
        return Polygon(ps[:3])
    raise ValueError('unsupported explicitly selected arrow type')

def draw_order(doc):
    mapping=dict(doc.modelspace().get_redraw_order())
    return [e.dxf.handle for e in sorted(doc.modelspace(),key=lambda e:2**128 if mapping.get(e.dxf.handle,e.dxf.handle)=='0' else int(mapping.get(e.dxf.handle,e.dxf.handle),16))]

def arrows_to_front(doc,handles):
    if not handles or len(set(handles))!=len(handles):raise ValueError('explicit unique arrow handles required')
    selected=set(handles)
    for h in handles:arrow_shape(_entity(doc,h))
    before=draw_order(doc)
    if not selected<=set(before):raise ValueError('selected arrow is not in modelspace')
    after=[h for h in before if h not in selected]+[h for h in before if h in selected]
    doc.modelspace().set_redraw_order(dict(zip(after,sorted(before,key=lambda h:int(h,16)))))
    doc.header['$SORTENTS']=doc.header.get('$SORTENTS',0)|32
    return {'before':before,'after':after,'selected':after[-len(selected):]}

def audit_arrow_order(doc,handles,*,label_boxes=()):
    if not handles or len(set(handles))!=len(handles):raise ValueError('explicit unique arrows required')
    shapes=[arrow_shape(_entity(doc,h)) for h in handles];order=draw_order(doc)
    if set(order[-len(handles):])!=set(handles) or not doc.header.get('$SORTENTS',0)&32:raise ValueError('arrows are not all at the top of plot-enabled draw order')
    for shape in shapes:
        if any(shape.intersects(box(*b)) for b in label_boxes):raise ValueError('arrow touches a declared label')
    return {'ok':True,'selected_arrow_count':len(handles),'actual_dxf_draw_order':order,'native_draw_order_verified':False}
