"""Offline checkpoint contract tests; separate optional real-runtime cases.

Guard/simplify tests use actual candidate Python and Shapely. Transport tests
mock only Node subprocess output; they are not real libavoid runtime tests.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
import pfd_guard as G
import pfd_router as R


def scene():
    return {'schema': 'pfd-guard/v1', 'parameters': {
        'linear_tolerance': 1e-7, 'angular_tolerance_deg': .01,
        'equipment_clearance': 2., 'pipe_clearance': 1., 'minimum_lead': 2.},
        'equipment': [
            {'id': 'A', 'polygon': [[0,0],[10,0],[10,10],[0,10],[0,0]],
             'ports': [{'id':'out','point':[10,5],'outward':[1,0],'lead':2.}]},
            {'id': 'B', 'polygon': [[30,0],[40,0],[40,10],[30,10],[30,0]],
             'ports': [{'id':'in','point':[30,5],'outward':[-1,0],'lead':2.}]}
        ], 'pipes': []}


def pipe():
    return {'id':'P1', 'source':{'equipment':'A','port':'out'},
            'target':{'equipment':'B','port':'in'}, 'points':[[10,5],[30,5]]}


def detour():
    p = pipe()
    p['points'] = [[10,5],[15,5],[15,15],[25,15],[25,5],[30,5]]
    p['checkpoints'] = [[17,15],[23,15]]
    return p


class CheckpointGuardTests(unittest.TestCase):
    def rejects(self, code, candidate, context=None):
        with self.assertRaises(G.GuardError) as caught:
            G.validate_pipe(context if context is not None else scene(), candidate)
        self.assertEqual(caught.exception.code, code)

    def test_old_no_checkpoint_and_explicit_empty_list(self):
        self.assertTrue(G.validate_pipe(scene(), pipe())['ok'])
        p = pipe(); p['checkpoints'] = []
        self.assertTrue(G.validate_pipe(scene(), p)['ok'])

    def test_ordered_points_inside_one_segment_are_valid(self):
        p = pipe(); p['checkpoints'] = [[15,5],[25,5]]
        self.assertTrue(G.validate_pipe(scene(), p)['ok'])
        self.assertEqual(p['points'], [[10,5],[30,5]])

    def test_source_and_target_endpoints_are_valid_ordered_checkpoints(self):
        p = pipe(); p['checkpoints'] = [[10,5],[20,5],[30,5]]
        self.assertTrue(G.validate_pipe(scene(), p)['ok'])

    def test_direct_guard_rejects_missing_checkpoint_without_router(self):
        p = pipe(); p['checkpoints'] = [[20,15]]
        self.rejects('checkpoint_missing', p)

    def test_direct_guard_rejects_reversed_checkpoint_order(self):
        p = pipe(); p['checkpoints'] = [[25,5],[15,5]]
        self.rejects('checkpoint_order', p)

    def test_only_existing_linear_tolerance_is_used_for_hits(self):
        p = pipe(); p['checkpoints'] = [[20,5 + 5e-8]]
        self.assertTrue(G.validate_pipe(scene(), p)['ok'])
        p['checkpoints'] = [[20,5 + 2e-7]]
        self.rejects('checkpoint_missing', p)

    def test_order_across_segments_and_inside_segments(self):
        p = detour()
        self.assertTrue(G.validate_pipe(scene(), p)['ok'])
        p['checkpoints'] = p['checkpoints'][::-1]
        self.rejects('checkpoint_order', p)

    def test_malformed_list_points_bool_and_nonfinite_rejected(self):
        bad = [(None, 'invalid_contract'), ({'x':20,'y':5}, 'invalid_contract'),
               ([[20]], 'invalid_point'), ([[20,5,0]], 'invalid_point'),
               ([{'x':20,'y':5}], 'invalid_point'), ([[True,5]], 'invalid_number'),
               ([[20,False]], 'invalid_number'), ([[float('nan'),5]], 'invalid_number'),
               ([[float('inf'),5]], 'invalid_number'), ([[20,float('-inf')]], 'invalid_number'),
               ([['20',5]], 'invalid_number'), ([[10**1000,5]], 'invalid_number')]
        for checkpoints, code in bad:
            with self.subTest(checkpoints=checkpoints):
                p = pipe(); p['checkpoints'] = checkpoints
                self.rejects(code, p)

    def test_duplicate_nonadjacent_and_tolerance_duplicate_rejected(self):
        for points in ([[15,5],[15,5]], [[15,5],[25,5],[15,5]],
                       [[15,5],[15 + 5e-8,5]]):
            with self.subTest(points=points):
                p = pipe(); p['checkpoints'] = points
                self.rejects('duplicate_checkpoint', p)

    def test_checkpoint_does_not_exempt_equipment_collision(self):
        s = scene()
        s['equipment'].append({'id':'C', 'polygon':[[18,2],[22,2],[22,8],[18,8],[18,2]], 'ports':[]})
        p = pipe(); p['checkpoints'] = [[20,5]]
        self.rejects('equipment_contact', p, s)

    def test_checkpoint_does_not_exempt_clearance(self):
        s = scene()
        s['equipment'].append({'id':'C', 'polygon':[[18,6],[22,6],[22,9],[18,9],[18,6]], 'ports':[]})
        p = pipe(); p['checkpoints'] = [[20,5]]
        self.rejects('equipment_clearance', p, s)

    def test_checkpoint_does_not_allow_crossing_another_pipe(self):
        s = scene()
        s['equipment'].extend([
            {'id':'C','polygon':[[18,-20],[22,-20],[22,-10],[18,-10],[18,-20]],
             'ports':[{'id':'out','point':[20,-10],'outward':[0,1],'lead':2}]},
            {'id':'D','polygon':[[18,20],[22,20],[22,30],[18,30],[18,20]],
             'ports':[{'id':'in','point':[20,20],'outward':[0,-1],'lead':2}]}])
        s['pipes'] = [{'id':'vertical','source':{'equipment':'C','port':'out'},
                       'target':{'equipment':'D','port':'in'},'points':[[20,-10],[20,20]]}]
        p = pipe(); p['checkpoints'] = [[20,5]]
        self.rejects('pipe_contact', p, s)

    def test_failed_checkpoint_commit_is_atomic(self):
        s = scene(); before = copy.deepcopy(s)
        p = pipe(); p['checkpoints'] = [[20,15]]
        with self.assertRaises(G.GuardError):
            G.commit_pipe(s, p)
        self.assertEqual(s, before)

    def test_simplify_cannot_remove_required_detour(self):
        p = detour(); original = copy.deepcopy(p)
        simplified = R.simplify(scene(), p)
        self.assertEqual(simplified['checkpoints'], original['checkpoints'])
        self.assertTrue(G.validate_pipe(scene(), simplified)['ok'])
        self.assertGreater(R.cost(simplified['points'])[1], 20)
        self.assertEqual(p, original)

    def test_collinear_vertex_can_disappear_without_losing_constraint(self):
        p = pipe(); p['points'] = [[10,5],[20,5],[30,5]]; p['checkpoints'] = [[20,5]]
        simplified = R.simplify(scene(), p)
        self.assertEqual(simplified['points'], [[10,5],[30,5]])
        self.assertEqual(simplified['checkpoints'], [[20,5]])
        self.assertTrue(G.validate_pipe(scene(), simplified)['ok'])

    def test_no_checkpoint_legacy_detour_still_simplifies(self):
        p = detour(); del p['checkpoints']
        self.assertEqual(R.simplify(scene(), p)['points'], [[10,5],[30,5]])

    def test_local_simplification_certificate_respects_checkpoints(self):
        s = scene(); s['pipes'] = [R.simplify(scene(), detour())]
        self.assertEqual(R.verify_simplified(s)['redundant_routes'], 0)

    def test_registered_scene_independently_rechecks_checkpoint_order(self):
        s = scene(); p = pipe(); p['checkpoints'] = [[25,5],[15,5]]; s['pipes'] = [p]
        with self.assertRaises(G.GuardError) as caught:
            G.validate_scene(s)
        self.assertEqual(caught.exception.code, 'checkpoint_order')


class CheckpointTransportTests(unittest.TestCase):
    def fake_runtime(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / 'route.mjs').write_text('// transport mock only; never executed', encoding='utf8')
        return root

    def test_python_passes_original_checkpoint_order_to_js_request(self):
        p = detour(); del p['points']; before = copy.deepcopy(p); requests = []
        def reply(command, **kwargs):
            payload = json.loads(kwargs['input']); request = payload['pipes'][0]
            requests.append(request)
            a,b=request['checkpoints']
            points = [request['start'],[a[0]-2,0],[a[0]-2,a[1]],[b[0]+2,b[1]],[b[0]+2,0],request['end']]
            return subprocess.CompletedProcess(command, 0, json.dumps({
                'router':'libavoid-js','version':'0.5.0-beta.5','paths':{'P1':points}}), '')
        with patch.object(R.shutil, 'which', return_value='mock-node'), patch.object(R.subprocess, 'run', side_effect=reply):
            routed = R.route_scene(scene(), [p], runtime=self.fake_runtime(), max_order_attempts=1)
        self.assertEqual(requests[0]['checkpoints'], [[17-12.000004,10],[23-12.000004,10]])
        self.assertEqual(requests[0]['start'], [0,0])
        self.assertEqual(routed['pipes'][0]['checkpoints'], p['checkpoints'])
        self.assertTrue(G.validate_scene(routed)['ok'])
        self.assertEqual(p, before)

    def test_endpoints_and_fixed_lead_checkpoints_are_not_sent_to_middle_router(self):
        p = pipe(); del p['points']
        p['checkpoints'] = [[10,5],[11,5],[20,5],[29,5],[30,5]]
        original = copy.deepcopy(p); requests = []
        def reply(command, **kwargs):
            request = json.loads(kwargs['input'])['pipes'][0]; requests.append(request)
            return subprocess.CompletedProcess(command, 0, json.dumps({
                'router':'mock-fixed-leads','version':'test','paths':{'P1':[request['start'],request['end']]}}), '')
        with patch.object(R.shutil, 'which', return_value='mock-node'), patch.object(R.subprocess, 'run', side_effect=reply):
            routed = R.route_scene(scene(), [p], runtime=self.fake_runtime(), max_order_attempts=1)
        self.assertEqual(requests[0]['checkpoints'], [[20-12.000004,0]])
        self.assertEqual(routed['pipes'][0]['checkpoints'], original['checkpoints'])
        self.assertTrue(G.validate_scene(routed)['ok'])
        self.assertEqual(p, original)

    def test_fixed_prefix_suffix_and_phase_reversals_rejected_before_js(self):
        for checkpoints in ([[11,5],[10,5]], [[30,5],[29,5]],
                            [[20,5],[11,5]], [[29,5],[20,5]], [[29,5],[11,5]]):
            with self.subTest(checkpoints=checkpoints):
                p = pipe(); del p['points']; p['checkpoints'] = checkpoints
                with patch.object(R.shutil, 'which', return_value='mock-node'), patch.object(R.subprocess, 'run') as run:
                    with self.assertRaises(G.GuardError) as caught:
                        R._route_order(scene(), [p], runtime=self.fake_runtime())
                self.assertEqual(caught.exception.code, 'checkpoint_order'); run.assert_not_called()

    def test_checkpoint_hits_on_both_virtual_tips_are_satisfied_by_fixed_leads(self):
        tol = scene()['parameters']['linear_tolerance']
        lead = 2 + tol*40
        p = pipe(); del p['points']; p['checkpoints'] = [[10+lead,5],[30-lead,5]]
        requests = []
        def reply(command, **kwargs):
            request = json.loads(kwargs['input'])['pipes'][0]; requests.append(request)
            return subprocess.CompletedProcess(command, 0, json.dumps({
                'router':'mock-tips','version':'test','paths':{'P1':[request['start'],request['end']]}}), '')
        with patch.object(R.shutil, 'which', return_value='mock-node'), patch.object(R.subprocess, 'run', side_effect=reply):
            routed = R.route_scene(scene(), [p], runtime=self.fake_runtime(), max_order_attempts=1)
        self.assertEqual(requests[0]['checkpoints'], [])
        self.assertEqual(routed['pipes'][0]['checkpoints'], p['checkpoints'])
        self.assertTrue(G.validate_scene(routed)['ok'])

    def test_boundary_tolerance_does_not_hide_or_reorder_full_metadata(self):
        tol = scene()['parameters']['linear_tolerance']; tip = 12 + tol*40
        p = pipe(); del p['points']; p['checkpoints'] = [[tip-.75*tol,5],[tip+.75*tol,5]]
        requests = []
        def reply(command, **kwargs):
            request = json.loads(kwargs['input'])['pipes'][0]; requests.append(request)
            return subprocess.CompletedProcess(command, 0, json.dumps({
                'router':'mock-tip-tolerance','version':'test','paths':{'P1':[request['start'],request['end']]}}), '')
        with patch.object(R.shutil, 'which', return_value='mock-node'), patch.object(R.subprocess, 'run', side_effect=reply):
            routed = R.route_scene(scene(), [p], runtime=self.fake_runtime(), max_order_attempts=1)
        self.assertEqual(requests[0]['checkpoints'], [])
        self.assertEqual(routed['pipes'][0]['checkpoints'], p['checkpoints'])
        self.assertTrue(G.validate_scene(routed)['ok'])
        p['checkpoints'].reverse()
        with patch.object(R.shutil, 'which', return_value='mock-node'), patch.object(R.subprocess, 'run', side_effect=reply):
            with self.assertRaises(G.GuardError) as caught:
                R.route_scene(scene(), [p], runtime=self.fake_runtime(), max_order_attempts=1)
        self.assertEqual(caught.exception.code, 'no_verified_route')
        self.assertIn('checkpoint_order', str(caught.exception))

    def test_off_fixed_lead_point_is_not_silently_dropped(self):
        tol = scene()['parameters']['linear_tolerance']
        checkpoint = [11,5+2*tol]
        self.assertEqual(R._middle_checkpoints([checkpoint],[10,5],[12,5],[28,5],[30,5],tol,'P1'),[checkpoint])

    def test_fixed_lead_checkpoint_still_cannot_exempt_collision(self):
        s = scene()
        s['equipment'].append({'id':'C','polygon':[[10.8,4.9],[11.2,4.9],[11.2,5.1],[10.8,5.1],[10.8,4.9]],'ports':[]})
        p = pipe(); del p['points']; p['checkpoints'] = [[11,5]]
        def reply(command, **kwargs):
            request = json.loads(kwargs['input'])['pipes'][0]
            self.assertEqual(request['checkpoints'], [])
            return subprocess.CompletedProcess(command, 0, json.dumps({
                'router':'mock-fixed-lead-collision','version':'test','paths':{'P1':[request['start'],request['end']]}}), '')
        with patch.object(R.shutil, 'which', return_value='mock-node'), patch.object(R.subprocess, 'run', side_effect=reply):
            with self.assertRaises(G.GuardError) as caught:
                R.route_scene(s, [p], runtime=self.fake_runtime(), max_order_attempts=1)
        self.assertEqual(caught.exception.code, 'no_verified_route')
        self.assertIn('equipment_contact', str(caught.exception))
        self.assertEqual(s['pipes'], [])

    def test_invalid_checkpoint_is_rejected_before_js_execution(self):
        p = pipe(); del p['points']; p['checkpoints'] = [[True,5]]
        with patch.object(R.subprocess, 'run') as run:
            with self.assertRaises(G.GuardError) as caught:
                R.route_scene(scene(), [p], runtime=self.fake_runtime())
        self.assertEqual(caught.exception.code, 'invalid_number'); run.assert_not_called()

    def test_engine_ignoring_checkpoint_stops_without_committing(self):
        s = scene(); before = copy.deepcopy(s)
        p = pipe(); del p['points']; p['checkpoints'] = [[20,15]]
        def reply(command, **kwargs):
            request = json.loads(kwargs['input'])['pipes'][0]
            return subprocess.CompletedProcess(command, 0, json.dumps({
                'router':'mock-ignored-checkpoint','version':'test','paths':{'P1':[request['start'],request['end']]}}), '')
        with patch.object(R.shutil, 'which', return_value='mock-node'), patch.object(R.subprocess, 'run', side_effect=reply):
            with self.assertRaises(G.GuardError) as caught:
                R.route_scene(s, [p], runtime=self.fake_runtime(), max_order_attempts=1)
        self.assertEqual(caught.exception.code, 'no_verified_route')
        self.assertIn('checkpoint_missing', str(caught.exception))
        self.assertEqual(s, before)

    def test_no_checkpoint_request_does_not_add_field(self):
        p = pipe(); del p['points']; requests = []
        def reply(command, **kwargs):
            request = json.loads(kwargs['input'])['pipes'][0]; requests.append(request)
            return subprocess.CompletedProcess(command, 0, json.dumps({
                'router':'mock-legacy','version':'test','paths':{'P1':[request['start'],request['end']]}}), '')
        with patch.object(R.shutil, 'which', return_value='mock-node'), patch.object(R.subprocess, 'run', side_effect=reply):
            R.route_scene(scene(), [p], runtime=self.fake_runtime(), max_order_attempts=1)
        self.assertNotIn('checkpoints', requests[0])

    def test_shared_port_still_rejected_with_checkpoints(self):
        p = pipe(); del p['points']; p['checkpoints'] = [[20,5]]
        other = copy.deepcopy(p); other['id'] = 'P2'
        with patch.object(R.subprocess, 'run') as run:
            with self.assertRaises(G.GuardError) as caught:
                R.route_scene(scene(), [p,other], runtime=self.fake_runtime())
        self.assertEqual(caught.exception.code, 'unsupported_shared_port'); run.assert_not_called()


@unittest.skipUnless(os.environ.get('PFD_TEST_RUNTIME'), 'Explicit separately reviewed libavoid runtime required')
class CheckpointRealRuntimeTests(unittest.TestCase):
    def test_real_middle_checkpoint_four_quarter_turns_and_two_lead_lengths(self):
        for lead in (2.,6.):
            for turn in range(4):
                with self.subTest(lead=lead,turn=turn):
                    s=scene();p=pipe();del p['points'];p['checkpoints']=[[20,15]]
                    def vector(q):
                        x,y=q
                        for _ in range(turn):x,y=-y,x
                        return [x,y]
                    def point(q):
                        x,y=vector(q)
                        return [100+x,200+y]
                    for equipment in s['equipment']:
                        equipment['polygon']=[point(q) for q in equipment['polygon']]
                        for port in equipment['ports']:
                            port['lead']=lead;port['point']=point(port['point']);port['outward']=vector(port['outward'])
                    p['checkpoints']=[point(q) for q in p['checkpoints']]
                    before=copy.deepcopy(s)
                    routed=R.route_scene(s,[p],runtime=Path(os.environ['PFD_TEST_RUNTIME']),max_order_attempts=1)
                    self.assertTrue(G.validate_scene(routed)['ok'])
                    self.assertEqual(routed['pipes'][0]['checkpoints'],p['checkpoints'])
                    self.assertEqual(s,before)

    def test_real_middle_checkpoint(self):
        p = pipe(); del p['points']; p['checkpoints'] = [[20,15]]
        routed = R.route_scene(scene(), [p], runtime=Path(os.environ['PFD_TEST_RUNTIME']))
        self.assertTrue(G.validate_scene(routed)['ok'])
        self.assertEqual(routed['pipes'][0]['checkpoints'], p['checkpoints'])

    def test_real_source_target_and_lead_checkpoints(self):
        p = pipe(); del p['points']; p['checkpoints'] = [[10,5],[11,5],[20,5],[29,5],[30,5]]
        routed = R.route_scene(scene(), [p], runtime=Path(os.environ['PFD_TEST_RUNTIME']))
        self.assertTrue(G.validate_scene(routed)['ok'])
        self.assertEqual(routed['pipes'][0]['checkpoints'], p['checkpoints'])

    def test_real_unreachable_checkpoint_stops_without_commit(self):
        s = scene(); original = copy.deepcopy(s)
        p = pipe(); del p['points']; p['checkpoints'] = [[5,5]]
        with self.assertRaises((G.GuardError, RuntimeError)):
            R.route_scene(s, [p], runtime=Path(os.environ['PFD_TEST_RUNTIME']), max_order_attempts=1)
        self.assertEqual(s, original)


if __name__ == '__main__':
    unittest.main()
