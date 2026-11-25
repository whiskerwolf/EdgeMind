import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { AppRoutes } from '../routes/AppRoutes';
import { apiClient } from '../api/client';

describe('AppShell & Routing Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });
    vi.spyOn(apiClient, 'getRecentAnalyses').mockResolvedValue([]);
  });

  it('renders Overview route by default', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppShell>
          <AppRoutes />
        </AppShell>
      </MemoryRouter>
    );

    expect(await screen.findByRole('heading', { level: 2, name: 'Overview' })).toBeDefined();
    expect(within(screen.getByRole('navigation')).getByText('EdgeMind')).toBeDefined();
  });

  it('navigates to Workspace route', async () => {
    render(
      <MemoryRouter initialEntries={['/workspace']}>
        <AppShell>
          <AppRoutes />
        </AppShell>
      </MemoryRouter>
    );

    expect(await screen.findByRole('heading', { level: 2, name: 'Code Workspace' })).toBeDefined();
  });

  it('navigates to Findings route', async () => {
    render(
      <MemoryRouter initialEntries={['/findings']}>
        <AppShell>
          <AppRoutes />
        </AppShell>
      </MemoryRouter>
    );

    expect(await screen.findByRole('heading', { level: 2, name: 'Findings Explorer' })).toBeDefined();
  });

  it('navigates to Settings route', async () => {
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <AppShell>
          <AppRoutes />
        </AppShell>
      </MemoryRouter>
    );

    expect(
      await screen.findByRole('heading', { level: 2, name: /Settings & Configuration/i })
    ).toBeDefined();
  });

  it('renders NotFoundPage on unknown route', async () => {
    render(
      <MemoryRouter initialEntries={['/unknown-path-xyz']}>
        <AppShell>
          <AppRoutes />
        </AppShell>
      </MemoryRouter>
    );

    expect(await screen.findByRole('heading', { name: 'Page Not Found' })).toBeDefined();
    expect(screen.getByText(/404 Error/i)).toBeDefined();
  });
});
