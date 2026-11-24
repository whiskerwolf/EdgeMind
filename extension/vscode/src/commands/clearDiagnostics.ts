import * as vscode from 'vscode';
import * as path from 'path';
import { Logger } from '../utils/logger';

/**
 * Command handler for "EdgeMind: Clear Diagnostics" (edgemind.clearDiagnostics).
 * Clears EdgeMind diagnostics for the active Python editor document, or all documents if none is active.
 */
export function clearDiagnostics(
  diagnosticCollection: vscode.DiagnosticCollection,
  logger: Logger
): void {
  const editor = vscode.window.activeTextEditor;
  if (editor && editor.document) {
    const filename = path.basename(editor.document.fileName);
    diagnosticCollection.delete(editor.document.uri);
    logger.info(`EdgeMind diagnostics cleared for active document: ${filename}`);
    vscode.window.showInformationMessage(`EdgeMind diagnostics cleared for '${filename}'.`);
  } else {
    diagnosticCollection.clear();
    logger.info('EdgeMind diagnostics cleared for all documents.');
    vscode.window.showInformationMessage('EdgeMind diagnostics cleared.');
  }
}
