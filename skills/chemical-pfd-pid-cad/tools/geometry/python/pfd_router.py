"""libavoid candidate generation followed by mandatory independent validation."""
import copy,json,math,os,shutil,subprocess
from pathlib import Path
from shapely.geometry import Polygon,LineString,Point
from pfd_guard import GuardError,validate_pipe,validate_scene,commit_pipe,validate_checkpoints

def canonical(points,tol=1e-7):
    out=[]
    for p in points:
        p=list(p)
        if out and math.dist(out[-1],p)<=tol: continue
        while len(out)>1:
            a,b=out[-2:];v=(b[0]-a[0],b[1]-a[1]);w=(p[0]-b[0],p[1]-b[1])
            if abs(v[0]*w[1]-v[1]*w[0])<=tol and v[0]*w[0]+v[1]*w[1]>0:out.pop()
            else:break
        out.append(p)
    return out

def cost(points):
    return (len(points)-2,round(sum(math.dist(a,b) for a,b in zip(points,points[1:])),6))

def simplify(scene,pipe):
    """Remove feasible local detours while preserving ends, checkpoints and clearance.
    A local certificate, not a claim of globally optimal multi-edge routing.
    """
    pipe=copy.deepcopy(pipe);pipe['points']=canonical(pipe['points'])
    validate_pipe(scene,pipe)
    while True:
        points=pipe['points'];best=pipe
        for i in range(len(points)-2):
            for j in range(i+2,len(points)):
                a,b=points[i],points[j]
                for middle in ([],[[a[0],b[1]]],[[b[0],a[1]]]):
                    q=copy.deepcopy(pipe);q['points']=canonical(points[:i+1]+middle+points[j:])
                    if cost(q['points'])>=cost(best['points']):continue
                    try:validate_pipe(scene,q)
                    except GuardError:continue
                    best=q
        if best is pipe:return pipe
        pipe=best

def verify_simplified(scene):
    for pipe in scene['pipes']:
        rest=copy.deepcopy(scene);rest['pipes']=[p for p in scene['pipes'] if p['id']!=pipe['id']]
        q=simplify(rest,pipe)
        if cost(q['points'])<cost(pipe['points']):
            raise GuardError('avoidable_detour','route contains a feasible simpler local replacement',pipe=pipe['id'])
    return {'redundant_routes':0,'criterion':'no feasible straight/one-bend replacement reduces bends or length while satisfying all geometry constraints'}


def _middle_checkpoints(checkpoints,source,start,end,target,tol,pid):
    """Send only the via-points not already met by the fixed directed leads.

    Keep the full declaration on the eventual pipe. These fixed-segment checks
    reject definite misordering before Node; the independent guard checks strict
    progression on the complete actual route, including tolerance-boundary hits.
    """
    if not checkpoints:return []
    prefix=LineString([source,start]);suffix=LineString([end,target])
    middle=[];previous_rank=-1;progress_by_rank={}
    for index,checkpoint in enumerate(checkpoints):
        point=Point(checkpoint)
        on_prefix=prefix.distance(point)<=tol
        on_suffix=suffix.distance(point)<=tol
        # At a coincident/tolerance-shared tip, use the first still-available
        # fixed phase. This is not an acceptance decision: full-route geometry
        # and the complete original checkpoint order are checked below by guard.
        rank=(0 if previous_rank<=0 else 2) if on_prefix and on_suffix else 0 if on_prefix else 2 if on_suffix else 1
        if rank<previous_rank:
            raise GuardError('checkpoint_order',f'checkpoint {index} contradicts fixed lead traversal order',pipe=pid)
        if rank in (0,2):
            progress=(prefix if rank==0 else suffix).project(point)
            previous=progress_by_rank.get(rank)
            # Endpoint projection is clamped. Do not falsely reject two points
            # straddling a virtual lead tip within tol; the complete-path guard
            # remains responsible for strict >tol progression after generation.
            if previous is not None and progress<previous-tol:
                raise GuardError('checkpoint_order',f'checkpoint {index} reverses a fixed lead',pipe=pid)
            progress_by_rank[rank]=progress
        else:middle.append(checkpoint)
        previous_rank=rank
    return middle


def _checkpoint_candidates(request):
    """Bounded libavoid direction variants, not a separate path planner.

    Direction masks are candidate-generation hints only. Every whole candidate
    still has to pass the unchanged independent guard with the full metadata.
    No-checkpoint calls retain exactly one original request.
    """
    yield request
    if not request.get('checkpoints'):return
    pairs=[(a,d) for a in (1,2,4,8) for d in (1,2,4,8)]
    for pair in pairs:
        candidate=copy.deepcopy(request)
        candidate['checkpoint_directions']=[list(pair) for _ in candidate['checkpoints']]
        yield candidate


def _checkpoint_frame(payload):
    """Rigid axis-aligned candidate frame only; world contract stays unchanged.

    All engine geometry uses one translation and a 90-degree rotation putting
    the source outward along +x. No snapping, scaling, obstacle filtering or
    tolerance change. No-checkpoint requests are returned untouched.
    """
    pipe=payload['pipes'][0]
    if not pipe.get('checkpoints'):return payload,lambda points:points
    vx,vy=pipe['start_outward']
    if abs(vy)<=1e-9 and abs(vx)>1e-9:sx,sy=(1 if vx>0 else -1),0
    elif abs(vx)<=1e-9 and abs(vy)>1e-9:sx,sy=0,(1 if vy>0 else -1)
    else:raise RuntimeError('checkpoint frame requires an axis-aligned source outward')
    ox,oy=pipe['start']
    def point(p):
        x,y=p[0]-ox,p[1]-oy
        return [x*sx+y*sy,-x*sy+y*sx]
    def vector(v):return [v[0]*sx+v[1]*sy,-v[0]*sy+v[1]*sx]
    normalized=copy.deepcopy(payload)
    for obstacle in normalized['obstacles']:
        obstacle['points']=[point(p) for p in obstacle['points']]
    for record in normalized['pipes']:
        for field in ('start','end'):
            record[field]=point(record[field])
            record[field+'_outward']=vector(record[field+'_outward'])
        if 'checkpoints' in record:record['checkpoints']=[point(p) for p in record['checkpoints']]
    def world(points):return [[ox+p[0]*sx-p[1]*sy,oy+p[0]*sy+p[1]*sx] for p in points]
    return normalized,world

def _route_order(scene,connections,runtime=None,*,state_cache=None):
    result=copy.deepcopy(scene)
    validate_scene(result)
    runtime=Path(runtime or Path(__file__).with_name('pfd_runtime'))
    runner=runtime/'route.mjs'
    node=os.environ.get('PFD_NODE') or shutil.which('node')
    if not node or not runner.exists():raise RuntimeError('libavoid runtime missing; no fallback route is permitted')
    eq={e['id']:e for e in result['equipment']}
    params=result['parameters'];clear=params['equipment_clearance']+params['linear_tolerance']*20
    requests=[]
    for connection in connections:
        request={'id':connection['id']};port_points=[]
        checkpoints=validate_checkpoints(connection,params['linear_tolerance'])
        for key,field in [('source','start'),('target','end')]:
            ref=connection[key]
            ports={p['id']:p for p in eq[ref['equipment']]['ports']}
            port=ports[ref['port']];p=port['point'];v=port['outward'];length=math.hypot(*v)
            lead=max(port['lead'],clear+params['linear_tolerance']*20)
            request[field]=[p[0]+v[0]/length*lead,p[1]+v[1]/length*lead]
            # Both ends describe visibility OUTWARD from the port. libavoid
            # reverses that direction for arrival at the target; negating the
            # target here would force a U-turn before the final lead segment.
            request[field+'_owner']=ref['equipment']
            request[field+'_outward']=[v[0]/length,v[1]/length]
            port_points.append(p)
        if 'checkpoints' in connection:
            request['checkpoints']=_middle_checkpoints(checkpoints,port_points[0],request['start'],
                                                       request['end'],port_points[1],params['linear_tolerance'],connection['id'])
            if request['checkpoints']:request['linear_tolerance']=params['linear_tolerance']
        requests.append((connection,request,port_points))
    obstacles=[]
    for e in result['equipment']:
        polygon=Polygon(e['polygon']).buffer(clear,join_style='mitre')
        obstacles.append({'id':e['id'],'points':list(polygon.exterior.coords)[:-1]})
    answer={'router':'libavoid-js','version':'0.5.0-beta.5'}
    # Accepted routes are hard obstacles. A soft crossing penalty alone does
    # not guarantee separation. Failed candidates never enter result.
    prefix=[];checkpoint_search=[]
    for connection,request,ports in requests:
        prefix.append(connection['id']);key=tuple(prefix)
        if state_cache is not None and key in state_cache:
            # Cache is local to one route_scene invocation and one immutable
            # input scene. Only independently committed prefixes are stored.
            result['pipes']=copy.deepcopy(state_cache[key])
            continue
        hard=list(obstacles)
        for p in result['pipes']:
            gap=params['pipe_clearance']+params['linear_tolerance']*20
            for i,(a,b) in enumerate(zip(p['points'],p['points'][1:])):
                x0,y0=min(a[0],b[0])-gap,min(a[1],b[1])-gap
                x1,y1=max(a[0],b[0])+gap,max(a[1],b[1])+gap
                hard.append({'id':'accepted_pipe_'+p['id']+'_'+str(i),'points':[[x0,y0],[x0,y1],[x1,y1],[x1,y0]]})
        rejected_directions=[];last_error=None
        for variant in _checkpoint_candidates(request):
            payload={'obstacles':hard,'pipes':[variant]}
            payload,world_points=_checkpoint_frame(payload)
            run=subprocess.run([node,str(runner)],input=json.dumps(payload),capture_output=True,text=True,encoding='utf8',timeout=45)
            if run.returncode:raise RuntimeError('libavoid failed: '+run.stderr[-2000:])
            answer=json.loads(run.stdout)
            if set(answer['paths'])!={connection['id']}:raise RuntimeError('libavoid omitted/added a connection')
            raw=world_points(answer['paths'][connection['id']])
            if len(raw)<2 and not request.get('checkpoints'):
                raise RuntimeError('libavoid returned an empty route: '+connection['id'])
            pipe=copy.deepcopy(connection);pipe['points']=[]
            try:
                if len(raw)<2:raise GuardError('missing_path','libavoid returned fewer than two route points',pipe=connection['id'])
                pipe['points']=canonical([ports[0]]+raw+[ports[1]])
                pipe=simplify(result,pipe)
                commit_pipe(result,pipe)
            except GuardError as error:
                last_error=error
                rejected_directions.append({'directions':variant.get('checkpoint_directions'),'error':error.to_dict()})
                continue
            if state_cache is not None:state_cache[key]=copy.deepcopy(result['pipes'])
            if request.get('checkpoints'):
                checkpoint_search.append({'pipe':connection['id'],'attempts':len(rejected_directions)+1,
                                          'selected_directions':variant.get('checkpoint_directions'),
                                          'candidate_frame':'rigid source-axis +x; world guard unchanged',
                                          'rejected_candidates':rejected_directions,'complete_search':False})
            break
        else:
            error=last_error
            if request.get('checkpoints'):error.checkpoint_rejected_candidates=rejected_directions
            # Diagnostic search context only: the failed candidate is never
            # committed. The independent gate remains the acceptance authority.
            error.accepted_prefix=[p['id'] for p in result['pipes']]
            line=LineString(pipe['points'])
            gap=params['pipe_clearance']+params['linear_tolerance']*20
            error.conflicting_pipes=[p['id'] for p in result['pipes']
                                     if line.distance(LineString(p['points']))<=gap]
            raise error
    verify_simplified(result)
    result['routing']={'engine':answer['router'],'version':answer['version'],'fallback':False,
                       'independent_guard':True,'accepted_pipe_count':len(result['pipes'])}
    if checkpoint_search:result['routing']['checkpoint_search']=checkpoint_search
    return result

def route_scene(scene,connections,runtime=None,*,max_order_attempts=96):
    """Try bounded routing orders; reject every colliding candidate immediately.
    Previously accepted routes in an attempt remain hard obstacles. An attempt
    works on a private copy and is never exported when another edge fails.
    """
    import itertools,heapq
    connections=list(connections)
    validate_scene(scene)
    if len({c['id'] for c in connections})!=len(connections):raise GuardError('duplicate_pipe','duplicate connection ID')
    known={(e['id'],p['id']) for e in scene['equipment'] for p in e['ports']}
    used={}
    existing={p['id'] for p in scene['pipes']}
    for c in list(scene['pipes'])+connections:
        validate_checkpoints(c,scene['parameters']['linear_tolerance'])
        if c in connections and c['id'] in existing:raise GuardError('duplicate_pipe','connection duplicates an existing pipe',pipe=c['id'])
        for side in ('source','target'):
            ref=c.get(side,{})
            endpoint=(ref.get('equipment'),ref.get('port'))
            if endpoint not in known:raise GuardError('unknown_port',f'{side} requires a declared equipment port',pipe=c['id'])
            if endpoint in used:raise GuardError('unsupported_shared_port',f'port {endpoint[0]}.{endpoint[1]} is reused by {used[endpoint]}; explicit junction support is required',pipe=c['id'])
            used[endpoint]=c['id']
    if not isinstance(max_order_attempts,int) or isinstance(max_order_attempts,bool) or not 1<=max_order_attempts<=512:
        raise ValueError('max_order_attempts must be an integer from 1 to 512')
    by_id={c['id']:c for c in connections}
    original=tuple(by_id);queue=[];queued=set();counter=0
    def enqueue(order,progress,priority):
        nonlocal counter
        order=tuple(order)
        if order in queued:return
        queued.add(order);counter+=1
        heapq.heappush(queue,(-progress,priority,counter,order))
    # Evaluate both coarse directions before a local reorder can monopolize
    # the bounded search. Their failures seed independent conflict repairs.
    enqueue(original,len(connections)+2,0)
    enqueue(reversed(original),len(connections)+1,4)
    # Preserve exhaustive behavior for the small, inexpensive case.
    if len(connections)<=4:
        for order in itertools.permutations(original):enqueue(order,0,5)
    rejected=[];state_cache={}
    while queue and len(rejected)<max_order_attempts:
        _,_,_,ids=heapq.heappop(queue)
        order=[by_id[k] for k in ids]
        try:
            result=_route_order(scene,order,runtime,state_cache=state_cache)
            result['routing']['attempts']=len(rejected)+1
            result['routing']['rejected_candidates']=rejected
            result['routing']['accepted_order']=[c['id'] for c in order]
            result['routing']['order_search']={'method':'bounded conflict-priority reorder','limit':max_order_attempts,'queued':len(queued),'cached_prefixes':len(state_cache),'complete_search':False}
            # Stable declaration order in the final CAD/manifest.
            ids={c['id']:i for i,c in enumerate(connections)}
            result['pipes'].sort(key=lambda p:ids.get(p['id'],-1))
            return result
        except GuardError as error:
            prefix=getattr(error,'accepted_prefix',[])
            conflicts=getattr(error,'conflicting_pipes',[])
            rejected.append({'order':list(ids),'error':error.to_dict(),'accepted_prefix':prefix,'conflicting_pipes':conflicts})
            if hasattr(error,'checkpoint_rejected_candidates'):
                rejected[-1]['checkpoint_candidates']=error.checkpoint_rejected_candidates
            if error.pipe in ids:
                failed=ids.index(error.pipe)
                # Promote the blocked edge ahead of actual intersecting routes
                # first, then earlier accepted edges. A long valid prefix gets
                # priority, but every attempt rebuilds and checks its own scene.
                targets=[ids.index(k) for k in reversed(conflicts) if k in ids and ids.index(k)<failed]
                targets+=list(range(failed-1,-1,-1))
                for rank,pos in enumerate(dict.fromkeys(targets)):
                    moved=list(ids);item=moved.pop(failed);moved.insert(pos,item)
                    enqueue(moved,len(prefix),rank)
                    swapped=list(ids);swapped[pos],swapped[failed]=swapped[failed],swapped[pos]
                    enqueue(swapped,len(prefix),rank+1)
    raise GuardError('no_verified_route','no verified route in bounded search: '+json.dumps(
        {'attempts':len(rejected),'limit':max_order_attempts,'budget_exhausted':bool(queue),
         'rejected_candidates':rejected},ensure_ascii=False))
