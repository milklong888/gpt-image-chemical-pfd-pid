"""Validate the final declared planning scope using the existing receipt gate."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--drawing', choices=['pfd', 'pid', 'equipment_condition', 'layout'], required=True)
    parser.add_argument('--equipment', nargs='+', required=True)
    parser.add_argument('--components', nargs='*', default=[])
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('OUTPUT_EXISTS')
    if not args.plan.is_file() or not args.plan.read_bytes().strip():
        raise ValueError('CONTENT_PLAN_REQUIRED')
    runtime = Path(__file__).resolve().parent
    sys.path.insert(0, str(runtime))
    import knowledge
    from retrieval_gate import check_receipt
    from portable_config import data_root
    root = data_root()
    modules = knowledge.expand_modules(args.drawing, args.equipment, args.components)
    original = args.plan.read_bytes()
    proof = check_receipt(args.receipt, root, args.drawing, modules)
    if args.plan.read_bytes() != original:
        raise ValueError('CONTENT_PLAN_CHANGED_DURING_CHECK')
    result = {'schema': 'final-planning-scope-check/v1', 'ok': True,
              'plan_path': str(args.plan.resolve()), 'plan_sha256': hashlib.sha256(original).hexdigest(),
              'drawing_kind': args.drawing, 'declared_equipment': args.equipment,
              'declared_components': args.components, 'required_modules': sorted(modules),
              'receipt_proof': proof, 'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'semantic_completeness_verified': False, 'engineering_release_eligible': False,
              'boundary': 'Checks the explicitly declared final scope, not natural-language completeness. An independent reviewer must compare the actual planned objects against this declaration. A plan change invalidates this bound proof; rerun before handoff.'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'ok': True, 'output': str(args.out), 'required_modules': sorted(modules)}))


if __name__ == '__main__':
    main()
