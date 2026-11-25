import { describe, it, expect, vi, afterEach } from 'vitest';
import { apiClient } from '../api/client';
import { AnalysisReport } from '../types/api';
import {
  computeTestingPriority,
  detectStaticTestingGaps,
  mapTestsToSources,
  parseBaselineTestInputs,
  parseSuppliedFile,
  SAMPLE_TEST_INTELLIGENCE_SUITE,
} from '../utils/testIntelligenceHelpers';

describe('testIntelligenceHelpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('parses pytest and unittest files, extracts test functions/classes, and flags unsupported frameworks', () => {
    const pytestFile = parseSuppliedFile({
      id: 't1',
      filename: 'test_array_solver.py',
      content: SAMPLE_TEST_INTELLIGENCE_SUITE.testCode,
    });
    expect(pytestFile.isSupported).toBe(true);
    expect(pytestFile.role).toBe('test');
    expect(pytestFile.framework).toBe('pytest');
    expect(pytestFile.testCases).toHaveLength(2);
    expect(pytestFile.testCases[0].name).toBe('test_find_pair_basic');
    expect(pytestFile.imports).toContain('array_solver');

    const unittestFile = parseSuppliedFile({
      id: 't2',
      filename: 'test_legacy.py',
      content: `import unittest\nclass TestMath(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(1 + 1, 2)\n`,
    });
    expect(unittestFile.isSupported).toBe(true);
    expect(unittestFile.framework).toBe('unittest');
    expect(unittestFile.testCases[0].className).toBe('TestMath');
    expect(unittestFile.testCases[0].name).toBe('test_add');

    const vitestUnsupported = parseSuppliedFile({
      id: 't3',
      filename: 'App.test.tsx',
      content: `import { it, expect } from 'vitest';\nit('works', () => expect(true).toBe(true));`,
    });
    expect(vitestUnsupported.isSupported).toBe(false);
    expect(vitestUnsupported.framework).toBe('unsupported');
    expect(vitestUnsupported.testCases).toHaveLength(0);
  });

  it('maps supplied tests to source modules with confidence evidence and flags unmapped suites', () => {
    const src = parseSuppliedFile(
      {
        id: 's1',
        filename: SAMPLE_TEST_INTELLIGENCE_SUITE.sourceFilename,
        content: SAMPLE_TEST_INTELLIGENCE_SUITE.sourceCode,
      },
      'source'
    );
    const testPy = parseSuppliedFile({
      id: 't1',
      filename: SAMPLE_TEST_INTELLIGENCE_SUITE.testFilename,
      content: SAMPLE_TEST_INTELLIGENCE_SUITE.testCode,
    });
    const orphanTest = parseSuppliedFile({
      id: 't-orphan',
      filename: 'test_unrelated.py',
      content: `import pytest\ndef test_other():\n    assert something_else() == 1\n`,
    });

    const rels = mapTestsToSources([testPy, orphanTest], [src], 'array_solver.py');
    expect(rels).toHaveLength(2);
    expect(rels[0].confidence).toBe('high');
    expect(rels[0].isWorkspaceTarget).toBe(true);
    expect(rels[0].matchedSymbols).toContain('find_pair_indices');
    expect(rels[1].confidence).toBe('unmapped');
  });

  it('detects deterministic function gaps when tests are supplied and stays silent when none supplied', () => {
    const src = parseSuppliedFile(
      {
        id: 's1',
        filename: SAMPLE_TEST_INTELLIGENCE_SUITE.sourceFilename,
        content: SAMPLE_TEST_INTELLIGENCE_SUITE.sourceCode,
      },
      'source'
    );

    expect(detectStaticTestingGaps([src], [], [])).toEqual([]);

    const testPy = parseSuppliedFile({
      id: 't1',
      filename: SAMPLE_TEST_INTELLIGENCE_SUITE.testFilename,
      content: SAMPLE_TEST_INTELLIGENCE_SUITE.testCode,
    });
    const rels = mapTestsToSources([testPy], [src], 'array_solver.py');
    const gaps = detectStaticTestingGaps([src], [testPy], rels);

    expect(gaps.some((g) => g.name === 'validate_non_empty_bounds()')).toBe(true);
    expect(gaps.every((g) => g.caveat.length > 0)).toBe(true);
  });

  it('computes transparent testing priority from findings, branching complexity, and static test refs', () => {
    const src = parseSuppliedFile(
      {
        id: 's1',
        filename: SAMPLE_TEST_INTELLIGENCE_SUITE.sourceFilename,
        content: SAMPLE_TEST_INTELLIGENCE_SUITE.sourceCode,
      },
      'source'
    );
    const testPy = parseSuppliedFile({
      id: 't1',
      filename: SAMPLE_TEST_INTELLIGENCE_SUITE.testFilename,
      content: SAMPLE_TEST_INTELLIGENCE_SUITE.testCode,
    });
    const rels = mapTestsToSources([testPy], [src], 'array_solver.py');

    const mockReport: AnalysisReport = {
      file_path: 'array_solver.py',
      file: 'array_solver.py',
      overall_status: 'FAIL',
      status: 'FAIL',
      score: 70,
      total_errors: 1,
      total_warnings: 0,
      syntax_status: 'PASS',
      runtime_status: 'SKIPPED',
      logic_status: 'FAIL',
      quality_status: 'PASS',
      complexity_status: 'PASS',
      errors: [
        {
          type: 'LogicIssue',
          line: 12,
          line_number: 12,
          message: 'Early return check on zero.',
          why: '',
          explanation: '',
          fix: '',
          suggested_fix: '',
          concept: 'LOGIC',
        },
      ],
      warnings: [],
      summary: { syntax: 'PASS', runtime: 'SKIPPED', logic: 'FAIL', quality: 'PASS', complexity: 'PASS' },
    };

    const priority = computeTestingPriority(
      [src],
      [testPy],
      rels,
      'array_solver.py',
      mockReport,
      null
    );

    expect(priority).toHaveLength(2);
    expect(priority[0].targetName).toBe('validate_non_empty_bounds()');
    expect(priority[0].tier).toBe('High');
    expect(priority[0].errorCount).toBe(1);
    expect(priority[0].hasStaticTestReference).toBe(false);
    expect(priority[0].priorityScore).toBeGreaterThan(priority[1].priorityScore);
  });

  it('parses baseline test JSON arrays cleanly and dispatches /api/v1/edgemind/analyze', async () => {
    const valid = parseBaselineTestInputs('[{"nums": [1, 2], "target": 3}]');
    expect(valid.error).toBeNull();
    expect(valid.testCases).toEqual([{ nums: [1, 2], target: 3 }]);

    const bad = parseBaselineTestInputs('[{"broken": ]');
    expect(bad.error).not.toBeNull();

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: (h: string) => (h === 'content-type' ? 'application/json' : null) },
      json: async () => ({ status: 'SUCCESS', analysis_mode: 'BASELINE_DRIVEN' }),
    });

    await apiClient.analyzeEdgeMind({
      code: 'def solve(x: int) -> int:\n    return x\n',
      filename: 'solve.py',
      test_cases: [{ x: 1 }],
    });

    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/v1/edgemind/analyze',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"static_only":true'),
      })
    );
  });
});
