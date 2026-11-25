import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client';
import { AnalysisSessionItem, ApiError, HealthStatus } from '../types/api';

export type OverviewHistoryStatus =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'empty'
  | 'unavailable'
  | 'disconnected'
  | 'error';

export type UnavailableReason =
  | 'auth_required'
  | 'database_offline'
  | 'endpoint_unavailable'
  | null;

export interface OverviewHistoryState {
  status: OverviewHistoryStatus;
  items: AnalysisSessionItem[];
  unavailableReason: UnavailableReason;
  message: string | null;
  error: ApiError | null;
  lastFetched: Date | null;
  refresh: () => Promise<void>;
}

export function useOverviewHistory(
  healthStatus: HealthStatus,
  limit: number = 5
): OverviewHistoryState {
  const [status, setStatus] = useState<OverviewHistoryStatus>('idle');
  const [items, setItems] = useState<AnalysisSessionItem[]>([]);
  const [unavailableReason, setUnavailableReason] = useState<UnavailableReason>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const hasFetchedForConnectionRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, []);

  const fetchHistory = useCallback(async () => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus('loading');
    setError(null);
    setUnavailableReason(null);
    setMessage(null);

    try {
      const data = await apiClient.getRecentAnalyses(limit, controller.signal);
      if (!mountedRef.current) return;

      const list = Array.isArray(data) ? data : [];
      setLastFetched(new Date());

      if (list.length === 0) {
        setItems([]);
        setStatus('empty');
        setMessage('No persisted analysis sessions recorded in the database yet.');
      } else {
        setItems(list);
        setStatus('ready');
      }
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError' || !mountedRef.current) {
        return;
      }

      const apiErr = err as ApiError;
      const code = apiErr.status_code;

      if (code === 401 || code === 403) {
        setItems([]);
        setStatus('unavailable');
        setUnavailableReason('auth_required');
        setMessage(
          'Persisted database history requires user authentication. Anonymous static analysis results from this browser session remain visible.'
        );
        return;
      }

      if (code === 503) {
        setItems([]);
        setStatus('unavailable');
        setUnavailableReason('database_offline');
        setMessage(
          'PostgreSQL persistence is not configured or currently unreachable on the backend.'
        );
        return;
      }

      if (code === 404 || code === 405) {
        setItems([]);
        setStatus('unavailable');
        setUnavailableReason('endpoint_unavailable');
        setMessage('Persisted analysis history endpoint is not enabled on this server.');
        return;
      }

      if (code === 0) {
        setItems([]);
        setStatus('disconnected');
        setMessage('Backend disconnected while loading recent analysis history.');
        return;
      }

      setItems([]);
      setStatus('error');
      setError(apiErr);
      setMessage(apiErr.detail || apiErr.error || 'Failed to fetch recent analyses.');
    }
  }, [limit]);

  useEffect(() => {
    if (healthStatus === 'connected') {
      if (!hasFetchedForConnectionRef.current) {
        hasFetchedForConnectionRef.current = true;
        fetchHistory();
      }
      return;
    }

    hasFetchedForConnectionRef.current = false;

    if (healthStatus === 'disconnected') {
      if (abortRef.current) {
        abortRef.current.abort();
      }
      setStatus('disconnected');
      setError(null);
      setUnavailableReason(null);
      setMessage('EdgeMind backend is unreachable. Reconnect to query persisted history.');
      return;
    }

    if (healthStatus === 'error') {
      setStatus('error');
      setMessage('Backend health check returned an invalid status.');
      return;
    }

    if (healthStatus === 'connecting' && status === 'idle') {
      setStatus('loading');
    }
  }, [healthStatus, fetchHistory, status]);

  return {
    status,
    items,
    unavailableReason,
    message,
    error,
    lastFetched,
    refresh: fetchHistory,
  };
}
