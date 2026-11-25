import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { apiClient, sanitizeApiErrorDetail } from '../api/client';
import { diagnosisClient } from '../api/diagnosisClient';
import { AnalysisProvider, useAnalysisContext } from '../context/AnalysisContext';
import { HealthProvider } from '../context/HealthContext';
import { SettingsProvider, useSettingsContext } from '../context/SettingsContext';
import { AnalysisReport } from '../types/api';
import {
  DEFAULT_APP_SETTINGS,
  EDGEMIND_SETTINGS_STORAGE_KEY,
} from '../utils/settingsConfig';

const BASE_REPORT: AnalysisReport = {
  file_path: 'risk.py',
  file: 'risk.py',
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

describe('Phase 6.11 Critical Integration Risks', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    apiClient.setAuthToken(null);
    apiClient.setBaseUrl('http://127.0.0.1:8000');
  });

  afterEach(() => {
    apiClient.setAuthToken(null);
    apiClient.setBaseUrl('http://127.0.0.1:8000');
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('synchronizes saved API base URL synchronously before HealthProvider initial poll & shares it with SSE client', async () => {
    localStorage.setItem(
      EDGEMIND_SETTINGS_STORAGE_KEY,
      JSON.stringify({
        ...DEFAULT_APP_SETTINGS,
        apiBaseUrl: 'http://127.0.0.1:9123',
      })
    );

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/health')) {
        return new Response(JSON.stringify({ status: 'healthy', service: 'EdgeMind' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response('event: completed\ndata: {"status":"completed","duration_ms":5}\n\n', {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      });
    });

    const ProbeComponent = () => {
      const { saveSettings, settings } = useSettingsContext();
      return (
        <div>
          <span data-testid="active-url">{settings.apiBaseUrl}</span>
          <button
            type="button"
            onClick={() =>
              saveSettings({ ...settings, apiBaseUrl: 'http://127.0.0.1:9456' })
            }
          >
            Switch URL
          </button>
        </div>
      );
    };

    render(
      <MemoryRouter>
        <SettingsProvider>
          <HealthProvider pollingIntervalMs={60000}>
            <ProbeComponent />
          </HealthProvider>
        </SettingsProvider>
      </MemoryRouter>
    );

    // Initial /health check must hit saved :9123 URL immediately, never :8000
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        'http://127.0.0.1:9123/health',
        expect.anything()
      );
    });
    expect(fetchSpy).not.toHaveBeenCalledWith(
      'http://127.0.0.1:8000/health',
      expect.anything()
    );

    fireEvent.click(screen.getByText('Switch URL'));

    for await (const _ of diagnosisClient.streamDiagnosis({
      finding: {
        finding_id: 'f1',
        type: 'ZeroDivisionError',
        severity: 'error',
        message: 'div by zero',
        line: 1,
      },
      code_context: 'return 1/0',
      context_start_line: 1,
      context_end_line: 1,
      filename: 'test.py',
      language: 'python',
    })) {
      // consume stream
    }

    expect(fetchSpy).toHaveBeenCalledWith(
      'http://127.0.0.1:9456/api/v1/diagnose/stream',
      expect.anything()
    );
  });

  it('prevents duplicate concurrent analyses and drops stale in-flight responses when cleared', async () => {
    let resolveFirst!: (val: AnalysisReport) => void;
    const analyzeSpy = vi
      .spyOn(apiClient, 'analyzeCode')
      .mockImplementationOnce(
        () =>
          new Promise<AnalysisReport>((resolve) => {
            resolveFirst = resolve;
          })
      );

    const Harness = () => {
      const {
        runAnalysis,
        clearWorkspaceResult,
        latestReport,
        sessionRuns,
        isAnalyzing,
      } = useAnalysisContext();
      return (
        <div>
          <button
            type="button"
            onClick={() => {
              void runAnalysis({ code: 'a = 1/0\n', filename: 'first.py', static_only: true });
              void runAnalysis({ code: 'b = 2/0\n', filename: 'dup.py', static_only: true });
            }}
          >
            Trigger Duplicate
          </button>
          <button type="button" onClick={() => clearWorkspaceResult()}>
            Clear Workspace
          </button>
          <span data-testid="analyzing-flag">{String(isAnalyzing)}</span>
          <span data-testid="latest-file">{latestReport?.file ?? 'none'}</span>
          <span data-testid="run-count">{sessionRuns.length}</span>
        </div>
      );
    };

    render(
      <MemoryRouter>
        <SettingsProvider>
          <HealthProvider pollingIntervalMs={60000}>
            <AnalysisProvider>
              <Harness />
            </AnalysisProvider>
          </HealthProvider>
        </SettingsProvider>
      </MemoryRouter>
    );

    fireEvent.click(screen.getByText('Trigger Duplicate'));
    expect(analyzeSpy).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('analyzing-flag').textContent).toBe('true');

    // User clears while first request is still in flight
    fireEvent.click(screen.getByText('Clear Workspace'));
    expect(screen.getByTestId('analyzing-flag').textContent).toBe('false');

    // Late resolution of aborted/stale request must NOT repopulate cleared state
    await act(async () => {
      resolveFirst(BASE_REPORT);
    });
    expect(screen.getByTestId('latest-file').textContent).toBe('none');
    expect(screen.getByTestId('run-count').textContent).toBe('0');
  });

  it('redacts sensitive tokens in REST ApiError responses and handles premature SSE EOF retryably', async () => {
    expect(
      sanitizeApiErrorDetail('Upstream rejected Bearer abc.def.ghi and api_key=secret12345')
    ).toBe('Upstream rejected Bearer [REDACTED] and api_key=[REDACTED]');

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Invalid sk-proj-abcdefghijklmnopqrstuvwxyz1234' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    await expect(apiClient.getRecentAnalyses(5)).rejects.toMatchObject({
      status_code: 401,
      detail: 'Invalid [REDACTED]',
    });

    // Premature SSE EOF without completed/error yields retryable DiagnosisStreamError
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'id: 1\nevent: diagnosis_started\ndata: {"session_id":"s1","finding_id":"f1","finding_type":"Err","line":1}\n\n'
          )
        );
        controller.close();
      },
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(stream, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      })
    );

    const events: string[] = [];
    await expect(
      (async () => {
        for await (const ev of diagnosisClient.streamDiagnosis({
          finding: { finding_id: 'f1', type: 'Err', severity: 'error', message: 'msg', line: 1 },
          code_context: 'x = 1',
          context_start_line: 1,
          context_end_line: 1,
          filename: 'a.py',
          language: 'python',
        })) {
          events.push(ev.event);
        }
      })()
    ).rejects.toMatchObject({
      retryable: true,
      errorType: 'premature_eof',
    });
    expect(events).toEqual(['diagnosis_started']);
  });

  it('propagates defaultFilename setting to an untouched blank Workspace', async () => {
    const SyncHarness = () => {
      const { workspaceFilename } = useAnalysisContext();
      const { saveSettings, settings } = useSettingsContext();
      return (
        <div>
          <span data-testid="ws-filename">{workspaceFilename}</span>
          <button
            type="button"
            onClick={() => saveSettings({ ...settings, defaultFilename: 'updated_entry.py' })}
          >
            Update Default Filename
          </button>
        </div>
      );
    };

    render(
      <MemoryRouter initialEntries={['/']}>
        <SettingsProvider>
          <HealthProvider pollingIntervalMs={60000}>
            <AnalysisProvider>
              <Routes>
                <Route path="/" element={<SyncHarness />} />
              </Routes>
            </AnalysisProvider>
          </HealthProvider>
        </SettingsProvider>
      </MemoryRouter>
    );

    expect(screen.getByTestId('ws-filename').textContent).toBe('snippet.py');
    fireEvent.click(screen.getByText('Update Default Filename'));
    await waitFor(() => {
      expect(screen.getByTestId('ws-filename').textContent).toBe('updated_entry.py');
    });
  });
});
