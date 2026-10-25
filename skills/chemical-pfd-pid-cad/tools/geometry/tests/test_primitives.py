import json,unittest,tempfile
from pathlib import Path
import ezdxf
from pfd_primitives import Jump,add_jump,audit_jump as _audit_jump,arrows_to_front,audit_arrow_order,draw_order
from audit_lineweight_continuity import effective_lineweight,WidthError

ROOT=Path(__file__).resolve().parents[1]
def audit_jump(*args,**kwargs):return _audit_jump(*args,paper_mm_per_unit=1.,**kwargs)

class Primitives(unittest.TestCase):
    def make(self,side=1):
        doc=ezdxf.new('R2018');s=Jump((0.,0.),3.,-20.,20.,side)
        hs=add_jump(doc,s);under=doc.modelspace().add_line((-20,0),(20,0),dxfattribs={'layer':'PROCESS','lineweight':80})
        return doc,s,hs,under.dxf.handle

    def saved(self,doc):
        out=ROOT/'validation-output';out.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=out) as td:
            p=Path(td)/'actual.dxf';doc.saveas(p);return ezdxf.readfile(p)

    def test_saved_left_and_right_tangent_jumps(self):
        for side in (-1,1):
            d,s,h,u=self.make(side);self.assertTrue(audit_jump(self.saved(d),s,h,u)['ok'])

    def test_deleted_arc_rejected(self):
        d,s,h,u=self.make();d.modelspace().delete_entity(d.entitydb[h['arcs'][1]])
        with self.assertRaisesRegex(ValueError,'missing'):audit_jump(self.saved(d),s,h,u)

    def test_wrong_side_rejected(self):
        d,s,h,u=self.make()
        with self.assertRaisesRegex(ValueError,'geometry'):audit_jump(self.saved(d),Jump(s.center,s.radius,s.lower_y,s.upper_y,-1),h,u)

    def test_break_endpoint_rejected(self):
        d,s,h,u=self.make();e=d.entitydb[h['lines'][0]];e.dxf.end=(0,-6.01)
        with self.assertRaisesRegex(ValueError,'endpoint'):audit_jump(self.saved(d),s,h,u)

    def test_changed_lineweight_rejected(self):
        d,s,h,u=self.make();d.entitydb[h['arcs'][0]].dxf.lineweight=25
        with self.assertRaisesRegex(ValueError,'style'):audit_jump(self.saved(d),s,h,u)

    def test_true_branch_protected(self):
        d,s,h,u=self.make()
        with self.assertRaisesRegex(ValueError,'protected'):audit_jump(self.saved(d),s,h,u,protected_points=[(0,5)])

    def test_arrow_label_body_collision_rejected(self):
        d,s,h,u=self.make()
        for context in [{'label_boxes':[(5,-1,7,1)]},{'equipment_polygons':[[(5,-1),(7,-1),(7,1),(5,1)]]},{'arrow_polygons':[[(5,-1),(7,0),(5,1)]]}]:
            with self.assertRaises(ValueError):audit_jump(self.saved(d),s,h,u,**context)

    def test_false_junction_dot_rejected(self):
        d,s,h,u=self.make();d.modelspace().add_circle((6,0),.3)
        with self.assertRaisesRegex(ValueError,'junction'):audit_jump(self.saved(d),s,h,u)

    def test_broken_under_route_rejected(self):
        d,s,h,u=self.make();d.entitydb[u].dxf.end=(-2,0)
        with self.assertRaisesRegex(ValueError,'under-line'):audit_jump(self.saved(d),s,h,u)

    def arrows(self):
        d=ezdxf.new();m=d.modelspace();p=m.add_lwpolyline([(10,-10,3,0,0),(15,-10,0,0,0)]);q=m.add_solid([(30,0),(25,2),(25,-2)])
        other=m.add_solid([(50,0),(52,0),(52,2),(50,2)]);m.add_line((0,0),(50,0))
        return d,[p.dxf.handle,q.dxf.handle],other.dxf.handle

    def test_only_explicit_arrows_raised_and_all_geometry_preserved(self):
        d,hs,other=self.arrows();before={e.dxf.handle:str(e.dxfattribs()) for e in d.modelspace()};order=arrows_to_front(d,hs);r=self.saved(d)
        self.assertTrue(audit_arrow_order(r,hs)['ok']);self.assertNotIn(other,order['selected'])
        self.assertEqual(before,{e.dxf.handle:str(e.dxfattribs()) for e in r.modelspace()})

    def test_source_arrow_behind_rejected(self):
        d,hs,other=self.arrows();arrows_to_front(d,hs);mp=dict(d.modelspace().get_redraw_order());mp[hs[0]],mp[other]=mp[other],mp[hs[0]];d.modelspace().set_redraw_order(mp)
        with self.assertRaisesRegex(ValueError,'top'):audit_arrow_order(self.saved(d),hs)

    def test_plot_sort_and_label_collision_rejected(self):
        d,hs,_=self.arrows();arrows_to_front(d,hs)
        with self.assertRaisesRegex(ValueError,'label'):audit_arrow_order(self.saved(d),hs,label_boxes=[(11,-11,13,-9)])
        d.header['$SORTENTS']=0
        with self.assertRaisesRegex(ValueError,'top'):audit_arrow_order(self.saved(d),hs)

    def test_quad_is_not_implicitly_an_arrow(self):
        d,hs,other=self.arrows()
        with self.assertRaisesRegex(ValueError,'triangular'):arrows_to_front(d,[other])

    def test_lineweight_byblock_and_default_require_context(self):
        d=ezdxf.new();e=d.modelspace().add_line((0,0),(1,0),dxfattribs={'lineweight':-2})
        with self.assertRaises(WidthError):effective_lineweight(d,e)
        e.dxf.lineweight=-3
        with self.assertRaises(WidthError):effective_lineweight(d,e)
        self.assertEqual(effective_lineweight(d,e,default_lineweight=50)['mm'],.5)

if __name__=='__main__':unittest.main()
