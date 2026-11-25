import { AnalysisReport, CoverageGapItem, EdgeMindAnalyzeResponse } from '../types/api';

export type CapabilityClassification =
  | 'IMPLEMENTABLE WITH EXISTING DATA'
  | 'IMPLEMENTABLE WITH DETERMINISTIC ANALYSIS'
  | 'REQUIRES BACKEND IMPLEMENTATION'
  | 'NOT CURRENTLY SUPPORTED';

export interface CapabilityMatrixEntry {
  id: string;
  feature: string;
  classification: CapabilityClassification;
  detail: string;
}

export const TEST_INTELLIGENCE_CAPABILITY_MATRIX: CapabilityMatrixEntry[] = [
  {
    id: 'adaptive-domain-intel',
    feature: 'Adaptive Input-Domain Gaps & Edge-Case Synthesis',
    classification: 'IMPLEMENTABLE WITH EXISTING DATA',
    detail:
      'Served by POST /api/v1/edgemind/analyze using static AST signatures, optional baseline inputs, and constraint rules.',
  },
  {
    id: 'supplied-test-discovery',
    feature: 'Supplied Python Test Parsing (pytest / unittest)',
    classification: 'IMPLEMENTABLE WITH DETERMINISTIC ANALYSIS',
    detail:
      'Parses user-uploaded or pasted .py files client-side for framework hints, Test* classes, def test_* functions, and line ranges.',
  },
  {
    id: 'static-test-mapping',
    feature: 'Test-to-Code Static Reference Mapping',
    classification: 'IMPLEMENTABLE WITH DETERMINISTIC ANALYSIS',
    detail:
      'Infers associations between supplied test files and Python source modules from imports, filename stems, and symbol calls.',
  },
  {
    id: 'risk-priority-ranking',
    feature: 'Heuristic Testing Priority Ranking',
    classification: 'IMPLEMENTABLE WITH DETERMINISTIC ANALYSIS',
    detail:
      'Ranks functions transparently using static analyzer findings, nesting/branching counts, missing static test references, and backend domain gaps.',
  },
  {
    id: 'repo-fs-discovery',
    feature: 'Automatic Server Repository Test Scanning',
    classification: 'REQUIRES BACKEND IMPLEMENTATION',
    detail:
      'The EdgeMind FastAPI backend has no filesystem/git enumeration endpoint; test files must be supplied explicitly.',
  },
  {
    id: 'test-execution',
    feature: 'Runtime Test Execution & Pass/Fail/Skip Results',
    classification: 'NOT CURRENTLY SUPPORTED',
    detail:
      'Runtime code execution is permanently disabled (static_only must be True); no pytest or test runner exists in the API.',
  },
  {
    id: 'measured-coverage',
    feature: 'Line / Branch Statement Coverage (%)',
    classification: 'NOT CURRENTLY SUPPORTED',
    detail:
      'No runtime coverage instrumentation (coverage.py / c8) exists; domain partition gaps do not represent statement coverage.',
  },
];

export type DetectedTestFramework =
  | 'pytest'
  | 'unittest'
  | 'python-test'
  | 'unsupported'
  | 'source-module';

export interface SuppliedCodeFile {
  id: string;
  filename: string;
  content: string;
}

export interface DiscoveredTestCase {
  id: string;
  name: string;
  className: string | null;
  line: number;
  endLine: number;
  decorators: string[];
  assertionsCount: number;
  calledSymbols: string[];
}

export interface ParsedSourceFunction {
  id: string;
  name: string;
  className: string | null;
  filename: string;
  line: number;
  endLine: number;
  params: string[];
  branchCount: number;
  maxNesting: number;
}

export interface ParsedTestFile {
  id: string;
  filename: string;
  stem: string;
  isSupported: boolean;
  unsupportedReason: string | null;
  role: 'test' | 'source';
  framework: DetectedTestFramework;
  imports: string[];
  importedSymbols: string[];
  testCases: DiscoveredTestCase[];
  functions: ParsedSourceFunction[];
  referencedSymbols: string[];
  lineCount: number;
}

export interface TestToCodeRelationship {
  id: string;
  testFileId: string;
  testFilename: string;
  sourceFilename: string;
  sourceStem: string;
  isWorkspaceTarget: boolean;
  confidence: 'high' | 'medium' | 'unmapped';
  matchedSymbols: string[];
  evidence: string[];
}

export interface StaticTestingGap {
  id: string;
  scope: 'file' | 'function' | 'unmapped-test';
  name: string;
  filename: string;
  line: number | null;
  evidence: string;
  caveat: string;
}

export interface PriorityFactor {
  label: string;
  points: number;
}

export interface TestingPriorityItem {
  id: string;
  targetName: string;
  filename: string;
  line: number | null;
  isWorkspaceTarget: boolean;
  tier: 'High' | 'Medium' | 'Low';
  priorityScore: number;
  errorCount: number;
  warningCount: number;
  branchCount: number;
  maxNesting: number;
  hasStaticTestReference: boolean | null;
  factors: PriorityFactor[];
  rationale: string;
}

export interface SampleSuiteFixture {
  id: string;
  label: string;
  sourceFilename: string;
  sourceCode: string;
  testFilename: string;
  testCode: string;
  baselineInputsJson: string;
  constraintsText: string;
}

export const SAMPLE_TEST_INTELLIGENCE_SUITE: SampleSuiteFixture = {
  id: 'two-sum-partition',
  label: 'Array Lookup & Pytest Unit Suite (Deterministic Sample)',
  sourceFilename: 'array_solver.py',
  sourceCode: `def find_pair_indices(nums: list[int], target: int) -> list[int]:
    seen = {}
    for idx, val in enumerate(nums):
        needed = target - val
        if needed in seen:
            return [seen[needed], idx]
        seen[val] = idx
    return []

def validate_non_empty_bounds(nums: list[int]) -> bool:
    if not nums:
        return False
    for n in nums:
        if n == 0:
            return False
    return True
`,
  testFilename: 'test_array_solver.py',
  testCode: `import pytest
from array_solver import find_pair_indices


@pytest.mark.parametrize("nums,target,expected", [([2, 7, 11, 15], 9, [0, 1])])
def test_find_pair_basic(nums, target, expected):
    assert find_pair_indices(nums, target) == expected


def test_find_pair_single_match():
    result = find_pair_indices([3, 3], 6)
    assert result == [0, 1]
`,
  baselineInputsJson: JSON.stringify([{ nums: [2, 7, 11, 15], target: 9 }], null, 2),
  constraintsText: '2 <= nums.length <= 10^4\n-10^9 <= nums[i] <= 10^9',
};

const CONTROL_FLOW_REGEX = /^\s*(if|elif|else|for|async\s+for|while|except|with|match|case)\b/;
const DEF_REGEX = /^(\s*)(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)/;
const CLASS_REGEX = /^(\s*)class\s+([A-Za-z_][A-Za-z0-9_]*)\b/;
const CALL_REGEX = /\b([A-Za-z_][A-Za-z0-9_]*)\s*\(/g;

function normalizeStem(filename: string): string {
  const base = filename.split(/[\\/]/).pop() || filename;
  return base.replace(/\.[^.]+$/, '').toLowerCase();
}

function getIndentWidth(line: string): number {
  const expanded = line.replace(/\t/g, '    ');
  const match = expanded.match(/^(\s*)/);
  return match ? match[1].length : 0;
}

function isSupportedPythonExtension(filename: string): boolean {
  const lower = filename.trim().toLowerCase();
  return lower.endsWith('.py') || lower.endsWith('.pyi');
}

function detectUnsupportedReason(filename: string): string | null {
  const lower = filename.trim().toLowerCase();
  if (lower.endsWith('.ts') || lower.endsWith('.tsx')) {
    return 'TypeScript / Vitest test parsing is not supported; EdgeMind analyzes Python (pytest / unittest) statically.';
  }
  if (lower.endsWith('.js') || lower.endsWith('.jsx') || lower.endsWith('.mjs')) {
    return 'JavaScript test parsing is not supported; EdgeMind analyzes Python (pytest / unittest) statically.';
  }
  if (!isSupportedPythonExtension(filename)) {
    return 'Unsupported file extension; provide Python (.py) files for deterministic AST inspection.';
  }
  return null;
}

function detectPythonFramework(content: string): {
  framework: DetectedTestFramework;
  hasTestSyntax: boolean;
} {
  const hasPytestImport = /(?:^|\n)\s*(?:import\s+pytest\b|from\s+pytest\b|@pytest\.mark\.)/.test(
    content
  );
  const hasUnittestImport =
    /(?:^|\n)\s*(?:import\s+unittest\b|from\s+unittest\b)|\(\s*(?:unittest\.)?TestCase\s*\)/.test(
      content
    );
  const hasTestDef = /(?:^|\n)\s*(?:async\s+)?def\s+test_[A-Za-z0-9_]*\s*\(/.test(content);
  const hasTestClass = /(?:^|\n)\s*class\s+Test[A-Za-z0-9_]*\b/.test(content);

  if (hasPytestImport) {
    return { framework: 'pytest', hasTestSyntax: hasPytestImport || hasTestDef || hasTestClass };
  }
  if (hasUnittestImport) {
    return {
      framework: 'unittest',
      hasTestSyntax: hasUnittestImport || hasTestDef || hasTestClass,
    };
  }
  if (hasTestDef || hasTestClass) {
    return { framework: 'python-test', hasTestSyntax: true };
  }
  return { framework: 'source-module', hasTestSyntax: false };
}

function extractImports(lines: string[]): { imports: string[]; importedSymbols: string[] } {
  const imports: string[] = [];
  const importedSymbols: string[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const fromMatch = trimmed.match(/^from\s+([A-Za-z0-9_.]+)\s+import\s+(.+)$/);
    if (fromMatch) {
      imports.push(fromMatch[1]);
      const rawSyms = fromMatch[2]
        .replace(/[()]/g, '')
        .split(',')
        .map((s) => s.trim().split(/\s+as\s+/)[0].trim())
        .filter((s) => s && s !== '*');
      importedSymbols.push(...rawSyms);
      continue;
    }

    const importMatch = trimmed.match(/^import\s+(.+)$/);
    if (importMatch) {
      const mods = importMatch[1]
        .split(',')
        .map((m) => m.trim().split(/\s+as\s+/)[0].trim())
        .filter(Boolean);
      imports.push(...mods);
    }
  }

  return {
    imports: Array.from(new Set(imports)),
    importedSymbols: Array.from(new Set(importedSymbols)),
  };
}

/**
 * Deterministically parses a supplied Python source or test file cleanly without executing code.
 */
export function parseSuppliedFile(
  file: SuppliedCodeFile,
  forceRole?: 'test' | 'source'
): ParsedTestFile {
  const cleanName = file.filename.split(/[\\/]/).pop() || file.filename || 'snippet.py';
  const stem = normalizeStem(cleanName);
  const unsupportedReason = detectUnsupportedReason(cleanName);
  const normalized = (file.content || '').replace(/\r\n/g, '\n');
  const lines = normalized ? normalized.split('\n') : [];

  if (unsupportedReason) {
    return {
      id: file.id,
      filename: cleanName,
      stem,
      isSupported: false,
      unsupportedReason,
      role: 'test',
      framework: 'unsupported',
      imports: [],
      importedSymbols: [],
      testCases: [],
      functions: [],
      referencedSymbols: [],
      lineCount: lines.length,
    };
  }

  const { framework, hasTestSyntax } = detectPythonFramework(normalized);
  const filenameLooksLikeTest = /^test_|_test$/i.test(stem);
  const role: 'test' | 'source' =
    forceRole ?? (filenameLooksLikeTest || hasTestSyntax ? 'test' : 'source');

  const { imports, importedSymbols } = extractImports(lines);
  const testCases: DiscoveredTestCase[] = [];
  const functions: ParsedSourceFunction[] = [];
  const fileCalls = new Set<string>();

  let currentClass: { name: string; indent: number } | null = null;
  let pendingDecorators: string[] = [];

  interface ActiveFunc {
    name: string;
    className: string | null;
    indent: number;
    line: number;
    params: string[];
    decorators: string[];
    branchCount: number;
    maxNesting: number;
    assertionsCount: number;
    calls: Set<string>;
  }

  let activeFunc: ActiveFunc | null = null;
  let inTripleQuote: string | null = null;

  const finalizeActiveFunc = (endLine: number) => {
    if (!activeFunc) return;
    const isTestCase =
      activeFunc.name.startsWith('test_') ||
      (role === 'test' &&
        activeFunc.className !== null &&
        activeFunc.className.startsWith('Test') &&
        activeFunc.name.startsWith('test'));

    if (role === 'test' && isTestCase) {
      testCases.push({
        id: `${file.id}-tc-${testCases.length + 1}`,
        name: activeFunc.name,
        className: activeFunc.className,
        line: activeFunc.line,
        endLine,
        decorators: activeFunc.decorators,
        assertionsCount: activeFunc.assertionsCount,
        calledSymbols: Array.from(activeFunc.calls),
      });
    } else {
      functions.push({
        id: `${file.id}-fn-${functions.length + 1}`,
        name: activeFunc.name,
        className: activeFunc.className,
        filename: cleanName,
        line: activeFunc.line,
        endLine,
        params: activeFunc.params,
        branchCount: activeFunc.branchCount,
        maxNesting: activeFunc.maxNesting,
      });
    }
    activeFunc = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const lineNum = i + 1;
    const trimmed = rawLine.trim();

    // Track multi-line docstrings conservatively
    if (inTripleQuote) {
      if (trimmed.includes(inTripleQuote)) {
        inTripleQuote = null;
      }
      continue;
    }
    if (
      (trimmed.startsWith('"""') && !trimmed.slice(3).includes('"""')) ||
      (trimmed.startsWith("'''") && !trimmed.slice(3).includes("'''"))
    ) {
      inTripleQuote = trimmed.startsWith('"""') ? '"""' : "'''";
      continue;
    }

    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    const indent = getIndentWidth(rawLine);

    if (activeFunc && indent <= activeFunc.indent && !trimmed.startsWith('@')) {
      finalizeActiveFunc(lineNum - 1);
    }
    if (currentClass && indent <= currentClass.indent) {
      currentClass = null;
    }

    if (trimmed.startsWith('@')) {
      pendingDecorators.push(trimmed);
      continue;
    }

    const classMatch = rawLine.match(CLASS_REGEX);
    if (classMatch) {
      finalizeActiveFunc(lineNum - 1);
      currentClass = { name: classMatch[2], indent };
      pendingDecorators = [];
      continue;
    }

    const defMatch = rawLine.match(DEF_REGEX);
    if (defMatch) {
      finalizeActiveFunc(lineNum - 1);
      const rawParams = defMatch[3]
        .split(',')
        .map((p) => p.trim().split(':')[0].split('=')[0].trim())
        .filter((p) => p && p !== 'self' && p !== 'cls');

      activeFunc = {
        name: defMatch[2],
        className: currentClass ? currentClass.name : null,
        indent,
        line: lineNum,
        params: rawParams,
        decorators: pendingDecorators,
        branchCount: 0,
        maxNesting: 0,
        assertionsCount: 0,
        calls: new Set<string>(),
      };
      pendingDecorators = [];
      continue;
    }

    pendingDecorators = [];

    if (activeFunc && indent > activeFunc.indent) {
      const relativeDepth = Math.max(1, Math.round((indent - activeFunc.indent) / 4));
      if (relativeDepth > activeFunc.maxNesting) {
        activeFunc.maxNesting = relativeDepth;
      }
      if (CONTROL_FLOW_REGEX.test(rawLine)) {
        activeFunc.branchCount += 1;
      }
      if (/\bassert\b|self\.assert|pytest\.raises/.test(trimmed)) {
        activeFunc.assertionsCount += 1;
      }
    }

    let callMatch: RegExpExecArray | null;
    CALL_REGEX.lastIndex = 0;
    while ((callMatch = CALL_REGEX.exec(trimmed)) !== null) {
      const sym = callMatch[1];
      if (!['if', 'elif', 'while', 'for', 'return', 'assert', 'print', 'len', 'range', 'list', 'dict', 'set', 'tuple', 'int', 'str', 'float', 'bool', 'enumerate'].includes(sym)) {
        fileCalls.add(sym);
        if (activeFunc) {
          activeFunc.calls.add(sym);
        }
      }
    }
  }

  finalizeActiveFunc(lines.length);

  return {
    id: file.id,
    filename: cleanName,
    stem,
    isSupported: true,
    unsupportedReason: null,
    role,
    framework: role === 'test' && framework === 'source-module' ? 'python-test' : framework,
    imports,
    importedSymbols,
    testCases,
    functions,
    referencedSymbols: Array.from(fileCalls),
    lineCount: lines.length,
  };
}

/**
 * Deterministically infers static associations between supplied test files and Python source modules.
 * Never claims measured runtime coverage.
 */
export function mapTestsToSources(
  testFiles: ParsedTestFile[],
  sourceModules: ParsedTestFile[],
  workspaceFilename?: string
): TestToCodeRelationship[] {
  const relationships: TestToCodeRelationship[] = [];
  const wsClean = (workspaceFilename || '').split(/[\\/]/).pop()?.toLowerCase();

  for (const tf of testFiles) {
    if (!tf.isSupported) continue;
    const tfCalls = new Set<string>([
      ...tf.referencedSymbols,
      ...tf.testCases.flatMap((tc) => tc.calledSymbols),
    ]);
    const cleanTestStem = tf.stem.replace(/^test_/, '').replace(/_test$/, '');

    let mappedAnySource = false;

    for (const src of sourceModules) {
      if (!src.isSupported || src.filename === tf.filename) continue;

      const srcSymbolNames = src.functions.map((fn) => fn.name);
      const importMatch = tf.imports.some((imp) => {
        const parts = imp.toLowerCase().split('.');
        return parts[parts.length - 1] === src.stem || imp.toLowerCase() === src.stem;
      });
      const stemMatch = cleanTestStem.length > 0 && cleanTestStem === src.stem;
      const matchedSymbols = srcSymbolNames.filter(
        (fnName) => tfCalls.has(fnName) || tf.importedSymbols.includes(fnName)
      );

      if (importMatch || stemMatch || matchedSymbols.length > 0) {
        mappedAnySource = true;
        const evidence: string[] = [];
        if (importMatch) {
          evidence.push(`Import references module '${src.stem}'`);
        }
        if (stemMatch) {
          evidence.push(`Filename matches '${src.filename}' naming pattern`);
        }
        if (matchedSymbols.length > 0) {
          evidence.push(`Calls/imports symbol(s): ${matchedSymbols.slice(0, 4).join(', ')}`);
        }

        const confidence: 'high' | 'medium' =
          importMatch || (stemMatch && matchedSymbols.length > 0) ? 'high' : 'medium';

        relationships.push({
          id: `${tf.id}->${src.id}`,
          testFileId: tf.id,
          testFilename: tf.filename,
          sourceFilename: src.filename,
          sourceStem: src.stem,
          isWorkspaceTarget: Boolean(wsClean && src.filename.toLowerCase() === wsClean),
          confidence,
          matchedSymbols,
          evidence,
        });
      }
    }

    if (!mappedAnySource) {
      relationships.push({
        id: `${tf.id}->unmapped`,
        testFileId: tf.id,
        testFilename: tf.filename,
        sourceFilename: 'No matched source module',
        sourceStem: '',
        isWorkspaceTarget: false,
        confidence: 'unmapped',
        matchedSymbols: [],
        evidence: [
          sourceModules.length === 0
            ? 'No Python source files loaded in Workspace or Test Intelligence to match against.'
            : `No matching import, filename stem, or function call detected across ${sourceModules.length} inspected source module(s).`,
        ],
      });
    }
  }

  return relationships;
}

/**
 * Deterministically identifies static source/function reference gaps when test files are provided.
 */
export function detectStaticTestingGaps(
  sourceModules: ParsedTestFile[],
  testFiles: ParsedTestFile[],
  relationships: TestToCodeRelationship[]
): StaticTestingGap[] {
  const supportedTests = testFiles.filter((t) => t.isSupported);
  if (supportedTests.length === 0) {
    return [];
  }

  const gaps: StaticTestingGap[] = [];
  const referencedBySource = new Map<string, Set<string>>();

  for (const rel of relationships) {
    if (rel.confidence === 'unmapped') continue;
    const current = referencedBySource.get(rel.sourceFilename) ?? new Set<string>();
    rel.matchedSymbols.forEach((s) => current.add(s));
    referencedBySource.set(rel.sourceFilename, current);
  }

  const allCalledAcrossTests = new Set<string>(
    supportedTests.flatMap((t) => [...t.referencedSymbols, ...t.importedSymbols])
  );

  for (const src of sourceModules) {
    if (!src.isSupported) continue;
    const mappedRels = relationships.filter(
      (r) => r.sourceFilename === src.filename && r.confidence !== 'unmapped'
    );

    if (mappedRels.length === 0) {
      gaps.push({
        id: `gap-file-${src.id}`,
        scope: 'file',
        name: src.filename,
        filename: src.filename,
        line: 1,
        evidence: `No uploaded test file imports '${src.stem}' or matches its defined functions.`,
        caveat:
          'Static reference heuristic only: runtime tests located outside uploaded files are not visible.',
      });
      continue;
    }

    const mappedSymbols = referencedBySource.get(src.filename) ?? new Set<string>();
    for (const fn of src.functions) {
      if (fn.name.startsWith('__') && fn.name.endsWith('__')) continue;
      if (!mappedSymbols.has(fn.name) && !allCalledAcrossTests.has(fn.name)) {
        gaps.push({
          id: `gap-fn-${fn.id}`,
          scope: 'function',
          name: fn.className ? `${fn.className}.${fn.name}()` : `${fn.name}()`,
          filename: src.filename,
          line: fn.line,
          evidence: `Function '${fn.name}' in ${src.filename}:${fn.line} has no direct static call or import reference in supplied tests.`,
          caveat:
            'Inferred from static symbol references; helper may still be exercised indirectly via callers.',
        });
      }
    }
  }

  for (const unmapped of relationships.filter((r) => r.confidence === 'unmapped')) {
    gaps.push({
      id: `gap-unmapped-${unmapped.testFileId}`,
      scope: 'unmapped-test',
      name: unmapped.testFilename,
      filename: unmapped.testFilename,
      line: 1,
      evidence: unmapped.evidence[0] || 'Test file has no recognizable source association.',
      caveat: 'Upload the corresponding source module or open it in Workspace to inspect linkage.',
    });
  }

  return gaps;
}

/**
 * Transparent deterministic testing-priority ranking combining:
 * - Real static analyzer errors (+30 pts) & warnings (+10 pts)
 * - Control-flow branches & nesting depth (up to +25 pts)
 * - Missing static test call reference when test files are supplied (+25 pts)
 * - Backend EdgeMind domain gap severity (+15 HIGH / +8 MEDIUM)
 */
export function computeTestingPriority(
  sourceModules: ParsedTestFile[],
  testFiles: ParsedTestFile[],
  relationships: TestToCodeRelationship[],
  workspaceFilename?: string,
  latestReport?: AnalysisReport | null,
  backendTIReport?: EdgeMindAnalyzeResponse | null
): TestingPriorityItem[] {
  const wsClean = (workspaceFilename || '').split(/[\\/]/).pop()?.toLowerCase();
  const hasSuppliedTests = testFiles.some((t) => t.isSupported);

  const allTestCalls = new Set<string>(
    testFiles
      .filter((t) => t.isSupported)
      .flatMap((t) => [
        ...t.referencedSymbols,
        ...t.importedSymbols,
        ...t.testCases.flatMap((tc) => tc.calledSymbols),
      ])
  );

  const reportErrors = latestReport?.errors ?? [];
  const reportWarnings = latestReport?.warnings ?? [];
  const reportFilename = (latestReport?.file || latestReport?.file_path || '')
    .split(/[\\/]/)
    .pop()
    ?.toLowerCase();

  const backendGaps: CoverageGapItem[] =
    backendTIReport?.test_intelligence?.coverage_gaps ?? [];
  const highGapCount = backendGaps.filter((g) => g.severity === 'HIGH').length;
  const medGapCount = backendGaps.filter((g) => g.severity === 'MEDIUM').length;

  const items: TestingPriorityItem[] = [];

  for (const src of sourceModules) {
    if (!src.isSupported) continue;
    const isWs = Boolean(wsClean && src.filename.toLowerCase() === wsClean);
    const matchesReport = Boolean(
      latestReport && reportFilename && src.filename.toLowerCase() === reportFilename
    );
    const fileHasRelationship = relationships.some(
      (r) => r.sourceFilename === src.filename && r.confidence !== 'unmapped'
    );

    if (src.functions.length === 0) {
      const errCount = matchesReport ? reportErrors.length : 0;
      const warnCount = matchesReport ? reportWarnings.length : 0;
      const factors: PriorityFactor[] = [];
      let score = 0;

      if (errCount > 0) {
        const pts = errCount * 30;
        score += pts;
        factors.push({ label: `${errCount} static error(s)`, points: pts });
      }
      if (warnCount > 0) {
        const pts = warnCount * 10;
        score += pts;
        factors.push({ label: `${warnCount} static warning(s)`, points: pts });
      }
      if (hasSuppliedTests && !fileHasRelationship) {
        score += 25;
        factors.push({ label: 'No static test association', points: 25 });
      }
      if (isWs && highGapCount > 0) {
        score += 15;
        factors.push({ label: `${highGapCount} HIGH domain gap(s)`, points: 15 });
      }

      if (score > 0 || isWs) {
        const tier = score >= 45 ? 'High' : score >= 20 ? 'Medium' : 'Low';
        items.push({
          id: `prio-mod-${src.id}`,
          targetName: `${src.filename} (module)`,
          filename: src.filename,
          line: 1,
          isWorkspaceTarget: isWs,
          tier,
          priorityScore: score,
          errorCount: errCount,
          warningCount: warnCount,
          branchCount: 0,
          maxNesting: 0,
          hasStaticTestReference: hasSuppliedTests ? fileHasRelationship : null,
          factors,
          rationale:
            factors.length > 0
              ? factors.map((f) => `${f.label} (+${f.points})`).join(' · ')
              : 'Module has no detected static findings or complexity spikes.',
        });
      }
      continue;
    }

    for (const fn of src.functions) {
      const fnErrors = matchesReport
        ? reportErrors.filter((e) => {
            const line = e.line || e.line_number || 0;
            return line >= fn.line && line <= fn.endLine;
          }).length
        : 0;
      const fnWarnings = matchesReport
        ? reportWarnings.filter((w) => {
            const line = w.line || w.line_number || 0;
            return line >= fn.line && line <= fn.endLine;
          }).length
        : 0;

      const factors: PriorityFactor[] = [];
      let score = 0;

      if (fnErrors > 0) {
        const pts = fnErrors * 30;
        score += pts;
        factors.push({ label: `${fnErrors} static error(s)`, points: pts });
      }
      if (fnWarnings > 0) {
        const pts = fnWarnings * 10;
        score += pts;
        factors.push({ label: `${fnWarnings} static warning(s)`, points: pts });
      }

      if (fn.branchCount > 0 || fn.maxNesting >= 2) {
        const pts = Math.min(25, fn.branchCount * 4 + fn.maxNesting * 3);
        if (pts > 0) {
          score += pts;
          factors.push({
            label: `${fn.branchCount} branch(es), depth ${fn.maxNesting}`,
            points: pts,
          });
        }
      }

      const fnHasTestRef = hasSuppliedTests ? allTestCalls.has(fn.name) : null;
      if (hasSuppliedTests && !fnHasTestRef) {
        score += 25;
        factors.push({ label: 'No static call ref in tests', points: 25 });
      }

      if (isWs && (highGapCount > 0 || medGapCount > 0)) {
        const pts = highGapCount > 0 ? 15 : 8;
        score += pts;
        factors.push({
          label:
            highGapCount > 0
              ? `${highGapCount} HIGH input-domain gap(s)`
              : `${medGapCount} MEDIUM input-domain gap(s)`,
          points: pts,
        });
      }

      const tier: 'High' | 'Medium' | 'Low' =
        score >= 45 ? 'High' : score >= 20 ? 'Medium' : 'Low';

      items.push({
        id: `prio-${fn.id}`,
        targetName: fn.className ? `${fn.className}.${fn.name}()` : `${fn.name}()`,
        filename: src.filename,
        line: fn.line,
        isWorkspaceTarget: isWs,
        tier,
        priorityScore: score,
        errorCount: fnErrors,
        warningCount: fnWarnings,
        branchCount: fn.branchCount,
        maxNesting: fn.maxNesting,
        hasStaticTestReference: fnHasTestRef,
        factors,
        rationale:
          factors.length > 0
            ? factors.map((f) => `${f.label} (+${f.points})`).join(' · ')
            : 'Simple control flow with no static findings.',
      });
    }
  }

  return items.sort((a, b) => {
    if (b.priorityScore !== a.priorityScore) return b.priorityScore - a.priorityScore;
    if (b.errorCount !== a.errorCount) return b.errorCount - a.errorCount;
    return (a.line ?? 0) - (b.line ?? 0);
  });
}

/**
 * Parses optional JSON test case array or newline-separated STDIN inputs for /api/v1/edgemind/analyze.
 */
export function parseBaselineTestInputs(rawText: string): {
  testCases: Array<Record<string, unknown>> | undefined;
  error: string | null;
} {
  const trimmed = rawText.trim();
  if (!trimmed) {
    return { testCases: undefined, error: null };
  }

  if (trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed);
      if (!Array.isArray(parsed)) {
        return { testCases: undefined, error: 'Baseline JSON must be an array of objects.' };
      }
      const normalized = parsed.map((item, idx) => {
        if (item && typeof item === 'object' && !Array.isArray(item)) {
          return item as Record<string, unknown>;
        }
        return { input: item, id: `user_${idx + 1}` };
      });
      return { testCases: normalized, error: null };
    } catch {
      return {
        testCases: undefined,
        error: 'Invalid JSON in baseline test inputs. Use e.g. [{"nums": [1, 2], "target": 3}].',
      };
    }
  }

  if (trimmed.startsWith('{')) {
    try {
      const single = JSON.parse(trimmed);
      if (single && typeof single === 'object' && !Array.isArray(single)) {
        return { testCases: [single as Record<string, unknown>], error: null };
      }
    } catch {
      return { testCases: undefined, error: 'Invalid JSON object in baseline input.' };
    }
  }

  // Fallback: treat double-newline separated blocks as raw_stdin cases matching core/service.py parse_test_cases
  const blocks = trimmed
    .split(/\n\s*\n/)
    .map((b) => b.trim())
    .filter(Boolean);
  return {
    testCases: blocks.map((raw_stdin) => ({ raw_stdin })),
    error: null,
  };
}
