import React, { useState } from 'react';
import { KeyRound, ShieldCheck, X } from 'lucide-react';
import { ApiError } from '../../types/api';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

export interface HistoryAuthCardProps {
  isAuthenticating: boolean;
  authError: ApiError | null;
  onLogin: (email: string, password: string) => Promise<boolean>;
  onGoogleLogin?: () => Promise<boolean>;
  onClose: () => void;
  onClearError: () => void;
}

export const HistoryAuthCard: React.FC<HistoryAuthCardProps> = ({
  isAuthenticating,
  authError,
  onLogin,
  onGoogleLogin,
  onClose,
  onClearError,
}) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return;
    const ok = await onLogin(email, password);
    if (ok) {
      setPassword('');
      onClose();
    }
  };

  const handleGoogleLogin = async () => {
    if (!onGoogleLogin) return;
    if (authError) onClearError();
    const ok = await onGoogleLogin();
    if (ok) {
      onClose();
    }
  };

  return (
    <section
      aria-label="Backend history authentication"
      className="rounded-lg border border-em-border-strong bg-em-card p-4 space-y-3"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <KeyRound className="w-4 h-4 text-em-accent-primary shrink-0" />
          <div>
            <h3 className="text-xs font-semibold text-em-text-primary">
              Sign In for Persisted PostgreSQL History
            </h3>
            <p className="text-[11px] text-em-text-muted mt-0.5">
              Connects to <span className="font-mono">/api/v1/auth/login</span>. Tokens are held
              strictly in memory for this browser tab session (never written to localStorage).
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-em-text-dim hover:text-em-text-primary transition-colors p-1"
          aria-label="Close sign in form"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {authError && (
        <div
          role="alert"
          className="rounded-md border border-em-status-error/30 bg-em-status-error/10 p-2.5 text-xs text-em-status-error font-mono"
        >
          {authError.detail}
        </div>
      )}

      <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-12 gap-2.5 items-end">
        <div className="md:col-span-5 space-y-1">
          <label
            htmlFor="history-auth-email"
            className="block text-[11px] font-mono uppercase text-em-text-dim"
          >
            Email
          </label>
          <Input
            id="history-auth-email"
            type="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              if (authError) onClearError();
            }}
            placeholder="developer@example.com"
            required
          />
        </div>

        <div className="md:col-span-5 space-y-1">
          <label
            htmlFor="history-auth-password"
            className="block text-[11px] font-mono uppercase text-em-text-dim"
          >
            Password
          </label>
          <Input
            id="history-auth-password"
            type="password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              if (authError) onClearError();
            }}
            placeholder="Enter backend account password"
            required
          />
        </div>

        <div className="md:col-span-2 flex items-center gap-2">
          <Button
            type="submit"
            variant="primary"
            size="md"
            isLoading={isAuthenticating}
            disabled={!email.trim() || !password}
            leftIcon={<ShieldCheck className="w-3.5 h-3.5" />}
            className="w-full"
          >
            Sign In
          </Button>
        </div>
      </form>

      {onGoogleLogin && (
        <div className="pt-2 border-t border-em-border-default flex flex-wrap items-center justify-between gap-2">
          <span className="text-[11px] text-em-text-muted">
            Or authenticate with your verified Google account via OAuth 2.0:
          </span>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            isLoading={isAuthenticating}
            disabled={isAuthenticating}
            onClick={() => void handleGoogleLogin()}
          >
            Continue with Google
          </Button>
        </div>
      )}
    </section>
  );
};
