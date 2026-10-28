"""Fail-closed PFD geometry gate; only Python + Shapely >= 2.1 are required.

Contract: schema='pfd-guard/v1', explicit parameters, equipment closed polygons
with boundary ports (point, outward, lead), and directed pipes. Coordinates are
world coordinates in one consistent unit. No symbol catalog, router or CAD API
is imported. Geometry is never snapped, trimmed or repaired by this module.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Mapping

from shapely.geometry import LineString, Point, Polygon


class GuardError(ValueError):
    def __init__(self, code, message, *, pipe=None, equipment=None, segment=None):
        self.code = code
        self.pipe = pipe
        self.equipment = equipment
        self.segment = segment
        super().__init__(message)

    def to_dict(self):
        return dict(code=self.code, message=str(self), pipe=self.pipe,
                    equipment=self.equipment, segment=self.segment)


def _fail(code, message, **ctx):
    raise GuardError(code, message, **ctx)


def _number(value, name, **ctx):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail('invalid_number', f'{name} must be a finite number', **ctx)
    return float(value)


def _point(value, name, **ctx):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        _fail('invalid_point', f'{name} must contain exactly two coordinates', **ctx)
    return tuple(_number(n, name, **ctx) for n in value)


def _id(value, name, **ctx):
    if not isinstance(value, str) or not value.strip():
        _fail('missing_id', f'{name} must be a nonempty string', **ctx)
    return value


def _mapping(value, name, **ctx):
    if not isinstance(value, Mapping):
        _fail('invalid_contract', f'{name} must be an object', **ctx)
    return value


def _array(value, name, **ctx):
    if not isinstance(value, list):
        _fail('invalid_contract', f'{name} must be an array', **ctx)
    return value


def validate_checkpoints(pipe, tol):
    """Validate optional ordered via-points; never snap, sort or deduplicate.

    This only validates the declaration. _one independently checks the actual
    path, including candidates supplied without going through the router.
    """
    _mapping(pipe, 'pipe')
    if 'checkpoints' not in pipe:
        return []
    pid = _id(pipe.get('id'), 'pipe.id')
    try:
        points = [_point(raw, 'pipe.checkpoints', pipe=pid)
                  for raw in _array(pipe['checkpoints'], 'pipe.checkpoints', pipe=pid)]
    except OverflowError:
        _fail('invalid_number', 'pipe.checkpoints coordinates must be finite representable numbers', pipe=pid)
    for i, point in enumerate(points):
        if any(math.dist(point, old) <= tol for old in points[:i]):
            _fail('duplicate_checkpoint', 'checkpoints must be distinct beyond linear_tolerance', pipe=pid)
    return [list(point) for point in points]


def _check_checkpoint_path(line, checkpoints, tol, pid):
    """Verify geometric hits in declared traversal order, including segment interiors."""
    previous = None
    for index, point in enumerate(checkpoints):
        mark = Point(point)
        if line.distance(mark) > tol:
            _fail('checkpoint_missing', f'route misses checkpoint {index}', pipe=pid)
        progress = line.project(mark)
        if previous is not None and progress <= previous + tol:
            _fail('checkpoint_order', f'route does not visit checkpoint {index} after its predecessor', pipe=pid)
        previous = progress


def _unexpected_contact(intersection, allowed, tol):
    """Only numerical point neighborhoods are allowed, never an owner body."""
    # GEOS may retain an almost-zero segment after difference at large world
    # coordinates. A whole connected component must fit ONE endpoint ball;
    # checking each vertex against any endpoint would wrongly exempt a chord.
    def numerical_point(component):
        if component.is_empty:return True
        if component.geom_type in ('Point','LineString','LinearRing'):
            coords=list(component.coords)
            return any(all(math.dist(c[:2],p)<=tol for c in coords) for p in allowed)
        if hasattr(component,'geoms'):return all(numerical_point(g) for g in component.geoms)
        return False
    if numerical_point(intersection):return False
    for point in allowed:
        intersection = intersection.difference(Point(point).buffer(tol))
    return not intersection.is_empty and not numerical_point(intersection)


def _context(scene):
    _mapping(scene, 'scene')
    if scene.get('schema') != 'pfd-guard/v1':
        _fail('invalid_schema', 'schema must be pfd-guard/v1')
    raw = _mapping(scene.get('parameters'), 'parameters')
    names = ('linear_tolerance', 'angular_tolerance_deg', 'equipment_clearance',
             'pipe_clearance', 'minimum_lead')
    p = {name: _number(raw.get(name), name) for name in names}
    if p['linear_tolerance'] <= 0 or not 0 <= p['angular_tolerance_deg'] < 45:
        _fail('invalid_parameters', 'linear tolerance must be positive; angular tolerance in [0,45)')
    if any(p[name] < 0 for name in names[2:]):
        _fail('invalid_parameters', 'clearances and minimum_lead must be nonnegative')
    tol = p['linear_tolerance']
    equipment, ports = {}, {}
    for raw_eq in _array(scene.get('equipment'), 'equipment'):
        _mapping(raw_eq, 'equipment record')
        eid = _id(raw_eq.get('id'), 'equipment.id')
        ctx = {'equipment': eid}
        if eid in equipment:
            _fail('duplicate_equipment', f'duplicate equipment {eid}', **ctx)
        ring = [_point(x, 'polygon point', **ctx) for x in _array(raw_eq.get('polygon'), 'polygon', **ctx)]
        if len(ring) < 4 or math.dist(ring[0], ring[-1]) > tol:
            _fail('unclosed_polygon', 'equipment polygon requires an explicit closed ring', **ctx)
        if any(math.dist(a, b) <= tol for a, b in zip(ring, ring[1:])):
            _fail('degenerate_polygon', 'polygon contains a zero length edge', **ctx)
        poly = Polygon(ring)
        if not poly.is_valid or poly.is_empty or poly.area <= tol * tol:
            _fail('invalid_polygon', 'equipment polygon must be valid, simple and nonzero', **ctx)
        equipment[eid] = poly
        for raw_port in _array(raw_eq.get('ports'), 'ports', **ctx):
            _mapping(raw_port, 'port', **ctx)
            pid = _id(raw_port.get('id'), 'port.id', **ctx)
            if (eid, pid) in ports:
                _fail('duplicate_port', f'duplicate port {eid}.{pid}', **ctx)
            pt = _point(raw_port.get('point'), 'port.point', **ctx)
            vector = _point(raw_port.get('outward'), 'port.outward', **ctx)
            length = math.hypot(*vector)
            if not math.isfinite(length) or length <= tol:
                _fail('invalid_outward', f'port {pid} outward must be nonzero', **ctx)
            unit = (vector[0] / length, vector[1] / length)
            lead = _number(raw_port.get('lead'), 'port.lead', **ctx)
            if lead + tol < p['minimum_lead'] or lead <= tol:
                _fail('invalid_lead', f'port {pid} lead must exceed tolerance and meet minimum_lead', **ctx)
            if poly.boundary.distance(Point(pt)) > tol:
                _fail('port_off_boundary', f'port {pid} must be on its actual closed polygon boundary', **ctx)
            tip = (pt[0] + unit[0] * lead, pt[1] + unit[1] * lead)
            ray = LineString([pt, tip])
            if _unexpected_contact(ray.intersection(poly), [pt], tol):
                _fail('invalid_outward', f'port {pid} outward lead runs into or along equipment', **ctx)
            ports[eid, pid] = {'point': pt, 'outward': unit, 'lead': lead}
    # Unconnected equipment also has to be drawable without covering another
    # original figure. Pipe-only checks cannot detect coincident spare items.
    placed=[]
    for eid,poly in equipment.items():
        for other,other_poly in placed:
            if poly.intersects(other_poly):
                _fail('equipment_overlap', f'equipment {eid} overlaps or touches {other}', equipment=eid)
        placed.append((eid,poly))
    _array(scene.get('pipes'), 'pipes')
    return p, equipment, ports


def _endpoint(raw, ports, pipe, which):
    _mapping(raw, which, pipe=pipe)
    eid = _id(raw.get('equipment'), f'{which}.equipment', pipe=pipe)
    pid = _id(raw.get('port'), f'{which}.port', pipe=pipe, equipment=eid)
    if (eid, pid) not in ports:
        _fail('unknown_port', f'{which} refers to unknown port {eid}.{pid}', pipe=pipe, equipment=eid)
    return eid, pid, ports[eid, pid]


def _initial_run(points, tol):
    """Length and segment count of the initial straight forward run."""
    a, b = points[:2]
    dx, dy = b[0] - a[0], b[1] - a[1]
    norm = math.hypot(dx, dy)
    unit = (dx / norm, dy / norm)
    length, count = norm, 1
    for a, b in zip(points[1:], points[2:]):
        x, y = b[0] - a[0], b[1] - a[1]
        if abs(x * unit[1] - y * unit[0]) > tol or x * unit[0] + y * unit[1] <= 0:
            break
        length += math.hypot(x, y)
        count += 1
    return unit, length, count


def _protection_exit(poly, point, unit, length, clearance, tol):
    """First exit from the port-connected protection interval along a ray.

    Compute exact line/capsule intervals for polygon edges, avoiding a rounded
    buffer approximation and avoiding exemption of a later protection re-entry.
    """
    intervals = []
    ring = list(poly.exterior.coords)
    for a, b in zip(ring, ring[1:]):
        for vertex in (a, b):
            w = (vertex[0]-point[0], vertex[1]-point[1])
            along = w[0]*unit[0]+w[1]*unit[1]
            normal = w[0]*unit[1]-w[1]*unit[0]
            if abs(normal) <= clearance:
                half = math.sqrt(max(0.,clearance*clearance-normal*normal))
                intervals.append((max(0.,along-half),min(length,along+half)))
        v = (b[0]-a[0], b[1]-a[1]); size=math.hypot(*v)
        w = (point[0]-a[0], point[1]-a[1])
        lo, hi = 0., length
        for constant, slope, low, high in (
            ((v[0]*w[1]-v[1]*w[0])/size,(v[0]*unit[1]-v[1]*unit[0])/size,-clearance,clearance),
            ((w[0]*v[0]+w[1]*v[1])/size,(unit[0]*v[0]+unit[1]*v[1])/size,0.,size)):
            if abs(slope) <= 1e-15:
                if constant < low or constant > high:hi=-1.;break
            else:
                left,right=sorted(((low-constant)/slope,(high-constant)/slope))
                lo,hi=max(lo,left),min(hi,right)
        if lo <= hi:intervals.append((lo,hi))
    end=0.
    for lo,hi in sorted(intervals):
        if hi < lo:continue
        if lo > end+tol:break
        end=max(end,hi)
    return min(length,end)


def _one(pipe, context):
    p, equipment, ports = context
    tol = p['linear_tolerance']
    _mapping(pipe, 'pipe')
    pid = _id(pipe.get('id'), 'pipe.id')
    checkpoints = validate_checkpoints(pipe, tol)
    source = _endpoint(pipe.get('source'), ports, pid, 'source')
    target = _endpoint(pipe.get('target'), ports, pid, 'target')
    if source[:2] == target[:2]:
        _fail('same_port', 'a pipe cannot start and finish at the same port', pipe=pid)
    points = [_point(x, 'pipe.points', pipe=pid) for x in _array(pipe.get('points'), 'pipe.points', pipe=pid)]
    if len(points) < 2:
        _fail('missing_path', 'pipe requires at least two points', pipe=pid)
    warnings = []
    for idx, (a, b) in enumerate(zip(points, points[1:])):
        if math.dist(a, b) <= tol:
            _fail('zero_segment', 'zero length pipe segment', pipe=pid, segment=idx)
        if min(abs(b[0] - a[0]), abs(b[1] - a[1])) > tol:
            _fail('nonorthogonal_segment', 'pipe segment must be horizontal or vertical', pipe=pid, segment=idx)
    for idx, (a, b, c) in enumerate(zip(points, points[1:], points[2:])):
        v, w = (b[0]-a[0], b[1]-a[1]), (c[0]-b[0], c[1]-b[1])
        lv, lw = math.hypot(*v), math.hypot(*w)
        cross = abs(v[0]*w[1]-v[1]*w[0]) / max(lv, lw)
        if cross <= tol:
            if v[0]*w[0]+v[1]*w[1] < 0:
                _fail('backtrack', '180 degree reversal in pipe', pipe=pid, segment=idx+1)
            warnings.append(dict(code='redundant_collinear_point', pipe=pid, point=idx+1))
    line = LineString(points)
    if not line.is_simple:
        _fail('self_intersection', 'pipe self-intersects or repeats a segment', pipe=pid)
    _check_checkpoint_path(line, checkpoints, tol, pid)
    runs, exemptions = [], []
    for which, endpoint, path in (('source', source, points), ('target', target, points[::-1])):
        eid, _, port = endpoint
        if math.dist(path[0], port['point']) > tol:
            _fail('endpoint_mismatch', f'{which} does not meet its declared port', pipe=pid, equipment=eid,
                  segment=0 if which == 'source' else len(points)-2)
        unit, length, count = _initial_run(path, tol)
        dot = max(-1.0, min(1.0, unit[0]*port['outward'][0]+unit[1]*port['outward'][1]))
        if math.degrees(math.acos(dot)) > p['angular_tolerance_deg'] + 1e-9:
            _fail('wrong_port_direction', f'{which} approach must follow its outward axis', pipe=pid,
                  equipment=eid, segment=0 if which == 'source' else len(points)-2)
        if length + tol < max(port['lead'], p['minimum_lead']):
            _fail('short_lead', f'{which} bends before its required lead length', pipe=pid, equipment=eid,
                  segment=0 if which == 'source' else len(points)-2)
        runs.append(count)
        clear = p['equipment_clearance']
        exit_length = _protection_exit(equipment[eid],port['point'],unit,length,clear,tol) if clear > tol else 0.
        exemptions.append(LineString([port['point'],(port['point'][0]+unit[0]*exit_length,
                                                    port['point'][1]+unit[1]*exit_length)]))
    for idx, (a, b) in enumerate(zip(points, points[1:])):
        segment = LineString([a, b])
        for eid, poly in equipment.items():
            allowed = []
            if idx == 0 and eid == source[0]:
                allowed.append(source[2]['point'])
            if idx == len(points)-2 and eid == target[0]:
                allowed.append(target[2]['point'])
            if _unexpected_contact(segment.intersection(poly), allowed, tol):
                _fail('equipment_contact', 'pipe crosses or touches an equipment body/boundary',
                      pipe=pid, equipment=eid, segment=idx)
            clear = p['equipment_clearance']
            own_initial = eid == source[0] and idx < runs[0]
            own_final = eid == target[0] and idx >= len(points)-1-runs[1]
            # Only the port-connected part of the own straight endpoint run is
            # exempt. A later re-entry into the same protection zone is blocked.
            # The actual body above is NEVER exempted.
            unexempt = segment
            if own_initial:unexempt=unexempt.difference(exemptions[0].buffer(tol))
            if own_final:unexempt=unexempt.difference(exemptions[1].buffer(tol))
            if clear > tol and not unexempt.is_empty and unexempt.distance(poly) < clear - tol:
                _fail('equipment_clearance', 'pipe violates equipment protection zone',
                      pipe=pid, equipment=eid, segment=idx)
    return line, warnings


def _pair(a, a_line, b, b_line, p):
    if a['id'] == b['id']:
        _fail('duplicate_pipe_id', 'pipe IDs must be unique', pipe=b['id'])
    tol = p['linear_tolerance']
    if a_line.equals(b_line) or (a_line.hausdorff_distance(b_line) <= tol and abs(a_line.length-b_line.length) <= tol):
        _fail('duplicate_pipe', f'pipe duplicates {a["id"]}', pipe=b['id'])
    overlap = a_line.intersection(b_line)
    if not overlap.is_empty:
        _fail('pipe_contact', f'pipe intersects registered pipe {a["id"]}', pipe=b['id'])
    if a_line.distance(b_line) < p['pipe_clearance'] - tol:
        _fail('pipe_clearance', f'pipe violates clearance from {a["id"]}', pipe=b['id'])


def _all(scene, extra=None):
    context = _context(scene)
    records = list(scene['pipes'])
    if extra is not None:
        records.append(extra)
    checked, warnings = [], []
    for pipe in records:
        line, local = _one(pipe, context)
        for old, old_line in checked:
            _pair(old, old_line, pipe, line, context[0])
        checked.append((pipe, line))
        warnings.extend(local)
    return {'ok': True, 'equipment_count': len(context[1]),
            'pipe_count': len(checked), 'warnings': warnings}


def validate_scene(scene):
    """Validate every registered pipe and equipment; do not mutate the scene."""
    return _all(scene)


def validate_pipe(scene, pipe):
    """Validate a new pipe against a valid scene without changing either."""
    return _all(scene, pipe)


def commit_pipe(scene, pipe):
    """Validate then atomically append an owned copy. Failure leaves scene intact."""
    candidate = copy.deepcopy(pipe)
    result = validate_pipe(scene, candidate)
    scene['pipes'].append(candidate)
    return result
