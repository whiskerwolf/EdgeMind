import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { FindingsPage } from '../pages/FindingsPage';
import { WorkspacePage } from '../pages/WorkspacePage';
import { HealthProvider } from '../context/HealthContext';
import { AnalysisProvider } from '../context/AnalysisContext';
import { apiClient } from '../api/client';
import { diagnosisClient, DiagnosisStreamError } from '../api/diagnosisClient';
import { AnalysisReport, DiagnosisStreamEvent } from '../types/api';

const MULTI_FINDING_CODE = `def compute_ratio(values, unused_arg):
    temp_flag = True
    return sum(values) / 0
`;

const MULTI_FINDING_REPORT: AnalysisReport = {
  file_path: 'sample_check.py',
  file: 'sample_check.py',
  overall_status: 'FAIL',
  status: 'FAIL',
  score: 70,
  total_errors: 1,
  total_warnings: 2,
  syntax_status: 'PASS',
  runtime_status: 'SKIPPED',
  logic_status: 'FAIL',
  quality_status: 'WARNING',
  complexity_status: 'PASS',
  errors: [
    {
      type: 'ZeroDivisionError',
      line: 3,
      line_number: 3,
      message: 'You are trying to divide a number by zero.',
      why: 'Division by literal zero always raises ZeroDivisionError.',
      explanation: 'Division by literal zero always raises ZeroDivisionError.',
      fix: 'Validate divisor before performing division.',
      suggested_fix: 'Validate divisor before performing division.',
      concept: 'DIVISION AND ERROR HANDLING',
    },
  ],
  warnings: [
    {
      type: 'UnusedVariable',
      line: 2,
      line_number: 2,
      message: "Variable 'temp_flag' is assigned but never used.",
      why: '',
      explanation: '',
      fix: '',
      suggested_fix: '',
      concept: 'CODE QUALITY',
    },
    {
      type: 'ModuleDesignNote',
      line: 0,
      line_number: 0,
      message: 'Module missing top-level docstring summary.',
      why: '',
      explanation: '',
      fix: '',
      suggested_fix: '',
      concept: '',
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

function renderMultiRouteApp(initialRoute: string = '/findings') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <HealthProvider pollingIntervalMs={60000}>
        <AnalysisProvider>
          <Routes>
            <Route path="/workspace" element={<WorkspacePage />} />
            <Route path="/findings" element={<FindingsPage />} />
          </Routes>
        </AnalysisProvider>
      </HealthProvider>
    </MemoryRouter>
  );
}

async function seedWorkspaceAndOpenFindings(report: AnalysisReport = MULTI_FINDING_REPORT) {
  vi.spyOn(apiClient, 'analyzeCode').mockResolvedValue(report);
  renderMultiRouteApp('/workspace');

  const editor = await screen.findByLabelText('Python source code editor');
  fireEvent.change(editor, { target: { value: MULTI_FINDING_CODE } });

  const analyzeBtn = await waitFor(() => {
    const btn = screen.getByTitle('Run static analysis (⌘↵)') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    return btn;
  });
  fireEvent.click(analyzeBtn);

  const explorerLink = await screen.findByTitle('Open Findings Explorer');
  fireEvent.click(explorerLink);

  expect(await screen.findByRole('heading', { level: 2, name: 'Findings Explorer' })).toBeDefined();
}

describe('FindingsPage Integration', () => {
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

  it('renders empty state when no analysis has been performed', async () => {
    renderMultiRouteApp('/findings');

    expect(await screen.findByRole('heading', { level: 2, name: 'Findings Explorer' })).toBeDefined();
    expect(screen.getByText('No Active Analysis')).toBeDefined();
    expect(screen.getByText('No Analysis Performed Yet')).toBeDefined();
    expect(screen.getByRole('link', { name: /go to code workspace/i })).toBeDefined();
  });

  it('shows Backend Disconnected warning when API is offline and no analysis exists', async () => {
    vi.spyOn(apiClient, 'getHealth').mockRejectedValue({
      error: 'NetworkError',
      detail: 'Connection refused',
      status_code: 0,
      request_id: null,
    });

    renderMultiRouteApp('/findings');

    expect(await screen.findByText('Backend Offline')).toBeDefined();
    expect(screen.getByText('Backend Disconnected')).toBeDefined();
  });

  it('renders zero findings empty state on PASS report', async () => {
    await seedWorkspaceAndOpenFindings({
      ...MULTI_FINDING_REPORT,
      overall_status: 'PASS',
      status: 'PASS',
      score: 100,
      total_errors: 0,
      total_warnings: 0,
      errors: [],
      warnings: [],
    });

    expect(screen.getByText('PASS (100/100)')).toBeDefined();
    expect(screen.getByText('Zero Findings Detected')).toBeDefined();
  });

  it('supports searching, severity filtering, category filtering, sorting, and clearing filters', async () => {
    await seedWorkspaceAndOpenFindings();

    // Default header & counts
    expect(screen.getByText('FAIL (70/100)')).toBeDefined();
    const list = screen.getByLabelText('Findings list');
    expect(within(list).getAllByRole('listitem')).toHaveLength(3);

    // Search filter
    const searchInput = screen.getByLabelText('Search findings');
    fireEvent.change(searchInput, { target: { value: 'temp_flag' } });
    expect(within(list).getAllByRole('listitem')).toHaveLength(1);
    expect(within(list).getByText('UnusedVariable')).toBeDefined();

    // Missing optional fields notice shown when selecting UnusedVariable
    expect(
      screen.getByText(/No pre-computed explanation or suggested fix metadata/i)
    ).toBeDefined();

    // Clear search then test severity + category filter composition
    fireEvent.click(screen.getByRole('button', { name: /clear filters/i }));
    expect(within(list).getAllByRole('listitem')).toHaveLength(3);

    const categorySelect = screen.getByLabelText('Filter by category') as HTMLSelectElement;
    // Actual categories: CODE QUALITY & DIVISION AND ERROR HANDLING
    expect(Array.from(categorySelect.options).map((o) => o.value)).toEqual([
      'all',
      'CODE QUALITY',
      'DIVISION AND ERROR HANDLING',
    ]);

    fireEvent.change(categorySelect, { target: { value: 'DIVISION AND ERROR HANDLING' } });
    expect(within(list).getAllByRole('listitem')).toHaveLength(1);

    // Combining incompatible warning severity leaves empty filter state
    fireEvent.click(screen.getByRole('button', { name: /warnings \(2\)/i }));
    expect(screen.getByText('No Findings Match Filters')).toBeDefined();

    // Clear filters inside empty filtered state restores list
    const clearButtons = screen.getAllByRole('button', { name: /clear filters/i });
    fireEvent.click(clearButtons[clearButtons.length - 1]);
    expect(within(list).getAllByRole('listitem')).toHaveLength(3);

    // Deterministic line sorting places module-level finding (missing line) safely last
    const sortSelect = screen.getByLabelText('Sort findings') as HTMLSelectElement;
    fireEvent.change(sortSelect, { target: { value: 'line-asc' } });
    const sortedItems = within(list).getAllByRole('listitem');
    expect(sortedItems[0].textContent).toContain('UnusedVariable');
    expect(sortedItems[1].textContent).toContain('ZeroDivisionError');
    expect(sortedItems[2].textContent).toContain('ModuleDesignNote');
  });

  it('supports two-way navigation between Findings and Workspace including line jump and missing line safety', async () => {
    await seedWorkspaceAndOpenFindings();

    // Jump from ZeroDivisionError (Line 3) -> Workspace
    const inspectBtn = screen.getByRole('button', { name: /inspect in workspace/i });
    fireEvent.click(inspectBtn);

    expect(await screen.findByRole('heading', { level: 2, name: 'Code Workspace' })).toBeDefined();
    expect(screen.getByText('Focused Line 3')).toBeDefined();
    const editor = screen.getByLabelText('Python source code editor') as HTMLTextAreaElement;
    expect(editor.value).toContain('return sum(values) / 0');

    // Jump from Workspace finding back into Findings Explorer pre-selecting ModuleDesignNote
    const openInFindingsBtns = screen.getAllByRole('button', { name: /open in findings/i });
    fireEvent.click(openInFindingsBtns[2]);

    expect(await screen.findByRole('heading', { level: 2, name: 'Findings Explorer' })).toBeDefined();
    expect(screen.getByRole('heading', { level: 3, name: 'ModuleDesignNote' })).toBeDefined();
    expect(screen.getByText('Location: Module-level (no specific line)')).toBeDefined();

    // Navigating on module-level finding returns cleanly to Workspace without fabricating Focused Line
    fireEvent.click(screen.getByRole('button', { name: /open file in workspace/i }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Code Workspace' })).toBeDefined();
    expect(screen.queryByText(/Focused Line/)).toBeNull();
  });

  it('streams AI diagnosis via SSE, marks output advisory, and supports cancellation and error retry', async () => {
    await seedWorkspaceAndOpenFindings();

    // 1. Mock streaming SSE response with incremental chunks + completion
    vi.spyOn(diagnosisClient, 'streamDiagnosis').mockImplementation(async function* () {
      const started: DiagnosisStreamEvent = {
        event: 'diagnosis_started',
        session_id: 'diag_abc123',
        finding_id: 'error-1-ZeroDivisionError-3',
        finding_type: 'ZeroDivisionError',
        line: 3,
        sequence_id: 1,
        timestamp: '2026-11-25T06:00:00Z',
      };
      yield started;
      yield {
        event: 'response_chunk',
        session_id: 'diag_abc123',
        finding_id: 'error-1-ZeroDivisionError-3',
        chunk: '### Root Cause\nDividing ',
        sequence_id: 2,
        timestamp: '2026-11-25T06:00:01Z',
      };
      yield {
        event: 'response_chunk',
        session_id: 'diag_abc123',
        finding_id: 'error-1-ZeroDivisionError-3',
        chunk: 'by zero fails.',
        sequence_id: 3,
        timestamp: '2026-11-25T06:00:02Z',
      };
      yield {
        event: 'completed',
        session_id: 'diag_abc123',
        finding_id: 'error-1-ZeroDivisionError-3',
        status: 'completed',
        duration_ms: 1200,
        finish_reason: 'stop',
        sequence_id: 4,
        timestamp: '2026-11-25T06:00:03Z',
      };
    });

    fireEvent.click(screen.getByRole('button', { name: /explain with ai/i }));

    expect(await screen.findByText('AI-Generated · Unverified')).toBeDefined();
    expect(await screen.findByText(/Completed · 1\.2s/i)).toBeDefined();
    expect(screen.getByText('Dividing by zero fails.')).toBeDefined();
    expect(screen.getByText('FAIL (70/100)')).toBeDefined(); // Static score preserved

    // 2. Test cancellation preserves partial streamed content
    vi.spyOn(diagnosisClient, 'streamDiagnosis').mockImplementation(async function* (_req, opts) {
      yield {
        event: 'diagnosis_started',
        session_id: 'diag_cancel_1',
        finding_id: 'warning-2-UnusedVariable-2',
        finding_type: 'UnusedVariable',
        line: 2,
        sequence_id: 1,
        timestamp: '2026-11-25T06:00:00Z',
      };
      yield {
        event: 'response_chunk',
        session_id: 'diag_cancel_1',
        finding_id: 'warning-2-UnusedVariable-2',
        chunk: 'Partial explanation token.',
        sequence_id: 2,
        timestamp: '2026-11-25T06:00:01Z',
      };
      await new Promise<void>((resolve) => {
        opts?.signal?.addEventListener('abort', () => resolve(), { once: true });
      });
    });

    // Select UnusedVariable (Line 2)
    fireEvent.click(screen.getByText('UnusedVariable'));
    fireEvent.click(screen.getByRole('button', { name: /explain with ai/i }));

    expect(await screen.findByText('Partial explanation token.')).toBeDefined();
    const cancelBtn = screen.getByRole('button', { name: /^cancel$/i });
    fireEvent.click(cancelBtn);

    expect(await screen.findByText('Diagnosis Cancelled')).toBeDefined();
    expect(screen.getByText('Partial explanation token.')).toBeDefined();

    // 3. Test error state & retry recovery
    const streamSpy = vi.spyOn(diagnosisClient, 'streamDiagnosis');
    streamSpy.mockImplementationOnce(async function* () {
      throw new DiagnosisStreamError('Upstream model timed out', 504, true, 'stream_timeout');
    });
    streamSpy.mockImplementationOnce(async function* () {
      yield {
        event: 'response_chunk',
        session_id: 'diag_retry_ok',
        finding_id: 'warning-2-UnusedVariable-2',
        chunk: 'Remove unused temp_flag assignment.',
        sequence_id: 1,
        timestamp: '2026-11-25T06:01:00Z',
      };
      yield {
        event: 'completed',
        session_id: 'diag_retry_ok',
        finding_id: 'warning-2-UnusedVariable-2',
        status: 'completed',
        duration_ms: 450,
        finish_reason: 'stop',
        sequence_id: 2,
        timestamp: '2026-11-25T06:01:01Z',
      };
    });

    fireEvent.click(screen.getByRole('button', { name: /retry diagnosis/i }));
    expect(await screen.findByText('Upstream model timed out')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: /retry diagnosis/i }));
    expect(await screen.findByText('Remove unused temp_flag assignment.')).toBeDefined();
  });
});
