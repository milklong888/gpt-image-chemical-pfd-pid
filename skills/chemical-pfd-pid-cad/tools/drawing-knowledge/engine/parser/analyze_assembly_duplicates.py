"""Read-only analysis of production candidate duplication; does not alter corpus."""
from pathlib import Path
import collections
import json
import re

import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from portable_config import data_root
ROOT = data_root()
page_cache = {}


def key(chunk):
    boxes = []
    for box in chunk.get("bboxes", []):
        t, b = box["t"], box["b"]
        if box["coordinate_origin"] == "BOTTOMLEFT":
            dp = chunk["docling_document_path"]
            if dp not in page_cache:
                page_cache[dp] = json.loads(Path(dp).read_text(encoding="utf-8"))["pages"]
            height = page_cache[dp][str(box["page"])]["size"]["height"]
            t, b = height - t, height - b
        boxes.append((box["page"], *[round(v, 3) for v in (min(box["l"],box["r"]), min(t,b), max(box["l"],box["r"]), max(t,b))]))
    # Preserve punctuation, decimal signs, minus signs, units and all internal text.
    return chunk["source_id"], tuple(sorted(chunk["physical_pages"])), chunk.get("text", "").strip(), tuple(sorted(boxes))


groups = collections.defaultdict(list)
types = collections.Counter()
total = 0
for file in (ROOT / "parsed/native-pdfs").rglob("chunks.json"):
    run = json.loads((file.parent / "run.json").read_text(encoding="utf-8"))
    if run.get("state") != "complete" or run.get("conversion_status") != "success":
        continue
    for chunk in json.loads(file.read_text(encoding="utf-8")):
        total += 1
        types[chunk["content_type"]] += 1
        groups[key(chunk)].append({"id": chunk["id"], "content_type": chunk["content_type"], "payload_path": str(file)})
duplicates = [rows for rows in groups.values() if len(rows) > 1]
result = {"scope": "Completed production native PDF outputs only; no corpus mutation", "raw_candidates": total,
          "content_types": dict(types), "canonical_groups": len(groups), "duplicate_groups": len(duplicates),
          "duplicate_candidates": sum(len(rows)-1 for rows in duplicates),
          "key": "Exact source_id + original physical pages + text.strip() + bbox in original TOPLEFT coordinates rounded to 0.001 pt. No fuzzy/numeric normalization.",
          "duplicate_samples": duplicates[:20]}
(ROOT / "parser/assembly-duplicate-analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k:result[k] for k in ["raw_candidates", "canonical_groups", "duplicate_groups", "duplicate_candidates", "content_types"]}))
