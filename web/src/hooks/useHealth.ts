import { useState, useEffect, useRef, useCallback } from 'react';
import { apiClient } from '../api/client';
import { HealthState, HealthResponse, ApiError } from '../types/api';

export interface UseHealthOptions {
  pollingIntervalMs?: number;
  enabled?: boolean;
}

export function useHealth({
  pollingIntervalMs = 10000,
  enabled = true,
}: UseHealthOptions = {}): HealthState & { checkHealth: () => Promise<void> } {
  const [state, setState] = useState<HealthState>({
    status: 'connecting',
    data: null,
    error: null,
    durationMs: null,
    lastChecked: null,
  });

  const abortControllerRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const checkHealth = useCallback(async () => {
    // Abort any in-flight check
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const startTime = performance.now();

    try {
      const data: HealthResponse = await apiClient.getHealth(controller.signal, 4000);
      const durationMs = Math.round(performance.now() - startTime);

      // Verify that data is genuinely the EdgeMind health response
      if (data && data.status === 'healthy') {
        setState({
          status: 'connected',
          data,
          error: null,
          durationMs,
          lastChecked: new Date(),
        });
      } else {
        setState({
          status: 'error',
          data: null,
          error: 'Invalid response from backend health check',
          durationMs,
          lastChecked: new Date(),
        });
      }
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError') {
        return; // Ignored aborted request
      }

      const durationMs = Math.round(performance.now() - startTime);
      const apiErr = err as ApiError;

      setState({
        status: apiErr.status_code === 0 ? 'disconnected' : 'error',
        data: null,
        error: apiErr.detail || apiErr.error || 'Failed to reach backend',
        durationMs,
        lastChecked: new Date(),
      });
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;

    let isMounted = true;

    const executeCycle = async () => {
      if (!isMounted) return;
      await checkHealth();

      if (!isMounted) return;
      timerRef.current = setTimeout(executeCycle, pollingIntervalMs);
    };

    executeCycle();

    return () => {
      isMounted = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [enabled, pollingIntervalMs, checkHealth]);

  return {
    ...state,
    checkHealth,
  };
}
