import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { apiClient } from '../api/client';
import { AnalysisProvider, useAnalysisContext } from '../context/AnalysisContext';
import { HealthProvider } from '../context/HealthContext';
import { SettingsProvider } from '../context/SettingsContext';
import { HistoryPage } from '../pages/HistoryPage';
import { SettingsPage } from '../pages/SettingsPage';
import { WorkspacePage } from '../pages/WorkspacePage';
import { EDGEMIND_SETTINGS_STORAGE_KEY } from '../utils/settingsConfig';

const SessionHelperBar = () => {
  const { sessionRuns, runAnalysis, loginBackend } = useAnalysisContext();
  return (
    <div>
      <button
        type="button"
        onClick={() => {
          void runAnalysis({ code: 'x = 1\n', filename: 'helper.py', static_only: true });
        }}
      >
        Seed Session Run
      </button>
      <button
        type="button"
        onClick={() => {
          void loginBackend('sec@edgemind.io', 'SecretPass!99');
        }}
      >
        Seed Auth
      </button>
      <span data-testid="session-run-count">{sessionRuns.length}</span>
      <Link to="/workspace">Go Workspace</Link>
      <Link to="/history">Go History</Link>
    </div>
  );
};

function renderSettingsApp(initialRoute: string = '/settings') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <SettingsProvider>
        <HealthProvider pollingIntervalMs={60000}>
          <AnalysisProvider>
            <SessionHelperBar />
            <Routes>
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/workspace" element={<WorkspacePage />} />
              <Route path="/history" element={<HistoryPage />} />
            </Routes>
          </AnalysisProvider>
        </HealthProvider>
      </SettingsProvider>
    </MemoryRouter>
  );
}

describe('SettingsPage Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    apiClient.setAuthToken(null);
    apiClient.setBaseUrl('http://127.0.0.1:8000');

    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });
    vi.spyOn(apiClient, 'getPersistedReports').mockResolvedValue({
      items: [],
      total: 0,
      skip: 0,
      limit: 20,
    });
    vi.spyOn(apiClient, 'getRecentAnalyses').mockResolvedValue([]);
  });

  afterEach(() => {
    apiClient.setAuthToken(null);
    apiClient.setBaseUrl('http://127.0.0.1:8000');
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('renders all real sections and honest backend-enforced read-only limitations', async () => {
    renderSettingsApp();

    expect(screen.getByRole('heading', { name: /Settings & Configuration/i })).toBeDefined();
    expect(screen.getByRole('heading', { name: /Connection & Backend API/i })).toBeDefined();
    expect(screen.getByRole('heading', { name: /General & Interface/i })).toBeDefined();
    expect(screen.getByRole('heading', { name: /Workspace & Editor/i })).toBeDefined();
    expect(screen.getByRole('heading', { name: /Static Analysis & Test Intelligence/i })).toBeDefined();
    expect(screen.getByRole('heading', { name: /AI Diagnosis Streaming/i })).toBeDefined();
    expect(screen.getByRole('heading', { name: /History & Retention/i })).toBeDefined();
    expect(screen.getByRole('heading', { name: /Security & Privacy Boundaries/i })).toBeDefined();

    // Honest backend invariants
    expect(screen.getByText('static_only = true')).toBeDefined();
    expect(screen.getByText(/Server \.env Only/i)).toBeDefined();
    expect(screen.getByText(/JavaScript and TypeScript remain disabled/i)).toBeDefined();

    expect(await screen.findByText(/Online \(/i)).toBeDefined();
  });

  it('validates invalid URLs, tests connection cleanly, handles save/discard/reset and persists across routes', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ status: 'healthy', service: 'EdgeMind' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    renderSettingsApp();

    const urlInput = screen.getByLabelText('EdgeMind API Base URL') as HTMLInputElement;
    const saveButton = screen.getByRole('button', { name: 'Save Settings' }) as HTMLButtonElement;
    expect(saveButton.disabled).toBe(true);

    // Invalid credential URL disables saving and testing
    fireEvent.change(urlInput, { target: { value: 'http://admin:secret@127.0.0.1:8000' } });
    expect(screen.getByText(/Credentials must not be embedded/i)).toBeDefined();
    expect(saveButton.disabled).toBe(true);

    // Discard restores clean URL
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(urlInput.value).toBe('http://127.0.0.1:8000');

    // Valid custom URL + Test Connection
    fireEvent.change(urlInput, { target: { value: 'http://127.0.0.1:8001' } });
    fireEvent.click(screen.getByRole('button', { name: 'Test Connection' }));
    expect(await screen.findByText(/Connected to http:\/\/127\.0\.0\.1:8001/i)).toBeDefined();

    // Update save-required analysis & history preferences
    fireEvent.change(screen.getByLabelText('Default Workspace Filename'), {
      target: { value: 'custom_task.py' },
    });
    fireEvent.change(screen.getByLabelText('PostgreSQL Page Size'), {
      target: { value: '50' },
    });

    expect(screen.getByText('Unsaved Changes')).toBeDefined();
    fireEvent.click(saveButton);

    expect(
      await screen.findByText('Settings saved locally and applied across active EdgeMind modules.')
    ).toBeDefined();
    expect(apiClient.getBaseUrl()).toBe('http://127.0.0.1:8001');

    const stored = JSON.parse(localStorage.getItem(EDGEMIND_SETTINGS_STORAGE_KEY) || '{}');
    expect(stored.defaultFilename).toBe('custom_task.py');
    expect(stored.historyPageSize).toBe(50);

    // Verify History route uses updated page size (limit: 50)
    fireEvent.click(screen.getByText('Go History'));
    await waitFor(() => {
      expect(apiClient.getPersistedReports).toHaveBeenLastCalledWith(
        { skip: 0, limit: 50 },
        expect.any(AbortSignal)
      );
    });
  });

  it('applies immediate editor & interface preferences and propagates to Workspace', async () => {
    renderSettingsApp();

    fireEvent.change(screen.getByLabelText('Editor Font Size'), {
      target: { value: '15' },
    });
    fireEvent.change(screen.getByLabelText('Gutter Line Numbers'), {
      target: { value: 'off' },
    });

    expect(
      await screen.findByText('Immediate preference updated and saved locally.')
    ).toBeDefined();

    fireEvent.click(screen.getByText('Go Workspace'));
    const editor = await screen.findByLabelText(/Python source code editor/i);
    const wrapper = editor.parentElement as HTMLElement;
    expect(wrapper.style.fontSize).toBe('15px');
    // Line-number gutter hidden when editorLineNumbers === 'off'
    expect(wrapper.children.length).toBe(1);
  });

  it('clears in-memory session runs with confirmation, keeps auth tokens redacted, and handles storage failure', async () => {
    vi.spyOn(apiClient, 'analyzeCode').mockResolvedValue({
      file_path: 'helper.py',
      file: 'helper.py',
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
    });
    vi.spyOn(apiClient, 'login').mockResolvedValue({
      access_token: 'super-secret-jwt-value-xyz',
      refresh_token: 'super-secret-refresh-xyz',
      token_type: 'bearer',
      expires_in: 1800,
    });
    vi.spyOn(apiClient, 'logout').mockResolvedValue(undefined);

    renderSettingsApp();

    // Seed session run & in-memory auth session
    fireEvent.click(screen.getByText('Seed Session Run'));
    fireEvent.click(screen.getByText('Seed Auth'));
    await waitFor(() => {
      expect(screen.getByTestId('session-run-count').textContent).toBe('1');
      expect(screen.getByText('sec@edgemind.io')).toBeDefined();
    });

    // Token strings must NEVER appear in the rendered DOM or localStorage
    expect(document.body.textContent).not.toContain('super-secret-jwt-value-xyz');
    expect(document.body.textContent).not.toContain('super-secret-refresh-xyz');
    expect(localStorage.getItem(EDGEMIND_SETTINGS_STORAGE_KEY) ?? '').not.toContain(
      'super-secret-jwt-value-xyz'
    );

    // Clear session runs with confirmation
    fireEvent.click(screen.getByRole('button', { name: 'Clear Session Runs' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Clear' }));
    expect(screen.getByTestId('session-run-count').textContent).toBe('0');

    // Sign out clears active token
    fireEvent.click(screen.getByRole('button', { name: 'Sign Out' }));
    await waitFor(() => {
      expect(apiClient.hasAuthToken()).toBe(false);
    });

    // Simulate localStorage write failure cleanly
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('Storage disabled');
    });
    fireEvent.change(screen.getByLabelText('Editor Font Size'), { target: { value: '16' } });
    expect(await screen.findByText(/Storage disabled/i)).toBeDefined();
  });
});
