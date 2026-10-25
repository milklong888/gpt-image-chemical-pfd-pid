#!/usr/bin/env python3
"""Safely merge ZIP member files into a content-addressed source registry.

This reads ZIP metadata and member bytes only. It never executes member files.
Run with: python ingest_archives.py --archives a.zip b.zip --out registry
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_stream(stream) -> tuple[str, int]:
    h, size = hashlib.sha256(), 0
    for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
        h.update(chunk)
        size += len(chunk)
    return h.hexdigest(), size


def decode_member_name(name: str, flag_bits: int) -> tuple[str, str]:
    if flag_bits & 0x800:
        return name, "utf-8"
    try:
        candidate = name.encode("cp437").decode("cp936")
        cjk = lambda s: sum("\u3400" <= c <= "\u9fff" for c in s)
        if cjk(candidate) > cjk(name):
            return candidate, "cp936-recovered"
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return name, "cp437"


def safe_basename(name: str) -> str:
    leaf = PurePosixPath(name.replace("\\", "/").rstrip("/")).name
    leaf = re.sub(r'[<>:"|?*\x00-\x1f]', "_", leaf).rstrip(" .")
    if leaf in ("", ".", ".."):
        leaf = "unnamed"
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", leaf, re.I):
        leaf = "_" + leaf
    if len(leaf) > 220:
        stem, suffix = os.path.splitext(leaf)
        leaf = stem[:180] + suffix
    return leaf


def validate_member_path(name: str) -> str | None:
    normalized = name.replace("\\", "/")
    parts = normalized.split("/")
    if "\x00" in name:
        return "nul_in_member_path"
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return "absolute_member_path"
    if any(part == ".." for part in parts):
        return "parent_traversal"
    return None


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def inside(path: Path, root: Path) -> bool:
    path, root = path.resolve(), root.resolve()
    return path == root or root in path.parents


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def pdf_metadata(path: Path) -> dict:
    if path.suffix.lower() != ".pdf":
        return {"pdf_page_count": None, "pdf_pages_text_length": None}
    try:
        import fitz

        doc = fitz.open(path)
        lengths = [len(page.get_text("text")) for page in doc]
        count = len(doc)
        doc.close()
        return {"pdf_page_count": count, "pdf_pages_text_length": lengths}
    except Exception as exc:  # Preserve the file even if its PDF structure is unreadable.
        return {"pdf_page_count": None, "pdf_pages_text_length": None,
                "pdf_error": f"{type(exc).__name__}: {exc}"}


def _archive_scan(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    archive_sha = sha_file(path)
    members, dirs, types = [], 0, collections.Counter()
    duplicate_names = collections.Counter()
    with zipfile.ZipFile(path, "r") as zf:
        infos = zf.infolist()
        # Check every path before reading or writing member payloads.
        unsafe = []
        for info in infos:
            decoded, codec = decode_member_name(info.filename, info.flag_bits)
            issue = validate_member_path(decoded)
            if issue:
                unsafe.append({"member": decoded, "issue": issue})
            if info.flag_bits & 0x1:
                raise ValueError(f"Encrypted ZIP member is unsupported: {path.name} :: {decoded}")
        if unsafe:
            raise ValueError(f"Unsafe ZIP member path(s); archive rejected before writes: {unsafe[:10]}")
        for index, info in enumerate(infos):
            decoded, codec = decode_member_name(info.filename, info.flag_bits)
            if info.is_dir():
                dirs += 1
                types["(directory)"] += 1
                continue
            duplicate_names[decoded] += 1
            ext = Path(decoded).suffix.lower() or "(no extension)"
            types[ext] += 1
            mode = (info.external_attr >> 16) & 0xFFFF
            member_type = "symlink" if stat.S_ISLNK(mode) else "file"
            with zf.open(info, "r") as stream:
                member_sha, actual_size = sha_stream(stream)
            if actual_size != info.file_size:
                raise IOError(f"ZIP member size mismatch: {path.name} :: {decoded}")
            members.append({
                "index": index, "raw_member_name": info.filename,
                "member_name": decoded, "name_codec": codec,
                "decoded_basename": safe_basename(decoded),
                "member_type": member_type, "size": actual_size,
                "extension": Path(decoded).suffix.lower(), "sha256": member_sha,
            })
    dups = [{"member_name": name, "count": count}
            for name, count in duplicate_names.items() if count > 1]
    by_hash = collections.defaultdict(list)
    for m in members:
        by_hash[m["sha256"]].append({"member_name": m["member_name"], "size": m["size"]})
    duplicate_content = [{"sha256": h, "members": rows}
                         for h, rows in by_hash.items() if len(rows) > 1]
    return {"zip_path": str(path.resolve()), "zip_name": path.name,
            "zip_size": path.stat().st_size, "zip_sha256": archive_sha,
            "member_count": len(infos), "file_member_count": len(members),
            "directory_member_count": dirs,
            "uncompressed_file_bytes": sum(m["size"] for m in members),
            "file_types": dict(sorted(types.items())),
            "duplicate_member_names": dups,
            "duplicate_content_groups": duplicate_content,
            "anomalies": [], "members": members}


def _alias_key(alias: dict) -> tuple:
    return (alias.get("zip_sha256", ""), alias.get("zip_path", ""),
            alias.get("raw_member_name", ""), alias.get("member_name", ""))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", nargs="+", required=True, type=Path,
                        help="One or more ZIP files to safely index and merge.")
    parser.add_argument("--out", required=True, type=Path,
                        help="Independent registry output directory.")
    args = parser.parse_args(argv)
    out = args.out.resolve()

    # Preflight all archive paths and all members before any output write.
    scanned = [_archive_scan(p.resolve()) for p in args.archives]
    out.mkdir(parents=True, exist_ok=True)
    sources_path, manifest_path = out / "sources.json", out / "manifest.json"
    sources_doc = load_json(sources_path, {"schema": "knowledge-v4-source-registry/v1", "sources": []})
    manifest = load_json(manifest_path, {"schema": "knowledge-v4-source-registry-manifest/v1", "archives": []})
    source_rows = sources_doc.get("sources", [])
    if not isinstance(source_rows, list):
        raise ValueError("sources.json must contain a sources list")
    by_hash, by_id = {}, {}
    original_source_ids = {row.get("source_id") for row in source_rows}
    for row in source_rows:
        h, sid = row.get("sha256"), row.get("source_id")
        if not isinstance(h, str) or len(h) != 64 or sid != "src-" + h[:16]:
            raise ValueError(f"Invalid existing source identity: {sid}")
        if h in by_hash or sid in by_id:
            raise ValueError(f"Duplicate source identity in sources.json: {sid}")
        if not inside(Path(row["path"]), out):
            raise ValueError(f"Existing source path escapes --out: {row['path']}")
        by_hash[h], by_id[sid] = row, h
    # Reject truncated source_id collisions before any original is written.
    planned_hashes = {m["sha256"] for ar in scanned for m in ar["members"]}
    for h in planned_hashes:
        sid = "src-" + h[:16]
        old = by_id.get(sid)
        if old is not None and old != h:
            raise ValueError(f"source_id collision: {sid} maps to {old}, incoming hash is {h}")
    # Validate existing source originals; a mismatch is preserved for explicit repair.
    for h, row in by_hash.items():
        original = Path(row["path"])
        if not original.is_file() or sha_file(original) != h:
            raise ValueError(f"Existing original is missing or hash-mismatched; refusing overwrite: {row['source_id']}")

    archive_rows = manifest.setdefault("archives", [])
    by_zip_hash = {r.get("zip_sha256"): r for r in archive_rows if r.get("zip_sha256")}
    created = []
    try:
        for ar in scanned:
            ziphash = ar["zip_sha256"]
            old_ar = by_zip_hash.get(ziphash)
            if old_ar is None:
                old_ar = {k: v for k, v in ar.items() if k != "members"}
                old_ar["zip_path_aliases"] = [ar["zip_path"]]
                archive_rows.append(old_ar)
                by_zip_hash[ziphash] = old_ar
            else:
                aliases = old_ar.setdefault("zip_path_aliases", [old_ar.get("zip_path", "")])
                if ar["zip_path"] not in aliases:
                    aliases.append(ar["zip_path"])

            # Existing archive details are refreshed only from identical ZIP bytes.
            old_ar.update({k: v for k, v in ar.items() if k != "members"})
            old_ar["zip_path_aliases"] = sorted(set(old_ar.get("zip_path_aliases", []) + [ar["zip_path"]]))
            with zipfile.ZipFile(ar["zip_path"], "r") as zf:
                for member in ar["members"]:
                    h = member["sha256"]
                    source = by_hash.get(h)
                    alias = {"zip_path": ar["zip_path"], "zip_name": ar["zip_name"],
                             "zip_sha256": ziphash, "member_name": member["member_name"],
                             "raw_member_name": member["raw_member_name"],
                             "name_codec": member["name_codec"],
                             "decoded_basename": member["decoded_basename"],
                             "member_type": member["member_type"]}
                    if source is not None:
                        keys = {_alias_key(a) for a in source.setdefault("original_aliases", [])}
                        if _alias_key(alias) not in keys:
                            source["original_aliases"].append(alias)
                        exts = source.setdefault("extensions", [source.get("extension", "")])
                        if member["extension"] not in exts:
                            exts.append(member["extension"])
                        continue

                    folder = out / "originals" / h[:16]
                    if not inside(folder, out):
                        raise ValueError("Computed original folder escapes --out")
                    folder.mkdir(parents=True, exist_ok=True)
                    dest = folder / member["decoded_basename"]
                    if dest.exists():
                        if sha_file(dest) != h:
                            raise ValueError(f"Refusing to overwrite conflicting original: {dest}")
                    else:
                        info = zf.infolist()[member["index"]]
                        fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                        created.append(dest)
                        hh, size = hashlib.sha256(), 0
                        try:
                            with os.fdopen(fd, "wb") as target, zf.open(info, "r") as source_stream:
                                for chunk in iter(lambda: source_stream.read(4 * 1024 * 1024), b""):
                                    target.write(chunk); hh.update(chunk); size += len(chunk)
                            if hh.hexdigest() != h or size != member["size"]:
                                raise IOError(f"Member bytes changed between scan and store: {member['member_name']}")
                        except Exception:
                            try: dest.unlink()
                            except OSError: pass
                            raise
                    row = {"source_id": "src-" + h[:16], "sha256": h,
                           "path": str(dest.resolve()), "original_aliases": [alias],
                           "extension": member["extension"],
                           "extensions": [member["extension"]], "size": member["size"]}
                    row.update(pdf_metadata(dest))
                    source_rows.append(row)
                    by_hash[h], by_id[row["source_id"]] = row, h
        # Rebuild aggregate duplicate records from all aliases, preserving any other manifest keys.
        alias_groups = collections.defaultdict(list)
        name_groups = collections.defaultdict(list)
        for row in source_rows:
            for alias in row.get("original_aliases", []):
                alias_groups[row["sha256"]].append({"source_id": row["source_id"], **alias, "size": row["size"]})
                name_groups[alias.get("member_name", "")].append({"zip_path": alias.get("zip_path"), "member_name": alias.get("member_name")})
        manifest["duplicate_content_groups_across_archives"] = [
            {"sha256": h, "source_id": "src-" + h[:16], "size": rows[0]["size"], "members": rows}
            for h, rows in alias_groups.items() if len(rows) > 1]
        manifest["repeated_decoded_member_names_across_archives"] = [
            {"member_name": name, "aliases": rows} for name, rows in name_groups.items() if len(rows) > 1]
        manifest["totals"] = {
            "zip_count": len(archive_rows),
            "zip_member_count": sum(r.get("member_count", 0) for r in archive_rows),
            "file_member_count": sum(r.get("file_member_count", 0) for r in archive_rows),
            "directory_member_count": sum(r.get("directory_member_count", 0) for r in archive_rows),
            "unique_content_source_count": len(source_rows),
            "uncompressed_file_bytes": sum(r.get("uncompressed_file_bytes", 0) for r in archive_rows),
            "encrypted_member_count": sum(len(r.get("encrypted_members", [])) for r in archive_rows),
            "anomaly_count": sum(len(r.get("anomalies", [])) for r in archive_rows),
        }
        atomic_json(sources_path, sources_doc)
        atomic_json(manifest_path, manifest)
    except Exception:
        # Remove only files created by this invocation; never remove or rewrite an older original.
        for path in reversed(created):
            try: path.unlink()
            except OSError: pass
        raise
    print(json.dumps({"ok": True, "zip_count": len(scanned),
                      "member_count": sum(x["file_member_count"] + x["directory_member_count"] for x in scanned),
                      "unique_source_count": len(source_rows),
                      "added_source_count": sum(1 for row in source_rows if row["source_id"] not in original_source_ids),
                      "out": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        raise SystemExit(1)
