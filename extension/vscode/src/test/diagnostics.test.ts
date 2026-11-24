import { describe, it } from 'node:test';
import * as assert from 'node:assert';
import {
  EdgeMindDiagnosticSeverity,
  calculateAbsoluteLine,
  calculateDiagnosticRange,
  formatDiagnosticMessage,
  mapFindingSeverity,
  mapFindingToDiagnostic,
  mapReportToDiagnostics,
  mergeSelectionDiagnostics,
  EdgeMindDiagnostic,
} from '../utils/diagnosticData';
import { AnalysisReport, ReportFinding } from '../types/api';

describe('EdgeMind Phase 5E: VS Code Diagnostics Tests', () => {
  describe('1. Severity Mapping (mapFindingSeverity)', () => {
    it('should map report error to DiagnosticSeverity.Error', () => {
      const finding: ReportFinding = {
        type: 'ZeroDivisionError',
        line: 3,
        line_number: 3,
        message: 'Division by zero',
        why: '',
        explanation: '',
        fix: '',
        suggested_fix: '',
        concept: '',
      };
      const severity = mapFindingSeverity(finding, EdgeMindDiagnosticSeverity.Error);
      assert.strictEqual(severity, EdgeMindDiagnosticSeverity.Error);
      assert.strictEqual(severity, 0);
    });

    it('should map report warning to DiagnosticSeverity.Warning', () => {
      const finding: ReportFinding = {
        type: 'UnusedVariable',
        line: 2,
        line_number: 2,
        message: 'Unused variable x',
        why: '',
        explanation: '',
        fix: '',
        suggested_fix: '',
        concept: '',
      };
      const severity = mapFindingSeverity(finding, EdgeMindDiagnosticSeverity.Warning);
      assert.strictEqual(severity, EdgeMindDiagnosticSeverity.Warning);
      assert.strictEqual(severity, 1);
    });

    it('should map explicit info severity or Info type to DiagnosticSeverity.Information', () => {
      const findingInfoSeverity: ReportFinding = {
        type: 'StyleSuggestion',
        line: 5,
        line_number: 5,
        message: 'Consider PEP 8 formatting',
        why: '',
        explanation: '',
        fix: '',
        suggested_fix: '',
        concept: '',
        severity: 'info',
      };
      const severity1 = mapFindingSeverity(findingInfoSeverity, EdgeMindDiagnosticSeverity.Warning);
      assert.strictEqual(severity1, EdgeMindDiagnosticSeverity.Information);
      assert.strictEqual(severity1, 2);

      const findingInfoType: ReportFinding = {
        type: 'InfoComplexity',
        line: 8,
        line_number: 8,
        message: 'Low cyclomatic complexity',
        why: '',
        explanation: '',
        fix: '',
        suggested_fix: '',
        concept: '',
      };
      const severity2 = mapFindingSeverity(findingInfoType, EdgeMindDiagnosticSeverity.Warning);
      assert.strictEqual(severity2, EdgeMindDiagnosticSeverity.Information);
    });
  });

  describe('2. Source Label & Message Formatting (formatDiagnosticMessage)', () => {
    it('should set diagnostic source to EdgeMind and code to finding type', () => {
      const finding: ReportFinding = {
        type: 'ZeroDivisionError',
        line: 10,
        line_number: 10,
        message: 'Division by zero detected',
        why: 'Denominator is 0',
        explanation: 'Denominator is 0',
        fix: 'Add guard check',
        suggested_fix: 'Add guard check',
        concept: 'Arithmetic Safety',
      };
      const diagnostic = mapFindingToDiagnostic(finding, EdgeMindDiagnosticSeverity.Error);
      assert.strictEqual(diagnostic.source, 'EdgeMind');
      assert.strictEqual(diagnostic.code, 'ZeroDivisionError');
    });

    it('should format multi-line diagnostic message with why, fix, and concept', () => {
      const finding: ReportFinding = {
        type: 'ZeroDivisionError',
        line: 10,
        line_number: 10,
        message: 'Division by zero detected',
        why: 'Denominator evaluated to 0',
        explanation: 'Denominator evaluated to 0',
        fix: 'Add denominator != 0 check',
        suggested_fix: 'Add denominator != 0 check',
        concept: 'Math Operations',
      };
      const msg = formatDiagnosticMessage(finding);
      assert.ok(msg.includes('Division by zero detected'));
      assert.ok(msg.includes('Why: Denominator evaluated to 0'));
      assert.ok(msg.includes('Fix: Add denominator != 0 check'));
      assert.ok(msg.includes('Concept: Math Operations'));
    });
  });

  describe('3. Line Conversion & Line Mapping (calculateAbsoluteLine)', () => {
    it('should convert 1-based line to 0-based index for full file', () => {
      // Backend line 1 -> VS Code index 0
      assert.strictEqual(calculateAbsoluteLine(1), 0);
      // Backend line 42 -> VS Code index 41
      assert.strictEqual(calculateAbsoluteLine(42), 41);
    });

    it('should map full-file findings accurately', () => {
      const line = calculateAbsoluteLine(15, undefined, 100);
      assert.strictEqual(line, 14); // 0-based 14 is line 15
    });

    it('should map snippet-relative line to absolute document line for selection', () => {
      // Selection starts at document line 15 (1-based)
      // Snippet finding on snippet line 1 -> document line 15 (0-based index 14)
      assert.strictEqual(calculateAbsoluteLine(1, 15, 100), 14);
      // Snippet finding on snippet line 3 -> document line 17 (0-based index 16)
      assert.strictEqual(calculateAbsoluteLine(3, 15, 100), 16);
    });

    it('should map selection starting far into the file correctly', () => {
      // Selection starts at document line 500 (1-based)
      // Snippet finding on snippet line 5 -> document line 504 (0-based index 503)
      assert.strictEqual(calculateAbsoluteLine(5, 500, 1000), 503);
    });

    it('should handle single-line selection correctly', () => {
      // Selection is on line 25 (1-based)
      // Finding on line 1 -> document line 25 (0-based index 24)
      assert.strictEqual(calculateAbsoluteLine(1, 25, 50), 24);
    });

    it('should handle missing line numbers safely by falling back to base line', () => {
      // Full file with missing line -> line 0
      assert.strictEqual(calculateAbsoluteLine(undefined), 0);
      assert.strictEqual(calculateAbsoluteLine(null), 0);

      // Selection starting at line 30 with missing line -> line 30 (0-based index 29)
      assert.strictEqual(calculateAbsoluteLine(undefined, 30, 100), 29);
      assert.strictEqual(calculateAbsoluteLine(null, 30, 100), 29);
    });

    it('should handle invalid (0 or negative or NaN) line numbers safely', () => {
      assert.strictEqual(calculateAbsoluteLine(0), 0);
      assert.strictEqual(calculateAbsoluteLine(-10), 0);
      assert.strictEqual(calculateAbsoluteLine(NaN), 0);

      assert.strictEqual(calculateAbsoluteLine(0, 20, 100), 19);
      assert.strictEqual(calculateAbsoluteLine(-5, 20, 100), 19);
    });

    it('should clamp out-of-range line numbers within document bounds', () => {
      // Document has 50 lines (maxLineIndex = 49)
      // Finding reports line 200 -> clamped to index 49
      assert.strictEqual(calculateAbsoluteLine(200, undefined, 49), 49);
      // Selection starts at line 40, snippet line 20 -> 40 + 19 = 59, clamped to 49
      assert.strictEqual(calculateAbsoluteLine(20, 40, 49), 49);
    });
  });

  describe('4. Character Range Calculation (calculateDiagnosticRange)', () => {
    it('should trim leading whitespace from diagnostic squiggly range', () => {
      const mockGetLineText = (line0: number) => {
        if (line0 === 3) return '    return 10 / 0';
        return '';
      };
      const range = calculateDiagnosticRange(3, mockGetLineText);
      assert.strictEqual(range.startLine, 3);
      assert.strictEqual(range.startChar, 4); // First non-whitespace char
      assert.strictEqual(range.endLine, 3);
      assert.strictEqual(range.endChar, 17); // End of line
    });

    it('should handle blank lines gracefully without 0-width error', () => {
      const mockGetLineText = () => '   ';
      const range = calculateDiagnosticRange(5, mockGetLineText);
      assert.strictEqual(range.startLine, 5);
      assert.strictEqual(range.startChar, 0);
      assert.strictEqual(range.endChar, 3);
    });
  });

  describe('5. Full Report Mapping (mapReportToDiagnostics)', () => {
    const mockReport: AnalysisReport = {
      file_path: 'app.py',
      file: 'app.py',
      overall_status: 'FAIL',
      status: 'FAIL',
      score: 60,
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
          line: 4,
          line_number: 4,
          message: 'Division by zero',
          why: 'Divisor is literal zero',
          explanation: 'Divisor is literal zero',
          fix: 'Check divisor',
          suggested_fix: 'Check divisor',
          concept: 'Math',
        },
      ],
      warnings: [
        {
          type: 'UnusedVariable',
          line: 2,
          line_number: 2,
          message: "Variable 'x' is unused",
          why: 'Dead code',
          explanation: 'Dead code',
          fix: "Remove 'x'",
          suggested_fix: "Remove 'x'",
          concept: 'Code Quality',
        },
        {
          type: 'MagicNumber',
          line: 3,
          line_number: 3,
          message: "Magic number '42' detected",
          why: 'Hardcoded literal',
          explanation: 'Hardcoded literal',
          fix: 'Define constant',
          suggested_fix: 'Define constant',
          concept: 'Code Smells',
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

    it('should map multiple findings across errors and warnings', () => {
      const diagnostics = mapReportToDiagnostics(mockReport);
      assert.strictEqual(diagnostics.length, 3);

      const errDiag = diagnostics.find((d) => d.code === 'ZeroDivisionError');
      assert.ok(errDiag);
      assert.strictEqual(errDiag.severity, EdgeMindDiagnosticSeverity.Error);
      assert.strictEqual(errDiag.range.startLine, 3); // line 4 -> index 3

      const warn1 = diagnostics.find((d) => d.code === 'UnusedVariable');
      assert.ok(warn1);
      assert.strictEqual(warn1.severity, EdgeMindDiagnosticSeverity.Warning);
      assert.strictEqual(warn1.range.startLine, 1); // line 2 -> index 1

      const warn2 = diagnostics.find((d) => d.code === 'MagicNumber');
      assert.ok(warn2);
      assert.strictEqual(warn2.severity, EdgeMindDiagnosticSeverity.Warning);
      assert.strictEqual(warn2.range.startLine, 2); // line 3 -> index 2
    });
  });

  describe('6. Stale Diagnostics Replacement (mergeSelectionDiagnostics)', () => {
    it('should replace stale findings in selection range while preserving outer findings', () => {
      const existing: EdgeMindDiagnostic[] = [
        {
          range: { startLine: 4, startChar: 0, endLine: 4, endChar: 20 },
          message: 'Top-level unused import',
          severity: EdgeMindDiagnosticSeverity.Warning,
          source: 'EdgeMind',
          code: 'UnusedImport',
        },
        {
          range: { startLine: 15, startChar: 4, endLine: 15, endChar: 25 },
          message: 'Old stale error in selection',
          severity: EdgeMindDiagnosticSeverity.Error,
          source: 'EdgeMind',
          code: 'OldError',
        },
        {
          range: { startLine: 35, startChar: 0, endLine: 35, endChar: 30 },
          message: 'Bottom-level warning',
          severity: EdgeMindDiagnosticSeverity.Warning,
          source: 'EdgeMind',
          code: 'MagicNumber',
        },
      ];

      // New findings in selection lines 15..20 (0-based: 14..19)
      const newFindings: EdgeMindDiagnostic[] = [
        {
          range: { startLine: 15, startChar: 4, endLine: 15, endChar: 25 },
          message: 'Newly confirmed ZeroDivisionError',
          severity: EdgeMindDiagnosticSeverity.Error,
          source: 'EdgeMind',
          code: 'ZeroDivisionError',
        },
        {
          range: { startLine: 17, startChar: 4, endLine: 17, endChar: 20 },
          message: 'New unused variable',
          severity: EdgeMindDiagnosticSeverity.Warning,
          source: 'EdgeMind',
          code: 'UnusedVariable',
        },
      ];

      const merged = mergeSelectionDiagnostics(existing, newFindings, 14, 19);

      assert.strictEqual(merged.length, 4);

      // Outer findings preserved
      assert.ok(merged.some((d) => d.code === 'UnusedImport' && d.range.startLine === 4));
      assert.ok(merged.some((d) => d.code === 'MagicNumber' && d.range.startLine === 35));

      // Stale finding replaced
      assert.strictEqual(merged.some((d) => d.code === 'OldError'), false);

      // New findings present
      assert.ok(merged.some((d) => d.code === 'ZeroDivisionError' && d.range.startLine === 15));
      assert.ok(merged.some((d) => d.code === 'UnusedVariable' && d.range.startLine === 17));
    });
  });

  describe('7. Lifecycle & Cleanup Verification', () => {
    it('should support setting, getting, deleting, and clearing diagnostic entries', () => {
      // Mock collection implementation matching vscode.DiagnosticCollection contract
      const store = new Map<string, EdgeMindDiagnostic[]>();
      const mockCollection = {
        set: (uri: string, diags: EdgeMindDiagnostic[]) => store.set(uri, diags),
        get: (uri: string) => store.get(uri) || [],
        delete: (uri: string) => store.delete(uri),
        clear: () => store.clear(),
      };

      const fileA = 'file:///workspace/a.py';
      const fileB = 'file:///workspace/b.py';

      mockCollection.set(fileA, [
        {
          range: { startLine: 1, startChar: 0, endLine: 1, endChar: 10 },
          message: 'Error in A',
          severity: EdgeMindDiagnosticSeverity.Error,
          source: 'EdgeMind',
          code: 'ErrA',
        },
      ]);
      mockCollection.set(fileB, [
        {
          range: { startLine: 2, startChar: 0, endLine: 2, endChar: 10 },
          message: 'Error in B',
          severity: EdgeMindDiagnosticSeverity.Error,
          source: 'EdgeMind',
          code: 'ErrB',
        },
      ]);

      assert.strictEqual(mockCollection.get(fileA).length, 1);
      assert.strictEqual(mockCollection.get(fileB).length, 1);

      // Closing document fileA should delete only fileA
      mockCollection.delete(fileA);
      assert.strictEqual(mockCollection.get(fileA).length, 0);
      assert.strictEqual(mockCollection.get(fileB).length, 1); // fileB preserved!

      // Explicit clear removes all
      mockCollection.clear();
      assert.strictEqual(mockCollection.get(fileB).length, 0);
    });
  });
});
