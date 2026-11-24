import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { StatusIndicator } from '../components/ui/StatusIndicator';
import { Input } from '../components/ui/Input';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';

describe('UI Primitives', () => {
  it('renders Button with variants and loading state', () => {
    const { rerender } = render(<Button variant="primary">Run Analysis</Button>);
    expect(screen.getByRole('button', { name: /run analysis/i })).toBeDefined();

    rerender(<Button isLoading>Run Analysis</Button>);
    const btn = screen.getByRole('button');
    expect(btn.hasAttribute('disabled')).toBe(true);
  });

  it('renders Badge with correct text and variant classes', () => {
    render(<Badge variant="error">SyntaxError</Badge>);
    const badge = screen.getByText('SyntaxError');
    expect(badge).toBeDefined();
    expect(badge.className).toContain('text-em-status-error');
  });

  it('renders StatusIndicator with connected dot and label', () => {
    render(<StatusIndicator status="connected" label="API: 8000 (12ms)" />);
    expect(screen.getByRole('status')).toBeDefined();
    expect(screen.getByText('API: 8000 (12ms)')).toBeDefined();
  });

  it('renders Input with error message', () => {
    render(<Input placeholder="snippet.py" error="Invalid filename" />);
    expect(screen.getByPlaceholderText('snippet.py')).toBeDefined();
    expect(screen.getByText('Invalid filename')).toBeDefined();
  });

  it('renders EmptyState with title and description', () => {
    render(<EmptyState title="No Issues" description="All checks passed clean." />);
    expect(screen.getByText('No Issues')).toBeDefined();
    expect(screen.getByText('All checks passed clean.')).toBeDefined();
  });

  it('renders ErrorState with retry callback', () => {
    render(<ErrorState title="Connection Error" message="Backend offline" onRetry={() => {}} />);
    expect(screen.getByRole('alert')).toBeDefined();
    expect(screen.getByText('Connection Error')).toBeDefined();
    expect(screen.getByText('Backend offline')).toBeDefined();
    expect(screen.getByRole('button', { name: /try again/i })).toBeDefined();
  });
});
