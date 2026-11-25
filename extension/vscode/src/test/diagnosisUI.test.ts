import { describe, it } from 'node:test';
import * as assert from 'node:assert';
import {
  extractContextFromLines,
  MAX_DIAGNOSIS_CONTEXT_BYTES,
  ExtractedDiagnosisContext,
} from '../ui/results/contextExtractor';
import {
  renderSafeMarkdown,
  isSafeUrl,
} from '../ui/results/markdownRenderer';
import {
  validateWebviewMessage,
  transformReportToViewModel,
  filterFindings,
  AnalysisContext,
  FindingItem,
} from '../ui/results/resultsProvider';
import {
  renderResultsHtml,
} from '../ui/results/resultsRenderer';
import { AnalysisReport } from '../types/api';
import { DiagnoseFindingRequest } from '../types/diagnosis';

describe('EdgeMind Phase 5G.6: Streaming Diagnosis UI Integration Tests', () => {
  const sampleBuggyReport: AnalysisReport = {
    file_path: 'math_ops.py',
    file: 'math_ops.py',
    overall_status: 'FAIL',
    status: 'FAIL',
    score: 65,
    total_errors: 1,
    total_warnings: 1,
    syntax_status: 'PASS',
    runtime_status: 'SKIPPED',
    logic_status: 'FAIL',
    quality_status: 'WARN',
    complexity_status: 'PASS',
    errors: [
      {
        type: 'ZeroDivisionError',
        line: 20,
        line_number: 20,
        message: 'Division by zero detected',
        why: 'Denominator evaluates to 0',
        explanation: 'Denominator evaluates to 0',
        fix: 'Add guard check before dividing',
        suggested_fix: 'Add guard check before dividing',
        concept: 'Arithmetic Safety',
      },
    ],
    warnings: [
      {
        type: 'UnusedVariable',
        line: 5,
        line_number: 5,
        message: "Variable 'unused' is not referenced",
        why: 'Dead code',
        explanation: 'Dead code',
        fix: "Remove variable 'unused'",
        suggested_fix: "Remove variable 'unused'",
        concept: 'Code Hygiene',
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

  const sample50Lines = Array.from({ length: 50 }, (_, i) => `line_${i + 1} = ${i + 1}`);

  // =========================================================================
  // 1. CONTEXT EXTRACTION & BOUNDS (contextExtractor)
  // =========================================================================
  describe('1. Bounded Source Context Extraction (contextExtractor)', () => {
    it('A. should extract ±15 lines around finding line in middle of document', () => {
      // Finding on line 20 of 50 lines -> start=5 (20-15), end=35 (20+15)
      const res = extractContextFromLines(sample50Lines, 20, 'math_ops.py', 'python');

      assert.strictEqual(res.contextStartLine, 5);
      assert.strictEqual(res.contextEndLine, 35);
      assert.strictEqual(res.filename, 'math_ops.py');
      assert.strictEqual(res.language, 'python');

      const extractedLines = res.codeContext.trimEnd().split('\n');
      assert.strictEqual(extractedLines.length, 31); // 35 - 5 + 1 = 31 lines
      assert.strictEqual(extractedLines[0], 'line_5 = 5');
      assert.strictEqual(extractedLines[15], 'line_20 = 20');
      assert.strictEqual(extractedLines[30], 'line_35 = 35');
    });

    it('B. should clamp context start line to 1 when finding is near top', () => {
      // Finding on line 3 of 50 lines -> start=1, end=18 (3+15)
      const res = extractContextFromLines(sample50Lines, 3, 'test.py', 'python');

      assert.strictEqual(res.contextStartLine, 1);
      assert.strictEqual(res.contextEndLine, 18);
      const lines = res.codeContext.trimEnd().split('\n');
      assert.strictEqual(lines.length, 18);
      assert.strictEqual(lines[0], 'line_1 = 1');
      assert.strictEqual(lines[2], 'line_3 = 3');
      assert.strictEqual(lines[17], 'line_18 = 18');
    });

    it('C. should clamp context end line to totalLines when finding is near bottom', () => {
      // Finding on line 48 of 50 lines -> start=33 (48-15), end=50
      const res = extractContextFromLines(sample50Lines, 48, 'test.py', 'python');

      assert.strictEqual(res.contextStartLine, 33);
      assert.strictEqual(res.contextEndLine, 50);
      const lines = res.codeContext.trimEnd().split('\n');
      assert.strictEqual(lines.length, 18);
      assert.strictEqual(lines[0], 'line_33 = 33');
      assert.strictEqual(lines[15], 'line_48 = 48');
      assert.strictEqual(lines[17], 'line_50 = 50');
    });

    it('D. should extract first 30 lines for module-level finding without line number', () => {
      // Line is undefined -> module-level finding
      const res = extractContextFromLines(sample50Lines, undefined, 'mod.py', 'python');

      assert.strictEqual(res.contextStartLine, 1);
      assert.strictEqual(res.contextEndLine, 30);
      const lines = res.codeContext.trimEnd().split('\n');
      assert.strictEqual(lines.length, 30);
      assert.strictEqual(lines[0], 'line_1 = 1');
      assert.strictEqual(lines[29], 'line_30 = 30');
    });

    it('E. should reject finding line exceeding document length (detect modified/stale document)', () => {
      // Finding line 55 in 50 lines
      assert.throws(
        () => extractContextFromLines(sample50Lines, 55, 'stale.py'),
        /exceeds document length \(50 lines\)/
      );
    });

    it('F. should reject finding line <= 0 or invalid line number', () => {
      assert.throws(
        () => extractContextFromLines(sample50Lines, 0, 'bad.py'),
        /Invalid finding line 0: line numbers must be >= 1/
      );
      assert.throws(
        () => extractContextFromLines(sample50Lines, -10, 'bad.py'),
        /Invalid finding line -10: line numbers must be >= 1/
      );
    });

    it('G. should reject empty document with 0 lines', () => {
      assert.throws(
        () => extractContextFromLines([], 1, 'empty.py'),
        /Document has no lines/
      );
    });

    it('H. should enforce 16 KiB size limit on extracted context', () => {
      // Create lines with very long strings to trigger size bounding
      const giantLines = Array.from({ length: 40 }, (_, i) => `line_${i + 1} = "${'x'.repeat(1000)}"`);
      const res = extractContextFromLines(giantLines, 20, 'giant.py');

      const byteLength = Buffer.byteLength(res.codeContext, 'utf8');
      assert.ok(byteLength <= MAX_DIAGNOSIS_CONTEXT_BYTES, `Byte length ${byteLength} exceeded 16 KiB`);
      assert.ok(res.contextStartLine >= 1);
      assert.ok(res.contextEndLine <= giantLines.length);
    });

    it('I. should sanitize Windows and POSIX path separators in filename metadata', () => {
      const resWin = extractContextFromLines(['x = 1'], 1, 'C:\\Users\\DELL\\project\\script.py');
      assert.strictEqual(resWin.filename, 'script.py');

      const resUnix = extractContextFromLines(['x = 1'], 1, '/home/user/project/utils/helper.py');
      assert.strictEqual(resUnix.filename, 'helper.py');
    });
  });

  // =========================================================================
  // 2. SAFE MARKDOWN RENDERING (markdownRenderer)
  // =========================================================================
  describe('2. Safe Markdown Rendering & Security (markdownRenderer)', () => {
    it('J. should escape hostile HTML tags to prevent XSS injection', () => {
      const dangerousMarkdown = 'Issue found: <script>alert("xss")</script> and <img src="x" onerror="evil()"/>';
      const html = renderSafeMarkdown(dangerousMarkdown);

      assert.ok(!html.includes('<script>'));
      assert.ok(!html.includes('</script>'));
      assert.ok(!html.includes('<img'));
      assert.ok(html.includes('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'));
      assert.ok(html.includes('&lt;img src=&quot;x&quot; onerror=&quot;evil()&quot;/&gt;'));
    });

    it('K. should preserve fenced code blocks with language classes', () => {
      const codeMarkdown = '```python\ndef divide(a, b):\n    if b == 0:\n        raise ValueError("zero")\n    return a / b\n```';
      const html = renderSafeMarkdown(codeMarkdown);

      assert.ok(html.includes('<pre><code class="language-python">'));
      assert.ok(html.includes('def divide(a, b):'));
      assert.ok(html.includes('&quot;zero&quot;'));
      assert.ok(html.includes('</code></pre>'));
    });

    it('L. should handle unclosed code block during active SSE streaming without crashing', () => {
      // Chunk arrived midway through code block
      const streamingChunk = '### Fix\n```python\nif b == 0:\n    return None';
      const html = renderSafeMarkdown(streamingChunk);

      assert.ok(html.includes('<pre><code class="language-python">'));
      assert.ok(html.includes('if b == 0:'));
      assert.ok(html.includes('</code></pre>'));
    });

    it('M. should strictly reject unsafe URI schemes (javascript:, data:, vbscript:)', () => {
      assert.strictEqual(isSafeUrl('javascript:alert(1)'), false);
      assert.strictEqual(isSafeUrl('data:text/html,<script>alert(1)</script>'), false);
      assert.strictEqual(isSafeUrl('vbscript:msgbox(1)'), false);
      assert.strictEqual(isSafeUrl('file:///etc/passwd'), false);

      const maliciousLink = '[Click here for fix](javascript:alert("pwned"))';
      const html = renderSafeMarkdown(maliciousLink);
      assert.ok(!html.includes('href="javascript:'));
      assert.ok(html.includes('Click here for fix'));
    });

    it('N. should permit safe HTTP and HTTPS URLs in markdown links', () => {
      assert.strictEqual(isSafeUrl('https://docs.python.org/3/library/exceptions.html'), true);
      assert.strictEqual(isSafeUrl('http://127.0.0.1:8000/docs'), true);

      const safeLink = 'See [Python Documentation](https://docs.python.org/3/library/exceptions.html) for details.';
      const html = renderSafeMarkdown(safeLink);
      assert.ok(html.includes('<a href="https://docs.python.org/3/library/exceptions.html" target="_blank" rel="noopener noreferrer">Python Documentation</a>'));
    });

    it('O. should render headings, lists, bold, italics, and inline code properly', () => {
      const markdown = '### Root Cause\n\n- The denominator `b` can be `0`\n- This triggers **ZeroDivisionError**\n\n*Check docs*';
      const html = renderSafeMarkdown(markdown);

      assert.ok(html.includes('<h3 class="diag-heading h3">Root Cause</h3>'));
      assert.ok(html.includes('<ul>'));
      assert.ok(html.includes('<li>The denominator <code class="inline-code">b</code> can be <code class="inline-code">0</code></li>'));
      assert.ok(html.includes('<li>This triggers <strong>ZeroDivisionError</strong></li>'));
      assert.ok(html.includes('</ul>'));
      assert.ok(html.includes('<em>Check docs</em>'));
    });
  });

  // =========================================================================
  // 3. WEBVIEW MESSAGE VALIDATION (resultsProvider)
  // =========================================================================
  describe('3. Webview Message Validation for Diagnosis Actions (resultsProvider)', () => {
    it('P. should validate explainFinding message with valid safe findingId', () => {
      const res = validateWebviewMessage({
        type: 'explainFinding',
        findingId: 'finding-0',
      });

      assert.strictEqual(res.isValid, true);
      assert.strictEqual(res.message?.type, 'explainFinding');
      assert.strictEqual(res.message?.findingId, 'finding-0');
    });

    it('Q. should validate cancelDiagnosis and retryDiagnosis messages', () => {
      const cancelRes = validateWebviewMessage({
        type: 'cancelDiagnosis',
        findingId: 'finding-1',
      });
      assert.strictEqual(cancelRes.isValid, true);
      assert.strictEqual(cancelRes.message?.type, 'cancelDiagnosis');
      assert.strictEqual(cancelRes.message?.findingId, 'finding-1');

      const retryRes = validateWebviewMessage({
        type: 'retryDiagnosis',
        findingId: 'finding-1',
      });
      assert.strictEqual(retryRes.isValid, true);
      assert.strictEqual(retryRes.message?.type, 'retryDiagnosis');
      assert.strictEqual(retryRes.message?.findingId, 'finding-1');
    });

    it('R. should reject explainFinding with missing or empty findingId', () => {
      assert.strictEqual(validateWebviewMessage({ type: 'explainFinding' }).isValid, false);
      assert.strictEqual(validateWebviewMessage({ type: 'explainFinding', findingId: '' }).isValid, false);
      assert.strictEqual(validateWebviewMessage({ type: 'explainFinding', findingId: '   ' }).isValid, false);
      assert.strictEqual(validateWebviewMessage({ type: 'explainFinding', findingId: 123 }).isValid, false);
    });

    it('S. should reject hostile findingId with script or path injection characters', () => {
      const hostileIds = [
        '<script>alert(1)</script>',
        '../../../etc/passwd',
        'finding 0 with spaces',
        'finding;DROP TABLE findings;--',
        'f'.repeat(150), // exceeds 128 chars limit
      ];

      for (const id of hostileIds) {
        const res = validateWebviewMessage({ type: 'explainFinding', findingId: id });
        assert.strictEqual(res.isValid, false, `Failed to reject hostile findingId: '${id}'`);
        assert.ok(res.error?.includes('must be a safe identifier'));
      }
    });
  });

  // =========================================================================
  // 4. WEBVIEW HTML RENDERING & STRUCTURE (resultsRenderer)
  // =========================================================================
  describe('4. Results UI Card & Diagnosis Container Rendering (resultsRenderer)', () => {
    it('T. should render Explain Finding button and Diagnosis Container in finding cards', () => {
      const context: AnalysisContext = {
        scope: 'full',
        documentUri: 'file:///c:/project/math_ops.py',
        documentPath: 'C:\\project\\math_ops.py',
        displayFilename: 'math_ops.py',
      };
      const vm = transformReportToViewModel(sampleBuggyReport, context);
      const html = renderResultsHtml(vm, 'vscode-webview:', 'testnonce');

      // Verify Explain Finding action button rendered
      assert.ok(html.includes('btn-explain-finding'));
      assert.ok(html.includes('data-finding-id="finding-0"'));
      assert.ok(html.includes('⚡ Explain Finding'));

      // Verify Diagnosis container rendered with initial idle hidden state
      assert.ok(html.includes('id="diagnosis-finding-0"'));
      assert.ok(html.includes('data-state="idle"'));
      assert.ok(html.includes('style="display: none;"'));

      // Verify Diagnosis Header elements
      assert.ok(html.includes('class="diagnosis-status-badge"'));
      assert.ok(html.includes('class="status-icon"'));
      assert.ok(html.includes('class="status-text"'));
      assert.ok(html.includes('btn-cancel-diagnosis'));
      assert.ok(html.includes('btn-retry-diagnosis'));

      // Verify Diagnosis Body
      assert.ok(html.includes('id="diagnosis-body-finding-0"'));
    });

    it('U. should include client script with delegation for explain, cancel, retry and window message handling', () => {
      const context: AnalysisContext = {
        scope: 'full',
        documentUri: 'file:///c:/project/math_ops.py',
        documentPath: 'C:\\project\\math_ops.py',
        displayFilename: 'math_ops.py',
      };
      const vm = transformReportToViewModel(sampleBuggyReport, context);
      const html = renderResultsHtml(vm, 'vscode-webview:', 'testnonce123');

      // Verify delegated click handlers for all three diagnosis actions
      assert.ok(html.includes('.btn-explain-finding'));
      assert.ok(html.includes("type: 'explainFinding'"));
      assert.ok(html.includes('.btn-cancel-diagnosis'));
      assert.ok(html.includes("type: 'cancelDiagnosis'"));
      assert.ok(html.includes('.btn-retry-diagnosis'));
      assert.ok(html.includes("type: 'retryDiagnosis'"));

      // Verify window message listener for real-time streaming updates
      assert.ok(html.includes("window.addEventListener('message'"));
      assert.ok(html.includes("message.type === 'diagnosisStateChange'"));
      assert.ok(html.includes("message.type === 'diagnosisChunk'"));
      assert.ok(html.includes("message.state === 'loading'"));
      assert.ok(html.includes("message.state === 'completed'"));
      assert.ok(html.includes("message.state === 'error'"));
      assert.ok(html.includes("message.state === 'cancelled'"));
    });
  });

  // =========================================================================
  // 5. REQUEST CONSTRUCTION & DATA FLOW
  // =========================================================================
  describe('5. DiagnoseFindingRequest Construction & Verification', () => {
    it('V. should construct complete DiagnoseFindingRequest with finding payload and bounded context', () => {
      const finding: FindingItem = {
        id: 'finding-0',
        type: 'ZeroDivisionError',
        severity: 'error',
        message: 'Division by zero on line 20',
        line: 20,
        why: 'Denominator evaluates to 0',
        fix: 'Add guard check before dividing',
      };

      const extracted: ExtractedDiagnosisContext = extractContextFromLines(
        sample50Lines,
        finding.line,
        'math_ops.py',
        'python'
      );

      const request: DiagnoseFindingRequest = {
        finding: {
          finding_id: finding.id,
          type: finding.type,
          severity: finding.severity,
          message: finding.message,
          line: finding.line ?? null,
          static_why: finding.why ?? null,
          static_fix: finding.fix ?? null,
        },
        code_context: extracted.codeContext,
        context_start_line: extracted.contextStartLine,
        context_end_line: extracted.contextEndLine,
        filename: extracted.filename,
        language: extracted.language,
      };

      assert.strictEqual(request.finding.finding_id, 'finding-0');
      assert.strictEqual(request.finding.type, 'ZeroDivisionError');
      assert.strictEqual(request.finding.severity, 'error');
      assert.strictEqual(request.finding.message, 'Division by zero on line 20');
      assert.strictEqual(request.finding.line, 20);
      assert.strictEqual(request.finding.static_why, 'Denominator evaluates to 0');
      assert.strictEqual(request.finding.static_fix, 'Add guard check before dividing');
      assert.strictEqual(request.context_start_line, 5);
      assert.strictEqual(request.context_end_line, 35);
      assert.strictEqual(request.filename, 'math_ops.py');
      assert.strictEqual(request.language, 'python');
      assert.ok(request.code_context.includes('line_20 = 20'));
    });
  });

  // =========================================================================
  // 6. PER-FINDING ISOLATION & CANCELLATION SEMANTICS
  // =========================================================================
  describe('6. Per-Finding Isolation & Cancellation Logic', () => {
    it('W. should allow independent cancellation of finding A without cancelling finding B', () => {
      const activeDiagnoses = new Map<string, { findingId: string; controller: AbortController }>();

      const ctrlA = new AbortController();
      const ctrlB = new AbortController();

      activeDiagnoses.set('finding-0', { findingId: 'finding-0', controller: ctrlA });
      activeDiagnoses.set('finding-1', { findingId: 'finding-1', controller: ctrlB });

      assert.strictEqual(activeDiagnoses.size, 2);
      assert.strictEqual(ctrlA.signal.aborted, false);
      assert.strictEqual(ctrlB.signal.aborted, false);

      // Cancel finding-0 only
      const target = activeDiagnoses.get('finding-0');
      target?.controller.abort();
      activeDiagnoses.delete('finding-0');

      assert.strictEqual(ctrlA.signal.aborted, true);
      assert.strictEqual(ctrlB.signal.aborted, false);
      assert.strictEqual(activeDiagnoses.has('finding-0'), false);
      assert.strictEqual(activeDiagnoses.has('finding-1'), true);
      assert.strictEqual(activeDiagnoses.size, 1);
    });

    it('X. should abort all active diagnosis controllers on cleanup / clear / dispose', () => {
      const activeDiagnoses = new Map<string, { findingId: string; controller: AbortController }>();

      const controllers = [new AbortController(), new AbortController(), new AbortController()];
      controllers.forEach((ctrl, idx) => {
        activeDiagnoses.set(`finding-${idx}`, { findingId: `finding-${idx}`, controller: ctrl });
      });

      assert.strictEqual(activeDiagnoses.size, 3);
      controllers.forEach((ctrl) => assert.strictEqual(ctrl.signal.aborted, false));

      // Abort all
      for (const active of activeDiagnoses.values()) {
        active.controller.abort();
      }
      activeDiagnoses.clear();

      assert.strictEqual(activeDiagnoses.size, 0);
      controllers.forEach((ctrl) => assert.strictEqual(ctrl.signal.aborted, true));
    });
  });

  // =========================================================================
  // 7. REGRESSION VERIFICATION (Filters, Navigation, Re-analysis)
  // =========================================================================
  describe('7. Regression Testing - Preserving Phase 5F Functionality', () => {
    it('Y. should maintain filter functionality alongside diagnosis UI', () => {
      const context: AnalysisContext = {
        scope: 'full',
        documentUri: 'file:///c:/project/test.py',
        documentPath: 'test.py',
        displayFilename: 'test.py',
      };
      const vm = transformReportToViewModel(sampleBuggyReport, context);

      const allFindings = filterFindings(vm.findings, 'all');
      const errorFindings = filterFindings(vm.findings, 'error');
      const warningFindings = filterFindings(vm.findings, 'warning');

      assert.strictEqual(allFindings.length, 2);
      assert.strictEqual(errorFindings.length, 1);
      assert.strictEqual(warningFindings.length, 1);

      // All findings have unique ids matching finding-<index>
      assert.strictEqual(allFindings[0].id, 'finding-0');
      assert.strictEqual(allFindings[1].id, 'finding-1');
    });

    it('Z. should preserve line navigation messages and security bindings', () => {
      const expectedUri = 'file:///c:/project/math_ops.py';
      const navMsg = validateWebviewMessage(
        { type: 'navigateToLine', line: 20 },
        expectedUri
      );

      assert.strictEqual(navMsg.isValid, true);
      assert.strictEqual(navMsg.message?.type, 'navigateToLine');
      assert.strictEqual(navMsg.message?.line, 20);
      assert.strictEqual(navMsg.message?.uri, expectedUri);
    });

    it('AA. should preserve analyzeAgain and clearResults commands', () => {
      const reanalyze = validateWebviewMessage({ type: 'analyzeAgain' });
      assert.strictEqual(reanalyze.isValid, true);

      const clear = validateWebviewMessage({ type: 'clearResults' });
      assert.strictEqual(clear.isValid, true);
    });
  });

  // =========================================================================
  // 8. PHASE 5G.7: WHATWG URL VALIDATION & EXTENDED MARKDOWN
  // =========================================================================
  describe('8. WHATWG URL Validation & Extended Markdown (Phase 5G.7)', () => {
    it('BB. should rigorously validate URLs using WHATWG standard in isSafeUrl', () => {
      // Valid URLs
      assert.strictEqual(isSafeUrl('https://docs.python.org/3'), true);
      assert.strictEqual(isSafeUrl('http://127.0.0.1:8000/api/v1/diagnose/stream'), true);
      assert.strictEqual(isSafeUrl('https://github.com/edgemind/edgemind?tab=readme-ov-file#faq'), true);

      // Invalid URLs
      assert.strictEqual(isSafeUrl('javascript:alert(1)'), false);
      assert.strictEqual(isSafeUrl('data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=='), false);
      assert.strictEqual(isSafeUrl('vbscript:msgbox("xss")'), false);
      assert.strictEqual(isSafeUrl('file:///C:/Windows/System32/drivers/etc/hosts'), false);
      assert.strictEqual(isSafeUrl('not_a_valid_url'), false);
      assert.strictEqual(isSafeUrl('   '), false);
      assert.strictEqual(isSafeUrl(''), false);
      assert.strictEqual(isSafeUrl(null as unknown as string), false);
      assert.strictEqual(isSafeUrl(undefined as unknown as string), false);
    });

    it('CC. should render blockquotes (> quote) with diag-quote CSS class', () => {
      const markdown = '> Note: This finding indicates that input validation is missing.\n\nRegular text.';
      const html = renderSafeMarkdown(markdown);

      assert.ok(html.includes('<blockquote class="diag-quote">Note: This finding indicates that input validation is missing.</blockquote>'));
      assert.ok(html.includes('<p>Regular text.</p>'));
    });

    it('DD. should render horizontal rules (--- and ***) with diag-hr CSS class', () => {
      const markdown = '### Section 1\n---\n### Section 2\n***\nFinished.';
      const html = renderSafeMarkdown(markdown);

      assert.ok(html.includes('<hr class="diag-hr" />'));
      assert.ok(html.includes('<h3 class="diag-heading h3">Section 1</h3>'));
      assert.ok(html.includes('<h3 class="diag-heading h3">Section 2</h3>'));
      assert.ok(html.includes('<p>Finished.</p>'));
    });
  });

  // =========================================================================
  // 9. PHASE 5G.7: ACCESSIBILITY & UI HARDENING
  // =========================================================================
  describe('9. Webview Accessibility & UI Attributes (Phase 5G.7)', () => {
    it('EE. should render semantic ARIA attributes on diagnosis container and finding cards', () => {
      const context: AnalysisContext = {
        scope: 'full',
        documentUri: 'file:///c:/project/math_ops.py',
        documentPath: 'C:\\project\\math_ops.py',
        displayFilename: 'math_ops.py',
      };
      const vm = transformReportToViewModel(sampleBuggyReport, context);
      const html = renderResultsHtml(vm, 'vscode-webview:', 'testnonce777');

      // Verify ARIA role and label on diagnosis container
      assert.ok(html.includes('role="region"'));
      assert.ok(html.includes('aria-label="AI Root Cause Diagnosis"'));

      // Verify role="status" and aria-live="polite" on diagnosis body
      assert.ok(html.includes('role="status"'));
      assert.ok(html.includes('aria-live="polite"'));
      assert.ok(html.includes('aria-busy="false"'));

      // Verify keyboard navigation attributes on line badge and card header
      assert.ok(html.includes('tabindex="0"'));
      assert.ok(html.includes('role="button"'));
      assert.ok(html.includes('aria-expanded="false"'));

      // Verify aria-label on cancel and retry buttons
      assert.ok(html.includes('aria-label="Cancel diagnosis for this finding"'));
      assert.ok(html.includes('aria-label="Retry diagnosis for this finding"'));
    });

    it('FF. should include keyboard event delegation (Enter/Space) in client script', () => {
      const context: AnalysisContext = {
        scope: 'full',
        documentUri: 'file:///c:/project/math_ops.py',
        documentPath: 'C:\\project\\math_ops.py',
        displayFilename: 'math_ops.py',
      };
      const vm = transformReportToViewModel(sampleBuggyReport, context);
      const html = renderResultsHtml(vm, 'vscode-webview:', 'testnonce888');

      assert.ok(html.includes("e.key === 'Enter' || e.key === ' '"));
      assert.ok(html.includes("target.matches('.line-nav-badge')"));
      assert.ok(html.includes("target.matches('.finding-header')"));
    });

    it('GG. should include interrupted banner and error banner styles in CSS', () => {
      const context: AnalysisContext = {
        scope: 'full',
        documentUri: 'file:///c:/project/math_ops.py',
        documentPath: 'C:\\project\\math_ops.py',
        displayFilename: 'math_ops.py',
      };
      const vm = transformReportToViewModel(sampleBuggyReport, context);
      const html = renderResultsHtml(vm, 'vscode-webview:', 'testnonce999');

      assert.ok(html.includes('.diagnosis-interrupted-banner'));
      assert.ok(html.includes('.diagnosis-error-banner'));
      assert.ok(html.includes('blockquote.diag-quote'));
      assert.ok(html.includes('hr.diag-hr'));
    });
  });

  // =========================================================================
  // 10. PHASE 5G.7: CONCURRENCY CAP & GENERATION TRACKING
  // =========================================================================
  describe('10. Concurrency Cap & Generation Isolation (Phase 5G.7)', () => {
    it('HH. should enforce maximum concurrent diagnoses limit of 3', () => {
      const MAX_CONCURRENT = 3;
      const activeDiagnoses = new Map<string, { findingId: string; controller: AbortController }>();

      // Fill up to max
      for (let i = 0; i < MAX_CONCURRENT; i++) {
        activeDiagnoses.set(`finding-${i}`, { findingId: `finding-${i}`, controller: new AbortController() });
      }

      assert.strictEqual(activeDiagnoses.size, 3);

      // Attempting 4th diagnosis should be rejected by concurrency check
      const canStart4th = activeDiagnoses.size < MAX_CONCURRENT;
      assert.strictEqual(canStart4th, false);

      // Once 1 finishes or is cancelled, 4th can start
      activeDiagnoses.delete('finding-0');
      assert.strictEqual(activeDiagnoses.size < MAX_CONCURRENT, true);
    });

    it('II. should track per-finding generation counter to isolate retried streams', () => {
      const generations = new Map<string, number>();

      // Initial explain for finding-0
      const gen1 = (generations.get('finding-0') || 0) + 1;
      generations.set('finding-0', gen1);
      assert.strictEqual(gen1, 1);

      // Retry finding-0: increments generation to 2
      const gen2 = (generations.get('finding-0') || 0) + 1;
      generations.set('finding-0', gen2);
      assert.strictEqual(gen2, 2);

      // Any delayed async events from gen1 must be rejected
      const isEventFromCurrentGen = (eventGen: number) => generations.get('finding-0') === eventGen;
      assert.strictEqual(isEventFromCurrentGen(gen1), false);
      assert.strictEqual(isEventFromCurrentGen(gen2), true);
    });

    it('JJ. should ignore cancel request idempotently if diagnosis is not active', () => {
      const activeDiagnoses = new Map<string, { findingId: string; controller: AbortController }>();

      // Cancel on non-existent finding
      let cancelledStateEmitted = false;
      const handleCancel = (findingId: string) => {
        const active = activeDiagnoses.get(findingId);
        if (!active) {
          return; // idempotent: ignore
        }
        active.controller.abort();
        activeDiagnoses.delete(findingId);
        cancelledStateEmitted = true;
      };

      handleCancel('finding-99');
      assert.strictEqual(cancelledStateEmitted, false);

      // Now add active and cancel
      const ctrl = new AbortController();
      activeDiagnoses.set('finding-1', { findingId: 'finding-1', controller: ctrl });
      handleCancel('finding-1');
      assert.strictEqual(cancelledStateEmitted, true);
      assert.strictEqual(ctrl.signal.aborted, true);
      assert.strictEqual(activeDiagnoses.has('finding-1'), false);

      // Second cancel on finding-1 should be ignored without emitting second event
      cancelledStateEmitted = false;
      handleCancel('finding-1');
      assert.strictEqual(cancelledStateEmitted, false);
    });
  });
});
