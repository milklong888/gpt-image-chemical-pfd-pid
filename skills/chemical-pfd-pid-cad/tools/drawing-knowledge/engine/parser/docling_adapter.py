"""Local Docling PDF ingestion with traceable page/region provenance.

This adapter does not judge requirements or turn examples into normative rules.
Every emitted item is an extracted_candidate requiring source review.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from portable_config import data_root
ROOT = data_root()
ADAPTER_VERSION = "docling-native-hierarchical/1.0"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def write_json(path, value):
    def finite(v):
        if isinstance(v, float) and not math.isfinite(v):
            return None
        if isinstance(v, dict):
            return {k: finite(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [finite(x) for x in v]
        return v
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(finite(value), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def version(package):
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def make_converter(threads=2, full_ocr=True, ocr_scale=3.0, mode="ocr"):
    os.environ.setdefault("OMP_NUM_THREADS", str(threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(threads))
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
    from docling.document_converter import DocumentConverter, PdfFormatOption

    if mode == "native":
        from docling.datamodel.pipeline_options import NativePdfPipelineOptions
        from docling.pipeline.native_pdf_pipeline import NativePdfPipeline
        options = NativePdfPipelineOptions(parser_threads=threads, generate_picture_images=False,
                                          generate_page_images=False, enable_remote_services=False)
        return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(
            pipeline_cls=NativePdfPipeline, pipeline_options=options)}), options

    options = PdfPipelineOptions()
    options.accelerator_options = AcceleratorOptions(num_threads=threads, device=AcceleratorDevice.CPU)
    options.do_ocr = True
    options.ocr_options = RapidOcrOptions(backend="onnxruntime", lang=["ch"], force_full_page_ocr=full_ocr, scale=ocr_scale)
    options.do_table_structure = True
    options.do_picture_description = False
    options.do_picture_classification = False
    options.generate_page_images = False
    options.generate_picture_images = False
    options.generate_parsed_pages = True
    options.enable_remote_services = False
    # On a 16 GB desktop, keep only a few pages and model batches in flight.
    for field in ("ocr_batch_size", "layout_batch_size", "table_batch_size"):
        if hasattr(options, field):
            setattr(options, field, 1)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}), options


class MemorySampler:
    def __init__(self):
        self.peak = 0
        self.samples = []
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self):
        try:
            import psutil
            proc = psutil.Process()
            while not self.stop_event.is_set():
                rss = proc.memory_info().rss
                self.peak = max(self.peak, rss)
                self.samples.append({"elapsed_s": round(time.monotonic() - self.started, 2), "rss_bytes": rss})
                self.stop_event.wait(2)
        except ImportError:
            pass

    def __enter__(self):
        self.started = time.monotonic()
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop_event.set()
        self.thread.join(timeout=3)


def object_value(obj):
    return getattr(obj, "value", str(obj))


def item_metadata(items):
    refs, boxes, parents, headers = [], [], [], []
    labels = []
    for item in items:
        refs.append(item.self_ref)
        labels.append(object_value(item.label))
        parent = getattr(item, "parent", None)
        if parent:
            parents.append(parent.cref)
        for prov in item.prov:
            box = prov.bbox
            boxes.append({"page": prov.page_no, "l": box.l, "t": box.t, "r": box.r,
                          "b": box.b, "coordinate_origin": object_value(box.coord_origin)})
        if hasattr(item, "data") and hasattr(item.data, "table_cells"):
            for cell in item.data.table_cells:
                if getattr(cell, "column_header", False) or getattr(cell, "row_header", False):
                    headers.append(cell.model_dump(mode="json"))
    return refs, boxes, sorted(set(parents)), labels, headers


def render_regions(source_path, boxes, out_dir, stem, scale=2.0):
    """Render each original page union region; no rewritten or invented pixels."""
    import pymupdf
    results = []
    with pymupdf.open(source_path) as pdf:
        by_page = {}
        for box in boxes:
            by_page.setdefault(box["page"], []).append(box)
        for page_no, page_boxes in by_page.items():
            page = pdf[page_no - 1]
            rects = []
            for box in page_boxes:
                t, b = box["t"], box["b"]
                if box["coordinate_origin"] in ("BOTTOMLEFT", "BOTTOM_LEFT"):
                    t, b = page.rect.height - t, page.rect.height - b
                rects.append(pymupdf.Rect(min(box["l"], box["r"]), min(t, b), max(box["l"], box["r"]), max(t, b)))
            rect = rects[0]
            for other in rects[1:]:
                rect |= other
            rect = (rect + (-3, -3, 3, 3)) & page.rect
            if rect.is_empty:
                continue
            path = out_dir / "crops" / f"{stem}-p{page_no:04d}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=rect, alpha=False).save(path)
            results.append({"path": str(path.resolve()), "page": page_no,
                            "clip_top_left": list(rect), "render_scale": scale,
                            "source_path": str(source_path)})
    return results


def map_source_boxes(boxes, page_transforms):
    if not page_transforms:
        return boxes
    import pymupdf
    mapped = []
    for box in boxes:
        trans = page_transforms[box["page"]]
        t, b = box["t"], box["b"]
        if box["coordinate_origin"] in ("BOTTOMLEFT", "BOTTOM_LEFT"):
            t, b = trans["derived_height"] - t, trans["derived_height"] - b
        rect = pymupdf.Rect(min(box["l"], box["r"]), min(t, b), max(box["l"], box["r"]), max(t, b))
        rect = rect * pymupdf.Matrix(*trans["derived_to_original_matrix"])
        mapped.append({"page": box["page"], "l": rect.x0, "t": rect.y0, "r": rect.x1,
                       "b": rect.y1, "coordinate_origin": "TOPLEFT"})
    return mapped


def prepare_rotation(source, start, end, rotation, folder):
    if not rotation:
        return source["path"], {}
    import pymupdf
    derived_path = folder / f"derived-rotate-{rotation:03d}.pdf"
    transforms = {}
    with pymupdf.open(source["path"]) as pdf:
        for page_no in range(start, end + 1):
            page = pdf[page_no - 1]
            original_rotation = page.rotation
            original_matrix = page.rotation_matrix
            original_rect = list(page.rect)
            page.set_rotation((original_rotation + rotation) % 360)
            matrix = page.derotation_matrix * original_matrix
            transforms[page_no] = {
                "original_rotation": original_rotation, "added_clockwise_rotation": rotation,
                "original_display_rect": original_rect, "derived_display_rect": list(page.rect),
                "derived_height": page.rect.height, "derived_to_original_matrix": list(matrix),
            }
        pdf.save(derived_path)
    write_json(folder / "source-transform.json", {
        "source_id": source["source_id"], "original_path": source["path"], "original_sha256": source["sha256"],
        "derived_path": str(derived_path.resolve()), "derived_sha256": sha256(derived_path),
        "method": "Explicit, visually justified page rotation; original page count and numbering retained; no text or graphics edits.",
        "page_transforms": transforms,
    })
    return str(derived_path), transforms


def build_chunks(document, source, doc_path, range_id, out_dir, crops=True, page_transforms=None):
    from docling.chunking import HierarchicalChunker
    # Keep all list entries together; no token-based cut through a condition or exception.
    chunker = HierarchicalChunker(merge_list_items=True, always_emit_headings=True)
    chunks = []
    for index, chunk in enumerate(chunker.chunk(dl_doc=document)):
        items = list(chunk.meta.doc_items or [])
        refs, boxes, parents, labels, headers = item_metadata(items)
        raw_boxes = boxes
        boxes = map_source_boxes(boxes, page_transforms)
        chunk_id = f"{source['source_id']}-{range_id}-c{index:05d}"
        row = {
            "id": chunk_id, "source_id": source["source_id"], "source_sha256": source["sha256"],
            "text": chunk.text, "physical_pages": sorted({x["page"] for x in boxes}),
            "bboxes": boxes, "docling_refs": refs,
            "docling_original_bboxes": raw_boxes if page_transforms else None,
            "source_transform_path": str((out_dir / "source-transform.json").resolve()) if page_transforms else None,
            "content_type": "table" if "table" in labels else (labels[0] if len(set(labels)) == 1 else "mixed"),
            "status": "extracted_candidate", "parser": ADAPTER_VERSION,
            "docling_document_path": str(doc_path.resolve()),
            "parent_docling_refs": parents, "headings": chunk.meta.headings or [],
            "captions": chunk.meta.captions or [], "table_headers": headers,
            "context_text": chunker.contextualize(chunk),
            "source_path": source["path"], "review_required": True,
            "boundary_context_policy": "Retrieve adjacent source pages and parent clause/table before treating text as a complete requirement.",
            "cropping": {"supported": True, "method": "original PDF page bbox union; coordinate_origin recorded"},
        }
        if crops and boxes:
            row["crops"] = render_regions(source["path"], boxes, out_dir, chunk_id)
        chunks.append(row)
    # A PID or symbol table may be detected only as a picture. Preserve its region,
    # without generating a prose description or inferring nozzle/valve semantics.
    covered_refs = {ref for chunk in chunks for ref in chunk["docling_refs"]}
    for index, item in enumerate(document.pictures):
        if item.self_ref in covered_refs:
            continue
        refs, boxes, parents, labels, headers = item_metadata([item])
        raw_boxes = boxes
        boxes = map_source_boxes(boxes, page_transforms)
        chunk_id = f"{source['source_id']}-{range_id}-picture{index:05d}"
        caption = item.caption_text(document) if hasattr(item, "caption_text") else ""
        row = {
            "id": chunk_id, "source_id": source["source_id"], "source_sha256": source["sha256"],
            "text": caption, "physical_pages": sorted({x["page"] for x in boxes}), "bboxes": boxes,
            "docling_refs": refs, "content_type": "picture", "status": "extracted_candidate",
            "docling_original_bboxes": raw_boxes if page_transforms else None,
            "source_transform_path": str((out_dir / "source-transform.json").resolve()) if page_transforms else None,
            "parser": ADAPTER_VERSION, "docling_document_path": str(doc_path.resolve()),
            "parent_docling_refs": parents, "headings": [], "captions": [caption] if caption else [],
            "table_headers": [], "source_path": source["path"], "review_required": True,
            "boundary_context_policy": "Visual review and native CAD source required; no geometry is inferred from OCR.",
        }
        if crops and boxes:
            row["crops"] = render_regions(source["path"], boxes, out_dir, chunk_id)
        chunks.append(row)
    # Always retain a source-page anchor. OCR often misses thin CAD text and a
    # diagram is not exhaustively represented by whatever text was recognized.
    for page_no, page in document.pages.items():
        chunk_id = f"{source['source_id']}-{range_id}-page{page_no:04d}"
        boxes = [{"page": page_no, "l": 0, "t": 0, "r": page.size.width,
                  "b": page.size.height, "coordinate_origin": "TOPLEFT"}]
        raw_boxes = boxes
        boxes = map_source_boxes(boxes, page_transforms)
        row = {
            "id": chunk_id, "source_id": source["source_id"], "source_sha256": source["sha256"],
            "text": "", "physical_pages": [page_no], "bboxes": boxes, "docling_refs": [],
            "docling_original_bboxes": raw_boxes if page_transforms else None,
            "source_transform_path": str((out_dir / "source-transform.json").resolve()) if page_transforms else None,
            "content_type": "page_visual", "status": "extracted_candidate", "parser": ADAPTER_VERSION,
            "docling_document_path": str(doc_path.resolve()), "source_path": source["path"],
            "review_required": True, "headings": [], "captions": [], "table_headers": [],
            "boundary_context_policy": "Whole original page retained for checking omitted text, symbols, conditions and cross-page context.",
        }
        if crops:
            row["crops"] = render_regions(source["path"], boxes, out_dir, chunk_id, scale=1.25)
        chunks.append(row)
    return chunks


def retain_page_cells(result, source, doc_path, range_id, folder, page_transforms):
    """Keep Docling's actual text cells before diagram/picture assembly hides them.

    These are not reconstructed table rows or requirements. Their independent
    provenance prevents an OCR fragment from being mistaken for a Docling item.
    """
    raw = []
    chunks = []
    cells_path = folder / "docling-page-cells.json"
    for page in result.pages:
        for index, cell in enumerate(page.cells):
            raw.append({"physical_page": page.page_no, "cell": cell.model_dump(mode="json")})
            if not cell.text.strip():
                continue
            box = cell.to_bounding_box()
            boxes = [{"page": page.page_no, "l": box.l, "t": box.t, "r": box.r, "b": box.b,
                      "coordinate_origin": object_value(box.coord_origin)}]
            raw_boxes = boxes
            boxes = map_source_boxes(boxes, page_transforms)
            chunks.append({
                "id": f"{source['source_id']}-{range_id}-cell{page.page_no:04d}-{index:05d}",
                "source_id": source["source_id"], "source_sha256": source["sha256"], "text": cell.text,
                "physical_pages": [page.page_no], "bboxes": boxes, "docling_refs": [],
                "content_type": "ocr_text_region" if cell.from_ocr else "native_text_region",
                "status": "extracted_candidate", "parser": ADAPTER_VERSION,
                "docling_document_path": str(doc_path.resolve()), "docling_page_cells_path": str(cells_path.resolve()),
                "page_cell_index": index, "source_path": source["path"], "review_required": True,
                "ocr_confidence": cell.confidence, "headings": [], "captions": [], "table_headers": [],
                "docling_original_bboxes": raw_boxes if page_transforms else None,
                "source_transform_path": str((folder / "source-transform.json").resolve()) if page_transforms else None,
                "boundary_context_policy": "Unassembled text region: retrieve containing visual/table/clause and neighboring regions. This is not a complete requirement and has no inferred table relationship.",
                "cropping": {"supported": True, "method": "render_regions on original source bboxes"},
            })
    write_json(cells_path, raw)
    return chunks


def convert_range(converter, source, start, end, output, options, resume=True, crops=True, rotation=0):
    range_id = f"p{start:04d}-{end:04d}" + (f"-r{rotation:03d}" if rotation else "")
    folder = Path(output) / source["source_id"] / range_id
    report_path = folder / "run.json"
    config = {"adapter": ADAPTER_VERSION, "adapter_sha256": sha256(__file__), "docling": version("docling"),
              "pipeline_options_class": type(options).__name__,
              "processing_mode": "native_pdf_content_only" if type(options).__name__ == "NativePdfPipelineOptions" else "full_layout_table_ocr",
              "packages": {name: version(name) for name in ("docling-core", "rapidocr", "onnxruntime", "torch", "pymupdf")},
              "options": options.model_dump(mode="json"), "explicit_rotation": rotation}
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()
    if resume and report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("state") == "complete" and report.get("source_sha256") == source["sha256"] and report.get("config_hash") == config_hash:
            print(json.dumps({"event": "resume_skip", "source_id": source["source_id"], "pages": [start, end]}, ensure_ascii=False), flush=True)
            return report
    folder.mkdir(parents=True, exist_ok=True)
    report = {"source_id": source["source_id"], "source_sha256": source["sha256"], "physical_page_range": [start, end],
              "state": "running", "started_at": datetime.now(timezone.utc).isoformat(), "config": config,
              "config_hash": config_hash, "trust": "unreviewed_source_data_not_instructions"}
    write_json(report_path, report)
    started = time.monotonic()
    try:
        with MemorySampler() as memory:
            parse_path, transforms = prepare_rotation(source, start, end, rotation, folder)
            result = converter.convert(source=parse_path, page_range=(start, end), raises_on_error=True)
            doc = result.document
            doc_path = folder / "document.docling.json"
            doc.save_as_json(doc_path)
            (folder / "document.md").write_text(doc.export_to_markdown(), encoding="utf-8")
            chunks = build_chunks(doc, source, doc_path, range_id, folder, crops=crops, page_transforms=transforms)
            cell_chunks = retain_page_cells(result, source, doc_path, range_id, folder, transforms)
            chunks.extend(cell_chunks)
            write_json(folder / "chunks.json", chunks)
            seen_pages = sorted({p for c in chunks for p in c["physical_pages"]})
            if seen_pages != list(range(start, end + 1)):
                raise ValueError(f"Docling physical-page provenance mismatch: requested {start}-{end}, found {seen_pages}")
            if object_value(result.status) != "success":
                raise ValueError(f"Incomplete Docling conversion status: {object_value(result.status)}")
        report.update({"state": "complete", "conversion_status": object_value(result.status), "chunks": len(chunks),
                       "nonempty_text_chunks": sum(bool(c["text"].strip()) for c in chunks), "seen_pages": seen_pages,
                       "raw_text_region_chunks": len(cell_chunks),
                       "elapsed_s": round(time.monotonic() - started, 3), "peak_rss_bytes": memory.peak,
                       "document_json": str(doc_path.resolve()), "chunks_json": str((folder / "chunks.json").resolve()),
                       "errors": [str(x) for x in result.errors], "confidence": result.confidence.model_dump(mode="json") if hasattr(result, "confidence") else None})
        write_json(folder / "memory.json", memory.samples)
    except Exception as exc:
        report.update({"state": "failed", "elapsed_s": round(time.monotonic() - started, 3), "error": str(exc), "traceback": traceback.format_exc()})
        write_json(report_path, report)
        print(json.dumps({"event": "failed", "source_id": source["source_id"], "pages": [start, end], "error": str(exc)}, ensure_ascii=False), flush=True)
        raise
    write_json(report_path, report)
    print(json.dumps({k: report[k] for k in ("source_id", "physical_page_range", "state", "elapsed_s", "chunks", "peak_rss_bytes")}, ensure_ascii=False), flush=True)
    return report


def page_groups(pages, batch_size):
    pages = sorted(set(pages))
    if not pages:
        return []
    groups = []
    start = previous = pages[0]
    for page in pages[1:]:
        if page != previous + 1 or page - start >= batch_size:
            groups.append((start, previous))
            start = page
        previous = page
    groups.append((start, previous))
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "registry" / "sources.json")
    parser.add_argument("--out", type=Path, default=ROOT / "parsed")
    parser.add_argument("--source-id", action="append")
    parser.add_argument("--manifest", type=Path, help="JSON with sources[] containing source_id and one-based pages[]; shares one converter.")
    parser.add_argument("--pages", help="One-based physical pages: 16,19-20. Omit for all pages.")
    parser.add_argument("--all-pdf", action="store_true")
    parser.add_argument("--batch-pages", type=int, default=12)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--mode", choices=["ocr", "native"], default="ocr",
                        help="ocr = Docling layout/table/Chinese OCR; native = model-free PDF content and visual anchors, no OCR or semantic structure.")
    parser.add_argument("--ocr-scale", type=float, default=3.0)
    parser.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], default=0,
                        help="Explicit clockwise rotation of selected pages in a derived PDF; source bboxes map back to original pages.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--no-crops", action="store_true")
    parser.add_argument("--native-text-plus-ocr", action="store_true", help="OCR image regions only; default full-page OCR for damaged text layers.")
    args = parser.parse_args()
    if not (args.source_id or args.all_pdf or args.manifest):
        parser.error("Select --source-id, --manifest or --all-pdf")
    sources = json.loads(args.registry.read_text(encoding="utf-8"))["sources"]
    manifest_pages = {s["source_id"]: s["pages"] for s in json.loads(args.manifest.read_text(encoding="utf-8"))["sources"]} if args.manifest else {}
    selected = [s for s in sources if s["extension"].lower() == ".pdf" and (args.all_pdf or s["source_id"] in (args.source_id or []) or s["source_id"] in manifest_pages)]
    if args.manifest:
        manifest_order = list(manifest_pages)
        selected.sort(key=lambda s: manifest_order.index(s["source_id"]) if s["source_id"] in manifest_order else len(manifest_order))
    if not selected:
        parser.error("No matching PDF sources")
    print(json.dumps({"event": "initializing_docling", "selected_pdf_count": len(selected)}), flush=True)
    converter, options = make_converter(args.threads, not args.native_text_plus_ocr, args.ocr_scale, args.mode)
    print(json.dumps({"event": "converter_ready", "docling": version("docling")}), flush=True)
    reports = []
    for source in selected:
        if sha256(source["path"]) != source["sha256"]:
            raise ValueError("Source hash mismatch: " + source["source_id"])
        pages = []
        if source["source_id"] in manifest_pages:
            pages = manifest_pages[source["source_id"]]
        elif args.pages:
            for part in args.pages.split(","):
                if "-" in part:
                    first, last = map(int, part.split("-", 1))
                    pages.extend(range(first, last + 1))
                else:
                    pages.append(int(part))
        else:
            pages = list(range(1, source["pdf_page_count"] + 1))
        if not pages or min(pages) < 1 or max(pages) > source["pdf_page_count"]:
            raise ValueError("Page selection outside original PDF")
        for start, end in page_groups(pages, args.batch_pages):
            try:
                reports.append(convert_range(converter, source, start, end, args.out, options, args.resume, not args.no_crops, args.rotate))
            except Exception:
                if not args.continue_on_error:
                    raise
                suffix = f"-r{args.rotate:03d}" if args.rotate else ""
                path = args.out / source["source_id"] / (f"p{start:04d}-{end:04d}" + suffix) / "run.json"
                reports.append(json.loads(path.read_text(encoding="utf-8")))
            write_json(args.out / "last-run.json", {"adapter": ADAPTER_VERSION, "runs": reports})
    write_json(args.out / "last-run.json", {"adapter": ADAPTER_VERSION, "runs": reports})


if __name__ == "__main__":
    main()
