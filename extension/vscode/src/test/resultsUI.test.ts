import { describe, it } from 'node:test';
import * as assert from 'node:assert';
import {
  transformReportToViewModel,
  classifyFindingSeverity,
  filterFindings,
  validateWebviewMessage,
  validateSelectionBounds,
  calculateAbsoluteLine1,
  getScoreLevel,
  AnalysisContext,
  FindingItem,
} from '../ui/results/resultsProvider';
import {
  renderResultsHtml,
  renderEmptyStateHtml,
  escapeHtml,
  safeJsonStringify,
} from '../ui/results/resultsRenderer';
import { AnalysisReport } from '../types/api';

describe('EdgeMind Phase 5F: Interactive Results UI Tests', () => {
  const sampleCleanReport: AnalysisReport = {
    file_path: 'clean_calc.py',
    file: 'clean_calc.py',
    overall_status: 'PASS',
    status: 'PASS',
    score: 100,
    total_errors: 0,
    total_warnings: 0,
    syntax_status: 'PASS',
    runtime_status: 'SKIPPED',
    logic_status: 'PASS',
    quality_status: 'PASS',
    complexity_status: 'PASS',
    errors: [],
    warnings: [],
    summary: {
      syntax: 'PASS',
      runtime: 'SKIPPED',
      logic: 'PASS',
      quality: 'PASS',
      complexity: 'PASS',
    },
  };

  const sampleBuggyReport: AnalysisReport = {
    file_path: 'math_ops.py',
    file: 'math_ops.py',
    overall_status: 'FAIL',
    status: 'FAIL',
    score: 65,
    total_errors: 1,
    total_warnings: 2,
    syntax_status: 'PASS',
    runtime_status: 'SKIPPED',
    logic_status: 'FAIL',
    quality_status: 'WARN',
    complexity_status: 'PASS',
    errors: [
      {
        type: 'ZeroDivisionError',
        line: 3,
        line_number: 3,
        message: 'Division by zero detected',
        why: 'Denominator is literal zero',
        explanation: 'Denominator is literal zero',
        fix: 'Add guard check before dividing',
        suggested_fix: 'Add guard check before dividing',
        concept: 'Arithmetic Safety',
      },
    ],
    warnings: [
      {
        type: 'UnusedVariable',
        line: 2,
        line_number: 2,
        message: "Variable 'unused_val' is unused",
        why: 'Dead code',
        explanation: 'Dead code',
        fix: "Remove 'unused_val'",
        suggested_fix: "Remove 'unused_val'",
        concept: 'Code Quality',
      },
      {
        type: 'InfoComplexity',
        line: 1,
        line_number: 1,
        message: 'Function cyclomatic complexity is 1',
        why: '',
        explanation: '',
        fix: '',
        suggested_fix: '',
        concept: 'Complexity',
      },
    ],
    summary: {
      syntax: 'PASS',
      runtime: 'SKIPPED',
      logic: 'FAIL',
      quality: 'WARN',
      complexity: 'PASS',
    },
  };

  describe('1. Data Transformation & Context (transformReportToViewModel)', () => {
    it('should transform full-file analysis report into view model', () => {
      const context: AnalysisContext = {
        scope: 'full',
        documentUri: 'file:///workspace/math_ops.py',
        documentPath: 'C:\\workspace\\math_ops.py',
        displayFilename: 'math_ops.py',
        timestamp: '10:30:00 AM',
      };

      const vm = transformReportToViewModel(sampleBuggyReport, context);

      assert.strictEqual(vm.header.branding, 'EdgeMind');
      assert.strictEqual(vm.header.displayFilename, 'math_ops.py');
      assert.strictEqual(vm.header.scope, 'full');
      assert.strictEqual(vm.header.scopeLabel, 'Full File');
      assert.strictEqual(vm.header.timestamp, '10:30:00 AM');

      assert.strictEqual(vm.score.value, 65);
      assert.strictEqual(vm.score.status, 'FAIL');
      assert.strictEqual(vm.score.level, 'fail');

      assert.strictEqual(vm.summary.totalFindings, 3);
      assert.strictEqual(vm.summary.errorCount, 1);
      assert.strictEqual(vm.summary.warningCount, 1);
      assert.strictEqual(vm.summary.infoCount, 1); // InfoComplexity mapped to info

      assert.strictEqual(vm.findings.length, 3);
      assert.strictEqual(vm.findings[0].type, 'ZeroDivisionError');
      assert.strictEqual(vm.findings[0].line, 3);
    });

    it('should map snippet-relative lines to document lines in selected-code context', () => {
      const context: AnalysisContext = {
        scope: 'selection',
        documentUri: 'file:///workspace/math_ops.py',
        documentPath: 'C:\\workspace\\math_ops.py',
        displayFilename: 'math_ops.py',
        selectionStartLine: 20,
        selectionEndLine: 25,
        timestamp: '10:35:00 AM',
      };

      const vm = transformReportToViewModel(sampleBuggyReport, context);

      assert.strictEqual(vm.header.scope, 'selection');
      assert.strictEqual(vm.header.scopeLabel, 'Selected Code (Lines 20–25)');

      // Snippet line 3 should map to absolute document line 22 (20 + 3 - 1)
      const errFinding = vm.findings.find((f) => f.type === 'ZeroDivisionError');
      assert.ok(errFinding);
      assert.strictEqual(errFinding.line, 22);
      assert.strictEqual(errFinding.snippetLine, 3);

      // Snippet line 2 should map to line 21
      const warnFinding = vm.findings.find((f) => f.type === 'UnusedVariable');
      assert.ok(warnFinding);
      assert.strictEqual(warnFinding.line, 21);
      assert.strictEqual(warnFinding.snippetLine, 2);
    });

    it('should format single-line selection label correctly', () => {
      const context: AnalysisContext = {
        scope: 'selection',
        documentUri: 'file:///workspace/script.py',
        documentPath: 'C:\\workspace\\script.py',
        displayFilename: 'script.py',
        selectionStartLine: 42,
        selectionEndLine: 42,
      };

      const vm = transformReportToViewModel(sampleCleanReport, context);
      assert.strictEqual(vm.header.scopeLabel, 'Selected Code (Line 42)');
    });

    it('should handle missing optional fields gracefully', () => {
      const minimalReport: AnalysisReport = {
        file_path: 'mini.py',
        file: 'mini.py',
        overall_status: '',
        status: '',
        score: undefined as unknown as number,
        total_errors: 0,
        total_warnings: 0,
        syntax_status: '',
        runtime_status: '',
        logic_status: '',
        quality_status: '',
        complexity_status: '',
        errors: [
          {
            type: 'SyntaxError',
            line: 0,
            line_number: 0,
            message: '',
            why: '',
            explanation: '',
            fix: '',
            suggested_fix: '',
            concept: '',
          },
        ],
        warnings: [],
        summary: undefined as unknown as any,
      };

      const context: AnalysisContext = {
        scope: 'full',
        documentUri: 'file:///workspace/mini.py',
        documentPath: 'mini.py',
        displayFilename: 'mini.py',
      };

      const vm = transformReportToViewModel(minimalReport, context);
      assert.strictEqual(vm.score.value, 100);
      assert.strictEqual(vm.findings.length, 1);
      assert.strictEqual(vm.findings[0].line, undefined); // line 0 becomes undefined
      assert.strictEqual(vm.findings[0].message, 'SyntaxError');
    });
  });

  describe('2. Severity Classification (classifyFindingSeverity)', () => {
    it('should classify error, warning, and info correctly', () => {
      const err = classifyFindingSeverity({ type: 'SyntaxError' } as any, 'error');
      assert.strictEqual(err, 'error');

      const warn = classifyFindingSeverity({ type: 'UnusedVariable' } as any, 'warning');
      assert.strictEqual(warn, 'warning');

      const explicitInfo = classifyFindingSeverity({ type: 'StyleNotice', severity: 'info' } as any, 'warning');
      assert.strictEqual(explicitInfo, 'info');

      const typeInfo = classifyFindingSeverity({ type: 'InfoComplexity' } as any, 'warning');
      assert.strictEqual(typeInfo, 'info');
    });
  });

  describe('3. Score Level Calculation (getScoreLevel)', () => {
    it('should return pass, warn, or fail based on score and errors', () => {
      assert.strictEqual(getScoreLevel(100, 0), 'pass');
      assert.strictEqual(getScoreLevel(85, 0), 'warn');
      assert.strictEqual(getScoreLevel(100, 1), 'fail'); // Any error = fail level
      assert.strictEqual(getScoreLevel(50, 0), 'fail');  // Score < 70 = fail level
    });
  });

  describe('4. Finding Filtering (filterFindings)', () => {
    const testFindings: FindingItem[] = [
      { id: '1', type: 'E1', severity: 'error', message: 'err' },
      { id: '2', type: 'W1', severity: 'warning', message: 'warn' },
      { id: '3', type: 'W2', severity: 'warning', message: 'warn 2' },
      { id: '4', type: 'I1', severity: 'info', message: 'info' },
    ];

    it('should filter correctly by severity', () => {
      assert.strictEqual(filterFindings(testFindings, 'all').length, 4);
      assert.strictEqual(filterFindings(testFindings, 'error').length, 1);
      assert.strictEqual(filterFindings(testFindings, 'warning').length, 2);
      assert.strictEqual(filterFindings(testFindings, 'info').length, 1);
    });
  });

  describe('5. Webview Message Validation (validateWebviewMessage)', () => {
    it('should validate navigateToLine with valid line number and bind to analyzed document', () => {
      const expectedUri = 'file:///c:/project/test.py';
      // When Webview sends just line number
      const res1 = validateWebviewMessage(
        { type: 'navigateToLine', line: 15 },
        expectedUri
      );
      assert.strictEqual(res1.isValid, true);
      assert.strictEqual(res1.message?.type, 'navigateToLine');
      assert.strictEqual(res1.message?.line, 15);
      assert.strictEqual(res1.message?.uri, expectedUri);

      // When Webview sends matching URI
      const res2 = validateWebviewMessage(
        { type: 'navigateToLine', line: 15, uri: 'file:///c:/project/test.py' },
        expectedUri
      );
      assert.strictEqual(res2.isValid, true);
      assert.strictEqual(res2.message?.line, 15);
      assert.strictEqual(res2.message?.uri, expectedUri);
    });

    it('should reject navigateToLine when a foreign URI is supplied', () => {
      const expectedUri = 'file:///c:/project/test.py';
      const foreignUris = [
        'file:///etc/passwd',
        'file:///c:/windows/system32/cmd.exe',
        'http://malicious.com/exploit.py',
        'file:///c:/other_project/secret.py',
      ];

      for (const foreignUri of foreignUris) {
        const res = validateWebviewMessage(
          { type: 'navigateToLine', line: 10, uri: foreignUri },
          expectedUri
        );
        assert.strictEqual(res.isValid, false);
        assert.ok(res.error?.includes('does not match analyzed document URI'));
      }
    });

    it('should reject navigateToLine with non-finite or invalid line numbers', () => {
      const invalidLines = [0, -5, -1, 3.14, NaN, Infinity, -Infinity, '10', null, undefined, true];

      for (const badLine of invalidLines) {
        const res = validateWebviewMessage({ type: 'navigateToLine', line: badLine });
        assert.strictEqual(res.isValid, false);
        assert.ok(res.error?.includes('Line number must be a finite positive integer'));
      }
    });

    it('should validate analyzeAgain and clearResults messages', () => {
      const res1 = validateWebviewMessage({ type: 'analyzeAgain' });
      assert.strictEqual(res1.isValid, true);
      assert.strictEqual(res1.message?.type, 'analyzeAgain');

      const res2 = validateWebviewMessage({ type: 'clearResults' });
      assert.strictEqual(res2.isValid, true);
      assert.strictEqual(res2.message?.type, 'clearResults');
    });

    it('should reject invalid or unknown messages', () => {
      assert.strictEqual(validateWebviewMessage(null).isValid, false);
      assert.strictEqual(validateWebviewMessage('string').isValid, false);
      assert.strictEqual(validateWebviewMessage([]).isValid, false);
      assert.strictEqual(validateWebviewMessage({ type: 'maliciousAction' }).isValid, false);
      assert.strictEqual(validateWebviewMessage({}).isValid, false);
    });
  });

  describe('6. Security & HTML Rendering (resultsRenderer)', () => {
    it('should escape HTML characters safely', () => {
      const dangerous = '<script>alert("xss")</script> & \'test\'';
      const escaped = escapeHtml(dangerous);
      assert.strictEqual(
        escaped,
        '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt; &amp; &#39;test&#39;'
      );
    });

    it('should sanitize inline JSON against script breakout attacks (safeJsonStringify)', () => {
      const hostilePayload = '</script><script>alert("xss")</script>';
      const sanitized = safeJsonStringify(hostilePayload);

      // Verify dangerous tags are escaped as unicode escape sequences
      assert.ok(!sanitized.includes('</script>'));
      assert.ok(!sanitized.includes('<script>'));
      assert.ok(sanitized.includes('\\u003c/script\\u003e'));
      assert.ok(sanitized.includes('\\u003cscript\\u003e'));

      // Verify round-trip parsing restores the exact original value
      const parsed = JSON.parse(sanitized);
      assert.strictEqual(parsed, hostilePayload);
    });

    it('should render results HTML with Content Security Policy and Nonce', () => {
      const context: AnalysisContext = {
        scope: 'full',
        documentUri: 'file:///workspace/test.py',
        documentPath: 'test.py',
        displayFilename: 'test.py',
        timestamp: '12:00:00 PM',
      };
      const vm = transformReportToViewModel(sampleBuggyReport, context);
      const cspSource = 'vscode-webview:';
      const nonce = 'testnonce12345';

      const html = renderResultsHtml(vm, cspSource, nonce);

      // Verify CSP header
      assert.ok(html.includes("Content-Security-Policy"));
      assert.ok(html.includes("default-src 'none'"));
      assert.ok(html.includes(`script-src 'nonce-${nonce}'`));
      assert.ok(html.includes(`style-src ${cspSource} 'unsafe-inline'`));

      // Verify Nonce on script tag
      assert.ok(html.includes(`<script nonce="${nonce}">`));

      // Verify Branding & Metrics
      assert.ok(html.includes('EdgeMind'));
      assert.ok(html.includes('test.py'));
      assert.ok(html.includes('Hygiene Score'));
      assert.ok(html.includes('65'));
      assert.ok(html.includes('ZeroDivisionError'));
      assert.ok(html.includes('UnusedVariable'));
      assert.ok(html.includes('Analyze Again'));
      assert.ok(html.includes('Clear Results'));
    });

    it('should prevent hostile script breakout inside rendered HTML when documentUri contains hostile tags', () => {
      const hostileContext: AnalysisContext = {
        scope: 'full',
        documentUri: 'file:///workspace/</script><script>alert("xss")</script>.py',
        documentPath: 'test.py',
        displayFilename: 'test.py',
      };
      const vm = transformReportToViewModel(sampleCleanReport, hostileContext);
      const html = renderResultsHtml(vm, 'vscode-webview:', 'testnonce');

      // The literal unescaped closing tag must NOT appear anywhere in the script block
      assert.ok(!html.includes('</script><script>alert("xss")</script>'));
      assert.ok(html.includes('\\u003c/script\\u003e'));
    });

    it('should render empty state HTML with CSP and Nonce', () => {
      const html = renderEmptyStateHtml('vscode-webview:', 'nonceabc');
      assert.ok(html.includes("Content-Security-Policy"));
      assert.ok(html.includes('No active analysis results'));
      assert.ok(html.includes('Run Analysis'));
      assert.ok(html.includes('<script nonce="nonceabc">'));
    });
  });

  describe('7. Line Calculation Helper (calculateAbsoluteLine1)', () => {
    it('should calculate 1-based absolute lines for full file and selections', () => {
      // Full file
      assert.strictEqual(calculateAbsoluteLine1(1), 1);
      assert.strictEqual(calculateAbsoluteLine1(15), 15);
      assert.strictEqual(calculateAbsoluteLine1(0), undefined);
      assert.strictEqual(calculateAbsoluteLine1(-5), undefined);
      assert.strictEqual(calculateAbsoluteLine1(undefined), undefined);

      // Selection starting at line 50
      assert.strictEqual(calculateAbsoluteLine1(1, 50), 50);
      assert.strictEqual(calculateAbsoluteLine1(3, 50), 52);
    });
  });

  describe('8. Selection Bounds Validation for Re-analysis (validateSelectionBounds)', () => {
    it('should accept valid selection bounds within document length', () => {
      const res = validateSelectionBounds(10, 25, 100);
      assert.strictEqual(res.isValid, true);
      assert.strictEqual(res.effectiveEndLine, 25);
    });

    it('should clamp effectiveEndLine when endLine exceeds current totalLines', () => {
      const res = validateSelectionBounds(10, 60, 50);
      assert.strictEqual(res.isValid, true);
      assert.strictEqual(res.effectiveEndLine, 50);
    });

    it('should reject stale bounds when startLine exceeds current totalLines', () => {
      const res = validateSelectionBounds(55, 60, 50);
      assert.strictEqual(res.isValid, false);
      assert.ok(res.error?.includes('Stale selection bounds'));
    });

    it('should reject inverted selection bounds', () => {
      const res = validateSelectionBounds(30, 20, 50);
      assert.strictEqual(res.isValid, false);
      assert.ok(res.error?.includes('Stale selection bounds'));
    });

    it('should reject non-positive or non-finite bounds', () => {
      assert.strictEqual(validateSelectionBounds(0, 10, 50).isValid, false);
      assert.strictEqual(validateSelectionBounds(-5, 10, 50).isValid, false);
      assert.strictEqual(validateSelectionBounds(NaN, 10, 50).isValid, false);
      assert.strictEqual(validateSelectionBounds(1, Infinity, 50).isValid, false);
    });

    it('should reject bounds when document has 0 lines', () => {
      const res = validateSelectionBounds(1, 5, 0);
      assert.strictEqual(res.isValid, false);
      assert.strictEqual(res.error, 'Document has no lines.');
    });
  });
});
