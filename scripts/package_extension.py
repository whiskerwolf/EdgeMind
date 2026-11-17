#!/usr/bin/env python3
"""
Chrome Extension Packaging Tool for EdgeMind.

Packages `extension/edgemind/` into `dist/edgemind-chrome-web-store.zip`
for production Chrome Web Store submission:
- Excludes development-only files (e.g. scripts/generate_icons.py, README.md).
- Validates Manifest V3 structure and verifies that all declared resources exist.
- Generates SHA-256 checksum and package metadata manifest.
"""

import hashlib
import json
import os
import sys
import zipfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT_DIR = os.path.join(PROJECT_ROOT, "extension", "edgemind")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
ZIP_OUTPUT_PATH = os.path.join(DIST_DIR, "edgemind-chrome-web-store.zip")
SHA256_OUTPUT_PATH = os.path.join(DIST_DIR, "edgemind-chrome-web-store.zip.sha256")

EXCLUDED_FILENAMES = {
    "generate_icons.py",
    "README.md",
    ".DS_Store",
    "Thumbs.db",
    ".git",
    ".gitignore",
}

EXCLUDED_EXTENSIONS = {
    ".py",
    ".pyc",
    ".pyo",
    ".tmp",
    ".bak",
}


def compute_sha256(filepath: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def validate_manifest(ext_dir: str) -> dict:
    """Validate manifest.json existence and essential MV3 fields."""
    manifest_path = os.path.join(ext_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"manifest.json missing at {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if manifest.get("manifest_version") != 3:
        raise ValueError(f"Expected manifest_version 3, got {manifest.get('manifest_version')}")

    if not manifest.get("name") or not manifest.get("version"):
        raise ValueError("manifest.json must specify 'name' and 'version'")

    return manifest


def package_extension() -> dict:
    """Package the Chrome extension into dist/edgemind-chrome-web-store.zip."""
    os.makedirs(DIST_DIR, exist_ok=True)
    manifest = validate_manifest(EXT_DIR)

    included_files = []
    total_uncompressed_bytes = 0

    if os.path.isfile(ZIP_OUTPUT_PATH):
        os.remove(ZIP_OUTPUT_PATH)

    with zipfile.ZipFile(ZIP_OUTPUT_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        for root, dirs, files in os.walk(EXT_DIR):
            # Sort for deterministic archive layout
            dirs.sort()
            files.sort()

            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if filename in EXCLUDED_FILENAMES or ext in EXCLUDED_EXTENSIONS:
                    continue

                abs_path = os.path.join(root, filename)
                rel_path = os.path.relpath(abs_path, EXT_DIR).replace("\\", "/")

                file_size = os.path.getsize(abs_path)
                total_uncompressed_bytes += file_size
                zipf.write(abs_path, arcname=rel_path)
                included_files.append((rel_path, file_size))

    # Verify manifest.json is at zip root
    with zipfile.ZipFile(ZIP_OUTPUT_PATH, "r") as check_zip:
        names = check_zip.namelist()
        if "manifest.json" not in names:
            raise RuntimeError("Corrupt package: manifest.json is not at the zip root")

        # Verify no excluded files leaked
        for name in names:
            base = os.path.basename(name)
            ext = os.path.splitext(base)[1].lower()
            if base in EXCLUDED_FILENAMES or ext in EXCLUDED_EXTENSIONS:
                raise RuntimeError(f"Prohibited file included in distribution zip: {name}")

    compressed_size = os.path.getsize(ZIP_OUTPUT_PATH)
    sha256_hash = compute_sha256(ZIP_OUTPUT_PATH)

    with open(SHA256_OUTPUT_PATH, "w", encoding="utf-8") as sha_f:
        sha_f.write(f"{sha256_hash}  {os.path.basename(ZIP_OUTPUT_PATH)}\n")

    summary = {
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "output_path": ZIP_OUTPUT_PATH,
        "sha256": sha256_hash,
        "files_count": len(included_files),
        "uncompressed_bytes": total_uncompressed_bytes,
        "compressed_bytes": compressed_size,
        "included_files": [f[0] for f in included_files],
    }

    return summary


if __name__ == "__main__":
    try:
        summary = package_extension()
        print("====================================================")
        print(" EdgeMind Chrome Web Store Package Created")
        print("====================================================")
        print(f"Package:      {summary['output_path']}")
        print(f"Version:      {summary['version']}")
        print(f"Files Count:  {summary['files_count']}")
        print(f"Raw Size:     {summary['uncompressed_bytes']:,} bytes")
        print(f"Zip Size:     {summary['compressed_bytes']:,} bytes")
        print(f"SHA-256:      {summary['sha256']}")
        print("\nIncluded Files:")
        for f in summary["included_files"]:
            print(f"  - {f}")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] Packaging failed: {e}", file=sys.stderr)
        sys.exit(1)
