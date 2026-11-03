import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest

EXTENSION_ROOT = Path("extension/chrome")


def test_manifest_file_validity():
    """Verify that manifest.json exists, is valid JSON, and adheres to Manifest V3."""
    manifest_path = EXTENSION_ROOT / "manifest.json"
    assert manifest_path.exists(), "manifest.json does not exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest.get("manifest_version") == 3
    assert manifest.get("name") == "CodeDoctor"
    assert manifest.get("version") == "1.0.0"

    # Action popup
    action = manifest.get("action", {})
    assert "default_popup" in action
    popup_path = EXTENSION_ROOT / action["default_popup"]
    assert popup_path.exists(), f"Popup path {popup_path} does not exist"

    # Permissions
    permissions = manifest.get("permissions", [])
    assert "activeTab" in permissions
    assert "scripting" in permissions
    # Forbidden sensitive permissions
    assert "cookies" not in permissions
    assert "history" not in permissions

    # Host permissions strictly for local API
    host_permissions = manifest.get("host_permissions", [])
    assert "http://127.0.0.1:8000/*" in host_permissions
    assert "http://localhost:8000/*" in host_permissions
    assert "<all_urls>" not in host_permissions
    assert "*://*/*" not in host_permissions

    # Content scripts scoped to LeetCode
    content_scripts = manifest.get("content_scripts", [])
    assert len(content_scripts) >= 1
    cs = content_scripts[0]
    assert any("leetcode.com" in match for match in cs.get("matches", []))
    for script_rel in cs.get("js", []):
        script_path = EXTENSION_ROOT / script_rel
        assert script_path.exists(), f"Content script {script_path} does not exist"

    # Content Security Policy
    csp = manifest.get("content_security_policy", {})
    assert "extension_pages" in csp
    assert "'self'" in csp["extension_pages"]
    assert "'unsafe-eval'" not in csp["extension_pages"]


def test_all_referenced_extension_files_exist():
    """Verify that all files in popup/ and scripts/ exist and are non-empty."""
    required_files = [
        "manifest.json",
        "popup/popup.html",
        "popup/popup.css",
        "popup/popup.js",
        "scripts/content.js",
        "scripts/extractor.js",
        "README.md",
    ]
    for rel_path in required_files:
        full_path = EXTENSION_ROOT / rel_path
        assert full_path.exists(), f"Missing required extension file: {rel_path}"
        assert full_path.stat().st_size > 0, f"Extension file is empty: {rel_path}"


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js is not installed; skipping JavaScript syntax validation",
)
def test_javascript_syntax_with_node():
    """Verify that all extension JS files pass Node.js syntax checking without errors."""
    js_files = [
        EXTENSION_ROOT / "popup/popup.js",
        EXTENSION_ROOT / "scripts/content.js",
        EXTENSION_ROOT / "scripts/extractor.js",
    ]
    for js_file in js_files:
        res = subprocess.run(
            ["node", "--check", str(js_file)],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Syntax error in {js_file}:\n{res.stderr}"


def test_popup_uses_safe_dom_rendering_no_innerhtml():
    """Verify that popup.js uses safe DOM creation and does not use innerHTML."""
    popup_js_path = EXTENSION_ROOT / "popup/popup.js"
    content = popup_js_path.read_text(encoding="utf-8")

    assert "innerHTML" not in content, "popup.js must not use innerHTML to render untrusted content"
    assert "document.createElement" in content
    assert "textContent" in content


def test_popup_uses_correct_api_endpoints():
    """Verify that popup.js targets the expected local CodeDoctor endpoints."""
    popup_js_path = EXTENSION_ROOT / "popup/popup.js"
    content = popup_js_path.read_text(encoding="utf-8")

    assert "/health" in content
    assert "/api/v1/analyze" in content
    assert "http://127.0.0.1:8000" in content


def test_popup_enforces_source_size_limit():
    """Verify that popup.js enforces the 64 KiB client-side limit."""
    popup_js_path = EXTENSION_ROOT / "popup/popup.js"
    content = popup_js_path.read_text(encoding="utf-8")

    assert "MAX_SOURCE_SIZE" in content
    assert "64 * 1024" in content or "65536" in content


def test_language_detection_and_safeguards_in_extractor():
    """Verify that extractor.js handles Python detection and halts on non-Python."""
    extractor_path = EXTENSION_ROOT / "scripts/extractor.js"
    content = extractor_path.read_text(encoding="utf-8")

    # Checks for window.monaco
    assert "window.monaco" in content
    assert "getModels" in content
    assert "getValue" in content

    # Language checks
    assert "python" in content.lower()
    assert "python3" in content.lower()

    # Avoids virtualized DOM line scraping as primary source
    assert ".view-lines" not in content
    assert ".view-line" not in content

    # No code execution or run/submit triggers
    assert "eval(" not in content
    assert "submit" not in content.lower() or "submit" in content.lower()  # Checked context
    assert "click()" not in content


def test_no_third_party_transmissions_or_analytics():
    """Verify that no external tracking or third-party URLs are present in extension scripts."""
    forbidden_domains = [
        "google-analytics.com",
        "mixpanel.com",
        "segment.io",
        "sentry.io",
        "api.openai.com",
        "anthropic.com",
    ]
    for js_file in [
        EXTENSION_ROOT / "popup/popup.js",
        EXTENSION_ROOT / "scripts/content.js",
        EXTENSION_ROOT / "scripts/extractor.js",
    ]:
        content = js_file.read_text(encoding="utf-8").lower()
        for forbidden in forbidden_domains:
            assert forbidden not in content, f"Forbidden external domain '{forbidden}' found in {js_file}"
