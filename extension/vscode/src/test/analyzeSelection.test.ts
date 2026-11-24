import { describe, it, before, after } from 'node:test';
import * as assert from 'node:assert';
import * as http from 'node:http';
import { ApiClient } from '../api/client';
import { validateEditorSelection, MAX_SOURCE_SIZE_BYTES } from '../utils/editorValidator';
import { formatReportOutput, formatSummaryNotification } from '../utils/reportFormatter';
import { AnalysisReport } from '../types/api';

describe('EdgeMind Phase 5D: Analyze Selection Tests', () => {
  describe('Selection Validation (validateEditorSelection)', () => {
    it('1. should reject when active editor is undefined', () => {
      const res = validateEditorSelection(undefined, undefined, false, undefined);
      assert.strictEqual(res.isValid, false);
      if (!res.isValid) {
        assert.ok(res.errorMessage.includes('No active editor found'));
      }
    });

    it('2. should reject when file is not Python by extension or languageId', () => {
      const res = validateEditorSelection(
        'server.ts',
        'typescript',
        true,
        'const x: number = 42;',
        1,
        1
      );
      assert.strictEqual(res.isValid, false);
      if (!res.isValid) {
        assert.ok(res.errorMessage.includes('supports Python files (.py) only'));
        assert.ok(res.errorMessage.includes('server.ts'));
      }
    });

    it('3. should reject when no selection is made (empty selection range)', () => {
      const res = validateEditorSelection(
        'calc.py',
        'python',
        false, // hasSelection = false
        '',
        10,
        10
      );
      assert.strictEqual(res.isValid, false);
      if (!res.isValid) {
        assert.ok(res.errorMessage.includes('No code selected'));
      }
    });

    it('4. should reject whitespace-only selection', () => {
      const res = validateEditorSelection(
        'calc.py',
        'python',
        true,
        '   \n\t   \n  ',
        5,
        7
      );
      assert.strictEqual(res.isValid, false);
      if (!res.isValid) {
        assert.ok(res.errorMessage.includes('Selected code is empty or whitespace-only'));
      }
    });

    it('5. should reject selection exceeding 64 KiB size limit without truncation', () => {
      const oversizedSnippet = 'x = 1\n'.repeat(15000); // ~90 KiB
      assert.ok(Buffer.byteLength(oversizedSnippet, 'utf8') > MAX_SOURCE_SIZE_BYTES);

      const res = validateEditorSelection(
        'big.py',
        'python',
        true,
        oversizedSnippet,
        1,
        15000
      );
      assert.strictEqual(res.isValid, false);
      if (!res.isValid) {
        assert.ok(res.errorMessage.includes('exceeds the maximum allowed limit of 64 KiB'));
      }
    });

    it('6. should accept valid single-line selection', () => {
      const res = validateEditorSelection(
        'C:\\Users\\DELL\\Projects\\calc.py',
        'python',
        true,
        'return a / b',
        15,
        15
      );
      assert.strictEqual(res.isValid, true);
      if (res.isValid) {
        assert.strictEqual(res.displayFilename, 'calc.py');
        assert.strictEqual(res.code, 'return a / b');
        assert.strictEqual(res.startLine, 15);
        assert.strictEqual(res.endLine, 15);
        assert.strictEqual(res.scopeLabel, 'Selection: Line 15');
        assert.strictEqual(res.sizeBytes, 12);
      }
    });

    it('7. should accept valid multi-line selection', () => {
      const code = 'def helper():\n    x = 10\n    return x * 2\n';
      const res = validateEditorSelection(
        '/home/user/workspace/utils.py',
        'python',
        true,
        code,
        10,
        13
      );
      assert.strictEqual(res.isValid, true);
      if (res.isValid) {
        assert.strictEqual(res.displayFilename, 'utils.py');
        assert.strictEqual(res.code, code);
        assert.strictEqual(res.startLine, 10);
        assert.strictEqual(res.endLine, 13);
        assert.strictEqual(res.scopeLabel, 'Selection: Lines 10-13');
      }
    });

    it('8. should accept buffer by languageId when filename has no extension', () => {
      const res = validateEditorSelection(
        'Untitled-2',
        'python',
        true,
        'print("hello from scratch")',
        1,
        1
      );
      assert.strictEqual(res.isValid, true);
      if (res.isValid) {
        assert.strictEqual(res.displayFilename, 'Untitled-2');
      }
    });
  });

  describe('Selection Report Formatting (reportFormatter)', () => {
    const sampleSelectionReport: AnalysisReport = {
      file_path: 'calc.py',
      file: 'calc.py',
      overall_status: 'FAIL',
      status: 'FAIL',
      score: 70,
      total_errors: 1,
      total_warnings: 0,
      syntax_status: 'PASS',
      runtime_status: 'SKIPPED',
      logic_status: 'FAIL',
      quality_status: 'PASS',
      complexity_status: 'PASS',
      errors: [
        {
          type: 'ZeroDivisionError',
          line: 2,
          line_number: 2,
          message: 'Division by zero detected',
          why: 'Expression divides by 0',
          explanation: 'Dividing by zero raises ZeroDivisionError',
          fix: 'Ensure divisor is not zero',
          suggested_fix: 'Ensure divisor is not zero',
          concept: 'Arithmetic Safety',
        },
      ],
      warnings: [],
      summary: {
        syntax: 'PASS',
        runtime: 'SKIPPED',
        logic: 'FAIL',
        quality: 'PASS',
        complexity: 'PASS',
      },
    };

    it('should format summary notification with selection scope label', () => {
      const summary = formatSummaryNotification(sampleSelectionReport, 'Selection: Lines 12-15');
      assert.strictEqual(
        summary,
        "EdgeMind Analysis for 'calc.py' (Selection: Lines 12-15): FAIL (Score: 70/100) — 1 error(s), 0 warning(s)."
      );
    });

    it('should format detailed OutputChannel report with selection scope label', () => {
      const output = formatReportOutput(sampleSelectionReport, 55, 'Selection: Lines 12-15');
      assert.ok(output.includes('EDGEMIND STATIC CODE ANALYSIS REPORT'));
      assert.ok(output.includes('File:             calc.py'));
      assert.ok(output.includes('Scope:            Selection: Lines 12-15'));
      assert.ok(output.includes('Overall Status:   FAIL'));
      assert.ok(output.includes('Score:            70/100'));
      assert.ok(output.includes('Latency:          55ms'));
      assert.ok(output.includes('ERRORS (1):'));
      assert.ok(output.includes('[1] Line 2: ZeroDivisionError — Division by zero detected'));
    });
  });

  describe('Backend Integration & ApiClient for Selection', () => {
    let mockServer: http.Server;
    let serverPort: number;
    let lastRequestBody: string = '';
    let responseCode = 200;
    let responseBody = '';
    let delayMs = 0;

    before(async () => {
      mockServer = http.createServer((req, res) => {
        let body = '';
        req.on('data', (chunk) => {
          body += chunk;
        });
        req.on('end', () => {
          lastRequestBody = body;
          setTimeout(() => {
            if (req.url === '/api/v1/analyze' && req.method === 'POST') {
              res.writeHead(responseCode, { 'Content-Type': 'application/json' });
              res.end(responseBody);
            } else {
              res.writeHead(404, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ error: 'Not Found' }));
            }
          }, delayMs);
        });
      });

      await new Promise<void>((resolve) => {
        mockServer.listen(0, '127.0.0.1', () => {
          const addr = mockServer.address();
          if (addr && typeof addr === 'object') {
            serverPort = addr.port;
          }
          resolve();
        });
      });
    });

    after(async () => {
      await new Promise<void>((resolve) => {
        mockServer.close(() => resolve());
      });
    });

    it('should send only the selected code to backend and return successful report', async () => {
      const selectedSnippet = 'def square(n):\n    return n * n\n';
      const mockReport: AnalysisReport = {
        file_path: 'math_lib.py',
        file: 'math_lib.py',
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

      responseCode = 200;
      responseBody = JSON.stringify(mockReport);
      delayMs = 0;

      const client = new ApiClient({
        baseUrl: `http://127.0.0.1:${serverPort}`,
      });

      const res = await client.analyzeCode({
        code: selectedSnippet,
        filename: 'math_lib.py',
        static_only: true,
      });

      assert.strictEqual(res.success, true);
      assert.strictEqual(res.statusCode, 200);
      assert.ok(res.data);
      assert.strictEqual(res.data.score, 100);

      // Verify that ONLY the selected snippet was transmitted
      const parsedBody = JSON.parse(lastRequestBody);
      assert.strictEqual(parsedBody.code, selectedSnippet);
      assert.strictEqual(parsedBody.filename, 'math_lib.py');
      assert.strictEqual(parsedBody.static_only, true);
    });

    it('should handle backend analysis failure (HTTP 400 Bad Request)', async () => {
      responseCode = 400;
      responseBody = JSON.stringify({
        error: 'Bad Request',
        detail: 'Syntax error in submitted Python code: unexpected EOF while parsing',
      });
      delayMs = 0;

      const client = new ApiClient({
        baseUrl: `http://127.0.0.1:${serverPort}`,
      });

      const res = await client.analyzeCode({
        code: 'def incomplete_func(',
        filename: 'snippet.py',
        static_only: true,
      });

      assert.strictEqual(res.success, false);
      assert.strictEqual(res.statusCode, 400);
      assert.ok(res.error);
      assert.ok(res.error.includes('Syntax error in submitted Python code'));
    });

    it('should respect AbortSignal cancellation during selection analysis', async () => {
      responseCode = 200;
      responseBody = JSON.stringify({});
      delayMs = 250;

      const client = new ApiClient({
        baseUrl: `http://127.0.0.1:${serverPort}`,
      });

      const controller = new AbortController();
      setTimeout(() => controller.abort(), 40);

      const res = await client.analyzeCode(
        { code: 'x = 1', filename: 'calc.py', static_only: true },
        { signal: controller.signal }
      );

      assert.strictEqual(res.success, false);
      assert.ok(res.error);
      assert.ok(
        res.error.includes('cancelled') || res.error.includes('timed out'),
        `Expected cancellation error, got: ${res.error}`
      );
    });
  });
});
