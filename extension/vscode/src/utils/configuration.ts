import * as vscode from 'vscode';
import {
  DEFAULT_BACKEND_URL,
  validateBackendUrl,
  UrlValidationResult,
} from './urlValidator';

export const CONFIG_SECTION = 'edgemind';
export const CONFIG_BACKEND_URL = 'backendUrl';
export { DEFAULT_BACKEND_URL, validateBackendUrl, UrlValidationResult };

/**
 * Retrieve the configured backend URL from VS Code settings.
 * Falls back to default if unconfigured or invalid.
 */
export function getBackendUrl(): string {
  const config = vscode.workspace.getConfiguration(CONFIG_SECTION);
  const raw = config.get<string>(CONFIG_BACKEND_URL, DEFAULT_BACKEND_URL);
  const validation = validateBackendUrl(raw);
  return validation.valid && validation.normalized ? validation.normalized : DEFAULT_BACKEND_URL;
}
