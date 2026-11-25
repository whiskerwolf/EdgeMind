import React, { useRef } from 'react';
import { FileCode2, Trash2, Upload } from 'lucide-react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import {
  formatByteSize,
  MAX_SOURCE_CODE_BYTES,
  WORKSPACE_LANGUAGES,
  WORKSPACE_SAMPLES,
  WorkspaceLanguage,
  WorkspaceSample,
} from '../../utils/workspaceConfig';
import { cn } from '../../utils/cn';

export interface AnalysisControlsProps {
  filename: string;
  filenameError: string | null;
  language: WorkspaceLanguage;
  codeBytes: number;
  isAnalyzing: boolean;
  hasCode: boolean;
  onFilenameChange: (filename: string) => void;
  onLanguageChange: (lang: WorkspaceLanguage) => void;
  onInsertSample: (sample: WorkspaceSample) => void;
  onUploadFile: (file: File) => void;
  onClear: () => void;
}

export const AnalysisControls: React.FC<AnalysisControlsProps> = ({
  filename,
  filenameError,
  language,
  codeBytes,
  isAnalyzing,
  hasCode,
  onFilenameChange,
  onLanguageChange,
  onInsertSample,
  onUploadFile,
  onClear,
}) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const exceedsSizeLimit = codeBytes > MAX_SOURCE_CODE_BYTES;
  const nearSizeLimit = !exceedsSizeLimit && codeBytes > MAX_SOURCE_CODE_BYTES * 0.85;

  return (
    <div className="p-3 rounded-md border border-em-border-default bg-em-surface-card space-y-2.5">
      <div className="flex flex-wrap items-start gap-2.5">
        {/* Filename Label Input */}
        <div className="w-full sm:w-44">
          <label htmlFor="workspace-filename" className="sr-only">
            Target filename
          </label>
          <Input
            id="workspace-filename"
            value={filename}
            onChange={(e) => onFilenameChange(e.target.value)}
            placeholder="snippet.py"
            error={filenameError ?? undefined}
            disabled={isAnalyzing}
            leftIcon={<FileCode2 className="w-3.5 h-3.5" />}
            aria-label="Filename label"
          />
        </div>

        {/* Language Selector */}
        <div className="w-full sm:w-auto flex-1 sm:flex-initial">
          <label htmlFor="workspace-language" className="sr-only">
            Analysis Language
          </label>
          <select
            id="workspace-language"
            aria-label="Language"
            value={language}
            disabled={isAnalyzing}
            onChange={(e) => onLanguageChange(e.target.value as WorkspaceLanguage)}
            className="w-full sm:w-48 h-9 px-2.5 rounded-md bg-em-surface-workspace border border-em-border-default text-xs text-em-text-primary font-mono focus:outline-none focus:border-em-border-focus focus:ring-1 focus:ring-em-border-focus disabled:opacity-40"
          >
            {WORKSPACE_LANGUAGES.map((lang) => (
              <option key={lang.id} value={lang.id} className="bg-em-surface-card text-em-text-primary">
                {lang.label}
              </option>
            ))}
          </select>
        </div>

        {/* Sample Code Selector */}
        <div className="w-full sm:w-auto">
          <label htmlFor="workspace-sample-select" className="sr-only">
            Load Sample Code
          </label>
          <select
            id="workspace-sample-select"
            aria-label="Insert sample code"
            value=""
            disabled={isAnalyzing}
            onChange={(e) => {
              const selected = WORKSPACE_SAMPLES.find((s) => s.id === e.target.value);
              if (selected) onInsertSample(selected);
            }}
            className="w-full sm:w-auto h-9 px-2.5 rounded-md bg-em-surface-workspace border border-em-border-default text-xs text-em-text-secondary hover:text-em-text-primary focus:outline-none focus:border-em-border-focus focus:ring-1 focus:ring-em-border-focus disabled:opacity-40"
          >
            <option value="" disabled>
              Insert sample...
            </option>
            {WORKSPACE_SAMPLES.map((sample) => (
              <option key={sample.id} value={sample.id} className="bg-em-surface-card text-em-text-primary">
                {sample.label}
              </option>
            ))}
          </select>
        </div>

        {/* Upload & Clear Controls */}
        <div className="flex items-center gap-2 ml-auto">
          <input
            ref={fileInputRef}
            type="file"
            accept=".py,.txt,.js,.ts"
            className="hidden"
            aria-label="Upload source file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                onUploadFile(file);
              }
              e.target.value = '';
            }}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={isAnalyzing}
            leftIcon={<Upload className="w-3.5 h-3.5" />}
            onClick={() => fileInputRef.current?.click()}
            className="h-9"
          >
            Upload
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={isAnalyzing || !hasCode}
            leftIcon={<Trash2 className="w-3.5 h-3.5" />}
            onClick={onClear}
            className="h-9"
          >
            Clear
          </Button>
        </div>
      </div>

      {/* Size & Constraints Sub-strip */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono">
        <span className="text-em-text-dim">
          Pure static AST analysis · Zero runtime execution
        </span>
        <span
          className={cn(
            'tabular-nums',
            exceedsSizeLimit
              ? 'text-em-status-error font-semibold'
              : nearSizeLimit
                ? 'text-em-status-warning'
                : 'text-em-text-dim'
          )}
        >
          {formatByteSize(codeBytes)} / 64 KiB
        </span>
      </div>
    </div>
  );
};
