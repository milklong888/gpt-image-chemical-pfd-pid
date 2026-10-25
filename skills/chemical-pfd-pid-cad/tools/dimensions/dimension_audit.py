"""Read-only native DIMENSION audit; no geometry repair, font substitution or CAD engine.

Classification/readout organization informed by kasc0206/dwg-reader-skill,
commit 8b04d54231700a0131073639ca0da02e20e45391 (MIT).
Copyright (c) 2026 DWG Reader Skill contributors. See THIRD_PARTY_NOTICES.md.
This implementation uses ezdxf APIs directly; upstream nearest-object inference,
text replacement and the reversed type 5/6 map are deliberately not reused.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import ezdxf
from ezdxf.entities import DimStyle
from ezdxf.math import Vec3
from ezdxf.render.dim_base import format_text

TYPES = {0: "linear_rotated", 1: "aligned", 2: "angular_2line",
         3: "diameter", 4: "radius", 5: "angular_3point", 6: "ordinate",
         8: "arc_length"}
SUPPORTED = {0, 1, 2, 3, 4, 5}
REQUIRED_POINTS = {0: ("defpoint", "defpoint2", "defpoint3"),
                   1: ("defpoint", "defpoint2", "defpoint3"),
                   2: ("defpoint", "defpoint2", "defpoint3", "defpoint4"),
                   3: ("defpoint", "defpoint4"), 4: ("defpoint", "defpoint4"),
                   5: ("defpoint", "defpoint2", "defpoint3", "defpoint4")}
POINTS = ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5",
          "text_midpoint", "insert", "extrusion")
NUMERIC = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, Vec3)):
        return [plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def finding(target, code, detail, severity="review"):
    target["findings"].append({"code": code, "severity": severity, "detail": plain(detail)})


def style_snapshot(entity, doc, result):
    name = entity.dxf.get("dimstyle", "Standard")
    snapshot = {"name": name, "exists": name in doc.dimstyles,
                "explicit_base": {}, "overrides": {}, "effective": {},
                "effective_origins": {}, "text_style": None}
    try:
        snapshot["raw_acad_dstyle"] = plain(list(entity.get_xdata_list("ACAD", "DSTYLE")))
    except ezdxf.DXFValueError:
        snapshot["raw_acad_dstyle"] = []
    if not snapshot["exists"]:
        finding(result, "DIMSTYLE_MISSING", name, "error")
        return snapshot
    base = doc.dimstyles.get(name)
    snapshot["explicit_base"] = plain(base.dxf.all_existing_dxf_attribs())
    try:
        override = entity.override()
        snapshot["overrides"] = plain(override.dimstyle_attribs)
        # The fallback below is each registered DXF attribute default, not a
        # chosen project style. Origins keep this distinction inspectable.
        for key in DimStyle.DXFATTRIBS._attribs:
            if not key.startswith("dim") or key.endswith("_handle"):
                continue
            snapshot["effective"][key] = plain(override.get(key, DimStyle.DXFATTRIBS.get(key).default))
            snapshot["effective_origins"][key] = (
                "entity_override" if key in override.dimstyle_attribs else
                "base_style_explicit" if base.dxf.hasattr(key) else "ezdxf_dxf_attribute_default")
    except Exception as exc:
        finding(result, "STYLE_READ_FAILED", str(exc), "error")
        return snapshot
    text_style = snapshot["effective"].get("dimtxsty")
    if not text_style:
        finding(result, "TEXT_STYLE_UNRESOLVED", "No explicit effective dimtxsty; no font was invented.")
    elif text_style not in doc.styles:
        finding(result, "TEXT_STYLE_MISSING", text_style, "error")
    else:
        snapshot["text_style"] = plain(doc.styles.get(text_style).dxf.all_existing_dxf_attribs())
        snapshot["font_file_availability"] = "not_checked_by_this_reader"
    return snapshot


def compare_numeric_text(result, tolerance):
    raw = result["raw_text"]
    if raw is None or raw in ("", "<>"):
        result["text_mode"] = "automatic"
        return
    if raw.isspace():
        result["text_mode"] = "suppressed_or_whitespace"
        finding(result, "TEXT_SUPPRESSED", repr(raw))
        return
    if "<>" in raw:
        result["text_mode"] = "measurement_placeholder_template"
        return
    result["text_mode"] = "literal_override"
    # Never strip MTEXT controls, units, tolerances or engineering prefixes
    # into a misleading bare number. Those require a source-aware review.
    if not NUMERIC.fullmatch(raw.strip()):
        finding(result, "LITERAL_TEXT_REQUIRES_REVIEW", raw)
        return
    number = float(raw)
    result["numeric_text_override"] = number
    candidate = result.get("rounded_primary_numeric_value")
    if candidate is None:
        finding(result, "NUMERIC_COMPARISON_UNAVAILABLE", result.get("comparison_limitation"))
        return
    difference = number - candidate
    result["numeric_comparison"] = {"literal_minus_comparison_value": difference,
                                    "basis": "primary value after effective DIMRND and decimal precision",
                                    "absolute_tolerance": tolerance}
    if not math.isclose(number, candidate, abs_tol=tolerance, rel_tol=1e-9):
        finding(result, "NUMERIC_OVERRIDE_DIFFERENCE", {
            "literal": number, "comparison_value": candidate, "difference": difference,
            "meaning": "Review against source; not proof the engineering dimension is wrong."})


def audit_dimension(entity, doc, context, tolerance):
    code = entity.dimtype
    result = {"handle": entity.dxf.handle, "entity_type": entity.dxftype(),
              "context": context, "layer": entity.dxf.layer,
              "type_code": code, "type_name": TYPES.get(code, "unknown"),
              "raw_dimtype_with_flags": entity.dxf.get("dimtype"),
              "supported_for_numeric_audit": code in SUPPORTED and entity.dxftype() == "DIMENSION",
              "raw_text": entity.dxf.get("text"), "findings": [],
              "definition_points": {k: plain(entity.dxf.get(k)) for k in POINTS},
              "angles": {k: entity.dxf.get(k) for k in
                         ("angle", "text_rotation", "horizontal_direction", "oblique_angle")},
              "cached_actual_measurement": entity.dxf.get("actual_measurement"),
              "association": {"status": "unverified", "native_entity_does_not_prove_association": True,
                              "reactor_handles": plain(entity.get_reactors())}}
    if context["kind"] == "block_definition":
        finding(result, "BLOCK_INSTANCE_TRANSFORMS_NOT_AUDITED", context["name"])
    if entity.is_dimensional_constraint:
        result["supported_for_numeric_audit"] = False
        finding(result, "DIMENSIONAL_CONSTRAINT_UNSUPPORTED", entity.dxf.layer)
    if not result["supported_for_numeric_audit"]:
        finding(result, "DIMENSION_TYPE_UNSUPPORTED", {"type": code, "entity": entity.dxftype()})
    missing = [p for p in REQUIRED_POINTS.get(code, ()) if not entity.dxf.hasattr(p)]
    if missing:
        finding(result, "DEFINITION_POINTS_MISSING", missing, "error")
    block_name = entity.dxf.get("geometry")
    result["geometry_block"] = {"name": block_name, "exists": bool(block_name and block_name in doc.blocks)}
    if not result["geometry_block"]["exists"]:
        finding(result, "DIMENSION_GRAPHICS_MISSING", block_name, "error")
    # Call the native API even for an unsupported subtype, but do not claim
    # its result is supported by this audit's numeric acceptance rules.
    measurement = None
    try:
        measurement = entity.get_measurement()
        result["get_measurement"] = plain(measurement)
        result["measurement_unit"] = "degree" if code in (2, 5) else (
            "drawing_unit_vector" if code == 6 else "drawing_unit")
    except Exception as exc:
        result["get_measurement"] = None
        finding(result, "MEASUREMENT_FAILED", str(exc), "error")
    result["style"] = style_snapshot(entity, doc, result)
    effective = result["style"]["effective"]
    factor = effective.get("dimlfac")
    result["scales"] = {"dimlfac": factor, "dimscale": effective.get("dimscale"),
                        "note": "dimscale controls annotation size; it is not a measurement multiplier."}
    scalar = isinstance(measurement, (int, float)) and math.isfinite(measurement)
    usable = scalar and result["supported_for_numeric_audit"] and not missing
    if code == 1 and not missing:
        point_distance = (entity.dxf.defpoint3 - entity.dxf.defpoint2).magnitude
        result["aligned_definition_point_distance_diagnostic"] = point_distance
        if scalar and not math.isclose(measurement, point_distance, rel_tol=1e-9, abs_tol=tolerance):
            usable = False
            finding(result, "ALIGNED_API_MEASUREMENT_DISAGREEMENT", {
                "api": measurement, "definition_point_distance": point_distance,
                "action": "No numeric acceptance; confirm in native CAD. No source value changed."})
    result["comparison_value"] = None
    result["comparison_limitation"] = "Unsupported or unresolved measurement/style."
    if usable and code in (0, 1, 3, 4) and isinstance(factor, (int, float)) and factor > 0:
        result["measurement_times_dimlfac"] = measurement * factor
        if effective.get("dimlunit") == 2:
            result["comparison_value"] = measurement * factor
            result["comparison_limitation"] = None
        else:
            result["comparison_limitation"] = "unsupported_display_compare: only decimal linear formatting is normalized."
    elif usable and code in (2, 5):
        result["measurement_times_dimlfac"] = None
        if effective.get("dimaunit") == 0:
            result["comparison_value"] = measurement
            result["comparison_limitation"] = None
        else:
            result["comparison_limitation"] = "unsupported_display_compare: only decimal-degree numeric overrides are compared."
    elif usable and factor is not None and factor <= 0:
        result["comparison_limitation"] = "Nonpositive dimlfac needs viewport/model-paper semantics review."
        finding(result, "NONPOSITIVE_DIMLFAC_NOT_NORMALIZED", factor)
    result["rounded_primary_numeric_text"] = None
    result["rounded_primary_numeric_value"] = None
    result["display_compare_status"] = "unsupported_display_compare"
    if result["comparison_value"] is not None:
        angular = code in (2, 5)
        dec = effective.get("dimadec" if angular else "dimdec")
        if dec is None or dec < 0:
            dec = effective.get("dimdec", 2)
        rounding = 0 if angular else effective.get("dimrnd", 0)
        # Reuse the pinned ezdxf formatter instead of implementing a second
        # unit/rounding engine. This is the primary numeric part, not the
        # complete text with prefixes, tolerances, fonts or MTEXT effects.
        normalized = format_text(result["comparison_value"], dimrnd=rounding or None,
                                 dimdec=int(dec), dimzin=effective.get("dimzin", 0), dimdsep=".")
        result["rounded_primary_numeric_value"] = float(normalized)
        separator = effective.get("dimdsep", 46)
        result["rounded_primary_numeric_text"] = normalized.replace(".", chr(separator))
        result["display_compare_status"] = "decimal_primary_value_compared"
    compare_numeric_text(result, tolerance)
    return result


def check_expectations(report, expectations, base_dir, tolerance):
    report["expectation_contract"] = plain(expectations)
    if set(expectations) - {"drawing_sha256", "source_files", "dimensions", "note"}:
        finding(report, "EXPECTATION_SCHEMA_UNKNOWN_FIELDS", sorted(set(expectations) -
                {"drawing_sha256", "source_files", "dimensions", "note"}), "error")
    expected_hash = expectations.get("drawing_sha256")
    if expected_hash and report["input"]["sha256"].lower() != expected_hash.lower():
        finding(report, "DRAWING_SHA256_MISMATCH", {"expected": expected_hash,
                "actual": report["input"]["sha256"]}, "error")
    report["source_file_checks"] = []
    for source in expectations.get("source_files", []):
        source_path = Path(source["path"])
        if not source_path.is_absolute():
            source_path = base_dir / source_path
        actual = sha256(source_path) if source_path.is_file() else None
        checked = {**source, "resolved_path": str(source_path.resolve()), "actual_sha256": actual}
        report["source_file_checks"].append(checked)
        if actual != source["sha256"].lower():
            finding(report, "SOURCE_FILE_MISMATCH", checked, "error")
    records = {d["handle"].upper(): d for d in report["dimensions"]}
    for handle, expected in expectations.get("dimensions", {}).items():
        record = records.get(handle.upper())
        if record is None:
            finding(report, "EXPECTED_DIMENSION_MISSING", handle, "error")
            continue
        # source_anchor is provenance supplied by a reviewer; this script
        # does not prove its semantic correspondence to the dimension.
        record["declared_source_anchor"] = expected.get("source_anchor")
        allowed = {"raw_text", "type_code", "dimstyle", "measurement", "effective", "source_anchor"}
        if set(expected) - allowed:
            finding(record, "EXPECTATION_SCHEMA_UNKNOWN_FIELDS", sorted(set(expected) - allowed), "error")
        for key, value in expected.items():
            if key == "source_anchor":
                continue
            actual = (record["style"]["name"] if key == "dimstyle" else
                      record["get_measurement"] if key == "measurement" else record.get(key))
            pairs = [(key, value, actual)]
            if key == "effective":
                pairs = [("effective." + k, v, record["style"]["effective"].get(k)) for k, v in value.items()]
            for label, wanted, got in pairs:
                numeric = isinstance(wanted, (float, int)) and isinstance(got, (float, int))
                matches = math.isclose(wanted, got, rel_tol=1e-9, abs_tol=tolerance) if numeric else wanted == got
                if not matches:
                    finding(record, "EXPECTED_SOURCE_FIELD_MISMATCH", {
                        "field": label, "expected": wanted, "actual": got,
                        "source_anchor": expected.get("source_anchor")}, "error")


def audit_file(path, expectation_path=None, tolerance=1e-6):
    path = Path(path).resolve()
    original_hash = sha256(path)
    doc = ezdxf.readfile(path)  # no ignore/recover: unreadable input must fail
    report = {"schema": "native-dimension-audit-0.1-candidate", "ezdxf_version": ezdxf.__version__,
              "input": {"path": str(path), "sha256": original_hash, "dxf_version": doc.dxfversion},
              "drawing_header": {k: plain(doc.header.get(k)) for k in
                    ("$INSUNITS", "$MEASUREMENT", "$LUNITS", "$LUPREC", "$AUNITS", "$AUPREC", "$DIMASSOC")},
              "findings": [], "dimensions": [],
              "boundaries": ["read-only; no source dimension correction",
                  "non-scale equipment drawings must retain source dimensions",
                  "native DIMENSION and DIMASSOC do not prove geometry association",
                  "no nearest-object inference; block insert transforms are not expanded",
                  "no source PDF/table interpretation, collision/layout or font availability verdict",
                  "matching source hashes do not prove the declared dimension-to-source correspondence",
                  "geometry block contents can be stale; native CAD save/reopen and visual review remain necessary"]}
    layout_names = set()
    for layout in doc.layouts:
        layout_names.add(layout.block_record_name.casefold())
        for entity in layout.query("DIMENSION ARC_DIMENSION"):
            report["dimensions"].append(audit_dimension(entity, doc,
                {"kind": "layout", "name": layout.name}, tolerance))
    for block in doc.blocks:
        if block.name.casefold() in layout_names:
            continue
        for entity in block.query("DIMENSION ARC_DIMENSION"):
            report["dimensions"].append(audit_dimension(entity, doc,
                {"kind": "block_definition", "name": block.name}, tolerance))
    if not report["dimensions"]:
        finding(report, "NO_NATIVE_DIMENSIONS", "Exploded line/text graphics are not audited as native dimensions.")
    if doc.dxfversion == "AC1009":
        finding(report, "R12_STYLE_LIMITATION", "Some modern DIMSTYLE fields are unavailable in R12.")
    if expectation_path:
        ep = Path(expectation_path).resolve()
        check_expectations(report, json.loads(ep.read_text(encoding="utf-8-sig")), ep.parent, tolerance)
    else:
        report["expectation_contract"] = None
    after_hash = sha256(path)
    report["read_only_input_hash_unchanged"] = after_hash == original_hash
    if after_hash != original_hash:
        finding(report, "INPUT_CHANGED_DURING_AUDIT", after_hash, "error")
    all_findings = report["findings"] + [f for d in report["dimensions"] for f in d["findings"]]
    report["summary"] = {"dimension_count": len(report["dimensions"]),
        "by_type": dict(Counter(d["type_name"] for d in report["dimensions"])),
        "findings_by_code": dict(Counter(f["code"] for f in all_findings)),
        "status": "review_required" if all_findings else "machine_checks_clear_visual_review_required"}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drawing", type=Path)
    parser.add_argument("--expect", type=Path, help="explicit source/handle expectation contract JSON")
    parser.add_argument("--out", type=Path, help="JSON report; input DXF is never saved")
    parser.add_argument("--tolerance", type=float, default=1e-6)
    args = parser.parse_args()
    if not math.isfinite(args.tolerance) or args.tolerance < 0:
        parser.error("--tolerance must be finite and nonnegative")
    if args.out and args.out.resolve() == args.drawing.resolve():
        parser.error("--out must not overwrite the input drawing")
    try:
        report = audit_file(args.drawing, args.expect, args.tolerance)
    except Exception as exc:
        print(json.dumps({"status": "audit_failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 2 if report["summary"]["findings_by_code"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
