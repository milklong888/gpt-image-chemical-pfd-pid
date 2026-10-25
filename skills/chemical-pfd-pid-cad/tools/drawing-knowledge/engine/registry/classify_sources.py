#!/usr/bin/env python3
"""Make keyword-based candidate classifications and a searchable local catalog.

No OCR or engineering approval is performed. Usage: python classify_sources.py --out registry
"""
from __future__ import annotations
import argparse, html, json, re
from pathlib import Path

CATEGORIES = {
    "standard": [r"\bGB\s*/?T?\s*\d", r"\bISO\s*\d", r"\bASME\b", r"\bAPI\s*\d", "标准", "规范"],
    "pfd": [r"\bPFD\b", "流程图", "工艺流程"],
    "pid": [r"\bP\s*&\s*I?\s*&?\s*D\b", r"\bPID\b", "管道及仪表", "管仪图"],
    "equipment_condition": ["设备条件", "设备数据表", "设备规格书", "datasheet"],
    "mechanical_drawing": ["机械图", "总装图", "零件图", "制造图", "fabrication drawing"],
    "layout": ["布置图", "设备布置", "plot plan", "layout"],
    "isometric": ["轴测图", "等轴测", "isometric", "iso drawing"],
    "album": ["图册", "样本", "catalog", "brochure"],
    "rendering": ["效果图", "渲染", "rendering", "visualization"],
    "support": ["支架", "管架", "吊架", "support", "hanger"],
}
MODULES = {
    "tower": ["塔器", "精馏塔", "吸收塔", "填料塔", "板式塔", "column", "distillation tower"],
    "heat_exchanger": ["换热器", "冷凝器", "再沸器", "heat exchanger", "shell and tube"],
    "reactor": ["反应器", "反应釜", "reactor"],
    "vessel": ["压力容器", "储罐", "容器", "压力罐", "vessel", "tank"],
    "pump_compressor": ["泵", "压缩机", "pump", "compressor"],
    "piping": ["管道", "管线", "配管", "piping", "pipeline"],
    "instrumentation": ["仪表", "控制阀", "流量计", "温度计", "压力表", "instrument", "control valve"],
    "common": ["通用设备", "通用零部件", "紧固件", "法兰", "阀门", "common equipment"],
}

def matches(term, text):
    return bool(re.search(term, text, re.I)) if term.startswith(r"\b") else term.lower() in text.lower()

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("--out", required=True, type=Path); args=ap.parse_args()
    root=args.out.resolve(); sp=root/"sources.json"; doc=json.loads(sp.read_text(encoding="utf-8-sig")); rows=doc.get("sources", [])
    try: import fitz
    except ImportError: fitz=None
    out=[]; thumbs=root/"thumbnails"; thumbs.mkdir(parents=True, exist_ok=True)
    for row in rows:
        aliases=row.get("original_aliases", []); names=[a.get("member_name", "") for a in aliases]
        text_by_page=[]; page_lengths=row.get("pdf_pages_text_length") or []
        path=Path(row["path"]); ispdf=path.suffix.lower()==".pdf"
        if ispdf and fitz:
            try:
                d=fitz.open(path); text_by_page=[p.get_text("text") for p in d]
                page_lengths=[len(t) for t in text_by_page]
                for i,p in enumerate(d):
                    pix=p.get_pixmap(matrix=fitz.Matrix(min(1000/p.rect.width, 1.5), min(1000/p.rect.width, 1.5)), alpha=False)
                    pix.save(thumbs/f"{row['source_id']}-p{i+1:03d}.png")
                d.close()
            except Exception: pass
        corpus="\n".join(names+text_by_page).lower()
        cats=[]
        for cat,terms in CATEGORIES.items():
            hits=[]
            for term in terms:
                if matches(term, corpus): hits.append({"keyword":term,"pages": [i+1 for i,t in enumerate(text_by_page) if matches(term,t)]})
            if hits: cats.append({"category":cat,"keywords":hits})
        if not cats: cats=[{"category":"unknown","keywords":[]}]
        mods=[]
        for mod,terms in MODULES.items():
            hits=[]
            for term in terms:
                if matches(term, corpus): hits.append({"keyword":term,"pages":[i+1 for i,t in enumerate(text_by_page) if matches(term,t)]})
            if hits: mods.append({"module":mod,"keywords":hits})
        out.append({"source_id":row["source_id"],"sha256":row["sha256"],"path":row["path"],"aliases":names,
                    "classification_candidates":cats,"module_candidates":mods,"scanned_pages":len(page_lengths),
                    "low_text_pages":[i+1 for i,n in enumerate(page_lengths) if n<30],
                    "non_rule_file_note": "原始3D/SKP/SHX/锁文件保留为资料原件；本分类不将其作为规则。" if path.suffix.lower() in {".skp",".shx",".dwl",".dwl2"} else None})
    atomic=root/"source-classification.json"; atomic.write_text(json.dumps({"schema":"knowledge-v4-machine-candidates/v1","approval":"candidate only; not validated or mandatory","sources":out},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    html_rows=[]
    for x in out:
        cats=", ".join(v["category"] for v in x["classification_candidates"])
        mods=", ".join(v["module"] for v in x["module_candidates"])
        aliases="; ".join(x["aliases"])
        rel=Path(x["path"])
        try: link=rel.resolve().as_uri()
        except Exception: link="#"
        html_rows.append(f'<tr data-category="{html.escape(cats)}"><td>{html.escape(x["source_id"])}</td><td>{html.escape(cats)}</td><td>{html.escape(mods)}</td><td>{x["scanned_pages"]}</td><td><a href="{html.escape(link,quote=True)}">original</a><br>{html.escape(aliases)}</td></tr>')
    page='''<!doctype html><meta charset="utf-8"><title>Source candidates</title><label>Category <select id="f"><option value="">all</option></select></label><table border="1"><thead><tr><th>ID</th><th>Candidate categories</th><th>Candidate modules</th><th>PDF pages</th><th>Original / aliases</th></tr></thead><tbody>'''+"\n".join(html_rows)+'''</tbody></table><script>const s=document.querySelector('#f'), rows=[...document.querySelectorAll('tbody tr')];[...new Set(rows.flatMap(r=>r.dataset.category.split(', ')))].filter(Boolean).sort().forEach(x=>s.add(new Option(x,x)));s.onchange=()=>rows.forEach(r=>r.hidden=!!s.value&&!r.dataset.category.split(', ').includes(s.value));</script>'''
    (root/"source-catalog.html").write_text(page,encoding="utf-8")
    print(json.dumps({"ok":True,"sources":len(out),"scanned_pages":sum(x['scanned_pages'] for x in out),"low_text_pages":sum(len(x['low_text_pages']) for x in out),"thumbnails":sum(1 for _ in thumbs.glob("*.png"))},ensure_ascii=False))
if __name__=="__main__":
    try: main()
    except Exception as e: print(json.dumps({"ok":False,"error":f"{type(e).__name__}: {e}"},ensure_ascii=False)); raise SystemExit(1)
