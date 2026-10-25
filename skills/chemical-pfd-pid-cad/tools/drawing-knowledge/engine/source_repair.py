"""Review-gated, same-data-root repair transaction. Does not implement an index.

Production backend calls the installed LlamaIndex/Docling/LinkML pipeline.
The current manifest is held back until all rebuild and retrieval checks pass.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback

VERSION = "source-repair-candidate-0.3"
INSTALLED_KNOWLEDGE = Path(__file__).with_name("knowledge.py")
MUTABLE = ("curated/requirements.json", "corpus", "modules",
           "schema/drawing_knowledge.schema.json", "indexes/current.json",
           "indexes/ingestion", "indexes/embedding-cache.json", "indexes/current.repair-pending.json")
INSTALLABLE = {"index_omission", "slice_incomplete"}
DIAGNOSES = INSTALLABLE | {"ocr_error", "missing_material", "source_conflict", "unknown_design"}
MODULES = {"common", "tower", "heat_exchanger", "reactor", "vessel",
           "pump_compressor", "piping", "instrumentation"}


def read(path):
    return json.loads(Path(path).read_text("utf8"))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False,
                                    sort_keys=True).encode("utf8")).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def require(value, error):
    if not value:
        raise ValueError(error)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def checked_file(ref, label):
    path = Path(ref["path"]).resolve()
    require(path.is_file() and sha(path) == ref["sha256"], label + "_HASH_MISMATCH")
    return path


def card_content_hash(card):
    """Reviewer binds all card fields, including status and use boundary."""
    return digest(card)


def validate_patch(root, patch, require_review=True, knowledge_path=INSTALLED_KNOWLEDGE,
                   baseline_checker=None):
    """Validate evidence only; validation is not engineering approval."""
    root = Path(root).resolve()
    kind = patch["gap"]["kind"]
    require(kind in DIAGNOSES, "UNKNOWN_DIAGNOSIS")
    require(re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", patch["patch_id"]), "BAD_PATCH_ID")
    require(bool(patch["gap"].get("finding")), "MISSING_GAP_FINDING")
    require(kind in INSTALLABLE, {
        "missing_material": "MISSING_MATERIAL_USE_EXISTING_REGISTRY_INGEST",
        "source_conflict": "SOURCE_CONFLICT_REQUIRES_EXPLICIT_RESOLUTION",
        "unknown_design": "UNKNOWN_DESIGN_CANNOT_BE_REPAIRED_BY_KNOWLEDGE_PATCH",
        "ocr_error": "OCR_ERROR_REPARSE_OR_REPLACE_REQUIRED_APPEND_IS_NOT_CORRECTION",
    }.get(kind, "UNSUPPORTED_DIAGNOSIS"))
    # Use the installed version's complete dependency gate, including model-file
    # hashes. check_generation does not instantiate an embedding model.
    checker = baseline_checker or load_module(knowledge_path, "repair_baseline_checker").check_generation
    checker(root)
    before_path = checked_file(patch["gap"]["retrieval_receipt"], "BEFORE_QUERY")
    before = read(before_path)
    require("results" in before or "retrieval" in before, "NOT_A_RETRIEVAL_RECEIPT")
    before_query = before.get("retrieval", before)
    current = read(root / "indexes/current.json")
    require(current["corpus_sha256"] == sha(root / "corpus/knowledge.json"),
            "BASELINE_INVALID_RECOVER_OR_REBUILD_FIRST")
    require(before_query.get("corpus_sha256") == current["corpus_sha256"], "BEFORE_QUERY_STALE_CORPUS")
    require(before_query.get("query_engine_sha256") == sha(knowledge_path), "BEFORE_QUERY_ENGINE_MISMATCH")
    require(before_query.get("question") == patch["recheck"]["question"], "BEFORE_AFTER_QUESTION_MISMATCH")
    filters = before_query.get("filters", {})
    require(set(filters) == {"standard_id", "source_id"}, "BEFORE_QUERY_FILTERS_MISSING")
    require(filters["standard_id"] == patch["recheck"].get("standard_id"), "STANDARD_FILTER_SCOPE_MISMATCH")
    require(filters["source_id"] in (None, patch["source"]["source_id"]), "SOURCE_FILTER_SCOPE_MISMATCH")
    audit = root / "evaluations/retrieval-calls.jsonl"
    require(audit.is_file() and any(json.loads(line).get("result_sha256") == digest(before_query)
            for line in audit.read_text("utf8").splitlines() if line.strip()), "BEFORE_QUERY_NOT_IN_AUDIT")
    registry = {s["source_id"]: s for s in read(root / "registry/sources.json")["sources"]}
    source = patch["source"]
    require(source["source_id"] in registry, "NEW_SOURCE_USE_EXISTING_REGISTRY_INGEST")
    registered = registry[source["source_id"]]
    require(source["sha256"] == registered["sha256"] == sha(registered["path"]),
            "SOURCE_HASH_MISMATCH")
    card = patch["card"]
    require(card["source_id"] == source["source_id"] and
            card["source_sha256"] == source["sha256"], "CARD_SOURCE_MISMATCH")
    require(Path(card["source_path"]).resolve() == Path(registered["path"]).resolve(),
            "CARD_SOURCE_PATH_MISMATCH")
    require(card["status"] in {"extracted_candidate", "reviewed_case", "reviewed_historical"},
            "FORBIDDEN_PROMOTION")
    require(card.get("valid_for_release") is False, "FORBIDDEN_RELEASE_APPROVAL")
    require(card.get("kind") in {"CasePattern", "ClauseCandidate", "Requirement"}, "BAD_CARD_KIND")
    require(not (card["status"] == "extracted_candidate" and card["kind"] == "Requirement"),
            "CANDIDATE_REQUIREMENT_WOULD_ENTER_PACKET_USE_CLAUSECANDIDATE")
    require(card["status"] != "reviewed_historical" or card["kind"] == "Requirement", "HISTORICAL_KIND_MISMATCH")
    require(card["status"] != "reviewed_case" or card["kind"] == "CasePattern", "CASE_KIND_MISMATCH")
    require(card.get("text", "").strip() and card.get("condition", "").strip()
            and card.get("exception", "").strip(), "MISSING_TEXT_CONDITIONS_OR_EXCEPTIONS")
    require(card.get("modules") and set(card["modules"]) <= MODULES, "BAD_MODULE_ATTACHMENT")
    p = patch["provenance"]
    for key in ("parent_clause", "conditions", "exceptions", "applicability"):
        require(key in p and p[key] is not None and str(p[key]).strip(), "MISSING_PROVENANCE_" + key)
    pages, handles = p.get("physical_pages", []), p.get("cad_handles", [])
    require(bool(pages or handles), "MISSING_PAGE_OR_HANDLE")
    require(pages == card.get("physical_pages", []) and handles == card.get("cad_handles", []),
            "ANCHOR_MISMATCH")
    if pages:
        require(all(type(n) is int and 1 <= n <= registered.get("pdf_page_count", 0)
                    for n in pages), "INVALID_PHYSICAL_PAGE")
    if handles:
        native = root / "native" / source["source_id"] / "evidence.json"
        require(native.is_file(), "MISSING_NATIVE_EVIDENCE")
        data = read(native)
        require(data.get("ok") and data["source_sha256"] == source["sha256"], "BAD_NATIVE_EVIDENCE")
        native_handles = {t["handle"] for t in data.get("texts", [])}
        native_handles |= {a["handle"] for i in data.get("inserts", []) for a in i.get("attributes", [])}
        require(set(handles) <= native_handles, "HANDLE_NOT_IN_NATIVE_SOURCE")
        if data.get("dxf_path"):
            require(sha(data["dxf_path"]) == data["dxf_sha256"], "DXF_HASH_MISMATCH")
    cards = read(root / "curated/requirements.json")
    require(card["id"] not in {c["id"] for c in cards}, "DUPLICATE_PATCH_CARD")
    import jsonschema
    jsonschema.validate({"schema_version": "4.0", "nodes": [card], "relations": []},
                        read(root / "schema/drawing_knowledge.schema.json"))
    if not require_review:
        return {"ok": True, "installable": False, "reason": "Independent content review required"}
    reviewer_path = checked_file(patch["independent_review"], "INDEPENDENT_REVIEW")
    review = read(reviewer_path)
    require(review.get("reviewer") and review["reviewer"] != patch.get("proposer"),
            "REVIEW_MUST_BE_INDEPENDENT")
    require(review.get("content_verified") is True, "CONTENT_NOT_VERIFIED")
    require(review.get("card_content_sha256") == card_content_hash(card), "REVIEW_CARD_HASH_MISMATCH")
    require(review.get("source_id") == source["source_id"] and
            review.get("source_sha256") == source["sha256"], "REVIEW_SOURCE_MISMATCH")
    require(review.get("physical_pages", []) == pages and review.get("cad_handles", []) == handles,
            "REVIEW_ANCHOR_MISMATCH")
    require(set(review.get("checked", [])) >= {
        "original_content", "parent_clause", "conditions", "exceptions", "applicability"},
        "INCOMPLETE_CONTENT_REVIEW")
    require(review.get("method") in {"original_page_visual", "native_source_verified"},
            "REVIEW_NOT_ORIGINAL_CONTENT")
    require(review.get("approved_status") == card["status"], "STATUS_NOT_REVIEWED")
    require(review.get("project_adoption") is False and review.get("current_standard_approval") is False,
            "REVIEW_CANNOT_APPROVE_PROJECT_OR_STANDARD_CURRENCY")
    for evidence in review.get("artifacts", []):
        checked_file(evidence, "REVIEW_ARTIFACT")
    require(bool(review.get("artifacts")), "MISSING_ORIGINAL_REVIEW_ARTIFACT")
    return {"ok": True, "installable": True, "card_sha256": card_content_hash(card),
            "review_sha256": sha(reviewer_path), "before_receipt_sha256": sha(before_path)}


def snapshot(root, transaction):
    entries = []
    for relative in MUTABLE:
        source, dest = root / relative, transaction / "backup" / relative
        entry = {"path": relative, "existed": source.exists(), "directory": source.is_dir(),
                 "state": path_state(source)}
        if source.is_dir():
            shutil.copytree(source, dest)
        elif source.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        entries.append(entry)
    return entries


def is_reparse(path):
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False


def reject_reparse_chain(path):
    # Inspect lexical ancestors before resolve() can hide symlink/junction aliases.
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        require(not is_reparse(candidate), "REPARSE_POINT_PATH_REFUSED: " + str(candidate))


def guard_transaction_path(root, transaction):
    reject_reparse_chain(root)
    reject_reparse_chain(transaction)
    check_mutable_paths(root)
    root, transaction = Path(root).resolve(), Path(transaction).resolve()
    require(transaction != root and not root.is_relative_to(transaction), "TRANSACTION_ROOT_OR_ANCESTOR")
    for relative in MUTABLE:
        target = (root / relative).resolve()
        require(not transaction.is_relative_to(target) and not target.is_relative_to(transaction),
                "TRANSACTION_OVERLAPS_MUTABLE: " + relative)
    if transaction.is_relative_to(root):
        require(transaction.is_relative_to(root / "evaluations"), "TRANSACTION_INSIDE_ROOT_MUST_BE_EVALUATIONS")
    return root, transaction


def check_mutable_paths(root):
    for relative in MUTABLE:
        reject_reparse_chain(Path(root) / relative)


def path_state(path):
    reject_reparse_chain(path)
    require(not is_reparse(path), "MUTABLE_REPARSE_POINT_REFUSED: " + str(path))
    if not path.exists():
        return {"exists": False}
    if path.is_file():
        return {"exists": True, "kind": "file", "sha256": sha(path)}
    files, directories = {}, []
    for item in sorted(path.rglob("*")):
        require(not is_reparse(item), "MUTABLE_REPARSE_POINT_REFUSED: " + str(item))
        name = item.relative_to(path).as_posix()
        if item.is_dir():
            directories.append(name)
        elif item.is_file():
            files[name] = sha(item)
    return {"exists": True, "kind": "directory", "files": files, "directories": directories}


def live_state(root, before_generations=()):
    state = {relative: path_state(root / relative) for relative in MUTABLE}
    before = set(before_generations)
    state["new_generations"] = {p.name: path_state(p) for p in sorted((root / "indexes").glob("generation-*"))
                                if str(p.resolve()) not in before}
    return state


def checkpoint(root, transaction, journal, phase):
    state = live_state(root, journal["before_generations"])
    journal["checkpoint"] = {"phase": phase, "state_sha256": digest(state), "state": state}
    record = transaction / "checkpoints" / (str(time.time_ns()) + "-" + phase + ".json")
    write(record, journal["checkpoint"])
    journal.setdefault("checkpoint_history", []).append({"path": str(record), "sha256": sha(record)})
    write(transaction / "journal.json", journal)


def recovery_conflict(transaction, expected, observed, reason):
    path = transaction / ("recovery-conflict-" + str(time.time_ns()) + ".json")
    write(path, {"reason": reason, "expected": expected, "observed": observed,
                 "live_files_preserved": True, "manual_review_required": True})
    raise ValueError("RECOVERY_EXTERNAL_OR_UNCHECKPOINTED_CHANGE: " + reason + "; preserved live state; " + str(path))


def require_recoverable_state(root, transaction, journal):
    saved = journal.get("checkpoint")
    observed = live_state(root, journal.get("before_generations", []))
    if not saved or digest(saved.get("state")) != saved.get("state_sha256"):
        recovery_conflict(transaction, saved, observed, "missing or corrupt checkpoint; manual recovery required")
    expected = saved["state"]
    candidates = [expected]
    if journal["status"] == "ready_to_commit":
        import copy
        # Both sides of the one atomic publication operation are exactly known.
        published = copy.deepcopy(expected)
        published["indexes/current.json"] = {"exists": True, "kind": "file", "sha256": journal["pending_sha256"]}
        candidates.append(published)
        temporary = copy.deepcopy(expected)
        temporary["indexes/current.repair-pending.json"] = {"exists": True, "kind": "file", "sha256": journal["pending_sha256"]}
        candidates.append(temporary)
    if observed not in candidates:
        recovery_conflict(transaction, candidates, observed, "external edit or interruption between recorded phases")


def remove_owned(path, root):
    reject_reparse_chain(path)
    require(path.resolve().is_relative_to(root.resolve()) and path.resolve() != root.resolve(),
            "UNSAFE_REMOVE_PATH")
    require(not path.is_symlink(), "REFUSE_SYMLINK_MUTATION")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def restore(root, transaction, entries):
    check_mutable_paths(root)
    # Validate every backup before deleting any live file.
    for entry in entries:
        require(entry.get("state") == path_state(transaction / "backup" / entry["path"]),
                "BACKUP_HASH_MISMATCH_NO_RESTORE: " + entry["path"])
    # Keep old current absent/stale while restoring; restore it last.
    for entry in sorted(entries, key=lambda e: e["path"] == "indexes/current.json"):
        target, backup = root / entry["path"], transaction / "backup" / entry["path"]
        reject_reparse_chain(target)
        remove_owned(target, root)
        if entry["existed"]:
            if entry["directory"]:
                shutil.copytree(backup, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)


class FrameworkBackend:
    """Reuse framework functions in one process under their existing query lock."""
    def __init__(self, knowledge_path, modules_path):
        self.knowledge_path = Path(knowledge_path).resolve()
        sys.path.insert(0, str(self.knowledge_path.parent))
        self.k = load_module(self.knowledge_path, "repair_installed_knowledge")
        self.modules_path = Path(modules_path).resolve()

    def session(self, root, out):
        return self.k.query_session(root, out, "source repair transaction")

    def check_generation(self, root):
        return self.k.check_generation(root)

    @contextmanager
    def pending_manifest(self, root, transaction):
        current = (root / "indexes/current.json").resolve()
        pending = transaction / "pending-current.json"
        original_write, original_read = self.k.write, self.k.read

        def intercept_write(path, value):
            if Path(path).resolve() == current:
                write(pending, value)
            else:
                original_write(path, value)

        def intercept_read(path):
            if Path(path).resolve() == current and pending.exists():
                return read(pending)
            return original_read(path)

        self.k.write, self.k.read = intercept_write, intercept_read
        try:
            yield pending
        finally:
            self.k.write, self.k.read = original_write, original_read

    def rebuild(self, root, transaction):
        check_mutable_paths(root)
        self.k.assemble(root)
        import gc
        gc.collect()
        prospective = root / "indexes" / ("generation-" + sha(root / "corpus/knowledge.json")[:16])
        require(not prospective.exists(), "TARGET_GENERATION_EXISTS_NO_OVERWRITE")
        self.k.build(root)
        # build_modules imports its own knowledge; only ordinary helpers are used.
        previous = sys.modules.get("knowledge")
        sys.modules["knowledge"] = self.k
        try:
            mod = load_module(self.modules_path, "repair_module_builder")
            mod.R = root
            mod.main()
        finally:
            if previous is None:
                sys.modules.pop("knowledge", None)
            else:
                sys.modules["knowledge"] = previous
        return self.k.read(root / 'corpus/knowledge.json')

    def recheck(self, root, patch, transaction):
        spec = patch["recheck"]
        before = read(patch["gap"]["retrieval_receipt"]["path"])
        filters = before.get("retrieval", before)["filters"]
        query = self.k.query(root, spec["question"], spec.get("limit", 20),
                             filters["standard_id"], filters["source_id"])
        packet = self.k.packet(root, spec["question"], spec["drawing"],
                              spec["equipment"], spec.get("components", []))
        self.k.write_new(transaction / "after-query.json", query)
        self.k.write_new(transaction / "after-packet.json", packet)
        return query, packet


def verify_recheck(root, patch, query, packet, manifest):
    card = patch["card"]
    wanted = card["id"]
    require(query.get("corpus_sha256") == manifest["corpus_sha256"], "QUERY_STALE_CORPUS")
    require(packet.get("corpus_sha256") == manifest["corpus_sha256"], "PACKET_STALE_CORPUS")
    before = read(patch["gap"]["retrieval_receipt"]["path"])
    before_query = before.get("retrieval", before)
    require(query.get("filters") == before_query["filters"], "BEFORE_AFTER_FILTER_SCOPE_MISMATCH")
    require(query.get("question") == before_query["question"], "AFTER_QUERY_QUESTION_MISMATCH")
    require(wanted in {n["id"] for n in query.get("results", [])}, "PATCH_NOT_RETRIEVED")
    require(set(card["modules"]) <= set(packet.get("loaded_modules", [])), "PACKET_MODULE_MISSING")
    groups = ("requirements", "historical_requirements_pending_adoption", "case_patterns")
    packet_cards = {n["id"] for group in groups for n in packet.get(group, [])}
    if card["status"] == "extracted_candidate":
        require(wanted not in packet_cards, "CANDIDATE_PROMOTED_IN_PACKET")
    else:
        require(wanted in packet_cards, "REVIEWED_CARD_MISSING_FROM_PACKET")
    corpus = read(root / "corpus/knowledge.json")
    require(wanted in {n["id"] for n in corpus["nodes"]}, "PATCH_MISSING_FROM_GRAPH_CORPUS")
    require(all(any(r["subject"] == wanted and r["object"] == "module:" + module
                    for r in corpus["relations"]) for module in card["modules"]), "MODULE_GRAPH_EDGE_MISSING")
    for module in card["modules"]:
        module_json = root / "modules" / module / "module.json"
        require(module_json.is_file(), "MODULE_VIEW_MISSING")
        if card["status"] != "extracted_candidate":
            view = read(module_json)
            ids = view.get("requirement_ids", []) + view.get("case_pattern_ids", [])
            require(wanted in ids, "REVIEWED_CARD_MISSING_FROM_MODULE_VIEW")
            require(wanted in (module_json.parent / "MODULE.md").read_text("utf8"),
                    "REVIEWED_CARD_MISSING_FROM_MODULE_MARKDOWN")
    return {"patch_retrieved": True, "packet_boundary_verified": True,
            "engineering_release_eligible": False}


def attach_patch(root, patch, transaction):
    check_mutable_paths(root)
    card = dict(patch["card"])
    reviewer_path = checked_file(patch["independent_review"], "INDEPENDENT_REVIEW")
    review_id = "repair-review:" + patch["patch_id"]
    # Keep provenance outside LinkML node fields; attach it as evidence Source.
    provenance = transaction / "provenance.json"
    write(provenance, {"patch_sha256": digest(patch), "provenance": patch["provenance"],
                       "review": patch["independent_review"], "gap": patch["gap"],
                       "source": patch["source"], "card_sha256": card_content_hash(card)})
    evidence = {"id": review_id, "kind": "Source", "label": "Independent repair review " + patch["patch_id"],
                "status": "extracted_candidate", "valid_for_release": False,
                "text": "Content review and complete repair provenance; no project or current-standard approval.",
                "source_path": str(provenance), "source_sha256": sha(provenance),
                "payload_path": str(reviewer_path), "modules": card["modules"]}
    card["evidence_ids"] = list(dict.fromkeys(card.get("evidence_ids", []) + [review_id]))
    cards = read(root / "curated/requirements.json")
    ids = {c["id"] for c in cards}
    require(review_id not in ids, "DUPLICATE_REVIEW_NODE")
    cards.extend([evidence, card])
    write(root / "curated/requirements.json", cards)


def install(root, patch, transaction, backend):
    root, transaction = guard_transaction_path(root, transaction)
    require(not transaction.exists(), "TRANSACTION_EXISTS")
    transaction.mkdir(parents=True)
    write(transaction / "patch.json", patch)
    journal = {"version": VERSION, "root": str(root), "patch_id": patch["patch_id"],
               "status": "validating", "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    write(transaction / "journal.json", journal)
    before_generations = set()
    snapshot_complete = False
    try:
        with backend.session(root, transaction / "commit.json"):
            journal["validation"] = validate_patch(root, patch,
                knowledge_path=getattr(backend, "knowledge_path", INSTALLED_KNOWLEDGE),
                baseline_checker=getattr(backend, "check_generation", None))
            journal["entries"] = snapshot(root, transaction)
            snapshot_complete = True
            before_generations = {str(p.resolve()) for p in (root / "indexes").glob("generation-*")}
            journal["before_generations"] = sorted(before_generations)
            journal["status"] = "prepared"
            checkpoint(root, transaction, journal, "prepared_before_attach")
            try:
                attach_patch(root, patch, transaction)
                checkpoint(root, transaction, journal, "card_attached")
                with backend.pending_manifest(root, transaction) as pending:
                    backend.rebuild(root, transaction)
                    checkpoint(root, transaction, journal, "rebuild_complete")
                    manifest = read(pending)
                    query, packet = backend.recheck(root, patch, transaction)
                    proof = verify_recheck(root, patch, query, packet, manifest)
                    # The pending manifest must still describe every input after
                    # retrieval, before it can become the public current version.
                    backend.check_generation(root)
                journal.update(status="ready_to_commit", pending_sha256=sha(pending), proof=proof)
                checkpoint(root, transaction, journal, "verified_before_publish")
                # Last publish operation: public queries can only see the old invalidated
                # manifest until this tested corpus+index generation is atomically visible.
                commit_payload = pending.read_bytes()
                check_mutable_paths(root)
                target = root / "indexes/current.json"
                temporary = target.with_name("current.repair-pending.json")
                with temporary.open("wb") as f:
                    f.write(commit_payload)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary, target)
                journal["status"] = "committed"
                journal["committed_current_sha256"] = sha(target)
                checkpoint(root, transaction, journal, "committed")
                write(transaction / "commit.json", journal)
                return journal
            except BaseException:
                restore(root, transaction, journal["entries"])
                quarantine_new_generations(root, transaction, before_generations)
                journal["status"] = "rolled_back_after_failure"
                checkpoint(root, transaction, journal, "restored_after_failure")
                raise
    except BaseException as error:
        journal.update(error=str(error), traceback=traceback.format_exc(), snapshot_complete=snapshot_complete)
        if journal["status"] == "validating":
            journal["status"] = "rejected_before_mutation"
        write(transaction / "journal.json", journal)
        write(transaction / "failure.json", journal)
        raise


def quarantine_new_generations(root, transaction, before):
    for path in (root / "indexes").glob("generation-*"):
        if str(path.resolve()) not in before:
            target = transaction / "quarantine" / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            require(not target.exists(), "QUARANTINE_ALREADY_EXISTS")
            shutil.move(str(path), str(target))


def rollback(transaction, backend, recover=False):
    reject_reparse_chain(transaction)
    transaction = Path(transaction).resolve()
    journal = read(transaction / "journal.json")
    root = Path(journal["root"]).resolve()
    guard_transaction_path(root, transaction)
    with backend.session(root, transaction / ("recovery.json" if recover else "rollback.json")):
        require_recoverable_state(root, transaction, journal)
        current = root / "indexes/current.json"
        if journal["status"] == "ready_to_commit" and current.exists() and sha(current) == journal["pending_sha256"]:
            require(recover, "USE_RECOVER_TO_FINALIZE_COMPLETED_COMMIT")
            journal.update(status="committed", recovered_completed_commit=True,
                           committed_current_sha256=sha(current))
        else:
            require(journal["status"] in {"prepared", "ready_to_commit", "committed"}, "NOT_ROLLBACKABLE")
            if journal["status"] == "committed":
                require(sha(current) == journal["committed_current_sha256"], "NEWER_CHANGE_REFUSE_ROLLBACK")
            else:
                backup_current = transaction / "backup/indexes/current.json"
                require(current.is_file() and sha(current) == sha(backup_current),
                        "NEWER_CHANGE_REFUSE_RECOVERY")
            restore(root, transaction, journal["entries"])
            quarantine_new_generations(root, transaction, set(journal["before_generations"]))
            journal["status"] = "rolled_back"
        checkpoint(root, transaction, journal, "recovered_commit" if journal["status"] == "committed" else "rolled_back")
        write(transaction / ("recovery.json" if recover else "rollback.json"), journal)
    return journal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--knowledge", type=Path, default=Path(__file__).with_name("knowledge.py"))
    parser.add_argument("--modules", type=Path, default=Path(__file__).with_name("build_modules.py"))
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate"); check.add_argument("patch", type=Path)
    check.add_argument("--allow-unreviewed", action="store_true")
    ins = sub.add_parser("install"); ins.add_argument("patch", type=Path); ins.add_argument("--transaction", type=Path, required=True)
    for name in ("rollback", "recover"):
        cmd = sub.add_parser(name); cmd.add_argument("transaction", type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        print(json.dumps(validate_patch(args.root, read(args.patch), not args.allow_unreviewed,
                                        knowledge_path=args.knowledge), ensure_ascii=False))
        return
    backend = FrameworkBackend(args.knowledge, args.modules)
    if args.command == "install":
        result = install(args.root, read(args.patch), args.transaction, backend)
    else:
        journal = read(args.transaction / "journal.json")
        require(Path(journal["root"]).resolve() == args.root.resolve(), "TRANSACTION_ROOT_MISMATCH")
        result = rollback(args.transaction, backend, args.command == "recover")
    print(json.dumps({"status": result["status"], "version": VERSION}, ensure_ascii=False))


if __name__ == "__main__":
    main()
