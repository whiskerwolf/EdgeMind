import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SettingsProvider } from '../context/SettingsContext';
import { HealthProvider } from '../context/HealthContext';
import { AnalysisProvider } from '../context/AnalysisContext';
import { HistoryPage } from '../pages/HistoryPage';

const mockEmptyHistory = {
  items: [],
  total: 0,
  skip: 0,
  limit: 20,
  has_more: false,
};

describe('Frontend Google OAuth Integration', () => {
  const originalFetch = globalThis.fetch;
  const originalOpen = window.open;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    window.open = originalOpen;
  });

  function renderHistory() {
    return render(
      <MemoryRouter initialEntries={['/history']}>
        <SettingsProvider>
          <HealthProvider>
            <AnalysisProvider>
              <HistoryPage />
            </AnalysisProvider>
          </HealthProvider>
        </SettingsProvider>
      </MemoryRouter>
    );
  }

  it('displays backend error when Google OAuth is unconfigured (HTTP 503)', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/health')) {
        return new Response(JSON.stringify({ status: 'healthy', service: 'EdgeMind' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/analyses/report')) {
        return new Response(
          JSON.stringify({ error: 'Unauthorized', detail: 'Not authenticated' }),
          { status: 401, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url.includes('/api/v1/auth/oauth/google')) {
        return new Response(
          JSON.stringify({ error: 'Service Unavailable', detail: 'Google OAuth is not configured.' }),
          { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response('{}', { status: 404 });
    });

    renderHistory();

    const signInBtn = await screen.findByRole('button', { name: /sign in/i });
    fireEvent.click(signInBtn);

    const googleBtn = await screen.findByRole('button', { name: /continue with google/i });
    fireEvent.click(googleBtn);

    const alertText = await screen.findByText(/not configured/i);
    expect(alertText).toBeTruthy();
  });

  it('handles popup cancellation cleanly when user closes the OAuth window', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/health')) {
        return new Response(JSON.stringify({ status: 'healthy', service: 'EdgeMind' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/analyses/report')) {
        return new Response(JSON.stringify({ error: 'Unauthorized', detail: 'Sign in required' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/auth/oauth/google')) {
        return new Response(
          JSON.stringify({
            provider: 'google',
            authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?state=cancelstate',
            expires_in: 600,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response('{}', { status: 404 });
    });

    const closedPopup = { closed: true, close: vi.fn() } as unknown as Window;
    window.open = vi.fn().mockReturnValue(closedPopup);

    renderHistory();

    const signInBtn = await screen.findByRole('button', { name: /sign in/i });
    fireEvent.click(signInBtn);
    const googleBtn = await screen.findByRole('button', { name: /continue with google/i });
    fireEvent.click(googleBtn);

    const cancelNotice = await screen.findByText(/cancelled before completion/i);
    expect(cancelNotice).toBeTruthy();
  });

  it('completes Google OAuth popup flow on valid origin postMessage and ignores untrusted origins', async () => {
    let authenticated = false;
    globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/health')) {
        return new Response(JSON.stringify({ status: 'healthy', service: 'EdgeMind' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/analyses/report')) {
        const authHeader = (init?.headers as Record<string, string> | undefined)?.Authorization;
        if (!authenticated && !authHeader) {
          return new Response(JSON.stringify({ error: 'Unauthorized', detail: 'Sign in required' }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify(mockEmptyHistory), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/auth/oauth/google')) {
        return new Response(
          JSON.stringify({
            provider: 'google',
            authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?state=teststate',
            expires_in: 600,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response('{}', { status: 404 });
    });

    const mockPopup = { closed: false, close: vi.fn() } as unknown as Window;
    window.open = vi.fn().mockReturnValue(mockPopup);

    renderHistory();

    const signInBtn = await screen.findByRole('button', { name: /sign in/i });
    fireEvent.click(signInBtn);
    const googleBtn = await screen.findByRole('button', { name: /continue with google/i });
    fireEvent.click(googleBtn);

    await waitFor(() => {
      expect(window.open).toHaveBeenCalled();
    });

    // 1. Forged message from untrusted origin must be ignored
    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'https://evil.example.com',
        data: {
          type: 'edgemind:oauth-callback',
          tokens: { access_token: 'evil-tok', refresh_token: 'evil-ref', expires_in: 900 },
          email: 'evil@example.com',
        },
      })
    );
    expect(screen.queryByRole('button', { name: /sign out/i })).toBeNull();

    // 2. Valid postMessage from expected backend origin unlocks session in memory
    authenticated = true;
    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'http://127.0.0.1:8000',
        data: {
          type: 'edgemind:oauth-callback',
          tokens: { access_token: 'oauth-jwt-access', refresh_token: 'oauth-jwt-refresh', expires_in: 900 },
          email: 'oauth@example.com',
        },
      })
    );

    expect(await screen.findByRole('button', { name: /sign out/i })).toBeTruthy();
  });
});
