/**
 * Bounded source-code context extractor for EdgeMind AI Diagnosis (Phase 5G.6).
 *
 * Responsibilities:
 * - Extracts bounded code context (approximately ±15 lines) around the finding's line
 * - Validates line bounds against current editor document length (detects stale/mismatched documents)
 * - Enforces the 16 KiB (16,384 bytes) backend context size limit
 * - Preserves line numbers, filename labels, and language metadata
 * - Handles module-level findings (where line is undefined or null)
 */

import type * as vscodeTypes from 'vscode';

let vscodeModule: typeof vscodeTypes | undefined;
function getVscode(): typeof vscodeTypes {
  if (!vscodeModule) {
    try {
      vscodeModule = require('vscode');
    } catch {
      throw new Error('Cannot access VS Code API outside of an extension host environment.');
    }
  }
  return vscodeModule!;
}

export interface ExtractedDiagnosisContext {
  codeContext: string;
  contextStartLine: number;
  contextEndLine: number;
  filename: string;
  language: string;
}

export const MAX_DIAGNOSIS_CONTEXT_BYTES = 16 * 1024; // 16 KiB

/**
 * Pure extraction logic operating on array of lines (testable in Node unit tests).
 */
export function extractContextFromLines(
  lines: string[],
  findingLine1?: number,
  filename = 'snippet.py',
  language = 'python'
): ExtractedDiagnosisContext {
  const totalLines = lines.length;
  if (totalLines === 0) {
    throw new Error('Document has no lines.');
  }

  let startLine1 = 1;
  let endLine1 = 1;

  if (findingLine1 !== undefined && findingLine1 !== null && !isNaN(findingLine1)) {
    if (findingLine1 < 1) {
      throw new Error(`Invalid finding line ${findingLine1}: line numbers must be >= 1.`);
    }
    if (findingLine1 > totalLines) {
      throw new Error(
        `Finding line ${findingLine1} exceeds document length (${totalLines} lines). Document may have been modified since analysis.`
      );
    }
    // ±15 lines around finding line
    startLine1 = Math.max(1, findingLine1 - 15);
    endLine1 = Math.min(totalLines, findingLine1 + 15);
  } else {
    // Module-level finding: take up to first 30 lines
    startLine1 = 1;
    endLine1 = Math.min(totalLines, 30);
  }

  // Extract lines from startLine1 - 1 to endLine1 - 1
  let slice = lines.slice(startLine1 - 1, endLine1);
  let codeContext = slice.join('\n') + '\n';
  let byteLen = Buffer.byteLength(codeContext, 'utf8');

  // Enforce 16 KiB limit
  if (byteLen > MAX_DIAGNOSIS_CONTEXT_BYTES) {
    while (byteLen > MAX_DIAGNOSIS_CONTEXT_BYTES && endLine1 > startLine1) {
      if (findingLine1 !== undefined) {
        if (endLine1 - findingLine1 >= findingLine1 - startLine1 && endLine1 > findingLine1) {
          endLine1--;
        } else if (startLine1 < findingLine1) {
          startLine1++;
        } else {
          break;
        }
      } else {
        endLine1--;
      }
      slice = lines.slice(startLine1 - 1, endLine1);
      codeContext = slice.join('\n') + '\n';
      byteLen = Buffer.byteLength(codeContext, 'utf8');
    }

    if (byteLen > MAX_DIAGNOSIS_CONTEXT_BYTES) {
      throw new Error(
        `Extracted code context size (${byteLen} bytes) exceeds maximum limit of ${MAX_DIAGNOSIS_CONTEXT_BYTES} bytes.`
      );
    }
  }

  const cleanFilename = filename.split(/[\\/]/).pop() || 'snippet.py';
  const cleanLanguage = (language || 'python').toLowerCase();

  return {
    codeContext,
    contextStartLine: startLine1,
    contextEndLine: endLine1,
    filename: cleanFilename,
    language: cleanLanguage,
  };
}

/**
 * Extracts context from a document URI via VS Code workspace.
 */
export async function extractDiagnosisContext(
  documentUriStr: string,
  findingLine1?: number,
  fallbackFilename = 'snippet.py'
): Promise<ExtractedDiagnosisContext> {
  if (!documentUriStr || !documentUriStr.trim()) {
    throw new Error('No target document URI available in analysis context.');
  }

  const vscode = getVscode();
  const uri = vscode.Uri.parse(documentUriStr);
  let document: vscodeTypes.TextDocument;
  try {
    document = await vscode.workspace.openTextDocument(uri);
  } catch (err) {
    throw new Error(`Failed to access document '${documentUriStr}': ${err instanceof Error ? err.message : String(err)}`);
  }

  const lines: string[] = [];
  for (let i = 0; i < document.lineCount; i++) {
    lines.push(document.lineAt(i).text);
  }

  const filename = document.fileName.split(/[\\/]/).pop() || fallbackFilename;
  const language = document.languageId || 'python';

  return extractContextFromLines(lines, findingLine1, filename, language);
}
