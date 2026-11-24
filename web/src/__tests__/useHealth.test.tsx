import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useHealth } from '../hooks/useHealth';
import { apiClient } from '../api/client';

describe('useHealth hook', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('starts in connecting status and transitions to connected on success', async () => {
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'healthy',
      service: 'EdgeMind',
    });

    const { result } = renderHook(() => useHealth({ enabled: true, pollingIntervalMs: 5000 }));

    expect(result.current.status).toBe('connecting');

    await waitFor(() => {
      expect(result.current.status).toBe('connected');
    });

    expect(result.current.data?.status).toBe('healthy');
    expect(result.current.error).toBeNull();
    expect(typeof result.current.durationMs).toBe('number');
  });

  it('transitions to disconnected status when backend is unreachable', async () => {
    vi.spyOn(apiClient, 'getHealth').mockRejectedValue({
      error: 'NetworkError',
      detail: 'Failed to connect to EdgeMind backend',
      status_code: 0,
      request_id: null,
    });

    const { result } = renderHook(() => useHealth({ enabled: true, pollingIntervalMs: 5000 }));

    await waitFor(() => {
      expect(result.current.status).toBe('disconnected');
    });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe('Failed to connect to EdgeMind backend');
  });
});
