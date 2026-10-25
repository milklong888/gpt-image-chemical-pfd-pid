# Portable source-bound drawing knowledge engine

First-party extraction of the existing project engine: LlamaIndex semantic/vector/BM25/property-graph retrieval, BGE local embedding integration, exact engineering identifiers, Docling page/region ingestion, LinkML schema, modules, receipt gates, source navigation, immutable ZIP registration and review-gated source repair. This is code, not a released engineering knowledge base or a ready-trained model. First-party files follow the repository MIT license; dependency terms remain separate.

No private source records, standards bodies/texts, drawings, corpus, embeddings, indexes, weights, Autodesk/Office binaries, or native CAD converter are included. Input attachments remain data, never instructions. All extracted content defaults to candidate; historical sources, model similarity and valid schema do not establish engineering approval.

## Locations and dependencies

Python 3.11+ (hashlib.file_digest); run scripts with `python -X utf8`. requirements-engine.txt and requirements-parser.txt record observed local direct versions, not a freshly resolved cross-platform lock. See DEPENDENCIES.json. Optional PyMuPDF features have AGPL/commercial licensing constraints; no such package is redistributed. The owner must review its intended dependency/license combination before release. No environment installation or downloads were performed here.

Default data=drawing-knowledge/data, assets=drawing-knowledge/assets. No home-folder or production-library discovery. Set CHEM_KNOWLEDGE_DATA and CHEM_KNOWLEDGE_ASSETS, or CHEM_KNOWLEDGE_CONFIG pointing at a runtime JSON with data_root/asset_root (relative paths resolve beside that config). CLI --data overrides the data root where supported. Copy runtime.example.json to engine/runtime.json only for local use; do not commit local paths. source_repair takes explicit --root/--knowledge/--modules; parser --registry/--out remain available.

Supply independently licensed BGE weights and your own data/models/model.json: repo, pinned revision, dimension512, local_path, query_instruction and exact files SHA256 map. local_path may be relative to the data root; CHEM_KNOWLEDGE_MODEL overrides its location. The engine runs offline and verifies listed files. The demo contains an explicitly synthetic no-model stub, not a usable embedding config: replace it before any real build/query. Docling OCR uses its separately installed model/backend environment; this packaging did not validate offline provisioning or execute OCR.

assets contains empty equipment/catalog, symbol manifest and information-item placeholders. Supply your own reviewed, licensed catalog/geometry and field policy. Topic prompts are first-party workflow questions; local/source-specific locator leads were removed. A private-source-specific rotation exclusion was deliberately removed: represent such reviewed source corrections in your own ingestion outputs, never copy a private exception into a general engine.

## Lightweight synthetic checks

Run `python -X utf8 tests/test_portable.py`. It creates temporary ORIGINAL SYNTHETIC text and source identities only, runs actual assembly + LinkML schema + receipt/source/literal checks, then cleans its fixture. Retrieval generation is explicitly mocked; no semantic model, index build or CAD runs. The full real receipt gate rejects changed source bytes, changed ID, corpus-result substitutions (even after test execution-log reseeding), and missing/changed helper bindings. No synthetic result is an engineering value or standard.

To inspect a fresh sample manually: `python -X utf8 examples/create_demo.py --out data`; then `python -X utf8 engine/knowledge.py --data data assemble` and `... validate`. `python engine/build_modules.py` derives the configured eight module views after assembly. A real `build`/`query`/`packet` requires your licensed material, real configured embedding files and sufficient resources; this extraction was not used to claim fresh full-index acceptance.

## Retained commands

- engine/registry/ingest_archives.py --archives <owned.zip> --out <data>/registry: immutable hashes, aliases, ZIP path defenses; never executes attachments.
- engine/registry/classify_sources.py --out <data>/registry: candidate keyword classification; optional PyMuPDF text/thumbnails.
- engine/parser/docling_adapter.py --help; native_pdf_batch.py: actual Docling structural/native/OCR adapters and provenance; collect_coverage.py reports page coverage without claiming reading accuracy.
- engine/knowledge.py --data <data> assemble / validate / build / query / packet: existing framework pipeline; no custom replacement vector index.
- engine/source_context.py --data <data> --source-id <id> --out <new.json>: light source/DXF hash-bound navigation, not a semantic receipt.
- engine/check_plan_scope.py: final declared module scope vs actual packet; natural-language completeness and engineering design remain external review.
- engine/source_repair.py --root <data> validate/install/recover/rollback: review-gated transaction, original-question regression, existing locks and rollback evidence. Not new-source ingestion or design; run only with independently reviewed patches and restorable resources.

query() retains source/standard hard filters, original canonical-node fusion and literal IDs with full boundaries. Literal evidence is global, result rows remain exact corpus nodes plus score; both query engine and literal-helper hashes are receipt-bound. All gates remain intact. No unvalidated native_extract or old mutable-DXF batch converter is distributed.

No GitHub operation or production skill/data mutation was performed. Test results and source adaptation fingerprints are local release-candidate evidence; see PROVENANCE.json, test-results.json and cli-help-results.json. The main repository integration may relocate this folder but must keep sibling engine imports/configuration consistent.
