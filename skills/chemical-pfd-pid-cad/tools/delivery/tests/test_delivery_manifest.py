"""Finite synthetic counterexamples for the delivery consistency boundary.

These tests do not exercise CAD, font rendering, standards or engineering review.
"""
import copy
import importlib.util
import json
import subprocess
import sys
import os
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "delivery_manifest.py"
SPEC = importlib.util.spec_from_file_location("delivery_manifest", MODULE)
dm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dm)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = {"schema": "delivery-source/v1", "streams": [
            {"id": sid, "fields": {"T": value, "F": "12.00"}, "units": {"T": "K", "F": "kmol/h"},
             "source_ref": "Synthetic case source, table row " + sid}
            for sid, value in (("S1", "300.000"), ("S2", "310.000"), ("ZERO", "0.000"))]}
        self.source_path = self.write("source.json", self.source)
        self.prepare_path = self.write("prepare.json", {"schema": "delivery-prepare/v1", "source_data": dm.identity(self.source_path),
            "exclusions": [{"stream_id": "ZERO", "reason": "Explicit synthetic zero boundary excluded from display.",
                            "authority": "Synthetic project decision A, not an engineering approval."}]})
        dm.prepare(self.prepare_path, "runA", self.root / "runs")
        self.record = self.root / "runs/runA/prepare-record.json"
        self.files = {key: dm.identity(self.write(key + ".synthetic", ("synthetic " + key).encode())) for key in dm.FILES}
        self.files["semantic_json"] = dm.identity(self.write("semantic_json.synthetic", {"synthetic_semantics_only": True}))
        self.obs = {"schema": "delivery-observations/v1", "run_id": "runA",
            "native_dwg_sha256": self.files["native_dwg"]["sha256"],
            "native_readback_dxf_sha256": self.files["native_readback_dxf"]["sha256"],
            "streams": [{"id": row["id"], "id_handles": ["AA"],
                "fields": {key: {"text": value, "adopted_unit": row["units"][key], "handles": ["AB"]}
                           for key, value in row["fields"].items()}} for row in self.source["streams"][:2]]}
        self.obs_path = self.write("observations.json", self.obs)
        self.exports = {"schema": "delivery-exports/v1", "run_id": "runA", "outputs": {
            key: {"file": self.files[key], "exit_code": 0, "audit": {"ok": True}} for key in dm.EXPORTS}}
        self.exports_path = self.write("exports.json", self.exports)
        bound, _, _ = dm.checked_prepared(dm.identity(self.record), self.root, "runA")
        bound.update(self.files)
        bound.update(observations=dm.identity(self.obs_path), exports=dm.identity(self.exports_path))
        self.review = {"schema": "delivery-review/v1", "run_id": "runA", "bindings": bound,
            "scopes": [{"scope": scope, "status": "pass", "reviewer": "Synthetic independent reviewer",
                        "observation": "Synthetic software-fixture observation only."} for scope in sorted(dm.SCOPES)]}
        self.review_path = self.write("review.json", self.review)
        self.audit_manifest = {"schema": "delivery-audit/v1", "run_id": "runA", "prepare_record": dm.identity(self.record),
            "files": self.files, "observations": dm.identity(self.obs_path), "exports": dm.identity(self.exports_path),
            "review_report": dm.identity(self.review_path)}
        self.audit_path = self.write("audit.json", self.audit_manifest)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if type(value) is bytes else dm.encoded(value))
        return path

    def save_audit(self):
        self.write("audit.json", self.audit_manifest)

    def observations_changed(self):
        self.write("observations.json", self.obs)
        self.audit_manifest["observations"] = dm.identity(self.obs_path)
        self.save_audit()

    def rejected(self, code):
        out = self.root / "consistency.json"
        with self.assertRaisesRegex(dm.Rejected, code):
            dm.audit(self.audit_path, out)
        self.assertFalse(out.exists())

    def test_valid_set_is_source_minus_explicit_exclusion(self):
        result = dm.audit(self.audit_path, self.root / "consistency.json")
        self.assertEqual(result["display_stream_ids"], ["S1", "S2"])
        self.assertEqual(result["status"], "consistency_passed")
        note = (self.record.parent / "reading-note.txt").read_text("utf8")
        self.assertIn("2 / source: 3", note)
        self.assertIn("ZERO", note)

    def test_missing_last_stream_even_with_plausible_old_count(self):
        self.obs["streams"].pop()
        self.observations_changed()
        self.rejected("MISSING_OBSERVED_STREAMS")

    def test_excluded_stream_cannot_reappear(self):
        extra = copy.deepcopy(self.obs["streams"][0])
        extra["id"] = "ZERO"
        self.obs["streams"].append(extra)
        self.observations_changed()
        self.rejected("EXTRA_OBSERVED_STREAM")

    def test_value_or_unit_change_fails_exact_comparison(self):
        original = copy.deepcopy(self.obs)
        for key, changed in (("text", "300.00"), ("adopted_unit", "degC")):
            with self.subTest(key=key):
                self.obs = copy.deepcopy(original)
                self.obs["streams"][0]["fields"]["T"][key] = changed
                self.observations_changed()
                self.rejected("OBSERVED_VALUE_MISMATCH")

    def test_duplicate_observed_id(self):
        self.obs["streams"].append(copy.deepcopy(self.obs["streams"][0]))
        self.observations_changed()
        self.rejected("DUPLICATE_OBSERVED_STREAM")

    def test_old_review_rejects_new_delivery_identity(self):
        changed = self.write("native_pdf.synthetic", b"different final PDF")
        self.files["native_pdf"] = dm.identity(changed)
        self.exports["outputs"]["native_pdf"]["file"] = self.files["native_pdf"]
        self.write("exports.json", self.exports)
        self.audit_manifest["exports"] = dm.identity(self.exports_path)
        self.save_audit()
        self.rejected("REVIEW_DELIVERY_IDENTITIES_MISMATCH")

    def test_tampered_prepare_output_is_not_accepted_by_updated_hash(self):
        path = self.record.parent / "streams.csv"
        path.write_bytes(b"tampered CSV")
        record = dm.parse(self.record.read_bytes())
        record["outputs"]["streams_csv"] = dm.identity(path)
        self.record.write_bytes(dm.encoded(record))
        self.audit_manifest["prepare_record"] = dm.identity(self.record)
        self.save_audit()
        self.rejected("PREPARED_OUTPUT_CONTENT_MISMATCH")

    def test_bool_is_not_export_exit_integer(self):
        self.exports["outputs"]["native_pdf"]["exit_code"] = False
        self.write("exports.json", self.exports)
        self.audit_manifest["exports"] = dm.identity(self.exports_path)
        self.save_audit()
        self.rejected("EXPORT_EXIT_CODE")

    def test_failed_export_audit_is_not_review_override(self):
        self.exports["outputs"]["native_pdf"]["audit"]["ok"] = False
        self.write("exports.json", self.exports)
        self.audit_manifest["exports"] = dm.identity(self.exports_path)
        self.save_audit()
        self.rejected("EXPORT_AUDIT_NOT_OK")

    def test_missing_review_scope(self):
        self.review["scopes"].pop()
        self.write("review.json", self.review)
        self.audit_manifest["review_report"] = dm.identity(self.review_path)
        self.save_audit()
        self.rejected("REVIEW_SCOPE_COVERAGE")

    def test_semantic_json_cannot_be_malformed_or_boolean(self):
        self.files["semantic_json"] = dm.identity(self.write("semantic_json.synthetic", b"true"))
        self.save_audit()
        self.rejected("SEMANTIC_JSON_OBJECT_REQUIRED")

    def test_unknown_duplicate_and_blank_exclusions(self):
        base = dm.parse(self.prepare_path.read_bytes())
        for exclusions, code in (([{"stream_id": "NOPE", "reason": "x", "authority": "x"}], "UNKNOWN_EXCLUSION"),
                (base["exclusions"] * 2, "DUPLICATE_EXCLUSION"),
                ([dict(base["exclusions"][0], reason=" ")], "EXCLUSION_REASON_REQUIRED")):
            with self.subTest(code=code):
                self.write("invalid-prepare.json", dict(base, exclusions=exclusions))
                with self.assertRaisesRegex(dm.Rejected, code):
                    dm.prepare(self.root / "invalid-prepare.json", "invalid", self.root / "runs")

    def test_duplicate_source_null_bool_nan_and_duplicate_json_key(self):
        invalids = [b'{"schema":"delivery-source/v1","streams":NaN}',
                    b'{"schema":"delivery-source/v1","streams":1e999}',
                    b'{"schema":"delivery-source/v1","streams":[],"streams":[]}']
        for data in invalids:
            with self.subTest(data=data), self.assertRaises(dm.Rejected):
                dm.load_source(data)
        for value in (None, False, "", "NaN"):
            bad = copy.deepcopy(self.source)
            bad["streams"][0]["fields"]["T"] = value
            with self.subTest(value=value), self.assertRaises(dm.Rejected):
                dm.load_source(dm.encoded(bad))
        bad = copy.deepcopy(self.source)
        bad["streams"].append(copy.deepcopy(bad["streams"][0]))
        with self.assertRaisesRegex(dm.Rejected, "DUPLICATE_STREAM"):
            dm.load_source(dm.encoded(bad))

    def test_cli_preserves_failure_exit_and_creates_no_success_record(self):
        self.exports["outputs"]["native_pdf"]["exit_code"] = 1
        self.write("exports.json", self.exports)
        self.audit_manifest["exports"] = dm.identity(self.exports_path)
        self.save_audit()
        output = self.root / "cli-consistency.json"
        run = subprocess.run([sys.executable, "-B", str(MODULE), "audit", "--manifest", str(self.audit_path),
                              "--output", str(output)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("EXPORT_EXIT_CODE", run.stderr)
        self.assertFalse(output.exists())

    def test_import_has_no_file_writes(self):
        directory = self.root / "import-check"
        directory.mkdir()
        def state():
            return {str(p.relative_to(MODULE.parent)): p.read_bytes() for p in MODULE.parent.rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts}
        before = state()
        code = "import runpy,sys; runpy.run_path(sys.argv[1], run_name='import_probe')"
        run = subprocess.run([sys.executable, "-B", "-c", code, str(MODULE)], cwd=directory,
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(before, state())
        self.assertEqual(list(directory.iterdir()), [])

    def test_existing_run_and_audit_output_are_preserved(self):
        with self.assertRaisesRegex(dm.Rejected, "RUN_ALREADY_EXISTS"):
            dm.prepare(self.prepare_path, "runA", self.root / "runs")
        output = self.write("consistency.json", b"preserve me")
        with self.assertRaises(FileExistsError):
            dm.audit(self.audit_path, output)
        self.assertEqual(output.read_bytes(), b"preserve me")

    def test_direct_artifact_role_reuse_is_rejected(self):
        self.files["native_pdf"] = self.files["native_dwg"]
        self.save_audit()
        self.rejected("FILE_ROLE_IDENTITY_REUSED")

    def test_input_or_evidence_cannot_be_reused_as_artifact(self):
        prepared = dm.parse(self.record.read_bytes())
        protected = [dm.identity(self.source_path), dm.identity(self.prepare_path), dm.identity(self.record),
                     prepared["outputs"]["drawing_data"], prepared["outputs"]["streams_csv"], prepared["outputs"]["reading_note"],
                     dm.identity(self.obs_path), dm.identity(self.exports_path), dm.identity(self.review_path)]
        original = self.files["native_pdf"]
        for ref in protected:
            with self.subTest(path=ref["path"]):
                self.files["native_pdf"] = ref
                self.save_audit()
                self.rejected("FILE_ROLE_IDENTITY_REUSED")
        self.files["native_pdf"] = original

    def test_hardlink_artifact_role_reuse_is_rejected(self):
        alias = self.root / "native-pdf-alias.synthetic"
        try:
            os.link(self.files["native_dwg"]["path"], alias)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Hardlinks unavailable on this platform/filesystem: " + str(exc))
        self.files["native_pdf"] = dm.identity(alias)
        self.save_audit()
        self.rejected("FILE_ROLE_IDENTITY_REUSED")

    def test_equal_content_in_distinct_files_is_legal(self):
        # This fixture's files are synthetic; no DWG/PDF format claim is made.
        native_bytes = Path(self.files["native_dwg"]["path"]).read_bytes()
        self.files["native_pdf"] = dm.identity(self.write("native_pdf.synthetic", native_bytes))
        self.exports["outputs"]["native_pdf"]["file"] = self.files["native_pdf"]
        self.write("exports.json", self.exports)
        self.audit_manifest["exports"] = dm.identity(self.exports_path)
        self.review["bindings"]["native_pdf"] = self.files["native_pdf"]
        self.review["bindings"]["exports"] = dm.identity(self.exports_path)
        self.write("review.json", self.review)
        self.audit_manifest["review_report"] = dm.identity(self.review_path)
        self.save_audit()
        self.assertEqual(dm.audit(self.audit_path, self.root / "consistency.json")["status"], "consistency_passed")

    def test_existing_output_alias_cannot_be_an_input(self):
        with self.assertRaisesRegex(dm.Rejected, "FILE_ROLE_IDENTITY_REUSED"):
            dm.audit(self.audit_path, Path(self.files["native_dwg"]["path"]))


if __name__ == "__main__":
    unittest.main()
