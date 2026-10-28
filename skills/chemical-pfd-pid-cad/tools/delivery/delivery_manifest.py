"""Source-bound delivery consistency records; no CAD control or publication.

Standard library only. Importing this module does not read or write files.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

FILES = ("drawing_dxf", "semantic_json", "native_dwg", "native_pdf", "native_readback_dxf")
EXPORTS = ("native_dwg", "native_pdf", "native_readback_dxf")
SCOPES = {"geometry", "typography", "native_visual", "data"}
OUTPUTS = {"drawing_data": "drawing-data.json", "streams_csv": "streams.csv", "reading_note": "reading-note.txt"}
LIMITATION = ("Consistency precondition only. Does not prove observation extraction authenticity, "
              "actual glyphs, GB compliance, engineering approval or release. No automatic publication or CAD control.")


class Rejected(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Rejected(code)


def exact(value, keys, code="FIELDS"):
    require(type(value) is dict and set(value) == set(keys), code)


def text(value, code="NONEMPTY_STRING"):
    require(type(value) is str and bool(value.strip()), code)
    require(not any(ord(c) < 32 and c not in "\n\r\t" for c in value), code)
    return value


def string_list(value, nonempty=False):
    require(type(value) is list and (bool(value) or not nonempty), "STRING_LIST")
    for item in value:
        text(item)
    require(len(value) == len(set(value)), "DUPLICATE_LIST_ITEM")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY: " + key)
        result[key] = value
    return result


def parse(data):
    def constant(value):
        raise Rejected("NONFINITE_JSON_NUMBER: " + value)
    try:
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Rejected("INVALID_JSON: " + str(exc)) from exc
    # Also reject finite-looking JSON exponents which Python converts to infinity.
    def finite_tree(item):
        if type(item) is float:
            import math
            require(math.isfinite(item), "NONFINITE_JSON_NUMBER")
        elif type(item) is dict:
            for child in item.values():
                finite_tree(child)
        elif type(item) is list:
            for child in item:
                finite_tree(child)
    finite_tree(value)
    return value


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf8")


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def identity(path, data=None):
    path = Path(path).resolve()
    data = path.read_bytes() if data is None else data
    return {"path": str(path), "sha256": hash_bytes(data)}


def read_ref(ref, base):
    exact(ref, {"path", "sha256"}, "FILE_REFERENCE_FIELDS")
    text(ref["path"])
    require(type(ref["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]), "SHA256_FORMAT")
    path = Path(ref["path"])
    path = path if path.is_absolute() else base / path
    path = path.resolve()
    data = path.read_bytes()
    require(bool(data), "EMPTY_FILE: " + str(path))
    actual = identity(path, data)
    require(actual["sha256"] == ref["sha256"], "FILE_CHANGED: " + str(path))
    return actual, data


def load_source(data):
    source = parse(data)
    exact(source, {"schema", "streams"}, "SOURCE_FIELDS")
    require(source["schema"] == "delivery-source/v1", "SOURCE_SCHEMA")
    require(type(source["streams"]) is list and source["streams"], "SOURCE_STREAMS")
    streams = {}
    for row in source["streams"]:
        exact(row, {"id", "fields", "units", "source_ref"}, "SOURCE_STREAM_FIELDS")
        sid = text(row["id"])
        require(sid not in streams, "DUPLICATE_STREAM: " + sid)
        text(row["source_ref"], "SOURCE_REFERENCE_REQUIRED")
        require(type(row["fields"]) is dict and row["fields"], "STREAM_FIELDS_REQUIRED")
        require(type(row["units"]) is dict and set(row["units"]) == set(row["fields"]), "FIELD_UNIT_COVERAGE")
        for key, value in row["fields"].items():
            text(key)
            text(value, "FIELD_MUST_BE_NONEMPTY_STRING")
            require(value.strip().casefold() not in {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}, "NONFINITE_FIELD_STRING")
            text(row["units"][key], "ADOPTED_UNIT_REQUIRED")
        streams[sid] = row
    return streams


def source_basis(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = parse(manifest_bytes)
    exact(manifest, {"schema", "source_data", "exclusions"}, "PREPARE_MANIFEST_FIELDS")
    require(manifest["schema"] == "delivery-prepare/v1", "PREPARE_SCHEMA")
    source_ref, source_bytes = read_ref(manifest["source_data"], manifest_path.parent)
    streams = load_source(source_bytes)
    require(type(manifest["exclusions"]) is list, "EXCLUSIONS_LIST")
    exclusions = {}
    for row in manifest["exclusions"]:
        exact(row, {"stream_id", "reason", "authority"}, "EXCLUSION_FIELDS")
        sid = text(row["stream_id"])
        text(row["reason"], "EXCLUSION_REASON_REQUIRED")
        text(row["authority"], "EXCLUSION_AUTHORITY_REQUIRED")
        require(sid in streams, "UNKNOWN_EXCLUSION: " + sid)
        require(sid not in exclusions, "DUPLICATE_EXCLUSION: " + sid)
        exclusions[sid] = row
    display = sorted(set(streams) - set(exclusions))
    require(display, "EMPTY_DISPLAY_SET")
    return identity(manifest_path, manifest_bytes), source_ref, streams, exclusions, display


def render(run_id, manifest_ref, source_ref, streams, exclusions, display):
    drawing = {"schema": "delivery-drawing-data/v1", "run_id": run_id,
               "prepare_manifest": manifest_ref, "source_data": source_ref,
               "display_stream_ids": display, "streams": [streams[sid] for sid in display],
               "excluded_streams": [exclusions[sid] for sid in sorted(exclusions)], "boundary": LIMITATION}
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["run_id", "stream_id", "field", "value", "adopted_unit", "source_ref"])
    for sid in display:
        for field in sorted(streams[sid]["fields"]):
            writer.writerow([run_id, sid, field, streams[sid]["fields"][field], streams[sid]["units"][field], streams[sid]["source_ref"]])
    note = ["Delivery reading note", "Run: " + run_id, "Source: " + source_ref["path"],
            "Source SHA256: " + source_ref["sha256"],
            "Displayed: " + str(len(display)) + " / source: " + str(len(streams)),
            "Displayed IDs: " + ", ".join(display), "Exclusions (explicit authority; no implicit omissions):"]
    note.extend(sid + " | " + exclusions[sid]["reason"] + " | " + exclusions[sid]["authority"] for sid in sorted(exclusions))
    if not exclusions:
        note.append("None")
    note.extend(["Values are literal adopted strings; units are separately bound. Do not reformat, normalize or infer missing values.", LIMITATION])
    return {"drawing_data": encoded(drawing), "streams_csv": buffer.getvalue().encode("utf8"),
            "reading_note": ("\n".join(note) + "\n").encode("utf8")}


def assert_unchanged(ref):
    require(identity(ref["path"]) == ref, "INPUT_CHANGED_DURING_OPERATION: " + ref["path"])


def distinct_files(refs):
    """Reject physical aliases, including hardlinks; equal content alone is legal."""
    prior = []
    for role, ref in refs.items():
        path = Path(ref["path"])
        for previous_role, previous_path in prior:
            require(not path.samefile(previous_path), "FILE_ROLE_IDENTITY_REUSED: " + previous_role + "/" + role)
        prior.append((role, path))


def prepare(manifest_path, run_id, out_root):
    require(type(run_id) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id), "RUN_ID_FORMAT")
    manifest_ref, source_ref, streams, exclusions, display = source_basis(manifest_path)
    content = render(run_id, manifest_ref, source_ref, streams, exclusions, display)
    folder = Path(out_root).resolve() / run_id
    require(not folder.exists(), "RUN_ALREADY_EXISTS")
    assert_unchanged(manifest_ref)
    assert_unchanged(source_ref)
    folder.parent.mkdir(parents=True, exist_ok=True)
    folder.mkdir()  # Exclusive reservation; never reuse an existing run.
    outputs = {}
    for key, name in OUTPUTS.items():
        target = folder / name
        with target.open("xb") as handle:
            handle.write(content[key])
        outputs[key] = identity(target, content[key])
    record = {"schema": "delivery-prepared/v1", "run_id": run_id, "prepare_manifest": manifest_ref,
              "source_data": source_ref, "display_stream_ids": display, "excluded_stream_ids": sorted(exclusions),
              "outputs": outputs, "boundary": LIMITATION}
    assert_unchanged(manifest_ref)
    assert_unchanged(source_ref)
    with (folder / "prepare-record.json").open("xb") as handle:
        handle.write(encoded(record))
    return record


def checked_prepared(ref, base, run_id):
    record_ref, data = read_ref(ref, base)
    record = parse(data)
    exact(record, {"schema", "run_id", "prepare_manifest", "source_data", "display_stream_ids", "excluded_stream_ids", "outputs", "boundary"}, "PREPARED_FIELDS")
    require(record["schema"] == "delivery-prepared/v1" and record["run_id"] == run_id, "PREPARED_RUN_MISMATCH")
    string_list(record["display_stream_ids"], True)
    string_list(record["excluded_stream_ids"])
    mref, _ = read_ref(record["prepare_manifest"], Path(record_ref["path"]).parent)
    manifest_ref, source_ref, streams, exclusions, display = source_basis(mref["path"])
    require(record["source_data"] == source_ref and record["prepare_manifest"] == manifest_ref, "PREPARED_SOURCE_IDENTITY_MISMATCH")
    require(record["display_stream_ids"] == display and record["excluded_stream_ids"] == sorted(exclusions), "PREPARED_SET_MISMATCH")
    require(record["boundary"] == LIMITATION, "PREPARED_BOUNDARY_MISMATCH")
    exact(record["outputs"], OUTPUTS, "PREPARED_OUTPUTS")
    expected = render(run_id, manifest_ref, source_ref, streams, exclusions, display)
    bound = {"prepare_record": record_ref, "prepare_manifest": manifest_ref, "source_data": source_ref}
    for key, name in OUTPUTS.items():
        output_ref, output_bytes = read_ref(record["outputs"][key], Path(record_ref["path"]).parent)
        require(Path(output_ref["path"]) == Path(record_ref["path"]).parent / name, "PREPARED_OUTPUT_LOCATION")
        require(output_bytes == expected[key], "PREPARED_OUTPUT_CONTENT_MISMATCH: " + key)
        bound[key] = output_ref
    return bound, streams, display


def handles(value):
    string_list(value, True)
    require(all(re.fullmatch(r"[0-9A-Fa-f]+", item) for item in value), "TEXT_HANDLES_REQUIRED")


def audit(manifest_path, output):
    manifest_path = Path(manifest_path).resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = parse(manifest_bytes)
    exact(manifest, {"schema", "run_id", "prepare_record", "files", "observations", "exports", "review_report"}, "AUDIT_MANIFEST_FIELDS")
    require(manifest["schema"] == "delivery-audit/v1", "AUDIT_SCHEMA")
    run_id = text(manifest["run_id"])
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id), "RUN_ID_FORMAT")
    bound, streams, display = checked_prepared(manifest["prepare_record"], manifest_path.parent, run_id)
    exact(manifest["files"], FILES, "DELIVERY_FILES_REQUIRED")
    artifact_content = {}
    for key in FILES:
        bound[key], artifact_bytes = read_ref(manifest["files"][key], manifest_path.parent)
        artifact_content[key] = artifact_bytes
    bound["observations"], obs_bytes = read_ref(manifest["observations"], manifest_path.parent)
    bound["exports"], export_bytes = read_ref(manifest["exports"], manifest_path.parent)
    review_ref, review_bytes = read_ref(manifest["review_report"], manifest_path.parent)
    audit_ref = identity(manifest_path, manifest_bytes)
    protected = dict(bound, review_report=review_ref, audit_manifest=audit_ref)
    # All these files exist. samefile rejects symlink/hardlink aliases without
    # mistaking two independently stored byte-identical files for one file.
    distinct_files(protected)
    output = Path(output)
    if output.exists():
        distinct_files(dict(protected, consistency_output=identity(output)))
    semantic = parse(artifact_content["semantic_json"])
    require(type(semantic) is dict and semantic, "SEMANTIC_JSON_OBJECT_REQUIRED")
    observations = parse(obs_bytes)
    exact(observations, {"schema", "run_id", "native_dwg_sha256", "native_readback_dxf_sha256", "streams"}, "OBSERVATION_FIELDS")
    require(observations["schema"] == "delivery-observations/v1" and observations["run_id"] == run_id, "OBSERVATION_RUN")
    require(observations["native_dwg_sha256"] == bound["native_dwg"]["sha256"] and observations["native_readback_dxf_sha256"] == bound["native_readback_dxf"]["sha256"], "OBSERVATION_FILE_BINDING")
    require(type(observations["streams"]) is list, "OBSERVATION_STREAM_LIST")
    observed = {}
    for row in observations["streams"]:
        exact(row, {"id", "id_handles", "fields"}, "OBSERVED_STREAM_FIELDS")
        sid = text(row["id"])
        require(sid not in observed, "DUPLICATE_OBSERVED_STREAM: " + sid)
        require(sid in display, "EXTRA_OBSERVED_STREAM: " + sid)
        handles(row["id_handles"])
        exact(row["fields"], streams[sid]["fields"], "OBSERVED_FIELD_SET: " + sid)
        for key, value in row["fields"].items():
            exact(value, {"text", "adopted_unit", "handles"}, "OBSERVED_VALUE_FIELDS")
            text(value["text"])
            text(value["adopted_unit"])
            handles(value["handles"])
            require(value["text"] == streams[sid]["fields"][key] and value["adopted_unit"] == streams[sid]["units"][key], "OBSERVED_VALUE_MISMATCH: " + sid + "/" + key)
        observed[sid] = row
    require(set(observed) == set(display), "MISSING_OBSERVED_STREAMS: " + ",".join(sorted(set(display) - set(observed))))
    exports = parse(export_bytes)
    exact(exports, {"schema", "run_id", "outputs"}, "EXPORT_FIELDS")
    require(exports["schema"] == "delivery-exports/v1" and exports["run_id"] == run_id, "EXPORT_RUN")
    exact(exports["outputs"], EXPORTS, "EXPORT_OUTPUT_COVERAGE")
    for key in EXPORTS:
        row = exports["outputs"][key]
        exact(row, {"file", "exit_code", "audit"}, "EXPORT_OUTPUT_FIELDS")
        exact(row["audit"], {"ok"}, "EXPORT_AUDIT_FIELDS")
        require(type(row["exit_code"]) is int and row["exit_code"] == 0, "EXPORT_EXIT_CODE: " + key)
        require(row["audit"]["ok"] is True, "EXPORT_AUDIT_NOT_OK: " + key)
        actual, _ = read_ref(row["file"], Path(bound["exports"]["path"]).parent)
        require(actual == bound[key], "EXPORT_FILE_MISMATCH: " + key)
    review = parse(review_bytes)
    exact(review, {"schema", "run_id", "bindings", "scopes"}, "REVIEW_FIELDS")
    require(review["schema"] == "delivery-review/v1" and review["run_id"] == run_id, "REVIEW_RUN")
    require(type(review["bindings"]) is dict and review["bindings"] == bound, "REVIEW_DELIVERY_IDENTITIES_MISMATCH")
    require(type(review["scopes"]) is list, "REVIEW_SCOPES_LIST")
    seen = set()
    for row in review["scopes"]:
        exact(row, {"scope", "status", "reviewer", "observation"}, "REVIEW_SCOPE_FIELDS")
        require(type(row["scope"]) is str and row["scope"] in SCOPES and row["scope"] not in seen, "REVIEW_SCOPE_COVERAGE")
        require(row["status"] == "pass", "REVIEW_NOT_PASS")
        text(row["reviewer"], "REVIEWER_REQUIRED")
        text(row["observation"], "REVIEW_OBSERVATION_REQUIRED")
        seen.add(row["scope"])
    require(seen == SCOPES, "REVIEW_SCOPE_COVERAGE")
    for ref in list(bound.values()) + [review_ref]:
        assert_unchanged(ref)
    assert_unchanged(audit_ref)
    distinct_files(protected)
    result = {"schema": "delivery-consistency/v1", "status": "consistency_passed", "run_id": run_id,
              "audit_manifest": audit_ref, "bindings": bound, "review_report": review_ref,
              "display_stream_ids": display, "observed_stream_ids": sorted(observed), "boundary": LIMITATION}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(encoded(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--manifest", required=True)
    prep.add_argument("--run-id", required=True)
    prep.add_argument("--out-root", required=True)
    check = sub.add_parser("audit")
    check.add_argument("--manifest", required=True)
    check.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.manifest, args.run_id, args.out_root) if args.command == "prepare" else audit(args.manifest, args.output)
        print(json.dumps({"ok": True, "run_id": result["run_id"], "status": result.get("status", "prepared")}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
