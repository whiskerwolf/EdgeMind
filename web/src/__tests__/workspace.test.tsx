import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { WorkspacePage } from '../pages/WorkspacePage';
import { HealthProvider } from '../context/HealthContext';
import { AnalysisProvider } from '../context/AnalysisContext';
import { apiClient } from '../api/client';
import { AnalysisReport } from '../types/api';

function renderWorkspace() {
  return render(
    <MemoryRouter initialEntries={['/workspace']}>
      <HealthProvider pollingIntervalMs={60000}>
        <AnalysisProvider>
          <WorkspacePage />
        </AnalysisProvider>
      </HealthProvider>
    </MemoryRouter>
  );
}

const SAMPLE_FAIL_REPORT: AnalysisReport = {
  file_path: 'sample_check.py',
  file: 'sample_check.py',
  overall_status: 'FAIL',
  status: 'FAIL',
  score: 70,
  total_errors: 1,
  total_warnings: 2,
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
      message: 'You are trying to divide a number by zero.',
      why: 'Dividing by 0 is mathematically undefined.',
      explanation: 'Dividing by 0 is mathematically undefined.',
      fix: 'Guard against zero divisor.',
      suggested_fix: 'Guard against zero divisor.',
      concept: 'Runtime Safety',
    },
  ],
  warnings: [
    {
      type: 'UnusedVariable',
      line: 2,
      line_number: 2,
      message: "Variable 'unused_flag' is assigned but never used.",
      why: 'Dead assignment adds noise.',
      explanation: 'Dead assignment adds noise.',
      fix: 'Remove unused_flag.',
      suggested_fix: 'Remove unused_flag.',
      concept: 'Code Quality',
    },
    {
      type: 'UnusedVariable',
      line: 1,
      line_number: 1,
      message: "Variable 'count' is assigned but never used.",
      why: 'Unused parameter.',
      explanation: 'Unused parameter.',
      fix: 'Prefix with underscore or use parameter.',
      suggested_fix: 'Prefix with underscore or use parameter.',
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

function getPrimaryAnalyzeButton(): HTMLButtonElement {
  return screen.getByTitle('Run static analysis (⌘↵)') as HTMLButtonElement;
}

describe('WorkspacePage Integration', () => {
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

  it('renders initial empty workspace state with code editor and disabled analyze CTA', async () => {
    renderWorkspace();

    expect(screen.getByRole('heading', { level: 2, name: 'Code Workspace' })).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText('Empty')).toBeDefined();
    });
    expect(screen.getByText('Ready for Static Analysis')).toBeDefined();

    const editor = screen.getByLabelText('Python source code editor') as HTMLTextAreaElement;
    expect(editor.value).toBe('');
    expect(getPrimaryAnalyzeButton().disabled).toBe(true);
  });

  it('handles sample code insertion and clearing cleanly', async () => {
    renderWorkspace();

    const sampleSelect = screen.getByLabelText('Insert sample code');
    fireEvent.change(sampleSelect, { target: { value: 'division-check' } });

    const editor = screen.getByLabelText('Python source code editor') as HTMLTextAreaElement;
    expect(editor.value).toContain('calculate_ratio');

    const filenameInput = screen.getByLabelText('Filename label') as HTMLInputElement;
    expect(filenameInput.value).toBe('sample_check.py');

    await waitFor(() => {
      expect(getPrimaryAnalyzeButton().disabled).toBe(false);
    });
    expect(screen.getByText('Code Not Yet Analyzed')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: /clear/i }));
    expect(editor.value).toBe('');
    expect(filenameInput.value).toBe('snippet.py');
    expect(screen.getByText('Ready for Static Analysis')).toBeDefined();
  });

  it('warns and disables analysis when an unsupported language is selected', async () => {
    renderWorkspace();

    const editor = screen.getByLabelText('Python source code editor');
    fireEvent.change(editor, { target: { value: 'const x = 1;' } });

    const langSelect = screen.getByLabelText('Language');
    fireEvent.change(langSelect, { target: { value: 'javascript' } });

    await waitFor(() => {
      expect(screen.getByText('Unsupported Language')).toBeDefined();
    });
    expect(screen.getByText('Unsupported Analysis Language')).toBeDefined();
    expect(getPrimaryAnalyzeButton().disabled).toBe(true);
  });

  it('rejects invalid traversal filenames before hitting backend', async () => {
    const analyzeSpy = vi.spyOn(apiClient, 'analyzeCode');
    renderWorkspace();

    fireEvent.change(screen.getByLabelText('Python source code editor'), {
      target: { value: 'x = 1' },
    });
    fireEvent.change(screen.getByLabelText('Filename label'), {
      target: { value: '../secret.py' },
    });

    await waitFor(() => {
      expect(
        screen.getByText('Filename must be a simple label without paths or traversal.')
      ).toBeDefined();
    });

    expect(getPrimaryAnalyzeButton().disabled).toBe(true);
    expect(analyzeSpy).not.toHaveBeenCalled();
  });

  it('executes analysis, shows loading state, renders findings, supports details/filter, and navigates to line', async () => {
    let resolveFn: ((val: AnalysisReport) => void) | undefined;
    const analyzeSpy = vi.spyOn(apiClient, 'analyzeCode').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFn = resolve;
        })
    );

    renderWorkspace();

    fireEvent.change(screen.getByLabelText('Insert sample code'), {
      target: { value: 'division-check' },
    });

    const analyzeBtn = await waitFor(() => {
      const btn = getPrimaryAnalyzeButton();
      expect(btn.disabled).toBe(false);
      return btn;
    });

    // Trigger analysis + rapid duplicate click to test duplicate prevention
    fireEvent.click(analyzeBtn);
    fireEvent.click(analyzeBtn);

    expect(analyzeSpy).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Analyzing code')).toBeDefined();
    expect(screen.getAllByText('Analyzing...').length).toBeGreaterThanOrEqual(1);

    resolveFn!(SAMPLE_FAIL_REPORT);

    await waitFor(() => {
      expect(screen.getByText('70 / 100')).toBeDefined();
    });

    expect(screen.getByText('ZeroDivisionError')).toBeDefined();
    expect(screen.getAllByText('UnusedVariable').length).toBe(2);

    // Filter to Errors only
    fireEvent.click(screen.getByRole('button', { name: 'Errors (1)' }));
    expect(screen.queryByText('UnusedVariable')).toBeNull();
    expect(screen.getByText('ZeroDivisionError')).toBeDefined();

    // Expand details
    fireEvent.click(screen.getByRole('button', { name: /view explanation & fix/i }));
    expect(screen.getByText('Dividing by 0 is mathematically undefined.')).toBeDefined();
    expect(screen.getByText('Guard against zero divisor.')).toBeDefined();

    // Navigate to line 3 in editor
    fireEvent.click(screen.getByRole('button', { name: /line 3/i }));
    expect(screen.getByText('Focused Line 3')).toBeDefined();
  });

  it('renders clean zero findings state on PASS report and detects unanalyzed code edits', async () => {
    const cleanReport: AnalysisReport = {
      file_path: 'clean_math.py',
      file: 'clean_math.py',
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

    vi.spyOn(apiClient, 'analyzeCode').mockResolvedValue(cleanReport);
    renderWorkspace();

    fireEvent.change(screen.getByLabelText('Insert sample code'), {
      target: { value: 'clean-math' },
    });

    const analyzeBtn = await waitFor(() => {
      const btn = getPrimaryAnalyzeButton();
      expect(btn.disabled).toBe(false);
      return btn;
    });
    fireEvent.click(analyzeBtn);

    expect(await screen.findByText('Zero Findings Detected')).toBeDefined();
    expect(screen.getByText('100 / 100')).toBeDefined();

    // Editing code after analysis should flag Unanalyzed Changes
    fireEvent.change(screen.getByLabelText('Python source code editor'), {
      target: { value: 'def modified():\n    pass\n' },
    });
    expect(screen.getByText('Unanalyzed Changes')).toBeDefined();
    expect(screen.getByText('Modified')).toBeDefined();
  });

  it('handles API failure responses and allows retry', async () => {
    vi.spyOn(apiClient, 'analyzeCode')
      .mockRejectedValueOnce({
        error: 'Internal Server Error',
        detail: 'Static analyzer worker failed',
        status_code: 500,
        request_id: 'req-ws-1',
      })
      .mockResolvedValueOnce(SAMPLE_FAIL_REPORT);

    renderWorkspace();

    fireEvent.change(screen.getByLabelText('Insert sample code'), {
      target: { value: 'division-check' },
    });

    const analyzeBtn = await waitFor(() => {
      const btn = getPrimaryAnalyzeButton();
      expect(btn.disabled).toBe(false);
      return btn;
    });
    fireEvent.click(analyzeBtn);

    expect(await screen.findByText('Analysis Request Failed')).toBeDefined();
    expect(screen.getByText(/Static analyzer worker failed/)).toBeDefined();
    expect(screen.getByText(/req-ws-1/)).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: /try again/i }));

    expect(await screen.findByText('70 / 100')).toBeDefined();
  });

  it('disables analysis and shows offline banner when backend is disconnected', async () => {
    vi.spyOn(apiClient, 'getHealth').mockRejectedValue({
      error: 'NetworkError',
      detail: 'Connection refused',
      status_code: 0,
      request_id: null,
    });

    renderWorkspace();

    expect(await screen.findByText('Backend Offline')).toBeDefined();
    expect(screen.getByText('Backend Disconnected')).toBeDefined();

    fireEvent.change(screen.getByLabelText('Insert sample code'), {
      target: { value: 'division-check' },
    });

    expect(getPrimaryAnalyzeButton().disabled).toBe(true);
  });
});
