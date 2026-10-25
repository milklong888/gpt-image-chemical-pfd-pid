"""Report actual original-page coverage, without implying semantic review."""
from pathlib import Path
import argparse
import json
from datetime import datetime, timezone

import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from portable_config import data_root
ROOT = data_root()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", type=Path, default=ROOT / "registry/sources.json")
    ap.add_argument("--parsed", type=Path, default=ROOT / "parsed")
    ap.add_argument("--out", type=Path, default=ROOT / "parsed/pdf-coverage.json")
    args = ap.parse_args()
    sources = {s["source_id"]: s for s in json.loads(args.registry.read_text(encoding="utf-8"))["sources"] if s["extension"] == ".pdf"}
    by_source = {sid: {} for sid in sources}
    failed, running, stale = [], [], []
    for report_path in args.parsed.rglob("run.json"):
        rel = report_path.relative_to(args.parsed)
        if any(part.startswith("benchmark") or part.startswith("native-pilot") for part in rel.parts):
            continue
        try:
            run = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        sid = run.get("source_id")
        if sid not in sources:
            continue
        if run.get("source_sha256") != sources[sid]["sha256"]:
            stale.append(str(report_path))
            continue
        if run.get("state") == "failed":
            failed.append({"source_id": sid, "report": str(report_path), "error": run.get("error")})
            continue
        if run.get("state") != "complete":
            running.append(str(report_path))
            continue
        if run.get("conversion_status") != "success":
            failed.append({"source_id": sid, "report": str(report_path), "error": "Conversion not fully successful"})
            continue
        chunks_path = report_path.parent / "chunks.json"
        if not chunks_path.exists():
            failed.append({"source_id": sid, "report": str(report_path), "error": "Completed report missing chunk data"})
            continue
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        mode = run.get("config", {}).get("processing_mode")
        if not mode:
            mode = "native_pdf_content_only" if run.get("config", {}).get("pipeline_options_class") == "NativePdfPipelineOptions" else "full_layout_table_ocr"
        for chunk in chunks:
            for page in chunk.get("physical_pages", []):
                if page < 1 or page > sources[sid]["pdf_page_count"]:
                    raise ValueError(f"Out-of-range original page: {sid}/{page}")
                dest = by_source[sid].setdefault(page, {"page": page, "native_indexed": False, "ocr_parsed": False,
                    "visual_anchor": False, "text_candidate_chars": 0, "has_saved_crop": False, "run_refs": []})
                dest["native_indexed"] |= mode == "native_pdf_content_only"
                dest["ocr_parsed"] |= mode == "full_layout_table_ocr"
                dest["visual_anchor"] |= chunk.get("content_type") == "page_visual"
                dest["text_candidate_chars"] += len(chunk.get("text", "").strip())
                dest["has_saved_crop"] |= bool(chunk.get("crops"))
                ref = str(report_path.resolve())
                if ref not in dest["run_refs"]:
                    dest["run_refs"].append(ref)
    results = []
    for sid, source in sources.items():
        pages = by_source[sid]
        expected = list(range(1, source["pdf_page_count"] + 1))
        missing = [p for p in expected if p not in pages or not pages[p]["visual_anchor"]]
        rows = []
        for page in sorted(pages):
            row = pages[page]
            row["content_status"] = "visual_only_no_reliable_text_claim" if row["text_candidate_chars"] == 0 else "unreviewed_text_candidates"
            rows.append(row)
        results.append({"source_id": sid, "source_sha256": source["sha256"], "path": source["path"],
                        "expected_pages": len(expected), "indexed_pages": len(rows), "missing_pages": missing,
                        "processing_state": "page_coverage_complete" if not missing else "partial_or_unprocessed",
                        "semantic_review_state": "not_established_by_parsing", "pages": rows})
    report = {"schema": "actual-pdf-coverage/v1", "generated_at": datetime.now(timezone.utc).isoformat(),
              "scope": "PDFs only; native CAD and other formats are covered by their separate adapters",
              "totals": {"pdf_sources": len(results), "expected_pages": sum(r["expected_pages"] for r in results),
                         "indexed_pages": sum(r["indexed_pages"] for r in results),
                         "complete_sources": sum(r["processing_state"] == "page_coverage_complete" for r in results),
                         "missing_pages": sum(len(r["missing_pages"]) for r in results)},
              "failed_runs": failed, "running_reports": running, "stale_source_reports": stale,
              "limitations": "Coverage means original pages and extracted candidates were indexed. It is not OCR completeness, standards applicability, reviewed engineering facts, or drawing release approval.",
              "sources": results}
    tmp = args.out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(args.out)
    print(json.dumps(report["totals"]))


if __name__ == "__main__":
    main()
