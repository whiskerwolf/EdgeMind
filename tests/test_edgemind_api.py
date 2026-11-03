"""
Tests for EdgeMind Adaptive Code Analysis and Test Intelligence API.

Verifies:
- POST /api/v1/edgemind/analyze with full problem context and test cases.
- Convenience test case format (raw parameter dictionaries).
- Validation of missing, malformed, empty, or non-string inputs.
- Empty or incomplete problem context (preserves honesty, never invents constraints).
- Deterministic ranking and candidate generation.
- Strict provenance tracking (GENERATED_TEST, expected_output=None).
- Existing CodeDoctor endpoints remain completely unchanged and functional.
- Zero external network dependencies.
"""

import json
import pytest
from fastapi.testclient import TestClient

from core.api import app


@pytest.fixture
def client():
    return TestClient(app)


TWO_SUM_CODE = (
    "class Solution:\n"
    "    def twoSum(self, nums: list[int], target: int) -> list[int]:\n"
    "        seen = {}\n"
    "        for i, n in enumerate(nums):\n"
    "            comp = target - n\n"
    "            if comp in seen:\n"
    "                return [seen[comp], i]\n"
    "            seen[n] = i\n"
    "        return []\n"
)


FIND_MAX_CODE = (
    "def find_max(nums):\n"
    "    if not nums:\n"
    "        return None\n"
    "    best = nums[0]\n"
    "    for n in nums:\n"
    "        if n > best:\n"
    "            best = n\n"
    "    return best\n"
)


# =============================================================================
# 1. Successful Analysis with Full Context & Test Cases
# =============================================================================


def test_edgemind_valid_request_with_context_and_samples(client):
    """Verify complete EdgeMind pipeline execution with full problem context and sample tests."""
    payload = {
        "code": TWO_SUM_CODE,
        "filename": "two_sum.py",
        "problem_context": {
            "platform": "leetcode",
            "problem_id": "1",
            "title": "Two Sum",
            "function_name": "twoSum",
            "parameters": ["nums", "target"],
            "constraints": [
                "2 <= nums.length <= 10^4",
                "-10^9 <= nums[i] <= 10^9",
                "-10^9 <= target <= 10^9",
            ],
            "constraint_spec": {
                "min_length": 2,
                "max_length": 10000,
                "min_value": -1000000000,
                "max_value": 1000000000,
                "raw_constraints": ["2 <= nums.length <= 10^4"],
            },
        },
        "test_cases": [
            {
                "id": "sample-1",
                "source": "PUBLIC_SAMPLE",
                "input_data": {"nums": [2, 7, 11, 15], "target": 9},
            },
            {
                "id": "sample-2",
                "source": "PUBLIC_SAMPLE",
                "input_data": {"nums": [3, 2, 4], "target": 6},
            },
        ],
        "max_candidates": 8,
    }

    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Top-level structure
    assert data["status"] == "SUCCESS"
    assert data["product"] == "EdgeMind"
    assert data["version"] == "1.0.0"

    # Code analysis section
    assert "code_analysis" in data
    assert data["code_analysis"]["overall_status"] == "PASS"
    assert data["code_analysis"]["score"] == 100

    # Test intelligence section
    intel = data["test_intelligence"]
    assert intel["existing_tests_analyzed"] == 2
    assert "detected_patterns" in intel
    assert "coverage_gaps" in intel
    assert intel["total_gaps"] > 0

    # Candidates and ranking
    candidates = intel["generated_candidates"]
    assert len(candidates) > 0
    assert len(candidates) <= 8

    # Provenance verification on all generated candidates
    for cand in candidates:
        assert cand["source"] == "GENERATED_TEST"
        assert cand["expected_output"] is None
        assert cand["is_expected_output_verified"] is False
        assert "input_data" in cand
        assert "target_gap" in cand

    # Ranking summary
    ranking_summary = intel["ranking_summary"]
    assert ranking_summary["total_evaluated"] >= len(candidates)
    assert ranking_summary["selection_limit"] == 8

    # Provenance and disclaimers
    assert data["provenance"]["execution_performed"] is False
    assert data["provenance"]["expected_outputs_known"] is False
    assert len(data["limitations"]) > 0


def test_edgemind_convenience_test_case_format(client):
    """Verify endpoint accepts raw input dictionaries without explicit TestCase schema."""
    payload = {
        "code": FIND_MAX_CODE,
        "filename": "find_max.py",
        "test_cases": [
            {"nums": [1, 2, 3]},
            {"nums": [10, 20, 5]},
        ],
        "max_candidates": 5,
    }

    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "SUCCESS"
    intel = data["test_intelligence"]
    assert intel["existing_tests_analyzed"] == 2
    assert len(intel["generated_candidates"]) > 0
    assert len(intel["generated_candidates"]) <= 5

    # Check that provenance defaults to GENERATED_TEST for output candidates
    for cand in intel["generated_candidates"]:
        assert cand["source"] == "GENERATED_TEST"
        assert cand["expected_output"] is None


# =============================================================================
# 2. Input Validation & Error Handling
# =============================================================================


def test_edgemind_missing_code_rejected(client):
    """Verify requests lacking the 'code' parameter are rejected with HTTP 400."""
    response = client.post("/api/v1/edgemind/analyze", json={"filename": "solution.py"})
    assert response.status_code == 400
    err = response.json()
    assert err["error"] == "Bad Request"
    assert "code" in err["detail"].lower()


def test_edgemind_non_string_code_rejected(client):
    """Verify non-string code payloads are rejected with HTTP 400."""
    for invalid in [123, None, ["def foo(): pass"], {"code": "pass"}]:
        response = client.post("/api/v1/edgemind/analyze", json={"code": invalid})
        assert response.status_code == 400
        err = response.json()
        assert err["error"] == "Bad Request"
        assert "string" in err["detail"].lower()


def test_edgemind_empty_code_rejected(client):
    """Verify empty or whitespace-only code is rejected with HTTP 400."""
    for empty in ["", "   ", "\n\t  \n"]:
        response = client.post("/api/v1/edgemind/analyze", json={"code": empty})
        assert response.status_code == 400
        err = response.json()
        assert err["error"] == "Bad Request"
        assert "empty" in err["detail"].lower()


def test_edgemind_empty_body_rejected(client):
    """Verify empty HTTP body is rejected with HTTP 400."""
    response = client.post(
        "/api/v1/edgemind/analyze",
        content="",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    err = response.json()
    assert err["error"] == "Bad Request"


def test_edgemind_malformed_json_rejected(client):
    """Verify non-JSON payload returns HTTP 400."""
    response = client.post(
        "/api/v1/edgemind/analyze",
        content="{broken json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    err = response.json()
    assert err["error"] == "Bad Request"
    assert "malformed" in err["detail"].lower()


def test_edgemind_static_only_enforced(client):
    """Verify static_only=False is rejected with HTTP 400."""
    payload = {
        "code": FIND_MAX_CODE,
        "static_only": False,
    }
    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 400
    err = response.json()
    assert "static_only" in err["detail"].lower()


def test_edgemind_malformed_test_cases_rejected(client):
    """Verify non-list test_cases or non-dict items return HTTP 400."""
    # test_cases not a list
    response = client.post(
        "/api/v1/edgemind/analyze",
        json={"code": FIND_MAX_CODE, "test_cases": "not a list"},
    )
    assert response.status_code == 400

    # item inside test_cases not a dict
    response = client.post(
        "/api/v1/edgemind/analyze",
        json={"code": FIND_MAX_CODE, "test_cases": ["not a dict"]},
    )
    assert response.status_code == 400


# =============================================================================
# 3. Empty or Incomplete Problem Context
# =============================================================================


def test_edgemind_empty_test_cases_returns_insufficient_context(client):
    """Verify code without test cases returns INSUFFICIENT_CONTEXT with actionable guidance."""
    payload = {
        "code": FIND_MAX_CODE,
        "filename": "find_max.py",
        "test_cases": [],
    }
    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "INSUFFICIENT_CONTEXT"
    assert data["test_intelligence"]["existing_tests_analyzed"] == 0
    assert data["test_intelligence"]["generated_candidates"] == []
    assert len(data["warnings"]) > 0
    assert any("test input" in w.lower() for w in data["warnings"])

    # Code analysis is still performed
    assert "code_analysis" in data
    assert data["code_analysis"]["overall_status"] == "PASS"


def test_edgemind_no_explicit_constraints_does_not_invent_them(client):
    """Verify absence of constraint_spec does not fabricate constraint bounds."""
    payload = {
        "code": FIND_MAX_CODE,
        "filename": "find_max.py",
        "test_cases": [{"nums": [1, 2, 3]}],
        # problem_context omitted entirely
    }
    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "SUCCESS"
    assert any("constraint" in w.lower() for w in data["warnings"])

    # Verify no constraint boundary gaps were fabricated without constraint_spec
    gaps = data["test_intelligence"]["coverage_gaps"]
    for gap in gaps:
        # Without constraint_spec, bounds should not claim VALID against constraints
        if gap["category"] in ("UPPER_CONSTRAINT_BOUND", "LOWER_CONSTRAINT_BOUND"):
            assert gap["constraint_validity"] == "UNKNOWN"


# =============================================================================
# 4. Deterministic Output
# =============================================================================


def test_edgemind_deterministic_output(client):
    """Verify identical requests produce identical ranking, scores, and candidate signatures."""
    payload = {
        "code": FIND_MAX_CODE,
        "filename": "find_max.py",
        "problem_context": {
            "function_name": "find_max",
            "parameters": ["nums"],
            "constraint_spec": {
                "min_length": 0,
                "max_length": 100,
                "min_value": -100,
                "max_value": 100,
            },
        },
        "test_cases": [
            {"id": "t1", "source": "PUBLIC_SAMPLE", "input_data": {"nums": [1, 2, 3]}}
        ],
        "max_candidates": 5,
    }

    res1 = client.post("/api/v1/edgemind/analyze", json=payload).json()
    res2 = client.post("/api/v1/edgemind/analyze", json=payload).json()

    # Compare selected candidate signatures and ranks
    cands1 = res1["test_intelligence"]["generated_candidates"]
    cands2 = res2["test_intelligence"]["generated_candidates"]

    assert len(cands1) == len(cands2)
    for c1, c2 in zip(cands1, cands2):
        assert c1["id"] == c2["id"]
        assert c1["input_data"] == c2["input_data"]
        assert c1["target_gap"] == c2["target_gap"]


# =============================================================================
# 5. Preservation of Existing CodeDoctor Endpoints
# =============================================================================


def test_codedoctor_endpoints_remain_unchanged(client):
    """Verify existing GET /health and POST /api/v1/analyze remain 100% functional."""
    # Health check
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json() == {
        "status": "healthy",
        "service": "EdgeMind",
    }

    # CodeDoctor analyze endpoint
    payload = {
        "code": "def add(a, b):\n    return a + b\n",
        "filename": "solution.py",
    }
    res_analyze = client.post("/api/v1/analyze", json=payload)
    assert res_analyze.status_code == 200
    data = res_analyze.json()
    assert data["overall_status"] == "PASS"
    assert data["score"] == 100
    assert "detailed_errors" in data
    assert "detailed_warnings" in data
    assert "summary" in data


# =============================================================================
# 6. Live Audit Report API Integration Regression Tests
# =============================================================================


def test_edgemind_raw_constraints_parsed_and_candidates_classified(client):
    """Verify raw constraint expressions are parsed, candidates classified, and unresolved constraints tracked."""
    payload = {
        "code": TWO_SUM_CODE,
        "filename": "two_sum.py",
        "problem_context": {
            "platform": "leetcode",
            "problem_id": "1",
            "title": "Two Sum",
            "function_name": "twoSum",
            "parameters": ["nums", "target"],
            "constraints": [
                "2 <= nums.length <= 10^4",
                "-10^9 <= nums[i] <= 10^9",
                "-10^9 <= target <= 10^9",
                "Only one valid answer exists.",
            ],
            # Note: constraint_spec omitted intentionally! Must be parsed from constraints.
        },
        "test_cases": [
            {"nums": [2, 7, 11, 15], "target": 9},
            {"nums": [3, 2, 4], "target": 6},
        ],
        "max_candidates": 10,
    }

    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "SUCCESS"
    intel = data["test_intelligence"]

    # Unresolved constraints tracked
    assert "unresolved_constraints" in intel
    assert "Only one valid answer exists." in intel["unresolved_constraints"]

    candidates = intel["generated_candidates"]
    assert len(candidates) > 0

    # Verify classification present on all candidates
    for cand in candidates:
        assert "classification" in cand
        assert cand["classification"] in ("VALID", "ROBUSTNESS PROBE", "CONSTRAINT VALIDITY UNKNOWN")
        assert "classification_reason" in cand
        assert len(cand["classification_reason"]) > 0

    # Verify relational duplicate candidate exists for Two Sum: [3, 3] and target 6
    dup_candidates = [
        c for c in candidates
        if c.get("target_gap") == "DUPLICATE_ELEMENTS" and c["input_data"].get("nums") == [3, 3]
    ]
    assert len(dup_candidates) >= 1
    two_sum_dup = dup_candidates[0]
    assert two_sum_dup["input_data"]["target"] == 6
    assert two_sum_dup["classification"] == "VALID"


def test_edgemind_api_two_sum_exponential_bounds_and_semantic_invariants(client):
    """End-to-end API verification that 10^9 constraints reach synthesizer and valid candidates have exactly 1 pair."""
    from core.test_intelligence.constraint_parser import count_valid_pairs

    payload = {
        "code": TWO_SUM_CODE,
        "filename": "two_sum.py",
        "problem_context": {
            "platform": "leetcode",
            "problem_id": "1",
            "title": "Two Sum",
            "function_name": "twoSum",
            "parameters": ["nums", "target"],
            "constraints": [
                "2 <= nums.length <= 10^4",
                "-10^9 <= nums[i] <= 10^9",
                "-10^9 <= target <= 10^9",
            ],
        },
        "test_cases": [
            {"nums": [2, 7, 11, 15], "target": 9},
            {"nums": [3, 2, 4], "target": 6},
        ],
        "max_candidates": 10,
    }

    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    candidates = data["test_intelligence"]["generated_candidates"]
    assert len(candidates) > 0

    has_exponential_boundary = False
    has_max_scale = False

    for cand in candidates:
        nums = cand["input_data"].get("nums")
        target = cand["input_data"].get("target")

        # 1. Verify exponential bound values: must NOT be 109.0 or -109.0
        if isinstance(target, (int, float)):
            assert target not in (109.0, -109.0, 109, -109)
            if abs(target) >= 1000000000:
                has_exponential_boundary = True
        if isinstance(nums, list):
            for x in nums:
                if isinstance(x, (int, float)):
                    assert x not in (109.0, -109.0, 109, -109)
                    if abs(x) >= 1000000000:
                        has_exponential_boundary = True

            # 2. Check scale candidate
            if len(nums) == 10000:
                has_max_scale = True
                assert "10000 elements" in cand["label"]
                assert "Maximum constraint length (10000 elements)" in cand["label"]

        # 3. Two Sum semantic invariant for candidates classified VALID
        if cand["classification"] == "VALID" and isinstance(nums, list) and isinstance(target, (int, float)):
            pairs = count_valid_pairs(nums, target)
            assert pairs == 1, f"Candidate {cand['id']} labelled VALID but has {pairs} valid pairs: {cand['input_data']}"

        # 4. Strict provenance
        assert cand["source"] == "GENERATED_TEST"
        assert cand["expected_output"] is None
        assert cand["is_expected_output_verified"] is False

    assert has_exponential_boundary, "Synthesizer must receive and generate 10^9 / -10^9 boundary candidates without truncation"
    assert has_max_scale, "Synthesizer must generate 10000 element scale candidate when max constraint is 10^4"


def test_edgemind_analyze_collapsed_constraints_end_to_end(client):
    """Verify that when constraints have collapsed exponents (104, -109, 109), backend parses 10000 and 10^9."""
    payload = {
        "code": TWO_SUM_CODE,
        "filename": "two_sum.py",
        "problem_context": {
            "platform": "leetcode",
            "problem_id": "1",
            "title": "Two Sum",
            "function_name": "twoSum",
            "parameters": ["nums", "target"],
            "constraints": [
                "2 <= nums.length <= 104",
                "-109 <= nums[i] <= 109",
                "-109 <= target <= 109",
            ],
        },
        "test_cases": [
            {"nums": [2, 7, 11, 15], "target": 9},
        ],
        "max_candidates": 10,
    }

    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    candidates = data["test_intelligence"]["generated_candidates"]

    # Verify candidate with length 10000 exists
    scale_cands = [c for c in candidates if len(c["input_data"].get("nums", [])) == 10000]
    assert len(scale_cands) >= 1
    assert "10000 elements" in scale_cands[0]["label"]

    # Verify bounds with 10^9 / -10^9 exist
    bound_vals = []
    for c in candidates:
        nums = c["input_data"].get("nums", [])
        if isinstance(nums, list):
            bound_vals.extend(nums)
        t = c["input_data"].get("target")
        if isinstance(t, (int, float)):
            bound_vals.append(t)

    assert any(abs(v) >= 1000000000 for v in bound_vals)
    assert not any(v in (109, -109, 109.0, -109.0) for v in bound_vals if abs(v) > 100)



