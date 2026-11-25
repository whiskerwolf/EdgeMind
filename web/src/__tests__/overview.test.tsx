import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { OverviewPage } from '../pages/OverviewPage';
import { HealthProvider } from '../context/HealthContext';
import { AnalysisProvider } from '../context/AnalysisContext';
import { apiClient } from '../api/client';
import { AnalysisReport, AnalysisSessionItem } from '../types/api';

function renderOverview() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <HealthProvider pollingIntervalMs={60000}>
        <AnalysisProvider>
          <OverviewPage />
        </AnalysisProvider>
      </HealthProvider>
    </MemoryRouter>
  );
}

describe('OverviewPage Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading skeletons before initial health check settles', () => {
    vi.spyOn(apiClient, 'getHealth').mockImplementation(
      () => new Promise(() => {}) // unresolved promise
    );

    renderOverview();

    expect(screen.getByLabelText('Loading system status')).toBeDefined();
    expect(screen.getByLabelText('Loading recent analyses')).toBeDefined();
  });

  it('renders healthy backend with honest empty analysis and auth-gated history unavailable state', async () => {
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });
    vi.spyOn(apiClient, 'getRecentAnalyses').mockRejectedValue({
      error: 'HTTP 401',
      detail: 'Not authenticated',
      status_code: 401,
      request_id: null,
    });

    renderOverview();

    expect(await screen.findByText('Backend Online')).toBeDefined();
    expect(screen.getByText('EdgeMind')).toBeDefined();
    expect(screen.getByText('No Analysis Performed Yet')).toBeDefined();
    expect(screen.getByText('Errors: — · Warnings: —')).toBeDefined();
    expect(await screen.findByText('Persisted History Unavailable')).toBeDefined();
    expect(screen.getByText('Auth Required')).toBeDefined();
  });

  it('renders disconnected backend state clearly without fabricating zeroes', async () => {
    vi.spyOn(apiClient, 'getHealth').mockRejectedValue({
      error: 'NetworkError',
      detail: 'Connection refused',
      status_code: 0,
      request_id: null,
    });
    const historySpy = vi.spyOn(apiClient, 'getRecentAnalyses');

    renderOverview();

    expect(await screen.findByText('Backend Offline')).toBeDefined();
    expect(screen.getAllByText('Backend Disconnected').length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByText('Severity metrics are unavailable while the backend is disconnected.')
    ).toBeDefined();
    expect(historySpy).not.toHaveBeenCalled();
  });

  it('renders database offline notice when history returns 503', async () => {
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });
    vi.spyOn(apiClient, 'getRecentAnalyses').mockRejectedValue({
      error: 'HTTP 503',
      detail: 'Database persistence is not configured or currently unreachable.',
      status_code: 503,
      request_id: null,
    });

    renderOverview();

    expect(await screen.findByText('Database Offline')).toBeDefined();
    expect(screen.getByText('Offline / Unconfigured')).toBeDefined();
  });

  it('renders persisted recent activity items when history returns data', async () => {
    const mockSessions: AnalysisSessionItem[] = [
      {
        id: '11111111-1111-1111-1111-111111111111',
        analysis_mode: 'BASELINE_DRIVEN',
        language: 'python',
        analysis_status: 'SUCCESS',
        gaps_detected: 3,
        candidates_generated: 5,
        duration_ms: 42.5,
        problem_title: 'Two Sum',
        created_at: '2026-11-24T12:00:00Z',
      },
    ];

    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });
    vi.spyOn(apiClient, 'getRecentAnalyses').mockResolvedValue(mockSessions);

    renderOverview();

    expect(await screen.findAllByText('Two Sum')).toBeDefined();
    expect(screen.getAllByText('BASELINE_DRIVEN').length).toBeGreaterThan(0);
    expect(screen.getAllByText('42.5ms').length).toBeGreaterThan(0);
  });

  it('renders empty state when backend history returns empty array', async () => {
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });
    vi.spyOn(apiClient, 'getRecentAnalyses').mockResolvedValue([]);

    renderOverview();

    expect(await screen.findByText('No Persisted Analyses Found')).toBeDefined();
  });

  it('renders error state and allows retrying when history endpoint returns 500', async () => {
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });
    const historySpy = vi
      .spyOn(apiClient, 'getRecentAnalyses')
      .mockRejectedValueOnce({
        error: 'Internal Server Error',
        detail: 'Query execution failed',
        status_code: 500,
        request_id: 'req-err-1',
      })
      .mockResolvedValueOnce([]);

    renderOverview();

    expect(await screen.findByText('Failed to Load History')).toBeDefined();
    expect(screen.getByText('Query execution failed')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: /try again/i }));

    expect(await screen.findByText('No Persisted Analyses Found')).toBeDefined();
    expect(historySpy).toHaveBeenCalledTimes(2);
  });

  it('runs sample verification analysis and displays findings & severity distribution', async () => {
    const mockReport: AnalysisReport = {
      file_path: 'sample_check.py',
      file: 'sample_check.py',
      overall_status: 'FAIL',
      status: 'FAIL',
      score: 75,
      total_errors: 1,
      total_warnings: 1,
      syntax_status: 'PASS',
      runtime_status: 'SKIPPED',
      logic_status: 'PASS',
      quality_status: 'WARNING',
      complexity_status: 'PASS',
      errors: [
        {
          type: 'ZeroDivisionError',
          line: 3,
          line_number: 3,
          message: 'Division by zero detected.',
          why: 'Divisor is literal 0.',
          explanation: 'Divisor is literal 0.',
          fix: 'Use non-zero divisor.',
          suggested_fix: 'Use non-zero divisor.',
          concept: 'Runtime Safety',
        },
      ],
      warnings: [
        {
          type: 'UnusedVariable',
          line: 2,
          line_number: 2,
          message: "Variable 'unused_flag' is unused.",
          why: 'Assigned but never read.',
          explanation: 'Assigned but never read.',
          fix: 'Remove unused variable.',
          suggested_fix: 'Remove unused variable.',
          concept: 'Code Quality',
        },
      ],
      summary: {
        syntax: 'PASS',
        runtime: 'SKIPPED',
        logic: 'PASS',
        quality: 'WARNING',
        complexity: 'PASS',
      },
    };

    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });
    vi.spyOn(apiClient, 'getRecentAnalyses').mockResolvedValue([]);
    vi.spyOn(apiClient, 'analyzeCode').mockResolvedValue(mockReport);

    renderOverview();

    const sampleButton = await screen.findByRole('button', { name: /run sample verification/i });
    fireEvent.click(sampleButton);

    await waitFor(() => {
      expect(screen.getByText('75 / 100')).toBeDefined();
    });

    expect(screen.getByText('ZeroDivisionError')).toBeDefined();
    expect(screen.getByText('UnusedVariable')).toBeDefined();
    expect(screen.getByText('Errors: 1')).toBeDefined();
    expect(screen.getByText('Warnings: 1')).toBeDefined();
    expect(screen.getByText('Current Browser Session (In-Memory)')).toBeDefined();
  });

  it('distinguishes zero findings state from unanalyzed state', async () => {
    const cleanReport: AnalysisReport = {
      file_path: 'sample_check.py',
      file: 'sample_check.py',
      overall_status: 'PASS',
      status: 'PASS',
      score: 100,
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

    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });
    vi.spyOn(apiClient, 'getRecentAnalyses').mockResolvedValue([]);
    vi.spyOn(apiClient, 'analyzeCode').mockResolvedValue(cleanReport);

    renderOverview();

    fireEvent.click(await screen.findByRole('button', { name: /run sample verification/i }));

    expect(await screen.findByText('Zero Findings Detected')).toBeDefined();
    expect(screen.getByText('100 / 100')).toBeDefined();
  });
});
