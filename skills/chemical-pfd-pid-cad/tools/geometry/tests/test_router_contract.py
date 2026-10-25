import copy,json,os,unittest
from pathlib import Path
from pfd_guard import validate_scene,GuardError
from pfd_router import route_scene,canonical,verify_simplified

ROOT=Path(__file__).resolve().parents[1]

class Router(unittest.TestCase):
    def payload(self):return json.loads((ROOT/'examples/synthetic-route.json').read_text('utf8'))

    def test_no_runtime_fallback(self):
        p=self.payload()
        with self.assertRaisesRegex(RuntimeError,'runtime missing'):route_scene(p['scene'],p['connections'],runtime=ROOT/'nonexistent-runtime')

    def test_canonical_does_not_hide_reversal(self):
        self.assertEqual(canonical([[0,0],[1,0],[2,0]]),[[0,0],[2,0]])
        self.assertEqual(canonical([[0,0],[1,0],[0,0]]),[[0,0],[1,0],[0,0]])

    @unittest.skipUnless(os.environ.get('PFD_TEST_RUNTIME'),'Explicit separately installed optional libavoid runtime required')
    def test_real_router_and_rotated_translated_scene(self):
        p=self.payload();runtime=Path(os.environ['PFD_TEST_RUNTIME'])
        for rotated in (False,True):
            scene=copy.deepcopy(p['scene'])
            if rotated:
                def point(q):return [100-q[1],200+q[0]]
                for e in scene['equipment']:
                    e['polygon']=[point(q) for q in e['polygon']]
                    for port in e['ports']:
                        port['point']=point(port['point']);x,y=port['outward'];port['outward']=[-y,x]
            out=route_scene(scene,p['connections'],runtime=runtime)
            self.assertEqual(validate_scene(out)['pipe_count'],1)
            self.assertGreater(len(out['pipes'][0]['points']),2)
            self.assertEqual(verify_simplified(out)['redundant_routes'],0)

if __name__=='__main__':unittest.main()
