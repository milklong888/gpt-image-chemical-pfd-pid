"""Bounded synthetic regression fixtures; no CAD/native support claim.

Copyright (c) 2026 milklong and contributors. See the accompanying .license.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

import ezdxf
from ezdxf.math import Matrix44
from ezdxf.entities.mtext import MTextColumns
from shapely.geometry import box
from native_text_envelopes import native_text_envelope, native_world_allocation


NATIVE_HASH = hashlib.sha256(b'synthetic native record fixture, not CAD evidence').hexdigest()


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def fixture(attachment=1, bounds=None, rotation=0, raw='AB12', location=None):
    doc = ezdxf.new()
    bounds = bounds or [100, 45, 0, 116.5, 50, 0]
    if location is None:
        ax = bounds[0] if attachment == 1 else bounds[3] if attachment == 3 else (bounds[0]+bounds[3])/2
        location = [ax, bounds[4], 0]
    entity = doc.modelspace().add_mtext(raw, dxfattribs={'attachment_point': attachment, 'rotation': rotation*180/math.pi, 'insert': location})
    record = {'handle': entity.dxf.handle, 'raw_text': raw, 'native_extents': bounds,
              'actual_width': 8, 'actual_height': 5, 'rotation': rotation, 'location': location}
    evidence = {'verified_single_line': True, 'native_text_file_sha256': NATIVE_HASH,
                'handle': entity.dxf.handle, 'dxf_raw_sha256': digest(raw),
                'native_raw_sha256': digest(raw), 'format_profile': 'plain_single_line'}
    return entity, record, evidence


def run():
    rows = []

    def check(name, attachment, native, expected, rotation=0, narrowed=False):
        entity, record, evidence = fixture(attachment, native, rotation)
        geom, meta = native_text_envelope(record, entity, coordinate_space='WCS',
                                         simple_line_evidence=evidence, native_text_file_sha256=NATIVE_HASH)
        assert max(abs(a-b) for a, b in zip(geom.bounds, expected)) < 1e-9, (name, geom.bounds)
        assert meta['narrowed'] is narrowed, (name, meta)
        rows.append({'test': name, 'passed': True, 'expected_bounds': expected,
                     'actual_bounds': list(geom.bounds), 'narrowed': meta['narrowed'], 'reason': meta['fallback_reason']})

    # The original fifteen mechanism cases, all now public synthetic inputs.
    check('TopLeft native left edge', 1, [100,45,0,116.5,50,0], [100,45,108,50], narrowed=True)
    check('TopRight native right edge', 3, [83.5,45,0,100,50,0], [92,45,100,50], narrowed=True)
    check('TopCentre is conservative; no actual centred support claimed', 2, [91.75,45,0,108.25,50,0], [91.75,45,108.25,50])
    check('MiddleCentre is conservative', 5, [91.75,47.5,0,108.25,52.5,0], [91.75,47.5,108.25,52.5])
    check('BottomRight is conservative', 9, [83.5,50,0,100,55,0], [83.5,50,100,55])
    check('90-degree rotation uses native WCS allocation', 3, [95,33.5,0,100,50,0], [95,33.5,100,50], math.pi/2)
    check('45-degree rotation is not narrowed', 1, [96,44,0,112,60,0], [96,44,112,60], math.pi/4)
    check('DefinedHeight larger than ActualHeight is conservative', 1, [100,42,0,116.5,50,0], [100,42,116.5,50])
    check('Measured advance exceeding allocation is conservative', 3, [96,45,0,100,50,0], [96,45,100,50])
    record = {'native_extents': [0,0,0,4,2,0]}
    matrix = Matrix44.z_rotate(math.pi/2) @ Matrix44.translate(10,20,0)
    geom, _ = native_world_allocation(record, coordinate_space='BLOCK_LOCAL', block_transform=matrix)
    assert max(abs(a-b) for a, b in zip(geom.bounds, [8,20,10,24])) < 1e-9
    rows.append({'test': 'Declared block-local AABB transformed once', 'passed': True})
    geom, _ = native_world_allocation(record, coordinate_space='BLOCK_LOCAL', block_transform=Matrix44.scale(-1,1,1) @ Matrix44.translate(10,0,0))
    assert list(geom.bounds) == [6,0,10,2]
    rows.append({'test': 'Mirrored block allocation stays conservative', 'passed': True})
    for name, kwargs in [('Missing block transform rejected', {'coordinate_space':'BLOCK_LOCAL'}),
                         ('Double transform of WCS rejected', {'coordinate_space':'WCS','block_transform':matrix}),
                         ('Unknown coordinate space rejected', {'coordinate_space':'UNKNOWN'})]:
        try:
            native_world_allocation(record, **kwargs)
        except ValueError:
            rows.append({'test': name, 'passed': True, 'rejected': True})
        else:
            raise AssertionError(name)
    # Golden expected coordinates are independent literals, not calculated by
    # the implementation. The old always-rightward formula must fail this box.
    entity, record, evidence = fixture(3, [234,115,0,250,120,0])
    geom, _ = native_text_envelope(record, entity, coordinate_space='WCS', simple_line_evidence=evidence, native_text_file_sha256=NATIVE_HASH)
    expected = [242,115,250,120]
    legacy_wrong = [250,115,258,120]
    assert list(geom.bounds) == expected and box(*expected).covers(geom)
    assert not box(*expected).covers(box(*legacy_wrong))
    rows.append({'test': 'Independent TopRight golden regression rejects old rightward box', 'passed': True,
                 'expected_bounds': expected, 'legacy_wrong_bounds': legacy_wrong})

    def fallback(name, mutate, raw='AB12', profile='plain_single_line'):
        entity, record, evidence = fixture(raw=raw)
        evidence['format_profile'] = profile
        kwargs = {'simple_line_evidence': evidence, 'native_text_file_sha256': NATIVE_HASH}
        mutate(entity, record, evidence, kwargs)
        geom, meta = native_text_envelope(record, entity, coordinate_space='WCS', **kwargs)
        assert not meta['narrowed'] and list(geom.bounds) == [100,45,116.5,50], (name, meta)
        rows.append({'test': name, 'passed': True, 'reason': meta['fallback_reason']})

    fallback('No native single-line evidence defaults to allocation', lambda e,r,v,k: k.update(simple_line_evidence=None))
    fallback('Paragraph indent is not interpreted', lambda *a: None, raw=r'\pi10;AB12')
    fallback('Paragraph centre alignment is not interpreted', lambda *a: None, raw=r'\pxqc;AB12')
    fallback('Column layout is conservative', lambda e,r,v,k: r.update(columns={'count':2}))
    fallback('Actual DXF column object is conservative', lambda e,r,v,k: e.setup_columns(MTextColumns.new_static_columns(2,20,2,10)))
    fallback('Vertical flow is conservative', lambda e,r,v,k: setattr(e.dxf,'flow_direction',3))
    fallback('Reverse text direction is conservative', lambda e,r,v,k: setattr(e.dxf,'text_direction',(-1,0,0)))
    fallback('Unknown inline stack format is conservative', lambda *a: None, raw=r'{\S1/2;}')
    fallback('Font wrapper without exact verified profile is conservative', lambda *a: None, raw=r'{\FMetricFont;AB12}')
    fallback('Paragraph command inside a claimed font span is conservative', lambda *a: None, raw=r'{\FMetricFont;\pxqc;AB12}', profile='verified_one_font_span')
    fallback('Multiple font spans are conservative', lambda *a: None, raw=r'{\FMetricFont;A}{\FSecondFont;B}', profile='verified_one_font_span')
    fallback('Multiple lines are conservative', lambda *a: None, raw='AB12\nCD34')
    fallback('Bidirectional layout is conservative', lambda *a: None, raw='\u202eAB12')
    # Independent reviewer counterexamples. The implementation uses Unicode
    # categories, rather than treating this list as an exhaustive allow/deny set.
    fallback('LRE format control is conservative', lambda *a: None, raw='\u202aAB12')
    fallback('LRO format control is conservative', lambda *a: None, raw='\u202dAB12')
    fallback('NEL line control is conservative', lambda *a: None, raw='AB12\u0085CD34')
    nonaffine = list(Matrix44())
    nonaffine[3] = 1
    try:
        native_world_allocation({'native_extents':[0,0,0,4,2,0]}, coordinate_space='BLOCK_LOCAL', block_transform=nonaffine)
    except ValueError:
        rows.append({'test':'Finite non-affine block matrix rejected before affine transform','passed':True,'rejected':True})
    else:
        raise AssertionError('Finite non-affine block matrix must be rejected')
    fallback('Native file identity mismatch is conservative', lambda e,r,v,k: v.update(native_text_file_sha256='0'*64))
    fallback('Raw text identity mismatch is conservative', lambda e,r,v,k: v.update(dxf_raw_sha256='0'*64))
    fallback('Native and DXF attachment anchor disagreement is conservative', lambda e,r,v,k: r.update(location=[116.5,50,0]))
    fallback('Nonstandard text plane is conservative', lambda e,r,v,k: setattr(e.dxf,'extrusion',(0,1,0)))
    # Five independently expected numeric-boundary cases added after root's
    # independent r1 review. No CAD run or expanded layout support is claimed.
    fallback('NaN native rotation must not become zero rotation', lambda e,r,v,k: r.update(rotation=float('nan')))
    fallback('Boolean rotation must not become numeric zero', lambda e,r,v,k: r.update(rotation=False))
    fallback('NaN native location must not pass anchor comparison', lambda e,r,v,k: r.update(location=[float('nan'),50,0]))
    for name, matrix in [('Non-finite block matrix rejected', Matrix44.scale(float('nan'),1,1)),
                         ('Finite block matrix producing overflow rejected', Matrix44.scale(1e308,1,1))]:
        try:
            native_world_allocation({'native_extents':[0,0,0,4,2,0]}, coordinate_space='BLOCK_LOCAL', block_transform=matrix)
        except ValueError:
            rows.append({'test':name,'passed':True,'rejected':True})
        else:
            raise AssertionError(name)
    # Format parsing is a bounded mechanism test, not native font support proof.
    entity, record, evidence = fixture(raw=r'{\FMetricFont;AB12}')
    evidence['format_profile'] = 'verified_one_font_span'
    geom, meta = native_text_envelope(record, entity, coordinate_space='WCS', simple_line_evidence=evidence, native_text_file_sha256=NATIVE_HASH)
    assert meta['narrowed'] and list(geom.bounds) == [100,45,108,50]
    rows.append({'test': 'Exact verified one-font-span parser mechanism only', 'passed': True})
    # CLI I/O is exercised with synthetic records and an ezdxf-written fixture;
    # this is deliberately not described as AutoCAD native execution.
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary);entity, record, _ = fixture()
        native = root/'metrics.json';native.write_text(json.dumps({'native_text_extents':[record]}), encoding='utf-8')
        dxf = root/'fixture.dxf';entity.doc.saveas(dxf);out = root/'result.json'
        subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('native_text_envelopes.py')),
                        '--native-text',str(native),'--readback-dxf',str(dxf),'--handle',record['handle'],
                        '--coordinate-space','WCS','--out',str(out)], check=True, capture_output=True)
        result = json.loads(out.read_text(encoding='utf-8'))
        assert result['envelope'] == [100,45,116.5,50] and result['formal_font_pass'] is False
        rows.append({'test': 'CLI defaults to conservative allocation and no approval', 'passed': True})
    return {'schema':'native-text-envelope-tests/v1','cases':rows,'case_count':len(rows),'all_passed':True,
            'evidence_kind':'bounded synthetic geometry and CLI fixtures only','new_native_CAD_run':False,
            'actual_native_scope_claim':'No new native support claimed by these fixtures',
            'font_ink_or_design_acceptance':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--json',type=Path);args=parser.parse_args()
    result=run()
    if args.json:
        with args.json.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'cases':result['case_count'],'all_passed':True,'new_native_CAD_run':False}))
