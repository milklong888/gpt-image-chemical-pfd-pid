import copy
import unittest
import pfd_guard as G


def scene():
    return {'schema':'pfd-guard/v1', 'parameters':{
        'linear_tolerance':1e-7, 'angular_tolerance_deg':0.01,
        'equipment_clearance':2., 'pipe_clearance':1., 'minimum_lead':2.},
        'equipment':[
            {'id':'A','polygon':[[0,0],[10,0],[10,10],[0,10],[0,0]],
             'ports':[{'id':'out','point':[10,5],'outward':[1,0],'lead':2.}]},
            {'id':'B','polygon':[[30,0],[40,0],[40,10],[30,10],[30,0]],
             'ports':[{'id':'in','point':[30,5],'outward':[-1,0],'lead':2.}]}
        ], 'pipes':[]}


def pipe():
    return {'id':'P1', 'source':{'equipment':'A','port':'out'},
            'target':{'equipment':'B','port':'in'},'points':[[10,5],[30,5]]}


class GuardTests(unittest.TestCase):
    def rejected(self, code, s=None, p=None):
        with self.assertRaises(G.GuardError) as err:
            G.validate_pipe(s if s is not None else scene(), p if p is not None else pipe())
        self.assertEqual(err.exception.code, code)
        self.assertEqual(set(err.exception.to_dict()), {'code','message','pipe','equipment','segment'})

    def test_good_directed_boundary_connection(self):
        self.assertTrue(G.validate_pipe(scene(),pipe())['ok'])

    def test_target_direction_is_reversed(self):
        s=scene(); s['equipment'][1]['ports'][0]['outward']=[1,0]
        self.rejected('invalid_outward',s)

    def test_bad_source_tangent(self):
        p=pipe(); p['points']=[[10,5],[10,15],[25,15],[25,5],[30,5]]
        self.rejected('wrong_port_direction',p=p)

    def test_bad_target_approach(self):
        p=pipe(); p['points']=[[10,5],[15,5],[15,15],[30,15],[30,5]]
        self.rejected('wrong_port_direction',p=p)

    def test_gap(self):
        p=pipe();p['points'][0]=[10.1,5]
        self.rejected('endpoint_mismatch',p=p)

    def test_tiny_other_equipment_near_source(self):
        s=scene();s['equipment'].append({'id':'C','polygon':[[10.2,4.9],[10.4,4.9],[10.4,5.1],[10.2,5.1],[10.2,4.9]],'ports':[]})
        self.rejected('equipment_contact',s)

    def test_cross_other_equipment(self):
        s=scene();s['equipment'].append({'id':'C','polygon':[[18,2],[22,2],[22,8],[18,8],[18,2]],'ports':[]})
        self.rejected('equipment_contact',s)

    def test_overlap_other_boundary(self):
        s=scene();s['equipment'].append({'id':'C','polygon':[[18,5],[22,5],[22,8],[18,8],[18,5]],'ports':[]})
        self.rejected('equipment_contact',s)

    def test_tangent_other_vertex(self):
        s=scene();s['equipment'].append({'id':'C','polygon':[[20,5],[22,7],[20,9],[18,7],[20,5]],'ports':[]})
        self.rejected('equipment_contact',s)

    def test_clearance(self):
        s=scene();s['equipment'].append({'id':'C','polygon':[[18,6],[22,6],[22,9],[18,9],[18,6]],'ports':[]})
        self.rejected('equipment_clearance',s)

    def test_fake_internal_port(self):
        s=scene();s['equipment'][0]['ports'][0]['point']=[9,5]
        self.rejected('port_off_boundary',s)

    def test_invalid_outward_along_boundary(self):
        s=scene();s['equipment'][0]['ports'][0]['outward']=[0,1]
        self.rejected('invalid_outward',s)

    def test_initial_body_exit_is_never_exempt(self):
        s=scene();s['equipment'][0]['polygon']=[[0,0],[10,0],[10,4],[16,4],[16,6],[10,6],[10,10],[0,10],[0,0]]
        self.rejected('port_off_boundary',s)

    def test_concave_body_reentry(self):
        s=scene(); s['equipment'][0]['polygon']=[[0,0],[17,0],[17,10],[15,10],[15,2],[10,2],[10,10],[0,10],[0,0]]
        # port on the concave side at x10; 2-unit lead is clear, full line crosses x15 body.
        self.rejected('equipment_contact',s)

    def test_same_body_protection_reentry_is_not_exempt(self):
        s=scene(); s['equipment'][0]['polygon']=[[0,0],[10,0],[10,8],[15,8],[15,6.5],[17,6.5],[17,10],[0,10],[0,0]]
        self.rejected('equipment_clearance',s)

    def test_no_zero_length(self):
        p=pipe();p['points']=[[10,5],[10,5],[30,5]]
        self.rejected('zero_segment',p=p)

    def test_no_backtracking(self):
        p=pipe();p['points']=[[10,5],[20,5],[18,5],[30,5]]
        self.rejected('backtrack',p=p)

    def test_no_self_cross(self):
        p=pipe();p['points']=[[10,5],[15,5],[15,15],[25,15],[25,0],[20,0],[20,20],[28,20],[28,5],[30,5]]
        self.rejected('self_intersection',p=p)

    def test_no_diagonal(self):
        p=pipe();p['points']=[[10,5],[20,6],[30,5]]
        self.rejected('nonorthogonal_segment',p=p)

    def test_short_lead(self):
        p=pipe();p['points']=[[10,5],[11,5],[11,15],[28,15],[28,5],[30,5]]
        self.rejected('short_lead',p=p)

    def test_bend_inside_protection_not_exempt(self):
        s=scene();s['parameters']['minimum_lead']=.5;s['equipment'][0]['ports'][0]['lead']=.5
        p=pipe();p['points']=[[10,5],[11,5],[11,15],[28,15],[28,5],[30,5]]
        self.rejected('equipment_clearance',s,p)

    def test_redundant_collinear_reported(self):
        p=pipe();p['points']=[[10,5],[11,5],[30,5]]
        result=G.validate_pipe(scene(),p)
        self.assertEqual(result['warnings'][0]['code'],'redundant_collinear_point')

    def test_reroute_outside_same_equipment(self):
        s=scene();s['equipment']=s['equipment'][:1]
        s['equipment'][0]['ports'].append({'id':'top','point':[5,10],'outward':[0,1],'lead':2})
        p=pipe();p['target']={'equipment':'A','port':'top'};p['points']=[[10,5],[15,5],[15,15],[5,15],[5,10]]
        self.assertTrue(G.validate_pipe(s,p)['ok'])

    def test_atomic_rejection(self):
        s=scene(); p=pipe(); p['points'][0]=[10.5,5]; before=copy.deepcopy(s)
        with self.assertRaises(G.GuardError):G.commit_pipe(s,p)
        self.assertEqual(s,before)

    def test_commit_owns_copy(self):
        s=scene();p=pipe();G.commit_pipe(s,p);p['points'][0][0]=999
        self.assertEqual(s['pipes'][0]['points'][0][0],10)
        self.assertTrue(G.validate_scene(s)['ok'])

    def test_duplicate_id(self):
        s=scene();G.commit_pipe(s,pipe());self.rejected('duplicate_pipe_id',s)

    def test_duplicate_geometry(self):
        s=scene();G.commit_pipe(s,pipe());p=pipe();p['id']='P2';self.rejected('duplicate_pipe',s,p)

    def test_missing_parameter(self):
        s=scene();del s['parameters']['pipe_clearance'];self.rejected('invalid_number',s)

    def test_nonfinite(self):
        p=pipe();p['points'][0]=[float('nan'),5];self.rejected('invalid_number',p=p)

    def test_missing_polygon(self):
        s=scene();del s['equipment'][0]['polygon'];self.rejected('invalid_contract',s)

    def test_unclosed_polygon(self):
        s=scene();s['equipment'][0]['polygon'].pop();self.rejected('unclosed_polygon',s)

    def test_invalid_polygon(self):
        s=scene();s['equipment'][0]['polygon']=[[0,0],[10,10],[0,10],[10,0],[0,0]];self.rejected('invalid_polygon',s)

    def test_unknown_port(self):
        p=pipe();p['target']['port']='missing';self.rejected('unknown_port',p=p)

    def test_missing_pipe_id(self):
        p=pipe();del p['id'];self.rejected('missing_id',p=p)


if __name__ == '__main__':
    unittest.main()
