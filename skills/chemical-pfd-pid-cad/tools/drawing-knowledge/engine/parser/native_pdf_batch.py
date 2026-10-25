"""Docling native PDF/content index using the lightweight official Pdfium backend.

No OCR, table reconstruction or reading-order inference is performed. Diagram
pages with outline text remain visual-only until linked to native CAD or OCR.
"""
from pathlib import Path
import argparse
import json
from docling_adapter import ROOT, convert_range, page_groups, sha256, write_json


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=ROOT / "parser/drawing_pdfs_manifest.json")
    ap.add_argument("--out", type=Path, default=ROOT / "parsed/native-pdfs")
    ap.add_argument("--batch-pages", type=int, default=24)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--continue-on-error", action="store_true")
    args = ap.parse_args()
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import NativePdfPipelineOptions
    from docling.pipeline.native_pdf_pipeline import NativePdfPipeline
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.document_converter import DocumentConverter, PdfFormatOption
    options = NativePdfPipelineOptions(parser_threads=args.threads, generate_picture_images=False,
                                      generate_page_images=False, enable_remote_services=False)
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(
        pipeline_cls=NativePdfPipeline, pipeline_options=options, backend=PyPdfiumDocumentBackend)})
    print(json.dumps({"event": "native_pdfium_ready"}), flush=True)
    sources = {s["source_id"]: s for s in json.loads((ROOT / "registry/sources.json").read_text(encoding="utf-8"))["sources"]}
    selections = json.loads(args.manifest.read_text(encoding="utf-8"))["sources"]
    runs = []
    for selection in selections:
        source = sources[selection["source_id"]]
        if sha256(source["path"]) != source["sha256"]:
            raise ValueError("Changed source: " + source["source_id"])
        for start, end in page_groups(selection["pages"], args.batch_pages):
            try:
                run = convert_range(converter, source, start, end, args.out, options, args.resume, False)
            except Exception:
                if not args.continue_on_error:
                    raise
                run = json.loads((args.out / source["source_id"] / f"p{start:04d}-{end:04d}/run.json").read_text(encoding="utf-8"))
            run["native_backend"] = "docling.backend.pypdfium2_backend.PyPdfiumDocumentBackend"
            run["batch_wrapper_sha256"] = sha256(__file__)
            run["native_limitations"] = "No OCR, reading order, headings or table relationships. Zero text is visual-only content, not an empty or complete drawing."
            write_json(args.out / source["source_id"] / f"p{start:04d}-{end:04d}/run.json", run)
            runs.append(run)
            write_json(args.out / "last-run.json", {"pipeline": "Docling NativePdfPipeline + PyPdfiumDocumentBackend", "runs": runs})


if __name__ == "__main__":
    main()
