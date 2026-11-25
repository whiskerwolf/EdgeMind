import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Link, Route, Routes } from 'react-router-dom';
import { HistoryPage } from '../pages/HistoryPage';
import { WorkspacePage } from '../pages/WorkspacePage';
import { FindingsPage } from '../pages/FindingsPage';
import { HealthProvider } from '../context/HealthContext';
import { AnalysisProvider } from '../context/AnalysisContext';
import { apiClient } from '../api/client';
import { AnalysisReport, PersistedReportDocument } from '../types/api';

const WORKSPACE_SAMPLE_CODE = `def divide(a, b):
    return a / b
`;

const SAMPLE_REPORT_ONE: AnalysisReport = {
  file_path: 'alpha.py',
  file: 'alpha.py',
  overall_status: 'FAIL',
  status: 'FAIL',
  score: 68,
  total_errors: 1,
  total_warnings: 1,
  syntax_status: 'PASS',
  runtime_status: 'SKIPPED',
  logic_status: 'FAIL',
  quality_status: 'WARNING',
  complexity_status: 'PASS',
  errors: [
    {
      type: 'ZeroDivisionError',
      line: 2,
      line_number: 2,
      message: 'Unchecked division by parameter b.',
      why: 'Denominator may be zero.',
      explanation: 'Denominator may be zero.',
      fix: 'Check if b == 0 before dividing.',
      suggested_fix: 'Check if b == 0 before dividing.',
      concept: 'SAFETY',
    },
  ],
  warnings: [
    {
      type: 'MissingDocstring',
      line: 1,
      line_number: 1,
      message: 'Function divide lacks docstring.',
      why: '',
      explanation: '',
      fix: '',
      suggested_fix: '',
      concept: 'STYLE',
    },
  ],
  summary: {
    syntax: 'PASS',
    runtime: 'SKIPPED',
    logic: 'FAIL',
    quality: 'WARNING',
    complexity: 'PASS',
  },
};

const SAMPLE_REPORT_TWO: AnalysisReport = {
  file_path: 'alpha.py',
  file: 'alpha.py',
  overall_status: 'PASS',
  status: 'PASS',
  score: 96,
  total_errors: 0,
  total_warnings: 0,
  syntax_status: 'PASS',
  runtime_status: 'SKIPPED',
  logic_status: 'PASS',
  quality_status: 'PASS',
  complexity_status: 'PASS',
  errors: [],
  warnings: [],
  summary: {
    syntax: 'PASS',
    runtime: 'SKIPPED',
    logic: 'PASS',
    quality: 'PASS',
    complexity: 'PASS',
  },
};

const DB_DOC_1: PersistedReportDocument = {
  id: 'doc-db-1',
  analysis_session_id: 'session-db-1',
  problem: { title: 'Two Sum Solver', slug: 'two-sum', platform: 'LeetCode' },
  problem_slug: 'two-sum',
  platform: 'LeetCode',
  language: 'python',
  analysis_mode: 'BASELINE_DRIVEN',
  analysis_status: 'SUCCESS',
  coverage_gaps: [
    {
      category: 'BOUNDARY_VALUE',
      param_name: 'nums',
      severity: 'HIGH',
      constraint_validity: 'VALID',
      relevance_score: 90,
      rationale: 'No empty array boundary test present.',
      risk_explained: 'Empty slice may raise ValueError or IndexError.',
      suggested_action: 'Add empty list boundary test.',
    },
  ],
  generated_candidates: [],
  explanations: { warnings: ['Static analysis only'] },
  analysis_metadata: {
    duration_ms: 42,
    gaps_detected: 1,
    candidates_generated: 3,
    score: 88,
    errors: [],
    warnings: [
      {
        type: 'BoundaryHint',
        line: 4,
        message: 'Handle empty array safely.',
        concept: 'EDGE_CASE',
      },
    ],
  },
  created_at: '2026-11-24T12:00:00.000Z',
};

const DB_DOC_2: PersistedReportDocument = {
  id: 'doc-db-2',
  analysis_session_id: 'session-db-2',
  problem: { title: 'Graph BFS', slug: 'graph-bfs', platform: 'Codeforces' },
  problem_slug: 'graph-bfs',
  platform: 'Codeforces',
  language: 'python',
  analysis_mode: 'CONTEXT_BASED',
  analysis_status: 'INSUFFICIENT_CONTEXT',
  coverage_gaps: [],
  generated_candidates: [],
  analysis_metadata: {
    duration_ms: 19,
    gaps_detected: 0,
    candidates_generated: 0,
    score: 64,
    errors: [
      {
        type: 'CycleRisk',
        line: 8,
        message: 'Visited set missing early cycle guard.',
        concept: 'GRAPH',
      },
    ],
    warnings: [],
  },
  created_at: '2026-11-20T09:00:00.000Z',
};

function renderHistoryApp(initialRoute: string = '/history') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <HealthProvider pollingIntervalMs={60000}>
        <AnalysisProvider>
          <Routes>
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/workspace" element={<WorkspacePage />} />
            <Route path="/findings" element={<FindingsPage />} />
          </Routes>
        </AnalysisProvider>
      </HealthProvider>
    </MemoryRouter>
  );
}

describe('HistoryPage Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    apiClient.setAuthToken(null);
    localStorage.clear();
    sessionStorage.clear();
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });
    vi.spyOn(apiClient, 'getRecentAnalyses').mockResolvedValue([]);
  });

  afterEach(() => {
    apiClient.setAuthToken(null);
    vi.restoreAllMocks();
  });

  it('renders loading skeletons while persisted history request is pending', () => {
    vi.spyOn(apiClient, 'getPersistedReports').mockImplementation(() => new Promise(() => {}));

    renderHistoryApp();

    expect(screen.getByRole('heading', { name: 'Analysis History' })).toBeDefined();
    expect(screen.getByLabelText('Loading history entries')).toBeDefined();
  });

  it('renders empty state cleanly when database reports empty list and no session runs exist', async () => {
    vi.spyOn(apiClient, 'getPersistedReports').mockResolvedValue({
      items: [],
      total: 0,
      skip: 0,
      limit: 20,
    });

    renderHistoryApp();

    expect(await screen.findByText('No Analysis History Recorded Yet')).toBeDefined();
    expect(screen.getByText('PostgreSQL Synced')).toBeDefined();
  });

  it('handles HTTP 500 backend error and recovers on Try Again', async () => {
    const spy = vi
      .spyOn(apiClient, 'getPersistedReports')
      .mockRejectedValueOnce({
        error: 'HTTP 500',
        detail: 'Database connection pool exhausted',
        status_code: 500,
        request_id: null,
      })
      .mockResolvedValueOnce({
        items: [DB_DOC_1],
        total: 1,
        skip: 0,
        limit: 20,
      });

    renderHistoryApp();

    expect(await screen.findByText('Failed to Load Database History')).toBeDefined();
    expect(screen.getByText('Database connection pool exhausted')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Try Again' }));

    expect(await screen.findByText('Two Sum Solver')).toBeDefined();
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('renders Backend Disconnected banner when API is unreachable (status_code 0)', async () => {
    vi.spyOn(apiClient, 'getPersistedReports').mockRejectedValue({
      error: 'NetworkError',
      detail: 'Connection refused',
      status_code: 0,
      request_id: null,
    });

    renderHistoryApp();

    expect(await screen.findByText('Backend Disconnected')).toBeDefined();
    expect(screen.getByText('Backend Offline')).toBeDefined();
    expect(screen.getByText('No Analysis History Recorded Yet')).toBeDefined();
  });

  it('renders HTTP 503 banner and displays multiple runs recorded in Workspace without mutating Workspace', async () => {
    vi.spyOn(apiClient, 'getPersistedReports').mockRejectedValue({
      error: 'HTTP 503',
      detail: 'Database persistence unavailable',
      status_code: 503,
      request_id: null,
    });
    vi.spyOn(apiClient, 'analyzeCode')
      .mockResolvedValueOnce(SAMPLE_REPORT_ONE)
      .mockResolvedValueOnce(SAMPLE_REPORT_TWO);

    render(
      <MemoryRouter initialEntries={['/workspace']}>
        <HealthProvider pollingIntervalMs={60000}>
          <AnalysisProvider>
            <div>
              <a href="/workspace" onClick={(e) => e.preventDefault()}>
                Nav Stub
              </a>
            </div>
            <Routes>
              <Route
                path="/workspace"
                element={
                  <>
                    <WorkspacePage />
                    <HistoryLinkTrigger />
                  </>
                }
              />
              <Route path="/history" element={<HistoryPage />} />
            </Routes>
          </AnalysisProvider>
        </HealthProvider>
      </MemoryRouter>
    );

    const codeEditor = await screen.findByLabelText(/Python source code editor/i);
    fireEvent.change(codeEditor, { target: { value: WORKSPACE_SAMPLE_CODE } });
    fireEvent.click(screen.getAllByRole('button', { name: /Analyze Code/i })[0]);
    await waitFor(() => expect(apiClient.analyzeCode).toHaveBeenCalledTimes(1));

    // Second run with higher score
    fireEvent.change(codeEditor, { target: { value: 'def safe(a):\n    return a\n' } });
    fireEvent.click(screen.getAllByRole('button', { name: /Analyze Code/i })[0]);
    await waitFor(() => expect(apiClient.analyzeCode).toHaveBeenCalledTimes(2));

    // Navigate to History via link button
    fireEvent.click(screen.getByText('Go To History'));

    expect(
      await screen.findByText('Stateless Mode — PostgreSQL Persistence Offline')
    ).toBeDefined();
    expect(screen.getAllByText('alpha.py').length).toBe(2);
    expect(screen.getByText('96/100')).toBeDefined();
    expect(screen.getByText('68/100')).toBeDefined();

    // Inspect immutable historical report
    const viewButtons = screen.getAllByRole('button', { name: 'View Report' });
    fireEvent.click(viewButtons[0]);

    expect(await screen.findByText('Immutable Historical Snapshot')).toBeDefined();
    expect(screen.getByText(/Source code is unavailable in this view\./i)).toBeDefined();

    // Navigate back to Workspace and confirm code draft is intact
    fireEvent.click(screen.getByRole('link', { name: /Workspace/i }));
    const restoredEditor = (await screen.findByLabelText(
      /Python source code editor/i
    )) as HTMLTextAreaElement;
    expect(restoredEditor.value).toBe('def safe(a):\n    return a\n');
  });

  it('unlocks persisted DB reports via in-memory login on HTTP 401 and clears token on Sign Out', async () => {
    vi.spyOn(apiClient, 'getPersistedReports').mockImplementation(async () => {
      if (!apiClient.hasAuthToken()) {
        throw {
          error: 'HTTP 401',
          detail: 'Not authenticated',
          status_code: 401,
          request_id: null,
        };
      }
      return {
        items: [DB_DOC_1, DB_DOC_2],
        total: 2,
        skip: 0,
        limit: 20,
      };
    });
    vi.spyOn(apiClient, 'login').mockResolvedValue({
      access_token: 'jwt-secret-mem-only',
      refresh_token: 'refresh-mem-only',
      token_type: 'bearer',
      expires_in: 1800,
    });
    vi.spyOn(apiClient, 'logout').mockResolvedValue(undefined);

    renderHistoryApp();

    expect(
      await screen.findByText('Authentication Required for Database History')
    ).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'dev@edgemind.io' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'StrongPass!123' },
    });

    const form = screen.getByLabelText('Backend history authentication');
    fireEvent.submit(form.querySelector('form')!);

    expect(await screen.findByText('Two Sum Solver')).toBeDefined();
    expect(screen.getByText('Graph BFS')).toBeDefined();
    expect(screen.getByText('PostgreSQL Synced')).toBeDefined();
    // Tokens never leak into browser storage
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);

    // Search filter + Clear Filters
    const searchInput = screen.getByLabelText('Search history');
    fireEvent.change(searchInput, { target: { value: 'Graph BFS' } });
    expect(screen.queryByText('Two Sum Solver')).toBeNull();
    expect(screen.getByText('Graph BFS')).toBeDefined();

    fireEvent.click(screen.getByText('Reset all filters'));
    expect(screen.getByText('Two Sum Solver')).toBeDefined();

    // Sign out revokes in-memory auth and locks DB view again
    fireEvent.click(screen.getByLabelText('Sign out of backend history'));
    expect(
      await screen.findByText('Authentication Required for Database History')
    ).toBeDefined();
    expect(apiClient.hasAuthToken()).toBe(false);
  });

  it('supports comparing two persisted runs, server pagination, exporting, and confirmed deletion', async () => {
    const reportsSpy = vi
      .spyOn(apiClient, 'getPersistedReports')
      .mockResolvedValueOnce({
        items: [DB_DOC_1, DB_DOC_2],
        total: 25,
        skip: 0,
        limit: 20,
      })
      .mockResolvedValueOnce({
        items: [DB_DOC_2],
        total: 25,
        skip: 20,
        limit: 20,
      });

    vi.spyOn(apiClient, 'deleteAnalysisReport')
      .mockRejectedValueOnce({
        error: 'HTTP 500',
        detail: 'Delete constraint blocked',
        status_code: 500,
        request_id: null,
      })
      .mockResolvedValueOnce(undefined);

    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const createObjectUrlSpy = vi.fn().mockReturnValue('blob:mock-download');
    const revokeObjectUrlSpy = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: createObjectUrlSpy,
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      writable: true,
      value: revokeObjectUrlSpy,
    });

    try {
      renderHistoryApp();

      expect(await screen.findByText('Two Sum Solver')).toBeDefined();
      expect(screen.getByText('Database records 1-20 of 25')).toBeDefined();

      // Set A and Set B to trigger Compare Mode
      const setAButtons = screen.getAllByRole('button', { name: 'Set A' });
      const setBButtons = screen.getAllByRole('button', { name: 'Set B' });
      fireEvent.click(setBButtons[0]); // Two Sum (88)
      fireEvent.click(setAButtons[1]); // Graph BFS (64)

      const compareSection = await screen.findByLabelText('Run comparison');
      expect(within(compareSection).getByText('Delta: +24')).toBeDefined();
      expect(within(compareSection).getByText(/Target mismatch notice/i)).toBeDefined();

      // View Detail & Export JSON/CSV
      fireEvent.click(screen.getAllByRole('button', { name: 'View Report' })[0]);
      const reportPanel = await screen.findByLabelText('Historical report for Two Sum Solver');
      expect(within(reportPanel).getByText('BoundaryHint')).toBeDefined();

      fireEvent.click(screen.getByRole('button', { name: 'Export JSON report for Two Sum Solver' }));
      expect(await screen.findByText(/JSON downloaded/i)).toBeDefined();
      expect(createObjectUrlSpy).toHaveBeenCalledTimes(1);
      expect(revokeObjectUrlSpy).toHaveBeenCalledTimes(1);

      // Delete failure leaves item intact
      const historyList = screen.getByRole('list', { name: 'Analysis history entries' });
      fireEvent.click(screen.getByLabelText('Delete Two Sum Solver'));
      fireEvent.click(screen.getByRole('button', { name: 'Confirm Delete' }));
      expect(await screen.findByText(/Delete failed: Delete constraint blocked/i)).toBeDefined();
      expect(within(historyList).getByText('Two Sum Solver')).toBeDefined();

      // Retry Delete succeeds (204) and removes entry
      fireEvent.click(screen.getByRole('button', { name: 'Confirm Delete' }));
      await waitFor(() => {
        expect(within(historyList).queryByText('Two Sum Solver')).toBeNull();
      });

      // Next page pagination queries skip=20
      fireEvent.click(screen.getByRole('button', { name: 'Next' }));
      await waitFor(() => {
        expect(reportsSpy).toHaveBeenLastCalledWith(
          { skip: 20, limit: 20 },
          expect.any(AbortSignal)
        );
      });
    } finally {
      Object.defineProperty(URL, 'createObjectURL', {
        configurable: true,
        writable: true,
        value: originalCreateObjectURL,
      });
      Object.defineProperty(URL, 'revokeObjectURL', {
        configurable: true,
        writable: true,
        value: originalRevokeObjectURL,
      });
    }
  });
});

const HistoryLinkTrigger = () => <Link to="/history">Go To History</Link>;
