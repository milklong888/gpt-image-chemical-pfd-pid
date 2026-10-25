import importlib.util
import tempfile
import unittest
from pathlib import Path
import ezdxf

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
dim=load('public_dimension_audit',ROOT/'skills/chemical-pfd-pid-cad/tools/dimensions/dimension_audit.py')
installer=load('public_skill_installer',ROOT/'scripts/install_skills.py')

class DimensionAndInstallTests(unittest.TestCase):
    def test_native_dimension_measurement_and_override_remain_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'original-synthetic.dxf'
            doc=ezdxf.new('R2010');msp=doc.modelspace()
            obj=msp.add_linear_dim(base=(0,10),p1=(0,0),p2=(720,0),text='TRAINING 999')
            obj.render();doc.saveas(path);before=path.read_bytes()
            report=dim.audit_file(path)
            self.assertEqual(path.read_bytes(),before)
            self.assertTrue(report['read_only_input_hash_unchanged'])
            row=report['dimensions'][0]
            self.assertEqual(row['raw_text'],'TRAINING 999')
            self.assertAlmostEqual(row['get_measurement'],720)
            self.assertIn('visual', ' '.join(report['boundaries']).lower())

    def test_exploded_lines_not_accepted_as_native_dimensions(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'lines-only.dxf';doc=ezdxf.new();doc.modelspace().add_line((0,0),(20,0));doc.saveas(path)
            report=dim.audit_file(path)
            self.assertEqual(report['summary']['dimension_count'],0)
            self.assertIn('NO_NATIVE_DIMENSIONS',report['summary']['findings_by_code'])

    def test_installer_preflights_all_targets_before_any_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'skills';dest.mkdir()
            target=dest/'chemical-pid-drawing';target.mkdir();marker=target/'user.txt';marker.write_text('keep',encoding='utf8')
            with self.assertRaises(FileExistsError):installer.install(dest)
            self.assertEqual(marker.read_text('utf8'),'keep')
            self.assertEqual(list(dest.iterdir()),[target])

    def test_install_five_skills_to_explicit_new_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            result=installer.install(Path(folder)/'skills')
            self.assertEqual(len(result),5)
            self.assertTrue(all((Path(p)/'SKILL.md').is_file() for p in result))

if __name__=='__main__':unittest.main()
