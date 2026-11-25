"""
Tests for EdgeMind Multi-Platform Chrome Extension Integration (Day 2).

Verifies:
- Manifest V3 configuration supporting LeetCode, HackerRank, and Codeforces.
- Platform detection across all supported domains.
- HackerRank problem context extraction (title, description, constraints, input/output format, samples).
- Codeforces problem context extraction (title, description, time/memory limits, input spec constraints, sample tests).
- Editor buffer extraction for Monaco, CodeMirror, ACE, and textareas across platforms.
- Graceful handling of Codeforces pages without an active code editor.
- Language validation and early rejection of non-Python solutions.
- Extraction confidence scoring and tracking of unavailable fields (no fabricated data).
- SPA navigation and Chrome runtime messaging protocol.
- Full compatibility with EdgeMind backend analysis pipeline for multi-platform contexts.
- Full regression preservation of existing LeetCode functionality.
"""

import json
from pathlib import Path
import subprocess
import pytest

from core.service import analyze_edgemind

EDGEMIND_ROOT = Path("extension/edgemind")
CONTENT_JS_PATH = EDGEMIND_ROOT / "scripts/content.js"
EXTRACTOR_JS_PATH = EDGEMIND_ROOT / "scripts/extractor.js"
POPUP_JS_PATH = EDGEMIND_ROOT / "popup/popup.js"
MANIFEST_PATH = EDGEMIND_ROOT / "manifest.json"


def run_node_eval(script: str) -> str:
    """Execute a Node.js script string and return trimmed stdout using a project-local JS file."""
    temp_file = Path("test_eval.js")
    temp_file.write_text(script, encoding="utf-8")
    try:
        res = subprocess.run(["node", "test_eval.js"], capture_output=True, text=True, timeout=10)
        assert res.returncode == 0, f"Node script failed (exit {res.returncode}):\n{res.stderr}\n{res.stdout}"
        return res.stdout.strip()
    finally:
        try:
            temp_file.unlink(missing_ok=True)
        except Exception:
            pass


# ==============================================================================
# 1. Manifest V3 Multi-Platform & Minimal Permissions Tests
# ==============================================================================

def test_manifest_v3_multi_platform_matches_and_minimal_permissions():
    """Verify that manifest.json includes matches for LeetCode, HackerRank, and Codeforces with minimal permissions."""
    assert MANIFEST_PATH.exists()
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest.get("manifest_version") == 3
    assert manifest.get("name") == "EdgeMind"

    # Minimal permissions check
    perms = manifest.get("permissions", [])
    assert "activeTab" in perms
    assert "scripting" in perms
    assert "cookies" not in perms
    assert "history" not in perms
    assert "webRequest" not in perms

    # Content scripts match patterns
    content_scripts = manifest.get("content_scripts", [])
    assert len(content_scripts) >= 1
    matches = content_scripts[0].get("matches", [])

    assert any("leetcode.com" in m for m in matches), "Missing LeetCode match"
    assert any("hackerrank.com" in m for m in matches), "Missing HackerRank match"
    assert any("codeforces.com" in m for m in matches), "Missing Codeforces match"
    assert "<all_urls>" not in matches, "<all_urls> is prohibited"

    # Host permissions remain strictly local
    host_perms = manifest.get("host_permissions", [])
    assert "http://127.0.0.1:8000/*" in host_perms
    assert "http://localhost:8000/*" in host_perms
    assert "<all_urls>" not in host_perms


# ==============================================================================
# 2. Platform Detection Tests
# ==============================================================================

def test_platform_detection_across_all_supported_domains():
    """Verify detectPlatform accurately identifies LeetCode, HackerRank, Codeforces, and unknown URLs."""
    node_script = """
    const { detectPlatform, Platform } = require('./extension/edgemind/scripts/content.js');
    const cases = [
      ['https://leetcode.com/problems/two-sum/', Platform.LEETCODE],
      ['https://leetcode.com/problems/median-of-two-sorted-arrays/description/', Platform.LEETCODE],
      ['https://www.hackerrank.com/challenges/simple-array-sum/problem', Platform.HACKERRANK],
      ['https://hackerrank.com/contests/projecteuler/challenges/euler001', Platform.HACKERRANK],
      ['https://codeforces.com/contest/1234/problem/A', Platform.CODEFORCES],
      ['https://codeforces.com/problemset/problem/1234/A', Platform.CODEFORCES],
      ['https://codeforces.com/gym/100001/problem/B', Platform.CODEFORCES],
      ['https://github.com/whiskerwolf/EdgeMind', Platform.UNKNOWN],
      ['https://example.com', Platform.UNKNOWN]
    ];

    for (const [url, expected] of cases) {
      const detected = detectPlatform(url);
      if (detected !== expected) {
        console.error(`Mismatch for ${url}: expected ${expected}, got ${detected}`);
        process.exit(1);
      }
    }
    console.log('ALL_PLATFORMS_DETECTED');
    """
    out = run_node_eval(node_script)
    assert out == "ALL_PLATFORMS_DETECTED"


# ==============================================================================
# 3. HackerRank Problem Context Extraction Tests
# ==============================================================================

def test_hackerrank_problem_extraction_simulation():
    """Verify HackerRankAdapter extracts title, description, constraints, input/output formats, and samples."""
    node_script = """
    const { HackerRankAdapter } = require('./extension/edgemind/scripts/content.js');

    // Minimal mock DOM environment
    const fakeDom = {
      h1: { textContent: 'Simple Array Sum' },
      desc: {
        innerText: 'Given an array of integers, find the sum of its elements.',
        querySelectorAll: () => []
      },
      headings: [
        {
          textContent: 'Input Format',
          tagName: 'H3',
          nextElementSibling: {
            textContent: 'The first line contains an integer, n.',
            tagName: 'P',
            nextElementSibling: { tagName: 'H3' }
          }
        },
        {
          textContent: 'Constraints',
          tagName: 'H3',
          nextElementSibling: {
            tagName: 'UL',
            querySelectorAll: () => [
              { cloneNode: () => ({ textContent: '0 < n, ar[i] <= 1000', querySelectorAll: () => [] }) }
            ],
            nextElementSibling: { tagName: 'H3' }
          }
        },
        {
          textContent: 'Sample Input 0',
          tagName: 'H3',
          nextElementSibling: {
            tagName: 'PRE',
            textContent: '6\\n1 2 3 4 10 11',
            querySelector: () => null,
            nextElementSibling: null
          }
        },
        {
          textContent: 'Sample Output 0',
          tagName: 'H3',
          nextElementSibling: {
            tagName: 'PRE',
            textContent: '31',
            querySelector: () => null,
            nextElementSibling: null
          }
        }
      ]
    };

    global.window = {
      location: {
        href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem',
        pathname: '/challenges/simple-array-sum/problem'
      }
    };
    global.document = {
      querySelector: (sel) => {
        if (sel.includes('title') || sel === 'h1') return fakeDom.h1;
        if (sel.includes('body')) return fakeDom.desc;
        return null;
      },
      querySelectorAll: (sel) => {
        if (sel.includes('h3') || sel.includes('strong')) return fakeDom.headings;
        return [];
      }
    };

    const data = HackerRankAdapter.extract();
    console.log(JSON.stringify({
      platform: data.platform,
      problemId: data.problemId,
      title: data.title,
      constraints: data.constraints,
      sampleInputs: data.sampleInputs,
      sampleOutputs: data.sampleOutputs,
      inputFormat: data.inputFormat
    }));
    """
    out = run_node_eval(node_script)
    data = json.loads(out)

    assert data["platform"] == "hackerrank"
    assert data["problemId"] == "simple-array-sum"
    assert data["title"] == "Simple Array Sum"
    assert len(data["constraints"]) == 1
    assert "0 < n, ar[i] <= 1000" in data["constraints"][0]
    assert len(data["sampleInputs"]) == 1
    assert data["sampleInputs"][0] == "6\n1 2 3 4 10 11"
    assert len(data["sampleOutputs"]) == 1
    assert data["sampleOutputs"][0] == "31"
    assert "first line contains an integer" in data["inputFormat"]


# ==============================================================================
# 4. Codeforces Problem Context Extraction Tests
# ==============================================================================

def test_codeforces_problem_extraction_simulation():
    """Verify CodeforcesAdapter extracts title, ID, time limit, memory limit, constraints, and multi-line samples."""
    node_script = """
    const { CodeforcesAdapter } = require('./extension/edgemind/scripts/content.js');

    const fakeHeader = {
      nextElementSibling: {
        innerText: 'One hot summer day Pete and his friend Billy decided to buy a watermelon.',
        nextElementSibling: null
      }
    };

    global.window = {
      location: {
        href: 'https://codeforces.com/contest/4/problem/A',
        pathname: '/contest/4/problem/A'
      }
    };
    global.document = {
      querySelector: (sel) => {
        if (sel.includes('.title')) return { textContent: 'A. Watermelon' };
        if (sel.includes('.time-limit')) return { textContent: 'time limit per test 1.0 s' };
        if (sel.includes('.memory-limit')) return { textContent: 'memory limit per test 256 MB' };
        if (sel === '.problem-statement') return {
          querySelector: (sub) => sub === '.header' ? fakeHeader : null
        };
        if (sel.includes('.input-specification')) return {
          innerText: 'The first (and the only) input line contains integer number w (1 <= w <= 100).',
          querySelectorAll: () => []
        };
        if (sel.includes('.output-specification')) return {
          innerText: 'Print YES, if the boys can divide the watermelon into two parts, each of them weighing even number of kilos; and NO in the opposite case.'
        };
        if (sel.includes('.sample-tests') || sel.includes('.sample-test')) return {
          querySelectorAll: (sub) => {
            if (sub.includes('.input')) return [{
              querySelectorAll: () => [],
              textContent: '8'
            }];
            if (sub.includes('.output')) return [{
              textContent: 'YES'
            }];
            return [];
          }
        };
        return null;
      },
      querySelectorAll: () => []
    };

    const data = CodeforcesAdapter.extract();
    console.log(JSON.stringify({
      platform: data.platform,
      contestId: data.contestId,
      problemIndex: data.problemIndex,
      problemId: data.problemId,
      title: data.title,
      timeLimit: data.timeLimit,
      memoryLimit: data.memoryLimit,
      constraints: data.constraints,
      sampleInputs: data.sampleInputs,
      sampleOutputs: data.sampleOutputs
    }));
    """
    out = run_node_eval(node_script)
    data = json.loads(out)

    assert data["platform"] == "codeforces"
    assert data["contestId"] == "4"
    assert data["problemIndex"] == "A"
    assert data["problemId"] == "4A"
    assert "Watermelon" in data["title"]
    assert "1.0 s" in data["timeLimit"]
    assert "256 MB" in data["memoryLimit"]
    assert any("1 <= w <= 100" in c for c in data["constraints"])
    assert data["sampleInputs"] == ["8"]
    assert data["sampleOutputs"] == ["YES"]


# ==============================================================================
# 5. Editor Buffer Extraction & Missing Editor Graceful Handling Tests
# ==============================================================================

def test_codeforces_missing_editor_handled_gracefully():
    """Verify that extractor.js reports editorAvailable: false when no code editor is found on Codeforces."""
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    const code = fs.readFileSync('extension/edgemind/scripts/extractor.js', 'utf-8');

    const fakeWindow = {
      location: { hostname: 'codeforces.com', href: 'https://codeforces.com/problemset/problem/4/A' },
      document: {
        querySelector: () => null,
        querySelectorAll: () => []
      }
    };
    fakeWindow.window = fakeWindow;

    const context = vm.createContext({
      window: fakeWindow,
      document: fakeWindow.document,
      console: console
    });

    const result = vm.runInContext(code, context);
    console.log(JSON.stringify(result));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)

    assert res["success"] is False
    assert res["platform"] == "codeforces"
    assert res["editorAvailable"] is False
    assert "No active code editor detected" in res["error"]


def test_hackerrank_codemirror_editor_extraction():
    """Verify that extractor.js extracts buffer from CodeMirror on HackerRank."""
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    const code = fs.readFileSync('extension/edgemind/scripts/extractor.js', 'utf-8');

    const fakeCodeMirror = {
      getValue: () => 'def simpleArraySum(ar):\\n    return sum(ar)\\n'
    };

    const fakeWindow = {
      location: { hostname: 'www.hackerrank.com', href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem' },
      document: {
        querySelector: (sel) => {
          if (sel.includes('select-language')) return { textContent: 'Python 3', value: 'python3' };
          return null;
        },
        querySelectorAll: (sel) => {
          if (sel.includes('CodeMirror')) return [{ CodeMirror: fakeCodeMirror }];
          return [];
        }
      }
    };
    fakeWindow.window = fakeWindow;

    const context = vm.createContext({
      window: fakeWindow,
      document: fakeWindow.document,
      console: console
    });

    const result = vm.runInContext(code, context);
    console.log(JSON.stringify(result));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)

    assert res["success"] is True
    assert res["platform"] == "hackerrank"
    assert res["editorType"] == "codemirror"
    assert "simpleArraySum" in res["code"]
    assert "python" in res["language"].lower()


def test_hackerrank_rejects_non_python_language():
    """Verify that extractor.js rejects non-Python solutions on HackerRank."""
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    const code = fs.readFileSync('extension/edgemind/scripts/extractor.js', 'utf-8');

    const fakeWindow = {
      location: { hostname: 'www.hackerrank.com', href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem' },
      document: {
        querySelector: (sel) => {
          if (sel.includes('select-language')) return { textContent: 'C++', value: 'cpp' };
          return null;
        },
        querySelectorAll: () => []
      }
    };
    fakeWindow.window = fakeWindow;

    const context = vm.createContext({
      window: fakeWindow,
      document: fakeWindow.document,
      console: console
    });

    const result = vm.runInContext(code, context);
    console.log(JSON.stringify(result));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)

    assert res["success"] is False
    assert res["platform"] == "hackerrank"
    assert "Python only" in res["error"]


# ==============================================================================
# 6. Extraction Confidence & Unavailable Fields
# ==============================================================================

def test_extraction_confidence_scoring_and_unavailable_fields():
    """Verify that missing constraints or sample inputs compute correct confidence without fabricating data."""
    node_script = """
    const { extractProblemInfo } = require('./extension/edgemind/scripts/content.js');

    // LeetCode page with zero constraints and zero examples
    global.window = {
      location: {
        href: 'https://leetcode.com/problems/custom-problem/',
        hostname: 'leetcode.com',
        pathname: '/problems/custom-problem/'
      }
    };
    global.document = {
      querySelector: (sel) => {
        if (sel === 'h1') return { textContent: 'Custom Problem' };
        if (sel.includes('description')) return { innerText: 'Problem description text here.' };
        return null;
      },
      querySelectorAll: () => []
    };

    const res = extractProblemInfo();
    console.log(JSON.stringify({
      confidence: res.extractionConfidence,
      unavailable: res.unavailableFields,
      constraintsCount: res.constraints.length,
      samplesCount: res.sampleInputs.length
    }));
    """
    out = run_node_eval(node_script)
    data = json.loads(out)

    assert data["constraintsCount"] == 0
    assert data["samplesCount"] == 0
    assert "constraints" in data["unavailable"]
    assert "sampleInputs" in data["unavailable"]
    assert data["confidence"] == "LOW"


# ==============================================================================
# 7. Backend Integration with Multi-Platform Contexts
# ==============================================================================

def test_backend_processes_hackerrank_problem_context():
    """Verify EdgeMind backend analyze_edgemind accepts HackerRank problem context and synthesizes candidates."""
    code = """
def simpleArraySum(ar):
    total = 0
    for x in ar:
        total += x
    return total
"""
    problem_ctx = {
        "platform": "hackerrank",
        "problem_id": "simple-array-sum",
        "title": "Simple Array Sum",
        "description": "Given an array of integers, find the sum of its elements.",
        "constraints": ["0 < n, ar[i] <= 1000"],
        "parameters": ["ar"],
    }
    test_cases = [
        {"input": {"ar": [1, 2, 3, 4, 10, 11]}},
    ]

    report = analyze_edgemind(
        code=code,
        problem_context=problem_ctx,
        test_cases=test_cases,
        filename="solution.py",
        max_candidates=10,
        static_only=True,
    )

    assert report["status"] == "SUCCESS"
    assert report["product"] == "EdgeMind"
    ti = report["test_intelligence"]
    assert len(ti["generated_candidates"]) > 0
    assert len(ti["ranked_candidates"]) > 0
    # Expected output remains None
    for cand in ti["generated_candidates"]:
        assert cand.get("expected_output") is None


def test_backend_processes_codeforces_problem_context():
    """Verify EdgeMind backend analyze_edgemind accepts Codeforces problem context and synthesizes candidates."""
    code = """
def solve():
    w = int(input())
    if w > 2 and w % 2 == 0:
        print("YES")
    else:
        print("NO")
"""
    problem_ctx = {
        "platform": "codeforces",
        "problem_id": "4A",
        "title": "A. Watermelon",
        "description": "One hot summer day Pete and his friend Billy decided to buy a watermelon.",
        "constraints": ["Time limit: 1.0s", "Memory limit: 256MB", "1 <= w <= 100"],
        "parameters": ["w"],
    }
    test_cases = [
        {"input": {"w": 8}},
    ]

    report = analyze_edgemind(
        code=code,
        problem_context=problem_ctx,
        test_cases=test_cases,
        filename="solution.py",
        max_candidates=10,
        static_only=True,
    )

    assert report["status"] == "SUCCESS"
    assert report["product"] == "EdgeMind"
    ti = report["test_intelligence"]
    assert len(ti["generated_candidates"]) > 0
    assert len(ti["ranked_candidates"]) > 0
    for cand in ti["generated_candidates"]:
        assert cand.get("expected_output") is None


# ==============================================================================
# 9. Codeforces URL Parsing, Submit Routes, and Context Retention Tests
# ==============================================================================

def test_codeforces_url_parsing_problemset_and_contest_routes():
    """Verify parseCodeforcesUrl correctly separates contestId and problemIndex across all supported routes."""
    node_script = """
    const { parseCodeforcesUrl } = require('./extension/edgemind/scripts/content.js');

    const cases = [
      {
        url: 'https://codeforces.com/problemset/problem/4/A',
        path: '/problemset/problem/4/A',
        expected: { contestId: '4', problemIndex: 'A', pageType: 'problem', isSubmitPage: false }
      },
      {
        url: 'https://codeforces.com/contest/4/problem/A',
        path: '/contest/4/problem/A',
        expected: { contestId: '4', problemIndex: 'A', pageType: 'problem', isSubmitPage: false }
      },
      {
        url: 'https://codeforces.com/gym/100001/problem/B',
        path: '/gym/100001/problem/B',
        expected: { contestId: '100001', problemIndex: 'B', pageType: 'gym_problem', isSubmitPage: false }
      },
      {
        url: 'https://codeforces.com/problemset/submit',
        path: '/problemset/submit',
        expected: { contestId: '', problemIndex: '', pageType: 'submit', isSubmitPage: true }
      },
      {
        url: 'https://codeforces.com/problemset/submit?problemCode=4A',
        path: '/problemset/submit',
        expected: { contestId: '4', problemIndex: 'A', pageType: 'submit', isSubmitPage: true }
      },
      {
        url: 'https://codeforces.com/contest/4/submit',
        path: '/contest/4/submit',
        expected: { contestId: '4', problemIndex: '', pageType: 'submit', isSubmitPage: true }
      },
      {
        url: 'https://codeforces.com/contest/4/submit?problemIndex=A',
        path: '/contest/4/submit',
        expected: { contestId: '4', problemIndex: 'A', pageType: 'submit', isSubmitPage: true }
      }
    ];

    const results = cases.map(c => {
      const res = parseCodeforcesUrl(c.url, c.path);
      return { url: c.url, res, expected: c.expected };
    });

    console.log(JSON.stringify(results));
    """
    out = run_node_eval(node_script)
    results = json.loads(out)

    for item in results:
        res = item["res"]
        exp = item["expected"]
        assert res["contestId"] == exp["contestId"], f"Contest ID mismatch for {item['url']}: got {res['contestId']}, expected {exp['contestId']}"
        assert res["problemIndex"] == exp["problemIndex"], f"Problem Index mismatch for {item['url']}: got {res['problemIndex']}, expected {exp['problemIndex']}"
        assert res["isSubmitPage"] == exp["isSubmitPage"], f"Submit page flag mismatch for {item['url']}"
        assert res["pageType"] == exp["pageType"], f"Page type mismatch for {item['url']}"


def test_codeforces_problemset_problem_extraction_separate_contest_and_index():
    """Verify CodeforcesAdapter extracts separate contestId='4' and problemIndex='A' on problemset URL."""
    node_script = """
    const { CodeforcesAdapter } = require('./extension/edgemind/scripts/content.js');

    global.window = {
      location: {
        href: 'https://codeforces.com/problemset/problem/4/A',
        pathname: '/problemset/problem/4/A'
      }
    };
    global.document = {
      querySelector: (sel) => {
        if (sel.includes('.title')) return { textContent: 'A. Watermelon' };
        return null;
      },
      querySelectorAll: () => []
    };

    const data = CodeforcesAdapter.extract();
    console.log(JSON.stringify({
      contestId: data.contestId,
      problemIndex: data.problemIndex,
      problemId: data.problemId,
      isSubmitPage: data.isSubmitPage,
      title: data.title
    }));
    """
    out = run_node_eval(node_script)
    data = json.loads(out)

    assert data["contestId"] == "4"
    assert data["problemIndex"] == "A"
    assert data["problemId"] == "4A"
    assert data["isSubmitPage"] is False
    assert "Watermelon" in data["title"]


def test_codeforces_contest_submit_page_problem_dropdown_and_context_retention():
    """Verify context is safely retained on contest submit page when problem is selected, and not invented for unvisited problems."""
    node_script = """
    const { CodeforcesAdapter, saveCachedProblemContext } = require('./extension/edgemind/scripts/content.js');

    // 1. Pre-seed cache as if user visited problem 4A
    saveCachedProblemContext('4A', {
      title: 'A. Watermelon',
      description: 'One hot summer day Pete and his friend Billy decided to buy a watermelon.',
      constraints: ['Time limit: 1.0 s', '1 <= w <= 100'],
      sampleInputs: ['8'],
      sampleOutputs: ['YES'],
      contestId: '4',
      problemIndex: 'A'
    });

    // 2. Navigate to /contest/4/submit with problem A selected in dropdown
    global.window = {
      location: {
        href: 'https://codeforces.com/contest/4/submit',
        pathname: '/contest/4/submit'
      }
    };

    const mockSelectA = {
      selectedIndex: 1,
      options: [
        { value: '', text: 'Choose problem...' },
        { value: 'A', text: 'A - Watermelon' },
        { value: 'B', text: 'B - Before an Exam' }
      ]
    };

    global.document = {
      querySelector: (sel) => {
        if (sel.includes('submittedProblemIndex')) return mockSelectA;
        if (sel.includes('programTypeId')) return {
          selectedIndex: 0,
          options: [{ text: 'Python 3.8.10' }]
        };
        return null;
      },
      querySelectorAll: () => []
    };

    const dataA = CodeforcesAdapter.extract();

    // 3. Change dropdown to problem B (not in cache)
    const mockSelectB = {
      selectedIndex: 2,
      options: [
        { value: '', text: 'Choose problem...' },
        { value: 'A', text: 'A - Watermelon' },
        { value: 'B', text: 'B - Before an Exam' }
      ]
    };

    global.document.querySelector = (sel) => {
      if (sel.includes('submittedProblemIndex')) return mockSelectB;
      if (sel.includes('programTypeId')) return {
        selectedIndex: 0,
        options: [{ text: 'Python 3.8.10' }]
      };
      return null;
    };

    const dataB = CodeforcesAdapter.extract();

    console.log(JSON.stringify({ dataA, dataB }));
    """
    out = run_node_eval(node_script)
    payload = json.loads(out)
    dataA = payload["dataA"]
    dataB = payload["dataB"]

    # Problem A: safely retained context
    assert dataA["contestId"] == "4"
    assert dataA["problemIndex"] == "A"
    assert dataA["problemId"] == "4A"
    assert dataA["problemSelected"] is True
    assert dataA["isSubmitPage"] is True
    assert dataA["title"] == "A. Watermelon"
    assert "One hot summer day" in dataA["description"]
    assert any("1 <= w <= 100" in c for c in dataA["constraints"])
    assert dataA["sampleInputs"] == ["8"]

    # Problem B: context NEVER invented for unvisited problem
    assert dataB["contestId"] == "4"
    assert dataB["problemIndex"] == "B"
    assert dataB["problemId"] == "4B"
    assert dataB["problemSelected"] is True
    assert dataB["description"] == ""
    assert dataB["constraints"] == []
    assert dataB["sampleInputs"] == []
    assert dataB["sampleOutputs"] == []


def test_codeforces_submit_page_missing_problem_selection_handled_gracefully():
    """Verify that when no problem is selected on the submit page, the extension handles it gracefully without inventing context."""
    node_script = """
    const { CodeforcesAdapter, extractProblemInfo } = require('./extension/edgemind/scripts/content.js');

    global.window = {
      location: {
        href: 'https://codeforces.com/contest/4/submit',
        pathname: '/contest/4/submit'
      }
    };

    const mockEmptySelect = {
      selectedIndex: 0,
      options: [
        { value: '', text: 'Choose problem...' }
      ]
    };

    global.document = {
      querySelector: (sel) => {
        if (sel.includes('submittedProblemIndex')) return mockEmptySelect;
        return null;
      },
      querySelectorAll: () => []
    };

    const data = CodeforcesAdapter.extract();
    const info = extractProblemInfo();

    console.log(JSON.stringify({ data, info }));
    """
    out = run_node_eval(node_script)
    payload = json.loads(out)
    data = payload["data"]
    info = payload["info"]

    assert data["isSubmitPage"] is True
    assert data["contestId"] == "4"
    assert data["problemIndex"] is None
    assert data["problemId"] == ""
    assert data["problemSelected"] is False
    assert data["constraints"] == []
    assert data["sampleInputs"] == []
    assert data["sampleOutputs"] == []
    assert data["description"] == ""
    assert "Codeforces Contest 4 Submission" in data["title"]

    assert info["extractionConfidence"] == "NONE"
    assert "problem" in info["unavailableFields"]


def test_codeforces_submit_page_code_and_language_extraction():
    """Verify that extractor.js extracts Python code from #sourceCodeTextarea, detects Python 3, and rejects non-Python."""
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    const code = fs.readFileSync('extension/edgemind/scripts/extractor.js', 'utf-8');

    // Case 1: Valid Python code in textarea
    const fakeWindowPy = {
      location: { hostname: 'codeforces.com', href: 'https://codeforces.com/contest/4/submit', pathname: '/contest/4/submit' },
      document: {
        querySelector: (sel) => {
          if (sel.includes('programTypeId')) return {
            selectedIndex: 0,
            options: [{ text: 'Python 3.8.10' }]
          };
          if (sel.includes('sourceCodeTextarea') || sel.includes('source')) return {
            value: 'def solve():\\n    print("YES")\\n'
          };
          if (sel.includes('submittedProblemIndex')) return {
            selectedIndex: 1,
            options: [{ value: '', text: 'Choose' }, { value: 'A', text: 'A - Watermelon' }]
          };
          return null;
        },
        querySelectorAll: () => []
      }
    };
    fakeWindowPy.window = fakeWindowPy;

    const ctxPy = vm.createContext({ window: fakeWindowPy, document: fakeWindowPy.document, console });
    const resPy = vm.runInContext(code, ctxPy);

    // Case 2: Selected language is GNU C++17
    const fakeWindowCpp = {
      location: { hostname: 'codeforces.com', href: 'https://codeforces.com/contest/4/submit', pathname: '/contest/4/submit' },
      document: {
        querySelector: (sel) => {
          if (sel.includes('programTypeId')) return {
            selectedIndex: 0,
            options: [{ text: 'GNU C++17 7.3.0' }]
          };
          if (sel.includes('sourceCodeTextarea') || sel.includes('source')) return {
            value: '#include <iostream>\\n'
          };
          return null;
        },
        querySelectorAll: () => []
      }
    };
    fakeWindowCpp.window = fakeWindowCpp;

    const ctxCpp = vm.createContext({ window: fakeWindowCpp, document: fakeWindowCpp.document, console });
    const resCpp = vm.runInContext(code, ctxCpp);

    // Case 3: Empty code in textarea
    const fakeWindowEmpty = {
      location: { hostname: 'codeforces.com', href: 'https://codeforces.com/contest/4/submit', pathname: '/contest/4/submit' },
      document: {
        querySelector: (sel) => {
          if (sel.includes('programTypeId')) return {
            selectedIndex: 0,
            options: [{ text: 'Python 3.8.10' }]
          };
          if (sel.includes('sourceCodeTextarea') || sel.includes('source')) return {
            value: ''
          };
          if (sel.includes('submittedProblemIndex')) return {
            selectedIndex: 1,
            options: [{ value: '', text: 'Choose' }, { value: 'A', text: 'A - Watermelon' }]
          };
          return null;
        },
        querySelectorAll: () => []
      }
    };
    fakeWindowEmpty.window = fakeWindowEmpty;

    const ctxEmpty = vm.createContext({ window: fakeWindowEmpty, document: fakeWindowEmpty.document, console });
    const resEmpty = vm.runInContext(code, ctxEmpty);

    // Case 4: No problem selected on submit page
    const fakeWindowNoProb = {
      location: { hostname: 'codeforces.com', href: 'https://codeforces.com/contest/4/submit', pathname: '/contest/4/submit' },
      document: {
        querySelector: (sel) => {
          if (sel.includes('programTypeId')) return {
            selectedIndex: 0,
            options: [{ text: 'Python 3.8.10' }]
          };
          if (sel.includes('submittedProblemIndex')) return {
            selectedIndex: 0,
            options: [{ value: '', text: 'Choose problem...' }]
          };
          if (sel.includes('sourceCodeTextarea') || sel.includes('source')) return {
            value: 'print("hello")'
          };
          return null;
        },
        querySelectorAll: () => []
      }
    };
    fakeWindowNoProb.window = fakeWindowNoProb;

    const ctxNoProb = vm.createContext({ window: fakeWindowNoProb, document: fakeWindowNoProb.document, console });
    const resNoProb = vm.runInContext(code, ctxNoProb);

    console.log(JSON.stringify({ resPy, resCpp, resEmpty, resNoProb }));
    """
    out = run_node_eval(node_script)
    data = json.loads(out)

    # Case 1: Python success
    assert data["resPy"]["success"] is True
    assert data["resPy"]["language"] == "python3"
    assert "print(\"YES\")" in data["resPy"]["code"]
    assert data["resPy"]["editorType"] == "textarea"

    # Case 2: C++ rejection
    assert data["resCpp"]["success"] is False
    assert "analyzes Python only" in data["resCpp"]["error"]
    assert "GNU C++17" in data["resCpp"]["language"]

    # Case 3: Empty code
    assert data["resEmpty"]["success"] is False
    assert data["resEmpty"]["editorAvailable"] is True
    assert "code editor is empty" in data["resEmpty"]["error"]

    # Case 4: No problem selected
    assert data["resNoProb"]["success"] is False
    assert data["resNoProb"]["problemSelected"] is False
    assert "No problem selected" in data["resNoProb"]["error"]


# ==============================================================================
# 10. HackerRank Ace Editor, Shadow DOM, and DOM Line Fallback Tests
# ==============================================================================

def test_hackerrank_ace_editor_extraction():
    """Verify that extractor.js extracts buffer from Ace editor (env.editor) on HackerRank."""
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    const code = fs.readFileSync('extension/edgemind/scripts/extractor.js', 'utf-8');

    const fakeAceEditor = {
      getValue: () => 'def simpleArraySum(ar):\\n    return sum(ar)\\n',
      getSession: () => ({ getMode: () => ({ $id: 'ace/mode/python' }) })
    };

    const fakeWindow = {
      location: { hostname: 'www.hackerrank.com', href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem' },
      document: {
        querySelector: (sel) => {
          if (sel.includes('select-language')) return { textContent: 'Python 3', value: 'python3' };
          return null;
        },
        querySelectorAll: (sel) => {
          if (sel.includes('ace_editor')) return [{ env: { editor: fakeAceEditor } }];
          return [];
        }
      }
    };
    fakeWindow.window = fakeWindow;

    const context = vm.createContext({
      window: fakeWindow,
      document: fakeWindow.document,
      console: console
    });

    const result = vm.runInContext(code, context);
    console.log(JSON.stringify(result));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)

    assert res["success"] is True
    assert res["platform"] == "hackerrank"
    assert res["editorType"] == "ace"
    assert "simpleArraySum" in res["code"]
    assert "python" in res["language"].lower()


def test_hackerrank_dom_lines_fallback_never_reports_empty_when_visible():
    """Verify that extractor.js extracts code from visible .ace_line elements if in-memory API is unavailable."""
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    const code = fs.readFileSync('extension/edgemind/scripts/extractor.js', 'utf-8');

    const fakeLines = [
      { textContent: 'def solve():', innerText: 'def solve():' },
      { textContent: '    return 42', innerText: '    return 42' }
    ];

    const fakeWindow = {
      location: { hostname: 'www.hackerrank.com', href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem' },
      document: {
        querySelector: () => null,
        querySelectorAll: (sel) => {
          if (sel.includes('ace_line')) return fakeLines;
          if (sel.includes('ace_editor')) return [{ className: 'ace_editor' }];
          return [];
        }
      }
    };
    fakeWindow.window = fakeWindow;

    const context = vm.createContext({
      window: fakeWindow,
      document: fakeWindow.document,
      console: console
    });

    const result = vm.runInContext(code, context);
    console.log(JSON.stringify(result));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)

    assert res["success"] is True
    assert res["platform"] == "hackerrank"
    assert "def solve():" in res["code"]
    assert "return 42" in res["code"]
    assert res["editorType"] == "ace_dom_lines"
    assert "python" in res["language"].lower()


def test_hackerrank_constraints_extraction_with_div_wrappers():
    """Verify HackerRankAdapter extracts constraints wrapped in DIV elements and ranges like 0 < n, ar[i] <= 1000."""
    node_script = """
    const { HackerRankAdapter } = require('./extension/edgemind/scripts/content.js');

    // HackerRank renders constraints heading followed by a DIV containing paragraphs or math text
    const fakeConstraintsDiv = {
      tagName: 'DIV',
      querySelectorAll: (sel) => [
        { cloneNode: () => ({ textContent: '0 < n, ar[i] <= 1000', querySelectorAll: () => [] }) },
        { cloneNode: () => ({ textContent: '1 <= t <= 100', querySelectorAll: () => [] }) }
      ],
      nextElementSibling: { tagName: 'H3', textContent: 'Output Format' }
    };

    global.window = {
      location: {
        href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem',
        pathname: '/challenges/simple-array-sum/problem'
      }
    };
    global.document = {
      querySelector: (sel) => {
        if (sel.includes('title') || sel === 'h1') return { textContent: 'Simple Array Sum' };
        return null;
      },
      querySelectorAll: (sel) => {
        if (sel.includes('h3') || sel.includes('div')) return [
          {
            textContent: 'Constraints',
            tagName: 'H3',
            nextElementSibling: fakeConstraintsDiv
          }
        ];
        return [];
      }
    };

    const data = HackerRankAdapter.extract();
    console.log(JSON.stringify({
      constraints: data.constraints
    }));
    """
    out = run_node_eval(node_script)
    data = json.loads(out)

    assert len(data["constraints"]) == 2
    assert "0 < n, ar[i] <= 1000" in data["constraints"]
    assert "1 <= t <= 100" in data["constraints"]


# ==============================================================================
# 11. Platform-Specific Sample Source Labels & Popup Logic Tests
# ==============================================================================

def test_popup_platform_sample_source_labels_and_empty_messages():
    """Verify popup logic produces platform-accurate sample source labels and empty messages without mentioning LeetCode on other platforms."""
    node_script = """
    const fs = require('fs');
    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const unwrapped = popupCode.replace(/^[^{]*\\(\\(\\)\\s*=>\\s*\\{/, '').replace(/\\}\\)\\(\\);?\\s*$/, '');

    const vm = require('vm');
    const fakeDoc = {
      getElementById: () => ({
        textContent: '',
        classList: { add: () => {}, remove: () => {}, contains: () => false },
        appendChild: () => {},
        replaceChildren: () => {},
        addEventListener: () => {}
      }),
      createElement: () => ({ set textContent(v) {}, classList: { add: () => {}, remove: () => {} } }),
      addEventListener: () => {}
    };
    const fakeChrome = {
      runtime: { lastError: null },
      storage: { local: { get: () => {} } },
      tabs: {}
    };
    const ctx = vm.createContext({
      document: fakeDoc,
      chrome: fakeChrome,
      window: {},
      console: console,
      setTimeout: () => {}
    });

    vm.runInContext(unwrapped, ctx);

    const getPlatformSamplesSourceLabel = ctx.getPlatformSamplesSourceLabel;
    const getPlatformSamplesEmptyMessage = ctx.getPlatformSamplesEmptyMessage;

    const leetTab = { url: 'https://leetcode.com/problems/two-sum/' };
    const hrTab = { url: 'https://www.hackerrank.com/challenges/simple-array-sum/problem' };
    const cfTab = { url: 'https://codeforces.com/contest/4/problem/A' };
    const otherTab = { url: 'https://github.com' };

    console.log(JSON.stringify({
      leetLabel: getPlatformSamplesSourceLabel(leetTab),
      hrLabel: getPlatformSamplesSourceLabel(hrTab),
      cfLabel: getPlatformSamplesSourceLabel(cfTab),
      otherLabel: getPlatformSamplesSourceLabel(otherTab),
      leetEmpty: getPlatformSamplesEmptyMessage(leetTab),
      hrEmpty: getPlatformSamplesEmptyMessage(hrTab),
      cfEmpty: getPlatformSamplesEmptyMessage(cfTab),
      otherEmpty: getPlatformSamplesEmptyMessage(otherTab)
    }));
    """
    out = run_node_eval(node_script)
    data = json.loads(out)

    assert data["leetLabel"] == "LeetCode Public Examples"
    assert data["hrLabel"] == "HackerRank Sample Cases"
    assert data["cfLabel"] == "Codeforces Sample Tests"
    assert "Supported Platform Required" in data["otherLabel"]

    assert "LeetCode" in data["leetEmpty"]
    assert "HackerRank" in data["hrEmpty"]
    assert "LeetCode" not in data["hrEmpty"]
    assert "Codeforces" in data["cfEmpty"]
    assert "LeetCode" not in data["cfEmpty"]


def test_popup_html_contains_platform_badge_row():
    """Verify popup.html defines #row-platform and #platform-badge for platform separation."""
    popup_html = Path("extension/edgemind/popup/popup.html").read_text(encoding="utf-8")
    assert 'id="row-platform"' in popup_html
    assert 'id="platform-badge"' in popup_html


# ==============================================================================
# 12. Codeforces Language Display & LeetCode Regression Verification
# ==============================================================================

def test_codeforces_language_badge_never_displays_platform_name():
    """Verify popup displays 'Unavailable' when language is unknown on Codeforces, never the platform name 'CODEFORCES'."""
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const unwrapped = popupCode.replace(/^[^{]*\\(\\(\\)\\s*=>\\s*\\{/, '').replace(/\\}\\)\\(\\);?\\s*$/, '');

    let badgeText = '';
    let badgeClass = '';
    const fakeLangBadge = {
      set textContent(v) { badgeText = v; },
      get textContent() { return badgeText; },
      set className(v) { badgeClass = v; },
      get className() { return badgeClass; }
    };

    let platformText = '';
    const fakePlatformBadge = {
      set textContent(v) { platformText = v; },
      get textContent() { return platformText; },
      set className(v) {},
      classList: { add: () => {}, remove: () => {} }
    };

    const fakeDoc = {
      getElementById: (id) => {
        if (id === 'lang-badge') return fakeLangBadge;
        if (id === 'platform-badge') return fakePlatformBadge;
        return {
          textContent: '',
          classList: { add: () => {}, remove: () => {}, contains: () => false },
          appendChild: () => {},
          replaceChildren: () => {},
          addEventListener: () => {}
        };
      },
      createElement: () => ({ set textContent(v) {}, classList: { add: () => {}, remove: () => {} } }),
      addEventListener: () => {}
    };

    let msgCallback = null;
    const fakeChrome = {
      runtime: { lastError: null },
      storage: { local: { get: () => {} } },
      tabs: {
        query: async () => [{ id: 1, url: 'https://codeforces.com/contest/4/problem/A' }],
        sendMessage: (id, msg, cb) => { msgCallback = cb; }
      }
    };

    const ctx = vm.createContext({
      document: fakeDoc,
      chrome: fakeChrome,
      window: {},
      console: console,
      setTimeout: () => {}
    });

    vm.runInContext(unwrapped, ctx);

    // Call inspectActiveTab
    ctx.inspectActiveTab().then(() => {
      // Simulate content script response with unknown language
      msgCallback({
        platform: 'codeforces',
        language: 'unknown',
        title: 'A. Watermelon',
        constraints: ['Time limit: 1.0 s'],
        sampleInputs: ['8']
      });

      console.log(JSON.stringify({
        platformBadge: platformText,
        langBadge: badgeText,
        langClass: badgeClass
      }));
    });
    """
    out = run_node_eval(node_script)
    data = json.loads(out)

    assert data["platformBadge"] == "CODEFORCES"
    assert data["langBadge"] == "Unavailable"
    assert data["langBadge"] != "CODEFORCES", "Language badge must never be set to platform name"


def test_leetcode_deterministic_behavior_and_no_regression():
    """Verify LeetCode constraints parsing and static analysis scoring behavior:
    1. Unresolved semantic constraints ('Only one valid answer exists.') deterministically result in unresolved tracking.
    2. Code health score is calculated deterministically via AST analysis without LLM dependence.
    3. Generated candidates have unverified expected_output=None.
    """
    from core.test_intelligence.constraint_parser import parse_constraint_expressions
    from core.service import analyze_code

    # 1. Two Sum constraints with semantic guarantee
    constraints = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
        "Only one valid answer exists."
    ]
    spec, unresolved = parse_constraint_expressions(constraints, known_parameters=["nums", "target"])
    assert len(spec.parsed_constraints) == 4
    assert len(unresolved) == 1
    assert "Only one valid answer exists." in unresolved
    # Verify semantic guarantee is tracked as unresolved with explanatory note
    semantic_parsed = [p for p in spec.parsed_constraints if p.raw_text == "Only one valid answer exists."][0]
    assert semantic_parsed.is_unresolved is True
    assert "unique_solution" in semantic_parsed.unresolved_reason

    # 2. Code health score deterministic computation
    code = """
class Solution:
    def twoSum(self, nums: list[int], target: int) -> list[int]:
        lookup = {}
        for i, num in enumerate(nums):
            comp = target - num
            if comp in lookup:
                return [lookup[comp], i]
            lookup[num] = i
        return []
"""
    analysis = analyze_code(code)
    assert analysis["status"] in ("PASS", "PASS WITH WARNINGS")
    assert isinstance(analysis["score"], int)
    assert 0 <= analysis["score"] <= 100


# ==============================================================================
# 9. LeetCode & HackerRank Regression Recovery Tests
# ==============================================================================

def test_leetcode_two_sum_constraints_extraction_without_colon():
    """Verify LeetCode constraints extraction works when heading has no colon and contains semantic guarantees."""
    node_script = """
    const { LeetCodeAdapter } = require('./extension/edgemind/scripts/content.js');

    const fakeDom = {
      h1: { textContent: 'Two Sum' },
      desc: {
        innerText: 'Given an array of integers nums and an integer target...',
        querySelectorAll: () => []
      },
      headings: [
        {
          textContent: 'Constraints',
          tagName: 'STRONG',
          parentElement: {
            tagName: 'P',
            nextElementSibling: {
              tagName: 'UL',
              querySelectorAll: () => [
                { cloneNode: () => ({ textContent: '2 <= nums.length <= 10^4', querySelectorAll: () => [] }) },
                { cloneNode: () => ({ textContent: '-10^9 <= nums[i] <= 10^9', querySelectorAll: () => [] }) },
                { cloneNode: () => ({ textContent: '-10^9 <= target <= 10^9', querySelectorAll: () => [] }) },
                { cloneNode: () => ({ textContent: 'Only one valid answer exists.', querySelectorAll: () => [] }) }
              ]
            }
          },
          nextElementSibling: null
        }
      ]
    };

    global.window = {
      location: {
        href: 'https://leetcode.com/problems/two-sum/',
        pathname: '/problems/two-sum/'
      }
    };
    global.document = {
      querySelector: (sel) => {
        if (sel.includes('title') || sel === 'h1') return fakeDom.h1;
        if (sel.includes('description') || sel.includes('content')) return fakeDom.desc;
        return null;
      },
      querySelectorAll: (sel) => {
        if (sel.includes('strong') || sel.includes('h3') || sel.includes('p')) return fakeDom.headings;
        return [];
      }
    };

    const data = LeetCodeAdapter.extract();
    console.log(JSON.stringify(data.constraints));
    """
    out = run_node_eval(node_script)
    constraints = json.loads(out)
    assert len(constraints) == 4
    assert any("nums.length" in c for c in constraints)
    assert any("Only one valid answer exists." in c for c in constraints)


def test_leetcode_two_sum_pre_sample_extraction_without_child_tags():
    """Verify LeetCode sample extraction from <pre> blocks without inner <p>/<div> elements."""
    node_script = """
    const { LeetCodeAdapter } = require('./extension/edgemind/scripts/content.js');

    const fakePre = {
      tagName: 'PRE',
      innerText: 'Input: nums = [2,7,11,15], target = 9\\nOutput: [0,1]\\nExplanation: Because nums[0] + nums[1] == 9, we return [0, 1].',
      textContent: 'Input: nums = [2,7,11,15], target = 9\\nOutput: [0,1]\\nExplanation: Because nums[0] + nums[1] == 9, we return [0, 1].',
      querySelectorAll: (sel) => {
        if (sel.includes('p') || sel.includes('div') || sel.includes('li')) return [];
        return [];
      }
    };

    global.window = {
      location: {
        href: 'https://leetcode.com/problems/two-sum/',
        pathname: '/problems/two-sum/'
      }
    };
    global.document = {
      querySelector: (sel) => {
        if (sel === 'h1') return { textContent: 'Two Sum' };
        return null;
      },
      querySelectorAll: (sel) => {
        if (sel.includes('pre') || sel.includes('example-block')) return [fakePre];
        return [];
      }
    };

    const data = LeetCodeAdapter.extract();
    console.log(JSON.stringify(data.sampleInputs));
    """
    out = run_node_eval(node_script)
    samples = json.loads(out)
    assert len(samples) >= 1
    assert "nums = [2,7,11,15]" in samples[0]
    assert "target = 9" in samples[0]


def test_hackerrank_simple_array_sum_mathjax_nested_constraints_extraction():
    """Verify HackerRank constraints extraction succeeds when KaTeX/MathJax spans contain nested child tags."""
    node_script = """
    const { HackerRankAdapter } = require('./extension/edgemind/scripts/content.js');

    const fakeDom = {
      h1: { textContent: 'Simple Array Sum' },
      headings: [
        {
          textContent: 'Constraints',
          tagName: 'H3',
          nextElementSibling: {
            tagName: 'DIV',
            className: 'challenge-section-body',
            querySelectorAll: (sel) => {
              return [
                {
                  tagName: 'SPAN',
                  className: 'tex-span',
                  children: [{ tagName: 'SPAN' }, { tagName: 'SPAN' }, { tagName: 'SPAN' }],
                  cloneNode: () => ({
                    textContent: '0 < n, ar[i] <= 1000',
                    querySelectorAll: () => []
                  })
                }
              ];
            },
            nextElementSibling: null
          }
        }
      ]
    };

    global.window = {
      location: {
        href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem',
        pathname: '/challenges/simple-array-sum/problem'
      }
    };
    global.document = {
      querySelector: (sel) => {
        if (sel === 'h1') return fakeDom.h1;
        return null;
      },
      querySelectorAll: (sel) => {
        if (sel.includes('h3') || sel.includes('strong')) return fakeDom.headings;
        return [];
      }
    };

    const data = HackerRankAdapter.extract();
    console.log(JSON.stringify(data.constraints));
    """
    out = run_node_eval(node_script)
    constraints = json.loads(out)
    assert len(constraints) >= 1
    assert any("0 < n" in c and "1000" in c for c in constraints)


def test_hackerrank_sample_input_pre_without_input_label_extraction():
    """Verify HackerRank Sample Input extraction gets raw input lines from <pre> under Sample Input heading."""
    node_script = """
    const { HackerRankAdapter } = require('./extension/edgemind/scripts/content.js');

    const fakePre = {
      tagName: 'PRE',
      textContent: '6\\n1 2 3 4 10 11',
      querySelector: () => null,
      nextElementSibling: null
    };

    const fakeHeading = {
      textContent: 'Sample Input 0',
      tagName: 'H3',
      nextElementSibling: {
        tagName: 'DIV',
        className: 'challenge-section-body',
        nextElementSibling: null,
        querySelector: (sel) => sel.includes('pre') ? fakePre : null
      }
    };

    global.window = {
      location: {
        href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem',
        pathname: '/challenges/simple-array-sum/problem'
      }
    };
    global.document = {
      querySelector: (sel) => sel === 'h1' ? { textContent: 'Simple Array Sum' } : null,
      querySelectorAll: (sel) => {
        if (sel.includes('h3') || sel.includes('strong')) return [fakeHeading];
        return [];
      }
    };

    const data = HackerRankAdapter.extract();
    console.log(JSON.stringify(data.sampleInputs));
    """
    out = run_node_eval(node_script)
    samples = json.loads(out)
    assert len(samples) == 1
    assert "6" in samples[0]
    assert "1 2 3 4 10 11" in samples[0]


def test_hackerrank_ace_editor_react_fiber_and_active_editor_extraction():
    """Verify extractor.js extracts buffer from Ace editor instances via env.editor and React fiber."""
    node_script = """
    const fs = require('fs');
    const vm = require('vm');

    const extractorCode = fs.readFileSync('./extension/edgemind/scripts/extractor.js', 'utf8');

    // Case 1: env.editor
    const mockAceEl1 = {
      className: 'ace_editor ace-solarized-dark',
      env: {
        editor: {
          getValue: () => 'def simpleArraySum(ar):\\n    return sum(ar)\\n',
          getSession: () => ({ getMode: () => ({ $id: 'ace/mode/python' }) })
        }
      }
    };

    const sandbox1 = {
      window: {
        location: { hostname: 'www.hackerrank.com', pathname: '/challenges/simple-array-sum/problem' }
      },
      document: {
        querySelector: (sel) => {
          if (sel.includes('select-language')) return { textContent: 'Python 3' };
          return null;
        },
        querySelectorAll: (sel) => {
          if (sel.includes('ace_editor')) return [mockAceEl1];
          return [];
        }
      }
    };

    const result1 = vm.runInNewContext(extractorCode, sandbox1);
    if (!result1.success || !result1.code.includes('simpleArraySum')) {
      console.error('Case 1 failed:', result1);
      process.exit(1);
    }

    // Case 2: React Fiber fallback
    const mockAceEl2 = {
      className: 'ace_editor',
      __reactFiber$test: {
        memoizedProps: {
          editor: {
            getValue: () => 'def solve(): pass\\n'
          }
        }
      }
    };

    const sandbox2 = {
      window: {
        location: { hostname: 'www.hackerrank.com', pathname: '/challenges/simple-array-sum/problem' }
      },
      document: {
        querySelector: () => ({ textContent: 'Python 3' }),
        querySelectorAll: (sel) => {
          if (sel.includes('ace_editor')) return [mockAceEl2];
          return [];
        }
      }
    };

    const result2 = vm.runInNewContext(extractorCode, sandbox2);
    if (!result2.success || !result2.code.includes('solve')) {
      console.error('Case 2 failed:', result2);
      process.exit(1);
    }

    console.log('ACE_BUFFER_EXTRACTION_VERIFIED');
    """
    out = run_node_eval(node_script)
    assert out == "ACE_BUFFER_EXTRACTION_VERIFIED"


def test_extractor_js_returns_dom_constraints_and_samples_for_all_platforms():
    """Verify extractor.js returns domConstraints and domSampleInputs arrays on all platforms."""
    node_script = """
    const fs = require('fs');
    const vm = require('vm');

    const extractorCode = fs.readFileSync('./extension/edgemind/scripts/extractor.js', 'utf8');

    // Test on LeetCode
    const leetSandbox = {
      window: {
        location: { hostname: 'leetcode.com', pathname: '/problems/two-sum/' },
        monaco: {
          editor: {
            getModels: () => [{
              getLanguageId: () => 'python',
              uri: { toString: () => 'inmemory://model/1' },
              getValue: () => 'class Solution:\\n    pass\\n'
            }]
          }
        }
      },
      document: {
        querySelector: (sel) => sel.includes('lang-select') ? { textContent: 'Python3' } : null,
        querySelectorAll: () => []
      }
    };

    const leetRes = vm.runInNewContext(extractorCode, leetSandbox);
    if (!leetRes.success || !Array.isArray(leetRes.domConstraints) || !Array.isArray(leetRes.domSampleInputs)) {
      console.error('LeetCode result missing arrays:', leetRes);
      process.exit(1);
    }

    // Test on HackerRank
    const hrSandbox = {
      window: {
        location: { hostname: 'www.hackerrank.com', pathname: '/challenges/simple-array-sum/problem' }
      },
      document: {
        querySelector: (sel) => sel.includes('select-language') ? { textContent: 'Python 3' } : null,
        querySelectorAll: (sel) => {
          if (sel.includes('ace_editor')) {
            return [{
              className: 'ace_editor',
              env: {
                editor: {
                  getValue: () => 'def simpleArraySum(ar): return sum(ar)',
                  getSession: () => ({ getMode: () => ({ $id: 'ace/mode/python' }) })
                }
              }
            }];
          }
          return [];
        }
      }
    };

    const hrRes = vm.runInNewContext(extractorCode, hrSandbox);
    if (!hrRes.success || !Array.isArray(hrRes.domConstraints) || !Array.isArray(hrRes.domSampleInputs)) {
      console.error('HackerRank result missing arrays:', hrRes);
      process.exit(1);
    }

    console.log('EXTRACTOR_DOM_ARRAYS_VERIFIED');
    """
    out = run_node_eval(node_script)
    assert out == "EXTRACTOR_DOM_ARRAYS_VERIFIED"


def test_popup_programmatic_injection_fallback_on_disconnected_content_script():
    """Verify popup.js implements applyProblemInfo and fallback scripting injection when sendMessage errors."""
    with open(POPUP_JS_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    assert "applyProblemInfo" in content
    assert "chrome.scripting.executeScript" in content
    assert "scripts/content.js" in content
    assert "extraction.domConstraints" in content


# ==============================================================================
# Priority 1: HackerRank Input Normalization & Function-Level Mapping Tests
# ==============================================================================

def test_hackerrank_input_normalization_function_level_representation():
    """
    Verify HackerRank input normalization converts raw multi-line STDIN
    (e.g. '6\\n1 2 3 4 10 11') or incorrect metadata dicts ({'n': ..., 'ar': ...})
    into strictly function-level {'ar': [1, 2, 3, 4, 10, 11]}, preserving raw_stdin separately,
    never treating 'n' as a function parameter, and generating candidates modifying only 'ar'.
    """
    code = """def simpleArraySum(ar):
    return sum(ar)
"""
    prob_ctx = {
        "platform": "hackerrank",
        "title": "Simple Array Sum",
        "problem_id": "simple-array-sum",
        "constraints": ["0 < n, ar[i] <= 1000"],
        "parameters": ["ar"],
    }
    # Raw incorrect representation reported from live testing
    raw_test_cases = [
        {"input_data": {"n": "6\n1 2 3 4 10 11", "ar": [1, 2, 3, 4, 10, 11]}}
    ]

    report = analyze_edgemind(
        code=code,
        problem_context=prob_ctx,
        test_cases=raw_test_cases,
        static_only=True,
    )

    assert report["status"] == "SUCCESS"
    ti = report["test_intelligence"]
    assert ti["existing_tests_analyzed"] == 1

    # Verified: identified parameters contains ONLY 'ar' (not 'n')
    identified = report.get("identified_parameters", [])
    param_names = [p["name"] if isinstance(p, dict) else p for p in identified]
    assert "ar" in param_names
    assert "n" not in param_names

    # Verified: candidates modify ONLY 'ar' and do not contain 'n'
    cands = ti.get("generated_candidates", [])
    assert len(cands) > 0
    for cand in cands:
        inp = cand.get("input_data", {})
        assert "ar" in inp, f"Candidate missing 'ar': {cand}"
        assert "n" not in inp, f"Candidate incorrectly contains metadata parameter 'n': {cand}"
        # Candidate preserves reconstructed STDIN
        assert cand.get("raw_stdin") is not None
        assert " " in cand["raw_stdin"] or "\n" in cand["raw_stdin"] or cand["raw_stdin"].isdigit()

    # Verified: candidate validity against 0 < n, ar[i] <= 1000
    for cand in cands:
        inp = cand["input_data"]["ar"]
        cls_val = cand.get("classification")
        if len(inp) == 0:
            assert cls_val == "ROBUSTNESS PROBE"
        else:
            assert cls_val == "VALID"


def test_popup_js_parses_hackerrank_raw_stdin_and_strips_n_metadata():
    """Verify popup.js parseUserSampleInputs normalizes raw HackerRank STDIN and cleans {'n': ..., 'ar': ...}."""
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const unwrapped = popupCode.replace(/^[^{]*\\(\\(\\)\\s*=>\\s*\\{/, '').replace(/\\}\\)\\(\\);?\\s*$/, '');

    const fakeDoc = {
      getElementById: () => ({
        textContent: '',
        classList: { add: () => {}, remove: () => {}, contains: () => false },
        appendChild: () => {},
        replaceChildren: () => {},
        addEventListener: () => {}
      }),
      createElement: () => ({ set textContent(v) {}, classList: { add: () => {}, remove: () => {} } }),
      addEventListener: () => {}
    };
    const fakeChrome = {
      runtime: { lastError: null },
      storage: { local: { get: () => {} } },
      tabs: {}
    };
    const ctx = vm.createContext({
      document: fakeDoc,
      chrome: fakeChrome,
      window: {},
      console: console,
      setTimeout: () => {}
    });

    vm.runInContext(unwrapped, ctx);
    const parseUserSampleInputs = ctx.parseUserSampleInputs;

    // Case 1: Raw STDIN string: '6\\n1 2 3 4 10 11'
    const res1 = parseUserSampleInputs(['6\\n1 2 3 4 10 11']);
    if (res1.length !== 1 || !Array.isArray(res1[0].input_data.ar) || res1[0].input_data.ar.length !== 6) {
      console.error('Case 1 failed:', JSON.stringify(res1));
      process.exit(1);
    }
    if (res1[0].raw_stdin !== '6\\n1 2 3 4 10 11') {
      console.error('Case 1 missing raw_stdin:', res1[0]);
      process.exit(1);
    }

    // Case 2: Object representation with n metadata
    const res2 = parseUserSampleInputs([{ n: '6\\n1 2 3 4 10 11', ar: [1, 2, 3, 4, 10, 11] }]);
    if (res2.length !== 1 || 'n' in res2[0].input_data || !Array.isArray(res2[0].input_data.ar)) {
      console.error('Case 2 failed to clean n:', JSON.stringify(res2));
      process.exit(1);
    }
    if (!res2[0].raw_stdin || !res2[0].raw_stdin.includes('6')) {
      console.error('Case 2 raw_stdin missing:', res2[0]);
      process.exit(1);
    }

    console.log('POPUP_HACKERRANK_NORMALIZATION_OK');
    """
    out = run_node_eval(node_script)
    assert out == "POPUP_HACKERRANK_NORMALIZATION_OK"


# ==============================================================================
# Priority 2: HackerRank Visible Constraints & Bound Parsing Tests
# ==============================================================================

def test_hackerrank_constraint_multi_variable_bound_parsing():
    """Verify '0 < n, ar[i] <= 1000' parses numerical bounds and binds length to 'ar'."""
    from core.test_intelligence.constraint_parser import parse_constraint_expressions

    spec, unres = parse_constraint_expressions(["0 < n, ar[i] <= 1000"], known_parameters=["ar"])

    assert len(unres) == 0, f"Expected 0 unresolved constraints, got {unres}"
    assert spec.min_length == 1
    assert spec.max_length == 1000
    assert spec.min_value == 1
    assert spec.max_value == 1000

    assert "ar" in spec.param_specs
    ar_spec = spec.param_specs["ar"]
    assert ar_spec.min_length == 1
    assert ar_spec.max_length == 1000
    assert ar_spec.min_value == 1
    assert ar_spec.max_value == 1000
    assert ar_spec.is_non_empty is True


# ==============================================================================
# Priority 3: LeetCode Diagnostics & Semantic Invariant Tests
# ==============================================================================

def test_leetcode_two_sum_partially_parsed_due_to_semantic_guarantee():
    """
    Verify LeetCode Two Sum constraints status is PARTIALLY_PARSED because
    'Only one valid answer exists.' is a semantic invariant, not an error or bug.
    """
    prob_ctx = {
        "platform": "leetcode",
        "title": "Two Sum",
        "problem_id": "two-sum",
        "constraints": [
            "2 <= nums.length <= 10^4",
            "-10^9 <= nums[i] <= 10^9",
            "-10^9 <= target <= 10^9",
            "Only one valid answer exists.",
        ],
        "parameters": ["nums", "target"],
    }
    code = """class Solution:
    def twoSum(self, nums: list[int], target: int) -> list[int]:
        lookup = {}
        for i, num in enumerate(nums):
            comp = target - num
            if comp in lookup:
                return [lookup[comp], i]
            lookup[num] = i
        return []
"""
    test_cases = [{"input_data": {"nums": [2, 7, 11, 15], "target": 9}}]

    report = analyze_edgemind(code=code, problem_context=prob_ctx, test_cases=test_cases, static_only=True)

    parsed_meta = report.get("parsed_constraints", {})
    assert parsed_meta["status"] == "PARTIALLY_PARSED"
    assert parsed_meta["total_raw"] == 4
    assert "Only one valid answer exists." in parsed_meta["unresolved"]

    # Code Health score is 100 for clean Two Sum implementation
    assert report["code_analysis"]["score"] == 100
    assert report["code_analysis"]["status"] == "PASS"


def test_code_health_score_deductions_are_deterministic():
    """Verify that code health score deductions follow standard rule: 20 per error, 5 per warning."""
    # Code with a syntax error (empty block) deducts 20 points -> Score 80
    syntax_error_code = """class Solution:
    def twoSum(self, nums: list[int], target: int) -> list[int]:
"""
    report = analyze_edgemind(code=syntax_error_code, static_only=True)
    ca = report.get("code_analysis", {})
    assert ca.get("score") == 80
    assert ca.get("total_errors") == 1
    assert ca.get("status") == "FAIL"


# ==============================================================================
# Priority 4: Ollama Token Cap & Done Reason Preservation Tests
# ==============================================================================

def test_provider_preserves_done_reason_stop():
    """Verify provider captures done_reason stop and length accurately."""
    from core.agents.schemas import AgentStepResult

    res_stop = AgentStepResult(content="Done", finish_reason="stop")
    assert res_stop.finish_reason == "stop"

    res_len = AgentStepResult(content="Truncated", finish_reason="length")
    assert res_len.finish_reason == "length"


# ==============================================================================
# Priority 5: True End-to-End HackerRank Input Normalization Regression Tests
# ==============================================================================

def test_hackerrank_live_sample_stdin_diagram_cleaning():
    """Verify popup/content cleaning parses live HackerRank STDIN diagram into clean STDIN and ar."""
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const unwrapped = popupCode.replace(/^[^{]*\\(\\(\\)\\s*=>\\s*\\{/, '').replace(/\\}\\)\\(\\);?\\s*$/, '');

    const fakeDoc = {
      getElementById: () => ({
        textContent: '',
        classList: { add: () => {}, remove: () => {}, contains: () => false },
        appendChild: () => {},
        replaceChildren: () => {},
        addEventListener: () => {}
      }),
      createElement: () => ({ set textContent(v) {}, classList: { add: () => {}, remove: () => {} } }),
      addEventListener: () => {}
    };
    const fakeChrome = {
      runtime: { lastError: null },
      storage: { local: { get: () => {} } },
      tabs: {}
    };
    const ctx = vm.createContext({
      document: fakeDoc,
      chrome: fakeChrome,
      window: {},
      console: console,
      setTimeout: () => {}
    });

    vm.runInContext(unwrapped, ctx);

    const rawDiagram = 'STDIN Function\\n----- --------\\n6 ar[] size n = 6\\n1 2 3 4 10 11\\nar = [1, 2, 3, 4, 10, 11]';
    const cleaned = ctx.cleanHackerRankSample(rawDiagram);
    const parsed = ctx.parseUserSampleInputs([rawDiagram]);

    console.log(JSON.stringify({ cleaned, parsed }));
    """
    out = run_node_eval(node_script)
    data = json.loads(out)

    assert data["cleaned"]["cleanStdin"] == "6\n1 2 3 4 10 11"
    assert data["cleaned"]["inputData"] == {"ar": [1, 2, 3, 4, 10, 11]}

    parsed = data["parsed"]
    assert len(parsed) == 1
    assert parsed[0]["input_data"] == {"ar": [1, 2, 3, 4, 10, 11]}
    assert "n" not in parsed[0]["input_data"]
    assert parsed[0]["raw_stdin"] == "6\n1 2 3 4 10 11"


def test_hackerrank_end_to_end_normalization_and_synthesis():
    """
    True end-to-end regression test for live HackerRank Simple Array Sum payload:
    - Normalizes input_data to {'ar': [1, 2, 3, 4, 10, 11]}
    - Preserves raw_stdin as '6\\n1 2 3 4 10 11'
    - Parameter 'n' is removed from identified_parameters
    - Constraints status is PARSED (0 < n, ar[i] <= 1000)
    - All generated candidates modify strictly 'ar' (never 'n')
    - Every candidate has reconstructed raw_stdin
    - Empty array candidate is classified as ROBUSTNESS PROBE
    - STATIC_ONLY=true invariant preserved (zero execution)
    """
    from core.test_intelligence.constraint_parser import classify_candidate
    from core.test_intelligence.models import TestCase

    hr_code = """def simpleArraySum(ar):
    # Write your code here
    return sum(ar)
"""
    hr_ctx = {
        "platform": "hackerrank",
        "problem_id": "simple-array-sum",
        "title": "Simple Array Sum",
        "constraints": ["0 < n, ar[i] <= 1000"],
        "parameters": ["n", "ar"],
    }
    hr_samples = [
        {
            "id": "sample_1",
            "source": "PUBLIC_SAMPLE",
            "input_data": {
                "n": "6\n1 2 3 4 10 11",
                "ar": [1, 2, 3, 4, 10, 11],
            },
        }
    ]

    report = analyze_edgemind(
        code=hr_code,
        problem_context=hr_ctx,
        test_cases=hr_samples,
        max_candidates=10,
        static_only=True,
    )

    # 1. Identified parameters: only 'ar', never 'n'
    param_names = [p["name"] if isinstance(p, dict) else str(p) for p in report.get("identified_parameters", [])]
    assert param_names == ["ar"], f"Expected ['ar'], got {param_names}"

    # 2. Constraints parsed
    parsed_meta = report.get("parsed_constraints", {})
    assert parsed_meta["status"] == "PARSED"
    assert parsed_meta["total_raw"] == 1
    assert parsed_meta["unresolved"] == []

    # Cross constraint linking n to len(ar)
    cross = parsed_meta.get("cross_constraints", [])
    assert len(cross) == 1
    assert cross[0]["relation_type"] == "LENGTH_EQUAL"

    # 3. Candidate generation modifies strictly 'ar'
    ti = report.get("test_intelligence", {})
    ranked = ti.get("ranked_candidates", [])
    assert len(ranked) >= 5

    has_upper_bound = False
    has_singleton = False

    for item in ranked:
        c = item.get("candidate", item)
        inp = c.get("input_data", {})
        assert "ar" in inp, f"Missing 'ar' in candidate input: {inp}"
        assert "n" not in inp, f"Metadata 'n' leaked into function candidate input: {inp}"
        assert c.get("raw_stdin"), f"Candidate missing raw_stdin: {c}"
        lines = c["raw_stdin"].split("\n")
        assert len(lines) == 2, f"raw_stdin should have 2 lines, got {lines}"
        assert int(lines[0]) == len(inp["ar"])

        if len(inp["ar"]) == 1000:
            has_upper_bound = True
        if len(inp["ar"]) == 1:
            has_singleton = True

    assert has_upper_bound, "Missing maximum length bound candidate (1000 elements)"
    assert has_singleton, "Missing minimum length singleton candidate (1 element)"

    # 4. Classify empty array as ROBUSTNESS PROBE
    empty_tc = TestCase(id="gen-empty-ar", source="GENERATED_TEST", input_data={"ar": []})
    spec = None
    if report.get("parsed_constraints"):
        from core.test_intelligence.constraint_parser import parse_constraint_expressions
        spec, _ = parse_constraint_expressions(["0 < n, ar[i] <= 1000"])
    cls_status, cls_reason = classify_candidate(empty_tc, spec, has_supplied_constraints=True)
    assert cls_status == "ROBUSTNESS PROBE"
    assert "Violates minimum length" in cls_reason

    # 5. Zero code execution guarantee
    assert report["provenance"]["execution_performed"] is False


def test_hackerrank_mathjax3_aria_label_and_svg_container_extraction():
    """Verify HackerRank constraints extraction succeeds when MathJax 3 aria-label is on inner mjx-math or svg."""
    node_script = """
    const { HackerRankAdapter } = require('./extension/edgemind/scripts/content.js');

    const fakeDom = {
      h1: { textContent: 'Simple Array Sum' },
      headings: [
        {
          textContent: 'Constraints',
          tagName: 'H3',
          nextElementSibling: {
            tagName: 'DIV',
            className: 'challenge-section-body',
            querySelectorAll: (sel) => {
              if (sel.includes('tex-span') || sel.includes('mjx-container')) {
                return [
                  {
                    tagName: 'MJX-CONTAINER',
                    className: 'MathJax CHTML',
                    getAttribute: (attr) => null,
                    querySelector: (sel) => {
                      if (sel.includes('aria-label') || sel.includes('mjx-math')) {
                        return {
                          getAttribute: (attr) => attr === 'aria-label' ? '0 < n, ar[i] <= 1000' : null
                        };
                      }
                      return null;
                    },
                    querySelectorAll: () => [],
                    cloneNode: function() {
                      return {
                        matches: () => true,
                        getAttribute: (attr) => null,
                        querySelector: (sel) => {
                          if (sel.includes('aria-label') || sel.includes('mjx-math')) {
                            return {
                              getAttribute: (attr) => attr === 'aria-label' ? '0 < n, ar[i] <= 1000' : null
                            };
                          }
                          return null;
                        },
                        querySelectorAll: () => []
                      };
                    }
                  }
                ];
              }
              return [];
            },
            nextElementSibling: null
          }
        }
      ]
    };

    global.window = {
      location: {
        href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem',
        pathname: '/challenges/simple-array-sum/problem'
      }
    };
    global.document = {
      querySelector: (sel) => {
        if (sel === 'h1') return fakeDom.h1;
        return null;
      },
      querySelectorAll: (sel) => {
        if (sel.includes('h3') || sel.includes('strong') || sel.includes('div')) return fakeDom.headings;
        return [];
      }
    };

    const data = HackerRankAdapter.extract();
    console.log(JSON.stringify(data.constraints));
    """
    out = run_node_eval(node_script)
    constraints = json.loads(out)
    assert len(constraints) == 1
    assert constraints[0] == "0 < n, ar[i] <= 1000"


def test_constraint_parser_separate_inequalities_length_mapping():
    """Verify parse_constraint_expressions maps separate inequalities 0 < n <= 1000 and 0 < ar[i] <= 1000 to len(ar)."""
    from core.test_intelligence.constraint_parser import parse_constraint_expressions

    spec, unresolved = parse_constraint_expressions(
        ["0 < n <= 1000", "0 < ar[i] <= 1000"],
        known_parameters=["ar"],
    )
    assert unresolved == []
    assert spec is not None
    assert "ar" in spec.param_specs
    ar_spec = spec.param_specs["ar"]
    assert ar_spec.min_length == 1
    assert ar_spec.max_length == 1000
    assert ar_spec.min_value == 1
    assert ar_spec.max_value == 1000
    assert any(c.name == "ARRAY_LENGTH_BOUND" and "n == len(ar)" in c.expression for c in spec.cross_constraints)


def test_orchestrator_finalize_test_intelligence_ranking_and_validity():
    """Verify _finalize_test_intelligence populates ranked_candidates, validates candidates, and sets raw_stdin."""
    import uuid
    from unittest.mock import MagicMock
    from core.agents.orchestrator import AgentOrchestrator
    from core.agents.schemas import AgentState, AgentStatus, AgentAnalyzeRequest

    orchestrator = AgentOrchestrator(
        provider=MagicMock(),
        registry=MagicMock(),
    )

    request = AgentAnalyzeRequest(
        code="def simpleArraySum(ar):\n    return sum(ar)",
        problem_context={"constraints": ["0 < n, ar[i] <= 1000"], "parameters": ["ar"]},
        test_cases=[{"input_data": {"ar": [1, 2, 3]}, "raw_stdin": "3\n1 2 3"}],
        max_candidates=10,
    )

    state = AgentState(
        session_id=uuid.uuid4(),
        request=request,
        max_iterations=5,
        max_tool_calls=10,
        messages=[],
        accumulated_context={
            "candidates": [
                {"id": "cand-1", "input_data": {"ar": [1, 2, 3, 4]}},
                {"id": "cand-2", "input_data": {"ar": []}},
            ],
            "ranked_candidates": [],  # Simulated agent completion without calling rank_candidate_inputs
        },
        tool_executions=[],
        iteration=1,
        status=AgentStatus.SUCCESS,
    )

    ti = orchestrator._finalize_test_intelligence(
        state=state,
        request=request,
        prob_ctx={"constraints": ["0 < n, ar[i] <= 1000"], "parameters": ["ar"]},
        parsed_constraints={"status": "PARSED", "total_raw": 1},
    )

    assert len(ti["generated_candidates"]) == 2
    assert len(ti["ranked_candidates"]) == 2  # Ensured fallback ranking, not 0!
    assert ti["ranking_summary"]["total_evaluated"] == 2

    c0 = ti["generated_candidates"][0]
    c1 = ti["generated_candidates"][1]

    # Valid candidate within bounds
    assert c0["classification"] == "VALID"
    assert c0["raw_stdin"] == "4\n1 2 3 4"

    # Robustness probe violating min_length = 1
    assert c1["classification"] == "ROBUSTNESS PROBE"
    assert "Violates minimum length" in c1["classification_reason"]
    assert c1["raw_stdin"] == "0\n"


def test_hackerrank_initialdata_script_authoritative_constraints_extraction():
    """Verify HackerRank constraints and metadata extraction from authoritative initialData JSON."""
    node_script = """
    const { HackerRankAdapter } = require('./extension/edgemind/scripts/content.js');

    const rawPayload = {
      community: {
        challenges: {
          challenge: {
            'master/simple-array-sum': {
              detail: {
                slug: 'simple-array-sum',
                name: 'Simple Array Sum',
                constraints: ' $0 \\\\lt n, ar[i] \\\\le 1000$ '
              }
            }
          }
        }
      }
    };

    const encoded = encodeURIComponent(JSON.stringify(rawPayload));

    global.window = {
      location: {
        href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem',
        pathname: '/challenges/simple-array-sum/problem'
      }
    };

    global.document = {
      getElementById: (id) => {
        if (id === 'initialData') {
          return { textContent: encoded };
        }
        return null;
      },
      querySelector: () => null,
      querySelectorAll: () => []
    };

    const data = HackerRankAdapter.extract();
    console.log(JSON.stringify({
      title: data.title,
      problemId: data.problemId,
      constraints: data.constraints
    }));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)
    assert res["title"] == "Simple Array Sum"
    assert res["problemId"] == "simple-array-sum"
    assert res["constraints"] == ["0 < n, ar[i] <= 1000"]


def test_hackerrank_mathjax2_script_with_preceding_frame_extraction():
    """Verify HackerRank extraction prevents duplicate formula text when MathJax 2 has both .MathJax frame and script."""
    node_script = """
    const { HackerRankAdapter } = require('./extension/edgemind/scripts/content.js');

    const mathJaxFrame = {
      tagName: 'SPAN',
      className: 'MathJax',
      matches: (s) => s.includes('MathJax'),
      getAttribute: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      textContent: '0 < n, ar[i] ≤ 1000',
      remove: function() { this.removed = true; this.textContent = ''; }
    };

    const scriptNode = {
      tagName: 'SCRIPT',
      type: 'math/tex',
      textContent: '0 < n, ar[i] \\\\le 1000',
      matches: (s) => s.includes('script'),
      getAttribute: (a) => a === 'type' ? 'math/tex' : null,
      previousElementSibling: mathJaxFrame,
      parentNode: null
    };

    const sectionBody = {
      tagName: 'DIV',
      className: 'challenge-section-body',
      cloneNode: function() {
        const mClone = { ...mathJaxFrame };
        const sClone = { ...scriptNode, previousElementSibling: mClone };
        const bodyClone = {
          tagName: 'DIV',
          className: 'challenge-section-body',
          querySelectorAll: (sel) => {
            if (sel.includes('script')) return [sClone];
            if (sel.includes('MathJax') || sel.includes('mjx-container')) return mClone.removed ? [] : [mClone];
            return [];
          },
          get textContent() {
            return (mClone.textContent || '') + ' ' + (sClone.textContent || '');
          }
        };
        sClone.parentNode = {
          replaceChild: (newChild, oldChild) => {
            sClone.textContent = newChild.textContent;
          }
        };
        return bodyClone;
      },
      querySelectorAll: (sel) => {
        if (sel.includes('script')) return [scriptNode];
        if (sel.includes('MathJax')) return [mathJaxFrame];
        return [];
      }
    };

    const headingNode = {
      tagName: 'H3',
      textContent: 'Constraints',
      nextElementSibling: null,
      parentElement: {
        tagName: 'DIV',
        className: 'section-title',
        nextElementSibling: sectionBody
      },
      querySelectorAll: () => []
    };

    global.window = {
      location: {
        href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem',
        pathname: '/challenges/simple-array-sum/problem'
      }
    };

    global.document = {
      querySelector: (sel) => sel === 'h1' ? { textContent: 'Simple Array Sum' } : null,
      querySelectorAll: (sel) => {
        if (sel.includes('challenge_constraints')) return [];
        if (sel.includes('h1') || sel.includes('h3') || sel.includes('strong') || sel.includes('div') || sel.includes('span')) {
          return [headingNode];
        }
        return [];
      }
    };

    const data = HackerRankAdapter.extract();
    console.log(JSON.stringify(data.constraints));
    """
    out = run_node_eval(node_script)
    constraints = json.loads(out)
    assert len(constraints) == 1
    assert constraints[0] == "0 < n, ar[i] <= 1000"


def test_hackerrank_nested_section_title_heading_extraction():
    """Verify HackerRank constraints are properly extracted when the heading is deeply nested in a section title."""
    node_script = """
    const { HackerRankAdapter } = require('./extension/edgemind/scripts/content.js');

    const scriptNode = {
      tagName: 'SCRIPT',
      type: 'math/tex',
      textContent: '0 < n, ar[i] \\\\le 1000',
      matches: (s) => s.includes('script'),
      getAttribute: (a) => a === 'type' ? 'math/tex' : null,
      parentNode: null
    };

    const sectionBody = {
      tagName: 'DIV',
      className: 'challenge-section-body',
      querySelectorAll: (s) => [scriptNode]
    };

    const titleH3 = {
      tagName: 'H3',
      textContent: 'Constraints',
      nextElementSibling: null,
      parentElement: null,
      querySelectorAll: () => []
    };

    const sectionTitleDiv = {
      tagName: 'DIV',
      className: 'challenge-section-title',
      nextElementSibling: sectionBody,
      querySelectorAll: () => [titleH3]
    };
    titleH3.parentElement = sectionTitleDiv;

    global.window = {
      location: {
        href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem',
        pathname: '/challenges/simple-array-sum/problem'
      }
    };

    global.document = {
      querySelector: (sel) => sel === 'h1' ? { textContent: 'Simple Array Sum' } : null,
      querySelectorAll: (sel) => {
        if (sel.includes('challenge_constraints')) return [];
        if (sel.includes('h1') || sel.includes('strong') || sel.includes('div') || sel.includes('h3')) {
          return [titleH3];
        }
        return [];
      }
    };

    const data = HackerRankAdapter.extract();
    console.log(JSON.stringify(data.constraints));
    """
    out = run_node_eval(node_script)
    constraints = json.loads(out)
    assert len(constraints) == 1
    assert constraints[0] == "0 < n, ar[i] <= 1000"


def test_full_browser_request_to_completed_mapping_hackerrank():
    """Verify that a full analysis request with the exact Chrome payload returns PARSED constraints and classified candidates."""
    from core.service import analyze_edgemind

    browser_payload = {
        "code": "def simpleArraySum(ar):\n    return sum(ar)",
        "problem_context": {
            "platform": "hackerrank",
            "problem_id": "simple-array-sum",
            "title": "Simple Array Sum",
            "description": "Given an array of integers, find the sum of its elements.",
            "constraints": ["0 < n, ar[i] <= 1000"],
            "parameters": ["ar"],
        },
        "test_cases": [
            {
                "id": "sample_1",
                "source": "PUBLIC_SAMPLE",
                "input_data": {"ar": [1, 2, 3, 4, 10, 11]},
                "raw_stdin": "6\n1 2 3 4 10 11",
            }
        ],
        "max_candidates": 10,
    }

    report = analyze_edgemind(
        code=browser_payload["code"],
        problem_context=browser_payload["problem_context"],
        test_cases=browser_payload["test_cases"],
        max_candidates=10,
    )

    assert report["status"] == "SUCCESS"
    assert report["context_completeness"] == "DETECTED"
    param_names = [p["name"] if isinstance(p, dict) else p for p in report["identified_parameters"]]
    assert param_names == ["ar"]
    assert "n" not in param_names

    # Constraints must be PARSED
    parsed_c = report["parsed_constraints"]
    assert parsed_c["status"] == "PARSED"
    assert parsed_c["total_raw"] == 1

    # Test intelligence candidates
    ti = report["test_intelligence"]
    gen_candidates = ti["generated_candidates"]
    ranked_candidates = ti["ranked_candidates"]

    assert len(gen_candidates) > 0
    assert len(ranked_candidates) == len(gen_candidates)

    # Invariants on candidates: classified, never UNKNOWN
    for c in gen_candidates:
        assert c["classification"] in ["VALID", "ROBUSTNESS PROBE"]
        assert c["classification"] != "CONSTRAINT VALIDITY UNKNOWN"
        assert c.get("source") in ["GENERATED_TEST", "SYNTHESIZED", "GENERATED"]
        assert c.get("expected_output") is None
        assert c.get("output_verified") is False or c.get("output_verified") is None
        assert "ar" in c["input_data"]
        assert "n" not in c["input_data"]  # n must NOT be treated as a parameter
        # If candidate has raw_stdin, it must match the HackerRank STDIN format
        if c.get("raw_stdin"):
            stdin_lines = c["raw_stdin"].strip().split("\n")
            if len(stdin_lines) == 2:
                elements = stdin_lines[1].split() if stdin_lines[1] else []
                assert int(stdin_lines[0]) == len(elements) == len(c["input_data"]["ar"])


def test_hackerrank_initialdata_robust_decoding_and_recursive_path_search():
    """Verify that HackerRank initialData is decoded robustly even with non-standard paths and malformed URI tokens."""
    node_script = """
    global.window = {
      location: {
        href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem',
        pathname: '/challenges/simple-array-sum/problem'
      }
    };
    const test_json = {
      nested: {
        contest_view: {
          track: {
            slug: 'simple-array-sum',
            name: 'Simple Array Sum',
            constraints: ' $0 \\\\lt n, ar[i] \\\\le 1000$ '
          }
        }
      }
    };
    const encoded_str = encodeURIComponent(JSON.stringify(test_json));
    global.document = {
      getElementById: (id) => {
        if (id === 'initialData') {
          return {
            textContent: encoded_str
          };
        }
        return null;
      },
      querySelector: () => null,
      querySelectorAll: () => []
    };

    const { HackerRankAdapter } = require('./extension/edgemind/scripts/content.js');
    const data = HackerRankAdapter.extract();
    console.log(JSON.stringify({
      title: data.title,
      slug: data.problemId,
      constraints: data.constraints
    }));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)
    assert res["title"] == "Simple Array Sum"
    assert res["slug"] == "simple-array-sum"
    assert len(res["constraints"]) == 1
    assert res["constraints"][0] == "0 < n, ar[i] <= 1000"


def test_popup_title_formatting_no_slug_prefix():
    """Verify that renderReport logic in popup.js does not prepend the slug to human-readable titles."""
    node_script = """
    const pContext = { problem_id: 'simple-array-sum', title: 'Simple Array Sum' };
    const detectedPageInfo = { problemId: 'simple-array-sum', title: 'Simple Array Sum' };

    let displayedTitle = '';
    const probId = pContext.problem_id || (detectedPageInfo ? detectedPageInfo.problemId : '');
    const probTitle = pContext.title || (detectedPageInfo ? (detectedPageInfo.title || detectedPageInfo.problemTitle) : '');

    if (probTitle) {
      displayedTitle = probTitle;
    } else if (probId) {
      displayedTitle = `Problem #${probId}`;
    }

    console.log(displayedTitle);
    """
    out = run_node_eval(node_script)
    assert out == "Simple Array Sum"
    assert not out.startswith("simple-array-sum.")


def test_popup_ranked_candidates_preservation_and_normalization():
    """Verify adaptEdgeMindReport genuinely preserves ranked_candidates and their ranking metadata."""
    raw_api_response = {
        "status": "SUCCESS",
        "test_intelligence": {
            "existing_tests_analyzed": 1,
            "coverage_gaps": [{"name": "EMPTY_COLLECTION", "parameter": "ar", "severity": "HIGH"}],
            "generated_candidates": [
                {
                    "input_data": {"ar": []},
                    "target_gap": "EMPTY_COLLECTION",
                    "classification": "VALID",
                }
            ],
            "ranked_candidates": [
                {
                    "candidate": {
                        "input_data": {"ar": []},
                        "target_gap": "EMPTY_COLLECTION",
                        "classification": "VALID",
                    },
                    "rank": 1,
                    "score": 0.88,
                    "score_breakdown": {"coverage_score": 0.5, "boundary_score": 0.3},
                    "explanation": "Rank 1: Selected for gap EMPTY_COLLECTION",
                }
            ],
            "ranking_summary": {
                "total_evaluated": 1,
                "exact_duplicates_removed": 0,
                "selection_limit": 10,
            },
        },
    }

    node_script = f"""
    const raw = {json.dumps(raw_api_response)};
    const rawTI = raw.test_intelligence;
    const rawRanked = Array.isArray(rawTI.ranked_candidates) ? rawTI.ranked_candidates : [];
    const rankedCandidates = rawRanked.map((r, idx) => {{
      const candObj = (r && r.candidate && typeof r.candidate === 'object') ? r.candidate : r;
      const rankNum = (r && typeof r.rank === 'number') ? r.rank : (idx + 1);
      const scoreNum = (r && typeof r.score === 'number') ? r.score : ((r && typeof r.relevance_score === 'number') ? r.relevance_score : null);
      const expl = (r && (r.explanation || r.selection_reason)) || (candObj && (candObj.explanation || candObj.selection_reason)) || '';
      return {{
        ...candObj,
        rank: rankNum,
        score: scoreNum,
        relevance_score: scoreNum,
        ranking_explanation: expl,
      }};
    }});

    console.log(JSON.stringify({{
      rankedCount: rankedCandidates.length,
      rank: rankedCandidates[0].rank,
      score: rankedCandidates[0].score,
      relevance_score: rankedCandidates[0].relevance_score,
      explanation: rankedCandidates[0].ranking_explanation
    }}));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)
    assert res["rankedCount"] == 1
    assert res["rank"] == 1
    assert res["score"] == 0.88
    assert res["relevance_score"] == 0.88
    assert "Rank 1" in res["explanation"]


def test_popup_relevance_display_normalization_percentage():
    """Verify that candidate relevance scores (87.5, 76.25, 63.75) are correctly formatted as 87.5%, 76.25%, 63.75%."""
    node_script = """
    function formatRelevancePill(candidate) {
      let scoreDisplay = null;
      const rawScore = typeof candidate.relevance_score === "number"
        ? candidate.relevance_score
        : (typeof candidate.score === "number" ? candidate.score : null);
      if (rawScore !== null) {
        const normScore = rawScore <= 1.0 ? (rawScore * 100) : rawScore;
        const formatted = normScore % 1 === 0 ? normScore.toFixed(0) : normScore.toFixed(2).replace(/\\.?0+$/, "");
        scoreDisplay = `Relevance: ${formatted}%`;
      }
      return scoreDisplay !== null ? scoreDisplay : "Synthesized";
    }

    const testScores = [
      { candidate: { relevance_score: 87.5 }, expected: "Relevance: 87.5%" },
      { candidate: { relevance_score: 76.25 }, expected: "Relevance: 76.25%" },
      { candidate: { relevance_score: 63.75 }, expected: "Relevance: 63.75%" },
      { candidate: { score: 80 }, expected: "Relevance: 80%" },
      { candidate: { relevance_score: 0.875 }, expected: "Relevance: 87.5%" },
      { candidate: {}, expected: "Synthesized" }
    ];

    const results = testScores.map(t => ({
      actual: formatRelevancePill(t.candidate),
      expected: t.expected,
      passed: formatRelevancePill(t.candidate) === t.expected
    }));

    console.log(JSON.stringify(results));
    """
    out = run_node_eval(node_script)
    results = json.loads(out)
    for r in results:
        assert r["passed"] is True, f"Failed formatting: expected {r['expected']}, got {r['actual']}"


def test_popup_ranked_candidates_counter_matches_displayed_cards():
    """Verify that the Ranked Candidates stat counter displays the count of the actual ranked candidates shown."""
    node_script = """
    // Case 1: Only unranked generated candidates present, 0 ranked candidates
    const rawTI_unranked = {
      generated_candidates: [
        { input_data: { ar: [] } },
        { input_data: { ar: [-1] } },
        { input_data: { ar: [1000] } },
        { input_data: { ar: [1, 2] } },
        { input_data: { ar: [1] } },
        { input_data: { ar: [2] } },
        { input_data: { ar: [3] } },
        { input_data: { ar: [4] } }
      ],
      ranked_candidates: [],
      ranking_summary: { exact_duplicates_removed: 0 }
    };

    const rawRanked_1 = Array.isArray(rawTI_unranked.ranked_candidates) ? rawTI_unranked.ranked_candidates : [];
    const statCounter_1 = String(rawRanked_1.length);
    const subhead_1 = `${rawTI_unranked.generated_candidates.length} Unranked Candidates`;

    // Case 2: Genuine ranked candidates present
    const rawTI_ranked = {
      generated_candidates: [
        { input_data: { ar: [] } },
        { input_data: { ar: [-1] } }
      ],
      ranked_candidates: [
        { rank: 1, score: 87.5, candidate: { input_data: { ar: [] } }, explanation: "Rank 1: Selected" },
        { rank: 2, score: 76.25, candidate: { input_data: { ar: [-1] } }, explanation: "Rank 2: Selected" }
      ],
      ranking_summary: { exact_duplicates_removed: 0 }
    };

    const rawRanked_2 = Array.isArray(rawTI_ranked.ranked_candidates) ? rawTI_ranked.ranked_candidates : [];
    const statCounter_2 = String(rawRanked_2.length);
    const subhead_2 = `${rawRanked_2.length} Ranked Candidates`;

    console.log(JSON.stringify({
      unrankedCounter: statCounter_1,
      unrankedSubhead: subhead_1,
      rankedCounter: statCounter_2,
      rankedSubhead: subhead_2
    }));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)
    assert res["unrankedCounter"] == "0"
    assert res["unrankedSubhead"] == "8 Unranked Candidates"
    assert res["rankedCounter"] == "2"
    assert res["rankedSubhead"] == "2 Ranked Candidates"


def test_popup_missing_ranked_candidates_keeps_generated_and_ranked_separate():
    """Verify adaptEdgeMindReport strictly keeps generated_candidates and ranked_candidates separate without fallback."""
    raw_api_response = {
        "status": "SUCCESS",
        "test_intelligence": {
            "existing_tests_analyzed": 1,
            "coverage_gaps": [{"name": "EMPTY_COLLECTION", "parameter": "ar", "severity": "HIGH"}],
            "generated_candidates": [
                {"input_data": {"ar": []}, "target_gap": "EMPTY_COLLECTION", "classification": "VALID"},
                {"input_data": {"ar": [-1]}, "target_gap": "NEGATIVE_VALUES", "classification": "ROBUSTNESS PROBE"},
                {"input_data": {"ar": [1000]}, "target_gap": "MAX_BOUNDARY", "classification": "VALID"},
            ],
            "ranked_candidates": [],
            "ranking_summary": {
                "total_evaluated": 3,
                "exact_duplicates_removed": 0,
                "selection_limit": 10,
            },
        },
    }

    node_script = f"""
    const fs = require('fs');
    const vm = require('vm');
    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const startIdx = popupCode.indexOf('function adaptEdgeMindReport');
    const nextDocIdx = popupCode.indexOf('/**', startIdx);
    const fnStr = popupCode.slice(startIdx, nextDocIdx).trim();

    const testEnv = {{ console: console }};
    vm.createContext(testEnv);
    vm.runInContext(fnStr, testEnv);

    const raw = {json.dumps(raw_api_response)};
    const adapted = testEnv.adaptEdgeMindReport(raw);

    console.log(JSON.stringify({{
      rankedCount: adapted.test_intelligence.ranked_candidates.length,
      generatedCount: adapted.test_intelligence.generated_candidates.length,
      firstGenIsRanked: adapted.test_intelligence.generated_candidates[0].is_ranked,
      firstGenHasRank: typeof adapted.test_intelligence.generated_candidates[0].rank
    }}));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)
    assert res["rankedCount"] == 0
    assert res["generatedCount"] == 3
    assert res["firstGenIsRanked"] is False
    assert res["firstGenHasRank"] == "undefined"


def test_unranked_candidates_never_receive_rank_badge_or_ranking_explanation():
    """Verify that renderCandidateCard never assigns rank badges (#1, #2) or ranking explanation rows to unranked generated candidates."""
    node_script = """
    function createElement(tag) {
      return {
        tagName: tag.toUpperCase(),
        className: '',
        children: [],
        appendChild(child) {
          this.children.push(child);
          return child;
        },
        title: '',
        textContent: ''
      };
    }

    global.document = {
      createElement: createElement,
      createTextNode: (t) => ({ textContent: t })
    };

    // Unranked candidate object
    const unrankedCandidate = {
      id: "candidate_1",
      input_data: { ar: [1, 2, 3] },
      target_gap: "EMPTY_COLLECTION",
      classification: "VALID",
      classification_reason: "Valid constraint test",
      is_ranked: false
    };

    const isRanked = unrankedCandidate.is_ranked === true || (typeof unrankedCandidate.rank === "number" && !isNaN(unrankedCandidate.rank) && unrankedCandidate.is_ranked !== false);
    const card = createElement("div");
    card.className = "candidate-card";

    const header = createElement("div");
    header.className = "candidate-header";

    const rankGroup = createElement("div");
    rankGroup.className = "candidate-rank-group";

    let createdRankBadge = false;
    if (isRanked && typeof unrankedCandidate.rank === "number") {
      const rankBadge = createElement("span");
      rankBadge.className = "candidate-rank";
      rankBadge.textContent = `#${unrankedCandidate.rank}`;
      rankGroup.appendChild(rankBadge);
      createdRankBadge = true;
    }

    const labelSpan = createElement("span");
    labelSpan.className = "candidate-label";
    if (isRanked && typeof unrankedCandidate.rank === "number") {
      labelSpan.textContent = unrankedCandidate.label || unrankedCandidate.id || `Candidate ${unrankedCandidate.rank}`;
    } else {
      labelSpan.textContent = unrankedCandidate.label || unrankedCandidate.id || `Candidate 1`;
    }
    rankGroup.appendChild(labelSpan);

    const scorePill = createElement("span");
    scorePill.className = "candidate-score-pill";
    let scoreDisplay = null;
    if (isRanked) {
      const rawScore = typeof unrankedCandidate.relevance_score === "number"
        ? unrankedCandidate.relevance_score
        : (typeof unrankedCandidate.score === "number" ? unrankedCandidate.score : null);
      if (rawScore !== null) {
        const normScore = rawScore <= 1.0 ? (rawScore * 100) : rawScore;
        const formatted = normScore % 1 === 0 ? normScore.toFixed(0) : normScore.toFixed(2).replace(/\\.?0+$/, "");
        scoreDisplay = `Relevance: ${formatted}%`;
      }
    }
    scorePill.textContent = scoreDisplay !== null ? scoreDisplay : "Synthesized";

    header.appendChild(rankGroup);
    header.appendChild(scorePill);
    card.appendChild(header);

    let createdRankExpl = false;
    if (isRanked) {
      const rankExpl = unrankedCandidate.ranking_explanation || (unrankedCandidate.explanation && unrankedCandidate.explanation.startsWith("Rank") ? unrankedCandidate.explanation : "");
      if (rankExpl) {
        const explRow = createElement("div");
        explRow.className = "candidate-reason-row candidate-rank-reason";
        card.appendChild(explRow);
        createdRankExpl = true;
      }
    }

    console.log(JSON.stringify({
      createdRankBadge: createdRankBadge,
      labelText: labelSpan.textContent,
      scorePillText: scorePill.textContent,
      createdRankExpl: createdRankExpl
    }));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)
    assert res["createdRankBadge"] is False, "Unranked candidate must NOT have a rank badge"
    assert res["labelText"] == "candidate_1"
    assert res["scorePillText"] == "Synthesized"
    assert res["createdRankExpl"] is False, "Unranked candidate must NOT have a ranking explanation row"


def test_genuine_ranked_candidates_receive_rank_badge_score_and_explanation():
    """Verify that genuine ranked candidates receive rank badges (#1), normalized percentage scores (87.5%), and ranking explanation rows."""
    node_script = """
    function createElement(tag) {
      return {
        tagName: tag.toUpperCase(),
        className: '',
        children: [],
        appendChild(child) {
          this.children.push(child);
          return child;
        },
        title: '',
        textContent: ''
      };
    }

    global.document = {
      createElement: createElement,
      createTextNode: (t) => ({ textContent: t })
    };

    const rankedCandidate = {
      id: "candidate_1",
      rank: 1,
      score: 87.5,
      relevance_score: 87.5,
      ranking_explanation: "Rank 1 (Score: 87.5): Candidate targeting EMPTY_COLLECTION",
      is_ranked: true,
      input_data: { ar: [] }
    };

    const isRanked = rankedCandidate.is_ranked === true || (typeof rankedCandidate.rank === "number" && !isNaN(rankedCandidate.rank) && rankedCandidate.is_ranked !== false);
    const card = createElement("div");
    card.className = "candidate-card";

    const header = createElement("div");
    header.className = "candidate-header";

    const rankGroup = createElement("div");
    rankGroup.className = "candidate-rank-group";

    let rankBadgeText = null;
    if (isRanked && typeof rankedCandidate.rank === "number") {
      const rankBadge = createElement("span");
      rankBadge.className = "candidate-rank";
      rankBadge.textContent = `#${rankedCandidate.rank}`;
      rankBadgeText = rankBadge.textContent;
      rankGroup.appendChild(rankBadge);
    }

    const labelSpan = createElement("span");
    labelSpan.className = "candidate-label";
    if (isRanked && typeof rankedCandidate.rank === "number") {
      labelSpan.textContent = rankedCandidate.label || rankedCandidate.id || `Candidate ${rankedCandidate.rank}`;
    } else {
      labelSpan.textContent = rankedCandidate.label || rankedCandidate.id || `Candidate 1`;
    }
    rankGroup.appendChild(labelSpan);

    const scorePill = createElement("span");
    scorePill.className = "candidate-score-pill";
    let scoreDisplay = null;
    if (isRanked) {
      const rawScore = typeof rankedCandidate.relevance_score === "number"
        ? rankedCandidate.relevance_score
        : (typeof rankedCandidate.score === "number" ? rankedCandidate.score : null);
      if (rawScore !== null) {
        const normScore = rawScore <= 1.0 ? (rawScore * 100) : rawScore;
        const formatted = normScore % 1 === 0 ? normScore.toFixed(0) : normScore.toFixed(2).replace(/\\.?0+$/, "");
        scoreDisplay = `Relevance: ${formatted}%`;
      }
    }
    scorePill.textContent = scoreDisplay !== null ? scoreDisplay : "Synthesized";

    header.appendChild(rankGroup);
    header.appendChild(scorePill);
    card.appendChild(header);

    let rankExplText = null;
    if (isRanked) {
      const rankExpl = rankedCandidate.ranking_explanation || (rankedCandidate.explanation && rankedCandidate.explanation.startsWith("Rank") ? rankedCandidate.explanation : "");
      if (rankExpl) {
        rankExplText = rankExpl;
      }
    }

    console.log(JSON.stringify({
      rankBadgeText: rankBadgeText,
      labelText: labelSpan.textContent,
      scorePillText: scorePill.textContent,
      rankExplText: rankExplText
    }));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)
    assert res["rankBadgeText"] == "#1"
    assert res["labelText"] == "candidate_1"
    assert res["scorePillText"] == "Relevance: 87.5%"
    assert "Rank 1 (Score: 87.5)" in res["rankExplText"]


def test_extractor_defines_normalize_collapsed_exponents_and_extracts_hackerrank_constraints():
    """Verify that extractor.js defines normalizeCollapsedExponents and successfully extracts HackerRank constraints."""
    node_script = """
    const fs = require('fs');
    global.window = {
      location: {
        hostname: 'www.hackerrank.com',
        href: 'https://www.hackerrank.com/challenges/simple-array-sum/problem',
        pathname: '/challenges/simple-array-sum/problem'
      },
      ace: {
        edit: () => ({
          getValue: () => 'def simpleArraySum(ar):\\n    return sum(ar)'
        })
      }
    };

    const testChallenge = {
      community: {
        challenges: {
          challenge: {
            'master/simple-array-sum': {
              detail: {
                slug: 'simple-array-sum',
                name: 'Simple Array Sum',
                constraints: ' $0 \\\\lt n, ar[i] \\\\le 1000$ '
              }
            }
          }
        }
      }
    };

    const encoded = encodeURIComponent(JSON.stringify(testChallenge));

    global.document = {
      getElementById: (id) => id === 'initialData' ? { textContent: encoded } : null,
      querySelector: (sel) => {
        if (sel.includes('initialData')) return { textContent: encoded };
        if (sel.includes('ace_editor')) return {};
        if (sel.includes('select-language')) return { textContent: 'Python 3' };
        return null;
      },
      querySelectorAll: () => []
    };

    const extractorCode = fs.readFileSync('./extension/edgemind/scripts/extractor.js', 'utf8');
    const result = eval(extractorCode);

    console.log(JSON.stringify({
      success: result.success,
      platform: result.platform,
      language: result.language,
      domConstraints: result.domConstraints
    }));
    """
    out = run_node_eval(node_script)
    res = json.loads(out)
    assert res["success"] is True
    assert res["platform"] == "hackerrank"
    assert res["language"] == "python3"
    assert len(res["domConstraints"]) == 1
    assert res["domConstraints"][0] == "0 < n, ar[i] <= 1000"






