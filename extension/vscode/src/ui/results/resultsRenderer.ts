import { AnalysisResultsViewModel, FindingItem } from './resultsProvider';

/**
 * Escapes characters with special meaning in HTML to prevent XSS.
 */
export function escapeHtml(str: unknown): string {
  if (str === null || str === undefined) {
    return '';
  }
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Safely serializes a value to JSON for inclusion within HTML <script> tags.
 * Replaces '<' with '\u003c' and '>' with '\u003e' to prevent premature script termination
 * or script breakout attacks via payloads containing '</script>'.
 */
export function safeJsonStringify(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e');
}

/**
 * Generates an accessible, theme-native Webview HTML document for analysis results.
 */
export function renderResultsHtml(
  model: AnalysisResultsViewModel,
  cspSource: string,
  nonce: string
): string {
  const { header, score, summary, findings } = model;

  const scoreBadgeClass = score.level === 'pass'
    ? 'score-pass'
    : score.level === 'warn'
      ? 'score-warn'
      : 'score-fail';

  const findingsHtml = findings.length === 0
    ? `
      <div class="empty-state">
        <div class="empty-state-icon">✓</div>
        <h3>No Code Hygiene Issues Detected</h3>
        <p>Your Python source code passed all static analysis checks with clean code quality.</p>
      </div>
    `
    : findings.map((f) => renderFindingCard(f)).join('\n');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}'; img-src ${cspSource} data:;">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EdgeMind Analysis Results</title>
  <style>
    :root {
      --font-family: var(--vscode-font-family, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif);
      --bg-color: var(--vscode-editor-background);
      --fg-color: var(--vscode-editor-foreground);
      --card-bg: var(--vscode-sideBar-background, rgba(127, 127, 127, 0.05));
      --border-color: var(--vscode-widget-border, var(--vscode-panel-border, rgba(127, 127, 127, 0.2)));
      --btn-primary-bg: var(--vscode-button-background);
      --btn-primary-fg: var(--vscode-button-foreground);
      --btn-primary-hover: var(--vscode-button-hoverBackground);
      --btn-sec-bg: var(--vscode-button-secondaryBackground, rgba(127, 127, 127, 0.15));
      --btn-sec-fg: var(--vscode-button-secondaryForeground, var(--vscode-editor-foreground));
      --btn-sec-hover: var(--vscode-button-secondaryHoverBackground, rgba(127, 127, 127, 0.25));
      --badge-bg: var(--vscode-badge-background, rgba(127, 127, 127, 0.2));
      --badge-fg: var(--vscode-badge-foreground, var(--vscode-editor-foreground));
      --error-color: var(--vscode-editorError-foreground, #f14c4c);
      --warning-color: var(--vscode-editorWarning-foreground, #cca700);
      --info-color: var(--vscode-editorInfo-foreground, #3794ff);
      --success-color: var(--vscode-testing-iconPassed, #73c991);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: var(--font-family);
      background-color: var(--bg-color);
      color: var(--fg-color);
      line-height: 1.5;
      padding: 18px 24px 40px 24px;
    }

    /* Header */
    .header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border-color);
      margin-bottom: 20px;
    }

    .brand-title {
      font-size: 20px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .brand-title .logo-accent {
      color: var(--btn-primary-bg);
    }

    .file-meta {
      margin-top: 4px;
      font-size: 13px;
      opacity: 0.85;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 12px;
      background: var(--badge-bg);
      color: var(--badge-fg);
    }

    .header-actions {
      display: flex;
      gap: 8px;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px;
      font-size: 12px;
      font-weight: 500;
      border-radius: 4px;
      border: 1px solid transparent;
      cursor: pointer;
      text-decoration: none;
      transition: background 0.15s ease;
    }

    .btn-primary {
      background-color: var(--btn-primary-bg);
      color: var(--btn-primary-fg);
    }

    .btn-primary:hover {
      background-color: var(--btn-primary-hover);
    }

    .btn-secondary {
      background-color: var(--btn-sec-bg);
      color: var(--btn-sec-fg);
      border-color: var(--border-color);
    }

    .btn-secondary:hover {
      background-color: var(--btn-sec-hover);
    }

    /* Score & Summary Grid */
    .dashboard-grid {
      display: grid;
      grid-template-columns: 180px 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }

    @media (max-width: 640px) {
      .dashboard-grid {
        grid-template-columns: 1fr;
      }
    }

    .score-card {
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 16px;
      text-align: center;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
    }

    .score-number {
      font-size: 42px;
      font-weight: 800;
      line-height: 1;
      margin-bottom: 4px;
    }

    .score-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      opacity: 0.75;
      margin-bottom: 6px;
    }

    .score-status {
      font-size: 12px;
      font-weight: 700;
      padding: 2px 10px;
      border-radius: 10px;
    }

    .score-pass .score-number, .score-pass .score-status { color: var(--success-color); }
    .score-warn .score-number, .score-warn .score-status { color: var(--warning-color); }
    .score-fail .score-number, .score-fail .score-status { color: var(--error-color); }

    .summary-card {
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .metrics-row {
      display: flex;
      gap: 20px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }

    .metric-item {
      display: flex;
      flex-direction: column;
    }

    .metric-value {
      font-size: 20px;
      font-weight: 700;
    }

    .metric-label {
      font-size: 11px;
      opacity: 0.75;
      text-transform: uppercase;
    }

    .categories-row {
      display: flex;
      gap: 12px;
      font-size: 11px;
      border-top: 1px solid var(--border-color);
      padding-top: 10px;
      flex-wrap: wrap;
    }

    .cat-item {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }

    .cat-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--success-color);
    }

    .cat-dot.warn { background: var(--warning-color); }
    .cat-dot.fail { background: var(--error-color); }
    .cat-dot.skip { background: rgba(127,127,127,0.5); }

    /* Filter Bar */
    .filter-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
      flex-wrap: wrap;
      gap: 8px;
    }

    .filter-group {
      display: flex;
      gap: 6px;
    }

    .filter-btn {
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      color: var(--fg-color);
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 11px;
      cursor: pointer;
      font-weight: 500;
      transition: all 0.1s ease;
    }

    .filter-btn.active {
      background: var(--btn-primary-bg);
      color: var(--btn-primary-fg);
      border-color: var(--btn-primary-bg);
    }

    /* Findings List */
    .findings-container {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .finding-card {
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-left: 4px solid var(--border-color);
      border-radius: 4px;
      overflow: hidden;
      transition: border-color 0.15s ease;
    }

    .finding-card.severity-error { border-left-color: var(--error-color); }
    .finding-card.severity-warning { border-left-color: var(--warning-color); }
    .finding-card.severity-info { border-left-color: var(--info-color); }

    .finding-header {
      padding: 10px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      user-select: none;
    }

    .finding-title-group {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .sev-badge {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      padding: 1px 6px;
      border-radius: 3px;
    }

    .sev-badge.error { background: rgba(241, 76, 76, 0.2); color: var(--error-color); }
    .sev-badge.warning { background: rgba(204, 167, 0, 0.2); color: var(--warning-color); }
    .sev-badge.info { background: rgba(55, 148, 255, 0.2); color: var(--info-color); }

    .finding-type {
      font-weight: 600;
      font-size: 13px;
    }

    .finding-msg-summary {
      font-size: 12px;
      opacity: 0.85;
      max-width: 500px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .line-nav-badge {
      font-size: 11px;
      font-family: var(--vscode-editor-font-family, monospace);
      padding: 2px 6px;
      border-radius: 3px;
      background: rgba(127, 127, 127, 0.15);
      border: 1px solid var(--border-color);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      transition: background 0.1s ease;
    }

    .line-nav-badge:hover {
      background: rgba(127, 127, 127, 0.3);
      color: var(--btn-primary-bg);
    }

    .toggle-arrow {
      font-size: 10px;
      transition: transform 0.15s ease;
      opacity: 0.7;
    }

    .finding-card.expanded .toggle-arrow {
      transform: rotate(90deg);
    }

    .finding-body {
      display: none;
      padding: 12px 14px 14px 14px;
      border-top: 1px solid var(--border-color);
      background: rgba(0, 0, 0, 0.05);
      font-size: 12px;
    }

    .finding-card.expanded .finding-body {
      display: block;
    }

    .finding-detail-item {
      margin-bottom: 8px;
    }

    .detail-label {
      font-weight: 600;
      color: var(--btn-primary-bg);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      margin-bottom: 2px;
    }

    .detail-content {
      background: rgba(127, 127, 127, 0.07);
      padding: 6px 10px;
      border-radius: 4px;
      border-left: 2px solid var(--border-color);
    }

    .finding-actions {
      margin-top: 10px;
      display: flex;
      gap: 8px;
    }

    .empty-state {
      text-align: center;
      padding: 40px 20px;
      border: 1px dashed var(--border-color);
      border-radius: 6px;
      background: var(--card-bg);
    }

    .empty-state-icon {
      font-size: 36px;
      color: var(--success-color);
      margin-bottom: 8px;
    }

    .hidden {
      display: none !important;
    }

    /* AI Diagnosis Styles */
    .diagnosis-container {
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 6px;
      border: 1px solid var(--border-color);
      background: var(--vscode-editor-background);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }

    .diagnosis-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border-color);
      font-size: 11px;
    }

    .diagnosis-status-badge {
      font-weight: 700;
      letter-spacing: 0.4px;
      color: var(--btn-primary-bg);
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .diagnosis-actions {
      display: flex;
      gap: 6px;
      align-items: center;
    }

    .diagnosis-body {
      font-size: 12px;
      line-height: 1.6;
      max-height: 520px;
      overflow-y: auto;
      padding-right: 4px;
    }

    .diagnosis-body blockquote.diag-quote {
      margin: 8px 0;
      padding: 6px 12px;
      border-left: 3px solid var(--btn-primary-bg);
      background: rgba(127, 127, 127, 0.08);
      border-radius: 0 4px 4px 0;
      font-style: italic;
      opacity: 0.9;
    }

    .diagnosis-body hr.diag-hr {
      border: none;
      border-top: 1px solid var(--border-color);
      margin: 12px 0;
    }

    .diagnosis-interrupted-banner {
      margin-top: 10px;
      padding: 8px 12px;
      border-radius: 4px;
      background: rgba(204, 167, 0, 0.12);
      border: 1px solid var(--warning-color);
      color: var(--fg-color);
      font-size: 11px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .diagnosis-error-banner {
      padding: 8px 12px;
      border-radius: 4px;
      background: rgba(241, 76, 76, 0.12);
      border: 1px solid var(--error-color);
      color: var(--error-color);
      font-size: 12px;
    }

    .diagnosis-body p {
      margin-bottom: 8px;
    }

    .diagnosis-body ul, .diagnosis-body ol {
      margin: 6px 0 8px 20px;
    }

    .diagnosis-body li {
      margin-bottom: 3px;
    }

    .diagnosis-body .diag-heading {
      font-weight: 700;
      margin-top: 12px;
      margin-bottom: 4px;
      color: var(--fg-color);
    }

    .diagnosis-body .diag-heading.h3, .diagnosis-body .diag-heading.h4 {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--btn-primary-bg);
      border-bottom: 1px dashed var(--border-color);
      padding-bottom: 2px;
    }

    .diagnosis-body pre {
      background: rgba(127, 127, 127, 0.1);
      padding: 8px 12px;
      border-radius: 4px;
      overflow-x: auto;
      margin: 8px 0;
      border: 1px solid var(--border-color);
      font-family: var(--vscode-editor-font-family, monospace);
    }

    .diagnosis-body code.inline-code {
      background: rgba(127, 127, 127, 0.15);
      padding: 1px 4px;
      border-radius: 3px;
      font-family: var(--vscode-editor-font-family, monospace);
    }

    .spinner {
      display: inline-block;
      width: 11px;
      height: 11px;
      border: 2px solid var(--border-color);
      border-top-color: var(--btn-primary-bg);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  </style>
</head>
<body>
  <!-- Header -->
  <header class="header">
    <div>
      <div class="brand-title">
        <span class="logo-accent">⚡</span> ${escapeHtml(header.branding)} Code Intelligence
      </div>
      <div class="file-meta">
        <span><strong>File:</strong> ${escapeHtml(header.displayFilename)}</span>
        <span class="badge">${escapeHtml(header.scopeLabel)}</span>
        <span><strong>Analyzed:</strong> ${escapeHtml(header.timestamp)}</span>
      </div>
    </div>
    <div class="header-actions">
      <button id="btn-reanalyze" class="btn btn-primary" title="Rerun analysis on this document/selection">
        ↻ Analyze Again
      </button>
      <button id="btn-clear" class="btn btn-secondary" title="Clear displayed results">
        ✕ Clear Results
      </button>
    </div>
  </header>

  <!-- Dashboard Overview -->
  <section class="dashboard-grid">
    <!-- Score Card -->
    <div class="score-card ${scoreBadgeClass}">
      <div class="score-label">Hygiene Score</div>
      <div class="score-number">${score.value}</div>
      <div class="score-status">${escapeHtml(score.status)}</div>
    </div>

    <!-- Summary Metrics -->
    <div class="summary-card">
      <div class="metrics-row">
        <div class="metric-item">
          <span class="metric-value">${summary.totalFindings}</span>
          <span class="metric-label">Total Findings</span>
        </div>
        <div class="metric-item">
          <span class="metric-value" style="color: var(--error-color);">${summary.errorCount}</span>
          <span class="metric-label">Errors</span>
        </div>
        <div class="metric-item">
          <span class="metric-value" style="color: var(--warning-color);">${summary.warningCount}</span>
          <span class="metric-label">Warnings</span>
        </div>
        <div class="metric-item">
          <span class="metric-value" style="color: var(--info-color);">${summary.infoCount}</span>
          <span class="metric-label">Informational</span>
        </div>
      </div>

      <div class="categories-row">
        <span class="cat-item">
          <span class="cat-dot ${summary.syntaxStatus === 'PASS' ? '' : 'fail'}"></span>
          Syntax: ${escapeHtml(summary.syntaxStatus || 'PASS')}
        </span>
        <span class="cat-item">
          <span class="cat-dot ${summary.runtimeStatus === 'PASS' ? '' : (summary.runtimeStatus === 'SKIPPED' ? 'skip' : 'fail')}"></span>
          Runtime: ${escapeHtml(summary.runtimeStatus || 'SKIPPED')}
        </span>
        <span class="cat-item">
          <span class="cat-dot ${summary.logicStatus === 'PASS' ? '' : 'warn'}"></span>
          Logic: ${escapeHtml(summary.logicStatus || 'PASS')}
        </span>
        <span class="cat-item">
          <span class="cat-dot ${summary.qualityStatus === 'PASS' ? '' : 'warn'}"></span>
          Quality: ${escapeHtml(summary.qualityStatus || 'PASS')}
        </span>
        <span class="cat-item">
          <span class="cat-dot ${summary.complexityStatus === 'PASS' ? '' : 'warn'}"></span>
          Complexity: ${escapeHtml(summary.complexityStatus || 'PASS')}
        </span>
      </div>
    </div>
  </section>

  <!-- Filter Controls -->
  <section class="filter-bar">
    <div class="filter-group">
      <button class="filter-btn active" data-filter="all">All (${summary.totalFindings})</button>
      <button class="filter-btn" data-filter="error">Errors (${summary.errorCount})</button>
      <button class="filter-btn" data-filter="warning">Warnings (${summary.warningCount})</button>
      <button class="filter-btn" data-filter="info">Info (${summary.infoCount})</button>
    </div>
    <span style="font-size: 11px; opacity: 0.7;">Click card to expand remediation guidance</span>
  </section>

  <!-- Findings List -->
  <main class="findings-container" id="findings-list">
    ${findingsHtml}
  </main>

  <script nonce="${nonce}">
    (function() {
      const vscode = acquireVsCodeApi();
      const documentUri = ${safeJsonStringify(header.documentUri)};

      // Filtering logic
      const filterBtns = document.querySelectorAll('.filter-btn');
      const cards = document.querySelectorAll('.finding-card');

      filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
          filterBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');

          const filter = btn.getAttribute('data-filter');
          cards.forEach(card => {
            if (filter === 'all' || card.getAttribute('data-severity') === filter) {
              card.classList.remove('hidden');
            } else {
              card.classList.add('hidden');
            }
          });
        });
      });

      // Expand/Collapse cards
      cards.forEach(card => {
        const header = card.querySelector('.finding-header');
        if (header) {
          header.addEventListener('click', (e) => {
            // Avoid toggling when clicking directly on the line navigation badge
            if (e.target.closest('.line-nav-badge')) {
              return;
            }
            const expanded = card.classList.toggle('expanded');
            header.setAttribute('aria-expanded', expanded ? 'true' : 'false');
          });
        }
      });

      // Keyboard navigation support for line badges and card headers
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          const target = e.target;
          if (target && target.matches && (target.matches('.line-nav-badge') || target.matches('.finding-header'))) {
            e.preventDefault();
            target.click();
          }
        }
      });

      // Line navigation delegation - navigation is bound to the analyzed document on extension side
      document.addEventListener('click', (e) => {
        const navEl = e.target.closest('[data-line]');
        if (navEl) {
          const lineStr = navEl.getAttribute('data-line');
          const line = parseInt(lineStr, 10);
          if (!isNaN(line) && line >= 1) {
            vscode.postMessage({
              type: 'navigateToLine',
              line: line
            });
          }
        }
      });

      // Actions
      const reanalyzeBtn = document.getElementById('btn-reanalyze');
      if (reanalyzeBtn) {
        reanalyzeBtn.addEventListener('click', () => {
          vscode.postMessage({ type: 'analyzeAgain' });
        });
      }

      const clearBtn = document.getElementById('btn-clear');
      if (clearBtn) {
        clearBtn.addEventListener('click', () => {
          vscode.postMessage({ type: 'clearResults' });
        });
      }

      // Action button delegation for diagnosis
      document.addEventListener('click', (e) => {
        // Explain Finding
        const explainBtn = e.target.closest('.btn-explain-finding');
        if (explainBtn) {
          e.stopPropagation();
          const findingId = explainBtn.getAttribute('data-finding-id');
          if (findingId) {
            const card = explainBtn.closest('.finding-card');
            if (card) {
              card.classList.add('expanded');
              const h = card.querySelector('.finding-header');
              if (h) {
                h.setAttribute('aria-expanded', 'true');
              }
            }
            explainBtn.setAttribute('aria-expanded', 'true');
            vscode.postMessage({
              type: 'explainFinding',
              findingId: findingId
            });
          }
          return;
        }

        // Cancel Diagnosis
        const cancelBtn = e.target.closest('.btn-cancel-diagnosis');
        if (cancelBtn) {
          e.stopPropagation();
          const findingId = cancelBtn.getAttribute('data-finding-id');
          if (findingId) {
            vscode.postMessage({
              type: 'cancelDiagnosis',
              findingId: findingId
            });
          }
          return;
        }

        // Retry Diagnosis
        const retryBtn = e.target.closest('.btn-retry-diagnosis');
        if (retryBtn) {
          e.stopPropagation();
          const findingId = retryBtn.getAttribute('data-finding-id');
          if (findingId) {
            vscode.postMessage({
              type: 'retryDiagnosis',
              findingId: findingId
            });
          }
          return;
        }
      });

      // Handle streaming updates and state changes from Extension Host
      window.addEventListener('message', (event) => {
        const message = event.data;
        if (!message || typeof message !== 'object') {
          return;
        }

        const findingId = message.findingId;
        if (!findingId) {
          return;
        }

        const container = document.getElementById('diagnosis-' + findingId);
        if (!container) {
          return;
        }

        const body = document.getElementById('diagnosis-body-' + findingId);
        const statusText = container.querySelector('.status-text');
        const statusIcon = container.querySelector('.status-icon');
        const cancelBtn = container.querySelector('.btn-cancel-diagnosis');
        const retryBtn = container.querySelector('.btn-retry-diagnosis');
        const explainBtn = document.querySelector('.btn-explain-finding[data-finding-id="' + findingId + '"]');

        if (message.type === 'diagnosisStateChange') {
          container.setAttribute('data-state', message.state);
          container.style.display = 'block';

          if (message.state === 'loading') {
            if (body) {
              body.setAttribute('aria-busy', 'true');
            }
            if (explainBtn) {
              explainBtn.setAttribute('aria-expanded', 'true');
              explainBtn.setAttribute('disabled', 'true');
              explainBtn.style.opacity = '0.6';
              explainBtn.style.pointerEvents = 'none';
            }
            if (statusIcon) statusIcon.innerHTML = '<span class="spinner" aria-hidden="true"></span>';
            if (statusText) {
              statusText.textContent = 'Diagnosing root cause...';
              statusText.style.color = '';
            }
            if (cancelBtn) cancelBtn.style.display = 'inline-flex';
            if (retryBtn) retryBtn.style.display = 'none';
            if (body && !body.innerHTML.trim()) {
              body.innerHTML = '<div style="opacity: 0.75; font-style: italic;"><span class="spinner" aria-hidden="true"></span> Analyzing finding context and root cause...</div>';
            }
          } else if (message.state === 'completed') {
            if (body) {
              body.setAttribute('aria-busy', 'false');
            }
            if (statusIcon) statusIcon.textContent = '⚡';
            if (statusText) {
              const durText = message.durationMs ? ' (' + (message.durationMs / 1000).toFixed(1) + 's)' : '';
              statusText.textContent = 'AI Root Cause Diagnosis' + durText;
              statusText.style.color = '';
            }
            if (cancelBtn) cancelBtn.style.display = 'none';
            if (retryBtn) retryBtn.style.display = 'none';
            if (explainBtn) {
              explainBtn.removeAttribute('disabled');
              explainBtn.style.opacity = '';
              explainBtn.style.pointerEvents = '';
              explainBtn.innerHTML = '⚡ Re-diagnose';
              explainBtn.setAttribute('aria-label', 'Re-run AI root cause diagnosis for this finding');
            }
            if (message.html && body) {
              body.innerHTML = message.html;
            }
          } else if (message.state === 'error') {
            if (body) {
              body.setAttribute('aria-busy', 'false');
            }
            if (statusIcon) statusIcon.textContent = '✕';
            if (statusText) {
              statusText.textContent = 'Diagnosis Failed';
              statusText.style.color = 'var(--error-color)';
            }
            if (cancelBtn) cancelBtn.style.display = 'none';
            if (retryBtn) retryBtn.style.display = message.retryable !== false ? 'inline-flex' : 'none';
            if (explainBtn) {
              explainBtn.removeAttribute('disabled');
              explainBtn.style.opacity = '';
              explainBtn.style.pointerEvents = '';
            }
            if (body) {
              const safeErr = String(message.error || 'Unknown error occurred')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
              // Preserve partial diagnosis if stream was interrupted midway
              if (message.partialHtml) {
                body.innerHTML = message.partialHtml +
                  '<div class="diagnosis-interrupted-banner"><span aria-hidden="true">⚠️</span> <span>Diagnosis stream interrupted: ' + safeErr + '</span></div>';
              } else {
                body.innerHTML = '<div class="diagnosis-error-banner">' + safeErr + '</div>';
              }
            }
          } else if (message.state === 'cancelled') {
            if (body) {
              body.setAttribute('aria-busy', 'false');
            }
            if (statusIcon) statusIcon.textContent = '⏹';
            if (statusText) {
              statusText.textContent = 'Diagnosis Cancelled';
              statusText.style.color = '';
            }
            if (cancelBtn) cancelBtn.style.display = 'none';
            if (retryBtn) retryBtn.style.display = 'inline-flex';
            if (explainBtn) {
              explainBtn.removeAttribute('disabled');
              explainBtn.style.opacity = '';
              explainBtn.style.pointerEvents = '';
            }
            if (body) {
              const hasUsefulContent = body.textContent &&
                !body.textContent.includes('Analyzing finding context') &&
                !body.textContent.includes('Diagnosis was cancelled');
              if (hasUsefulContent) {
                body.innerHTML += '<div style="opacity: 0.75; font-style: italic; margin-top: 8px;">(Diagnosis stopped by user)</div>';
              } else {
                body.innerHTML = '<div style="opacity: 0.7; font-style: italic;">Diagnosis was cancelled by user.</div>';
              }
            }
          }
        } else if (message.type === 'diagnosisChunk') {
          const currentState = container.getAttribute('data-state');
          if (currentState !== 'streaming') {
            container.style.display = 'block';
            container.setAttribute('data-state', 'streaming');
            if (body) {
              body.setAttribute('aria-busy', 'true');
            }
            if (statusIcon) statusIcon.innerHTML = '<span class="spinner" aria-hidden="true"></span>';
            if (statusText) {
              statusText.textContent = 'Streaming diagnosis...';
              statusText.style.color = '';
            }
            if (cancelBtn) cancelBtn.style.display = 'inline-flex';
            if (retryBtn) retryBtn.style.display = 'none';
          }
          if (body && message.html) {
            body.innerHTML = message.html;
          }
        }
      });
    })();
  </script>
</body>
</html>`;
}

/**
 * Renders an individual finding card.
 */
function renderFindingCard(finding: FindingItem): string {
  const lineLabel = finding.line
    ? `<span class="line-nav-badge" data-line="${finding.line}" tabindex="0" role="button" aria-label="Navigate to line ${finding.line} in editor" title="Click to navigate to line ${finding.line}">Line ${finding.line} ↗</span>`
    : '';

  const conceptBadge = finding.concept
    ? `<span class="badge" style="font-size: 10px;">${escapeHtml(finding.concept)}</span>`
    : '';

  let detailsHtml = '';
  if (finding.why) {
    detailsHtml += `
      <div class="finding-detail-item">
        <div class="detail-label">Why:</div>
        <div class="detail-content">${escapeHtml(finding.why)}</div>
      </div>
    `;
  }

  if (finding.fix) {
    detailsHtml += `
      <div class="finding-detail-item">
        <div class="detail-label">Suggested Fix:</div>
        <div class="detail-content">${escapeHtml(finding.fix)}</div>
      </div>
    `;
  }

  const navButton = finding.line
    ? `
        <button class="btn btn-secondary" data-line="${finding.line}">
          Jump to Line ${finding.line} in Editor
        </button>
      `
    : '';

  return `
    <article class="finding-card severity-${finding.severity}" data-severity="${finding.severity}" id="${escapeHtml(finding.id)}">
      <div class="finding-header" tabindex="0" role="button" aria-expanded="false" aria-controls="finding-body-${escapeHtml(finding.id)}">
        <div class="finding-title-group">
          <span class="sev-badge ${finding.severity}">${escapeHtml(finding.severity)}</span>
          <span class="finding-type">${escapeHtml(finding.type)}</span>
          <span class="finding-msg-summary">${escapeHtml(finding.message)}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          ${conceptBadge}
          ${lineLabel}
          <span class="toggle-arrow" aria-hidden="true">▶</span>
        </div>
      </div>
      <div class="finding-body" id="finding-body-${escapeHtml(finding.id)}">
        <div class="finding-detail-item">
          <div class="detail-label">Issue:</div>
          <div style="font-size: 13px; font-weight: 500; margin-bottom: 6px;">${escapeHtml(finding.message)}</div>
        </div>
        ${detailsHtml}
        <div class="finding-actions">
          <button class="btn btn-secondary btn-explain-finding" data-finding-id="${escapeHtml(finding.id)}" aria-expanded="false" aria-controls="diagnosis-${escapeHtml(finding.id)}" title="Request AI root-cause diagnosis for this finding">
            ⚡ Explain Finding
          </button>
          ${navButton}
        </div>
        <div class="diagnosis-container" id="diagnosis-${escapeHtml(finding.id)}" data-state="idle" role="region" aria-label="AI Root Cause Diagnosis" style="display: none;">
          <div class="diagnosis-header">
            <span class="diagnosis-status-badge">
              <span class="status-icon" aria-hidden="true">⚡</span>
              <span class="status-text">AI Diagnosis</span>
            </span>
            <div class="diagnosis-actions">
              <button class="btn btn-secondary btn-cancel-diagnosis" data-finding-id="${escapeHtml(finding.id)}" aria-label="Cancel diagnosis for this finding" style="display: none; padding: 2px 8px; font-size: 11px;">Cancel</button>
              <button class="btn btn-secondary btn-retry-diagnosis" data-finding-id="${escapeHtml(finding.id)}" aria-label="Retry diagnosis for this finding" style="display: none; padding: 2px 8px; font-size: 11px;">Retry</button>
            </div>
          </div>
          <div class="diagnosis-body" id="diagnosis-body-${escapeHtml(finding.id)}" role="status" aria-live="polite" aria-busy="false"></div>
        </div>
      </div>
    </article>
  `;
}

/**
 * Renders an idle/empty state when no results are active or results have been cleared.
 */
export function renderEmptyStateHtml(cspSource: string, nonce: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EdgeMind Results</title>
  <style>
    body {
      font-family: var(--vscode-font-family, sans-serif);
      background-color: var(--vscode-editor-background);
      color: var(--vscode-editor-foreground);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 80vh;
      text-align: center;
      padding: 20px;
    }
    .logo {
      font-size: 40px;
      margin-bottom: 12px;
    }
    h2 { margin-bottom: 8px; }
    p { opacity: 0.75; font-size: 13px; max-width: 400px; margin-bottom: 20px; }
    .btn {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border: none;
      padding: 8px 16px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 13px;
    }
    .btn:hover {
      background: var(--vscode-button-hoverBackground);
    }
  </style>
</head>
<body>
  <div class="logo">⚡</div>
  <h2>EdgeMind Analysis Results</h2>
  <p>No active analysis results. Open a Python file and run <strong>EdgeMind: Analyze Current File</strong> or select code and run <strong>EdgeMind: Analyze Selection</strong>.</p>
  <button id="btn-reanalyze" class="btn">Run Analysis</button>

  <script nonce="${nonce}">
    (function() {
      const vscode = acquireVsCodeApi();
      const reanalyzeBtn = document.getElementById('btn-reanalyze');
      if (reanalyzeBtn) {
        reanalyzeBtn.addEventListener('click', () => {
          vscode.postMessage({ type: 'analyzeAgain' });
        });
      }
    })();
  </script>
</body>
</html>`;
}
