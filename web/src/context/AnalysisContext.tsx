import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client';
import { diagnosisClient, DiagnosisStreamError } from '../api/diagnosisClient';
import {
  AnalysisReport,
  AnalyzeCodeRequest,
  ApiError,
  EdgeMindAnalyzeRequest,
  EdgeMindAnalyzeResponse,
  SessionAnalysisRecord,
} from '../types/api';
import { buildDiagnosisRequest, ExplorerFinding } from '../utils/findingsHelpers';
import { SuppliedCodeFile } from '../utils/testIntelligenceHelpers';
import { WorkspaceLanguage } from '../utils/workspaceConfig';
import { useOptionalSettings } from './SettingsContext';

export interface AnalyzedSnapshot {
  code: string;
  filename: string;
  language: WorkspaceLanguage;
}

export interface WorkspaceNavigationTarget {
  findingId: string;
  line: number | null;
  seq: number;
}

export type FindingDiagnosisStatus =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'completed'
  | 'cancelled'
  | 'error';

export interface FindingDiagnosisState {
  status: FindingDiagnosisStatus;
  content: string;
  sessionId: string | null;
  durationMs: number | null;
  errorMessage: string | null;
  retryable: boolean;
}

export const INITIAL_FINDING_DIAGNOSIS_STATE: FindingDiagnosisState = {
  status: 'idle',
  content: '',
  sessionId: null,
  durationMs: null,
  errorMessage: null,
  retryable: true,
};

export interface BackendAuthSession {
  email: string;
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export interface AnalysisContextValue {
  // Latest session report & history (shared across Overview, Workspace, Findings)
  latestReport: AnalysisReport | null;
  latestDurationMs: number | null;
  latestTimestamp: string | null;
  sessionRuns: SessionAnalysisRecord[];
  removeSessionRun: (id: string) => void;
  clearSessionRuns: () => void;
  isAnalyzing: boolean;
  analysisError: ApiError | null;
  runAnalysis: (payload: AnalyzeCodeRequest) => Promise<AnalysisReport | null>;
  clearError: () => void;
  clearAnalysis: () => void;

  // Workspace draft & synchronization state
  workspaceCode: string;
  workspaceFilename: string;
  workspaceLanguage: WorkspaceLanguage;
  analyzedSnapshot: AnalyzedSnapshot | null;
  hasUnanalyzedChanges: boolean;
  setWorkspaceCode: (code: string) => void;
  setWorkspaceFilename: (filename: string) => void;
  setWorkspaceLanguage: (language: WorkspaceLanguage) => void;
  clearWorkspaceResult: () => void;

  // Cross-route Findings <-> Workspace selection & navigation
  selectedFindingId: string | null;
  setSelectedFindingId: (findingId: string | null) => void;
  pendingWorkspaceNavigation: WorkspaceNavigationTarget | null;
  inspectFindingInWorkspace: (findingId: string, line: number | null) => void;
  clearPendingWorkspaceNavigation: () => void;

  // Finding-level AI diagnosis streaming state
  diagnosisByFinding: Record<string, FindingDiagnosisState>;
  startFindingDiagnosis: (finding: ExplorerFinding) => Promise<void>;
  cancelFindingDiagnosis: (findingId: string) => void;

  // EdgeMind Adaptive Test Intelligence & supplied test workspace state
  edgeMindReport: EdgeMindAnalyzeResponse | null;
  isEdgeMindAnalyzing: boolean;
  edgeMindError: ApiError | null;
  runEdgeMindAnalysis: (payload: EdgeMindAnalyzeRequest) => Promise<EdgeMindAnalyzeResponse | null>;
  clearEdgeMindError: () => void;
  suppliedFiles: SuppliedCodeFile[];
  addSuppliedFiles: (files: SuppliedCodeFile[]) => void;
  removeSuppliedFile: (id: string) => void;
  clearSuppliedFiles: () => void;
  baselineTestsText: string;
  setBaselineTestsText: (val: string) => void;
  constraintsText: string;
  setConstraintsText: (val: string) => void;
  openCodeInWorkspace: (options: {
    code?: string;
    filename?: string;
    language?: WorkspaceLanguage;
    line?: number | null;
  }) => void;

  // In-memory optional backend JWT authentication (no browser storage persistence)
  authSession: BackendAuthSession | null;
  isAuthenticating: boolean;
  authError: ApiError | null;
  loginBackend: (email: string, password: string) => Promise<boolean>;
  loginWithGoogle: () => Promise<boolean>;
  logoutBackend: () => Promise<void>;
  clearAuthError: () => void;
}

const AnalysisContext = createContext<AnalysisContextValue | undefined>(undefined);

const MAX_SESSION_RUNS = 25;

export const AnalysisProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const settings = useOptionalSettings();
  const [latestReport, setLatestReport] = useState<AnalysisReport | null>(null);
  const [latestDurationMs, setLatestDurationMs] = useState<number | null>(null);
  const [latestTimestamp, setLatestTimestamp] = useState<string | null>(null);
  const [sessionRuns, setSessionRuns] = useState<SessionAnalysisRecord[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<ApiError | null>(null);

  // Persistent workspace editor draft across route switches
  const [workspaceCode, setWorkspaceCode] = useState<string>('');
  const [workspaceFilename, setWorkspaceFilename] = useState<string>(
    () => settings.defaultFilename || 'snippet.py'
  );
  const [workspaceLanguage, setWorkspaceLanguage] = useState<WorkspaceLanguage>('python');
  const [analyzedSnapshot, setAnalyzedSnapshot] = useState<AnalyzedSnapshot | null>(null);

  // Findings Explorer selection & navigation bridge
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [pendingWorkspaceNavigation, setPendingWorkspaceNavigation] =
    useState<WorkspaceNavigationTarget | null>(null);

  // AI Diagnosis stream state keyed by ExplorerFinding.id for current report
  const [diagnosisByFinding, setDiagnosisByFinding] = useState<
    Record<string, FindingDiagnosisState>
  >({});

  // Test Intelligence state shared across routes
  const [edgeMindReport, setEdgeMindReport] = useState<EdgeMindAnalyzeResponse | null>(null);
  const [isEdgeMindAnalyzing, setIsEdgeMindAnalyzing] = useState(false);
  const [edgeMindError, setEdgeMindError] = useState<ApiError | null>(null);
  const [suppliedFiles, setSuppliedFiles] = useState<SuppliedCodeFile[]>([]);
  const [baselineTestsText, setBaselineTestsText] = useState('');
  const [constraintsText, setConstraintsText] = useState('');

  const abortControllerRef = useRef<AbortController | null>(null);
  const edgeMindAbortRef = useRef<AbortController | null>(null);
  const diagnosisControllersRef = useRef<Map<string, AbortController>>(new Map());
  const diagnosisSeqRef = useRef<Map<string, number>>(new Map());
  // In-memory backend authentication session (for PostgreSQL history endpoints)
  const [authSession, setAuthSession] = useState<BackendAuthSession | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [authError, setAuthError] = useState<ApiError | null>(null);

  const navSeqRef = useRef(0);
  const analysisSeqRef = useRef(0);
  const edgeMindSeqRef = useRef(0);
  const isAnalyzingRef = useRef(false);
  const isEdgeMindAnalyzingRef = useRef(false);
  const authAbortRef = useRef<AbortController | null>(null);
  const prevDefaultFilenameRef = useRef(settings.defaultFilename || 'snippet.py');
  const mountedRef = useRef(true);

  const abortAllDiagnoses = useCallback(() => {
    diagnosisControllersRef.current.forEach((ctrl) => ctrl.abort());
    diagnosisControllersRef.current.clear();
  }, []);

  const abortActiveAnalyses = useCallback(() => {
    analysisSeqRef.current += 1;
    edgeMindSeqRef.current += 1;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (edgeMindAbortRef.current) {
      edgeMindAbortRef.current.abort();
      edgeMindAbortRef.current = null;
    }
    isAnalyzingRef.current = false;
    isEdgeMindAnalyzingRef.current = false;
    setIsAnalyzing(false);
    setIsEdgeMindAnalyzing(false);
  }, []);

  // Propagate default filename preference to an untouched empty Workspace
  useEffect(() => {
    const nextDefault = settings.defaultFilename || 'snippet.py';
    if (
      !workspaceCode.trim() &&
      !latestReport &&
      workspaceFilename === prevDefaultFilenameRef.current &&
      workspaceFilename !== nextDefault
    ) {
      setWorkspaceFilename(nextDefault);
    }
    prevDefaultFilenameRef.current = nextDefault;
  }, [settings.defaultFilename, workspaceCode, latestReport, workspaceFilename]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (edgeMindAbortRef.current) {
        edgeMindAbortRef.current.abort();
      }
      if (authAbortRef.current) {
        authAbortRef.current.abort();
      }
      diagnosisControllersRef.current.forEach((ctrl) => ctrl.abort());
      diagnosisControllersRef.current.clear();
    };
  }, []);

  const runAnalysis = useCallback(
    async (payload: AnalyzeCodeRequest): Promise<AnalysisReport | null> => {
      // Prevent duplicate concurrent requests while an analysis is already in-flight
      if (isAnalyzingRef.current) {
        return null;
      }

      const runSeq = ++analysisSeqRef.current;
      const controller = new AbortController();
      abortControllerRef.current = controller;
      isAnalyzingRef.current = true;

      setIsAnalyzing(true);
      setAnalysisError(null);
      const start = performance.now();

      try {
        const timeoutOverride =
          settings.analysisTimeoutMs !== 15000 ? settings.analysisTimeoutMs : undefined;
        const report = await apiClient.analyzeCode(payload, controller.signal, timeoutOverride);
        if (!mountedRef.current || analysisSeqRef.current !== runSeq || controller.signal.aborted) {
          return null;
        }

        const durationMs = Math.max(1, Math.round(performance.now() - start));
        const executedAt = new Date().toISOString();
        const effectiveFilename =
          report.file || payload.filename || settings.defaultFilename || 'snippet.py';

        abortAllDiagnoses();
        setDiagnosisByFinding({});
        setSelectedFindingId(null);

        setLatestReport(report);
        setLatestDurationMs(durationMs);
        setLatestTimestamp(executedAt);
        setAnalyzedSnapshot({
          code: payload.code,
          filename: effectiveFilename,
          language: 'python',
        });

        const clonedReport = JSON.parse(JSON.stringify(report)) as AnalysisReport;

        const record: SessionAnalysisRecord = {
          id: `session-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          filename: effectiveFilename,
          score: clonedReport.score,
          overall_status: clonedReport.overall_status,
          total_errors: clonedReport.total_errors,
          total_warnings: clonedReport.total_warnings,
          durationMs,
          executedAt,
          report: clonedReport,
        };

        setSessionRuns((prev) =>
          [record, ...prev].slice(0, settings.sessionHistoryLimit || MAX_SESSION_RUNS)
        );
        return report;
      } catch (err: unknown) {
        if (
          (err as Error)?.name === 'AbortError' ||
          !mountedRef.current ||
          analysisSeqRef.current !== runSeq
        ) {
          return null;
        }

        const normalized: ApiError =
          typeof err === 'object' && err !== null && 'error' in err && 'detail' in err
            ? (err as ApiError)
            : {
                error: 'AnalysisError',
                detail: (err as Error)?.message || 'Failed to execute static analysis',
                status_code: 0,
                request_id: null,
              };

        setAnalysisError(normalized);
        return null;
      } finally {
        if (analysisSeqRef.current === runSeq) {
          isAnalyzingRef.current = false;
          if (abortControllerRef.current === controller) {
            abortControllerRef.current = null;
          }
          if (mountedRef.current) {
            setIsAnalyzing(false);
          }
        }
      }
    },
    [abortAllDiagnoses, settings.analysisTimeoutMs, settings.defaultFilename, settings.sessionHistoryLimit]
  );

  const clearError = useCallback(() => {
    setAnalysisError(null);
  }, []);

  const clearWorkspaceResult = useCallback(() => {
    abortActiveAnalyses();
    abortAllDiagnoses();
    setDiagnosisByFinding({});
    setSelectedFindingId(null);
    setPendingWorkspaceNavigation(null);
    setLatestReport(null);
    setLatestDurationMs(null);
    setLatestTimestamp(null);
    setAnalyzedSnapshot(null);
    setAnalysisError(null);
    setEdgeMindReport(null);
    setEdgeMindError(null);
  }, [abortActiveAnalyses, abortAllDiagnoses]);

  const removeSessionRun = useCallback((id: string) => {
    setSessionRuns((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const clearSessionRuns = useCallback(() => {
    setSessionRuns([]);
  }, []);

  const clearAuthError = useCallback(() => {
    setAuthError(null);
  }, []);

  const loginBackend = useCallback(async (email: string, password: string): Promise<boolean> => {
    if (authAbortRef.current) {
      authAbortRef.current.abort();
    }
    const controller = new AbortController();
    authAbortRef.current = controller;
    setIsAuthenticating(true);
    setAuthError(null);

    try {
      const tokens = await apiClient.login(
        { email: email.trim(), password },
        controller.signal
      );
      if (!mountedRef.current) return false;

      apiClient.setAuthToken?.(tokens.access_token);
      setAuthSession({
        email: email.trim(),
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        expiresIn: tokens.expires_in,
      });
      return true;
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError' || !mountedRef.current) {
        return false;
      }
      const normalized: ApiError =
        typeof err === 'object' && err !== null && 'error' in err && 'detail' in err
          ? (err as ApiError)
          : {
              error: 'AuthenticationError',
              detail: (err as Error)?.message || 'Failed to authenticate with EdgeMind API',
              status_code: 401,
              request_id: null,
            };
      setAuthError(normalized);
      return false;
    } finally {
      if (mountedRef.current) {
        setIsAuthenticating(false);
      }
    }
  }, []);

  const loginWithGoogle = useCallback(async (): Promise<boolean> => {
    if (authAbortRef.current) {
      authAbortRef.current.abort();
    }
    const controller = new AbortController();
    authAbortRef.current = controller;
    setIsAuthenticating(true);
    setAuthError(null);

    try {
      const origin = typeof window !== 'undefined' ? window.location.origin : undefined;
      const { authorization_url } = await apiClient.getGoogleOAuthAuthorizationUrl(
        origin,
        controller.signal
      );
      if (!mountedRef.current) return false;

      const expectedSenderOrigin = (() => {
        try {
          const base = apiClient.getBaseUrl();
          return base ? new URL(base).origin : window.location.origin;
        } catch {
          return window.location.origin;
        }
      })();

      const popup = window.open(
        authorization_url,
        'edgemind-google-oauth',
        'width=520,height=640,menubar=no,toolbar=no,status=no'
      );
      if (!popup) {
        setAuthError({
          error: 'OAuthPopupBlocked',
          detail: 'Popup window was blocked. Allow popups for this site and try again.',
          status_code: 400,
          request_id: null,
        });
        return false;
      }

      return await new Promise<boolean>((resolve) => {
        let settled = false;
        let closePoll: number | null = null;
        let abortHandler: (() => void) | null = null;

        const finish = (ok: boolean, err?: ApiError) => {
          if (settled) return;
          settled = true;
          window.removeEventListener('message', onMessage);
          if (closePoll !== null) window.clearInterval(closePoll);
          if (abortHandler) controller.signal.removeEventListener('abort', abortHandler);
          if (err && mountedRef.current) {
            setAuthError(err);
          }
          resolve(ok);
        };

        const onMessage = (event: MessageEvent) => {
          if (event.origin !== expectedSenderOrigin) return;
          const payload = event.data as
            | {
                type?: string;
                tokens?: { access_token: string; refresh_token: string; expires_in: number };
                email?: string;
                error?: string;
              }
            | undefined;
          if (!payload || typeof payload !== 'object') return;

          if (payload.type === 'edgemind:oauth-callback' && payload.tokens?.access_token) {
            apiClient.setAuthToken?.(payload.tokens.access_token);
            setAuthSession({
              email: payload.email || 'Google Account',
              accessToken: payload.tokens.access_token,
              refreshToken: payload.tokens.refresh_token,
              expiresIn: payload.tokens.expires_in,
            });
            try {
              popup.close();
            } catch {
              // ignore cross-window close failure
            }
            finish(true);
          } else if (payload.type === 'edgemind:oauth-error') {
            finish(false, {
              error: 'OAuthError',
              detail: payload.error || 'Google authentication failed.',
              status_code: 401,
              request_id: null,
            });
          }
        };

        abortHandler = () => finish(false);
        controller.signal.addEventListener('abort', abortHandler);
        window.addEventListener('message', onMessage);
        closePoll = window.setInterval(() => {
          if (popup.closed) {
            finish(false, {
              error: 'OAuthCancelled',
              detail: 'Google sign-in was cancelled before completion.',
              status_code: 400,
              request_id: null,
            });
          }
        }, 250);
      });
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError' || !mountedRef.current) {
        return false;
      }
      const normalized: ApiError =
        typeof err === 'object' && err !== null && 'error' in err && 'detail' in err
          ? (err as ApiError)
          : {
              error: 'OAuthError',
              detail: (err as Error)?.message || 'Failed to initiate Google sign-in.',
              status_code: 503,
              request_id: null,
            };
      setAuthError(normalized);
      return false;
    } finally {
      if (mountedRef.current) {
        setIsAuthenticating(false);
      }
    }
  }, []);

  const logoutBackend = useCallback(async (): Promise<void> => {
    const refreshToken = authSession?.refreshToken;
    apiClient.setAuthToken?.(null);
    setAuthSession(null);
    setAuthError(null);

    if (refreshToken) {
      try {
        await apiClient.logout(refreshToken);
      } catch {
        // Best-effort revocation; local session token is already cleared
      }
    }
  }, [authSession?.refreshToken]);

  const clearAnalysis = useCallback(() => {
    abortActiveAnalyses();
    abortAllDiagnoses();
    setDiagnosisByFinding({});
    setSelectedFindingId(null);
    setPendingWorkspaceNavigation(null);
    setLatestReport(null);
    setLatestDurationMs(null);
    setLatestTimestamp(null);
    setAnalyzedSnapshot(null);
    setSessionRuns([]);
    setAnalysisError(null);
    setEdgeMindReport(null);
    setEdgeMindError(null);
  }, [abortActiveAnalyses, abortAllDiagnoses]);

  const runEdgeMindAnalysis = useCallback(
    async (payload: EdgeMindAnalyzeRequest): Promise<EdgeMindAnalyzeResponse | null> => {
      if (isEdgeMindAnalyzingRef.current) {
        return null;
      }

      const runSeq = ++edgeMindSeqRef.current;
      const controller = new AbortController();
      edgeMindAbortRef.current = controller;
      isEdgeMindAnalyzingRef.current = true;
      setIsEdgeMindAnalyzing(true);
      setEdgeMindError(null);
      const start = performance.now();

      try {
        const timeoutOverride =
          settings.analysisTimeoutMs !== 15000 ? settings.analysisTimeoutMs : undefined;
        const result = await apiClient.analyzeEdgeMind(payload, controller.signal, timeoutOverride);
        if (!mountedRef.current || edgeMindSeqRef.current !== runSeq || controller.signal.aborted) {
          return null;
        }

        setEdgeMindReport(result);

        if (result.code_analysis && (!latestReport || analyzedSnapshot?.code === payload.code)) {
          const durationMs = Math.max(1, Math.round(performance.now() - start));
          setLatestReport(result.code_analysis);
          setLatestDurationMs(durationMs);
          setLatestTimestamp(new Date().toISOString());
          setAnalyzedSnapshot({
            code: payload.code,
            filename: result.code_analysis.file || payload.filename || 'snippet.py',
            language: 'python',
          });
        }

        return result;
      } catch (err: unknown) {
        if (
          (err as Error)?.name === 'AbortError' ||
          !mountedRef.current ||
          edgeMindSeqRef.current !== runSeq
        ) {
          return null;
        }
        const normalized: ApiError =
          typeof err === 'object' && err !== null && 'error' in err && 'detail' in err
            ? (err as ApiError)
            : {
                error: 'TestIntelligenceError',
                detail:
                  (err as Error)?.message || 'Failed to execute EdgeMind adaptive test analysis',
                status_code: 0,
                request_id: null,
              };
        setEdgeMindError(normalized);
        return null;
      } finally {
        if (edgeMindSeqRef.current === runSeq) {
          isEdgeMindAnalyzingRef.current = false;
          if (edgeMindAbortRef.current === controller) {
            edgeMindAbortRef.current = null;
          }
          if (mountedRef.current) {
            setIsEdgeMindAnalyzing(false);
          }
        }
      }
    },
    [latestReport, analyzedSnapshot, settings.analysisTimeoutMs]
  );

  const clearEdgeMindError = useCallback(() => {
    setEdgeMindError(null);
  }, []);

  const addSuppliedFiles = useCallback((incoming: SuppliedCodeFile[]) => {
    setSuppliedFiles((prev) => {
      const next = [...prev];
      for (const file of incoming) {
        const cleanName = file.filename.split(/[\\/]/).pop() || file.filename;
        const normalized = { ...file, filename: cleanName };
        const existingIdx = next.findIndex(
          (item) => item.filename.toLowerCase() === cleanName.toLowerCase()
        );
        if (existingIdx >= 0) {
          next[existingIdx] = normalized;
        } else {
          next.push(normalized);
        }
      }
      return next;
    });
  }, []);

  const removeSuppliedFile = useCallback((id: string) => {
    setSuppliedFiles((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const clearSuppliedFiles = useCallback(() => {
    setSuppliedFiles([]);
  }, []);

  const openCodeInWorkspace = useCallback(
    (options: {
      code?: string;
      filename?: string;
      language?: WorkspaceLanguage;
      line?: number | null;
    }) => {
      if (options.code !== undefined) {
        setWorkspaceCode(options.code);
      }
      if (options.filename !== undefined) {
        setWorkspaceFilename(options.filename);
      }
      if (options.language !== undefined) {
        setWorkspaceLanguage(options.language);
      }
      if (options.line !== undefined && options.line !== null && options.line >= 1) {
        navSeqRef.current += 1;
        setPendingWorkspaceNavigation({
          findingId: 'ti-nav',
          line: options.line,
          seq: navSeqRef.current,
        });
      }
    },
    []
  );

  const inspectFindingInWorkspace = useCallback(
    (findingId: string, line: number | null) => {
      setSelectedFindingId(findingId);

      // Preserve existing Workspace contents if already populated; seed from analyzedSnapshot
      // only when Workspace is currently blank (e.g., analysis initiated from OverviewPage).
      if (!workspaceCode.trim() && analyzedSnapshot?.code) {
        setWorkspaceCode(analyzedSnapshot.code);
        setWorkspaceFilename(analyzedSnapshot.filename);
        setWorkspaceLanguage(analyzedSnapshot.language);
      }

      navSeqRef.current += 1;
      setPendingWorkspaceNavigation({
        findingId,
        line,
        seq: navSeqRef.current,
      });
    },
    [workspaceCode, analyzedSnapshot]
  );

  const clearPendingWorkspaceNavigation = useCallback(() => {
    setPendingWorkspaceNavigation(null);
  }, []);

  const cancelFindingDiagnosis = useCallback((findingId: string) => {
    const existingController = diagnosisControllersRef.current.get(findingId);
    if (existingController) {
      diagnosisControllersRef.current.delete(findingId);
      existingController.abort();
    }

    setDiagnosisByFinding((prev) => {
      const current = prev[findingId];
      if (!current || (current.status !== 'connecting' && current.status !== 'streaming')) {
        return prev;
      }
      return {
        ...prev,
        [findingId]: {
          ...current,
          status: 'cancelled',
          errorMessage: null,
        },
      };
    });
  }, []);

  const startFindingDiagnosis = useCallback(
    async (finding: ExplorerFinding): Promise<void> => {
      const sourceForDiagnosis = analyzedSnapshot?.code ?? null;
      const langForDiagnosis = analyzedSnapshot?.language ?? workspaceLanguage;
      const prepared = buildDiagnosisRequest(
        finding,
        sourceForDiagnosis,
        langForDiagnosis,
        settings.diagnosisContextRadius
      );

      if (!prepared.request) {
        setDiagnosisByFinding((prev) => ({
          ...prev,
          [finding.id]: {
            status: 'error',
            content: prev[finding.id]?.content ?? '',
            sessionId: null,
            durationMs: null,
            errorMessage:
              prepared.unavailableReason ||
              'Unable to prepare bounded source context for AI diagnosis.',
            retryable: false,
          },
        }));
        return;
      }

      // Abort any existing in-flight stream for this finding before restarting
      const prevController = diagnosisControllersRef.current.get(finding.id);
      if (prevController) {
        prevController.abort();
        diagnosisControllersRef.current.delete(finding.id);
      }

      const nextSeq = (diagnosisSeqRef.current.get(finding.id) ?? 0) + 1;
      diagnosisSeqRef.current.set(finding.id, nextSeq);

      const controller = new AbortController();
      diagnosisControllersRef.current.set(finding.id, controller);

      const isCurrentRun = () =>
        mountedRef.current && diagnosisSeqRef.current.get(finding.id) === nextSeq;

      setDiagnosisByFinding((prev) => ({
        ...prev,
        [finding.id]: {
          status: 'connecting',
          content: '',
          sessionId: null,
          durationMs: null,
          errorMessage: null,
          retryable: true,
        },
      }));

      try {
        for await (const event of diagnosisClient.streamDiagnosis(prepared.request, {
          signal: controller.signal,
          timeoutMs: settings.diagnosisTimeoutMs,
        })) {
          if (!isCurrentRun() || controller.signal.aborted) {
            return;
          }

          if (event.event === 'diagnosis_started') {
            setDiagnosisByFinding((prev) => ({
              ...prev,
              [finding.id]: {
                ...(prev[finding.id] ?? INITIAL_FINDING_DIAGNOSIS_STATE),
                status: 'streaming',
                sessionId: event.session_id,
              },
            }));
          } else if (event.event === 'response_chunk') {
            setDiagnosisByFinding((prev) => {
              const current = prev[finding.id] ?? INITIAL_FINDING_DIAGNOSIS_STATE;
              return {
                ...prev,
                [finding.id]: {
                  ...current,
                  status: 'streaming',
                  content: current.content + event.chunk,
                },
              };
            });
          } else if (event.event === 'completed') {
            setDiagnosisByFinding((prev) => {
              const current = prev[finding.id] ?? INITIAL_FINDING_DIAGNOSIS_STATE;
              return {
                ...prev,
                [finding.id]: {
                  ...current,
                  status: 'completed',
                  durationMs: event.duration_ms,
                },
              };
            });
            return;
          } else if (event.event === 'error') {
            setDiagnosisByFinding((prev) => {
              const current = prev[finding.id] ?? INITIAL_FINDING_DIAGNOSIS_STATE;
              return {
                ...prev,
                [finding.id]: {
                  ...current,
                  status: 'error',
                  errorMessage: event.message,
                  retryable: event.retryable,
                },
              };
            });
            return;
          }
        }
      } catch (err: unknown) {
        if (!isCurrentRun() || controller.signal.aborted) {
          return;
        }
        const streamErr =
          err instanceof DiagnosisStreamError
            ? err
            : new DiagnosisStreamError(
                err instanceof Error ? err.message : 'Unexpected diagnosis streaming failure.'
              );
        setDiagnosisByFinding((prev) => {
          const current = prev[finding.id] ?? INITIAL_FINDING_DIAGNOSIS_STATE;
          return {
            ...prev,
            [finding.id]: {
              ...current,
              status: 'error',
              errorMessage: streamErr.message,
              retryable: streamErr.retryable,
            },
          };
        });
      } finally {
        if (diagnosisControllersRef.current.get(finding.id) === controller) {
          diagnosisControllersRef.current.delete(finding.id);
        }
      }
    },
    [analyzedSnapshot, workspaceLanguage, settings.diagnosisContextRadius, settings.diagnosisTimeoutMs]
  );

  const hasUnanalyzedChanges = Boolean(
    latestReport &&
      analyzedSnapshot &&
      (analyzedSnapshot.code !== workspaceCode ||
        analyzedSnapshot.filename !== (workspaceFilename.trim() || 'snippet.py'))
  );

  return (
    <AnalysisContext.Provider
      value={{
        latestReport,
        latestDurationMs,
        latestTimestamp,
        sessionRuns,
        removeSessionRun,
        clearSessionRuns,
        isAnalyzing,
        analysisError,
        runAnalysis,
        clearError,
        clearAnalysis,
        workspaceCode,
        workspaceFilename,
        workspaceLanguage,
        analyzedSnapshot,
        hasUnanalyzedChanges,
        setWorkspaceCode,
        setWorkspaceFilename,
        setWorkspaceLanguage,
        clearWorkspaceResult,
        selectedFindingId,
        setSelectedFindingId,
        pendingWorkspaceNavigation,
        inspectFindingInWorkspace,
        clearPendingWorkspaceNavigation,
        diagnosisByFinding,
        startFindingDiagnosis,
        cancelFindingDiagnosis,
        edgeMindReport,
        isEdgeMindAnalyzing,
        edgeMindError,
        runEdgeMindAnalysis,
        clearEdgeMindError,
        suppliedFiles,
        addSuppliedFiles,
        removeSuppliedFile,
        clearSuppliedFiles,
        baselineTestsText,
        setBaselineTestsText,
        constraintsText,
        setConstraintsText,
        openCodeInWorkspace,
        authSession,
        isAuthenticating,
        authError,
        loginBackend,
        loginWithGoogle,
        logoutBackend,
        clearAuthError,
      }}
    >
      {children}
    </AnalysisContext.Provider>
  );
};

export function useAnalysisContext(): AnalysisContextValue {
  const context = useContext(AnalysisContext);
  if (!context) {
    throw new Error('useAnalysisContext must be used within an AnalysisProvider');
  }
  return context;
}
