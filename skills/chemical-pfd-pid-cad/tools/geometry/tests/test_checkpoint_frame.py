"""Bounded normalization and retry regressions; no CAD calls."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import pfd_router as R
import pfd_guard as G
from test_checkpoints import scene,pipe


class CheckpointFrameTests(unittest.TestCase):
    def test_no_checkpoints_returns_identical_payload(self):
        payload={'obstacles':[],'pipes':[{'id':'P1'}]}
        result,inverse=R._checkpoint_frame(payload)
        self.assertIs(result,payload)
        points=[[1,2],[3,4]]
        self.assertIs(inverse(points),points)

    def test_rigid_frame_all_geometry_and_inverse_in_four_directions(self):
        for turn,(sx,sy) in enumerate(((1,0),(0,1),(-1,0),(0,-1))):
            with self.subTest(turn=turn):
                payload={'obstacles':[{'id':'wall','points':[[9,18],[12,18],[12,22],[9,22]]}],
                         'pipes':[{'id':'P1','start':[10,20],'end':[10+8*sx,20+8*sy],
                                   'start_outward':[sx,sy],'end_outward':[-sx,-sy],
                                   'checkpoints':[[10+4*sx-3*sy,20+4*sy+3*sx]],'linear_tolerance':1e-7}]}
                before=copy.deepcopy(payload)
                result,inverse=R._checkpoint_frame(payload)
                actual=result['pipes'][0]
                self.assertEqual(actual['start'],[0,0])
                self.assertEqual(actual['end'],[8,0])
                self.assertEqual(actual['start_outward'],[1,0])
                self.assertEqual(actual['end_outward'],[-1,0])
                self.assertEqual(actual['checkpoints'],[[4,3]])
                self.assertEqual(inverse(result['obstacles'][0]['points']),payload['obstacles'][0]['points'])
                self.assertEqual(inverse(actual['checkpoints']),payload['pipes'][0]['checkpoints'])
                self.assertEqual(actual['linear_tolerance'],1e-7)
                self.assertEqual(payload,before)

    def fake_runtime(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);(root/'route.mjs').write_text('// never executed',encoding='utf8')
        return root

    def test_empty_direction_candidate_is_rejected_then_next_whole_route_checked(self):
        p=pipe();del p['points'];p['checkpoints']=[[20,15]]
        original=copy.deepcopy(p);calls=[]
        def reply(command,**kwargs):
            request=json.loads(kwargs['input'])['pipes'][0];calls.append(request)
            if len(calls)==1:points=[]
            else:
                cp=request['checkpoints'][0];end=request['end']
                points=[request['start'],[cp[0],0],cp,[end[0],cp[1]],end]
            return subprocess.CompletedProcess(command,0,json.dumps({'router':'mock','version':'test','paths':{'P1':points}}),'')
        with patch.object(R.shutil,'which',return_value='mock-node'),patch.object(R.subprocess,'run',side_effect=reply):
            result=R.route_scene(scene(),[p],runtime=self.fake_runtime(),max_order_attempts=1)
        self.assertEqual(len(calls),2)
        self.assertEqual(result['pipes'][0]['checkpoints'],original['checkpoints'])
        self.assertTrue(G.validate_scene(result)['ok'])
        rejected=result['routing']['checkpoint_search'][0]['rejected_candidates']
        self.assertEqual(rejected[0]['error']['code'],'missing_path')
        self.assertEqual(p,original)

    def test_all_empty_candidates_fail_closed_without_uninitialized_diagnostics(self):
        s=scene();before=copy.deepcopy(s);p=pipe();del p['points'];p['checkpoints']=[[20,15]]
        reply=subprocess.CompletedProcess([],0,json.dumps({'router':'mock','version':'test','paths':{'P1':[]}}),'')
        with patch.object(R.shutil,'which',return_value='mock-node'),patch.object(R.subprocess,'run',return_value=reply) as run:
            with self.assertRaises(G.GuardError) as caught:
                R.route_scene(s,[p],runtime=self.fake_runtime(),max_order_attempts=1)
        self.assertEqual(run.call_count,17)
        self.assertEqual(caught.exception.code,'no_verified_route')
        self.assertIn('missing_path',str(caught.exception))
        self.assertEqual(s,before)


if __name__=='__main__':unittest.main()
