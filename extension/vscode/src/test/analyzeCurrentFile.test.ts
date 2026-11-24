import { describe, it, before, after } from 'node:test';
import * as assert from 'node:assert';
import * as http from 'node:http';
import { ApiClient } from '../api/client';
import { validateEditorDocument, MAX_SOURCE_SIZE_BYTES } from '../utils/editorValidator';
import { formatReportOutput, formatSummaryNotification } from '../utils/reportFormatter';
import { AnalysisReport } from '../types/api';

describe('EdgeMind Phase 5C: Editor Validation & Report Formatting Tests', () => {
  describe('Editor Document Validation (validateEditorDocument)', () => {
    it('should reject when active editor document is undefined', () => {
      const res = validateEditorDocument(undefined, undefined, undefined);
      assert.strictEqual(res.isValid, false);
      if (!res.isValid) {
        assert.ok(res.errorMessage.includes('No active editor found'));
      }
    });

    it('should reject non-Python files by extension and languageId', () => {
      const res = validateEditorDocument('app.js', 'javascript', 'console.log("hello");');
      assert.strictEqual(res.isValid, false);
      if (!res.isValid) {
        assert.ok(res.errorMessage.includes('supports Python files (.py) only'));
        assert.ok(res.errorMessage.includes('app.js'));
      }
    });

    it('should accept Python file by .py extension even if languageId is unset', () => {
      const res = validateEditorDocument('script.py', undefined, 'x = 1\nprint(x)\n');
      assert.strictEqual(res.isValid, true);
      if (res.isValid) {
        assert.strictEqual(res.displayFilename, 'script.py');
        assert.strictEqual(res.code, 'x = 1\nprint(x)\n');
        assert.strictEqual(res.sizeBytes, 15);
      }
    });

    it('should accept Python buffer by languageId even if extension is not .py', () => {
      const res = validateEditorDocument('Untitled-1', 'python', 'def foo(): pass');
      assert.strictEqual(res.isValid, true);
      if (res.isValid) {
        assert.strictEqual(res.displayFilename, 'Untitled-1');
      }
    });

    it('should sanitize absolute paths to clean display filename', () => {
      const windowsPath = 'C:\\Users\\DELL\\Projects\\EdgeMind\\models\\user.py';
      const res = validateEditorDocument(windowsPath, 'python', 'class User: pass');
      assert.strictEqual(res.isValid, true);
      if (res.isValid) {
        assert.strictEqual(res.displayFilename, 'user.py');
      }
    });

    it('should reject empty source code', () => {
      const res = validateEditorDocument('empty.py', 'python', '');
      assert.strictEqual(res.isValid, false);
      if (!res.isValid) {
        assert.ok(res.errorMessage.includes('Cannot analyze an empty file'));
      }
    });

    it('should reject whitespace-only source code', () => {
      const res = validateEditorDocument('whitespace.py', 'python', '   \n\t   \n');
      assert.strictEqual(res.isValid, false);
      if (!res.isValid) {
        assert.ok(res.errorMessage.includes('Cannot analyze an empty file'));
      }
    });

    it('should reject files exceeding the 64 KiB size limit', () => {
      const oversizedText = 'x = 1\n'.repeat(15000); // ~90 KiB
      assert.ok(Buffer.byteLength(oversizedText, 'utf8') > MAX_SOURCE_SIZE_BYTES);

      const res = validateEditorDocument('large.py', 'python', oversizedText);
      assert.strictEqual(res.isValid, false);
      if (!res.isValid) {
        assert.ok(res.errorMessage.includes('exceeds the maximum allowed limit of 64 KiB'));
      }
    });

    it('should accept files within the 64 KiB size limit', () => {
      const validText = 'a = 1\n'.repeat(5000); // ~30 KiB
      const byteLen = Buffer.byteLength(validText, 'utf8');
      assert.ok(byteLen < MAX_SOURCE_SIZE_BYTES);

      const res = validateEditorDocument('valid_size.py', 'python', validText);
      assert.strictEqual(res.isValid, true);
      if (res.isValid) {
        assert.strictEqual(res.sizeBytes, byteLen);
      }
    });
  });

  describe('Report Formatting (reportFormatter)', () => {
    const sampleCleanReport: AnalysisReport = {
      file_path: 'clean_module.py',
      file: 'clean_module.py',
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
      file_path: 'buggy.py',
      file: 'buggy.py',
      overall_status: 'FAIL',
      status: 'FAIL',
      score: 75,
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
          line: 3,
          line_number: 3,
          message: 'Division by zero detected',
          why: 'Expression divides a number by literal zero',
          explanation: 'Dividing by zero raises ZeroDivisionError at runtime',
          fix: 'Check the denominator before dividing',
          suggested_fix: 'Check the denominator before dividing',
          concept: 'Arithmetic Safety',
        },
      ],
      warnings: [
        {
          type: 'UnusedVariable',
          line: 2,
          line_number: 2,
          message: "Variable 'unused_val' is assigned but never used",
          why: 'Dead store',
          explanation: 'Unused variables clutter code and waste memory',
          fix: "Remove 'unused_val' or prefix with underscore",
          suggested_fix: "Remove 'unused_val' or prefix with underscore",
          concept: 'Clean Code',
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

    it('should format one-line notification summary for clean report', () => {
      const summary = formatSummaryNotification(sampleCleanReport);
      assert.strictEqual(
        summary,
        "EdgeMind Analysis for 'clean_module.py': PASS (Score: 100/100) — 0 error(s), 0 warning(s)."
      );
    });

    it('should format one-line notification summary for buggy report', () => {
      const summary = formatSummaryNotification(sampleBuggyReport);
      assert.strictEqual(
        summary,
        "EdgeMind Analysis for 'buggy.py': FAIL (Score: 75/100) — 1 error(s), 1 warning(s)."
      );
    });

    it('should format detailed text report for clean code', () => {
      const formatted = formatReportOutput(sampleCleanReport, 45);
      assert.ok(formatted.includes('EDGEMIND STATIC CODE ANALYSIS REPORT'));
      assert.ok(formatted.includes('File:             clean_module.py'));
      assert.ok(formatted.includes('Score:            100/100'));
      assert.ok(formatted.includes('Latency:          45ms'));
      assert.ok(formatted.includes('No errors or warnings detected. Clean static code hygiene!'));
    });

    it('should format detailed text report with errors, warnings, and remediation guidance', () => {
      const formatted = formatReportOutput(sampleBuggyReport, 120);
      assert.ok(formatted.includes('Score:            75/100'));
      assert.ok(formatted.includes('ERRORS (1):'));
      assert.ok(formatted.includes('[1] Line 3: ZeroDivisionError — Division by zero detected'));
      assert.ok(formatted.includes('Why:     Expression divides a number by literal zero'));
      assert.ok(formatted.includes('Fix:     Check the denominator before dividing'));
      assert.ok(formatted.includes('Concept: Arithmetic Safety'));

      assert.ok(formatted.includes('WARNINGS (1):'));
      assert.ok(formatted.includes("[1] Line 2: UnusedVariable — Variable 'unused_val' is assigned but never used"));
      assert.ok(formatted.includes('Concept: Clean Code'));
    });
  });

  describe('ApiClient.analyzeCode Integration', () => {
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

    it('should dispatch POST /api/v1/analyze with correct payload and return report', async () => {
      const mockReport: AnalysisReport = {
        file_path: 'calc.py',
        file: 'calc.py',
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
        code: 'def add(a, b): return a + b\n',
        filename: 'calc.py',
        static_only: true,
      });

      assert.strictEqual(res.success, true);
      assert.strictEqual(res.statusCode, 200);
      assert.ok(res.data);
      assert.strictEqual(res.data.score, 100);
      assert.strictEqual(res.data.file, 'calc.py');

      // Verify request payload sent to backend
      const parsedBody = JSON.parse(lastRequestBody);
      assert.strictEqual(parsedBody.code, 'def add(a, b): return a + b\n');
      assert.strictEqual(parsedBody.filename, 'calc.py');
      assert.strictEqual(parsedBody.static_only, true);
    });

    it('should handle backend HTTP 400 Bad Request error detail', async () => {
      responseCode = 400;
      responseBody = JSON.stringify({
        error: 'Validation Error',
        detail: 'Source code exceeds maximum allowed size.',
      });
      delayMs = 0;

      const client = new ApiClient({
        baseUrl: `http://127.0.0.1:${serverPort}`,
      });

      const res = await client.analyzeCode({
        code: 'large code...',
        filename: 'large.py',
      });

      assert.strictEqual(res.success, false);
      assert.strictEqual(res.statusCode, 400);
      assert.ok(res.error);
      assert.ok(res.error.includes('Source code exceeds maximum allowed size'));
    });

    it('should respect AbortSignal cancellation', async () => {
      responseCode = 200;
      responseBody = JSON.stringify({});
      delayMs = 300;

      const client = new ApiClient({
        baseUrl: `http://127.0.0.1:${serverPort}`,
      });

      const controller = new AbortController();
      setTimeout(() => controller.abort(), 50);

      const res = await client.analyzeCode(
        { code: 'x = 1', filename: 'test.py' },
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
