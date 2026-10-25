import unittest,tempfile,math
from pathlib import Path
import ezdxf
from pfd_source_geometry import signature,equal_geometry
from pfd_guard import GuardError

ROOT=Path(__file__).resolve().parents[1]

class Snapshot(unittest.TestCase):
    def test_actual_saved_primitive_roundtrip(self):
        doc=ezdxf.new();m=doc.modelspace();m.add_line((0,0),(10,2));m.add_circle((20,2),3);m.add_arc((30,0),4,20,240);m.add_ellipse((50,0),(5,2),.4);m.add_lwpolyline([(0,20,3,0,0),(10,20,0,0,0)]);m.add_spline([(0,30),(5,35),(10,30)])
        before=[signature(e) for e in m];out=ROOT/'validation-output';out.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=out) as td:
            p=Path(td)/'roundtrip.dxf';doc.saveas(p);actual=[signature(e) for e in ezdxf.readfile(p).modelspace()]
        self.assertTrue(equal_geometry(before,actual,1e-8))

    def test_actual_arc_direction_change_detected(self):
        doc=ezdxf.new();e=doc.modelspace().add_arc((0,0),3,10,80);old=signature(e);e.dxf.end_angle=90
        self.assertFalse(equal_geometry(old,signature(e),1e-6))

    def test_nonfinite_never_equal(self):self.assertFalse(equal_geometry(float('nan'),float('nan'),1))

    def test_unsupported_text_fails_closed(self):
        d=ezdxf.new();e=d.modelspace().add_text('synthetic')
        with self.assertRaises(GuardError):signature(e)

if __name__=='__main__':unittest.main()
