import * as path from 'path';

export const MAX_SOURCE_SIZE_BYTES = 64 * 1024; // 64 KiB (65,536 bytes)

export interface ValidationSuccess {
  isValid: true;
  code: string;
  displayFilename: string;
  sizeBytes: number;
}

export interface ValidationFailure {
  isValid: false;
  errorMessage: string;
}

export type EditorValidationResult = ValidationSuccess | ValidationFailure;

/**
 * Validates document metadata and code contents.
 * Pure function independent of VS Code runtime, directly unit-testable.
 */
export function validateEditorDocument(
  fileName?: string,
  languageId?: string,
  text?: string
): EditorValidationResult {
  if (text === undefined || fileName === undefined) {
    return {
      isValid: false,
      errorMessage: 'No active editor found. Please open a Python file to analyze.',
    };
  }

  // Check language or file extension
  const isPythonExt = fileName.toLowerCase().endsWith('.py');
  const isPythonLang = languageId === 'python';
  if (!isPythonExt && !isPythonLang) {
    return {
      isValid: false,
      errorMessage: `EdgeMind currently supports Python files (.py) only. Detected file: '${path.basename(fileName)}'`,
    };
  }

  // Check empty or whitespace-only
  if (!text || !text.trim()) {
    return {
      isValid: false,
      errorMessage: 'Cannot analyze an empty file. Please provide Python source code.',
    };
  }

  // Validate size against backend limit
  const byteLength = Buffer.byteLength(text, 'utf8');
  if (byteLength > MAX_SOURCE_SIZE_BYTES) {
    const sizeKiB = (byteLength / 1024).toFixed(1);
    return {
      isValid: false,
      errorMessage: `Source code size (${sizeKiB} KiB) exceeds the maximum allowed limit of 64 KiB. Please select a smaller snippet or split the file.`,
    };
  }

  // Extract clean display label (never send full local path)
  let baseName = path.basename(fileName);
  if (!baseName || baseName === '.' || baseName === '/' || baseName === '\\') {
    baseName = 'snippet.py';
  }

  return {
    isValid: true,
    code: text,
    displayFilename: baseName,
    sizeBytes: byteLength,
  };
}

export interface SelectionValidationSuccess {
  isValid: true;
  code: string;
  displayFilename: string;
  sizeBytes: number;
  startLine: number;
  endLine: number;
  scopeLabel: string;
}

export interface SelectionValidationFailure {
  isValid: false;
  errorMessage: string;
}

export type SelectionValidationResult = SelectionValidationSuccess | SelectionValidationFailure;

/**
 * Validates selected code metadata and contents.
 * Pure function independent of VS Code runtime, directly unit-testable.
 */
export function validateEditorSelection(
  fileName?: string,
  languageId?: string,
  hasSelection?: boolean,
  selectedText?: string,
  startLine?: number,
  endLine?: number
): SelectionValidationResult {
  if (selectedText === undefined || fileName === undefined) {
    return {
      isValid: false,
      errorMessage: 'No active editor found. Please open a Python file and select code to analyze.',
    };
  }

  // Check language or file extension
  const isPythonExt = fileName.toLowerCase().endsWith('.py');
  const isPythonLang = languageId === 'python';
  if (!isPythonExt && !isPythonLang) {
    return {
      isValid: false,
      errorMessage: `EdgeMind currently supports Python files (.py) only. Detected file: '${path.basename(fileName)}'`,
    };
  }

  // Check whether a selection was made
  if (!hasSelection || !selectedText) {
    return {
      isValid: false,
      errorMessage: 'No code selected. Please select a block of Python code to analyze.',
    };
  }

  // Check empty or whitespace-only selection
  if (!selectedText.trim()) {
    return {
      isValid: false,
      errorMessage: 'Selected code is empty or whitespace-only. Please select a valid block of Python code.',
    };
  }

  // Validate size against backend limit
  const byteLength = Buffer.byteLength(selectedText, 'utf8');
  if (byteLength > MAX_SOURCE_SIZE_BYTES) {
    const sizeKiB = (byteLength / 1024).toFixed(1);
    return {
      isValid: false,
      errorMessage: `Selected code size (${sizeKiB} KiB) exceeds the maximum allowed limit of 64 KiB. Please select a smaller snippet.`,
    };
  }

  // Extract clean display label
  let baseName = path.basename(fileName);
  if (!baseName || baseName === '.' || baseName === '/' || baseName === '\\') {
    baseName = 'snippet.py';
  }

  const sLine = startLine ?? 1;
  const eLine = endLine ?? sLine;
  const scopeLabel = sLine === eLine ? `Selection: Line ${sLine}` : `Selection: Lines ${sLine}-${eLine}`;

  return {
    isValid: true,
    code: selectedText,
    displayFilename: baseName,
    sizeBytes: byteLength,
    startLine: sLine,
    endLine: eLine,
    scopeLabel,
  };
}
