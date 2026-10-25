# Dependency and provenance boundaries

Only project-authored Python adapters, workflow topic definitions and LinkML schema are copied. No third-party library implementation, standards text, model weights, commercial CAD/Office code or real source record is bundled. Existing files had no individual copyright/license grants; final first-party license and ownership confirmation belong to the repository owner. This candidate does not invent licenses for them.

Local distribution declarations: LlamaIndex core MIT; Docling MIT; LinkML Apache-2.0. Other direct dependency declarations and observed versions/URLs are recorded in DEPENDENCIES.json. Those installed metadata declarations do not cover all transitive components, downloaded model licenses, optional backends or combined-distribution obligations. Read upstream terms for the exact environment you redistribute. BGE integration expects independently supplied model files (the prior model metadata identifies MIT; weights are absent).

PyMuPDF local metadata states dual GNU Affero GPL3 / Artifex commercial licensing. It is an optional dependency for selected PDF/coordinate/image features, not vendored here; the first-party adapter license cannot override it. An empty placeholder or synthetic fixture is not proof the full dependency stack has a permissive license.

No Autodesk API implementation or AutoCAD executable is present; no Office automation source or macros are executed by this package. Ordinary native-DXF evidence ingestion remains supported as user-provided data, but the unsafe/unvalidated native conversion candidate is excluded entirely.
