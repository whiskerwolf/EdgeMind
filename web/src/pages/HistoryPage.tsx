import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  Code2,
  Database,
  History,
  ShieldAlert,
  WifiOff,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { useAnalysisContext } from '../context/AnalysisContext';
import { useOptionalSettings } from '../context/SettingsContext';
import { ApiError } from '../types/api';
import {
  DEFAULT_HISTORY_FILTERS,
  extractAvailableHistoryStatuses,
  filterAndSortHistory,
  HistoryFilters,
  NormalizedHistoryEntry,
  normalizePersistedReportDoc,
  normalizeSessionJoinItem,
  normalizeSessionRecord,
} from '../utils/historyHelpers';
import { HistoryAuthCard } from '../components/history/HistoryAuthCard';
import { HistoricalReportView } from '../components/history/HistoricalReportView';
import { HistoryBackendStatus, HistoryHeader } from '../components/history/HistoryHeader';
import { HistoryList } from '../components/history/HistoryList';
import { HistoryToolbar } from '../components/history/HistoryToolbar';
import { ReportComparison } from '../components/history/ReportComparison';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';

export const HistoryPage: React.FC = () => {
  const settings = useOptionalSettings();
  const dbLimit = settings.historyPageSize || 20;
  const {
    sessionRuns,
    removeSessionRun,
    authSession,
    isAuthenticating,
    authError,
    loginBackend,
    loginWithGoogle,
    logoutBackend,
    clearAuthError,
  } = useAnalysisContext();

  const [dbStatus, setDbStatus] = useState<HistoryBackendStatus>('loading');
  const [unavailableReason, setUnavailableReason] = useState<
    'auth_required' | 'database_offline' | null
  >(null);
  const [dbError, setDbError] = useState<ApiError | null>(null);
  const [dbRecords, setDbRecords] = useState<NormalizedHistoryEntry[]>([]);
  const [dbTotal, setDbTotal] = useState(0);
  const [dbSkip, setDbSkip] = useState(0);

  const [filters, setFilters] = useState<HistoryFilters>(() => ({
    ...DEFAULT_HISTORY_FILTERS,
    sort: settings.historyDefaultSort,
  }));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hydratedById, setHydratedById] = useState<Record<string, NormalizedHistoryEntry>>({});
  const [hydratingId, setHydratingId] = useState<string | null>(null);
  const [hydrationError, setHydrationError] = useState<ApiError | null>(null);

  const [isCompareMode, setIsCompareMode] = useState(false);
  const [baselineId, setBaselineId] = useState<string | null>(null);
  const [targetId, setTargetId] = useState<string | null>(null);

  const [isAuthDrawerOpen, setIsAuthDrawerOpen] = useState(false);
  const [pendingDeleteEntry, setPendingDeleteEntry] = useState<NormalizedHistoryEntry | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<ApiError | null>(null);

  const fetchControllerRef = useRef<AbortController | null>(null);
  const detailControllerRef = useRef<AbortController | null>(null);
  const deleteControllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  const loadPersistedHistory = useCallback(async (skip: number) => {
    if (fetchControllerRef.current) {
      fetchControllerRef.current.abort();
    }
    const controller = new AbortController();
    fetchControllerRef.current = controller;

    setDbStatus('loading');
    setDbError(null);
    setUnavailableReason(null);

    try {
      const page = await apiClient.getPersistedReports(
        { skip, limit: dbLimit },
        controller.signal
      );
      if (!mountedRef.current) return;

      // Best-effort fetch of SQL-joined session metadata for project titles and DELETED rows
      let recentSessions: Awaited<ReturnType<typeof apiClient.getRecentAnalyses>> = [];
      try {
        recentSessions = await apiClient.getRecentAnalyses(
          Math.min(50, skip + dbLimit),
          controller.signal
        );
      } catch {
        recentSessions = [];
      }
      if (!mountedRef.current) return;

      const joinMap = new Map(recentSessions.map((item) => [item.id, item]));
      const normalizedDocs = (page.items || []).map((doc) =>
        normalizePersistedReportDoc(doc, joinMap.get(doc.analysis_session_id))
      );
      const docIds = new Set(normalizedDocs.map((d) => d.sessionId));

      // Include deleted or metadata-only rows on the first page so audit history remains accurate
      const sessionOnlyRows =
        skip === 0
          ? recentSessions
              .filter((row) => !docIds.has(row.id))
              .map((row) => normalizeSessionJoinItem(row))
          : [];

      setDbRecords([...normalizedDocs, ...sessionOnlyRows]);
      setDbTotal(typeof page.total === 'number' ? page.total : normalizedDocs.length);
      setDbSkip(skip);
      setDbStatus('ready');
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError' || !mountedRef.current) return;

      const apiErr = err as ApiError;
      if (apiErr?.status_code === 0) {
        setDbStatus('disconnected');
        setDbRecords([]);
        return;
      }
      if (apiErr?.status_code === 401 || apiErr?.status_code === 403) {
        setDbStatus('unavailable');
        setUnavailableReason('auth_required');
        setDbRecords([]);
        return;
      }
      if (apiErr?.status_code === 503) {
        setDbStatus('unavailable');
        setUnavailableReason('database_offline');
        setDbRecords([]);
        return;
      }

      setDbStatus('error');
      setDbError(
        apiErr?.detail
          ? apiErr
          : {
              error: 'HistoryFetchError',
              detail: (err as Error)?.message || 'Failed to load persisted analysis history',
              status_code: apiErr?.status_code ?? 500,
              request_id: null,
            }
      );
    }
  }, [dbLimit]);

  useEffect(() => {
    mountedRef.current = true;
    setHydratedById({});
    setHydrationError(null);
    setPendingDeleteEntry(null);
    loadPersistedHistory(0);

    return () => {
      mountedRef.current = false;
      fetchControllerRef.current?.abort();
      detailControllerRef.current?.abort();
      deleteControllerRef.current?.abort();
    };
  }, [loadPersistedHistory, authSession?.accessToken]);

  const sessionEntries = useMemo(
    () => sessionRuns.map((run) => normalizeSessionRecord(run)),
    [sessionRuns]
  );

  const allEntries = useMemo(() => {
    const merged: NormalizedHistoryEntry[] = [];
    const seenIds = new Set<string>();

    for (const item of [...dbRecords, ...sessionEntries]) {
      if (seenIds.has(item.id)) continue;
      seenIds.add(item.id);
      merged.push(hydratedById[item.id] ?? item);
    }
    return merged;
  }, [dbRecords, sessionEntries, hydratedById]);

  const availableStatuses = useMemo(
    () => extractAvailableHistoryStatuses(allEntries),
    [allEntries]
  );

  const filteredEntries = useMemo(
    () => filterAndSortHistory(allEntries, filters),
    [allEntries, filters]
  );

  const selectedEntry = useMemo(
    () => (selectedId ? allEntries.find((item) => item.id === selectedId) ?? null : null),
    [allEntries, selectedId]
  );

  const handleInspect = useCallback(async (entry: NormalizedHistoryEntry) => {
    setSelectedId(entry.id);
    setHydrationError(null);

    const needsHydration =
      entry.source === 'database' &&
      entry.hasDetailedReport &&
      entry.storageStatus !== 'DELETED' &&
      !('analysis_metadata' in ((entry.rawSnapshot as Record<string, unknown>) || {}));

    if (!needsHydration) return;

    detailControllerRef.current?.abort();
    const controller = new AbortController();
    detailControllerRef.current = controller;
    setHydratingId(entry.id);

    try {
      const fullDoc = await apiClient.getReportBySessionId(entry.sessionId, controller.signal);
      if (!mountedRef.current) return;
      const hydrated = normalizePersistedReportDoc(fullDoc);
      setHydratedById((prev) => ({ ...prev, [entry.id]: hydrated }));
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError' || !mountedRef.current) return;
      setHydrationError(
        err && typeof err === 'object' && 'detail' in err
          ? (err as ApiError)
          : {
              error: 'ReportLoadError',
              detail: (err as Error)?.message || 'Unable to load full report document',
              status_code: 500,
              request_id: null,
            }
      );
    } finally {
      if (mountedRef.current) {
        setHydratingId((prev) => (prev === entry.id ? null : prev));
      }
    }
  }, []);

  const handleSelectCompare = useCallback(
    (role: 'A' | 'B', id: string) => {
      if (role === 'A') {
        setBaselineId(id);
      } else {
        setTargetId(id);
      }
      setIsCompareMode(true);
    },
    []
  );

  const handleToggleCompareMode = useCallback(() => {
    setIsCompareMode((prev) => {
      const next = !prev;
      if (next && (!baselineId || !targetId)) {
        const defaultTarget = filteredEntries[0]?.id || allEntries[0]?.id || null;
        const defaultBaseline =
          filteredEntries[1]?.id || allEntries[1]?.id || defaultTarget;
        if (!targetId) setTargetId(defaultTarget);
        if (!baselineId) setBaselineId(defaultBaseline);
      }
      return next;
    });
  }, [baselineId, targetId, filteredEntries, allEntries]);

  const handleSwapCompare = useCallback(() => {
    setBaselineId(targetId);
    setTargetId(baselineId);
  }, [baselineId, targetId]);

  const handleConfirmDelete = useCallback(async () => {
    const entry = pendingDeleteEntry;
    if (!entry) return;

    setDeleteError(null);

    if (entry.source === 'session') {
      removeSessionRun(entry.id);
      setPendingDeleteEntry(null);
      if (selectedId === entry.id) setSelectedId(null);
      if (baselineId === entry.id) setBaselineId(null);
      if (targetId === entry.id) setTargetId(null);
      return;
    }

    deleteControllerRef.current?.abort();
    const controller = new AbortController();
    deleteControllerRef.current = controller;
    setDeletingId(entry.id);

    try {
      await apiClient.deleteAnalysisReport(entry.sessionId, controller.signal);
      if (!mountedRef.current) return;

      setDbRecords((prev) => prev.filter((item) => item.id !== entry.id));
      setDbTotal((prev) => Math.max(0, prev - 1));
      setPendingDeleteEntry(null);
      if (selectedId === entry.id) setSelectedId(null);
      if (baselineId === entry.id) setBaselineId(null);
      if (targetId === entry.id) setTargetId(null);
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError' || !mountedRef.current) return;
      const apiErr = err as ApiError;
      setDeleteError(
        apiErr?.detail
          ? apiErr
          : {
              error: 'DeleteReportError',
              detail: (err as Error)?.message || 'Failed to delete persisted analysis report',
              status_code: apiErr?.status_code ?? 500,
              request_id: null,
            }
      );
    } finally {
      if (mountedRef.current) {
        setDeletingId(null);
      }
    }
  }, [pendingDeleteEntry, removeSessionRun, selectedId, baselineId, targetId]);

  return (
    <div className="space-y-4">
      <HistoryHeader
        totalShown={filteredEntries.length}
        totalRecords={allEntries.length}
        dbStatus={dbStatus}
        unavailableReason={unavailableReason}
        authSessionEmail={authSession?.email ?? null}
        isAuthDrawerOpen={isAuthDrawerOpen}
        onToggleAuthDrawer={() => setIsAuthDrawerOpen((prev) => !prev)}
        onLogout={logoutBackend}
        onRefresh={() => loadPersistedHistory(dbSkip)}
        isRefreshing={dbStatus === 'loading'}
        isCompareMode={isCompareMode}
        onToggleCompareMode={handleToggleCompareMode}
        canCompare={allEntries.length >= 2}
      />

      {isAuthDrawerOpen && !authSession && (
        <HistoryAuthCard
          isAuthenticating={isAuthenticating}
          authError={authError}
          onLogin={loginBackend}
          onGoogleLogin={loginWithGoogle}
          onClose={() => setIsAuthDrawerOpen(false)}
          onClearError={clearAuthError}
        />
      )}

      {/* Backend Persistence Status Banners */}
      {dbStatus === 'disconnected' && (
        <div
          role="status"
          className="rounded-lg border border-em-border-default bg-em-card p-3.5 flex items-start gap-3 text-xs"
        >
          <WifiOff className="w-4 h-4 text-em-text-muted shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold text-em-text-primary">Backend Disconnected</p>
            <p className="text-em-text-muted">
              Cannot reach the EdgeMind API server to query persisted reports. Any runs executed in
              this tab remain inspectable under In-Memory Session history below.
            </p>
          </div>
        </div>
      )}

      {dbStatus === 'unavailable' && unavailableReason === 'auth_required' && (
        <div
          role="status"
          className="rounded-lg border border-em-status-info/30 bg-em-status-info/5 p-3.5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between text-xs"
        >
          <div className="flex items-start gap-3">
            <ShieldAlert className="w-4 h-4 text-em-status-info shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <p className="font-semibold text-em-text-primary">
                Authentication Required for Database History
              </p>
              <p className="text-em-text-muted">
                Database endpoints return HTTP 401 until signed in. Use{' '}
                <span className="font-mono">Sign In for DB</span> to inspect PostgreSQL-stored
                reports, or browse active browser-session runs below.
              </p>
            </div>
          </div>
          {!isAuthDrawerOpen && (
            <Button
              type="button"
              variant="primary"
              size="sm"
              className="shrink-0 whitespace-nowrap"
              onClick={() => setIsAuthDrawerOpen(true)}
            >
              Sign In
            </Button>
          )}
        </div>
      )}

      {dbStatus === 'unavailable' && unavailableReason === 'database_offline' && (
        <div
          role="status"
          className="rounded-lg border border-em-status-warning/30 bg-em-status-warning/5 p-3.5 flex items-start gap-3 text-xs"
        >
          <Database className="w-4 h-4 text-em-status-warning shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <p className="font-semibold text-em-text-primary">
              Stateless Mode — PostgreSQL Persistence Offline
            </p>
            <p className="text-em-text-muted">
              The EdgeMind API is running without <span className="font-mono">DATABASE_URL</span>{' '}
              configured (HTTP 503). Historical runs from this browser session are retained in
              memory until tab reload.
            </p>
          </div>
        </div>
      )}

      {dbStatus === 'error' && dbError && (
        <ErrorState
          title="Failed to Load Database History"
          message={dbError.detail}
          onRetry={() => loadPersistedHistory(dbSkip)}
        />
      )}

      {/* Explicit Delete Confirmation & Error Bar */}
      {pendingDeleteEntry && (
        <div
          role="alertdialog"
          aria-labelledby="confirm-delete-heading"
          className="rounded-lg border border-em-status-error/40 bg-em-status-error/10 p-3.5 space-y-2.5"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-2.5 text-xs">
              <AlertTriangle className="w-4 h-4 text-em-status-error shrink-0 mt-0.5" />
              <div>
                <p id="confirm-delete-heading" className="font-semibold text-em-text-primary">
                  Confirm deletion of &ldquo;{pendingDeleteEntry.title}&rdquo;?
                </p>
                <p className="text-em-text-muted mt-0.5">
                  {pendingDeleteEntry.source === 'database'
                    ? 'This calls DELETE /api/v1/analyses/{id}/report to permanently remove the persisted JSONB report document from PostgreSQL.'
                    : 'This removes the snapshot from in-memory session history without affecting Workspace code.'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setPendingDeleteEntry(null);
                  setDeleteError(null);
                }}
                disabled={Boolean(deletingId)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                size="sm"
                isLoading={deletingId === pendingDeleteEntry.id}
                onClick={handleConfirmDelete}
              >
                Confirm Delete
              </Button>
            </div>
          </div>

          {deleteError && (
            <p className="text-xs font-mono text-em-status-error" role="alert">
              Delete failed: {deleteError.detail}
            </p>
          )}
        </div>
      )}

      <HistoryToolbar
        filters={filters}
        availableStatuses={availableStatuses}
        onChange={setFilters}
        onClear={() => setFilters(DEFAULT_HISTORY_FILTERS)}
      />

      {isCompareMode && (
        <ReportComparison
          entries={allEntries}
          baselineId={baselineId}
          targetId={targetId}
          onChangeBaseline={setBaselineId}
          onChangeTarget={setTargetId}
          onSwap={handleSwapCompare}
          onClose={() => setIsCompareMode(false)}
        />
      )}

      {selectedEntry && (
        <HistoricalReportView
          entry={selectedEntry}
          isHydrating={hydratingId === selectedEntry.id}
          hydrationError={hydrationError}
          onClose={() => {
            setSelectedId(null);
            setHydrationError(null);
          }}
        />
      )}

      {/* History List / Loading / Honest Empty States */}
      {dbStatus === 'loading' && allEntries.length === 0 ? (
        <div className="space-y-2.5" aria-label="Loading history entries">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : allEntries.length === 0 ? (
        <EmptyState
          icon={History}
          title="No Analysis History Recorded Yet"
          description="Run a static code analysis in the Workspace to record snapshots in this session, or sign in to view PostgreSQL-persisted analysis reports."
          action={
            <Link
              to="/workspace"
              className="inline-flex items-center gap-1.5 h-9 px-3.5 text-xs font-semibold rounded-md bg-em-accent-primary text-em-canvas hover:bg-em-accent-hover transition-colors"
            >
              <Code2 className="w-3.5 h-3.5" />
              Analyze Code in Workspace
            </Link>
          }
        />
      ) : filteredEntries.length === 0 ? (
        <EmptyState
          icon={History}
          title="No Matching History Runs"
          description="No history entries match your active search query, status, score, or date filters."
          action={
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setFilters(DEFAULT_HISTORY_FILTERS)}
            >
              Clear Filters
            </Button>
          }
        />
      ) : (
        <HistoryList
          items={filteredEntries}
          selectedId={selectedId}
          baselineId={isCompareMode ? baselineId : null}
          targetId={isCompareMode ? targetId : null}
          onInspect={handleInspect}
          onSelectCompare={handleSelectCompare}
          onRequestDelete={(entry) => {
            setDeleteError(null);
            setPendingDeleteEntry(entry);
          }}
          deletingId={deletingId}
          showDbPagination={dbStatus === 'ready'}
          dbTotal={dbTotal}
          dbSkip={dbSkip}
          dbLimit={dbLimit}
          onPrevPage={() => loadPersistedHistory(Math.max(0, dbSkip - dbLimit))}
          onNextPage={() => loadPersistedHistory(dbSkip + dbLimit)}
        />
      )}
    </div>
  );
};
