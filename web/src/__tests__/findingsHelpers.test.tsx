import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { AnalysisReport } from '../types/api';
import { SSEParser } from '../utils/sseParser';
import { SafeMarkdown } from '../utils/safeMarkdown';
import {
  buildDiagnosisRequest,
  DEFAULT_FINDING_FILTERS,
  extractAvailableCategories,
  extractExplorerFindings,
  filterAndSortFindings,
  MAX_DIAGNOSIS_CONTEXT_BYTES,
} from '../utils/findingsHelpers';

const MOCK_REPORT: AnalysisReport = {
  file_path: 'calc.py',
  file: 'calc.py',
  overall_status: 'FAIL',
  status: 'FAIL',
  score: 65,
  total_errors: 1,
  total_warnings: 3,
  syntax_status: 'PASS',
  runtime_status: 'SKIPPED',
  logic_status: 'FAIL',
  quality_status: 'WARNING',
  complexity_status: 'PASS',
  errors: [
    {
      type: 'ZeroDivisionError',
      line: 12,
      line_number: 12,
      message: 'Division by zero detected on divisor.',
      why: 'Dividing by zero raises ZeroDivisionError.',
      explanation: 'Dividing by zero raises ZeroDivisionError.',
      fix: 'Check divisor != 0 before dividing.',
      suggested_fix: 'Check divisor != 0 before dividing.',
      concept: 'DIVISION AND ERROR HANDLING',
    },
  ],
  warnings: [
    {
      type: 'UnusedVariable',
      line: 4,
      line_number: 4,
      message: "Variable 'temp' is unused.",
      why: '',
      explanation: '',
      fix: '',
      suggested_fix: '',
      concept: 'CODE QUALITY',
    },
    {
      type: 'HighComplexity',
      line: 0,
      line_number: 0,
      message: 'Module exceeds recommended branching factor.',
      why: 'Deep nesting slows comprehension.',
      explanation: 'Deep nesting slows comprehension.',
      fix: 'Extract helper functions.',
      suggested_fix: 'Extract helper functions.',
      concept: 'COMPLEXITY',
    },
    {
      type: 'NamingConvention',
      line: 8,
      line_number: 8,
      message: 'Function name is not snake_case.',
      why: 'PEP 8 recommends snake_case.',
      explanation: 'PEP 8 recommends snake_case.',
      fix: 'Rename function.',
      suggested_fix: 'Rename function.',
      concept: 'CODE QUALITY',
    },
  ],
  summary: {
    syntax: 'PASS',
    runtime: 'SKIPPED',
    logic: 'FAIL',
    quality: 'WARNING',
    complexity: 'PASS',
  },
};

describe('SSEParser', () => {
  it('reassembles split chunks, handles CRLF/comments, and flushes trailing payload', () => {
    const parser = new SSEParser();
    const encoder = new TextEncoder();

    const part1 = encoder.encode(': heartbeat\r\nevent: diagnosis_started\r\ndata: {"session_id":');
    const part2 = encoder.encode('"diag_1","finding_id":"f1"}\r\n\r\nevent: response_chunk\ndata: {"chunk":"Hello 🚀"');
    const part3 = encoder.encode('}');

    const events = [
      ...Array.from(parser.feed(part1)),
      ...Array.from(parser.feed(part2)),
      ...Array.from(parser.feed(part3)),
    ];

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('diagnosis_started');
    expect(SSEParser.parseJsonData<{ session_id: string }>(events[0].data)?.session_id).toBe(
      'diag_1'
    );

    const trailing = parser.flush();
    expect(trailing).not.toBeNull();
    expect(trailing?.event).toBe('response_chunk');
    expect(SSEParser.parseJsonData<{ chunk: string }>(trailing!.data)?.chunk).toBe('Hello 🚀');
  });
});

describe('findingsHelpers', () => {
  it('extracts normalized findings without mutating original report and extracts real categories', () => {
    const originalSnapshot = JSON.stringify(MOCK_REPORT);
    const items = extractExplorerFindings(MOCK_REPORT);

    expect(items).toHaveLength(4);
    expect(items[0].severity).toBe('error');
    expect(items[2].line).toBeNull(); // line 0 normalized to null
    expect(extractAvailableCategories(items)).toEqual([
      'CODE QUALITY',
      'COMPLEXITY',
      'DIVISION AND ERROR HANDLING',
    ]);
    expect(JSON.stringify(MOCK_REPORT)).toBe(originalSnapshot);
  });

  it('filters and sorts deterministically while handling missing line numbers safely', () => {
    const items = extractExplorerFindings(MOCK_REPORT);

    const ascByLine = filterAndSortFindings(items, {
      ...DEFAULT_FINDING_FILTERS,
      sort: 'line-asc',
    });
    expect(ascByLine.map((i) => i.line)).toEqual([4, 8, 12, null]);

    const descByLine = filterAndSortFindings(items, {
      ...DEFAULT_FINDING_FILTERS,
      sort: 'line-desc',
    });
    expect(descByLine.map((i) => i.line)).toEqual([12, 8, 4, null]);

    const filtered = filterAndSortFindings(items, {
      search: 'unused',
      severity: 'warning',
      category: 'CODE QUALITY',
      sort: 'default',
    });
    expect(filtered).toHaveLength(1);
    expect(filtered[0].type).toBe('UnusedVariable');
  });

  it('prepares bounded ±15-line Python diagnosis context under 16 KiB and rejects invalid bounds', () => {
    const items = extractExplorerFindings(MOCK_REPORT);
    const lines = Array.from({ length: 40 }, (_, i) => `line_${i + 1} = ${i + 1}`);
    const sourceCode = lines.join('\n');

    const res = buildDiagnosisRequest(items[0], sourceCode, 'python');
    expect(res.unavailableReason).toBeNull();
    expect(res.request).not.toBeNull();
    expect(res.request?.context_start_line).toBe(1);
    expect(res.request?.context_end_line).toBe(27);
    expect(res.request?.finding.line).toBe(12);
    expect(new TextEncoder().encode(res.request!.code_context).length).toBeLessThanOrEqual(
      MAX_DIAGNOSIS_CONTEXT_BYTES
    );

    // Out-of-bounds finding line safely rejected
    const outOfBounds = buildDiagnosisRequest(items[0], 'a = 1\nb = 2\n', 'python');
    expect(outOfBounds.request).toBeNull();
    expect(outOfBounds.unavailableReason).toContain('outside');

    // Empty source safely rejected
    const emptySrc = buildDiagnosisRequest(items[0], '   ', 'python');
    expect(emptySrc.request).toBeNull();
    expect(emptySrc.unavailableReason).toContain('unavailable');
  });
});

describe('SafeMarkdown', () => {
  it('renders headings/code safely and strips unsafe javascript URLs without raw HTML execution', () => {
    const md = [
      '### Root Cause',
      'Divide by zero with <script>alert(1)</script> and **bold** `x / 0`.',
      '',
      '[Safe Docs](https://docs.python.org) and [Unsafe](javascript:alert(1))',
      '',
      '```python',
      'if b != 0:',
      '    return a / b',
    ].join('\n');

    const { container } = render(<SafeMarkdown content={md} />);
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).toContain('<script>alert(1)</script>');
    expect(container.querySelector('a')?.getAttribute('href')).toBe('https://docs.python.org');
    expect(container.querySelectorAll('a')).toHaveLength(1);
    expect(container.querySelector('pre code')?.textContent).toContain('return a / b');
  });
});
