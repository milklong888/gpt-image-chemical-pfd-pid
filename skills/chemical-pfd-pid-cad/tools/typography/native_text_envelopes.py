"""Locate native text metric envelopes; never approve glyph ink or a design.

Copyright (c) 2026 milklong and contributors. See the accompanying .license.
Native GeometricExtents remains the default. The narrow optional path is limited
to directly measured, explicitly verified single-line TopLeft/TopRight MTEXT.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata

from ezdxf.math import Matrix44
from shapely.geometry import box


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _valid_digest(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _finite_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _finite_vector3(value):
    return isinstance(value, (list, tuple)) and len(value) == 3 and all(_finite_number(v) for v in value)


def native_world_allocation(record, *, coordinate_space, block_transform=None):
    """Use actual WCS extents, or transform a declared local AABB once.

    A transformed local AABB stays conservative; it is not a new native glyph
    measurement. Supplying a block matrix for already-WCS extents is rejected.
    """
    b = record['native_extents']
    if len(b) != 6 or not all(_finite_number(v) for v in b):
        raise ValueError('Invalid native extents')
    if any(b[i] > b[i+3] for i in range(3)):
        raise ValueError('Native minimum exceeds maximum')
    if coordinate_space == 'WCS':
        if block_transform is not None:
            raise ValueError('Do not apply a block transform to native WCS extents twice')
        return box(b[0], b[1], b[3], b[4]), 'native GeometricExtents WCS'
    if coordinate_space != 'BLOCK_LOCAL' or block_transform is None:
        raise ValueError('Explicit WCS extents or a declared block-local transform is required')
    try:
        values = list(block_transform)
    except (TypeError, ValueError) as error:
        raise ValueError('Invalid block transform values') from error
    if len(values) != 16 or not all(_finite_number(v) for v in values):
        raise ValueError('Block transform must contain sixteen finite numeric values')
    # ezdxf Matrix44.transform applies affine point coordinates and does not
    # evaluate projective division. Do not silently call a projective input a
    # conservative affine AABB. In its row-vector convention, column four must
    # be exactly (0, 0, 0, 1).
    if any(values[i] != 0 for i in (3, 7, 11)) or values[15] != 1:
        raise ValueError('Only affine block transforms are supported')
    matrix = Matrix44(values)
    corners = [matrix.transform((x, y, z)) for x in (b[0], b[3]) for y in (b[1], b[4]) for z in (b[2], b[5])]
    if not all(_finite_number(v) for point in corners for v in point):
        raise ValueError('Block transform produced non-finite coordinates')
    return box(min(v.x for v in corners), min(v.y for v in corners), max(v.x for v in corners), max(v.y for v in corners)), 'transformed native local AABB; conservative WCS allocation'


def _simple_layout_reason(record, entity, evidence, native_text_file_sha256):
    """Return None only for the deliberately small, evidence-bound path."""
    if not isinstance(evidence, dict) or evidence.get('verified_single_line') is not True:
        return 'no explicit verified single-line native evidence'
    if not _valid_digest(native_text_file_sha256) or evidence.get('native_text_file_sha256') != native_text_file_sha256:
        return 'native file identity is missing or differs'
    if str(evidence.get('handle', '')).upper() != str(record.get('handle', '')).upper() or str(entity.dxf.handle).upper() != str(record.get('handle', '')).upper():
        return 'text handle differs'
    raw = entity.text
    if evidence.get('dxf_raw_sha256') != _digest(raw) or evidence.get('native_raw_sha256') != _digest(record.get('raw_text', '')):
        return 'exact raw text identity differs'
    if getattr(entity, 'columns', None) is not None or record.get('columns'):
        return 'columns are outside the verified path'
    if entity.dxf.get('flow_direction', 5) not in (1, 5):
        return 'vertical or reverse flow is outside the verified path'
    if entity.doc is None:
        return 'text style is unavailable'
    style = entity.doc.styles.get(entity.dxf.style)
    if style.dxf.get('flags', 0) & 4:
        return 'vertical text style is outside the verified path'
    if any(unicodedata.category(c) in ('Cc', 'Cf', 'Zl', 'Zp') for c in raw) or re.search(r'\^[IJM]', raw):
        return 'Unicode control/format or line/paragraph layout is outside the verified path'
    profile = evidence.get('format_profile')
    if profile == 'plain_single_line':
        if any(c in raw for c in '\\{}'):
            return 'inline format or paragraph layout is not plain text'
        payload = raw
    elif profile == 'verified_one_font_span':
        # Only a single font span whose exact raw bytes were actually reviewed.
        # No paragraph/alignment/indent/stack/column commands are interpreted.
        match = re.fullmatch(r'\{\\[fF]([^;{}\\]+);([^{}\\\r\n\t]*)\}', raw)
        if match is None:
            return 'unrecognized inline format; use native allocation'
        payload = match.group(2)
    else:
        return 'unknown text format profile'
    if any(unicodedata.bidirectional(c) in ('R', 'AL', 'RLE', 'RLO', 'RLI', 'LRI', 'FSI', 'PDI', 'PDF') for c in payload):
        return 'bidirectional or reverse layout is outside the verified path'
    return None


def native_text_envelope(record, entity, *, coordinate_space, block_transform=None,
                         simple_line_evidence=None, native_text_file_sha256=None):
    """Return (Shapely envelope, provenance metadata), without a fit verdict.

    By default this returns native GeometricExtents. Narrowing needs explicit
    exact-file/exact-text single-line evidence and the limited conditions below.
    That evidence is supplied by the caller's actual native review, not invented
    by this helper. A metric rectangle touching a contour still needs PDF ink.
    """
    allocation, method = native_world_allocation(record, coordinate_space=coordinate_space, block_transform=block_transform)
    rotation = record.get('rotation')
    meta = {'method': method, 'certainty': 'conservative native allocation, not glyph ink',
            'native_allocation_bounds': list(allocation.bounds),
            'attachment_point': entity.dxf.get('attachment_point', None),
            'native_rotation_radians': rotation if _finite_number(rotation) else None, 'narrowed': False,
            'font_or_design_approval': False, 'fallback_reason': None}

    def fallback(reason):
        meta['fallback_reason'] = reason
        return allocation, meta

    if coordinate_space != 'WCS' or block_transform is not None:
        return fallback('block/transformed allocation is conservative only')
    if entity.dxftype() != 'MTEXT':
        return fallback('only the bounded MTEXT path can be narrowed')
    if not _finite_number(rotation):
        meta['native_rotation_invalid_input'] = repr(rotation)
        return fallback('native rotation is not a finite numeric value')
    if abs(rotation) > 1e-10:
        return fallback('rotation is missing or outside zero-rotation native evidence')
    normal = tuple(entity.dxf.get('extrusion', (0, 0, 1)))
    try:
        direction = entity.get_text_direction()
    except (ValueError, ZeroDivisionError):
        return fallback('invalid text direction')
    if not _finite_vector3(normal) or not _finite_vector3(tuple(direction)):
        return fallback('non-finite text plane or direction')
    if any(abs(a-b) > 1e-10 for a, b in zip(normal, (0, 0, 1))) or abs(direction.x-1) > 1e-10 or abs(direction.y) > 1e-10 or abs(direction.z) > 1e-10:
        return fallback('nonstandard plane or reversed direction')
    attachment = entity.dxf.attachment_point
    if attachment not in (1, 3):
        return fallback('only TopLeft and TopRight have actual native support in this bounded path')
    reason = _simple_layout_reason(record, entity, simple_line_evidence, native_text_file_sha256)
    if reason:
        return fallback(reason)
    width, height = record.get('actual_width'), record.get('actual_height')
    if any(not _finite_number(v) or v < 0 for v in (width, height)):
        return fallback('native actual metrics are missing or invalid')
    x0, y0, x1, y1 = allocation.bounds
    if width > x1-x0+1e-7 or abs(height-(y1-y0)) > 1e-7:
        return fallback('allocated Width/DefinedHeight differs from actual metrics')
    location = record.get('location')
    if not _finite_vector3(location) or not _finite_vector3(tuple(entity.dxf.insert)):
        return fallback('native/readback location is not a finite numeric 3-vector')
    anchor_x = x0 if attachment == 1 else x1
    if abs(location[0]-anchor_x) > 1e-7 or abs(location[1]-y1) > 1e-7 or any(abs(a-b) > 1e-7 for a, b in zip(location, entity.dxf.insert)):
        return fallback('native location, allocation edge and readback attachment disagree')
    # Anchor to the actual native allocation edge, never assume Location is left.
    gx0 = x0 if attachment == 1 else x1-width
    envelope = box(gx0, y0, gx0+width, y1)
    meta.update(method='native allocation '+('left' if attachment == 1 else 'right')+' edge + ActualWidth',
                certainty='bounded native advance-metric rectangle, not actual ink', narrowed=True,
                exact_native_evidence=dict(simple_line_evidence))
    return envelope, meta


def main():
    import ezdxf
    parser = argparse.ArgumentParser(description='Native metrics locator only; no ink, font-fit or design acceptance')
    parser.add_argument('--native-text', type=Path, required=True)
    parser.add_argument('--readback-dxf', type=Path, required=True)
    parser.add_argument('--handle', required=True)
    parser.add_argument('--coordinate-space', choices=['WCS'], required=True)
    parser.add_argument('--simple-line-evidence', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    native_hash = hashlib.sha256(args.native_text.read_bytes()).hexdigest()
    data = json.loads(args.native_text.read_text(encoding='utf-8'))
    record = next(r for r in data['native_text_extents'] if str(r['handle']).upper() == args.handle.upper())
    doc = ezdxf.readfile(args.readback_dxf)
    entity = doc.entitydb[args.handle.upper()]
    if entity.dxf.owner != doc.modelspace().block_record_handle:
        raise ValueError('CLI requires a direct modelspace entity with actual native WCS extents')
    evidence = json.loads(args.simple_line_evidence.read_text(encoding='utf-8')) if args.simple_line_evidence else None
    envelope, meta = native_text_envelope(record, entity, coordinate_space=args.coordinate_space,
                                        simple_line_evidence=evidence, native_text_file_sha256=native_hash)
    result = {'handle': args.handle, 'envelope': list(envelope.bounds), 'metadata': meta,
              'native_text': {'path': str(args.native_text), 'sha256': native_hash},
              'readback_dxf': {'path': str(args.readback_dxf), 'sha256': hashlib.sha256(args.readback_dxf.read_bytes()).hexdigest()},
              'formal_font_pass': False, 'ink_containment_pass': None, 'engineering_approval': False}
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
