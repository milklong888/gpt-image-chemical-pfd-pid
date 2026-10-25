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
// Absolute offsets may lie outside the buffered shape: they retain the exact
// precomputed lead point, without creating additional artificial obstacles.
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
  const owner=shapes.get(pipe[field+'_owner']);
  if(!owner)throw new Error('endpoint requires a registered owner shape');
  const p=point(pipe[field]),mask=directionMask(pipe[field+'_outward']);
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
    pipe.checkpoints.forEach(p=>checks.push_back(new A.Checkpoint(point(p))));
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
