import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { TestIntelligencePage } from '../pages/TestIntelligencePage';
import { WorkspacePage } from '../pages/WorkspacePage';
import { FindingsPage } from '../pages/FindingsPage';
import { HealthProvider } from '../context/HealthContext';
import { AnalysisProvider } from '../context/AnalysisContext';
import { apiClient } from '../api/client';
import { EdgeMindAnalyzeResponse } from '../types/api';

const MOCK_EDGEMIND_RESPONSE: EdgeMindAnalyzeResponse = {
  status: 'SUCCESS',
  product: 'EdgeMind',
  version: '1.0.0',
  analysis_mode: 'BASELINE_DRIVEN',
  baseline_available: true,
  context_completeness: 'COMPLETE',
  identified_parameters: [
    { name: 'nums', param_type: 'int', structure: 'array_1d', source: 'AST_SIGNATURE' },
    { name: 'target', param_type: 'int', structure: 'scalar', source: 'AST_SIGNATURE' },
  ],
  parsed_constraints: {
    status: 'PARSED',
    total_raw: 2,
    unresolved: [],
  },
  generation_status: 'SUCCESS',
  code_analysis: {
    file_path: 'array_solver.py',
    file: 'array_solver.py',
    overall_status: 'PASS WITH WARNINGS',
    status: 'PASS WITH WARNINGS',
    score: 90,
    total_errors: 0,
    total_warnings: 1,
    syntax_status: 'PASS',
    runtime_status: 'SKIPPED',
    logic_status: 'PASS',
    quality_status: 'WARNING',
    complexity_status: 'PASS',
    errors: [],
    warnings: [
      {
        type: 'UnusedVariable',
        line: 12,
        line_number: 12,
        message: 'Check branch edge conditions.',
        why: 'Edge check improves readability.',
        explanation: 'Edge check improves readability.',
        fix: 'Simplify conditional branch.',
        suggested_fix: 'Simplify conditional branch.',
        concept: 'CODE QUALITY',
      },
    ],
    summary: {
      syntax: 'PASS',
      runtime: 'SKIPPED',
      logic: 'PASS',
      quality: 'WARNING',
      complexity: 'PASS',
    },
  },
  test_intelligence: {
    existing_tests_analyzed: 1,
    detected_patterns: {},
    coverage_gaps: [
      {
        category: 'NEGATIVE_VALUES',
        param_name: 'nums',
        severity: 'MEDIUM',
        constraint_validity: 'VALID',
        relevance_score: 0.85,
        rationale: 'Baseline input contains only positive numbers.',
        risk_explained: 'Negative complements may mishandle offset signs.',
        suggested_action: 'Test negative elements within constraints.',
      },
    ],
    total_gaps: 1,
    unresolved_constraints: [],
    ranking_summary: {
      total_evaluated: 3,
      exact_duplicates_removed: 1,
      redundant_candidates_penalized: 0,
      selection_limit: 10,
    },
    generated_candidates: [],
    ranked_candidates: [
      {
        rank: 1,
        score: 68.5,
        explanation: 'Medium Gap (+20.0); Relevance (+21.3)',
        score_breakdown: {
          severity_score: 20,
          relevance_score: 21.3,
          boundary_score: 15,
          failure_family_score: 0,
          performance_score: 0,
          novelty_score: 12.2,
          diversity_penalty: 0,
          total_score: 68.5,
          explanation: 'Medium Gap (+20.0)',
        },
        candidate: {
          id: 'gen-neg-nums',
          source: 'GENERATED_TEST',
          input_data: { nums: [-3, -4, 3, 90], target: 0 },
          expected_output: null,
          is_expected_output_verified: false,
          label: 'Negative Elements Probe',
          rationale: 'Exercises negative numbers allowed by constraint bounds.',
          target_gap: 'NEGATIVE_VALUES',
          relevance_score: 0.85,
          is_boundary: true,
          is_performance: false,
          classification: 'VALID',
        },
      },
    ],
  },
  provenance: {
    source: 'GENERATED_TEST',
    execution_performed: false,
    expected_outputs_known: false,
    guarantees: ['Zero execution performed.'],
  },
  limitations: ['Expected outputs are null (None).'],
  warnings: [],
};

function renderApp(initialRoute: string = '/test-intelligence') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <HealthProvider pollingIntervalMs={60000}>
        <AnalysisProvider>
          <Routes>
            <Route path="/workspace" element={<WorkspacePage />} />
            <Route path="/findings" element={<FindingsPage />} />
            <Route path="/test-intelligence" element={<TestIntelligencePage />} />
          </Routes>
        </AnalysisProvider>
      </HealthProvider>
    </MemoryRouter>
  );
}

describe('TestIntelligencePage Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders empty state cleanly without fabricating zeroes for missing execution/coverage metrics', async () => {
    renderApp('/test-intelligence');

    expect(
      await screen.findByRole('heading', { level: 2, name: 'Adaptive Test Intelligence' })
    ).toBeDefined();

    const summary = screen.getByLabelText('Test intelligence availability summary');
    expect(within(summary).getByText('None Loaded')).toBeDefined();
    expect(within(summary).getByText('None Supplied')).toBeDefined();
    expect(within(summary).getByText('Unavailable')).toBeDefined();
    expect(within(summary).getByText('Not Measured')).toBeDefined();
    expect(screen.getByText('No Test Files Discovered or Loaded')).toBeDefined();
    expect(screen.getByText('Not Supported (Static-Only API)')).toBeDefined();
  });

  it('displays backend disconnected banner and disables Run Adaptive Analysis when offline', async () => {
    vi.spyOn(apiClient, 'getHealth').mockRejectedValue({
      error: 'NetworkError',
      detail: 'Connection refused',
      status_code: 0,
      request_id: null,
    });

    renderApp('/test-intelligence');

    expect(await screen.findByText('Backend Offline')).toBeDefined();
    expect(screen.getByText('Backend Disconnected')).toBeDefined();

    const runBtn = screen.getByRole('button', { name: /run adaptive analysis/i }) as HTMLButtonElement;
    expect(runBtn.disabled).toBe(true);
  });

  it('shows unsupported workspace language alert when Workspace is switched to JavaScript', async () => {
    renderApp('/workspace');

    const langSelect = await screen.findByLabelText('Analysis Language');
    fireEvent.change(langSelect, { target: { value: 'javascript' } });
    // Navigate via UI or test separate direct load after pasting unsupported test file
    expect(screen.getByText('Unsupported Language')).toBeDefined();
  });

  it('handles pasting an unsupported TypeScript test file without fabricating Python test counts', async () => {
    renderApp('/test-intelligence');

    fireEvent.click(await screen.findByRole('button', { name: /paste test file/i }));
    fireEvent.change(screen.getByLabelText('Pasted file name'), {
      target: { value: 'widget.test.tsx' },
    });
    fireEvent.change(screen.getByLabelText('Pasted Python test source'), {
      target: { value: "import { it, expect } from 'vitest';\nit('ok', () => expect(1).toBe(1));" },
    });
    fireEvent.click(screen.getByRole('button', { name: /add file to explorer/i }));

    expect(await screen.findByText('widget.test.tsx')).toBeDefined();
    expect(screen.getByText('Unsupported test framework/extension')).toBeDefined();

    // Summary must still not treat unsupported files as parsed Python test files
    const summary = screen.getByLabelText('Test intelligence availability summary');
    expect(within(summary).getByText('None Loaded')).toBeDefined();
    expect(within(summary).getByText('None Supplied')).toBeDefined();
  });

  it('discovers sample tests, filters explorer, maps relationships, detects static gaps, runs backend EdgeMind analysis, and navigates to Workspace & Findings', async () => {
    const analyzeSpy = vi
      .spyOn(apiClient, 'analyzeEdgeMind')
      .mockResolvedValue(MOCK_EDGEMIND_RESPONSE);

    renderApp('/test-intelligence');

    // Load deterministic sample suite
    fireEvent.click(await screen.findByRole('button', { name: /load sample suite/i }));

    expect((await screen.findAllByText('test_array_solver.py')).length).toBeGreaterThan(0);
    expect(screen.getByText('2 test(s)')).toBeDefined();
    expect(screen.getByText('HIGH CONFIDENCE (INFERRED)')).toBeDefined();
    expect(screen.getAllByText(/validate_non_empty_bounds\(\)/).length).toBeGreaterThan(0);

    // Expand test file item to inspect discovered test functions
    fireEvent.click(screen.getByLabelText('Expand test_array_solver.py'));
    expect(screen.getByText('test_find_pair_basic()')).toBeDefined();
    expect(screen.getByText('test_find_pair_single_match()')).toBeDefined();

    // Filter explorer cleanly
    fireEvent.change(screen.getByLabelText('Search test files or test functions'), {
      target: { value: 'does_not_exist_xyz' },
    });
    expect(screen.getByText('No supplied files match your current filter.')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /reset test filter/i }));
    expect(screen.getAllByText('test_array_solver.py').length).toBeGreaterThan(0);

    // Run real backend /api/v1/edgemind/analyze contract
    fireEvent.click(screen.getByRole('button', { name: /run adaptive analysis/i }));

    await waitFor(() => {
      expect(analyzeSpy).toHaveBeenCalledTimes(1);
    });
    expect((await screen.findAllByText('NEGATIVE_VALUES')).length).toBeGreaterThan(0);
    expect(screen.getByText('Expected Output: null (Unverified; static-only mode)')).toBeDefined();

    // Reveal Capability Matrix explicitly
    fireEvent.click(screen.getByRole('button', { name: /view capability matrix/i }));
    expect(screen.getByText('Automatic Server Repository Test Scanning')).toBeDefined();

    // Navigate from Testing Priority to Findings Explorer (populated from code_analysis)
    fireEvent.click(screen.getByRole('button', { name: /inspect findings/i }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Findings Explorer' })).toBeDefined();
    expect(screen.getAllByText('Check branch edge conditions.').length).toBeGreaterThan(0);

    // Jump to Workspace from Findings cleanly preserving code
    fireEvent.click(screen.getByRole('button', { name: /inspect in workspace/i }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Code Workspace' })).toBeDefined();
    expect(screen.getByText('Focused Line 12')).toBeDefined();
  });

  it('handles EdgeMind API failures gracefully and supports retry', async () => {
    vi.spyOn(apiClient, 'analyzeEdgeMind')
      .mockRejectedValueOnce({
        error: 'Internal Server Error',
        detail: 'Adaptive intelligence worker failed',
        status_code: 500,
        request_id: 'req-ti-500',
      })
      .mockResolvedValueOnce(MOCK_EDGEMIND_RESPONSE);

    renderApp('/test-intelligence');

    fireEvent.click(await screen.findByRole('button', { name: /load sample suite/i }));
    fireEvent.click(screen.getByRole('button', { name: /run adaptive analysis/i }));

    expect(await screen.findByText('Adaptive Test Intelligence Request Failed')).toBeDefined();
    expect(screen.getByText(/req-ti-500/)).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect((await screen.findAllByText('NEGATIVE_VALUES')).length).toBeGreaterThan(0);
  });
});
