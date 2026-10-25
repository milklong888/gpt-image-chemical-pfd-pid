"""Static launch-gate checks only. This module cannot launch AutoCAD."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'))
from emit_script import script

class NativeGate(unittest.TestCase):
    def test_reporterror_readback_precedes_load(self):
        text=script('example-tool.dll')
        self.assertLess(text.index('REPORTERROR'),text.index('_.NETLOAD'))
        self.assertIn('(equal PFD_REPORT_READ 0)',text)
        self.assertIn('PFD_NATIVE_GATE_FAIL_NO_NETLOAD',text)

    def test_security_settings_never_changed(self):
        text=script('example-tool.dll')
        for key in ('SECURELOAD','TRUSTEDPATHS','PROJECTAWARE'):
            self.assertIn('(getvar "'+key+'")',text)
            self.assertNotIn('(setvar "'+key+'"',text)
        self.assertIn('findtrustedfile',text)

    def test_lisp_parentheses_and_strings_balanced(self):
        text=script('example tool.dll');depth=0;quoted=False;escape=False
        for c in text:
            if quoted:
                if escape:escape=False
                elif c=='\\':escape=True
                elif c=='"':quoted=False
            elif c=='"':quoted=True
            elif c=='(':depth+=1
            elif c==')':depth-=1;self.assertGreaterEqual(depth,0)
        self.assertFalse(quoted);self.assertEqual(depth,0)

if __name__=='__main__':unittest.main()
