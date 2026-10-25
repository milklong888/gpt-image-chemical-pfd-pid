# Third-party and source boundaries

- The retired `Ahuaisnotficklehearted/chemical-autocad-drafting1.3` engine at commit `f660054c1b696bac845500816aabcd2dc745a901` carries a non-commercial restriction in its author notice. No upstream engine files, references or source drawings are included here; that material is not relabeled MIT.
- Shapely is a separately installed BSD-3-Clause dependency, and its geometry backend/components retain their own licenses. No Shapely/GEOS source or binary is vendored.
- ezdxf is a separately installed MIT dependency. No ezdxf implementation is vendored.
- Optional `libavoid-js` 0.5.0-beta.5 declares `LGPL-2.1-or-later`. Its unchanged license text is retained in `licenses/libavoid-js-LGPL-2.1.txt`; the JS/wasm implementation and Node runtime are not bundled. Install from its package upstream and retain the package's notices and source availability terms.
- The optional native source calls Autodesk AutoCAD APIs. It requires a separately licensed installation. No AutoCAD SDK, managed/native DLL, compiler/runtime binary, driver, font or user drawing is included in the publication allowlist.
- This project's independently authored modules and bounded implementations use the repository root MIT license. That license does not cover third-party dependencies, standards or source drawings.
