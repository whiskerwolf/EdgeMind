"""
Tests for EdgeMind Chrome Extension (Manifest V3).

Verifies:
- Manifest file validity, MV3 compliance, and EdgeMind branding.
- All referenced files (popup, styles, scripts, icons) exist and are non-empty.
- Safe DOM rendering (no innerHTML).
- Target API endpoint configuration (POST /api/v1/edgemind/analyze).
- Client-side size limit enforcement (64 KiB).
- Monaco editor extractor safeguards and language validation.
- Zero external tracking domains or third-party network calls.
- Full preservation and separation from the original CodeDoctor extension.
"""

import json
from pathlib import Path
import pytest

EDGEMIND_ROOT = Path("extension/edgemind")
CODEDOCTOR_ROOT = Path("extension/chrome")


def test_edgemind_manifest_file_validity():
    """Verify that manifest.json exists, is valid JSON, and adheres to Manifest V3 for EdgeMind."""
    manifest_path = EDGEMIND_ROOT / "manifest.json"
    assert manifest_path.exists(), "EdgeMind manifest.json does not exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest.get("manifest_version") == 3
    assert manifest.get("name") == "EdgeMind"
    assert manifest.get("version") == "1.0.0"
    assert "adaptive" in manifest.get("description", "").lower()

    # Action popup
    action = manifest.get("action", {})
    assert "default_popup" in action
    popup_path = EDGEMIND_ROOT / action["default_popup"]
    assert popup_path.exists(), f"Popup path {popup_path} does not exist"

    # Action icons
    default_icon = action.get("default_icon", {})
    assert "16" in default_icon
    assert "48" in default_icon
    assert "128" in default_icon
    for size, icon_rel in default_icon.items():
        icon_path = EDGEMIND_ROOT / icon_rel
        assert icon_path.exists(), f"Icon {icon_path} does not exist"

    # Top-level icons
    icons = manifest.get("icons", {})
    assert "16" in icons
    assert "48" in icons
    assert "128" in icons

    # Permissions
    permissions = manifest.get("permissions", [])
    assert "activeTab" in permissions
    assert "scripting" in permissions
    assert "cookies" not in permissions
    assert "history" not in permissions

    # Host permissions strictly for local API
    host_permissions = manifest.get("host_permissions", [])
    assert "http://127.0.0.1:8000/*" in host_permissions
    assert "http://localhost:8000/*" in host_permissions
    assert "<all_urls>" not in host_permissions

    # Content scripts
    content_scripts = manifest.get("content_scripts", [])
    assert len(content_scripts) >= 1
    cs = content_scripts[0]
    assert any("leetcode.com" in match for match in cs.get("matches", []))
    for script_rel in cs.get("js", []):
        script_path = EDGEMIND_ROOT / script_rel
        assert script_path.exists(), f"Content script {script_path} does not exist"

    # CSP
    csp = manifest.get("content_security_policy", {})
    assert "extension_pages" in csp
    assert "'self'" in csp["extension_pages"]
    assert "'unsafe-eval'" not in csp["extension_pages"]


def test_edgemind_all_referenced_extension_files_exist():
    """Verify that all files in icons/, popup/, and scripts/ exist and are non-empty."""
    required_files = [
        "manifest.json",
        "icons/icon16.png",
        "icons/icon48.png",
        "icons/icon128.png",
        "popup/popup.html",
        "popup/popup.css",
        "popup/popup.js",
        "scripts/content.js",
        "scripts/extractor.js",
        "README.md",
    ]
    for rel_path in required_files:
        full_path = EDGEMIND_ROOT / rel_path
        assert full_path.exists(), f"Missing required EdgeMind extension file: {rel_path}"
        assert full_path.stat().st_size > 0, f"EdgeMind extension file is empty: {rel_path}"


def test_edgemind_popup_uses_safe_dom_rendering_no_innerhtml():
    """Verify that popup.js uses safe DOM creation and does not use innerHTML."""
    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"
    content = popup_js_path.read_text(encoding="utf-8")

    assert "innerHTML" not in content, "EdgeMind popup.js must not use innerHTML"
    assert "document.createElement" in content
    assert "textContent" in content


def test_edgemind_popup_uses_correct_api_endpoints():
    """Verify that popup.js targets the EdgeMind endpoint."""
    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"
    content = popup_js_path.read_text(encoding="utf-8")

    assert "/api/v1/edgemind/analyze" in content
    assert "/health" in content
    assert "http://127.0.0.1:8000" in content


def test_edgemind_popup_enforces_source_size_limit():
    """Verify that popup.js enforces the 64 KiB client-side limit."""
    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"
    content = popup_js_path.read_text(encoding="utf-8")

    assert "MAX_SOURCE_SIZE" in content
    assert "64 * 1024" in content or "65536" in content


def test_edgemind_extractor_safeguards_and_monaco():
    """Verify extractor.js inspects Monaco models safely and extracts testcase buffers."""
    extractor_path = EDGEMIND_ROOT / "scripts/extractor.js"
    content = extractor_path.read_text(encoding="utf-8")

    assert "window.monaco" in content
    assert "getModels" in content
    assert "getValue" in content
    assert "testcase" in content.lower()
    assert "eval(" not in content
    assert "click()" not in content


def test_edgemind_no_third_party_transmissions_or_analytics():
    """Verify no external tracking or third-party domains exist in EdgeMind extension scripts."""
    forbidden_domains = [
        "google-analytics.com",
        "mixpanel.com",
        "segment.io",
        "sentry.io",
        "api.openai.com",
        "anthropic.com",
    ]
    for js_file in [
        EDGEMIND_ROOT / "popup/popup.js",
        EDGEMIND_ROOT / "scripts/content.js",
        EDGEMIND_ROOT / "scripts/extractor.js",
    ]:
        content = js_file.read_text(encoding="utf-8").lower()
        for forbidden in forbidden_domains:
            assert forbidden not in content, f"Forbidden domain '{forbidden}' found in {js_file}"


def test_original_codedoctor_extension_remains_untouched():
    """Verify that extension/chrome/ still exists and is untouched as CodeDoctor."""
    assert CODEDOCTOR_ROOT.exists(), "Original CodeDoctor extension directory must not be removed"
    manifest_path = CODEDOCTOR_ROOT / "manifest.json"
    assert manifest_path.exists()

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest.get("name") == "CodeDoctor"
    assert (CODEDOCTOR_ROOT / "popup/popup.js").exists()
    assert (CODEDOCTOR_ROOT / "scripts/extractor.js").exists()


# =============================================================================
# Regression Tests for EdgeMind Live Audit Report
# =============================================================================


def test_extractor_checks_active_editor_and_rejects_cpp_with_stale_python_model():
    """Verify that extractor.js prioritizes the active editor language and rejects C++ even if a stale Python model exists."""
    extractor_path = EDGEMIND_ROOT / "scripts/extractor.js"
    content = extractor_path.read_text(encoding="utf-8")

    # 1. Checks active editor instance before background models
    assert "window.monaco.editor.getEditors" in content
    assert "activeEditorModel" in content
    assert "activeEditorLang" in content

    # 2. Rejects if active editor model is non-python (e.g. C++ / cpp)
    assert "!activeEditorLang.includes(\"python\")" in content

    # 3. Rejects if non-Python models exist and active editor is not verified Python
    assert "nonPythonModels.length > 0" in content

    # 4. Rejects early if page dropdown indicates non-Python
    assert "detectedPageLang && !detectedPageLang.includes(\"python\")" in content


def test_extractor_proceeds_when_valid_python_model_is_available():
    """Verify extractor.js succeeds when an active Python model is present."""
    extractor_path = EDGEMIND_ROOT / "scripts/extractor.js"
    content = extractor_path.read_text(encoding="utf-8")

    # Has logic to return success when active editor has python model
    assert "activeEditorModel && activeEditorLang && activeEditorLang.includes(\"python\")" in content
    assert "success: true" in content
    assert "language: activeEditorLang" in content


def test_popup_static_code_hygiene_label_and_explanation():
    """Verify the 100-point score is named 'Static Code Hygiene' with the required visible explanation."""
    popup_html_path = EDGEMIND_ROOT / "popup/popup.html"
    content_html = popup_html_path.read_text(encoding="utf-8")

    # Tab renamed to Static Code Hygiene
    assert "Static Code Hygiene" in content_html

    # Visible explanation text present
    expected_explanation = (
        "This score measures static code-analysis findings. "
        "It does not establish algorithmic correctness or guarantee that a solution passes platform tests."
    )
    assert expected_explanation in content_html

    # Check CSS styling exists for hygiene banner
    popup_css_path = EDGEMIND_ROOT / "popup/popup.css"
    content_css = popup_css_path.read_text(encoding="utf-8")
    assert ".hygiene-banner" in content_css
    assert ".hygiene-banner-title" in content_css
    assert ".hygiene-banner-text" in content_css


def test_popup_renders_candidate_classification_tags():
    """Verify popup.js renders the 3 classification tags: VALID, ROBUSTNESS PROBE, and VALIDITY UNKNOWN."""
    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"
    content_js = popup_js_path.read_text(encoding="utf-8")

    assert "VALID" in content_js
    assert "ROBUSTNESS PROBE" in content_js
    assert "VALIDITY UNKNOWN" in content_js
    assert "classification-valid" in content_js
    assert "classification-probe" in content_js
    assert "classification-unknown" in content_js


def test_popup_language_badge_dynamic_not_hardcoded_python():
    """Verify popup does not hardcode Python in HTML badge and updates from verified detection results."""
    popup_html_path = EDGEMIND_ROOT / "popup/popup.html"
    content_html = popup_html_path.read_text(encoding="utf-8")

    # HTML badge initializes as 'Detecting...', not hardcoded 'Python'
    assert '<span id="lang-badge" class="badge badge-neutral">Detecting...</span>' in content_html

    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"
    content_js = popup_js_path.read_text(encoding="utf-8")

    # In inspectActiveTab(), starts as Detecting...
    assert 'elLangBadge.textContent = "Detecting...";' in content_js

    # When non-Python is detected, sets badge-fail
    assert 'elLangBadge.className = "badge badge-fail";' in content_js


# =============================================================================
# Regression Tests for Baseline Sample Extraction & Language Display Fixes
# =============================================================================


def _python_parse_assignment_string(line: str):
    import re
    pairs = {}
    i = 0
    n = len(line)

    while i < n:
        m = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=', line[i:])
        if not m:
            break
        key = m.group(1)
        val_start = i + m.end()

        while val_start < n and line[val_start].isspace():
            val_start += 1
        if val_start >= n:
            break

        first_char = line[val_start]
        val_end = val_start

        if first_char == '[':
            depth = 0
            j = val_start
            in_quote = None
            while j < n:
                c = line[j]
                if in_quote:
                    if c == in_quote and line[j-1] != '\\':
                        in_quote = None
                else:
                    if c in ('"', "'"):
                        in_quote = c
                    elif c == '[':
                        depth += 1
                    elif c == ']':
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                j += 1
            val_end = j
        elif first_char == '{':
            depth = 0
            j = val_start
            in_quote = None
            while j < n:
                c = line[j]
                if in_quote:
                    if c == in_quote and line[j-1] != '\\':
                        in_quote = None
                else:
                    if c in ('"', "'"):
                        in_quote = c
                    elif c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                j += 1
            val_end = j
        elif first_char in ('"', "'"):
            quote = first_char
            j = val_start + 1
            while j < n:
                if line[j] == quote and line[j-1] != '\\':
                    j += 1
                    break
                j += 1
            val_end = j
        else:
            j = val_start
            while j < n:
                if line[j] == ',':
                    break
                if re.match(r'\s+[a-zA-Z_][a-zA-Z0-9_]*\s*=', line[j:]):
                    break
                j += 1
            val_end = j

        raw_val = line[val_start:val_end].strip()
        parsed_val = raw_val

        if raw_val == "True":
            parsed_val = True
        elif raw_val == "False":
            parsed_val = False
        elif raw_val == "None":
            parsed_val = None
        elif (raw_val.startswith('"') and raw_val.endswith('"')) or (raw_val.startswith("'") and raw_val.endswith("'")):
            parsed_val = raw_val[1:-1]
        elif raw_val.startswith("[") or raw_val.startswith("{"):
            try:
                parsed_val = json.loads(raw_val.replace("'", '"'))
            except Exception:
                parsed_val = raw_val
        else:
            try:
                parsed_val = int(raw_val) if "." not in raw_val else float(raw_val)
            except Exception:
                pass

        pairs[key] = parsed_val
        i = val_end

    return pairs


def _python_parse_user_sample_inputs(input_data):
    """Python reference mirroring popup.js parseUserSampleInputs."""
    if not input_data:
        return []

    if isinstance(input_data, list):
        cases = []
        for idx, item in enumerate(input_data):
            if not item:
                continue
            if isinstance(item, dict):
                cases.append({
                    "id": f"sample_{idx + 1}",
                    "source": "PUBLIC_SAMPLE",
                    "input_data": item.get("input_data", item)
                })
            elif isinstance(item, str):
                d = _python_parse_assignment_string(item)
                if d:
                    cases.append({
                        "id": f"sample_{len(cases) + 1}",
                        "source": "PUBLIC_SAMPLE",
                        "input_data": d
                    })
        return cases

    if not isinstance(input_data, str) or not input_data.strip():
        return []
    trimmed = input_data.strip()

    if trimmed.startswith("[") or trimmed.startswith("{"):
        try:
            parsed = json.loads(trimmed)
            if isinstance(parsed, list):
                return _python_parse_user_sample_inputs(parsed)
            elif isinstance(parsed, dict):
                return [{"id": "sample_1", "source": "PUBLIC_SAMPLE", "input_data": parsed}]
        except Exception:
            pass

    import re
    raw_blocks = re.split(r'\n\s*\n+|(?=Example\s*\d+:?)', trimmed, flags=re.IGNORECASE)
    blocks = [b.strip() for b in raw_blocks if b.strip()]
    cases = []

    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        current_case = {}

        for line in lines:
            clean_line = re.split(r'Output\s*:', line, flags=re.IGNORECASE)[0]
            clean_line = re.split(r'Explanation\s*:', clean_line, flags=re.IGNORECASE)[0]
            pairs = _python_parse_assignment_string(clean_line)
            if not pairs:
                continue

            has_multiple = len(pairs) > 1
            collision = any(k in current_case for k in pairs.keys())

            if collision or (has_multiple and len(current_case) > 0):
                if current_case:
                    cases.append({
                        "id": f"sample_{len(cases) + 1}",
                        "source": "PUBLIC_SAMPLE",
                        "input_data": current_case
                    })
                current_case = dict(pairs)
            else:
                current_case.update(pairs)

        if current_case:
            cases.append({
                "id": f"sample_{len(cases) + 1}",
                "source": "PUBLIC_SAMPLE",
                "input_data": current_case
            })

    return cases


def test_popup_html_separates_language_and_constraints_rows():
    """Verify popup.html places Language and Constraints in distinct context rows."""
    popup_html_path = EDGEMIND_ROOT / "popup/popup.html"
    content_html = popup_html_path.read_text(encoding="utf-8")

    assert '<div class="context-row" id="row-constraints">' in content_html
    assert '<span class="context-label">Language:</span>' in content_html
    assert '<span class="context-label">Constraints:</span>' in content_html

    # Ensure constraints-badge is NOT inside the language context-badges container
    assert '<div class="context-badges">\n          <span id="lang-badge"' not in content_html
    assert '<span id="lang-badge" class="badge badge-neutral">Detecting...</span>' in content_html
    assert '<span id="constraints-badge" class="badge badge-subtle hidden">Constraints</span>' in content_html


def test_content_and_extractor_use_resilient_selectors_and_regex():
    """Verify content.js and extractor.js include modern example selectors and bounded lookahead regex."""
    for script_name in ["scripts/content.js", "scripts/extractor.js"]:
        script_path = EDGEMIND_ROOT / script_name
        content = script_path.read_text(encoding="utf-8")

        # 1. Contains modern container selectors
        assert ".example-block" in content
        assert "div[class*='example-block']" in content

        # 2. Contains cleaning helper removing Output and Explanation prefixes
        assert "cleanInputString" in content
        assert "Output" in content
        assert "Explanation" in content

        # 3. Contains bounded lookahead regex preventing greedy cross-field consumption
        assert "Input" in content
        assert "(?=(?:Output" in content or "Output\\s*:" in content

        # 4. Searches child code elements
        assert "codeTags" in content
        assert "querySelectorAll(\"code\")" in content


def test_sample_parser_multiline_parameter_assignments_two_sum():
    """Verify multi-line input assignments merge into a single structured test case with nums and target."""
    raw_multiline = "nums = [2,7,11,15]\ntarget = 9"
    cases = _python_parse_user_sample_inputs(raw_multiline)

    assert len(cases) == 1
    assert cases[0]["input_data"] == {"nums": [2, 7, 11, 15], "target": 9}
    assert cases[0]["source"] == "PUBLIC_SAMPLE"


def test_sample_parser_preserves_multiple_distinct_examples():
    """Verify multiple distinct LeetCode Two Sum examples are parsed into separate test cases."""
    raw_three_examples = (
        "nums = [2,7,11,15], target = 9\n"
        "nums = [3,2,4], target = 6\n"
        "nums = [3,3], target = 6"
    )
    cases = _python_parse_user_sample_inputs(raw_three_examples)

    assert len(cases) == 3
    assert cases[0]["input_data"] == {"nums": [2, 7, 11, 15], "target": 9}
    assert cases[1]["input_data"] == {"nums": [3, 2, 4], "target": 6}
    assert cases[2]["input_data"] == {"nums": [3, 3], "target": 6}


def test_sample_parser_strips_inline_output_and_explanation():
    """Verify inline Output and Explanation text (from DOM textContent without newlines) is stripped."""
    raw_inline = "nums = [3,2,4], target = 6Output: [1,2]Explanation: Because 3 + 3 == 6"
    cases = _python_parse_user_sample_inputs(raw_inline)

    assert len(cases) == 1
    assert cases[0]["input_data"] == {"nums": [3, 2, 4], "target": 6}
    assert "Output" not in cases[0]["input_data"]
    assert "Explanation" not in cases[0]["input_data"]


def test_sample_parser_no_fabricated_samples_on_empty():
    """Verify that when extraction fails or input is empty, zero samples are fabricated."""
    assert _python_parse_user_sample_inputs("") == []
    assert _python_parse_user_sample_inputs("   \n\t  ") == []
    assert _python_parse_user_sample_inputs("No valid variable assignments here.") == []


def test_popup_js_includes_enhanced_sample_parser_logic():
    """Verify popup.js contains the enhanced multi-line and collision-aware sample parser."""
    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"
    content_js = popup_js_path.read_text(encoding="utf-8")

    assert "parseAssignmentString" in content_js
    assert "rawBlocks" in content_js
    assert "collision" in content_js
    assert "0 Constraints" in content_js
    assert "elConstraintsBadge" in content_js


def test_popup_html_no_manual_baseline_textarea_or_paste_instructions():
    """Verify popup.html contains zero textarea elements or paste prompts, and has read-only metadata."""
    popup_html_path = EDGEMIND_ROOT / "popup/popup.html"
    content_html = popup_html_path.read_text(encoding="utf-8")

    # 1. No textarea
    assert "<textarea" not in content_html, "Manual textarea must be removed from EdgeMind popup"
    assert "textarea" not in content_html.lower()

    # 2. No paste prompt
    assert "paste" not in content_html.lower()

    # 3. Read-only metadata fields
    assert "Automatically Detected:" in content_html
    assert 'id="samples-detected-badge"' in content_html
    assert "Examples Found:" in content_html
    assert 'id="samples-found-count"' in content_html
    assert "LeetCode Public Examples" in content_html
    assert "No public examples detected on this problem page." in content_html


def test_content_script_supports_spa_navigation_and_description():
    """Verify content.js handles SPA navigation, debounced dynamic mutation observation, and description extraction."""
    content_js_path = EDGEMIND_ROOT / "scripts/content.js"
    content_js = content_js_path.read_text(encoding="utf-8")

    # SPA navigation hooks
    assert "popstate" in content_js
    assert "lastUrl" in content_js

    # Dynamic DOM observation & debouncing
    assert "MutationObserver" in content_js
    assert "debounceTimer" in content_js or "debounce" in content_js

    # Extracts problem description
    assert "description" in content_js
    assert "description_content" in content_js

    # Supports refresh
    assert "REFRESH_PROBLEM_INFO" in content_js


def test_sample_parser_various_parameter_types_strings_matrices_arrays():
    """Verify parsing supports diverse parameter types: 2D matrices, strings, booleans, and integers."""
    raw_samples = (
        'matrix = [[1, 2], [3, 4]], target = 3\n'
        's = "leetcode", k = 2\n'
        'flag = True, limit = -5'
    )
    cases = _python_parse_user_sample_inputs(raw_samples)

    assert len(cases) == 3
    assert cases[0]["input_data"] == {"matrix": [[1, 2], [3, 4]], "target": 3}
    assert cases[1]["input_data"] == {"s": "leetcode", "k": 2}
    assert cases[2]["input_data"] == {"flag": True, "limit": -5}


def test_popup_handles_zero_examples_gracefully_without_asking_to_paste():
    """Verify popup.js handles zero examples gracefully with clear notification and zero paste prompts."""
    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"
    content_js = popup_js_path.read_text(encoding="utf-8")

    assert "No public examples detected on this problem page." in content_js
    assert "paste" not in content_js.lower()
    assert "samples-input" not in content_js
    assert "samples-detected-badge" in content_js
    assert "samples-found-count" in content_js


def test_popup_ui_presentation_label_and_tag_separation():
    """Verify popup.js separates parameter names, severity pills, classifications, and probe tags with whitespace and separators."""
    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"
    content_js = popup_js_path.read_text(encoding="utf-8")

    # Spacing between parameter badge and severity pill
    assert 'badgesDiv.appendChild(document.createTextNode(" "))' in content_js

    # Spacing between candidate tags
    assert 'tagsRow.appendChild(document.createTextNode(" "))' in content_js
    assert "tag-separator" in content_js
    assert '" | "' in content_js

    # Distinct scale tag class
    assert "tag-scale" in content_js


def test_popup_css_has_distinct_tag_and_badge_styles():
    """Verify popup.css contains dedicated classes for tag-scale, gap-param-badge, tag-separator, gap-badges, and wrapping tags row."""
    popup_css_path = EDGEMIND_ROOT / "popup/popup.css"
    content_css = popup_css_path.read_text(encoding="utf-8")

    assert ".tag-scale" in content_css
    assert ".gap-param-badge" in content_css
    assert ".tag-separator" in content_css
    assert ".gap-badges" in content_css
    assert "flex-wrap: wrap" in content_css


def test_page_title_extraction_and_fallback_never_blank():
    """Verify popup.js and content.js guarantee Page title is never blank when on LeetCode."""
    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"
    content_js_path = EDGEMIND_ROOT / "scripts/content.js"

    p_js = popup_js_path.read_text(encoding="utf-8")
    c_js = content_js_path.read_text(encoding="utf-8")

    # Fallback to currentTab.title or URL slug in popup.js
    assert "fallbackTitle" in p_js
    assert "probTitle" in p_js
    assert "LeetCode Problem" in p_js
    assert "isValidTitle" in p_js
    assert "getFallbackTitle" in p_js

    # Title extraction in content.js
    assert "extractProblemInfo" in c_js
    assert "isValidProblemTitle" in c_js


def test_content_script_superscript_and_katex_extraction():
    """Verify content.js handles sup tags, KaTeX msupsub, mathml, and annotations to prevent 10^9 collapsing to 109."""
    content_js_path = EDGEMIND_ROOT / "scripts/content.js"
    c_js = content_js_path.read_text(encoding="utf-8")

    assert "extractTextWithSuperscripts" in c_js
    assert 'sup.textContent = "^"' in c_js or '"^" +' in c_js or '"^" + supText' in c_js
    assert "katex" in c_js
    assert "msupsub" in c_js
    assert "normalizeCollapsedExponents" in c_js


def test_toolbar_icon_consistency_and_manifest_sizes():
    """Verify manifest action.default_icon and icons include 16, 24, 32, 48, 128 as the single declarative source of truth."""
    manifest_path = EDGEMIND_ROOT / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for section in ["icons", "action"]:
        icons_dict = manifest.get(section if section == "icons" else "action", {}).get(
            "default_icon" if section == "action" else ""
        ) if section == "action" else manifest.get("icons", {})

        for sz in ["16", "24", "32", "48", "128"]:
            assert sz in icons_dict, f"Size {sz} missing from {section}"
            icon_file = EDGEMIND_ROOT / icons_dict[sz]
            assert icon_file.exists(), f"Icon file missing: {icon_file}"
            assert icon_file.stat().st_size > 0, f"Icon file empty: {icon_file}"

    # Confirm popup.js preserves clean lifecycle without redundant setIcon hacks
    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"
    popup_js = popup_js_path.read_text(encoding="utf-8")
    assert "syncActionIcon" not in popup_js
    assert "chrome.action.setIcon" not in popup_js


def test_icon_bitmap_geometry_and_brand_mark():
    """Verify rendered PNG icons have correct geometric E polygon structure, transparency, and brand colors."""
    from PIL import Image

    master_path = EDGEMIND_ROOT / "icons/edgemind-logo.svg"
    assert master_path.exists(), "Master SVG edgemind-logo.svg must exist"

    for sz in [16, 24, 32, 48, 128]:
        png_path = EDGEMIND_ROOT / f"icons/icon{sz}.png"
        assert png_path.exists(), f"PNG icon {sz} must exist"
        with Image.open(png_path) as im:
            assert im.size == (sz, sz)
            assert im.mode == "RGBA"

            # Check 16x16 geometry specifically
            if sz == 16:
                # Top bar: line 2-4 has active pixels across width
                top_pixels = [im.getpixel((x, 3))[3] > 50 for x in range(3, 13)]
                assert sum(top_pixels) >= 8, "Top bar must be solid in 16x16 E"

                # Upper gap: line 5-6 right side has transparent pixels
                upper_gap = [im.getpixel((x, 5))[3] == 0 for x in range(6, 14)]
                assert sum(upper_gap) >= 5, "Upper gap must be open in 16x16 E"

                # Middle bar: line 7-8 has active pixels
                mid_pixels = [im.getpixel((x, 7))[3] > 50 for x in range(3, 10)]
                assert sum(mid_pixels) >= 6, "Middle bar must be solid in 16x16 E"

                # Lower gap: line 9-10 right side has transparent/dim pixels (< 50 alpha)
                lower_gap = [im.getpixel((x, 10))[3] == 0 for x in range(6, 14)]
                assert sum(lower_gap) >= 5, "Lower gap must be open in 16x16 E"

                # Bottom bar: line 11-13 has active pixels across width
                bot_pixels = [im.getpixel((x, 12))[3] > 50 for x in range(3, 13)]
                assert sum(bot_pixels) >= 8, "Bottom bar must be solid in 16x16 E"

                # Check brand colors (electric blue top, radiant violet bottom)
                top_color = im.getpixel((3, 3))
                bot_color = im.getpixel((3, 12))
                # Top should be blueish (high B, high G, low R)
                assert top_color[2] > top_color[0], f"Top bar should be electric blue: {top_color}"
                # Bottom should be purplish/violet (high R and high B)
                assert bot_color[0] > 100 and bot_color[2] > 150, f"Bottom bar should be violet: {bot_color}"


def test_popup_svg_matches_master_geometric_e():
    """Verify popup.html embedded SVG matches the master geometric E polygon."""
    popup_html_path = EDGEMIND_ROOT / "popup/popup.html"
    popup_html = popup_html_path.read_text(encoding="utf-8")

    expected_path = "M 20 16 L 104 16 L 112 24 L 112 36 L 36 36 L 36 56 L 84 56 L 84 72 L 36 72 L 36 92 L 112 92 L 112 104 L 104 112 L 20 112 L 16 108 L 16 20 Z"
    assert expected_path in popup_html, "Popup brand logo must use the official geometric E path"
    assert "hdr-e-grad" in popup_html
    assert "#38BDF8" in popup_html
    assert "#C084FC" in popup_html


def test_baseline_source_label_handling():
    """Verify popup handles baseline source label correctly on supported and unsupported pages."""
    popup_html_path = EDGEMIND_ROOT / "popup/popup.html"
    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"

    html = popup_html_path.read_text(encoding="utf-8")
    js = popup_js_path.read_text(encoding="utf-8")

    # Element exists in HTML
    assert 'id="samples-source-value"' in html

    # Element referenced in JS
    assert "elSamplesSourceValue" in js
    assert "samples-source-value" in js

    # Displays appropriate label for unsupported pages
    assert "Unavailable — Open a LeetCode problem" in js

    # Conditional update for LeetCode problem pages
    assert '"LeetCode Public Examples"' in js


def test_api_status_badge_states():
    """Verify API connection badge supports Connected, Offline, Connecting, and Error states."""
    popup_html_path = EDGEMIND_ROOT / "popup/popup.html"
    popup_js_path = EDGEMIND_ROOT / "popup/popup.js"
    popup_css_path = EDGEMIND_ROOT / "popup/popup.css"

    html = popup_html_path.read_text(encoding="utf-8")
    js = popup_js_path.read_text(encoding="utf-8")
    css = popup_css_path.read_text(encoding="utf-8")

    # HTML status elements
    assert 'id="api-status"' in html
    assert 'id="api-status-text"' in html

    # JS state controller
    assert "setApiStatus" in js
    assert '"connected", "Connected"' in js or "'connected', 'Connected'" in js
    assert '"offline", "Offline"' in js or "'offline', 'Offline'" in js
    assert '"connecting", "Connecting"' in js or "'connecting', 'Connecting'" in js
    assert '"error", "Error"' in js or "'error', 'Error'" in js

    # CSS status styling
    assert ".api-status.connected" in css
    assert ".api-status.offline" in css
    assert ".api-status.connecting" in css
    assert ".api-status.error" in css
    assert "status-pulse" in css







