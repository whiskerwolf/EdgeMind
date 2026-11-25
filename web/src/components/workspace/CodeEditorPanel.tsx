import React, { Component, Suspense, useEffect, useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import type { WorkspaceFindingDecoration } from './MonacoEditorAdapter';
import { cn } from '../../utils/cn';
import { useOptionalSettings } from '../../context/SettingsContext';

const LazyMonacoEditor = React.lazy(() => import('./MonacoEditorAdapter'));

interface EditorErrorBoundaryState {
  hasError: boolean;
}

class EditorErrorBoundary extends Component<
  { children: React.ReactNode; fallback: React.ReactNode },
  EditorErrorBoundaryState
> {
  constructor(props: { children: React.ReactNode; fallback: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): EditorErrorBoundaryState {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

export interface CodeEditorPanelProps {
  value: string;
  language: string;
  filename: string;
  findings: WorkspaceFindingDecoration[];
  navigationTarget: { line: number; seq: number } | null;
  onChange: (value: string) => void;
  onFileDrop: (file: File) => void;
  onAnalyzeShortcut: () => void;
}

interface TextareaFallbackProps {
  value: string;
  navigationTarget: { line: number; seq: number } | null;
  onChange: (value: string) => void;
  onAnalyzeShortcut: () => void;
  fontSize?: number;
  lineNumbers?: 'on' | 'off';
  wordWrap?: 'off' | 'on';
}

const TextareaFallbackEditor: React.FC<TextareaFallbackProps> = ({
  value,
  navigationTarget,
  onChange,
  onAnalyzeShortcut,
  fontSize = 13,
  lineNumbers = 'on',
  wordWrap = 'off',
}) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!navigationTarget || navigationTarget.line < 1 || !textareaRef.current) return;
    const lines = value.split('\n');
    let charOffset = 0;
    const targetIdx = Math.min(lines.length - 1, navigationTarget.line - 1);
    for (let i = 0; i < targetIdx; i++) {
      charOffset += lines[i].length + 1;
    }
    textareaRef.current.focus();
    textareaRef.current.setSelectionRange(charOffset, charOffset + (lines[targetIdx]?.length ?? 0));
  }, [navigationTarget, value]);

  const lineCount = Math.max(1, value ? value.split('\n').length : 1);

  return (
    <div
      className="relative flex h-full w-full bg-em-surface-workspace font-mono leading-5"
      style={{ fontSize: `${fontSize}px` }}
    >
      {lineNumbers !== 'off' && (
        <div
          aria-hidden="true"
          className="py-3 px-2.5 select-none text-right text-em-text-dim border-r border-em-border-hairline bg-em-surface-workspace shrink-0 min-w-[42px]"
        >
          {Array.from({ length: lineCount }, (_, idx) => {
            const lineNo = idx + 1;
            const isTarget = navigationTarget?.line === lineNo;
            return (
              <div
                key={lineNo}
                className={cn('px-1 rounded-xs', isTarget && 'text-em-accent-primary font-semibold bg-em-accent-primary/10')}
              >
                {lineNo}
              </div>
            );
          })}
        </div>
      )}
      <textarea
        ref={textareaRef}
        value={value}
        wrap={wordWrap === 'on' ? 'soft' : 'off'}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
            e.preventDefault();
            onAnalyzeShortcut();
          }
        }}
        spellCheck={false}
        placeholder="# Write or paste Python code here, upload a .py file, or load a sample..."
        aria-label="Python source code editor"
        className="flex-1 h-full w-full resize-none bg-transparent p-3 text-em-text-primary placeholder:text-em-text-dim focus:outline-none overflow-auto"
      />
    </div>
  );
};

export const CodeEditorPanel: React.FC<CodeEditorPanelProps> = ({
  value,
  language,
  filename,
  findings,
  navigationTarget,
  onChange,
  onFileDrop,
  onAnalyzeShortcut,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const settings = useOptionalSettings();

  // Detect JSDOM / test environment where Web Workers & Monaco DOM aren't supported
  const isJsdom =
    typeof navigator !== 'undefined' && navigator.userAgent.toLowerCase().includes('jsdom');

  const fallback = (
    <TextareaFallbackEditor
      value={value}
      navigationTarget={navigationTarget}
      onChange={onChange}
      onAnalyzeShortcut={onAnalyzeShortcut}
      fontSize={settings.editorFontSize}
      lineNumbers={settings.editorLineNumbers}
      wordWrap={settings.editorWordWrap}
    />
  );

  return (
    <div
      className={cn(
        'relative flex flex-col h-[360px] sm:h-[420px] lg:h-[520px] rounded-md border bg-em-surface-workspace overflow-hidden transition-colors',
        isDragging ? 'border-em-accent-primary' : 'border-em-border-default'
      )}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        const file = e.dataTransfer?.files?.[0];
        if (file) {
          onFileDrop(file);
        }
      }}
    >
      {/* Editor Top Sub-bar */}
      <div className="h-8 px-3 bg-em-surface-card border-b border-em-border-hairline flex items-center justify-between text-[11px] font-mono text-em-text-muted shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-em-text-primary truncate">{filename || 'snippet.py'}</span>
          <span className="text-em-text-dim hidden sm:inline">·</span>
          <span className="text-em-text-dim uppercase hidden sm:inline">{language}</span>
        </div>
        {navigationTarget && navigationTarget.line > 0 && (
          <span className="text-em-accent-primary tabular-nums">
            Focused Line {navigationTarget.line}
          </span>
        )}
      </div>

      {/* Editor Surface */}
      <div className="relative flex-1 min-h-0">
        {isJsdom ? (
          fallback
        ) : (
          <EditorErrorBoundary fallback={fallback}>
            <Suspense fallback={fallback}>{
              <LazyMonacoEditor
                value={value}
                language={language}
                findings={findings}
                navigationTarget={navigationTarget}
                onChange={onChange}
                onAnalyzeShortcut={onAnalyzeShortcut}
                fontSize={settings.editorFontSize}
                tabSize={settings.editorTabSize}
                minimap={settings.editorMinimap}
                wordWrap={settings.editorWordWrap}
                lineNumbers={settings.editorLineNumbers}
              />
            }</Suspense>
          </EditorErrorBoundary>
        )}

        {/* Drag-and-drop overlay */}
        {isDragging && (
          <div className="absolute inset-0 z-10 bg-em-canvas/85 border-2 border-dashed border-em-accent-primary flex flex-col items-center justify-center gap-2 pointer-events-none">
            <Upload className="w-6 h-6 text-em-accent-primary" />
            <span className="text-xs font-medium text-em-text-primary">
              Drop source file to load into Workspace
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
