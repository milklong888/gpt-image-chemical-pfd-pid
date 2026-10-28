// Directed escape endpoints; the independent Python gate validates all paths.
import fs from 'node:fs';
import {AvoidLib} from 'libavoid-js';
const request=JSON.parse(fs.readFileSync(0,'utf8'));
await AvoidLib.load();
const A=AvoidLib.getInstance();
const router=new A.Router(A.RouterFlag.OrthogonalRouting.value);
router.setRoutingParameter(A.RoutingParameter.segmentPenalty,30);
router.setRoutingParameter(A.RoutingParameter.crossingPenalty,100);
router.setRoutingParameter(A.RoutingParameter.shapeBufferDistance,0);
const point=p=>new A.Point(p[0],-p[1]);
const refs=[];
const shapes=new Map();
for(const obstacle of request.obstacles){
  const polygon=new A.Polygon(obstacle.points.length);
  obstacle.points.forEach((p,i)=>polygon.setPoint(i,point(p)));
  const shape=new A.ShapeRef(router,polygon);
  refs.push(shape);
  shapes.set(obstacle.id,{shape,polygon,
    minX:Math.min(...obstacle.points.map(p=>p[0])),
    minY:Math.min(...obstacle.points.map(p=>-p[1]))});
}
// libavoid-js 0.5.0-beta.5 does not bind ConnEnd(Point, directions).
// Its real, supported directional API is ShapeConnectionPin + ConnEnd(shape,id).
// Without checkpoints, preserve the original absolute-offset owner pins.
// With checkpoints, the branch below uses small candidate-only anchor shapes
// to retain exact lead tips with pins on an actual boundary; the independent
// world-space guard remains responsible for the unchanged physical contract.
let pinClass=0;
const directionMask=v=>{
  if(!Array.isArray(v)||v.length!==2||v.some(x=>typeof x!=='number'||!Number.isFinite(x)))
    throw new Error('endpoint outward direction must be a finite vector');
  const n=Math.hypot(...v);
  if(n===0)throw new Error('endpoint outward direction must be nonzero');
  const x=v[0]/n,y=v[1]/n;
  // CAD y increases upward; point() reflects it for libavoid's downward y.
  // ConnDirUp=1, Down=2, Left=4, Right=8 (libavoid/connend.h).
  if(Math.abs(y)<=1e-9)return x<0?4:8;
  if(Math.abs(x)<=1e-9)return y>0?1:2;
  throw new Error('orthogonal endpoint direction must be axis-aligned');
};
const endpoint=(pipe,field)=>{
  let owner=shapes.get(pipe[field+'_owner']);
  if(!owner)throw new Error('endpoint requires a registered owner shape');
  const p=point(pipe[field]),mask=directionMask(pipe[field+'_outward']);
  if(pipe.checkpoints?.length){
    // Candidate-generation anchor only, not a new engineering port/junction.
    // A pin outside its owner polygon has a correct reported position but can
    // route back through that polygon boundary in libavoid-js 0.5.0-beta.5.
    // Keep the original equipment obstacle; place this directional pin exactly
    // on a tiny anchor boundary at the unmodified requested lead tip instead.
    const tol=pipe.linear_tolerance;
    if(typeof tol!=='number'||!Number.isFinite(tol)||tol<=0)throw new Error('checkpoint routing requires positive linear_tolerance');
    const [cx,cy]=pipe[field+'_outward'],n=Math.hypot(cx,cy),dx=cx/n,dy=-cy/n;
    const width=tol*10,half=width/2,tx=-dy,ty=dx;
    const coords=[[p.x+tx*half,p.y+ty*half],[p.x-tx*half,p.y-ty*half],
      [p.x-dx*width-tx*half,p.y-dy*width-ty*half],[p.x-dx*width+tx*half,p.y-dy*width+ty*half]];
    const polygon=new A.Polygon(4);
    coords.forEach((q,i)=>polygon.setPoint(i,new A.Point(q[0],q[1])));
    const shape=new A.ShapeRef(router,polygon);
    refs.push(polygon,shape);
    owner={shape,polygon,minX:Math.min(...coords.map(q=>q[0])),minY:Math.min(...coords.map(q=>q[1]))};
  }
  const id=++pinClass;
  const pin=new A.ShapeConnectionPin(owner.shape,id,p.x-owner.minX,p.y-owner.minY,false,0,mask);
  pin.setExclusive(true);
  const actual=pin.position(owner.polygon);
  if(Math.hypot(actual.x-p.x,actual.y-p.y)>1e-7||pin.directions()!==mask)
    throw new Error('libavoid directional pin differs from requested endpoint');
  refs.push(pin);
  return new A.ConnEnd(owner.shape,id);
};
const connectors=[];
for(const pipe of request.pipes){
  const connector=new A.ConnRef(router,endpoint(pipe,'start'),endpoint(pipe,'end'));
  connector.setRoutingType(A.ConnType.ConnType_Orthogonal);
  connector.setHateCrossings(true);
  if(pipe.checkpoints?.length){
    const checks=new A.CheckpointVector();
    if(pipe.checkpoint_directions!==undefined && (!Array.isArray(pipe.checkpoint_directions)||pipe.checkpoint_directions.length!==pipe.checkpoints.length))
      throw new Error('checkpoint direction count mismatch');
    pipe.checkpoints.forEach((p,i)=>{
      const dirs=pipe.checkpoint_directions?.[i];
      if(dirs!==undefined && (!Array.isArray(dirs)||dirs.length!==2||dirs.some(d=>![1,2,4,8].includes(d))))
        throw new Error('invalid checkpoint direction masks');
      checks.push_back(dirs===undefined?new A.Checkpoint(point(p)):new A.Checkpoint(point(p),dirs[0],dirs[1]));
    });
    connector.setRoutingCheckpoints(checks);
  }
  connectors.push([pipe.id,connector]);
}
router.processTransaction();
const paths={};
for(const [id,c] of connectors){
  const r=c.displayRoute(),pts=[];
  for(let i=0;i<r.size();i++){const p=r.at(i);pts.push([p.x,-p.y]);}
  paths[id]=pts;
}
process.stdout.write(JSON.stringify({router:'libavoid-js',version:'0.5.0-beta.5',paths}));
router.delete();
