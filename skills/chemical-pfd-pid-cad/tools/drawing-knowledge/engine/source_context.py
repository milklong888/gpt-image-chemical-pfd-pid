"""Read-only source navigation; candidate associations are never approved equivalence."""
import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import unicodedata


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_identity(source):
    path = Path(source['path'])
    if not path.is_file() or sha(path) != source['sha256']:
        raise ValueError('SOURCE_CHANGED: ' + source['source_id'])
    return {k: source[k] for k in ('source_id', 'path', 'sha256', 'original_aliases')}


def sibling_evidence(left, right):
    result = []
    for a in left['original_aliases']:
        for b in right['original_aliases']:
            pa = PurePosixPath(a['member_name'].replace('\\', '/')).parent
            pb = PurePosixPath(b['member_name'].replace('\\', '/')).parent
            if a['zip_path'] == b['zip_path'] and pa == pb:
                result.append({'archive': a['zip_path'], 'directory': str(pa),
                               'source_member': a['member_name'], 'candidate_member': b['member_name']})
    return result


def member_parts(value):
    """Comparison only: retain original alias strings in all returned evidence."""
    value = unicodedata.normalize('NFKC', value.replace('\\', '/'))
    path = PurePosixPath(value)
    if path.is_absolute() or any(p == '..' or ':' in p for p in path.parts):
        return None
    return tuple(p.casefold() for p in path.parts if p not in ('', '.'))


def archive_key(value):
    # Archives are actual Windows paths: do not merge different compatibility
    # Unicode filenames or archives merely having the same zip basename.
    return str(PureWindowsPath(value)).casefold()


def unnumber(value):
    return re.sub(r'^\s*\d+(?:[.]\d+)*\s*[-_.、]\s*', '', value)


def version_kind(value):
    value = re.sub(r'\s+', '', unnumber(value))
    if re.fullmatch(r'pdf(?:版|版本|格式)?', value):
        return 'pdf'
    if re.fullmatch(r'(?:autocad|cad|dwg)(?:-?r?\d{2,4})?(?:版|版本|格式)?', value):
        return 'cad'
    return None


def version_scopes(alias, kind):
    parts = member_parts(alias['member_name'])
    if not parts:
        return []
    result = []
    generic = {'图纸', '设计图纸', '图纸集', '文件', '资料', '设计资料', '新建文件夹',
               'documents', 'drawings', 'files', 'data', 'archive', 'archives'}
    for index, part in enumerate(parts[:-1]):
        if version_kind(part) != kind:
            continue
        prefix = parts[:index]
        # A bare archive/container/PDF/CAD folder is not a project ancestor.
        # Preserve numbered ancestor names; never equate project 2 with 11.
        if not prefix or not any(p not in generic and version_kind(p) is None for p in prefix):
            continue
        tail = parts[index+1:]
        if not 1 <= len(tail) <= 3:
            continue  # at most two topic directories below a version folder
        result.append({'ancestor': prefix, 'version_directory': part, 'tail': tail})
    return result


def topic_key(value, filename=False):
    if filename:
        value = PurePosixPath(value).stem
    return re.sub(r'\s+', '', unnumber(value))


def project_version_evidence(left, right):
    """Narrow archive/path/topic relation; never drawing/page equivalence."""
    result = []
    for a in left['original_aliases']:
        for b in right['original_aliases']:
            if archive_key(a['zip_path']) != archive_key(b['zip_path']):
                continue
            for sa in version_scopes(a, 'pdf'):
                for sb in version_scopes(b, 'cad'):
                    if sa['ancestor'] != sb['ancestor']:
                        continue
                    source_topic = topic_key(sa['tail'][-1], filename=True)
                    if not source_topic:
                        continue
                    source_subdirectories = tuple(topic_key(p) for p in sa['tail'][:-1])
                    candidate_subdirectories = tuple(topic_key(p) for p in sb['tail'][:-1])
                    if candidate_subdirectories not in (source_subdirectories,
                                                       source_subdirectories + (source_topic,)):
                        continue  # do not cross a new/unmatched subproject below CAD/PDF
                    filename_match = source_topic == topic_key(sb['tail'][-1], filename=True)
                    folder_match = source_topic in [topic_key(p) for p in sb['tail'][:-1]]
                    if not (filename_match or folder_match):
                        continue
                    result.append({'archive': a['zip_path'],
                        'project_ancestor_comparison_key': '/'.join(sa['ancestor']),
                        'source_version_directory': sa['version_directory'],
                        'candidate_version_directory': sb['version_directory'],
                        'source_member': a['member_name'], 'candidate_member': b['member_name'],
                        'subdirectory_rule': 'same relative directories, optionally one extra source-topic directory on CAD side',
                        'topic_match': 'normalized_basename' if filename_match else 'normalized_topic_directory',
                        'comparison_normalization': 'NFKC/casefold/slashes; strip number prefixes only for version/topic, never project ancestor',
                        'status': 'same_project_version_directory_candidate_only; no equivalence or page match'})
    # Multiple archive aliases may support one source; do not duplicate a source.
    return list({json.dumps(r, sort_keys=True, ensure_ascii=False): r for r in result}.values())


def discover_candidates(source, sources, mode='auto', candidate_limit=5):
    if mode not in ('auto', 'same-directory', 'project-versions'):
        raise ValueError('INVALID_CANDIDATE_SEARCH_MODE')
    if type(candidate_limit) is not int or not 1 <= candidate_limit <= 10:
        raise ValueError('INVALID_CANDIDATE_LIMIT')
    exact, versions = [], []
    for candidate in sources:
        if candidate['source_id'] == source['source_id'] or candidate.get('extension', '').lower() not in ('.dwg', '.bak', '.dxf'):
            continue
        reasons = sibling_evidence(source, candidate)
        if reasons:
            exact.append((candidate, 'same_archive_directory_candidate_only', reasons))
        if mode == 'project-versions' or mode == 'auto':
            reasons = project_version_evidence(source, candidate)
            if reasons:
                versions.append((candidate, 'same_project_version_directory_candidate_only', reasons))
    if mode == 'same-directory' or (mode == 'auto' and exact):
        selected, selected_mode = exact, 'same-directory'
    else:
        selected, selected_mode = versions, 'project-versions'
    # Stable ordering is navigation order, not semantic confidence or latest-version rank.
    selected.sort(key=lambda row: row[0]['source_id'])
    return selected[:candidate_limit], {'requested_mode': mode, 'selected_mode': selected_mode,
        'candidate_limit': candidate_limit, 'eligible_candidate_count': len(selected),
        'returned_candidate_count': min(len(selected), candidate_limit),
        'candidates_truncated': len(selected) > candidate_limit,
        'same_directory_eligible_count': len(exact),
        'explicit_expansion_when_same_directory_candidates_do_not_match': '--candidate-search project-versions',
        'selection_is_not_confidence_ranking': True}


def verified_native_text(document, row, owner_cache):
    """Verify extracted text-like entities without turning definitions into instances."""
    handle = row['handle']
    entity = document.entitydb.get(handle)
    if entity is None or not entity.is_alive or entity.dxftype() not in ('TEXT', 'MTEXT', 'ATTRIB', 'ATTDEF'):
        raise ValueError('NATIVE_TEXT_HANDLE_INVALID: ' + handle)
    kind = entity.dxftype()
    # Layout records carry kind; old block texts omit it. The extractor does
    # not put ATTRIB into blocks[].texts, so that route must remain distinct.
    if (row.get('kind') is not None and row['kind'] != kind) or (row['scope'] == 'block_definition' and kind == 'ATTRIB'):
        raise ValueError('NATIVE_TEXT_TYPE_MISMATCH: ' + handle)
    value = entity.plain_text() if kind == 'MTEXT' else entity.dxf.text
    position, recorded = list(entity.dxf.insert), row.get('insert', [])
    numeric = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    if (value != row['text'] or not isinstance(recorded, (list, tuple)) or len(recorded) != len(position)
            or not all(numeric(v) for v in position + list(recorded))
            or any(abs(a-b) > 1e-7 for a, b in zip(position, recorded))):
        raise ValueError('NATIVE_TEXT_MISMATCH: ' + handle)
    if row.get('layer') is not None and row['layer'] != entity.dxf.layer:
        raise ValueError('NATIVE_TEXT_LAYER_MISMATCH: ' + handle)
    owner_handle = entity.dxf.get('owner')
    owner = document.entitydb.get(owner_handle)
    membership_entity, parent_insert = entity, None
    if kind == 'ATTRIB' and owner is not None and owner.dxftype() == 'INSERT':
        if not any(a.dxf.handle == handle for a in owner.attribs):
            raise ValueError('NATIVE_TEXT_OWNER_INVALID: ' + handle)
        parent_insert = owner.dxf.handle
        membership_entity = owner
        owner = document.entitydb.get(owner.dxf.get('owner'))
    if owner is None or owner.dxftype() != 'BLOCK_RECORD':
        raise ValueError('NATIVE_TEXT_OWNER_INVALID: ' + handle)
    block_handle, owner_name = owner.dxf.handle, owner.dxf.name
    if block_handle not in owner_cache:
        block = document.blocks.get(owner_name)
        if block is None or block.block_record_handle != block_handle:
            raise ValueError('NATIVE_TEXT_OWNER_INVALID: ' + handle)
        layout_name = next((layout.name for layout in document.layouts
                            if layout.block_record_handle == block_handle), None)
        owner_cache[block_handle] = (layout_name, {e.dxf.handle for e in block})
    layout_name, members = owner_cache[block_handle]
    if membership_entity.dxf.handle not in members:
        raise ValueError('NATIVE_TEXT_OWNER_INVALID: ' + handle)
    actual_scope = 'drawing' if layout_name is not None else 'block_definition'
    if row['scope'] != actual_scope:
        raise ValueError('NATIVE_TEXT_SCOPE_MISMATCH: ' + handle)
    if actual_scope == 'drawing' and row.get('layout') is not None and row['layout'] != layout_name:
        raise ValueError('NATIVE_TEXT_LAYOUT_MISMATCH: ' + handle)
    if actual_scope == 'block_definition' and row.get('block') != owner_name:
        raise ValueError('NATIVE_TEXT_OWNER_MISMATCH: ' + handle)
    for key in ('owner', 'owner_handle'):
        if row.get(key) is not None and row[key] != owner_handle:
            raise ValueError('NATIVE_TEXT_OWNER_MISMATCH: ' + handle)
    if row.get('owner_block') is not None and row['owner_block'] != owner_name:
        raise ValueError('NATIVE_TEXT_OWNER_MISMATCH: ' + handle)
    if row.get('parent_insert_handle') is not None and row['parent_insert_handle'] != parent_insert:
        raise ValueError('NATIVE_ATTRIBUTE_PARENT_MISMATCH: ' + handle)
    attribute = kind in ('ATTDEF', 'ATTRIB')
    tag = entity.dxf.tag if attribute else None
    if row.get('tag') is not None and row['tag'] != tag:
        raise ValueError('NATIVE_ATTRIBUTE_TAG_MISMATCH: ' + handle)
    return {'handle': entity.dxf.handle, 'kind': kind, 'entity_type': kind, 'text': value,
            'insert': position, 'layer': entity.dxf.layer, 'owner_handle': owner_handle,
            'owner_block': owner_name, 'scope': actual_scope, 'layout': layout_name,
            'owner_and_scope_verified': True,
            'coordinate_context': 'drawing_layout' if actual_scope == 'drawing' else 'block_definition_local',
            'attribute_definition': kind == 'ATTDEF', 'attribute_tag': tag,
            'text_role': 'attribute_definition_default' if kind == 'ATTDEF' else 'attribute_value' if kind == 'ATTRIB' else 'text',
            'parent_insert_handle': parent_insert,
            'is_insert_attribute_value': kind == 'ATTRIB' and parent_insert is not None,
            'matched_literals': row['matched_literals'], 'verified_against_actual_dxf': True}


def native_summary(root, source, terms, limit, navigation_only=False):
    path = root / 'native' / source['source_id'] / 'evidence.json'
    if not path.is_file():
        return {'available': False, 'reason': 'No native extraction record at the registered location.'}
    evidence = read(path)
    if evidence['source_id'] != source['source_id'] or evidence['source_sha256'] != source['sha256']:
        raise ValueError('NATIVE_SOURCE_BINDING_CHANGED: ' + source['source_id'])
    if evidence.get('ok') is not True:
        return {'available': False, 'evidence_path': str(path), 'evidence_sha256': sha(path),
                'reason': 'Native extraction is not recorded as successful.'}
    dxf = Path(evidence['dxf_path'])
    if not dxf.is_file() or sha(dxf) != evidence['dxf_sha256']:
        raise ValueError('NATIVE_DXF_CHANGED: ' + source['source_id'])
    if navigation_only:
        # Hash/metadata only. Do not load a whole DXF for every path candidate,
        # and never return extraction-only text as if actual entities were read.
        return {'available': True, 'evidence_path': str(path), 'evidence_sha256': sha(path),
                'dxf_path': str(dxf), 'dxf_sha256': evidence['dxf_sha256'],
                'text_count': len(evidence.get('texts', [])) + sum(len(b.get('texts', [])) for b in evidence.get('blocks', [])),
                'hits': [], 'literal_hit_count': None, 'hits_truncated': False,
                'navigation_only': True, 'actual_text_verification_performed': False,
                'literal_search_performed': False, 'literal_terms_deferred': list(terms),
                'next_step': 'After matching the original page/title/frame, select this native source_id and repeat --find to verify actual entities. Do not add --page to the native source call.',
                'interpretation': 'Only source/evidence/DXF binding and paths checked. Candidate is not equivalent, not assigned to any PDF page, and no native text is approved by this record.'}
    texts = []
    for row in evidence.get('texts', []):
        if row.get('scope') not in (None, 'drawing'):
            raise ValueError('NATIVE_TEXT_SCOPE_MISMATCH: ' + row['handle'])
        texts.append({**row, 'scope': 'drawing'})
    for block in evidence.get('blocks', []):
        for row in block.get('texts', []):
            if row.get('scope') not in (None, 'block_definition') or row.get('block') not in (None, block.get('name')):
                raise ValueError('NATIVE_TEXT_SCOPE_MISMATCH: ' + row['handle'])
            texts.append({**row, 'scope': 'block_definition', 'block': block.get('name')})
    # Attached attributes are instance values, distinct from block ATTDEF
    # defaults. Attribute insert coordinates are already stored by DXF;
    # do not apply the parent INSERT transform a second time.
    by_handle = {row['handle']: row for row in texts}
    for insert in evidence.get('inserts', []):
        for attribute in insert.get('attributes', []):
            if attribute.get('scope') not in (None, 'drawing'):
                raise ValueError('NATIVE_TEXT_SCOPE_MISMATCH: ' + attribute['handle'])
            row = {**attribute, 'scope': 'drawing', 'kind': 'ATTRIB',
                   'layout': insert['layout'], 'parent_insert_handle': insert['handle']}
            prior = by_handle.get(row['handle'])
            if prior is not None:
                if (prior['text'] != row['text'] or prior.get('insert') != row.get('insert')
                        or prior.get('scope') != 'drawing'
                        or prior.get('kind') not in (None, 'ATTRIB')):
                    raise ValueError('NATIVE_ATTRIBUTE_DUPLICATE_MISMATCH: ' + row['handle'])
                prior.update(row)
            else:
                texts.append(row)
                by_handle[row['handle']] = row
    hits = []
    for row in texts:
        searchable = row.get('text', '') + '\n' + row.get('tag', '')
        matched = [term for term in terms if term.casefold() in searchable.casefold()]
        if matched:
            hits.append({**row, 'matched_literals': matched})
    returned = []
    if hits:
        import ezdxf
        document = ezdxf.readfile(dxf)
        owner_cache = {}
        for row in hits[:limit]:
            returned.append(verified_native_text(document, row, owner_cache))
    return {'available': True, 'evidence_path': str(path), 'evidence_sha256': sha(path),
            'dxf_path': str(dxf), 'dxf_sha256': evidence['dxf_sha256'],
            'attached_insert_attributes_searched': True,
            'geometry_reusable_as_recorded': evidence.get('geometry_reusable'),
            'geometry_reusable_status': 'explicit_true' if evidence.get('geometry_reusable') is True else 'false_or_not_established_by_record',
            'text_count': len(texts), 'literal_hit_count': len(hits), 'hits': returned,
            'hits_truncated': len(hits) > limit,
            'hit_completeness': 'Search begins in extraction metadata; returned hits are verified against actual DXF. Empty results do not prove absence or a complete extraction.',
            'interpretation': 'Returned TEXT/MTEXT/ATTRIB/ATTDEF, coordinates and owner/scope are verified against the hashed DXF. ATTDEF is a definition default, never an INSERT attribute-instance value; block-definition coordinates remain local. Attached INSERT attribute values/tags are searched and their parent INSERT is verified; they are never filled from ATTDEF defaults. Verify correspondence against the target page; no automatic PDF-page match, approved reusable geometry or engineering authority.'}


def context(root, source_id, page=None, terms=(), limit=50, candidate_search='auto', candidate_limit=5):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('INVALID_HIT_LIMIT')
    registry_path = root / 'registry/sources.json'
    sources = read(registry_path)['sources']
    lookup = {s['source_id']: s for s in sources}
    if source_id not in lookup:
        raise ValueError('UNKNOWN_SOURCE: ' + source_id)
    source = lookup[source_id]
    identity = source_identity(source)
    total = source.get('pdf_page_count')
    if page is not None and (type(page) is not int or type(total) is not int or not 1 <= page <= total):
        raise ValueError('INVALID_PHYSICAL_PAGE')
    pages = []
    coverage_path = root / 'parsed/pdf-coverage.json'
    coverage = None
    if total:
        coverage = next((s for s in read(coverage_path)['sources'] if s['source_id'] == source_id), None)
        if coverage:
            if coverage['source_sha256'] != source['sha256']:
                raise ValueError('PDF_COVERAGE_SOURCE_CHANGED')
            selected = {page} if page is not None else set(range(1, total + 1))
            if page is not None:
                selected.update(p for p in (page - 1, page + 1) if 1 <= p <= total)
            for row in coverage['pages']:
                if row['page'] in selected:
                    pages.append({**row, 'role': 'target' if row['page'] == page else 'document_context',
                                  'chunk_files': [str(Path(ref).with_name('chunks.json')) for ref in row.get('run_refs', [])]})
    native_candidates = []
    selected_candidates, discovery = discover_candidates(source, sources, candidate_search, candidate_limit)
    for candidate, association, reasons in selected_candidates:
        native_candidates.append({**source_identity(candidate), 'association_status': association,
                                  'association_evidence': reasons,
                                  'native': native_summary(root, candidate, terms, limit,
                                      navigation_only=association == 'same_project_version_directory_candidate_only'
                                      or source.get('extension', '').lower() in ('.dwg', '.bak', '.dxf'))})
    own_native = native_summary(root, source, terms, limit) if source.get('extension', '').lower() in ('.dwg', '.bak', '.dxf') else None
    return {'schema': 'source-navigation-context/v1', 'source': identity,
            'registry_sha256': sha(registry_path), 'requested_physical_page': page,
            'total_physical_pages': total, 'coverage': pages,
            'coverage_manifest_path': str(coverage_path) if coverage else None,
            'coverage_manifest_sha256': sha(coverage_path) if coverage else None,
            'native': own_native, 'native_candidates': native_candidates,
            'candidate_discovery': discovery,
            'literal_terms': list(terms), 'hit_limit_per_candidate': limit,
            'requested_page_filters_pdf_coverage_only': True,
            'native_text_pdf_page_assignment': 'not_performed; candidates and literal hits may span every drawing frame/layout in the native file',
            'no_candidate_is_not_proof_of_absence': True,
            'instructions_for_use': [
                'Read the target page and available same-document legend/title/continuation pages. Adjacent pages are navigation context, not automatic continuation proof.',
                'Validate candidate native drawing identity by title/number, equipment and geometry before using its text. Directory proximity or AutoCAD format year does not establish design equivalence or authority.',
                'The requested PDF page does not filter native text. Use title/frame/layout and coordinates to establish each native hit’s actual PDF page before assigning equipment or endpoints to a scoped sheet. Use literal hits and coordinates to locate native text, then return to the PDF view. Readable native text must not be replaced by an unverified visual guess; record true conflicts in both locations.',
                'If no same-directory candidate exists, search registry aliases/title further. This bounded lookup is not exhaustive pairing.',
                'Auto mode uses bounded PDF/CAD sibling-version-directory candidates only when no same-directory candidate exists. If listed same-directory candidates prove unsuitable, use --candidate-search project-versions. Version candidates are metadata-only; select one native source_id for actual --find entity verification. Candidate-list caps and exact topic comparisons can omit legitimate sources; no result is not proof of absence.',
                'This is source navigation, not semantic retrieval and not a completed query receipt. Continue the normal module and standards retrieval workflow.'
            ], 'engineering_release_eligible': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path)
    parser.add_argument('--source-id', required=True)
    parser.add_argument('--page', type=int)
    parser.add_argument('--find', action='append', default=[])
    parser.add_argument('--limit', type=int, default=50)
    parser.add_argument('--candidate-search', choices=['auto', 'same-directory', 'project-versions'], default='auto')
    parser.add_argument('--candidate-limit', type=int, default=5)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 500:
        parser.error('--limit must be 1..500')
    from portable_config import data_root
    root = args.data or data_root()
    if args.out.exists():
        raise ValueError('OUTPUT_EXISTS')
    result = context(root.resolve(), args.source_id, args.page, args.find, args.limit,
                     args.candidate_search, args.candidate_limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'output': str(args.out), 'native_candidates': len(result['native_candidates']), 'page_contexts': len(result['coverage'])}))


if __name__ == '__main__':
    main()
