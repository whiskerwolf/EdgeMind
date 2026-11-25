export type WorkspaceLanguage = 'python' | 'javascript' | 'typescript';

export interface LanguageOption {
  id: WorkspaceLanguage;
  label: string;
  monacoLanguage: string;
  supported: boolean;
  defaultExtension: string;
}

export const WORKSPACE_LANGUAGES: LanguageOption[] = [
  {
    id: 'python',
    label: 'Python 3 (Static AST)',
    monacoLanguage: 'python',
    supported: true,
    defaultExtension: '.py',
  },
  {
    id: 'javascript',
    label: 'JavaScript (Unsupported)',
    monacoLanguage: 'javascript',
    supported: false,
    defaultExtension: '.js',
  },
  {
    id: 'typescript',
    label: 'TypeScript (Unsupported)',
    monacoLanguage: 'typescript',
    supported: false,
    defaultExtension: '.ts',
  },
];

export const MAX_SOURCE_CODE_BYTES = 64 * 1024; // 65,536 bytes matching core/sanitization.py
export const MAX_FILENAME_CHARS = 255;

export interface WorkspaceSample {
  id: string;
  label: string;
  filename: string;
  language: WorkspaceLanguage;
  code: string;
}

export const WORKSPACE_SAMPLES: WorkspaceSample[] = [
  {
    id: 'division-check',
    label: 'Divide-by-Zero & Unused Variable',
    filename: 'sample_check.py',
    language: 'python',
    code: `def calculate_ratio(total: int, count: int) -> float:
    unused_flag = True
    return total / 0
`,
  },
  {
    id: 'clean-math',
    label: 'Clean Python Module',
    filename: 'clean_math.py',
    language: 'python',
    code: `def clamp_score(value: int, minimum: int = 0, maximum: int = 100) -> int:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value
`,
  },
  {
    id: 'complexity-loops',
    label: 'Nested Complexity & Smells',
    filename: 'nested_logic.py',
    language: 'python',
    code: `def find_matches(matrix: list, target: int) -> list:
    matches = []
    for row_idx in range(len(matrix)):
        for col_idx in range(len(matrix[row_idx])):
            for offset in range(3):
                if matrix[row_idx][col_idx] + offset == target:
                    matches.append((row_idx, col_idx))
    return matches
`,
  },
];

export function isSupportedLanguage(lang: WorkspaceLanguage): boolean {
  const match = WORKSPACE_LANGUAGES.find((item) => item.id === lang);
  return Boolean(match?.supported);
}

export function inferLanguageFromFilename(filename: string): WorkspaceLanguage {
  const lower = filename.trim().toLowerCase();
  if (lower.endsWith('.ts') || lower.endsWith('.tsx')) return 'typescript';
  if (lower.endsWith('.js') || lower.endsWith('.jsx')) return 'javascript';
  return 'python';
}

export function getUtf8ByteLength(text: string): number {
  if (!text) return 0;
  return new TextEncoder().encode(text).length;
}

export function formatByteSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KiB`;
}

/**
 * Mirrors core/sanitization.py validate_filename_label rules.
 */
export function validateWorkspaceFilename(filename: string): string | null {
  if (!filename || !filename.trim()) {
    return 'Filename must not be empty.';
  }
  if (filename.includes('\x00') || filename.includes('\0')) {
    return 'Filename contains invalid null bytes.';
  }
  const cleaned = filename.trim();
  if (cleaned.length > MAX_FILENAME_CHARS) {
    return `Filename exceeds maximum ${MAX_FILENAME_CHARS} characters.`;
  }
  if (
    cleaned.includes('..') ||
    cleaned.includes('/') ||
    cleaned.includes('\\') ||
    (cleaned.length > 1 && cleaned[1] === ':')
  ) {
    return 'Filename must be a simple label without paths or traversal.';
  }
  return null;
}
